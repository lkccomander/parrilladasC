from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    database_url: SecretStr
    database_pool_size: int = Field(default=5, ge=1, le=20)

    @field_validator("database_url")
    @classmethod
    def require_postgres(cls, value: SecretStr) -> SecretStr:
        url = make_url(value.get_secret_value())
        if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError("DATABASE_URL must be a PostgreSQL URL using psycopg")
        # Managed providers supply a standard PostgreSQL URL. Select our installed
        # driver explicitly while preserving encoded credentials and query options.
        return SecretStr(
            url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
        )
