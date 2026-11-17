"""Publish the approved editable menu. Never ingest customer messages or arbitrary documents."""

import argparse

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

import parrilladas.db.models  # noqa: F401
from parrilladas.core.config import ApiSettings
from parrilladas.db.session import create_database_engine
from parrilladas.integrations.vertex_ai.client import VertexExtractor
from parrilladas.integrations.vertex_ai.knowledge import VertexKnowledge

from .config import AssistantSettings
from .errors import ExtractionUnavailable
from .knowledge import load_menu
from .rag import KnowledgeService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["ingest", "show"])
    arguments = parser.parse_args()
    engine = generator = provider = None
    try:
        settings = AssistantSettings()
        engine = create_database_engine(ApiSettings())
        if arguments.command == "ingest":
            menu = load_menu()
            if menu is None:
                raise ValueError("Approved catalog unavailable")
            generator = VertexExtractor.from_settings(settings)
            provider = VertexKnowledge.from_settings(settings, generator)
            service = KnowledgeService(sessionmaker(engine), provider, settings)
            print(service.ingest(menu))
        else:
            service = KnowledgeService(sessionmaker(engine), None, settings)
        print(service.overview(tenant_id="parrilladas").model_dump_json(indent=2))
        return 0
    except (ExtractionUnavailable, SQLAlchemyError, ValidationError, ValueError):
        print("Knowledge operation failed; no partial catalog was published.")
        return 1
    finally:
        if provider is not None:
            provider.close()
        if generator is not None:
            generator.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
