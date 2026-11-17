import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, inspect, text
from sqlalchemy.orm import Session

from parrilladas.admin import create_app as create_admin
from parrilladas.core.config import AdminSettings, ApiSettings
from parrilladas.main import create_app
from parrilladas.modules.accounts.contracts import Role
from parrilladas.modules.accounts.schemas import AccountCreate
from parrilladas.modules.accounts.service import AccountService
from parrilladas.modules.conversations.models import Conversation, Interaction
from parrilladas.modules.dashboard.client import AdminApiClient, ApiUnavailable

pytestmark = pytest.mark.postgres
PASSWORD = "synthetic interaction password 123"
API_PATH = "/conversations/interactions"
ADMIN_PATH = "/dashboard/interactions"


@pytest.fixture(scope="module")
def interaction_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an empty, disposable PostgreSQL database")
    engine = create_engine(url)
    assert not inspect(engine).get_table_names(), "Use an empty, disposable test database"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", url)
        command.upgrade(config, "head")
        try:
            with Session(engine, expire_on_commit=False) as session:
                service = AccountService(session)
                admin = service.bootstrap_admin(
                    AccountCreate(
                        email="interactions-admin@example.com",
                        display_name="Synthetic Admin",
                        role=Role.ADMIN,
                        password=PASSWORD,
                    )
                )
                service.create_account(
                    admin.id,
                    AccountCreate(
                        email="interactions-sales@example.com",
                        display_name="Synthetic Sales",
                        role=Role.SALES,
                        password=PASSWORD,
                    ),
                )
            yield engine, url
        finally:
            command.downgrade(config, "base")
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            engine.dispose()


@pytest.fixture
def interactions_client(interaction_database):
    engine, url = interaction_database
    with Session(engine) as session, session.begin():
        session.execute(delete(Interaction))
        session.execute(delete(Conversation))
        conversations = [
            Conversation(whatsapp_number=f"1555000000{i}", bot_paused=True) for i in (1, 2)
        ]
        session.add_all(conversations)
        session.flush()
        for i in range(28):
            draft = {
                "event_date": "2027-06-03",
                "guest_count": "7",
                "location": "Guachipelín",
                "service_type": "parrilla",
            }
            if i == 27:
                draft["location"] = "<script>unsafe()</script>"
            session.add(
                Interaction(
                    conversation_id=conversations[i % 2].id,
                    reference=f"PEC-SYNTHETIC-{i:02}",
                    status="active" if i == 27 else ("referred" if i == 1 else "submitted"),
                    created_at=datetime(2026, 11, 15, 1, tzinfo=UTC) + timedelta(minutes=i),
                    closed_at=None if i == 27 else datetime(2026, 11, 15, 2, tzinfo=UTC),
                    snapshot={"_nl_draft": draft, "private_metadata": "synthetic-hidden"}
                    if i == 27
                    else draft,
                )
            )
    settings = ApiSettings(
        app_env="test",
        database_url=url,
        jwt_secret="synthetic-interaction-signing-key-32-characters",
        _env_file=None,
    )
    with (
        TestClient(create_app(settings)) as api,
        TestClient(
            create_admin(AdminSettings(app_env="test", _env_file=None), api_http=api)
        ) as admin,
    ):
        yield SimpleNamespace(api=api, admin=admin, engine=engine)


def login(state, role="admin"):
    token = re.search(r'name="csrf_token"\s+value="([^"]+)"', state.admin.get("/login").text).group(
        1
    )
    response = state.admin.post(
        "/login",
        data={
            "csrf_token": token,
            "email": f"interactions-{role}@example.com",
            "password": PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return {"Authorization": f"Bearer {state.admin.cookies.get('parrilladas_session')}"}


def test_interactions_require_a_logged_in_account(interactions_client):
    state = interactions_client
    assert state.api.get(API_PATH).status_code == 401
    response = state.admin.get(ADMIN_PATH, follow_redirects=False)
    assert response.status_code == 303 and response.headers["Location"] == "/login"
    state.admin.get("/login")
    headers = {"Authorization": f"Bearer {state.admin.cookies.get('parrilladas_session')}"}
    assert state.api.get(API_PATH, headers=headers).status_code == 401


@pytest.mark.parametrize("role", ["admin", "sales"])
def test_admin_and_sales_can_browse_search_and_filter_independent_interactions(
    interactions_client, role
):
    state = interactions_client
    headers = login(state, role)
    response = state.api.get(API_PATH, headers=headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()
    assert (data["total"], data["page_size"], len(data["items"])) == (28, 25, 25)
    assert data["items"][0]["reference"] == "PEC-SYNTHETIC-27"
    assert data["items"][0]["guest_count"] == 7
    assert data["items"][0]["bot_paused"] is True
    assert "private_metadata" not in response.text and "synthetic-hidden" not in response.text
    following = state.api.get(API_PATH, headers=headers, params={"page": 2}).json()
    assert [row["reference"] for row in following["items"]] == [
        "PEC-SYNTHETIC-02",
        "PEC-SYNTHETIC-01",
        "PEC-SYNTHETIC-00",
    ]
    for status, count in [("active", 1), ("submitted", 26), ("referred", 1)]:
        filtered = state.api.get(API_PATH, headers=headers, params={"status": status}).json()
        assert filtered["total"] == count
        assert all(row["status"] == status for row in filtered["items"])
        if status != "active":
            assert all(not row["bot_paused"] for row in filtered["items"])
    assert (
        state.api.get(API_PATH, headers=headers, params={"q": "+1 (555) 000-0002"}).json()["total"]
        == 14
    )
    assert (
        state.api.get(API_PATH, headers=headers, params={"q": "pec-synthetic-27"}).json()["total"]
        == 1
    )
    assert state.api.get(API_PATH, headers=headers, params={"q": "%"}).json()["total"] == 0
    page = state.admin.get(ADMIN_PATH)
    assert page.status_code == 200 and page.headers["Cache-Control"] == "no-store"
    assert "Bot pausado" in page.text and "Registrada" in page.text
    assert "14/11/2026 19:27" in page.text
    assert "&lt;script&gt;unsafe()&lt;/script&gt;" in page.text
    assert "<script>unsafe()" not in page.text
    assert "page=2" in page.text
    assert 'href="/dashboard/interactions"' in state.admin.get("/dashboard").text
    empty = state.admin.get(ADMIN_PATH, params={"q": "not-found", "status": "submitted"})
    assert "No hay interacciones para mostrar" in empty.text
    assert 'value="not-found"' in empty.text
    assert 'value="submitted" selected' in empty.text


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"page": 100001}, {"status": "unknown"}, {"q": "x" * 101}]
)
def test_interaction_filters_are_validated_on_admin_and_api(interactions_client, params):
    state = interactions_client
    headers = login(state)
    assert state.api.get(API_PATH, headers=headers, params=params).status_code == 422
    assert state.admin.get(ADMIN_PATH, params=params).status_code == 422


def test_admin_shows_an_honest_error_if_api_is_unavailable(interactions_client, monkeypatch):
    state = interactions_client
    login(state)

    def unavailable(self, filters):
        raise ApiUnavailable

    monkeypatch.setattr(AdminApiClient, "list_interactions", unavailable)
    page = state.admin.get(ADMIN_PATH)
    assert page.status_code == 503
    assert "No pudimos cargar las interacciones" in page.text
    assert "PEC-SYNTHETIC" not in page.text
