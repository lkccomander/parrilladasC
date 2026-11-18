import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from google.genai import types
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from parrilladas.integrations.vertex_ai.client import VertexExtractor
from parrilladas.modules.assistant.config import AssistantSettings
from parrilladas.modules.assistant.models import GeminiTelemetry
from parrilladas.modules.assistant.schemas import ExtractionRequest
from parrilladas.modules.assistant.telemetry import Observation, Telemetry
from parrilladas.modules.assistant.telemetry_contracts import TelemetryEvent


def test_metadata_capture_preserves_unknown_counts_and_never_copies_text():
    span = Observation(operation="extraction")
    span.response(
        SimpleNamespace(
            text="PRIVATE REPLY",
            usage_metadata=SimpleNamespace(
                prompt_token_count=12,
                candidates_token_count=3,
                total_token_count=17,
                thoughts_token_count=2,
                cached_content_token_count=4,
                tool_use_prompt_token_count=0,
            ),
            candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
        )
    )
    assert span.values["input_tokens"] == 12
    assert span.values["output_tokens"] == 3
    assert span.values["total_tokens"] == 17
    assert span.values["thinking_tokens"] == 2
    assert span.values["cached_tokens"] == 4
    assert span.values["finish_reason"] == "STOP"
    assert "PRIVATE" not in str(span.values)
    absent = Observation()
    absent.response(SimpleNamespace())
    assert absent.values["total_tokens"] is None
    embed = Observation()
    embed.response(
        SimpleNamespace(
            metadata=SimpleNamespace(billable_character_count=80),
            embeddings=[SimpleNamespace(statistics=SimpleNamespace(token_count=9.0))],
        )
    )
    assert embed.values["billable_characters"] == 80
    assert embed.values["input_tokens"] == 9
    assert embed.values["total_tokens"] is None


def test_observation_sanitizes_error_without_message_or_credentials():
    error = RuntimeError("SECRET TOKEN AND CUSTOMER TEXT")
    error.code = 429
    span = Observation()
    span.fail(error)
    assert span.values == {"status": "error", "error_kind": "quota", "http_status": 429}
    span.fail(ValueError("private model output"))
    assert span.values["status"] == "invalid_output"
    assert "private" not in str(span.values)


def test_telemetry_failure_cannot_break_a_successful_model_call(caplog):
    telemetry = Telemetry(Mock(side_effect=RuntimeError("PRIVATE DB CONFIG")))
    sdk = Mock()
    sdk.models.generate_content.return_value = SimpleNamespace(
        text='{"intent":"quote"}',
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
    )
    extractor = VertexExtractor(sdk, model="synthetic", telemetry=telemetry)
    assert extractor.extract(ExtractionRequest(message="PRIVATE QUESTION")) == '{"intent":"quote"}'
    assert telemetry.persistence_failures == 1
    assert "PRIVATE" not in caplog.text
    assert "could not be persisted" in caplog.text


@pytest.mark.parametrize(
    "extra",
    [
        {"prompt": "private"},
        {"reply": "private"},
        {"phone": "15550000001"},
        {"customer_id": "private"},
        {"reason": "private customer text"},
    ],
)
def test_telemetry_contract_rejects_customer_content(extra):
    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate({"operation": "extraction", **extra})


@pytest.fixture(scope="module")
def telemetry_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an empty, disposable PostgreSQL database")
    engine = create_engine(url)
    assert not inspect(engine).get_table_names(), "Use an empty, disposable database"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", url)
        command.upgrade(config, "head")
        try:
            yield sessionmaker(engine, expire_on_commit=False)
        finally:
            command.downgrade(config, "base")
            with engine.begin() as c:
                c.execute(text("DROP TABLE IF EXISTS alembic_version"))
            engine.dispose()


@pytest.fixture
def telemetry(telemetry_database):
    with telemetry_database() as session, session.begin():
        session.execute(text("TRUNCATE gemini_telemetry"))
    return Telemetry(telemetry_database)


@pytest.mark.postgres
def test_sql_aggregation_uses_real_percentiles_tenant_scope_and_no_double_counting(telemetry):
    now = datetime.now(UTC)
    events = [
        TelemetryEvent(
            operation="extraction",
            is_model_call=True,
            model="synthetic",
            region="global",
            duration_ms=100,
            input_tokens=10,
            output_tokens=2,
            thinking_tokens=3,
            total_tokens=15,
            cached_tokens=2,
        ),
        TelemetryEvent(
            operation="grounding",
            is_model_call=True,
            model="synthetic",
            duration_ms=300,
            status="error",
            error_kind="quota",
            http_status=429,
        ),
        TelemetryEvent(
            operation="embedding_query",
            is_model_call=True,
            model="embedding",
            duration_ms=200,
            input_tokens=5,
            billable_characters=20,
        ),
        TelemetryEvent(operation="rag_result", reason="grounded", result_count=1, selected_count=1),
    ]
    with telemetry.sessions() as session, session.begin():
        for event in events:
            session.add(
                GeminiTelemetry(**event.model_dump(), created_at=now - timedelta(minutes=5))
            )
        for stamp, tenant in [
            (now - timedelta(days=8), "parrilladas"),
            (now + timedelta(days=1), "parrilladas"),
            (now, "other-business"),
        ]:
            values = events[0].model_dump()
            values["tenant_id"] = tenant
            session.add(GeminiTelemetry(**values, created_at=stamp))
    result = telemetry.report(settings=AssistantSettings(_env_file=None), days=7)
    assert result.calls == 3 and result.total_events == 4 and result.errors == 1
    assert result.rag_answers == 1 and result.quota_errors == 1
    assert result.p50_ms == 200 and result.p95_ms == pytest.approx(290)
    assert result.input_tokens == 15 and result.output_tokens == 2 and result.total_tokens == 15
    assert result.cached_tokens == 2 and result.thinking_tokens == 3
    assert result.usage_reported_calls == 1
    assert len(result.timeline) == 1 and result.timeline[0].calls == 3
    assert len(result.groups) == 3
    assert all(e.tenant_id == "parrilladas" for e in result.recent)
    filtered = telemetry.report(
        settings=AssistantSettings(_env_file=None), days=7, operation="embedding_query"
    )
    assert filtered.calls == 1 and filtered.total_tokens is None
    assert filtered.input_tokens == 5 and filtered.billable_characters == 20


@pytest.mark.postgres
def test_recent_events_are_paginated_without_fake_model_usage(telemetry):
    with telemetry.sessions() as session, session.begin():
        for _ in range(51):
            session.add(
                GeminiTelemetry(
                    **TelemetryEvent(
                        operation="rag_result", status="no_evidence", reason="no_matches"
                    ).model_dump()
                )
            )
    a = telemetry.report(settings=AssistantSettings(_env_file=None), days=1)
    b = telemetry.report(settings=AssistantSettings(_env_file=None), days=1, page=2)
    assert a.calls == 0 and a.error_rate is None and a.total_tokens is None
    assert a.total_events == 51 and a.rag_no_evidence == 51
    assert len(a.recent) == 50 and len(b.recent) == 1
    assert not ({r.id for r in a.recent} & {r.id for r in b.recent})


@pytest.mark.postgres
def test_capture_persists_success_failure_and_usage_even_for_incomplete_output(telemetry):
    sdk = Mock()
    sdk.models.generate_content.return_value = SimpleNamespace(
        text=None,
        usage_metadata=SimpleNamespace(prompt_token_count=8, total_token_count=8),
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.MAX_TOKENS)],
    )
    from parrilladas.modules.assistant.errors import ExtractionUnavailable

    extractor = VertexExtractor(sdk, model="synthetic", region="global", telemetry=telemetry)
    with pytest.raises(ExtractionUnavailable):
        extractor.extract(ExtractionRequest(message="Synthetic request"))
    result = telemetry.report(settings=AssistantSettings(_env_file=None), days=1)
    assert result.calls == 1 and result.errors == 1
    assert result.total_tokens == 8 and result.recent[0].finish_reason == "MAX_TOKENS"
    assert result.recent[0].status == "invalid_output"


@pytest.mark.postgres
def test_trace_groups_nested_steps_and_resets_between_requests(telemetry):
    from parrilladas.modules.assistant.telemetry import telemetry_trace

    @telemetry_trace
    def inner():
        telemetry.emit(operation="rag_result", status="no_evidence", reason="no_matches")

    @telemetry_trace
    def request():
        telemetry.emit(operation="extraction_result", reason="knowledge_not_available")
        inner()

    request()
    request()
    result = telemetry.report(settings=AssistantSettings(_env_file=None), days=1)
    from collections import Counter

    assert sorted(Counter(r.trace_id for r in result.recent).values()) == [2, 2]
