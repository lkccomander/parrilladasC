import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

KnowledgeTopic = Literal[
    "menu", "coverage", "preparation", "pricing", "availability", "allergens", "policies", "general"
]

EventField = Literal["event_date", "guest_count", "location", "service_type"]
EVENT_FIELDS: tuple[EventField, ...] = (
    "event_date",
    "guest_count",
    "location",
    "service_type",
)


class EventDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    event_date: date | None = Field(default=None, repr=False)
    guest_count: int | None = Field(default=None, ge=1, strict=True, repr=False)
    location: str | None = Field(default=None, min_length=1, max_length=200, repr=False)
    service_type: Literal["parrilla"] | None = None

    @field_validator("event_date", mode="before")
    @classmethod
    def require_complete_date(cls, value):
        if value is None or type(value) is date:
            return value
        if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return date.fromisoformat(value)
        raise ValueError("Use a complete ISO event date")

    @field_validator("location")
    @classmethod
    def reject_blank_location(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Location cannot be blank")
        return value.strip() if value is not None else None


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    message: str = Field(min_length=1, max_length=4000, repr=False)
    confirmed: EventDetails = Field(default_factory=EventDetails, repr=False)
    requested_field: EventField | None = None
    reference_date: date = Field(
        default_factory=lambda: datetime.now(ZoneInfo("America/Costa_Rica")).date()
    )

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value):
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value


class ExtractionCandidate(BaseModel):
    """Untrusted provider output: these fields never authorize business actions."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    intent: Literal["quote", "business_question", "human_handoff", "unsupported"]
    topic: KnowledgeTopic = "general"
    details: EventDetails = Field(repr=False)
    ambiguities: list[EventField] = Field(default_factory=list, max_length=4)
    date_evidence: str | None = Field(default=None, max_length=4000, repr=False)


class ExtractionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["disabled", "paused", "fallback", "handoff", "knowledge", "extracted"]
    reason: Literal[
        "disabled",
        "human_control",
        "provider_unavailable",
        "invalid_output",
        "unsupported",
        "knowledge_not_available",
        "requested_handoff",
        "review_required",
    ]
    details: EventDetails = Field(repr=False)
    topic: KnowledgeTopic = "general"
    proposed_changes: EventDetails = Field(default_factory=EventDetails, repr=False)
    missing_fields: tuple[EventField, ...] = ()
    changed_fields: tuple[EventField, ...] = ()
    ambiguities: tuple[EventField, ...] = ()


class AdvisorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    enabled: bool = Field(default=False, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{7,14}$", repr=False)
    template: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,100}$")
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}(?:_[A-Z]{2})?$")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Nombre del asesor vacío")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_enabled_configuration(self):
        if self.enabled and not all((self.name, self.phone, self.template, self.language)):
            raise ValueError(
                "Complete nombre, WhatsApp, plantilla e idioma antes de habilitar al asesor."
            )
        return self


class AdvisorNotificationView(BaseModel):
    reference: str
    status: str
    reason: str | None = None
    created_at: datetime


class AssistantPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    natural_language_enabled: bool = Field(strict=True)


class AssistantPreferencesView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str
    natural_language_enabled: bool
    active_mode: Literal["guided", "natural_language"] = "guided"
    updated_at: datetime | None = None
    updated_by: UUID | None = None


class AdvisorPreferencesView(BaseModel):
    settings: AdvisorSettings = Field(default_factory=AdvisorSettings)
    notifications: list[AdvisorNotificationView] = Field(default_factory=list)
