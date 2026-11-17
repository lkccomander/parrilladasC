from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.genai import types

from parrilladas.integrations.vertex_ai.knowledge import VertexKnowledge
from parrilladas.modules.assistant.errors import ExtractionUnavailable
from parrilladas.modules.assistant.rag_contracts import RetrievedFact


def provider():
    return VertexKnowledge(Mock(), Mock(model="synthetic-generation"), model="gemini-embedding-001")


def test_embedding_uses_distinct_query_document_tasks_and_bounded_dimensions():
    p = provider()
    p.embedding.client.models.embed_content.return_value = SimpleNamespace(
        embeddings=[SimpleNamespace(values=[1.0] + [0.0] * 767, statistics=None)]
    )
    for document, task in ((True, "RETRIEVAL_DOCUMENT"), (False, "RETRIEVAL_QUERY")):
        assert len(p.embed("synthetic text", document=document)) == 768
        config = p.embedding.client.models.embed_content.call_args.kwargs["config"]
        assert config.task_type == task
        assert config.output_dimensionality == 768 and config.auto_truncate is False


@pytest.mark.parametrize(
    "embeddings",
    [
        None,
        [],
        [SimpleNamespace(values=[1.0], statistics=None)],
        [SimpleNamespace(values=[1.0] * 768, statistics=SimpleNamespace(truncated=True))],
    ],
)
def test_incomplete_or_truncated_embeddings_fail_closed(embeddings):
    p = provider()
    p.embedding.client.models.embed_content.return_value = SimpleNamespace(embeddings=embeddings)
    with pytest.raises(ExtractionUnavailable):
        p.embed("synthetic text", document=False)


def test_generation_only_selects_ids_without_tools_or_arbitrary_prose():
    p = provider()
    p.generation.client.models.generate_content.return_value = SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
        text='{"fact_ids":["approved"]}',
    )
    fact = RetrievedFact(
        id="approved",
        topic="menu",
        text="Lomito",
        source="approved.json",
        content_version=1,
        similarity=0.9,
    )
    assert p.select_facts("¿Qué ofrecen?", [fact]).fact_ids == ["approved"]
    config = p.generation.client.models.generate_content.call_args.kwargs["config"]
    assert config.tools == []
    assert config.max_output_tokens == 256
    p.generation.client.models.generate_content.return_value.text = (
        '{"fact_ids":["approved"],"answer":"Precio inventado"}'
    )
    with pytest.raises(ExtractionUnavailable):
        p.select_facts("¿Qué ofrecen?", [fact])
