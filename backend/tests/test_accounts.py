import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.orm import Session

from parrilladas.core.config import Settings
from parrilladas.main import create_app
from parrilladas.modules.accounts.errors import AccessDenied, AccountConflict
from parrilladas.modules.accounts.models import Account, AuthSession, LoginAttempt, Role
from parrilladas.modules.accounts.schemas import AccountCreate, AccountUpdate, PasswordReset
from parrilladas.modules.accounts.security import token_digest, verify_password
from parrilladas.modules.accounts.service import AccountService

pytestmark = pytest.mark.postgres
PASSWORD = "testing a long passphrase 123"


@pytest.fixture(scope="module")
def account_database():
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
            yield engine, url
        finally:
            command.downgrade(config, "base")
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            engine.dispose()


@pytest.fixture
def account_client(account_database):
    engine, url = account_database
    with Session(engine) as session, session.begin():
        for model in (AuthSession, LoginAttempt, Account):
            session.execute(delete(model))
    with Session(engine, expire_on_commit=False) as session:
        admin = AccountService(session).bootstrap_admin(
            AccountCreate(
                email="admin@example.com",
                display_name="Admin de prueba",
                role=Role.ADMIN,
                password=PASSWORD,
            )
        )
    with TestClient(
        create_app(Settings(app_env="test", database_url=url, _env_file=None))
    ) as client:
        yield client, engine, admin


def csrf(response):
    return re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text).group(1)


def login(client, email="admin@example.com", password=PASSWORD):
    token = csrf(client.get("/login"))
    return client.post(
        "/login",
        data={"csrf_token": token, "email": email, "password": password},
        follow_redirects=False,
    )


def account_form(client, *, email="sales@example.com", name="Ventas", role="sales"):
    token = csrf(client.get("/dashboard/accounts/new"))
    return {
        "csrf_token": token,
        "email": email,
        "display_name": name,
        "role": role,
        "password": PASSWORD,
    }


def test_login_rotates_session_and_logout_revokes_it(account_client):
    client, engine, _ = account_client
    initial = client.get("/login")
    anonymous = client.cookies.get("parrilladas_session")
    response = client.post(
        "/login",
        data={"csrf_token": csrf(initial), "email": "ADMIN@EXAMPLE.COM", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    authenticated = client.cookies.get("parrilladas_session")
    assert authenticated != anonymous
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Admin de prueba" in dashboard.text
    assert dashboard.headers["cache-control"] == "no-store"
    with Session(engine) as session:
        assert (
            session.scalar(
                select(AuthSession).where(AuthSession.token_hash == token_digest(anonymous))
            )
            is None
        )
        persisted = session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_digest(authenticated))
        )
        assert persisted.token_hash != authenticated
    response = client.post("/logout", data={"csrf_token": csrf(dashboard)}, follow_redirects=False)
    assert response.status_code == 303
    client.cookies.set("parrilladas_session", authenticated)
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_csrf_enforced_for_login_and_all_mutations(account_client):
    client, _, _ = account_client
    client.get("/login")
    assert (
        client.post("/login", data={"email": "admin@example.com", "password": PASSWORD}).status_code
        == 403
    )
    assert login(client).status_code == 303
    form = account_form(client)
    without_token = {key: value for key, value in form.items() if key != "csrf_token"}
    assert client.post("/dashboard/accounts/new", data=without_token).status_code == 403
    assert (
        client.post("/dashboard/accounts/new", data={**form, "csrf_token": "wrong"}).status_code
        == 403
    )
    assert (
        client.post(
            "/dashboard/accounts/new", data=form, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert client.post("/logout", data={"csrf_token": ""}).status_code == 403
    # The CSRF header also supports a future HTMX client.
    assert (
        client.post(
            "/dashboard/accounts/new",
            data=without_token,
            headers={"X-CSRF-Token": form["csrf_token"]},
            follow_redirects=False,
        ).status_code
        == 303
    )


def test_admin_create_edit_deactivate_reactivate_and_password_reset(account_client):
    client, engine, admin = account_client
    login(client)
    form = account_form(client, name='<script>alert("x")</script>')
    assert (
        client.post("/dashboard/accounts/new", data=form, follow_redirects=False).status_code == 303
    )
    listing = client.get("/dashboard/accounts")
    assert "&lt;script&gt;" in listing.text
    assert '<script>alert("x")</script>' not in listing.text
    with Session(engine) as session:
        sales = session.scalar(select(Account).where(Account.email == "sales@example.com"))
        sales_id = sales.id
        assert verify_password(sales.password_hash, PASSWORD)
        assert sales.password_hash != PASSWORD
    with TestClient(client.app) as sales_client:
        assert login(sales_client, "sales@example.com").status_code == 303
        assert sales_client.get("/dashboard").status_code == 200
        edit = client.get(f"/dashboard/accounts/{sales_id}")
        update = {
            "csrf_token": csrf(edit),
            "email": "sales@example.com",
            "display_name": "Ventas",
            "role": "sales",
            "password": "",
            "is_active": "on",
        }
        new_password = "changed long passphrase 456"
        assert (
            client.post(
                f"/dashboard/accounts/{sales_id}",
                data={**update, "password": new_password},
                follow_redirects=False,
            ).status_code
            == 303
        )
        assert sales_client.get("/dashboard", follow_redirects=False).status_code == 303
        assert login(sales_client, "sales@example.com", PASSWORD).status_code == 401
        assert login(sales_client, "sales@example.com", new_password).status_code == 303
        update.pop("is_active")
        assert (
            client.post(
                f"/dashboard/accounts/{sales_id}", data=update, follow_redirects=False
            ).status_code
            == 303
        )
        assert sales_client.get("/dashboard", follow_redirects=False).status_code == 303
        assert login(sales_client, "sales@example.com", new_password).status_code == 401
        assert (
            client.post(
                f"/dashboard/accounts/{sales_id}",
                data={**update, "is_active": "on"},
                follow_redirects=False,
            ).status_code
            == 303
        )
        assert login(sales_client, "sales@example.com", new_password).status_code == 303
    with Session(engine) as session:
        assert AccountService(session).get_account(admin.id, sales_id).is_active


def test_sales_cannot_manage_accounts_in_routes_or_services(account_client):
    client, engine, admin = account_client
    with Session(engine) as session:
        sales = AccountService(session).create_account(
            admin.id,
            AccountCreate(
                email="sales@example.com", display_name="Sales", role=Role.SALES, password=PASSWORD
            ),
        )
    login(client, "sales@example.com")
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert 'href="/dashboard/accounts"' not in dashboard.text
    for url in [
        "/dashboard/accounts",
        "/dashboard/accounts/new",
        f"/dashboard/accounts/{admin.id}",
    ]:
        assert client.get(url).status_code == 403
    for url in ["/dashboard/accounts/new", f"/dashboard/accounts/{admin.id}"]:
        assert client.post(url, data={"csrf_token": csrf(dashboard)}).status_code == 403
    with Session(engine) as session:
        service = AccountService(session)
        with pytest.raises(AccessDenied):
            service.list_accounts(sales.id)
        with pytest.raises(AccessDenied):
            service.create_account(
                sales.id,
                AccountCreate(
                    email="other@example.com",
                    display_name="Other",
                    role=Role.ADMIN,
                    password=PASSWORD,
                ),
            )


def test_validation_duplicate_email_and_self_protection(account_client):
    client, _, admin = account_client
    login(client)
    form = account_form(client)
    for field, value in [
        ("email", "invalid"),
        ("role", "owner"),
        ("password", "short"),
        ("display_name", "   "),
    ]:
        response = client.post("/dashboard/accounts/new", data={**form, field: value})
        assert response.status_code == 422
        assert PASSWORD not in response.text
        assert 'value="short"' not in response.text
    duplicate = client.post("/dashboard/accounts/new", data={**form, "email": "ADMIN@EXAMPLE.COM"})
    assert duplicate.status_code == 409
    edit = client.get(f"/dashboard/accounts/{admin.id}")
    update = {
        "csrf_token": csrf(edit),
        "email": admin.email,
        "display_name": admin.display_name,
        "role": "admin",
        "password": "",
    }
    assert client.post(f"/dashboard/accounts/{admin.id}", data=update).status_code == 409
    assert (
        client.post(
            f"/dashboard/accounts/{admin.id}", data={**update, "role": "sales", "is_active": "on"}
        ).status_code
        == 409
    )
    assert client.get("/dashboard/accounts").status_code == 200


def test_failed_login_is_generic_and_throttle_survives_new_session(account_client):
    client, _, _ = account_client
    wrong = login(client, password="incorrect password")
    unknown = login(client, "unknown@example.com", "incorrect password")
    assert wrong.status_code == unknown.status_code == 401
    assert "Correo o contraseña incorrectos." in wrong.text
    assert "Correo o contraseña incorrectos." in unknown.text
    for _ in range(4):
        assert login(client, password="incorrect password").status_code == 401
    client.cookies.clear()
    throttled = login(client)
    assert throttled.status_code == 429
    assert throttled.headers["Retry-After"] == "900"


def test_expired_sessions_rejected_and_role_changes_revoke_sessions(account_client):
    client, engine, admin = account_client
    login(client)
    token = client.cookies.get("parrilladas_session")
    with Session(engine) as session, session.begin():
        record = session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_digest(token))
        )
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get("/dashboard", follow_redirects=False).status_code == 303
    login(client)
    with Session(engine) as session:
        service = AccountService(session)
        second = service.create_account(
            admin.id,
            AccountCreate(
                email="second@example.com",
                display_name="Second",
                role=Role.ADMIN,
                password=PASSWORD,
            ),
        )
        service.update_account(
            second.id,
            admin.id,
            AccountUpdate(
                email=admin.email, display_name=admin.display_name, role=Role.SALES, is_active=True
            ),
        )
    assert client.get("/dashboard", follow_redirects=False).status_code == 303
    login(client)
    assert client.get("/dashboard/accounts").status_code == 403


def test_bootstrap_is_single_use_and_operator_reset_revokes_sessions(account_client):
    client, engine, _ = account_client
    login(client)
    with Session(engine) as session:
        service = AccountService(session)
        with pytest.raises(AccountConflict):
            service.bootstrap_admin(
                AccountCreate(
                    email="second@example.com",
                    display_name="Second",
                    role=Role.ADMIN,
                    password=PASSWORD,
                )
            )
        service.reset_password(
            PasswordReset(email="ADMIN@example.com", password="operator reset passphrase 789")
        )
    assert client.get("/dashboard", follow_redirects=False).status_code == 303
    assert login(client, password="operator reset passphrase 789").status_code == 303


def test_concurrent_account_creation_preserves_unique_email(account_client):
    _, engine, admin = account_client
    data = AccountCreate(
        email="unique@example.com", display_name="Unique", role=Role.SALES, password=PASSWORD
    )

    def create():
        with Session(engine) as session:
            try:
                AccountService(session).create_account(admin.id, data)
                return "created"
            except AccountConflict:
                return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: create(), range(2))) == ["created", "duplicate"]


def test_password_policy_uses_secret_fields():
    with pytest.raises(ValidationError):
        AccountCreate(
            email="user@example.com", display_name="User", role=Role.SALES, password="short"
        )
    data = AccountCreate(
        email="user@example.com", display_name="User", role=Role.SALES, password=PASSWORD
    )
    assert PASSWORD not in repr(data)


def test_production_cookie_security_and_anonymous_guards(account_client):
    _, _, _ = account_client
    settings = account_client[0].app
    settings.state.secure_cookies = True
    with TestClient(settings, base_url="https://testserver") as client:
        assert client.get("/dashboard", follow_redirects=False).status_code == 303
        assert client.get("/dashboard/accounts", follow_redirects=False).status_code == 303
        response = client.get("/login")
        cookie = response.headers["set-cookie"]
        assert "__Host-parrilladas=" in cookie
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert "Domain=" not in cookie
        assert login(client).status_code == 303
        assert client.get("/dashboard").status_code == 200


def test_csrf_tokens_cannot_be_reused_from_another_session(account_client):
    client, _, _ = account_client
    token = csrf(client.get("/login"))
    client.cookies.clear()
    client.get("/login")
    assert (
        client.post(
            "/login", data={"csrf_token": token, "email": "admin@example.com", "password": PASSWORD}
        ).status_code
        == 403
    )


def test_bootstrap_serializes_concurrent_first_admins(account_client):
    _, engine, _ = account_client
    with Session(engine) as session, session.begin():
        session.execute(delete(AuthSession))
        session.execute(delete(Account))

    def bootstrap(number):
        with Session(engine) as session:
            try:
                AccountService(session).bootstrap_admin(
                    AccountCreate(
                        email=f"admin{number}@example.com",
                        display_name="Admin",
                        role=Role.ADMIN,
                        password=PASSWORD,
                    )
                )
                return "created"
            except AccountConflict:
                return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(bootstrap, range(2))) == ["blocked", "created"]
