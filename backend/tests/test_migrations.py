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


@pytest.mark.postgres
def test_multiple_roles_migration_preserves_access_without_granting_dev(monkeypatch):
    from uuid import uuid4

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Use an empty, disposable PostgreSQL database")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    engine = create_engine(url)
    owns_empty_database = False
    try:
        assert not inspect(engine).get_table_names(), "Use an empty, disposable test database"
        owns_empty_database = True
        command.upgrade(config, "0008")
        admin_id, sales_id = uuid4(), uuid4()
        with engine.begin() as connection:
            for account_id, role in ((admin_id, "admin"), (sales_id, "sales")):
                connection.execute(
                    text(
                        "INSERT INTO accounts "
                        "(id,created_at,email,display_name,password_hash,role,is_active) "
                        "VALUES (:id,now(),:email,'Migration fixture',"
                        "'not-a-live-password',:role,true)"
                    ),
                    {"id": account_id, "email": role + "@example.com", "role": role},
                )
        command.upgrade(config, "head")
        with engine.begin() as connection:
            rows = connection.execute(text("SELECT role,roles FROM accounts ORDER BY role")).all()
            assert rows == [("admin", ["admin"]), ("sales", ["sales"])]
            connection.execute(
                text("UPDATE accounts SET role='dev',roles=ARRAY['dev'] WHERE id=:id"),
                {"id": sales_id},
            )
        command.downgrade(config, "0008")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT role FROM accounts WHERE id=:id"), {"id": sales_id})
                == "admin"
            )
    finally:
        if owns_empty_database:
            command.downgrade(config, "base")
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        engine.dispose()
