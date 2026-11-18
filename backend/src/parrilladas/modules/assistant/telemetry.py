"""Best-effort numeric observations. Persistence failure must not fail a customer request."""

import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from functools import wraps
from time import monotonic
from uuid import uuid4

from sqlalchemy import text

from .telemetry_contracts import TelemetryEvent, TelemetryReport
from .telemetry_repository import TelemetryRepository

logger = logging.getLogger(__name__)


_trace = ContextVar("gemini_telemetry_trace", default=None)


def telemetry_trace(function):
    @wraps(function)
    def traced(*args, **kwargs):
        if _trace.get() is not None:
            return function(*args, **kwargs)
        token = _trace.set(uuid4())
        try:
            return function(*args, **kwargs)
        finally:
            _trace.reset(token)

    return traced


def number(value):
    if type(value) in (int, float) and 0 <= value <= 10**12 and value == int(value):
        return int(value)
    return None


class Observation:
    def __init__(self, **values):
        self.values = values

    def response(self, response):
        usage = getattr(response, "usage_metadata", None)
        for field, sdk in (
            ("input_tokens", "prompt_token_count"),
            ("output_tokens", "candidates_token_count"),
            ("total_tokens", "total_token_count"),
            ("thinking_tokens", "thoughts_token_count"),
            ("cached_tokens", "cached_content_token_count"),
            ("tool_tokens", "tool_use_prompt_token_count"),
        ):
            self.values[field] = number(getattr(usage, sdk, None))
        metadata = getattr(response, "metadata", None)
        self.values["billable_characters"] = number(
            getattr(metadata, "billable_character_count", None)
        )
        embeddings = getattr(response, "embeddings", None)
        if isinstance(embeddings, list) and len(embeddings) == 1:
            self.values["input_tokens"] = number(
                getattr(getattr(embeddings[0], "statistics", None), "token_count", None)
            )
        candidates = getattr(response, "candidates", None)
        if isinstance(candidates, list) and candidates:
            finish = getattr(candidates[0], "finish_reason", None)
            finish = getattr(finish, "value", finish)
            if isinstance(finish, str) and re.fullmatch(r"[A-Z_0-9]{1,40}", finish):
                self.values["finish_reason"] = finish

    def fail(self, error):
        code = getattr(error, "code", None)
        if type(code) is not int or not 100 <= code <= 599:
            code = None
        name = type(error).__name__
        kind = (
            "invalid_output"
            if isinstance(error, ValueError)
            else "quota"
            if code == 429
            else "authentication"
            if code in (401, 403)
            or name in ("GoogleAuthError", "RefreshError", "DefaultCredentialsError")
            else "timeout"
            if "Timeout" in name
            else "provider"
            if code
            else "transport"
        )
        self.values.update(
            status="invalid_output" if kind == "invalid_output" else "error",
            error_kind=kind,
            http_status=code,
        )


class Telemetry:
    def __init__(self, session_factory=None):
        self.sessions = session_factory
        self.persistence_failures = 0

    @contextmanager
    def measure(self, operation, *, model=None, region=None):
        started = monotonic()
        observation = Observation(
            operation=operation, model=model, region=region, is_model_call=True
        )
        try:
            yield observation
        except Exception as error:
            observation.fail(error)
            raise
        finally:
            self.emit(**observation.values, duration_ms=max(0, int((monotonic() - started) * 1000)))

    def emit(self, **values):
        if self.sessions is None:
            return
        try:
            values.setdefault("trace_id", _trace.get() or uuid4())
            event = TelemetryEvent.model_validate(values)
            with self.sessions() as session, session.begin():
                session.execute(text("SET LOCAL statement_timeout = '500ms'"))
                session.execute(text("SET LOCAL lock_timeout = '200ms'"))
                TelemetryRepository(session).add(event)
        except Exception:
            self.persistence_failures += 1
            # Never log raw exceptions: SQL parameters or provider errors may contain content.
            logger.warning("Gemini telemetry could not be persisted")

    def report(self, *, settings, days, operation=None, page=1, runtime=None):
        now = datetime.now(UTC)
        since = now - timedelta(days=days)
        with self.sessions() as session, session.begin():
            data = TelemetryRepository(session).report(
                since=since, until=now, operation=operation, page=page, hourly=days == 1
            )
        return TelemetryReport(
            days=days,
            operation=operation,
            since=since,
            **data,
            **(runtime or {}),
            generation_model=settings.gemini_model,
            generation_region=settings.google_cloud_location,
            embedding_model=settings.embedding_model,
            embedding_region=settings.embedding_location,
            timeout_ms=settings.assistant_timeout_ms,
            max_output_tokens=settings.assistant_max_output_tokens,
            project_id=settings.google_cloud_project,
            rag_min_similarity=settings.rag_min_similarity,
            persistence_failures_since_start=self.persistence_failures,
        )
