from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base, Record


class Lead(Record, Base):
    __tablename__ = "leads"
    __table_args__ = (CheckConstraint("guest_count > 0", name="positive_guest_count"),)

    contact_name: Mapped[str | None] = mapped_column(String(120))
    whatsapp_number: Mapped[str] = mapped_column(String(32), index=True)
    event_date: Mapped[date | None] = mapped_column(Date)
    time_preference: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(Text)
    guest_count: Mapped[int | None]
    service_type: Mapped[str | None] = mapped_column(String(120))
    requirements: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    assigned_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"))
