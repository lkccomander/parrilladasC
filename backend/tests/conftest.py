import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from parrilladas.core.config import Settings
from parrilladas.main import create_app


@pytest.fixture
def client():
    settings = Settings(
        app_env="test",
        database_url=SecretStr("postgresql+psycopg://test:test@localhost:1/test"),
        _env_file=None,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
