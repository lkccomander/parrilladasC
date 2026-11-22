"""Trace measurements are observational, private and independent of response success."""

import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from parrilladas.modules.assistant.config import AssistantSettings
from parrilladas.modules.assistant.monitoring.instrumentation import TraceRecorder
from parrilladas.modules.assistant.monitoring.trace_models import RagQueryTrace
from parrilladas.modules.assistant.rag import KnowledgeService
from parrilladas.modules.assistant.rag_contracts import GroundedSelection
from parrilladas.modules.assistant.telemetry import current_trace_id, telemetry_trace


@contextmanager
def captured_session(rows):
    session = Mock()
    session.begin.return_value.__enter__ = Mock()
    session.begin.return_value.__exit__ = Mock(return_value=False)
    session.add.side_effect = rows.append
    yield session


def values():
    return dict(
        tenant_id="parrilladas",
        embedding_model="synthetic-model",
        embedding_dim=768,
        total_ms=5,
        top_k=3,
        score_threshold=0.35,
        used_count=0,
        decision="no_evidence",
        decision_reason="no_matches",
    )


def test_hmac_is_tenant_scoped_and_no_text_or_secret_is_persisted():
    rows = []
    recorder = TraceRecorder(lambda: captured_session(rows), "synthetic-secret")
    recorder.record(query="Synthetic private question", **values())
    recorder.record(query="Synthetic private question", **values())
    recorder.record(query="Synthetic private question", **{**values(), "tenant_id": "other"})
    assert rows[0].query_hash == rows[1].query_hash != rows[2].query_hash
    assert len(rows[0].query_hash) == 64
    assert "private question" not in str(rows[0].__dict__)
    assert "synthetic-secret" not in str(rows[0].__dict__)
    assert rows[0].unsupported_amounts is None


def test_failure_never_logs_payload_or_raw_error(caplog):
    def broken():
        raise RuntimeError("Sensitive synthetic SQL payload")

    recorder = TraceRecorder(broken, "synthetic-secret")
    recorder.record(query="Private synthetic input", **values())
    assert recorder.persistence_failures == 1
    assert "Sensitive" not in caplog.text and "Private" not in caplog.text
    # An extra content field fails closed before persistence.
    recorder.record(query="Private", response="Private response", **values())
    assert recorder.persistence_failures == 2
    assert "Private" not in caplog.text


def test_technical_trace_shared_with_telemetry_and_reset_after_call():
    rows = []
    recorder = TraceRecorder(lambda: captured_session(rows), "synthetic-secret")

    @telemetry_trace
    def run():
        trace = current_trace_id()
        recorder.record(query="Synthetic", **values())
        return trace

    assert current_trace_id() is None
    assert rows == []
    trace = run()
    assert rows[0].trace_id == trace
    assert current_trace_id() is None


def test_recorder_failures_do_not_change_approved_catalog_answer():
    recorder = Mock(record=Mock(side_effect=RuntimeError("Private failure")))
    service = KnowledgeService(None, None, AssistantSettings(_env_file=None), recorder=recorder)
    answer = service.answer("menu", tenant_id="parrilladas")
    assert "Lomito" in answer.text
    assert recorder.record.call_args.kwargs["decision"] == "catalog_fallback"
    assert recorder.record.call_args.kwargs["search_ms"] is None


def test_grounded_trace_records_ranked_evidence_and_selection_without_text(monkeypatch):
    fact_id = str(uuid4())
    fact = SimpleNamespace(
        id=fact_id,
        text="Approved synthetic fact",
        source="synthetic",
        content_version=1,
        similarity=0.8,
    )
    repository = Mock()
    repository.active.return_value = object()
    repository.retrieve.return_value = [fact]
    monkeypatch.setattr(
        "parrilladas.modules.assistant.rag.KnowledgeRepository", lambda _: repository
    )
    rows = []
    recorder = TraceRecorder(lambda: captured_session(rows), "synthetic-secret")
    provider = Mock()
    provider.embed.return_value = [1.0] + [0.0] * 767
    provider.select_facts.return_value = GroundedSelection(fact_ids=[fact_id])
    settings = AssistantSettings(
        rag_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        _env_file=None,
    )
    service = KnowledgeService(lambda: captured_session([]), provider, settings, recorder=recorder)
    result = service.answer(
        "menu", tenant_id="parrilladas", question="Synthetic query", kind="eval"
    )
    assert result.text == fact.text
    trace = rows[0]
    assert trace.kind == "eval" and trace.decision == "grounded"
    assert trace.results == [{"chunk_id": fact_id, "rank": 1, "score": 0.8, "used": True}]
    assert trace.used_count == 1 and trace.unsupported_amounts == 0
    assert trace.embed_ms >= 0 and trace.search_ms >= 0
    assert trace.top_k == 3
    assert "Synthetic query" not in str(trace.__dict__)


@pytest.mark.postgres
def test_trace_migration_and_persistence_only_in_disposable_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an empty disposable PostgreSQL database")
    engine = create_engine(url)
    assert not inspect(engine).get_table_names(), "Use an empty, disposable database"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", url)
        command.upgrade(config, "head")
        try:
            sessions = sessionmaker(engine)
            TraceRecorder(sessions, "synthetic-secret").record(
                query="Private synthetic", **values()
            )
            with sessions() as session:
                row = session.scalar(select(RagQueryTrace))
                assert row.tenant_id == "parrilladas" and row.results == []
                assert row.created_at.tzinfo is not None
                assert row.unsupported_amounts is None
            assert "query" not in {
                c["name"] for c in inspect(engine).get_columns("rag_query_traces")
            }
        finally:
            command.downgrade(config, "base")
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            engine.dispose()


@pytest.mark.parametrize(
    ("failure", "selection", "matches", "decision", "reason"),
    [
        (False, [], True, "no_evidence", "no_selection"),
        (False, [str(uuid4())], True, "no_evidence", "invalid_citation"),
        (False, None, False, "no_evidence", "no_matches"),
        (True, None, True, "catalog_fallback", "catalog_fallback"),
    ],
)
def test_unavailable_and_rejected_evidence_traces_are_truthful(
    monkeypatch, failure, selection, matches, decision, reason
):
    from parrilladas.modules.assistant.errors import ExtractionUnavailable

    fact = SimpleNamespace(id=str(uuid4()), similarity=0.9)
    repository = Mock()
    repository.active.return_value = object()
    repository.retrieve.return_value = [fact] if matches else []
    monkeypatch.setattr(
        "parrilladas.modules.assistant.rag.KnowledgeRepository", lambda _: repository
    )
    provider = Mock()
    provider.embed.return_value = [1.0] + [0.0] * 767
    if failure:
        provider.embed.side_effect = ExtractionUnavailable("Synthetic private error")
    provider.select_facts.return_value = GroundedSelection(fact_ids=selection or [])
    rows = []
    recorder = TraceRecorder(lambda: captured_session(rows), "synthetic-secret")
    settings = AssistantSettings(
        rag_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        _env_file=None,
    )
    service = KnowledgeService(lambda: captured_session([]), provider, settings, recorder=recorder)
    service.answer("menu", tenant_id="parrilladas", question="Private synthetic query")
    assert rows[0].decision == decision and rows[0].decision_reason == reason
    assert rows[0].used_count == 0
    assert rows[0].unsupported_amounts is None
    assert all(not result["used"] for result in rows[0].results)
    assert rows[0].embed_ms >= 0
    assert (rows[0].search_ms is None) == failure


def test_isolation_probe_uses_production_filters_without_calling_models(monkeypatch):
    repository = Mock()
    repository.isolation_probe.return_value = {"probes": 5, "violations": 0}
    monkeypatch.setattr(
        "parrilladas.modules.assistant.rag.KnowledgeRepository", lambda _: repository
    )
    provider = Mock()
    settings = AssistantSettings(_env_file=None)
    service = KnowledgeService(lambda: captured_session([]), provider, settings)
    vector = [1.0] + [0.0] * 767
    result = service.isolation_probe("synthetic-second-tenant", [("menu", vector)] * 7)
    assert result == {"probes": 5, "violations": 0}
    provider.embed.assert_not_called()
    provider.select_facts.assert_not_called()
    args, kwargs = repository.isolation_probe.call_args
    assert args[0] == "synthetic-second-tenant" and len(args[1]) == 5
    assert kwargs == {
        "model": settings.embedding_model,
        "location": settings.embedding_location,
        "minimum": settings.rag_min_similarity,
    }
