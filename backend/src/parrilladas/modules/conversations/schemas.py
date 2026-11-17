from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

InteractionStatus = Literal["active", "submitted", "referred"]


class InteractionFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, le=100000)
    q: str = Field(default="", max_length=100)
    status: InteractionStatus | None = None


class InteractionView(BaseModel):
    id: UUID
    reference: str
    status: InteractionStatus
    whatsapp_number: str
    bot_paused: bool
    created_at: AwareDatetime
    closed_at: AwareDatetime | None
    event_date: str | None
    guest_count: int | None
    location: str | None
    service_type: str | None


class InteractionPage(BaseModel):
    items: list[InteractionView]
    total: int
    page: int
    page_size: int
