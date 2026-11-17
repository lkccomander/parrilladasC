"""Public contracts for approved business knowledge; vectors never cross the Admin boundary."""

import math
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

DIMENSIONS = 768
SOURCE = "knowledge/parrilladas/menu.json"
RagTopic = Literal["menu", "coverage", "preparation"]


class RetrievedFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    topic: RagTopic
    text: str
    source: str
    content_version: int
    similarity: float


class GroundedSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_ids: list[str] = Field(max_length=3)


class KnowledgeDocumentView(BaseModel):
    source: str
    content_version: int
    content_hash: str
    embedding_model: str
    embedding_location: str
    dimensions: int = DIMENSIONS
    facts: list[RetrievedFact]


class KnowledgeOverview(BaseModel):
    enabled: bool
    documents: list[KnowledgeDocumentView]


class RagProvider(Protocol):
    def embed(self, text: str, *, document: bool) -> list[float]: ...
    def select_facts(self, question: str, facts: list[RetrievedFact]) -> GroundedSelection: ...


def validated_vector(values) -> list[float]:
    if values is None or len(values) != DIMENSIONS:
        raise ValueError("Invalid embedding dimensions")
    vector = [float(value) for value in values]
    if not all(math.isfinite(value) for value in vector) or not any(vector):
        raise ValueError("Invalid embedding values")
    return vector
