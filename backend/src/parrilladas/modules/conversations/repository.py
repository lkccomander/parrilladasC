import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Numeric, case, cast, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from parrilladas.modules.conversations.contracts import InboxEvent, child_event_key
from parrilladas.modules.conversations.models import (
    Conversation,
    Interaction,
    Message,
    WhatsAppInboxEvent,
)


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

    def list_interactions(self, *, search: str, status: str | None, offset: int, limit: int):
        conditions = []
        if status:
            conditions.append(Interaction.status == status)
        if search:
            conditions.append(
                or_(
                    Interaction.reference.icontains(search, autoescape=True),
                    Conversation.whatsapp_number.contains(search, autoescape=True),
                )
            )
        query = (
            select(Interaction, Conversation)
            .join(Conversation, Conversation.id == Interaction.conversation_id)
            .where(*conditions)
        )
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.session.execute(
            query.order_by(Interaction.created_at.desc(), Interaction.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return rows, total

    def interaction_for_reference(
        self, conversation_id: UUID, reference: str | None
    ) -> Interaction | None:
        return self.session.scalar(
            select(Interaction)
            .where(
                Interaction.conversation_id == conversation_id,
                Interaction.reference == reference,
            )
            .with_for_update()
        )

    def active_interaction(self, conversation: Conversation) -> Interaction:
        row = self.session.scalar(
            select(Interaction)
            .where(Interaction.conversation_id == conversation.id, Interaction.status == "active")
            .with_for_update()
        )
        if row is None:
            reference = (conversation.flow_data or {}).get("request_reference")
            if not reference or self.session.scalar(
                select(Interaction.id).where(Interaction.reference == reference)
            ):
                reference = f"PEC-{secrets.token_hex(6).upper()}"
            row = Interaction(
                conversation_id=conversation.id,
                reference=reference,
                snapshot=dict(conversation.flow_data or {}),
            )
            self.session.add(row)
            self.session.flush()
        conversation.flow_data = {
            **(conversation.flow_data or {}),
            "request_reference": row.reference,
        }
        return row

    def outbound_context(self, external_id: str) -> Message | None:
        return self.session.scalar(
            select(Message).where(
                Message.external_message_id == external_id, Message.direction == "outbound"
            )
        )

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
        interaction_id: UUID | None = None,
        recipient: str | None = None,
        purpose: str = "customer",
        depends_on_id: UUID | None = None,
        delivery_status: str = "pending",
    ) -> Message:
        result = self.session.execute(
            insert(Message)
            .values(
                conversation_id=conversation_id,
                event_key=event_key,
                direction="outbound",
                interaction_id=interaction_id,
                recipient=recipient,
                purpose=purpose,
                depends_on_id=depends_on_id,
                content=content,
                delivery_status=delivery_status,
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

    def get_message(self, message_id: UUID) -> Message:
        return self.session.get(Message, message_id)

    def cancel_pending(self, interaction_id: UUID) -> None:
        self.session.execute(
            update(Message)
            .where(
                Message.interaction_id == interaction_id,
                Message.purpose == "customer",
                Message.delivery_status == "pending",
            )
            .values(delivery_status="cancelled")
        )

    def recent_customer_texts(self, interaction_id: UUID) -> list[str]:
        return list(
            self.session.scalars(
                select(Message.content)
                .where(
                    Message.interaction_id == interaction_id,
                    Message.direction == "inbound",
                )
                .order_by(Message.created_at.desc())
                .limit(4)
            )
        )

    def recent_advisor_notifications(self):
        return self.session.execute(
            select(
                Interaction.reference, Message.delivery_status, Message.content, Message.created_at
            )
            .join(Message, Message.interaction_id == Interaction.id)
            .where(Message.purpose == "advisor_notification")
            .order_by(Message.created_at.desc())
            .limit(10)
        )

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

    def next_outbound(self, not_before: datetime, event_prefix: str | None = None):
        attempt = aliased(Message)
        parent = aliased(Message)
        earlier = aliased(Message)
        query = (
            select(Message, Conversation)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.direction == "outbound",
                Message.delivery_status == "pending",
                Message.created_at >= not_before,
                ~exists().where(
                    attempt.conversation_id == Message.conversation_id,
                    attempt.purpose == "customer",
                    attempt.delivery_status.in_(("sending", "uncertain")),
                ),
                or_(
                    Message.depends_on_id.is_(None),
                    exists().where(
                        parent.id == Message.depends_on_id,
                        parent.delivery_status.in_(
                            ("sent", "delivered", "read", "failed", "uncertain", "cancelled")
                        ),
                    ),
                ),
                ~exists().where(
                    earlier.conversation_id == Message.conversation_id,
                    earlier.purpose == "customer",
                    earlier.delivery_status == "pending",
                    earlier.created_at >= not_before,
                    earlier.created_at < Message.created_at,
                ),
            )
        )
        if event_prefix is not None:
            query = query.where(
                Message.event_key.in_(
                    [child_event_key(event_prefix, kind) for kind in ("advisor", "ack", "welcome")]
                )
            )
        return self.session.execute(
            query.order_by(Message.created_at, Message.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()

    def recover_advisor_attempts(self, before: datetime) -> None:
        self.session.execute(
            update(Message)
            .where(
                Message.purpose.in_(("advisor_notification", "confirmation_notification")),
                Message.delivery_status == "sending",
                Message.attempted_at < before,
            )
            .values(delivery_status="uncertain")
        )

    def update_advisor_status(self, external_id: str, status: str) -> None:
        row = self.outbound_context(external_id)
        # Meta sends delivery callbacks for every outbound WhatsApp message.
        # Confirmation notices use a different purpose, but need the same
        # delivery lifecycle as advisor handoffs.
        if row is None or row.purpose not in {
            "advisor_notification",
            "confirmation_notification",
        }:
            return
        ranks = {"sent": 1, "delivered": 2, "read": 3}
        if (
            status in ranks
            and ranks[status] > ranks.get(row.delivery_status, 0)
            and row.delivery_status != "failed"
        ):
            row.delivery_status = status
        elif status == "failed" and row.delivery_status not in {"delivered", "read"}:
            row.delivery_status = "failed"

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
