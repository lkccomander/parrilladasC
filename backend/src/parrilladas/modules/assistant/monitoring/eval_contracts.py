"""Curated synthetic evaluation contracts, safe to import from Admin."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvalCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)
    topic: Literal["menu", "coverage", "preparation", "policies", "pricing", "availability"]
    language: Literal["es"] = "es"
    expected_chunk_ids: list[UUID] = Field(default_factory=list, max_length=100)
    expected_source_ids: list[str] = Field(default_factory=list, max_length=100)
    expected_action: Literal["answer", "no_evidence"] | None = None

    @model_validator(mode="after")
    def distinct_label_kind(self):
        if not self.question.strip():
            raise ValueError("A nonblank curated question is required")
        if self.expected_chunk_ids and self.expected_source_ids:
            raise ValueError("Choose chunk or source labels, not both")
        if any(not value.strip() or len(value) > 120 for value in self.expected_source_ids):
            raise ValueError("Source IDs must be bounded and nonblank")
        return self


class EvalSetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1, strict=True)
    synthetic: Literal[True]
    cases: list[EvalCaseInput] = Field(min_length=1, max_length=100)


class EvalSetView(BaseModel):
    id: UUID
    name: str
    version: int
    case_count: int
    created_at: datetime


class EvalCaseResultView(BaseModel):
    case_id: UUID
    question: str
    answer_text: str | None
    retrieved: list[dict]
    selected_ids: list[str]
    actual_action: str
    duration_ms: int
    metrics: dict[str, float | None]
    error_kind: str | None


class EvalRunView(BaseModel):
    id: UUID
    set_id: UUID
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    case_count: int
    completed_cases: int
    model_calls: int
    error_kind: str | None
    metrics: dict[str, float | None]
    retrieval_k: int = 3
    metric_k: int = 5
    note: str = (
        "Evaluación sintética del recuperador actual (máximo 3 candidatos); "
        "métricas @5 sin ampliar búsqueda."
    )
    results: list[EvalCaseResultView] = Field(default_factory=list)
