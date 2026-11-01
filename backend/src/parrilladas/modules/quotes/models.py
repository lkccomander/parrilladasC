from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base, Record


class Quote(Record, Base):
    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint("total >= 0", name="nonnegative_total"),
        CheckConstraint("version > 0", name="positive_version"),
    )

    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="CRC")
    version: Mapped[int] = mapped_column(default=1)
    approved_version: Mapped[int | None]
    approved_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
