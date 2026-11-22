"""SQL for bounded tenant-scoped evaluation jobs; transactions belong to service."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from .eval_models import RagEvalCase, RagEvalCaseResult, RagEvalRun, RagEvalSet


class EvaluationRepository:
    def __init__(self, session):
        self.session = session

    def sets(self, tenant_id):
        return self.session.execute(
            select(RagEvalSet, func.count(RagEvalCase.id))
            .join(RagEvalCase, RagEvalCase.set_id == RagEvalSet.id)
            .where(RagEvalSet.tenant_id == tenant_id, RagEvalCase.tenant_id == tenant_id)
            .group_by(RagEvalSet.id)
            .order_by(RagEvalSet.created_at.desc())
            .limit(100)
        ).all()

    def find_set(self, tenant_id, name, version):
        return self.session.scalar(
            select(RagEvalSet).where(
                RagEvalSet.tenant_id == tenant_id,
                RagEvalSet.name == name,
                RagEvalSet.version == version,
            )
        )

    def get_set(self, set_id, tenant_id):
        return self.session.scalar(
            select(RagEvalSet).where(RagEvalSet.id == set_id, RagEvalSet.tenant_id == tenant_id)
        )

    def cases(self, set_id, tenant_id):
        return list(
            self.session.scalars(
                select(RagEvalCase)
                .where(RagEvalCase.set_id == set_id, RagEvalCase.tenant_id == tenant_id)
                .order_by(RagEvalCase.position)
                .limit(101)
            )
        )

    def get_run(self, run_id, tenant_id):
        return self.session.scalar(
            select(RagEvalRun).where(RagEvalRun.id == run_id, RagEvalRun.tenant_id == tenant_id)
        )

    def latest(self, tenant_id):
        return self.session.scalar(
            select(RagEvalRun)
            .where(RagEvalRun.tenant_id == tenant_id)
            .order_by(RagEvalRun.created_at.desc())
            .limit(1)
        )

    def pending(self, tenant_id):
        return self.session.scalar(
            select(RagEvalRun)
            .where(RagEvalRun.tenant_id == tenant_id, RagEvalRun.status.in_(["queued", "running"]))
            .limit(1)
        )

    def claim(self, maximum_age_seconds):
        now = datetime.now(UTC)
        # A worker terminated mid-call is failed rather than rerun and double-billed.
        self.session.execute(
            update(RagEvalRun)
            .where(
                RagEvalRun.status == "running",
                RagEvalRun.started_at < now - timedelta(seconds=maximum_age_seconds),
            )
            .values(status="failed", error_kind="worker_interrupted", completed_at=now)
        )
        job = self.session.scalar(
            select(RagEvalRun)
            .where(RagEvalRun.status == "queued")
            .order_by(RagEvalRun.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is not None:
            job.status = "running"
            job.started_at = now
        return job

    def results(self, run_id, tenant_id):
        return self.session.execute(
            select(RagEvalCaseResult, RagEvalCase.question)
            .join(RagEvalCase, RagEvalCase.id == RagEvalCaseResult.case_id)
            .where(
                RagEvalCaseResult.run_id == run_id,
                RagEvalCaseResult.tenant_id == tenant_id,
                RagEvalCase.tenant_id == tenant_id,
            )
            .order_by(RagEvalCase.position)
            .limit(100)
        ).all()

    def add(self, row):
        self.session.add(row)
        self.session.flush()
        return row
