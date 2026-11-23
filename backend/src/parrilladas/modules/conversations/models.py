from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base, Record


class Conversation(Record, Base):
    __tablename__ = "conversations"

    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    whatsapp_number: Mapped[str] = mapped_column(String(32), index=True, unique=True)
    bot_paused: Mapped[bool] = mapped_column(default=False)
    flow_step: Mapped[str] = mapped_column(String(64), default="start")
    flow_data: Mapped[dict | None] = mapped_column(JSONB)


class Message(Record, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    interaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversation_interactions.id"), index=True
    )
    recipient: Mapped[str | None] = mapped_column(String(32))
    purpose: Mapped[str] = mapped_column(String(32), default="customer", server_default="customer")
    depends_on_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id"))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_message_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    direction: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(32), default="pending")
    event_key: Mapped[str | None] = mapped_column(String(64), unique=True)


class WhatsAppInboxEvent(Record, Base):
    """Verified provider events awaiting durable conversation processing."""

    __tablename__ = "whatsapp_inbox_events"

    event_key: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSONB)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Interaction(Record, Base):
    __tablename__ = "conversation_interactions"

    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="active", server_default="active")
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index(
    "uq_interaction_active_conversation",
    Interaction.conversation_id,
    unique=True,
    postgresql_where=text("status = 'active'"),
)
