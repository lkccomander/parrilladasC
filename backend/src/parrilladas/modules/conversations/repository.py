from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Numeric, case, cast, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from parrilladas.modules.conversations.contracts import InboxEvent
from parrilladas.modules.conversations.models import Conversation, Message, WhatsAppInboxEvent


class InboxRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, event: InboxEvent) -> None:
        self.session.execute(
            insert(WhatsAppInboxEvent)
            .values(event_key=event.event_key, kind=event.kind, payload=event.payload)
            .on_conflict_do_nothing(index_elements=[WhatsAppInboxEvent.event_key])
        )

    def get(self, event_key: str) -> WhatsAppInboxEvent | None:
        return self.session.scalar(
            select(WhatsAppInboxEvent).where(WhatsAppInboxEvent.event_key == event_key)
        )

    def ensure(self, event: InboxEvent) -> WhatsAppInboxEvent:
        self.add(event)
        row = self.get(event.event_key)
        if row is None:  # pragma: no cover - guarded by the database unique constraint
            raise RuntimeError("WhatsApp inbox event was not persisted")
        return row

    def mark_processed(self, event: WhatsAppInboxEvent) -> None:
        event.processed_at = datetime.now(UTC)

    def lock_worker(self) -> bool:
        # Serialize this single-business pilot across replicas, not just threads.
        return bool(self.session.scalar(select(func.pg_try_advisory_xact_lock(74291301))))

    def next_pending(self, not_before: datetime) -> WhatsAppInboxEvent | None:
        timestamp = WhatsAppInboxEvent.payload["value"]["messages"][0]["timestamp"].as_string()
        return self.session.scalar(
            select(WhatsAppInboxEvent)
            .where(
                WhatsAppInboxEvent.processed_at.is_(None),
                WhatsAppInboxEvent.created_at >= not_before,
            )
            .order_by(
                case(
                    (WhatsAppInboxEvent.kind == "message", cast(timestamp, Numeric(20, 0))), else_=0
                ),
                WhatsAppInboxEvent.created_at,
                WhatsAppInboxEvent.id,
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )


class ConversationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create(self, whatsapp_number: str) -> Conversation:
        self.session.execute(
            insert(Conversation)
            .values(whatsapp_number=whatsapp_number, flow_step="start", flow_data={})
            .on_conflict_do_nothing(index_elements=[Conversation.whatsapp_number])
        )
        conversation = self.session.scalar(
            select(Conversation)
            .where(Conversation.whatsapp_number == whatsapp_number)
            .with_for_update()
        )
        if conversation is None:  # pragma: no cover - guarded by the database insert
            raise RuntimeError("Conversation was not persisted")
        if conversation.flow_data is None:
            conversation.flow_data = {}
        return conversation

    def add_inbound(
        self,
        *,
        conversation_id: UUID,
        external_message_id: str,
        content: str,
    ) -> Message | None:
        result = self.session.execute(
            insert(Message)
            .values(
                conversation_id=conversation_id,
                external_message_id=external_message_id,
                direction="inbound",
                content=content,
                delivery_status="received",
            )
            .on_conflict_do_nothing(index_elements=[Message.external_message_id])
            .returning(Message.id)
        )
        message_id = result.scalar_one_or_none()
        if message_id is None:
            return None
        return self.session.get(Message, message_id)

    def add_outbound(
        self,
        *,
        conversation_id: UUID,
        event_key: str,
        content: str,
    ) -> Message:
        result = self.session.execute(
            insert(Message)
            .values(
                conversation_id=conversation_id,
                event_key=event_key,
                direction="outbound",
                content=content,
                delivery_status="pending",
            )
            .on_conflict_do_nothing(index_elements=[Message.event_key])
            .returning(Message.id)
        )
        message_id = result.scalar_one_or_none()
        if message_id is None:
            existing = self.session.scalar(select(Message).where(Message.event_key == event_key))
            if existing is None:  # pragma: no cover - guarded by the unique constraint
                raise RuntimeError("Outbound message was not persisted")
            return existing
        message = self.session.get(Message, message_id)
        if message is None:  # pragma: no cover - guarded by the insert
            raise RuntimeError("Outbound message was not persisted")
        return message

    def mark_sent(self, message_id: UUID, external_message_id: str) -> None:
        self.session.execute(
            update(Message)
            .where(Message.id == message_id)
            .values(delivery_status="sent", external_message_id=external_message_id)
        )

    def mark_failed(self, message_id: UUID) -> None:
        self.session.execute(
            update(Message).where(Message.id == message_id).values(delivery_status="failed")
        )

    def next_outbound(self, not_before: datetime):
        attempt = aliased(Message)
        return self.session.execute(
            select(Message, Conversation)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.direction == "outbound",
                Message.delivery_status == "pending",
                Message.created_at >= not_before,
                ~exists().where(
                    attempt.conversation_id == Message.conversation_id,
                    attempt.delivery_status.in_(("sending", "uncertain")),
                ),
            )
            .order_by(Message.created_at, Message.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()

    def mark_uncertain(self, message_id: UUID) -> None:
        self.session.execute(
            update(Message).where(Message.id == message_id).values(delivery_status="uncertain")
        )
        self.session.execute(
            update(Conversation)
            .where(
                Conversation.id
                == select(Message.conversation_id).where(Message.id == message_id).scalar_subquery()
            )
            .values(bot_paused=True)
        )
