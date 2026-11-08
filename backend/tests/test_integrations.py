from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from parrilladas.admin import create_app as create_admin
from parrilladas.core.config import AdminSettings, ApiSettings
from parrilladas.integrations.whatsapp.client import MetaClient
from parrilladas.main import create_app
from parrilladas.modules.accounts.contracts import Role
from parrilladas.modules.accounts.schemas import AccountView, SessionContext
from parrilladas.modules.integrations.service import IntegrationService

TOKEN = "synthetic-meta-access-token"
APP_SECRET = "synthetic-app-secret"
VERIFY_TOKEN = "synthetic-verify-token"
PHONE_ID = "200000001"
WABA = "100000001"


def settings(**overrides):
    values = dict(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost:1/test",
        jwt_secret="test-only-signing-key-at-least-32-characters",
        whatsapp_app_secret=APP_SECRET,
        whatsapp_verify_token=VERIFY_TOKEN,
        whatsapp_business_account_id=WABA,
        whatsapp_phone_number_id=PHONE_ID,
        whatsapp_access_token=TOKEN,
        whatsapp_graph_api_version="v24.0",
        api_public_base_url="https://api.example.com/",
        _env_file=None,
    )
    return ApiSettings(**(values | overrides))


def test_status_shows_public_webhook_without_network_or_secrets():
    def unexpected(request):
        pytest.fail("Opening the integration page must not contact Meta")

    with httpx.Client(transport=httpx.MockTransport(unexpected)) as http:
        service = IntegrationService(settings(), MetaClient(http))
        report = service.status()
        assert report.webhook_url == "https://api.example.com/webhooks/whatsapp"
        assert report.webhook_enabled
        assert report.access_token_configured
        assert report.check is None
        assert not any(
            secret in report.model_dump_json() for secret in (TOKEN, APP_SECRET, VERIFY_TOKEN)
        )
        report = IntegrationService(settings(api_public_base_url=None), MetaClient(http)).status()
        assert report.webhook_url is None
        assert report.webhook_path == "/webhooks/whatsapp"


def test_admin_footer_displays_product_release(dashboard):
    client, _, _ = dashboard
    response = client.get("/dashboard/integrations")

    assert response.status_code == 200
    assert "Parrilladas en su Casa" in response.text
    assert "Beta 1.00" in response.text
    assert "v1.0.0-beta.1" in response.text


def test_connection_check_uses_read_only_meta_request_and_bearer_header():
    calls = []

    def meta(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "graph.facebook.com"
        assert request.url.path == f"/v24.0/{PHONE_ID}"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(request.url)
        assert request.url.params["fields"] == "id,display_phone_number"
        return httpx.Response(200, json={"id": PHONE_ID, "display_phone_number": "+506 6364 7552"})

    with httpx.Client(transport=httpx.MockTransport(meta)) as http:
        report = IntegrationService(settings(), MetaClient(http)).check()
    assert len(calls) == 1
    assert report.check.meta.status == "ok"
    assert report.check.whatsapp.status == "ok"
    assert report.check.checked_at.tzinfo is not None
    assert not any(
        secret in report.model_dump_json() for secret in (TOKEN, APP_SECRET, VERIFY_TOKEN)
    )


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"id": "different-number", "display_phone_number": "+506 6000 0000"}, "error"),
        ({"id": PHONE_ID}, "ok"),
        ({"data": [{"id": PHONE_ID}]}, "unknown"),
    ],
)
def test_phone_lookup_requires_direct_phone_object(body, expected):
    calls = []

    def meta(request):
        calls.append(request)
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(meta)) as http:
        report = IntegrationService(settings(), MetaClient(http)).check()
    assert report.check.whatsapp.status == expected
    assert report.check.meta.status == ("ok" if expected != "unknown" else "error")
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (400, {"error": {"code": 190, "message": TOKEN}}, "vigencia del token"),
        (403, {"error": {"message": TOKEN}}, "permisos"),
        (429, {"error": {"message": TOKEN}}, "limitó"),
        (503, {"error": {"message": TOKEN}}, "contactar"),
        (200, {"data": [{"not_id": TOKEN}]}, "respuesta válida"),
        (200, {"data": None}, "respuesta válida"),
        (200, [], "respuesta válida"),
        (302, {}, "respuesta válida"),
    ],
)
def test_provider_errors_are_safe_and_actionable(status, body, message):
    def meta(request):
        return httpx.Response(status, json=body, headers={"Location": "https://untrusted.example"})

    with httpx.Client(transport=httpx.MockTransport(meta)) as http:
        report = IntegrationService(settings(), MetaClient(http)).check()
    assert report.check.meta.status == "error"
    assert report.check.whatsapp.status == "unknown"
    assert message in report.check.meta.message
    assert TOKEN not in report.model_dump_json()


@pytest.mark.parametrize("failure", ["timeout", "invalid_json"])
def test_timeout_and_non_json_response_are_reported_without_exception_details(failure):
    def meta(request):
        if failure == "timeout":
            raise httpx.ReadTimeout(TOKEN, request=request)
        return httpx.Response(200, text=TOKEN)

    with httpx.Client(transport=httpx.MockTransport(meta)) as http:
        report = IntegrationService(settings(), MetaClient(http)).check()
    assert report.check.meta.status == "error"
    assert TOKEN not in report.model_dump_json()


@pytest.mark.parametrize("missing", ["whatsapp_access_token", "whatsapp_graph_api_version"])
def test_missing_configuration_does_not_contact_meta(missing):
    def unexpected(request):
        pytest.fail("Incomplete configuration must not cause an external request")

    with httpx.Client(transport=httpx.MockTransport(unexpected)) as http:
        report = IntegrationService(settings(**{missing: None}), MetaClient(http)).check()
    assert report.check.meta.status == "not_configured"
    assert report.check.whatsapp.status == "not_configured"


@pytest.mark.parametrize(
    "origin",
    [
        "https://user:password@example.com",
        "https://example.com/path",
        "https://example.com?token=secret",
    ],
)
def test_public_webhook_origin_rejects_credentials_paths_and_queries(origin):
    with pytest.raises(ValidationError):
        settings(api_public_base_url=origin)


def test_public_production_webhook_requires_https_and_version_has_no_url_syntax():
    with pytest.raises(ValidationError, match="HTTPS"):
        settings(app_env="production", api_public_base_url="http://api.example.com")
    with pytest.raises(ValidationError):
        settings(whatsapp_graph_api_version="../../other-host")
    assert TOKEN not in repr(settings())
    assert "whatsapp_access_token" not in AdminSettings.model_fields


def test_api_integration_endpoints_require_authentication():
    with TestClient(create_app(settings())) as client:
        assert client.get("/integrations/whatsapp").status_code == 401
        assert client.post("/integrations/whatsapp/check").status_code == 401


@pytest.fixture
def dashboard(request):
    actor = SessionContext(
        id=uuid4(),
        csrf_token="synthetic-csrf-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        account=AccountView(
            id=uuid4(),
            email="admin@example.com",
            display_name="Test Admin",
            role=getattr(request, "param", Role.ADMIN),
            is_active=True,
        ),
    )
    calls = []

    def api(request):
        calls.append(request)
        if request.url.path == "/auth/me":
            return httpx.Response(200, json=actor.model_dump(mode="json"))
        assert request.headers["Authorization"] == "Bearer synthetic-jwt"
        assert request.headers["X-CSRF-Token"] == actor.csrf_token
        if request.url.path == "/integrations/whatsapp":
            with httpx.Client() as unused:
                report = IntegrationService(settings(), MetaClient(unused)).status()
        elif request.url.path == "/integrations/whatsapp/check":
            with httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"id": PHONE_ID})
                )
            ) as meta:
                report = IntegrationService(settings(), MetaClient(meta)).check()
        else:
            pytest.fail(f"Unexpected API request: {request.url.path}")
        return httpx.Response(200, json=report.model_dump(mode="json"))

    with (
        httpx.Client(transport=httpx.MockTransport(api), base_url="http://api") as http,
        TestClient(create_admin(AdminSettings(_env_file=None), api_http=http)) as client,
    ):
        client.cookies.set("parrilladas_session", "synthetic-jwt")
        yield client, actor, calls


def test_admin_page_shows_webhook_and_post_displays_live_check_results(dashboard):
    client, actor, calls = dashboard
    response = client.get("/dashboard/integrations")
    assert response.status_code == 200
    assert 'value="https://api.example.com/webhooks/whatsapp"' in response.text
    assert 'aria-current="page"' in response.text
    assert "Conexión sin comprobar" in response.text
    assert response.headers["Cache-Control"] == "no-store"
    response = client.post(
        "/dashboard/integrations/whatsapp/check", data={"csrf_token": actor.csrf_token}
    )
    assert response.status_code == 200
    assert "Resultado de la comprobación" in response.text
    assert "Conectado" in response.text
    assert any(
        request.method == "POST" and request.url.path.endswith("/check") for request in calls
    )
    assert not any(secret in response.text for secret in (TOKEN, APP_SECRET, VERIFY_TOKEN))


def test_admin_check_form_requires_csrf_and_rejects_cross_site_requests(dashboard):
    client, actor, calls = dashboard
    path = "/dashboard/integrations/whatsapp/check"
    assert (
        client.post(
            path, content=b"", headers={"Content-Type": "application/x-www-form-urlencoded"}
        ).status_code
        == 403
    )
    assert client.post(path, data={"csrf_token": "wrong"}).status_code == 403
    assert (
        client.post(
            path, data={"csrf_token": actor.csrf_token}, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert not any(request.url.path.endswith("/check") for request in calls)


@pytest.mark.parametrize("dashboard", [Role.SALES], indirect=True)
def test_sales_cannot_view_integrations_or_run_checks(dashboard):
    client, actor, calls = dashboard
    assert client.get("/dashboard/integrations").status_code == 403
    assert (
        client.post(
            "/dashboard/integrations/whatsapp/check", data={"csrf_token": actor.csrf_token}
        ).status_code
        == 403
    )


def test_anonymous_admin_requests_redirect_to_login(dashboard):
    client, _, _ = dashboard
    client.cookies.clear()
    response = client.get("/dashboard/integrations", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == "/login"
