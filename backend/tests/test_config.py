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
