"""Operator CLI: import curated JSON, enqueue, execute one job, or read a report."""

import argparse

from sqlalchemy.orm import sessionmaker

from parrilladas.core.config import ApiSettings
from parrilladas.db.session import create_database_engine
from parrilladas.integrations.vertex_ai.client import VertexExtractor
from parrilladas.integrations.vertex_ai.knowledge import VertexKnowledge

from ..config import AssistantSettings
from ..rag import KnowledgeService
from ..telemetry import Telemetry
from .evaluation import EvaluationService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("import")
    load.add_argument("path", help="JSON containing only curated synthetic cases")
    enqueue = commands.add_parser("enqueue")
    enqueue.add_argument("set_id")
    report = commands.add_parser("report")
    report.add_argument("run_id")
    commands.add_parser("run-next")
    commands.add_parser("sets")
    args = parser.parse_args()
    settings = AssistantSettings()
    engine = create_database_engine(ApiSettings())
    sessions = sessionmaker(engine, expire_on_commit=False)
    provider = None
    generation = None
    try:
        # Imports/reports do not instantiate a model client or make Google calls.
        if args.command in {"enqueue", "run-next"} and settings.rag_enabled:
            generation = VertexExtractor.from_settings(settings)
            generation.telemetry = Telemetry(sessions)
            provider = VertexKnowledge.from_settings(settings, generation)
        service = EvaluationService(
            sessions, KnowledgeService(sessions, provider, settings), settings
        )
        if args.command == "import":
            result = service.import_set(args.path)
        elif args.command == "enqueue":
            result = service.enqueue(args.set_id)
        elif args.command == "report":
            result = service.report(args.run_id)
        elif args.command == "run-next":
            result = service.run_next()
        else:
            result = service.sets()
        if isinstance(result, list):
            print("[" + ",".join(item.model_dump_json() for item in result) + "]")
        else:
            print(result.model_dump_json(indent=2) if result else "null")
    finally:
        if provider is not None:
            provider.close()
        if generation is not None:
            generation.close()
        engine.dispose()


if __name__ == "__main__":
    main()
