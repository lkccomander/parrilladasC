import httpx
import pytest
from fastapi.testclient import TestClient

from parrilladas.admin import create_app
from parrilladas.core.config import AdminSettings


@pytest.fixture
def client():
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(503, json={"status": "unavailable"})
            ),
            base_url="http://api",
        ) as api,
        TestClient(
            create_app(AdminSettings(app_env="test", _env_file=None), api_http=api)
        ) as client,
    ):
        yield client
