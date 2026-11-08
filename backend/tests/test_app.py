from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError

from parrilladas.core.config import ApiSettings
from parrilladas.db.session import get_session
from parrilladas.main import create_app


def test_liveness_and_public_page_do_not_require_a_database(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    response = client.get("/")
    assert response.status_code == 200
    assert "Parrillas en su Casa" in response.text


def test_greeting_asset_is_publicly_available(client):
    settings = ApiSettings(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost:1/test",
        jwt_secret="test-only-signing-key-at-least-32-characters",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as api:
        response = api.get("/assets/greeting-grill.png")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG")


def test_readiness_hides_connection_details(client):
    class BrokenSession:
        def execute(self, statement):
            raise OperationalError("SELECT 1", {}, Exception("private-database-password"))

    settings = ApiSettings(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost:1/test",
        jwt_secret="test-only-signing-key-at-least-32-characters",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as api:
        api.app.dependency_overrides[get_session] = lambda: BrokenSession()
        response = api.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert "private-database-password" not in response.text
    assert client.get("/health/ready").status_code == 503
    assert client.get("/login").status_code == 503


def test_production_disables_api_documentation():
    settings = ApiSettings(
        jwt_secret="test-only-signing-key-at-least-32-characters",
        app_env="production",
        database_url=SecretStr("postgresql+psycopg://test:test@localhost:1/test"),
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_legal_pages_are_public_without_database_access(client):
    for path, heading in [
        ("/privacy", "Política de privacidad"),
        ("/terms-of-service", "Términos de servicio"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert heading in response.text
        assert 'href="/login"' in response.text
        assert 'href="/privacy"' in response.text
        assert 'href="/terms-of-service"' in response.text
        assert "Welcome to Nicaragua" not in response.text
        assert "font-src 'self'" in response.headers["content-security-policy"]


def test_legal_language_switch_and_english_navigation(client):
    for path, title, other_path in [
        ("/privacy", "Privacy policy", "/terms-of-service"),
        ("/terms-of-service", "Terms of service", "/privacy"),
    ]:
        spanish = client.get(path)
        assert spanish.headers["content-language"] == "es"
        assert '<html lang="es">' in spanish.text
        assert f'href="{path}?lang=en"' in spanish.text
        assert 'hreflang="en"' in spanish.text

        english = client.get(path, params={"lang": "en"})
        assert english.status_code == 200
        assert english.headers["content-language"] == "en"
        assert '<html lang="en">' in english.text
        assert f"<h1>{title}</h1>" in english.text
        assert 'class="button quiet language-switch"' in english.text
        assert f'href="{path}" lang="es" hreflang="es"' in english.text
        assert f'href="{other_path}?lang=en"' in english.text
        assert "Back to sign in" in english.text
        assert "On this page" in english.text
        assert "Last updated: November 1, 2026" in english.text
        assert 'href="mailto:info@parrillasensucasa.com"' in english.text

        explicit_spanish = client.get(path, params={"lang": "es"})
        assert explicit_spanish.status_code == 200
        assert explicit_spanish.headers["content-language"] == "es"
        assert explicit_spanish.text == spanish.text


def test_legal_pages_reject_unsupported_languages(client):
    for path in ["/privacy", "/terms-of-service"]:
        assert client.get(path, params={"lang": "fr"}).status_code == 422
        assert client.get(path, params={"lang": "../../base"}).status_code == 422
