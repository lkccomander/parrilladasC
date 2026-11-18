"""Allowlisted numeric telemetry. Never accept prompts, replies or customer identifiers."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

Operation = Literal[
    "extraction",
    "embedding_document",
    "embedding_query",
    "grounding",
    "extraction_result",
    "rag_result",
]
Status = Literal["ok", "error", "invalid_output", "no_evidence", "fallback"]
Reason = Literal[
    "disabled",
    "human_control",
    "provider_unavailable",
    "invalid_output",
    "unsupported",
    "knowledge_not_available",
    "requested_handoff",
    "review_required",
    "no_matches",
    "no_selection",
    "invalid_citation",
    "catalog_fallback",
    "grounded",
    "invalid_query",
]
ErrorKind = Literal["authentication", "quota", "timeout", "provider", "transport", "invalid_output"]


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: UUID = Field(default_factory=uuid4)
    tenant_id: Literal["parrilladas"] = "parrilladas"
    operation: Operation
    status: Status = "ok"
    is_model_call: bool = False
    model: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=40)
    duration_ms: int = Field(default=0, ge=0)
    error_kind: ErrorKind | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    finish_reason: str | None = Field(default=None, pattern=r"^[A-Z_0-9]{1,40}$")
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    thinking_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    tool_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    billable_characters: int | None = Field(default=None, ge=0)
    reason: Reason | None = None
    result_count: int | None = Field(default=None, ge=0, le=3)
    selected_count: int | None = Field(default=None, ge=0, le=3)
    similarity: float | None = Field(default=None, ge=-1, le=1)


class TelemetryRow(TelemetryEvent):
    id: UUID
    created_at: datetime


class MetricGroup(BaseModel):
    operation: str
    model: str | None = None
    calls: int
    errors: int
    p50_ms: float | None = None
    p95_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class TimelinePoint(BaseModel):
    at: datetime
    calls: int
    errors: int
    total_tokens: int | None = None


class TelemetryReport(BaseModel):
    days: int
    operation: Operation | None = None
    since: datetime
    first_recorded_at: datetime | None
    calls: int
    errors: int
    quota_errors: int
    usage_reported_calls: int
    error_rate: float | None
    p50_ms: float | None
    p95_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    thinking_tokens: int | None
    cached_tokens: int | None
    tool_tokens: int | None
    total_tokens: int | None
    billable_characters: int | None
    rag_p50_ms: float | None
    rag_p95_ms: float | None
    rag_answers: int
    rag_no_evidence: int
    rag_fallbacks: int
    extraction_invalid: int
    groups: list[MetricGroup]
    timeline: list[TimelinePoint]
    recent: list[TelemetryRow]
    page: int
    page_size: int = 50
    total_events: int
    natural_language_available: bool = False
    rag_available: bool = False
    generation_model: str | None = None
    generation_region: str | None = None
    embedding_model: str | None = None
    embedding_region: str | None = None
    timeout_ms: int
    max_output_tokens: int

    project_id: str | None = None
    rag_min_similarity: float
    persistence_failures_since_start: int = 0
