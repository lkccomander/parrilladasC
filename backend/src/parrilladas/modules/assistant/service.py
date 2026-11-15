import re
from typing import Protocol

from pydantic import ValidationError

from .errors import ExtractionUnavailable
from .schemas import (
    EVENT_FIELDS,
    EventDetails,
    ExtractionCandidate,
    ExtractionOutcome,
    ExtractionRequest,
)


class Extractor(Protocol):
    def extract(self, request: ExtractionRequest) -> str: ...


class AssistantService:
    def __init__(self, provider: Extractor | None = None, *, enabled: bool = False):
        self.provider = provider
        self.enabled = enabled

    def extract(self, request: ExtractionRequest, *, bot_paused: bool = False) -> ExtractionOutcome:
        def unchanged(status, reason):
            return ExtractionOutcome(
                status=status,
                reason=reason,
                details=request.confirmed,
                missing_fields=tuple(
                    field for field in EVENT_FIELDS if getattr(request.confirmed, field) is None
                ),
            )

        if bot_paused:
            return unchanged("paused", "human_control")
        if not self.enabled:
            return unchanged("disabled", "disabled")
        if self.provider is None:
            return unchanged("fallback", "provider_unavailable")
        try:
            raw = self.provider.extract(request)
            if not isinstance(raw, str) or len(raw) > 16000:
                return unchanged("fallback", "invalid_output")
            candidate = ExtractionCandidate.model_validate_json(raw)
        except ExtractionUnavailable:
            return unchanged("fallback", "provider_unavailable")
        except ValidationError:
            return unchanged("fallback", "invalid_output")

        if candidate.intent == "human_handoff":
            return unchanged("handoff", "requested_handoff")
        if candidate.intent == "business_question":
            return unchanged("handoff", "knowledge_not_available")
        if candidate.intent == "unsupported":
            return unchanged("fallback", "unsupported")

        ambiguities = set(candidate.ambiguities)
        event_date = candidate.details.event_date
        if event_date is not None:
            evidence = candidate.date_evidence or ""
            if (
                not evidence
                or evidence not in request.message
                or not re.search(rf"(?<![0-9]){event_date.year}(?![0-9])", evidence)
                or event_date < request.reference_date
            ):
                ambiguities.add("event_date")

        details = request.confirmed.model_dump()
        proposals = {}
        for field in EVENT_FIELDS:
            value = getattr(candidate.details, field)
            if field in ambiguities or value is None:
                continue
            if details[field] is None:
                details[field] = value
            elif details[field] != value:
                proposals[field] = value

        return ExtractionOutcome(
            status="extracted",
            reason="review_required",
            details=EventDetails.model_validate(details),
            proposed_changes=EventDetails.model_validate(proposals),
            missing_fields=tuple(field for field in EVENT_FIELDS if details[field] is None),
            changed_fields=tuple(field for field in EVENT_FIELDS if field in proposals),
            ambiguities=tuple(field for field in EVENT_FIELDS if field in ambiguities),
        )
