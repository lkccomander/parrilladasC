import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import httpx2
import pytest
from google import genai
from google.auth.exceptions import DefaultCredentialsError
from google.genai import types
from google.oauth2.credentials import Credentials
from pydantic import ValidationError

from parrilladas.integrations.vertex_ai.client import VertexExtractor
from parrilladas.modules.assistant.config import AssistantSettings
from parrilladas.modules.assistant.errors import ExtractionUnavailable
from parrilladas.modules.assistant.schemas import EventDetails, ExtractionRequest
from parrilladas.modules.assistant.service import AssistantService


def request(message="Parrillada para 20 personas el 20 de diciembre de 2026 en Alajuela.", **kw):
    return ExtractionRequest(message=message, reference_date=date(2026, 11, 15), **kw)


def candidate(**changes):
    data = {
        "intent": "quote",
        "details": {
            "event_date": "2026-12-20",
            "guest_count": 20,
            "location": "Alajuela",
            "service_type": "parrilla",
        },
        "date_evidence": "20 de diciembre de 2026",
        "ambiguities": [],
    }
    data.update(changes)
    return json.dumps(data)


def provider_returning(raw):
    return SimpleNamespace(extract=Mock(return_value=raw))


def test_default_gate_and_human_pause_never_call_provider():
    provider = provider_returning(candidate())
    assert AssistantService(provider).extract(request()).status == "disabled"
    outcome = AssistantService(provider, enabled=True).extract(request(), bot_paused=True)
    assert outcome.status == "paused"
    assert outcome.reason == "human_control"
    provider.extract.assert_not_called()


def test_complete_spanish_extraction_requires_review_and_no_optional_commercial_fields():
    outcome = AssistantService(provider_returning(candidate()), enabled=True).extract(request())
    assert outcome.status == "extracted"
    assert outcome.reason == "review_required"
    assert outcome.details == EventDetails(
        event_date=date(2026, 12, 20), guest_count=20, location="Alajuela", service_type="parrilla"
    )
    assert outcome.missing_fields == ()
    assert outcome.changed_fields == ()


def test_partial_messages_preserve_confirmed_data_and_report_proposed_changes():
    confirmed = EventDetails(guest_count=20, location="Alajuela", service_type="parrilla")
    raw = candidate(details={"guest_count": 30, "location": "Heredia"}, date_evidence=None)
    outcome = AssistantService(provider_returning(raw), enabled=True).extract(
        request("Ahora seremos 30 personas en Heredia", confirmed=confirmed)
    )
    assert outcome.details == confirmed
    assert outcome.proposed_changes == EventDetails(guest_count=30, location="Heredia")
    assert outcome.changed_fields == ("guest_count", "location")
    assert outcome.missing_fields == ("event_date",)
    assert confirmed.guest_count == 20


def test_new_fields_complete_an_existing_request_without_erasing_confirmed_values():
    confirmed = EventDetails(guest_count=20, service_type="parrilla")
    raw = candidate(details={"location": "Alajuela"}, date_evidence=None)
    outcome = AssistantService(provider_returning(raw), enabled=True).extract(
        request("En Alajuela", confirmed=confirmed)
    )
    assert outcome.details.location == "Alajuela"
    assert outcome.details.guest_count == 20
    assert outcome.details.service_type == "parrilla"
    assert outcome.missing_fields == ("event_date",)


@pytest.mark.parametrize(
    ("message", "evidence", "event_date"),
    [
        ("Parrillada el 20 de diciembre", "20 de diciembre", "2026-12-20"),
        ("Parrillada mañana", "20 de diciembre de 2026", "2026-12-20"),
        ("Parrillada el 20 de diciembre de 2026", None, "2026-12-20"),
        ("Parrillada el 20 de diciembre de 2025", "20 de diciembre de 2025", "2025-12-20"),
    ],
)
def test_dates_without_current_message_evidence_or_in_the_past_need_clarification(
    message, evidence, event_date
):
    raw = candidate(details={"event_date": event_date}, date_evidence=evidence)
    outcome = AssistantService(provider_returning(raw), enabled=True).extract(request(message))
    assert outcome.details.event_date is None
    assert "event_date" in outcome.missing_fields
    assert outcome.ambiguities == ("event_date",)


def test_model_ambiguity_cannot_overwrite_confirmed_data_or_fill_missing_fields():
    raw = candidate(ambiguities=["guest_count", "location"])
    outcome = AssistantService(provider_returning(raw), enabled=True).extract(
        request(confirmed=EventDetails(guest_count=10))
    )
    assert outcome.details.guest_count == 10
    assert outcome.details.location is None
    assert outcome.changed_fields == ()
    assert outcome.ambiguities == ("guest_count", "location")


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        "```json\n{}\n```",
        "x" * 16001,
        candidate(details={"guest_count": "20"}),
        candidate(details={"guest_count": True}),
        candidate(details={"guest_count": 0}),
        candidate(details={"guest_count": -2}),
        candidate(details={"event_date": "2026-02-30"}),
        candidate(details={"event_date": 1797724800}),
        candidate(details={"location": " "}),
        candidate(details={"location": "x" * 201}),
        candidate(details={"total": 100}),
        candidate(details={"service_type": "buffet"}),
        candidate(tenant_id="another-tenant"),
        candidate(intent="send_quote"),
    ],
)
def test_untrusted_output_falls_back_without_modifying_confirmed_details(raw):
    confirmed = EventDetails(guest_count=20)
    outcome = AssistantService(provider_returning(raw), enabled=True).extract(
        request(confirmed=confirmed)
    )
    assert outcome.status == "fallback"
    assert outcome.reason == "invalid_output"
    assert outcome.details == confirmed
    assert outcome.changed_fields == ()


def test_provider_outage_preserves_details_and_uses_a_safe_reason():
    provider = SimpleNamespace(extract=Mock(side_effect=ExtractionUnavailable()))
    outcome = AssistantService(provider, enabled=True).extract(
        request(confirmed=EventDetails(location="Alajuela"))
    )
    assert outcome.status == "fallback"
    assert outcome.reason == "provider_unavailable"
    assert outcome.details.location == "Alajuela"
    assert AssistantService(enabled=True).extract(request()).status == "fallback"


@pytest.mark.parametrize(
    ("intent", "status", "reason"),
    [
        ("human_handoff", "handoff", "requested_handoff"),
        ("business_question", "handoff", "knowledge_not_available"),
        ("unsupported", "fallback", "unsupported"),
    ],
)
def test_non_quote_intents_do_not_apply_extracted_fields(intent, status, reason):
    outcome = AssistantService(provider_returning(candidate(intent=intent)), enabled=True).extract(
        request()
    )
    assert outcome.status == status
    assert outcome.reason == reason
    assert outcome.details == EventDetails()


def test_input_is_bounded_and_repr_hides_customer_text():
    assert "private-message" not in repr(request("private-message"))
    assert "private-location" not in repr(EventDetails(location="private-location"))
    for message in ("", " ", "x" * 4001):
        with pytest.raises(ValidationError):
            request(message)


def test_settings_default_off_and_require_explicit_configuration_for_local_pilot(monkeypatch):
    for name in (
        "APP_ENV",
        "NATURAL_LANGUAGE_ENABLED",
        "VERTEX_CONNECTION_ENABLED",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GEMINI_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    assert not AssistantSettings(_env_file=None).natural_language_enabled
    with pytest.raises(ValidationError, match="project, location and model"):
        AssistantSettings(natural_language_enabled=True, _env_file=None)
    with pytest.raises(ValidationError, match="project, location and model"):
        AssistantSettings(app_env="production", natural_language_enabled=True, _env_file=None)


def test_disabled_factory_does_not_load_credentials(monkeypatch):
    auth = Mock()
    monkeypatch.setattr("parrilladas.integrations.vertex_ai.client.google.auth.default", auth)
    with pytest.raises(ExtractionUnavailable, match="disabled"):
        VertexExtractor.from_settings(
            AssistantSettings(natural_language_enabled=False, _env_file=None)
        )
    auth.assert_not_called()


def test_vertex_factory_uses_adc_explicit_project_and_bounded_transport(monkeypatch):
    credentials = object()
    auth = Mock(return_value=(credentials, None))
    client_factory = Mock()
    monkeypatch.setattr("parrilladas.integrations.vertex_ai.client.google.auth.default", auth)
    monkeypatch.setattr("parrilladas.integrations.vertex_ai.client.genai.Client", client_factory)
    settings = AssistantSettings(
        app_env="test",
        natural_language_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        _env_file=None,
    )
    provider = VertexExtractor.from_settings(settings)
    arguments = client_factory.call_args.kwargs
    assert arguments["credentials"] is credentials
    assert arguments["enterprise"] is True
    assert arguments["project"] == "synthetic-project"
    assert arguments["location"] == "global"
    assert "api_key" not in arguments
    assert arguments["http_options"].timeout == 30000
    assert arguments["http_options"].retry_options.attempts == 1
    provider.close()
    client_factory.return_value.close.assert_called_once()


def test_vertex_factory_redacts_authentication_errors(monkeypatch):
    monkeypatch.setattr(
        "parrilladas.integrations.vertex_ai.client.google.auth.default",
        Mock(side_effect=DefaultCredentialsError("synthetic-sensitive-value")),
    )
    settings = AssistantSettings(
        app_env="test",
        natural_language_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        _env_file=None,
    )
    with pytest.raises(ExtractionUnavailable) as error:
        VertexExtractor.from_settings(settings)
    assert "synthetic-sensitive-value" not in str(error.value)
    assert error.value.__suppress_context__


def test_vertex_request_uses_structured_output_without_external_tools():
    generate = Mock(
        return_value=SimpleNamespace(
            candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)], text=candidate()
        )
    )
    sdk = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    assert VertexExtractor(sdk, model="synthetic-model").extract(request()) == candidate()
    config = generate.call_args.kwargs["config"]
    assert config.tools == []
    assert config.response_mime_type == "application/json"
    assert config.max_output_tokens == 512
    assert config.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
    assert json.loads(generate.call_args.kwargs["contents"])["message"] == request().message


def test_real_sdk_serializes_schema_and_parses_mock_response_without_network():
    def respond(http_request):
        payload = json.loads(http_request.content)
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert payload["generationConfig"]["responseSchema"]
        assert not payload.get("tools")
        return httpx2.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"role": "model", "parts": [{"text": candidate()}]},
                    }
                ]
            },
        )

    with genai.Client(
        enterprise=True,
        project="synthetic-project",
        location="global",
        credentials=Credentials(token="synthetic-test-token"),
        http_options=types.HttpOptions(
            client_args={"transport": httpx2.MockTransport(respond)},
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    ) as client:
        outcome = AssistantService(
            VertexExtractor(client, model="synthetic-model"), enabled=True
        ).extract(request())
    assert outcome.status == "extracted"
    assert outcome.details.guest_count == 20


@pytest.mark.parametrize("finish", [types.FinishReason.MAX_TOKENS, types.FinishReason.SAFETY])
def test_vertex_rejects_incomplete_or_blocked_responses(finish):
    sdk = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=Mock(
                return_value=SimpleNamespace(
                    candidates=[SimpleNamespace(finish_reason=finish)], text=candidate()
                )
            )
        )
    )
    with pytest.raises(ExtractionUnavailable):
        VertexExtractor(sdk, model="synthetic-model").extract(request())


def test_vertex_timeout_is_redacted_and_returns_fallback():
    sdk = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=Mock(side_effect=httpx2.ReadTimeout("synthetic-sensitive-value"))
        )
    )
    outcome = AssistantService(VertexExtractor(sdk, model="synthetic-model"), enabled=True).extract(
        request()
    )
    assert outcome.status == "fallback"
    assert "synthetic-sensitive-value" not in repr(outcome)


@pytest.mark.parametrize(
    "overrides",
    [
        {"assistant_timeout_ms": 999},
        {"assistant_timeout_ms": 60001},
        {"assistant_max_output_tokens": 127},
        {"assistant_max_output_tokens": 2049},
    ],
)
def test_configuration_rejects_unbounded_model_requests(overrides):
    with pytest.raises(ValidationError):
        AssistantSettings(natural_language_enabled=False, _env_file=None, **overrides)


def test_disabled_cli_never_initializes_vertex(monkeypatch, capsys):
    from parrilladas.modules.assistant import cli

    monkeypatch.setattr(
        cli,
        "AssistantSettings",
        lambda: AssistantSettings(natural_language_enabled=False, _env_file=None),
    )
    factory = Mock()
    monkeypatch.setattr(VertexExtractor, "from_settings", factory)
    assert cli.main() == 0
    factory.assert_not_called()
    assert "disabled" in capsys.readouterr().out


def test_synthetic_cli_validates_result_and_closes_provider(monkeypatch, capsys):
    from parrilladas.modules.assistant import cli

    settings = AssistantSettings(
        app_env="test",
        natural_language_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        _env_file=None,
    )
    monkeypatch.setattr(cli, "AssistantSettings", lambda: settings)

    def extract(request):
        year = request.reference_date.year + 1
        return candidate(
            details={
                "event_date": f"{year}-12-20",
                "guest_count": 20,
                "location": "Alajuela",
                "service_type": "parrilla",
            },
            date_evidence=f"20 de diciembre de {year}",
        )

    provider = SimpleNamespace(extract=Mock(side_effect=extract), close=Mock())
    monkeypatch.setattr(VertexExtractor, "from_settings", lambda _: provider)
    assert cli.main() == 0
    assert "Pilot passed" in capsys.readouterr().out
    provider.close.assert_called_once()


def test_cli_authentication_failure_has_nonzero_exit_without_sensitive_output(monkeypatch, capsys):
    from parrilladas.modules.assistant import cli

    settings = AssistantSettings(
        app_env="test",
        natural_language_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        _env_file=None,
    )
    monkeypatch.setattr(cli, "AssistantSettings", lambda: settings)
    monkeypatch.setattr(
        VertexExtractor,
        "from_settings",
        Mock(side_effect=ExtractionUnavailable("synthetic-sensitive-value")),
    )
    assert cli.main() == 1
    output = capsys.readouterr().out
    assert "authentication unavailable" in output
    assert "synthetic-sensitive-value" not in output


def test_production_connection_check_does_not_enable_natural_language():
    settings = AssistantSettings(
        app_env="production",
        vertex_connection_enabled=True,
        natural_language_enabled=False,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        _env_file=None,
    )
    assert settings.vertex_connection_enabled
    assert not settings.natural_language_enabled


def test_railway_service_credentials_are_explicit_and_hidden(monkeypatch):
    info = {
        "type": "service_account",
        "project_id": "synthetic-project",
        "token_uri": "https://oauth2.googleapis.com/token",
        "private_key": "synthetic-sensitive-value",
    }
    settings = AssistantSettings(
        app_env="production",
        vertex_connection_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        google_service_account_json=json.dumps(info),
        _env_file=None,
    )
    credentials = object()
    load = Mock(return_value=credentials)
    adc = Mock()
    factory = Mock()
    monkeypatch.setattr(
        "parrilladas.integrations.vertex_ai.client.service_account.Credentials.from_service_account_info",
        load,
    )
    monkeypatch.setattr("parrilladas.integrations.vertex_ai.client.google.auth.default", adc)
    monkeypatch.setattr("parrilladas.integrations.vertex_ai.client.genai.Client", factory)
    provider = VertexExtractor.from_settings(settings)
    assert load.call_args.args[0] == info
    assert factory.call_args.kwargs["credentials"] is credentials
    assert "synthetic-sensitive-value" not in repr(settings)
    adc.assert_not_called()
    provider.close()


@pytest.mark.parametrize(
    "info",
    [
        "not JSON",
        json.dumps([]),
        json.dumps({"type": "authorized_user"}),
        json.dumps(
            {
                "type": "service_account",
                "project_id": "another-project",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        json.dumps(
            {
                "type": "service_account",
                "project_id": "synthetic-project",
                "token_uri": "https://untrusted.example/token",
            }
        ),
    ],
)
def test_deployed_credentials_reject_wrong_project_personal_credentials_and_token_endpoints(info):
    settings = AssistantSettings(
        app_env="production",
        vertex_connection_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        google_service_account_json=info,
        _env_file=None,
    )
    with pytest.raises(ExtractionUnavailable, match="authentication unavailable"):
        VertexExtractor.from_settings(settings)


def test_production_rejects_personal_adc(monkeypatch):
    monkeypatch.setattr(
        "parrilladas.integrations.vertex_ai.client.google.auth.default",
        Mock(return_value=(Credentials(token="synthetic-test-token"), "synthetic-project")),
    )
    settings = AssistantSettings(
        app_env="production",
        vertex_connection_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        _env_file=None,
    )
    with pytest.raises(ExtractionUnavailable):
        VertexExtractor.from_settings(settings)


def test_default_cli_does_not_call_models_when_only_connectivity_is_enabled(monkeypatch, capsys):
    from parrilladas.modules.assistant import cli

    settings = AssistantSettings(
        app_env="production",
        vertex_connection_enabled=True,
        google_cloud_project="synthetic-project",
        google_cloud_location="global",
        gemini_model="synthetic-model",
        _env_file=None,
    )
    monkeypatch.setattr(cli, "AssistantSettings", lambda: settings)
    factory = Mock()
    monkeypatch.setattr(VertexExtractor, "from_settings", factory)
    assert cli.main() == 0
    factory.assert_not_called()
    assert "disabled" in capsys.readouterr().out
