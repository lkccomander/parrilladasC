from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base, Record


class Conversation(Record, Base):
    __tablename__ = "conversations"

    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    whatsapp_number: Mapped[str] = mapped_column(String(32), index=True)
    bot_paused: Mapped[bool] = mapped_column(default=False)
    flow_step: Mapped[str] = mapped_column(String(64), default="start")


class Message(Record, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    direction: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(32), default="pending")
