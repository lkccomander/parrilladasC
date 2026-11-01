from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError

from parrilladas.core.config import Settings
from parrilladas.db.session import get_session
from parrilladas.main import create_app


def test_liveness_and_public_page_do_not_require_a_database(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    response = client.get("/")
    assert response.status_code == 200
    assert "Parrillas en su Casa" in response.text


def test_readiness_hides_connection_details(client):
    class BrokenSession:
        def execute(self, statement):
            raise OperationalError("SELECT 1", {}, Exception("private-database-password"))

    client.app.dependency_overrides[get_session] = lambda: BrokenSession()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "private-database-password" not in response.text


def test_production_disables_api_documentation():
    settings = Settings(
        app_env="production",
        database_url=SecretStr("postgresql+psycopg://test:test@localhost:1/test"),
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
