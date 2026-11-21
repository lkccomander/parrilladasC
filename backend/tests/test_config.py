import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import make_url

from parrilladas.core.config import Settings


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_provider_urls_select_psycopg_and_preserve_credentials(scheme):
    settings = Settings(
        database_url=SecretStr(
            f"{scheme}://staff:p%40ss%3Aword@db.internal:5432/catering?sslmode=require"
        ),
        _env_file=None,
    )
    url = make_url(settings.database_url.get_secret_value())
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss:word"
    assert url.host == "db.internal"
    assert url.database == "catering"
    assert url.query == {"sslmode": "require"}
    assert "p@ss:word" not in repr(settings)


@pytest.mark.parametrize("scheme", ["sqlite", "mysql", "postgresql+asyncpg"])
def test_unsupported_database_drivers_are_rejected(scheme):
    with pytest.raises(ValidationError, match="PostgreSQL URL using psycopg"):
        Settings(database_url=SecretStr(f"{scheme}://host/database"), _env_file=None)


@pytest.mark.parametrize(
    "url",
    [
        "http://public.example.com",
        "https://user:password@example.com",
        "https://api.example.com/path",
    ],
)
def test_admin_rejects_unsafe_production_api_origins(url):
    from parrilladas.core.config import AdminSettings

    with pytest.raises(ValidationError):
        AdminSettings(app_env="production", api_base_url=url, _env_file=None)


def test_admin_needs_neither_database_nor_signing_secret():
    from parrilladas.core.config import AdminSettings

    settings = AdminSettings(
        app_env="production", api_base_url="http://api.railway.internal:8080", _env_file=None
    )
    assert "database_url" not in type(settings).model_fields
    assert "jwt_secret" not in type(settings).model_fields


def test_durable_worker_requires_an_aware_cutoff_and_complete_outbound_configuration():
    from parrilladas.core.config import ApiSettings

    with pytest.raises(ValidationError, match="worker requires"):
        ApiSettings(
            app_env="test",
            database_url="postgresql://test@localhost/test",
            jwt_secret="synthetic-only-key-at-least-32-characters",
            conversation_worker_enabled=True,
            _env_file=None,
        )


def test_live_model_processing_requires_a_durable_worker():
    from parrilladas.core.config import ApiSettings
    from parrilladas.main import create_app
    from parrilladas.modules.assistant.config import AssistantSettings

    with pytest.raises(ValueError, match="durable conversation worker"):
        create_app(
            ApiSettings(
                app_env="test",
                database_url="postgresql://test@localhost/test",
                jwt_secret="synthetic-only-key-at-least-32-characters",
                _env_file=None,
            ),
            assistant_settings=AssistantSettings(
                natural_language_enabled=True,
                google_cloud_project="synthetic",
                google_cloud_location="global",
                gemini_model="synthetic",
                _env_file=None,
            ),
        )


def test_dev_role_key_is_optional_private_api_configuration(monkeypatch):
    from parrilladas.core.config import AdminSettings, ApiSettings

    monkeypatch.delenv("DEV_ROLE_KEY", raising=False)
    kwargs = {
        "database_url": "postgresql://test:test@localhost/disposable",
        "jwt_secret": "synthetic-signing-secret-for-tests-only",
        "_env_file": None,
    }
    assert ApiSettings(**kwargs).dev_role_key is None
    key = "synthetic-dev-role-key-for-tests-only"
    monkeypatch.setenv("DEV_ROLE_KEY", key)
    configured = ApiSettings(**kwargs)
    assert configured.dev_role_key.get_secret_value() == key
    assert key not in repr(configured)
    assert not hasattr(AdminSettings(_env_file=None), "dev_role_key")
    with pytest.raises(ValidationError) as error:
        ApiSettings(**kwargs, dev_role_key="too-short-private-key")
    assert "too-short-private-key" not in str(error.value)
