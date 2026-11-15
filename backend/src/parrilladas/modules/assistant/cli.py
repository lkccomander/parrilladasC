"""Run a synthetic extraction pilot without connecting WhatsApp or PostgreSQL."""

from datetime import date

from pydantic import ValidationError

from .config import AssistantSettings
from .errors import ExtractionUnavailable
from .schemas import ExtractionRequest
from .service import AssistantService


def main(*, check_connection: bool = False) -> int:
    try:
        settings = AssistantSettings()
    except ValidationError:
        print("Invalid assistant configuration. See docs/assistant.md.")
        return 1
    enabled = (
        settings.vertex_connection_enabled
        if check_connection
        else settings.natural_language_enabled
    )
    if not enabled:
        print("Extraction pilot disabled. No model call was made.")
        return 0

    from parrilladas.integrations.vertex_ai.client import VertexExtractor

    today = ExtractionRequest(message="pilot").reference_date
    event_date = date(today.year + 1, 12, 20)
    request = ExtractionRequest(
        message=(
            f"Quiero una parrillada para 20 personas el 20 de diciembre "
            f"de {event_date.year} en Alajuela."
        ),
        reference_date=today,
    )
    try:
        provider = VertexExtractor.from_settings(settings)
    except ExtractionUnavailable:
        print(
            "Model authentication unavailable. Check the configured workload identity or local ADC."
        )
        return 1
    try:
        outcome = AssistantService(provider, enabled=True).extract(request)
    finally:
        provider.close()
    if (
        outcome.status != "extracted"
        or outcome.missing_fields
        or outcome.ambiguities
        or outcome.details.event_date != event_date
        or outcome.details.guest_count != 20
        or outcome.details.location != "Alajuela"
        or outcome.details.service_type != "parrilla"
    ):
        print(f"Pilot did not pass: {outcome.reason}. No customer message was sent.")
        return 1
    label = "Connection check passed" if check_connection else "Pilot passed"
    print(f"{label}: validated synthetic extraction; no customer message sent.")
    print(outcome.model_dump_json())
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-connection", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(main(check_connection=arguments.check_connection))
