from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, false
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base


class AssistantPreference(Base):
    __tablename__ = "assistant_preferences"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    natural_language_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    advisor_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    advisor_name: Mapped[str | None] = mapped_column(String(80))
    advisor_phone: Mapped[str | None] = mapped_column(String(16))
    advisor_template: Mapped[str | None] = mapped_column(String(100))
    advisor_language: Mapped[str | None] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
