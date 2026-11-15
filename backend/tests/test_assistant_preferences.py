import os
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.orm import Session

from parrilladas.admin import create_app as create_admin
from parrilladas.core.config import AdminSettings, ApiSettings
from parrilladas.main import create_app
from parrilladas.modules.accounts.contracts import Role
from parrilladas.modules.accounts.errors import AccessDenied
from parrilladas.modules.accounts.schemas import AccountCreate
from parrilladas.modules.accounts.service import AccountService
from parrilladas.modules.assistant.models import AssistantPreference
from parrilladas.modules.assistant.preferences import AssistantPreferenceService
from parrilladas.modules.assistant.schemas import AssistantPreferencesUpdate
from parrilladas.modules.conversations.models import Conversation

pytestmark = pytest.mark.postgres
PASSWORD = "synthetic assistant passphrase 123"


def csrf(response):
    return re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text).group(1)


@pytest.fixture(scope="module")
def preference_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an empty, disposable PostgreSQL database")
    engine = create_engine(url)
    assert not inspect(engine).get_table_names(), "Use an empty, disposable test database"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("DATABASE_URL", url)
        command.upgrade(config, "head")
        try:
            with Session(engine, expire_on_commit=False) as session:
                accounts = AccountService(session)
                admin = accounts.bootstrap_admin(
                    AccountCreate(
                        email="assistant-admin@example.com",
                        display_name="Assistant Admin",
                        role=Role.ADMIN,
                        password=PASSWORD,
                    )
                )
                sales = accounts.create_account(
                    admin.id,
                    AccountCreate(
                        email="assistant-sales@example.com",
                        display_name="Assistant Sales",
                        role=Role.SALES,
                        password=PASSWORD,
                    ),
                )
            yield SimpleNamespace(engine=engine, url=url, admin=admin, sales=sales)
        finally:
            command.downgrade(config, "base")
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            engine.dispose()


@pytest.fixture
def preference_client(preference_database):
    db = preference_database
    with Session(db.engine) as session, session.begin():
        session.execute(delete(AssistantPreference))
    settings = ApiSettings(
        app_env="test",
        database_url=db.url,
        jwt_secret="synthetic-preferences-signing-key-32-characters",
        _env_file=None,
    )
    with (
        TestClient(create_app(settings)) as api,
        TestClient(
            create_admin(AdminSettings(app_env="test", _env_file=None), api_http=api)
        ) as client,
    ):
        yield SimpleNamespace(api=api, client=client, db=db)


def login(state, *, sales=False):
    response = state.client.post(
        "/login",
        data={
            "csrf_token": csrf(state.client.get("/login")),
            "email": state.db.sales.email if sales else state.db.admin.email,
            "password": PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    token = state.client.cookies.get("parrilladas_session")
    headers = {"Authorization": f"Bearer {token}"}
    context = state.api.get("/auth/me", headers=headers).json()
    return {**headers, "X-CSRF-Token": context["csrf_token"]}


def test_anonymous_preferences_require_authentication(preference_client):
    state = preference_client
    assert state.api.get("/assistant/preferences").status_code == 401
    assert (
        state.api.patch(
            "/assistant/preferences", json={"natural_language_enabled": True}
        ).status_code
        == 401
    )
    response = state.client.get("/dashboard/assistant", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == "/login"


def test_default_is_disabled_and_read_does_not_create_a_row(preference_client):
    state = preference_client
    headers = login(state)
    response = state.api.get("/assistant/preferences", headers=headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "tenant_id": "parrilladas",
        "natural_language_enabled": False,
        "active_mode": "guided",
        "updated_at": None,
        "updated_by": None,
    }
    with Session(state.db.engine) as session:
        assert session.scalar(select(AssistantPreference)) is None


def test_database_default_is_disabled(preference_client):
    state = preference_client
    with state.db.engine.begin() as connection:
        enabled = connection.execute(
            text(
                "INSERT INTO assistant_preferences (tenant_id, updated_at, updated_by) "
                "VALUES (:tenant, :now, :actor) RETURNING natural_language_enabled"
            ),
            {"tenant": "parrilladas", "now": datetime.now(UTC), "actor": state.db.admin.id},
        ).scalar_one()
    assert enabled is False


def test_preference_survives_api_restart_and_records_actor_and_time(preference_client):
    state = preference_client
    headers = login(state)
    response = state.api.patch(
        "/assistant/preferences", headers=headers, json={"natural_language_enabled": True}
    )
    assert response.status_code == 200
    assert response.json()["natural_language_enabled"] is True
    assert response.json()["active_mode"] == "guided"
    assert response.json()["updated_by"] == str(state.db.admin.id)
    assert datetime.fromisoformat(response.json()["updated_at"]).tzinfo is not None
    # A new API app/engine must read the persisted preference, not a process-local flag.
    settings = ApiSettings(
        app_env="test",
        database_url=state.db.url,
        jwt_secret="synthetic-preferences-signing-key-32-characters",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get("/assistant/preferences", headers=headers).json() == response.json()


def test_api_mutation_requires_csrf_and_sales_are_denied(preference_client):
    state = preference_client
    headers = login(state)
    for csrf_token in (None, "wrong"):
        supplied = {key: value for key, value in headers.items() if key != "X-CSRF-Token"}
        if csrf_token:
            supplied["X-CSRF-Token"] = csrf_token
        assert (
            state.api.patch(
                "/assistant/preferences", headers=supplied, json={"natural_language_enabled": True}
            ).status_code
            == 403
        )
    state.client.cookies.clear()
    headers = login(state, sales=True)
    assert state.api.get("/assistant/preferences", headers=headers).status_code == 403
    assert (
        state.api.patch(
            "/assistant/preferences", headers=headers, json={"natural_language_enabled": True}
        ).status_code
        == 403
    )
    assert state.client.get("/dashboard/assistant").status_code == 403
    assert (
        state.client.post(
            "/dashboard/assistant", data={"csrf_token": headers["X-CSRF-Token"]}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"natural_language_enabled": "true"},
        {"natural_language_enabled": 1},
        {"natural_language_enabled": True, "tenant_id": "another-business"},
        {"natural_language_enabled": True, "active_mode": "natural_language"},
    ],
)
def test_api_rejects_coercion_missing_values_and_client_scope(preference_client, payload):
    state = preference_client
    response = state.api.patch("/assistant/preferences", headers=login(state), json=payload)
    assert response.status_code == 422
    with Session(state.db.engine) as session:
        assert session.scalar(select(AssistantPreference)) is None


def test_reads_and_writes_are_scoped_to_server_business(preference_client):
    state = preference_client
    with Session(state.db.engine) as session, session.begin():
        session.add(
            AssistantPreference(
                tenant_id="another-business",
                natural_language_enabled=True,
                updated_at=datetime.now(UTC),
                updated_by=state.db.admin.id,
            )
        )
    headers = login(state)
    response = state.api.get("/assistant/preferences?tenant_id=another-business", headers=headers)
    assert response.json()["tenant_id"] == "parrilladas"
    assert response.json()["natural_language_enabled"] is False
    for enabled in (True, False):
        assert (
            state.api.patch(
                "/assistant/preferences",
                headers=headers,
                json={"natural_language_enabled": enabled},
            ).json()["natural_language_enabled"]
            is enabled
        )
    with Session(state.db.engine) as session:
        assert session.get(AssistantPreference, "parrilladas").natural_language_enabled is False
        assert session.get(AssistantPreference, "another-business").natural_language_enabled is True


def test_preference_does_not_resume_a_conversation_or_modify_its_data(preference_client):
    state = preference_client
    with Session(state.db.engine) as session, session.begin():
        conversation = Conversation(
            whatsapp_number="50600000000",
            bot_paused=True,
            flow_step="guest_count",
            flow_data={"guest_count": "20"},
        )
        session.add(conversation)
        session.flush()
        conversation_id = conversation.id
    try:
        headers = login(state)
        assert (
            state.api.patch(
                "/assistant/preferences", headers=headers, json={"natural_language_enabled": True}
            ).status_code
            == 200
        )
        with Session(state.db.engine) as session:
            saved = session.get(Conversation, conversation_id)
            assert saved.bot_paused
            assert saved.flow_step == "guest_count"
            assert saved.flow_data == {"guest_count": "20"}
    finally:
        with Session(state.db.engine) as session, session.begin():
            session.execute(delete(Conversation).where(Conversation.id == conversation_id))


def test_dashboard_form_forwards_authenticated_csrf_and_displays_pending_activation(
    preference_client,
):
    state = preference_client
    login(state)
    page = state.client.get("/dashboard/assistant")
    assert page.status_code == 200
    assert 'aria-current="page"' in page.text
    assert "Modo actual:</strong> Guiado" in page.text
    dashboard = state.client.get("/dashboard")
    assert dashboard.status_code == 200
    assert 'aria-label="Modo de atención actual">Modo guiado' in dashboard.text
    assert 'id="guided-mode-heading">Modo guiado' in dashboard.text
    assert 'id="natural-mode-heading">Lenguaje natural' in dashboard.text
    assert ">Inactivo</span>" in dashboard.text
    response = state.client.post(
        "/dashboard/assistant",
        data={"csrf_token": csrf(page), "natural_language_enabled": "on"},
    )
    assert response.status_code == 200
    assert "Preferencia guardada." in response.text
    assert "Activación pendiente" in response.text
    assert "Preferencia guardada:</strong> Lenguaje natural" in response.text
    assert "Modo actual:</strong> Guiado" in response.text
    dashboard = state.client.get("/dashboard")
    assert 'aria-label="Modo de atención actual">Modo guiado' in dashboard.text
    assert ">Activación pendiente</span>" in dashboard.text
    response = state.client.post("/dashboard/assistant", data={"csrf_token": csrf(response)})
    assert "Preferencia guardada:</strong> Guiado" in response.text
    with Session(state.db.engine) as session:
        assert session.get(AssistantPreference, "parrilladas").natural_language_enabled is False


def test_dashboard_csrf_cross_site_and_invalid_fields_cannot_change_preference(preference_client):
    state = preference_client
    login(state)
    token = csrf(state.client.get("/dashboard/assistant"))
    for payload, headers, status in (
        ({"natural_language_enabled": "on"}, {}, 403),
        ({"csrf_token": "wrong", "natural_language_enabled": "on"}, {}, 403),
        ({"csrf_token": token}, {"Sec-Fetch-Site": "cross-site"}, 403),
        ({"csrf_token": token, "natural_language_enabled": "anything"}, {}, 422),
        ({"csrf_token": token, "tenant_id": "another-business"}, {}, 422),
    ):
        response = state.client.post("/dashboard/assistant", data=payload, headers=headers)
        assert response.status_code == status
    with Session(state.db.engine) as session:
        assert session.scalar(select(AssistantPreference)) is None


def test_service_rejects_non_admin_and_inactive_actors(preference_database):
    db = preference_database
    for actor in (db.sales, db.admin.model_copy(update={"is_active": False})):
        with Session(db.engine) as session:
            service = AssistantPreferenceService(session)
            with pytest.raises(AccessDenied):
                service.get(actor)
            with pytest.raises(AccessDenied):
                service.update(actor, AssistantPreferencesUpdate(natural_language_enabled=True))
