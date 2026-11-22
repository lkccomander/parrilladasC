from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelPrice(BaseModel):
    input_per_million: Decimal = Field(ge=0)
    output_per_million: Decimal = Field(ge=0)
    cached_per_million: Decimal | None = Field(default=None, ge=0)


class AssistantSettings(BaseSettings):
    """Model connection and extraction settings; no database credentials required."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "staging", "production"] = "development"
    natural_language_enabled: bool = False
    vertex_connection_enabled: bool = False
    rag_enabled: bool = False
    embedding_model: Literal["gemini-embedding-001"] = "gemini-embedding-001"
    embedding_location: Literal["us-central1"] = "us-central1"
    rag_min_similarity: float = Field(default=0.35, ge=0, le=1)
    rag_trace_retention_days: int = Field(default=30, ge=1, le=365)
    rag_monitoring_enabled: bool = True
    rag_monitoring_interval_seconds: int = Field(default=300, ge=30, le=86400)
    rag_eval_enabled: bool = False
    rag_eval_max_cases: int = Field(default=20, ge=1, le=100)
    rag_eval_max_calls: int = Field(default=40, ge=1, le=200)
    rag_eval_timeout_seconds: int = Field(default=120, ge=5, le=600)
    rag_model_prices: dict[str, ModelPrice] = Field(default_factory=dict)
    rag_price_table_updated_at: date | None = None
    rag_target_recall_watch: float = Field(default=0.90, ge=0, le=1)
    rag_target_recall_breach: float = Field(default=0.85, ge=0, le=1)
    rag_target_faithfulness_watch: float = Field(default=0.95, ge=0, le=1)
    rag_target_faithfulness_breach: float = Field(default=0.90, ge=0, le=1)
    rag_target_no_evidence_watch: float = Field(default=0.08, ge=0, le=1)
    rag_target_no_evidence_breach: float = Field(default=0.15, ge=0, le=1)
    rag_target_latency_watch_ms: int = Field(default=3000, ge=1)
    rag_target_latency_breach_ms: int = Field(default=5000, ge=1)
    rag_target_cost_budget: Decimal = Field(default=Decimal("0.020"), gt=0)
    rag_target_index_recall_watch: float = Field(default=0.97, ge=0, le=1)
    rag_target_index_recall_breach: float = Field(default=0.95, ge=0, le=1)
    rag_target_bloat_watch: float = Field(default=0.10, ge=0, le=1)
    rag_target_bloat_breach: float = Field(default=0.25, ge=0, le=1)
    rag_target_provider_error_watch: float = Field(default=0.05, ge=0, le=1)
    rag_target_provider_error_breach: float = Field(default=0.15, ge=0, le=1)
    rag_target_eval_stale_days: int = Field(default=7, ge=1)
    google_cloud_project: str | None = Field(default=None, min_length=1)
    google_cloud_location: str | None = Field(default=None, min_length=1)
    gemini_model: str | None = Field(default=None, min_length=1)
    google_service_account_json: SecretStr | None = Field(default=None, repr=False)
    assistant_timeout_ms: int = Field(default=30000, ge=1000, le=60000)
    assistant_max_output_tokens: int = Field(default=512, ge=128, le=2048)

    @model_validator(mode="after")
    def require_explicit_pilot_configuration(self):
        if (
            self.natural_language_enabled or self.vertex_connection_enabled or self.rag_enabled
        ) and not all(
            value and value.strip()
            for value in (
                self.google_cloud_project,
                self.google_cloud_location,
                self.gemini_model,
            )
        ):
            raise ValueError("Enabled pilot requires project, location and model")
        return self
