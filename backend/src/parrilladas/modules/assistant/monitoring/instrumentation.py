"""Best-effort trace recorder. Never log payloads, exceptions or customer text."""

import hashlib
import hmac
import logging
from uuid import uuid4

from ..telemetry import current_trace_id
from .trace_contracts import TraceEvent
from .trace_repository import TraceRepository

logger = logging.getLogger(__name__)


class TraceRecorder:
    def __init__(self, session_factory, secret, retention_days=30):
        self.sessions = session_factory
        secret = secret.get_secret_value() if hasattr(secret, "get_secret_value") else secret
        self.secret = secret.encode() if isinstance(secret, str) else secret
        if not self.secret:
            raise ValueError("A private trace hashing secret is required")
        if not 1 <= retention_days <= 365:
            raise ValueError("Trace retention must be between 1 and 365 days")
        self.retention_days = retention_days
        self.persistence_failures = 0

    def record(self, *, query, **values):
        try:
            # Domain separation prevents correlation with other uses of the API secret.
            tenant = values.get("tenant_id", "")
            digest = hmac.new(
                self.secret,
                b"rag-query-v1\0" + tenant.encode() + b"\0" + query.encode(),
                hashlib.sha256,
            ).hexdigest()
            values.setdefault("trace_id", current_trace_id() or uuid4())
            event = TraceEvent(query_hash=digest, **values)
            with self.sessions() as session, session.begin():
                TraceRepository(session).add(event)
        except Exception:
            self.persistence_failures += 1
            logger.warning("RAG trace could not be persisted")
