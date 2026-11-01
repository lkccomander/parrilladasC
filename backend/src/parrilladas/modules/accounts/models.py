from enum import StrEnum

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base, Record


class Role(StrEnum):
    ADMIN = "admin"
    SALES = "sales"


class Account(Record, Base):
    __tablename__ = "accounts"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.SALES)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
