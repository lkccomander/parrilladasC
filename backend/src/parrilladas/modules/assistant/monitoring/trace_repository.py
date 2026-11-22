"""Short trace writes; caller owns the transaction."""

from sqlalchemy import text

from .trace_models import RagQueryTrace


class TraceRepository:
    def __init__(self, session):
        self.session = session

    def add(self, event):
        self.session.execute(text("SET LOCAL statement_timeout = '500ms'"))
        self.session.execute(text("SET LOCAL lock_timeout = '200ms'"))
        payload = event.model_dump()
        payload["results"] = [r.model_dump(mode="json") for r in event.results]
        self.session.add(RagQueryTrace(**payload))
