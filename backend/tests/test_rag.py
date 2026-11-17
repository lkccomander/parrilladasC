import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from parrilladas.modules.assistant.config import AssistantSettings
from parrilladas.modules.assistant.errors import ExtractionUnavailable
from parrilladas.modules.assistant.knowledge import load_menu
from parrilladas.modules.assistant.models import KnowledgeDocument
from parrilladas.modules.assistant.rag import KnowledgeService
from parrilladas.modules.assistant.rag_contracts import GroundedSelection, validated_vector


class Provider:
    def __init__(self):
        self.calls = 0
        self.failure = False
        self.selection = None

    def embed(self, body, *, document):
        self.calls += 1
        if self.failure:
            raise ExtractionUnavailable("Synthetic failure")
        return [1.0] + [0.0] * 767

    def select_facts(self, question, facts):
        if self.selection is not None:
            return self.selection
        return GroundedSelection(fact_ids=[facts[0].id])


@pytest.fixture(scope="module")
def rag_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an empty, disposable PostgreSQL database")
    engine = create_engine(url)
    assert not inspect(engine).get_table_names(), "Use an empty, disposable database"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", url)
        command.upgrade(config, "head")
        try:
            yield sessionmaker(engine, expire_on_commit=False)
        finally:
            command.downgrade(config, "base")
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            engine.dispose()


@pytest.fixture
def rag(rag_database):
    with rag_database() as session, session.begin():
        session.execute(text("TRUNCATE knowledge_documents CASCADE"))
    provider = Provider()
    settings = AssistantSettings(
        rag_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        _env_file=None,
    )
    return KnowledgeService(rag_database, provider, settings), provider


@pytest.mark.postgres
def test_ingestion_publishes_real_vectors_idempotently_and_retrieves_only_tenant(rag):
    service, provider = rag
    assert service.ingest(load_menu()) == "published"
    assert provider.calls == 3
    assert service.ingest(load_menu()) == "unchanged"
    assert provider.calls == 3
    overview = service.overview(tenant_id="parrilladas")
    assert len(overview.documents) == 1
    assert len(overview.documents[0].facts) == 3
    assert overview.documents[0].dimensions == 768
    assert service.overview(tenant_id="other").documents == []
    result = service.answer("menu", tenant_id="parrilladas", question="¿Qué carnes ofrecen?")
    assert result.source.startswith("rag:")
    assert "Lomito" in result.text
    assert service.answer("menu", tenant_id="other").source is None


@pytest.mark.postgres
def test_atomic_update_and_version_policy_preserve_previous_knowledge(rag):
    service, provider = rag
    menu = load_menu()
    service.ingest(menu)
    changed = menu.model_copy(update={"prepared_on_site": False})
    with pytest.raises(ValueError, match="content_version"):
        service.ingest(changed)
    next_version = changed.model_copy(update={"content_version": menu.content_version + 1})
    provider.failure = True
    with pytest.raises(ExtractionUnavailable):
        service.ingest(next_version)
    assert service.overview(tenant_id="parrilladas").documents[0].content_version == 1
    provider.failure = False
    assert service.ingest(next_version) == "published"
    overview = service.overview(tenant_id="parrilladas")
    assert overview.documents[0].content_version == 2
    assert len(overview.documents[0].facts) == 2
    with service.sessions() as session:
        documents = session.scalars(select(KnowledgeDocument)).all()
        assert len(documents) == 2
        assert sum(doc.active for doc in documents) == 1


@pytest.mark.postgres
@pytest.mark.parametrize("selection", [[], ["invented-id"], ["a", "a"]])
def test_missing_or_forged_evidence_never_becomes_an_answer(rag, selection):
    service, provider = rag
    service.ingest(load_menu())
    provider.selection = GroundedSelection(fact_ids=selection)
    answer = service.answer("menu", tenant_id="parrilladas", question="¿Tienen salmón?")
    assert answer.source is None
    assert "confirmarlo" in answer.text
    assert "Lomito" not in answer.text


@pytest.mark.postgres
def test_failure_uses_approved_fallback_but_sensitive_topics_never_call_models(rag):
    service, provider = rag
    service.ingest(load_menu())
    provider.failure = True
    assert "Lomito" in service.answer("menu", tenant_id="parrilladas").text
    calls = provider.calls
    for topic in ("pricing", "availability", "allergens", "policies"):
        assert service.answer(topic, tenant_id="parrilladas").source is None
    assert provider.calls == calls


@pytest.mark.postgres
def test_low_similarity_and_wrong_embedding_profile_fail_closed(rag):
    service, provider = rag
    service.ingest(load_menu())
    provider.embed = Mock(return_value=[0.0, 1.0] + [0.0] * 766)
    assert service.answer("menu", tenant_id="parrilladas").source is None
    provider.embed = Mock(return_value=[1.0] + [0.0] * 767)
    with service.sessions() as session, session.begin():
        doc = session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.active))
        doc.embedding_model = "different-space"
    assert service.answer("menu", tenant_id="parrilladas").source is None


@pytest.mark.parametrize(
    "vector", [None, [], [1.0] * 767, [0.0] * 768, [float("nan")] * 768, [float("inf")] * 768]
)
def test_invalid_vectors_are_rejected_before_sql(vector):
    with pytest.raises(ValueError):
        validated_vector(vector)


def test_conversation_passes_customer_question_and_keeps_the_draft():
    import json

    from parrilladas.modules.assistant.knowledge import KnowledgeAnswer
    from parrilladas.modules.assistant.service import AssistantService
    from parrilladas.modules.conversations.contracts import IncomingText
    from parrilladas.modules.conversations.natural_language import natural_language_decision

    provider = Mock(
        extract=Mock(
            return_value=json.dumps({"intent": "business_question", "topic": "menu", "details": {}})
        )
    )
    knowledge = Mock(answer=Mock(return_value=KnowledgeAnswer("Menú aprobado", "rag:test")))
    assistant = AssistantService(provider, enabled=True, knowledge=knowledge)
    result = natural_language_decision(
        "nl_review",
        IncomingText("¿Qué carnes ofrecen?"),
        {"_nl_draft": {"guest_count": 20}},
        assistant,
    )
    knowledge.answer.assert_called_once_with(
        "menu", tenant_id="parrilladas", question="¿Qué carnes ofrecen?"
    )
    assert result.text == "Menú aprobado"
    assert not result.updates and not result.handoff
