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


@pytest.mark.postgres
def test_advisor_upgrade_preserves_existing_conversation_and_message(monkeypatch):
    from uuid import uuid4

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
        command.upgrade(config, "0005")
        conversation_id, message_id = uuid4(), uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO conversations "
                    "(id,created_at,whatsapp_number,bot_paused,flow_step,flow_data) "
                    "VALUES (:id,now(),'15550000001',true,'nl_review',cast(:data as jsonb))"
                ),
                {
                    "id": conversation_id,
                    "data": '{"request_reference":"PEC-LEGACY","guest_count":20}',
                },
            )
            connection.execute(
                text(
                    "INSERT INTO messages "
                    "(id,created_at,conversation_id,direction,content,delivery_status) "
                    "VALUES (:id,now(),:conversation_id,'inbound',"
                    "'Synthetic migration message','received')"
                ),
                {"id": message_id, "conversation_id": conversation_id},
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = (
                connection.execute(
                    text("select bot_paused,flow_step,flow_data from conversations where id=:id"),
                    {"id": conversation_id},
                )
                .mappings()
                .one()
            )
            assert row["bot_paused"] and row["flow_step"] == "nl_review"
            assert row["flow_data"] == {"request_reference": "PEC-LEGACY", "guest_count": 20}
            message = (
                connection.execute(
                    text("select purpose,interaction_id,recipient from messages where id=:id"),
                    {"id": message_id},
                )
                .mappings()
                .one()
            )
            assert message == {"purpose": "customer", "interaction_id": None, "recipient": None}
            assert connection.scalar(text("select count(*) from conversation_interactions")) == 0
    finally:
        try:
            if owns_empty_database:
                command.downgrade(config, "base")
                with engine.begin() as connection:
                    connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        finally:
            engine.dispose()
