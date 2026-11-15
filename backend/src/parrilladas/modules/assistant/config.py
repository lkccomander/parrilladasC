from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AssistantSettings(BaseSettings):
    """Model connection and extraction settings; no database credentials required."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "staging", "production"] = "development"
    natural_language_enabled: bool = False
    vertex_connection_enabled: bool = False
    google_cloud_project: str | None = Field(default=None, min_length=1)
    google_cloud_location: str | None = Field(default=None, min_length=1)
    gemini_model: str | None = Field(default=None, min_length=1)
    google_service_account_json: SecretStr | None = Field(default=None, repr=False)
    assistant_timeout_ms: int = Field(default=30000, ge=1000, le=60000)
    assistant_max_output_tokens: int = Field(default=512, ge=128, le=2048)

    @model_validator(mode="after")
    def require_explicit_pilot_configuration(self):
        if (self.natural_language_enabled or self.vertex_connection_enabled) and not all(
            value and value.strip()
            for value in (
                self.google_cloud_project,
                self.google_cloud_location,
                self.gemini_model,
            )
        ):
            raise ValueError("Enabled pilot requires project, location and model")
        return self
