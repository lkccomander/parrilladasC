import json

import google.auth
import httpx2
from google import genai
from google.auth.exceptions import GoogleAuthError
from google.genai import types
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account

from parrilladas.modules.assistant.config import AssistantSettings
from parrilladas.modules.assistant.errors import ExtractionUnavailable
from parrilladas.modules.assistant.prompts import EXTRACTION_INSTRUCTIONS
from parrilladas.modules.assistant.schemas import ExtractionCandidate, ExtractionRequest
from parrilladas.modules.assistant.telemetry import Telemetry


class VertexExtractor:
    def __init__(
        self,
        client: genai.Client,
        *,
        model: str,
        max_output_tokens: int = 512,
        region: str | None = None,
        telemetry=None,
    ):
        self.client = client
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.region = region
        self.telemetry = telemetry or Telemetry()

    @classmethod
    def from_settings(cls, settings: AssistantSettings) -> "VertexExtractor":
        if not (settings.natural_language_enabled or settings.vertex_connection_enabled):
            raise ExtractionUnavailable("Extraction is disabled")
        try:
            scopes = ["https://www.googleapis.com/auth/cloud-platform"]
            if settings.google_service_account_json is not None:
                info = json.loads(settings.google_service_account_json.get_secret_value())
                if not isinstance(info, dict) or (
                    info.get("type") != "service_account"
                    or info.get("project_id") != settings.google_cloud_project
                    or info.get("token_uri") != "https://oauth2.googleapis.com/token"
                ):
                    raise ValueError("Invalid service account configuration")
                credentials = service_account.Credentials.from_service_account_info(
                    info, scopes=scopes
                )
            else:
                credentials, _ = google.auth.default(scopes=scopes)
            if settings.app_env in {"staging", "production"} and isinstance(
                credentials, user_credentials.Credentials
            ):
                raise ValueError("Deployed services require a workload identity")
            client = genai.Client(
                enterprise=True,
                credentials=credentials,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
                http_options=types.HttpOptions(
                    timeout=settings.assistant_timeout_ms,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        except (GoogleAuthError, ValueError, OSError):
            raise ExtractionUnavailable("Model authentication unavailable") from None
        return cls(
            client,
            model=settings.gemini_model,
            max_output_tokens=settings.assistant_max_output_tokens,
            region=settings.google_cloud_location,
        )

    def extract(self, request: ExtractionRequest) -> str:
        try:
            with self.telemetry.measure("extraction", model=self.model, region=self.region) as span:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=request.model_dump_json(),
                    config=types.GenerateContentConfig(
                        system_instruction=EXTRACTION_INSTRUCTIONS,
                        response_mime_type="application/json",
                        response_schema=ExtractionCandidate,
                        max_output_tokens=self.max_output_tokens,
                        thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
                        tools=[],
                    ),
                )
                span.response(response)
                if (
                    not response.candidates
                    or response.candidates[0].finish_reason != types.FinishReason.STOP
                    or not response.text
                ):
                    raise ValueError("Model response incomplete")
                return response.text
        except (genai.errors.APIError, GoogleAuthError, httpx2.HTTPError, OSError, ValueError):
            raise ExtractionUnavailable("Model request unavailable") from None

    def close(self) -> None:
        self.client.close()
