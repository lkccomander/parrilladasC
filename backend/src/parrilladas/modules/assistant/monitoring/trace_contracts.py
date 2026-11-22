"""Closed trace payloads: identifiers and measurements only."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TraceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    chunk_id: UUID
    rank: int = Field(ge=1, le=100)
    score: float = Field(ge=-1, le=1, allow_inf_nan=False)
    used: bool


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    tenant_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    trace_id: UUID
    kind: Literal["online", "eval"] = "online"
    query_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    embedding_model: str = Field(min_length=1, max_length=120)
    embedding_dim: int = Field(ge=1, le=4096)
    embed_ms: int | None = Field(default=None, ge=0, le=10**9)
    search_ms: int | None = Field(default=None, ge=0, le=10**9)
    total_ms: int = Field(ge=0, le=10**9)
    top_k: int = Field(ge=1, le=100)
    score_threshold: float = Field(ge=-1, le=1, allow_inf_nan=False)
    results: list[TraceResult] = Field(default_factory=list, max_length=100)
    used_count: int = Field(ge=0, le=100)
    decision: Literal["grounded", "no_evidence", "catalog_fallback", "bypassed", "error"]
    decision_reason: Literal[
        "grounded",
        "unsupported",
        "disabled",
        "provider_unavailable",
        "invalid_query",
        "no_matches",
        "no_selection",
        "invalid_citation",
        "catalog_fallback",
        "knowledge_not_available",
        "provider_error",
        "internal_error",
    ]
    index_mode: Literal["exact", "hnsw", "ivfflat", "unknown"] = "unknown"
    unsupported_amounts: int | None = Field(default=None, ge=0)
