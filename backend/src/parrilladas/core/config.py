from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
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


class ApiSettings(Settings):
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    jwt_secret: SecretStr = Field(min_length=32)
    jwt_issuer: str = "parrilladas-auth"
    jwt_audience: str = "parrilladas-api"
    whatsapp_app_secret: SecretStr | None = Field(default=None, min_length=1)
    whatsapp_verify_token: SecretStr | None = Field(default=None, min_length=1)
    whatsapp_business_account_id: str | None = Field(default=None, pattern=r"^[0-9]+$")
    whatsapp_phone_number_id: str | None = Field(default=None, pattern=r"^[0-9]+$")
    whatsapp_access_token: SecretStr | None = Field(default=None, min_length=1)
    whatsapp_graph_api_version: str | None = Field(
        default=None, pattern=r"^v[0-9]{1,3}\.[0-9]{1,2}$"
    )
    api_public_base_url: str | None = None

    @field_validator("api_public_base_url")
    @classmethod
    def require_public_api_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("API_PUBLIC_BASE_URL must be an HTTP origin without credentials")
        return value.rstrip("/")

    @model_validator(mode="after")
    def require_complete_whatsapp_configuration(self):
        if (
            self.api_public_base_url
            and self.app_env in {"production", "staging"}
            and urlsplit(self.api_public_base_url).scheme != "https"
        ):
            raise ValueError("Public production webhook requires HTTPS")
        values = (
            self.whatsapp_app_secret,
            self.whatsapp_business_account_id,
            self.whatsapp_phone_number_id,
        )
        # Meta verifies the subscription before message intake is configured.
        # A verify token alone enables only the GET challenge handshake.
        if any(value is not None for value in values) and (
            self.whatsapp_verify_token is None or not all(value is not None for value in values)
        ):
            raise ValueError("WhatsApp intake requires all four WHATSAPP_* settings")
        return self


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    api_base_url: str = "http://127.0.0.1:8001"

    @field_validator("api_base_url")
    @classmethod
    def require_api_origin(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("API_BASE_URL must be an HTTP origin without credentials")
        return value.rstrip("/")

    @model_validator(mode="after")
    def require_safe_transport(self):
        url = urlsplit(self.api_base_url)
        if (
            self.app_env in {"production", "staging"}
            and url.scheme != "https"
            and not url.hostname.endswith(".railway.internal")
        ):
            raise ValueError("Production API_BASE_URL needs HTTPS or Railway private networking")
        return self
