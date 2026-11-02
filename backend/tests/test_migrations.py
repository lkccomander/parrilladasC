import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from parrilladas.core.config import ApiSettings
from parrilladas.db import models  # noqa: F401
from parrilladas.db.base import Base
from parrilladas.main import create_app


@pytest.mark.postgres
def test_migration_round_trip_and_model_consistency(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an empty, disposable PostgreSQL database")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    engine = create_engine(url)
    owns_empty_database = False
    try:
        assert not inspect(engine).get_table_names(), "Use an empty, disposable test database"
        owns_empty_database = True
        command.upgrade(config, "head")
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            assert compare_metadata(context, Base.metadata) == []
        with TestClient(
            create_app(ApiSettings(jwt_secret="test-only-signing-key-at-least-32-characters"))
        ) as client:
            assert client.get("/health/ready").status_code == 200
        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
        command.upgrade(config, "head")
    finally:
        try:
            if owns_empty_database:
                command.downgrade(config, "base")
                with engine.begin() as connection:
                    connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        finally:
            engine.dispose()
