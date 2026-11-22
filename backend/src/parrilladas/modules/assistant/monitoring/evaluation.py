"""Explicit, bounded synthetic jobs using the real knowledge service; no LLM judge."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..rag import KnowledgeService
from .eval_contracts import EvalCaseResultView, EvalRunView, EvalSetInput, EvalSetView
from .eval_models import RagEvalCase, RagEvalCaseResult, RagEvalRun, RagEvalSet
from .eval_repository import EvaluationRepository
from .metrics import (
    citation_accuracy,
    grounded_text_proxy,
    measured_mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

LOCK_ID = 419078115


class EvaluationLimit(Exception):
    """A preflight budget or deadline was exhausted before making another call."""


class CaptureProvider:
    def __init__(self, provider, *, max_calls, deadline, call_timeout):
        self.provider = provider
        self.max_calls = max_calls
        self.deadline = deadline
        self.call_timeout = call_timeout
        self.calls = 0
        self.facts = []
        self.selection = []

    def _reserve(self):
        # Reserve a full configured provider timeout before starting any new call.
        if self.calls >= self.max_calls or monotonic() + self.call_timeout > self.deadline:
            raise EvaluationLimit("Evaluation budget exhausted")
        self.calls += 1

    def embed(self, text, *, document):
        self._reserve()
        return self.provider.embed(text, document=document)

    def select_facts(self, question, facts):
        self.facts = facts
        self._reserve()
        result = self.provider.select_facts(question, facts)
        self.selection = list(result.fact_ids)
        return result


def case_metrics(case, answer, facts, selected):
    labels = case.expected_chunk_ids or case.expected_source_ids
    ranked = [fact.id if case.expected_chunk_ids else fact.source for fact in facts]
    actual_action = "answer" if answer.source else "no_evidence"
    selected_texts = [
        fact.text for identifier in selected for fact in facts if fact.id == identifier
    ]
    # Catalog fallback is not scored as retrieved evidence.
    grounded = bool(answer.source and answer.source.startswith("rag:"))
    return actual_action, {
        "recall_at_5": recall_at_k(ranked, labels),
        "precision_at_5": precision_at_k(ranked, labels),
        "mrr": reciprocal_rank(ranked, labels),
        "ndcg_at_5": ndcg_at_k(ranked, labels),
        "citation_accuracy": citation_accuracy(selected, [fact.id for fact in facts]),
        "faithfulness_proxy": grounded_text_proxy(answer.text, selected_texts)
        if grounded
        else None,
        "correct_action_rate": float(actual_action == case.expected_action)
        if case.expected_action
        else None,
        "correct_handoff_rate": None,
        "empty_result_rate": float(not facts),
        "faithfulness": None,
        "answer_relevance": None,
        "context_relevance": None,
        "language_match": None,
        "unsupported_amounts": None,
    }


class EvaluationService:
    def __init__(self, session_factory, knowledge, settings):
        self.sessions = session_factory
        self.knowledge = knowledge
        self.settings = settings

    def import_set(self, data, *, tenant_id="parrilladas"):
        if isinstance(data, (str, Path)):
            path = Path(data)
            if path.stat().st_size > 1_000_000:
                raise ValueError("Evaluation JSON is too large")
            data = json.loads(path.read_text(encoding="utf-8"))
        dataset = EvalSetInput.model_validate(data)
        digest = hashlib.sha256(dataset.model_dump_json().encode()).hexdigest()
        with self.sessions() as session, session.begin():
            repo = EvaluationRepository(session)
            existing = repo.find_set(tenant_id, dataset.name, dataset.version)
            if existing is not None:
                if existing.content_hash != digest:
                    raise ValueError("Increment evaluation set version before editing cases")
                return self._set_view(existing, len(dataset.cases))
            row = repo.add(
                RagEvalSet(
                    tenant_id=tenant_id,
                    name=dataset.name,
                    version=dataset.version,
                    content_hash=digest,
                )
            )
            for position, case in enumerate(dataset.cases):
                repo.add(
                    RagEvalCase(
                        tenant_id=tenant_id,
                        set_id=row.id,
                        position=position,
                        **case.model_dump(mode="json"),
                    )
                )
            return self._set_view(row, len(dataset.cases))

    def enqueue(self, set_id, *, tenant_id="parrilladas"):
        if not getattr(self.settings, "rag_eval_enabled", False):
            raise ValueError("Synthetic Gemini evaluations are disabled")
        if self.knowledge.provider is None or not self.knowledge.settings.rag_enabled:
            raise ValueError("The real knowledge provider is unavailable")
        try:
            with self.sessions() as session, session.begin():
                repo = EvaluationRepository(session)
                if repo.get_set(set_id, tenant_id) is None:
                    raise LookupError("Evaluation set not found")
                pending = repo.pending(tenant_id)
                if pending is not None:
                    return self._run_view(pending)
                count = len(repo.cases(set_id, tenant_id))
                if count > getattr(self.settings, "rag_eval_max_cases", 20):
                    raise ValueError("Evaluation set exceeds configured case budget")
                row = repo.add(
                    RagEvalRun(
                        tenant_id=tenant_id,
                        set_id=set_id,
                        status="queued",
                        case_count=count,
                        completed_cases=0,
                        model_calls=0,
                        metrics={},
                    )
                )
                return self._run_view(row)
        except IntegrityError as error:
            raise ValueError("An evaluation is already pending for this tenant") from error

    def run_next(self):
        if not getattr(self.settings, "rag_eval_enabled", False):
            return None
        # Transaction-scoped advisory lock holds a bounded worker transaction on a
        # dedicated connection. It never locks customer tables or calls their worker.
        with self.sessions() as lock_session, lock_session.begin():
            acquired = lock_session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_ID}
            )
            if not acquired:
                return None
            timeout = getattr(self.settings, "rag_eval_timeout_seconds", 120)
            with self.sessions() as session, session.begin():
                job = EvaluationRepository(session).claim(timeout + 120)
                if job is None:
                    return None
                run_id, tenant_id, set_id = job.id, job.tenant_id, job.set_id
            self._execute(run_id, tenant_id, set_id, timeout)
            return self.report(run_id, tenant_id=tenant_id)

    def _execute(self, run_id, tenant_id, set_id, timeout):
        started = monotonic()
        provider = CaptureProvider(
            self.knowledge.provider,
            max_calls=getattr(self.settings, "rag_eval_max_calls", 40),
            deadline=started + timeout,
            call_timeout=self.knowledge.settings.assistant_timeout_ms / 1000,
        )
        knowledge = KnowledgeService(self.sessions, provider, self.knowledge.settings)
        failure = None
        collected = []
        try:
            with self.sessions() as session, session.begin():
                cases = EvaluationRepository(session).cases(set_id, tenant_id)
                session.expunge_all()
            if len(cases) > getattr(self.settings, "rag_eval_max_cases", 20):
                raise EvaluationLimit("Case budget exhausted")
            for case in cases:
                if monotonic() >= provider.deadline:
                    raise EvaluationLimit("Deadline exhausted")
                provider.facts, provider.selection = [], []
                case_started = monotonic()
                answer = knowledge.answer(case.topic, tenant_id=tenant_id, question=case.question)
                action, metrics = case_metrics(case, answer, provider.facts, provider.selection)
                collected.append(metrics)
                with self.sessions() as session, session.begin():
                    repo = EvaluationRepository(session)
                    repo.add(
                        RagEvalCaseResult(
                            tenant_id=tenant_id,
                            run_id=run_id,
                            set_id=set_id,
                            case_id=case.id,
                            retrieved=[fact.model_dump(mode="json") for fact in provider.facts],
                            selected_ids=provider.selection,
                            answer_text=answer.text,
                            actual_action=action,
                            duration_ms=int((monotonic() - case_started) * 1000),
                            metrics=metrics,
                            error_kind=None,
                        )
                    )
                    job = repo.get_run(run_id, tenant_id)
                    job.completed_cases = len(collected)
                    job.model_calls = provider.calls
        except EvaluationLimit:
            failure = "budget_exhausted"
        except Exception:
            # Curated text is intentionally not included in operational error logs.
            failure = "evaluation_failed"
        with self.sessions() as session, session.begin():
            job = EvaluationRepository(session).get_run(run_id, tenant_id)
            job.status = "failed" if failure else "completed"
            job.completed_at = datetime.now(UTC)
            job.error_kind = failure
            job.model_calls = provider.calls
            job.metrics = (
                {key: measured_mean(row[key] for row in collected) for key in collected[0]}
                if collected
                else {}
            )

    def report(self, run_id, *, tenant_id="parrilladas"):
        with self.sessions() as session, session.begin():
            repo = EvaluationRepository(session)
            row = repo.get_run(UUID(str(run_id)), tenant_id)
            if row is None:
                raise LookupError("Evaluation run not found")
            result = self._run_view(row)
            result.results = [
                EvalCaseResultView(
                    question=question,
                    **{
                        field: getattr(entry, field)
                        for field in EvalCaseResultView.model_fields
                        if field != "question"
                    },
                )
                for entry, question in repo.results(row.id, tenant_id)
            ]
            return result

    def latest(self, *, tenant_id="parrilladas"):
        with self.sessions() as session, session.begin():
            row = EvaluationRepository(session).latest(tenant_id)
            return self._run_view(row) if row else None

    def sets(self, *, tenant_id="parrilladas"):
        with self.sessions() as session, session.begin():
            return [
                self._set_view(row, count)
                for row, count in EvaluationRepository(session).sets(tenant_id)
            ]

    @staticmethod
    def _set_view(row, count):
        return EvalSetView(
            id=row.id,
            name=row.name,
            version=row.version,
            case_count=count,
            created_at=row.created_at,
        )

    @staticmethod
    def _run_view(row):
        return EvalRunView(
            **{
                field: getattr(row, field)
                for field in (
                    "id",
                    "set_id",
                    "status",
                    "created_at",
                    "started_at",
                    "completed_at",
                    "case_count",
                    "completed_cases",
                    "model_calls",
                    "error_kind",
                    "metrics",
                )
            }
        )
