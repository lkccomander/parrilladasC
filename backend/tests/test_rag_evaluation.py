"""Synthetic-only evaluation checks; PostgreSQL always disposable."""

import math
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from parrilladas.modules.assistant.config import AssistantSettings
from parrilladas.modules.assistant.knowledge import KnowledgeAnswer, load_menu
from parrilladas.modules.assistant.monitoring.eval_contracts import EvalSetInput
from parrilladas.modules.assistant.monitoring.eval_models import RagEvalCase, RagEvalRun
from parrilladas.modules.assistant.monitoring.evaluation import (
    CaptureProvider,
    EvaluationLimit,
    EvaluationService,
    case_metrics,
)
from parrilladas.modules.assistant.monitoring.metrics import (
    citation_accuracy,
    grounded_text_proxy,
    measured_mean,
    ndcg_at_k,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from parrilladas.modules.assistant.rag import KnowledgeService
from parrilladas.modules.assistant.rag_contracts import GroundedSelection, RetrievedFact


def test_retrieval_metrics_calculated_by_hand():
    ranked, labels = ["x", "a", "b"], ["a", "b", "c"]
    assert recall_at_k(ranked, labels) == pytest.approx(2 / 3)
    assert precision_at_k(ranked, labels) == pytest.approx(2 / 5)
    assert reciprocal_rank(ranked, labels) == 0.5
    assert ndcg_at_k(ranked, labels) == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(4)) / (1 + 1 / math.log2(3) + 1 / math.log2(4))
    )


@pytest.mark.parametrize("metric", [recall_at_k, precision_at_k, reciprocal_rank, ndcg_at_k])
def test_no_labels_are_unknown_and_labeled_empty_results_are_zero(metric):
    assert metric([], []) is None
    assert metric([], ["a"]) == 0


def test_duplicates_never_inflate_retrieval_credit():
    assert recall_at_k(["a", "a"], ["a"]) == 1
    assert precision_at_k(["a", "a"], ["a"]) == 0.2
    assert ndcg_at_k(["a", "a"], ["a"]) == 1
    assert recall_at_k(["x"] * 5 + ["a"], ["a"]) == 0


@pytest.mark.parametrize("metric", [recall_at_k, precision_at_k, ndcg_at_k])
def test_invalid_k_rejected(metric):
    with pytest.raises(ValueError):
        metric([], [], 0)


def test_percentiles_nulls_and_exact_proxy_semantics():
    assert percentile([], 0.95) is None
    assert percentile([5], 0.95) == 5
    assert percentile([0, 10, 20, 30], 0.95) == pytest.approx(28.5)
    assert measured_mean([None, 0.0, 1.0]) == 0.5
    assert measured_mean([None]) is None
    assert citation_accuracy([], ["a"]) is None
    assert citation_accuracy(["a", "invented"], ["a"]) == 0.5
    assert citation_accuracy(["a", "a"], ["a"]) == 0.5
    assert grounded_text_proxy("a\n\nb", ["a", "b"]) == 1
    assert grounded_text_proxy("invented", ["a"]) == 0
    assert grounded_text_proxy("unknown", []) is None
    with pytest.raises(ValueError):
        percentile([float("nan")], 0.95)


def dataset():
    return {
        "name": "Curated synthetic coverage",
        "version": 1,
        "synthetic": True,
        "cases": [
            {
                "question": "¿Cuál es el menú?",
                "topic": "menu",
                "expected_source_ids": ["knowledge/parrilladas/menu.json"],
                "expected_action": "answer",
            }
        ],
    }


def test_dataset_requires_curated_declaration_and_bounded_strict_schema():
    raw = dataset()
    assert EvalSetInput.model_validate(raw).cases[0].language == "es"
    raw.pop("synthetic")
    with pytest.raises(ValidationError):
        EvalSetInput.model_validate(raw)
    raw = dataset()
    raw["tenant_id"] = "untrusted"
    with pytest.raises(ValidationError):
        EvalSetInput.model_validate(raw)
    raw = dataset()
    raw["cases"][0]["expected_chunk_ids"] = [str(uuid4())]
    with pytest.raises(ValidationError):
        EvalSetInput.model_validate(raw)


def test_budget_prevents_unapproved_remote_calls():
    class Provider:
        def embed(self, *args, **kwargs):
            raise AssertionError("No provider call should occur")

    with pytest.raises(EvaluationLimit):
        CaptureProvider(Provider(), max_calls=0, deadline=10**12, call_timeout=1).embed(
            "synthetic", document=False
        )
    with pytest.raises(EvaluationLimit):
        CaptureProvider(Provider(), max_calls=10, deadline=0, call_timeout=1).embed(
            "synthetic", document=False
        )


def test_generation_metrics_never_claim_semantic_judgments_or_real_handoffs():
    fact = RetrievedFact(
        id="a",
        topic="menu",
        text="Approved synthetic fact",
        source="source",
        content_version=1,
        similarity=0.9,
    )
    case = SimpleNamespace(
        expected_chunk_ids=["a"], expected_source_ids=[], expected_action="answer"
    )
    action, metrics = case_metrics(
        case, KnowledgeAnswer(fact.text, "rag:source:v1:a"), [fact], ["a"]
    )
    assert action == "answer"
    assert metrics["faithfulness_proxy"] == 1
    assert metrics["faithfulness"] is None
    assert metrics["answer_relevance"] is None
    assert metrics["correct_handoff_rate"] is None
    assert metrics["language_match"] is None


@pytest.fixture(scope="module")
def evaluation_db():
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
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            engine.dispose()


@pytest.fixture
def evaluations(evaluation_db):
    with evaluation_db() as session, session.begin():
        session.execute(text("TRUNCATE rag_eval_sets, knowledge_documents CASCADE"))

    class Provider:
        def embed(self, question, *, document):
            return [1.0] + [0.0] * 767

        def select_facts(self, question, facts):
            return GroundedSelection(fact_ids=[facts[0].id])

    settings = AssistantSettings(
        rag_enabled=True,
        google_cloud_project="synthetic",
        google_cloud_location="global",
        gemini_model="synthetic",
        _env_file=None,
    )
    knowledge = KnowledgeService(evaluation_db, Provider(), settings)
    knowledge.ingest(load_menu())
    config = SimpleNamespace(
        rag_eval_enabled=True,
        rag_eval_max_cases=20,
        rag_eval_max_calls=40,
        rag_eval_timeout_seconds=120,
    )
    return EvaluationService(evaluation_db, knowledge, config)


@pytest.mark.postgres
def test_import_enqueue_execute_and_tenant_isolation(evaluations):
    service = evaluations
    imported = service.import_set(dataset())
    assert service.import_set(dataset()).id == imported.id
    assert service.sets(tenant_id="other") == []
    with pytest.raises(LookupError):
        service.enqueue(imported.id, tenant_id="other")
    job = service.enqueue(imported.id)
    assert job.status == "queued"
    assert service.enqueue(imported.id).id == job.id
    finished = service.run_next()
    assert finished.status == "completed"
    assert finished.completed_cases == 1
    assert finished.model_calls == 2
    assert finished.metrics["recall_at_5"] == 1
    assert finished.metrics["precision_at_5"] == 0.2
    assert finished.metrics["faithfulness_proxy"] == 1
    assert finished.results[0].answer_text
    with pytest.raises(LookupError):
        service.report(job.id, tenant_id="other")
    assert service.latest(tenant_id="other") is None


@pytest.mark.postgres
def test_version_immutability_and_disabled_run_are_fail_closed(evaluations):
    service = evaluations
    imported = service.import_set(dataset())
    changed = dataset()
    changed["cases"][0]["question"] = "¿Qué carnes ofrecen?"
    with pytest.raises(ValueError, match="version"):
        service.import_set(changed)
    service.settings.rag_eval_enabled = False
    with pytest.raises(ValueError, match="disabled"):
        service.enqueue(imported.id)
    assert service.run_next() is None


@pytest.mark.postgres
def test_budget_exhaustion_is_durable_and_never_reruns(evaluations):
    service = evaluations
    imported = service.import_set(dataset())
    service.settings.rag_eval_max_calls = 1
    job = service.enqueue(imported.id)
    result = service.run_next()
    assert result.status == "failed"
    assert result.error_kind == "budget_exhausted"
    assert result.model_calls == 1
    assert service.run_next() is None
    assert service.report(job.id).status == "failed"


@pytest.mark.postgres
def test_database_blocks_foreign_tenant_evaluation_links(evaluations):
    imported = evaluations.import_set(dataset())
    with pytest.raises(IntegrityError), evaluations.sessions() as session, session.begin():
        session.add(
            RagEvalCase(
                tenant_id="other",
                set_id=imported.id,
                position=0,
                question="Synthetic",
                topic="menu",
                language="es",
                expected_chunk_ids=[],
                expected_source_ids=[],
                expected_action=None,
            )
        )
        session.flush()


@pytest.mark.postgres
def test_advisory_lock_prevents_parallel_jobs(evaluations):
    imported = evaluations.import_set(dataset())
    evaluations.enqueue(imported.id)
    with evaluations.sessions() as session, session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(419078115)"))
        assert evaluations.run_next() is None
    assert evaluations.run_next().status == "completed"


@pytest.mark.postgres
def test_interrupted_running_job_is_failed_without_second_provider_call(evaluations):
    from datetime import UTC, datetime, timedelta

    imported = evaluations.import_set(dataset())
    job = evaluations.enqueue(imported.id)
    with evaluations.sessions() as session, session.begin():
        row = session.get(RagEvalRun, job.id)
        row.status = "running"
        row.started_at = datetime.now(UTC) - timedelta(hours=1)
    assert evaluations.run_next() is None
    assert evaluations.report(job.id).error_kind == "worker_interrupted"
