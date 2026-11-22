"""HTTP-only monitoring contracts shared with the separate Admin service."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MetricStatus = Literal["ok", "watch", "breach", "not_measured"]


class Metric(BaseModel):
    key: str
    label: str
    value: float | None = None
    display: str = "No medido"
    target_text: str = ""
    status: MetricStatus = "not_measured"
    note: str = ""


class IndexInfo(BaseModel):
    mode: str = "unknown"
    name: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)
    checks: list[dict[str, float | int | str | None]] = Field(default_factory=list)
    note: str = ""


class TraceSummary(BaseModel):
    id: UUID
    created_at: datetime
    kind: str
    decision: str
    decision_reason: str | None = None
    used_count: int
    total_ms: int


class TraceResult(BaseModel):
    chunk_id: UUID
    rank: int
    score: float
    used: bool
    title: str | None = None
    source: str | None = None
    content_version: int | None = None


class TraceDetail(TraceSummary):
    query_hash: str
    query_text: str | None = None
    embed_ms: int | None = None
    search_ms: int | None = None
    top_k: int
    score_threshold: float
    embedding_model: str
    embedding_dim: int
    index_mode: str
    unsupported_amounts: int | None = None
    top1_gap: float | None = None
    results: list[TraceResult] = Field(default_factory=list)


class KnowledgeRow(BaseModel):
    source: str
    content_version: int
    status: str
    valid_until: datetime | None = None
    chunks: int
    created_at: datetime


class AlertView(BaseModel):
    rule_key: str
    severity: str
    message: str
    first_seen: datetime
    last_seen: datetime
    detail: dict[str, str | int | float | None] = Field(default_factory=dict)


class EvalSetSummary(BaseModel):
    id: UUID
    name: str
    version: int
    cases: int


class EvalRunView(BaseModel):
    id: UUID
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics: dict[str, float | None] = Field(default_factory=dict)
    error: str | None = None


class MonitoringReport(BaseModel):
    days: int
    generated_at: datetime
    tenant_id: str
    last_eval_run_at: datetime | None = None
    kpis: list[Metric] = Field(default_factory=list)
    retrieval_metrics: list[Metric] = Field(default_factory=list)
    generation_metrics: list[Metric] = Field(default_factory=list)
    vector_health: list[Metric] = Field(default_factory=list)
    index: IndexInfo = Field(default_factory=IndexInfo)
    traces: list[TraceSummary] = Field(default_factory=list)
    knowledge: list[KnowledgeRow] = Field(default_factory=list)
    alerts: list[AlertView] = Field(default_factory=list)
    eval_sets: list[EvalSetSummary] = Field(default_factory=list)
    price_table_updated_at: str | None = None
    latency_series: list[float] = Field(default_factory=list)
    eval_enabled: bool = False
