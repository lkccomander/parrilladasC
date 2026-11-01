from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base, Record


class Reminder(Record, Base):
    __tablename__ = "reminders"

    quote_id: Mapped[UUID] = mapped_column(ForeignKey("quotes.id"), unique=True)
    assigned_account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    notes: Mapped[str | None] = mapped_column(Text)
