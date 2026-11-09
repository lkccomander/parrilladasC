import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from parrilladas.modules.conversations.contracts import ButtonReply, InboxEvent, IncomingText
from parrilladas.modules.conversations.flow import decide
from parrilladas.modules.conversations.repository import ConversationRepository, InboxRepository


@dataclass(frozen=True)
class OutboundAction:
    event_key: str
    recipient: str
    text: str
    buttons: tuple[tuple[str, str], ...]


OutboundSender = Callable[[OutboundAction], str]


class InboxService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = InboxRepository(session)

    def receive(self, events: list[InboxEvent]) -> None:
        # Acknowledge only after the entire batch commits. Sorted keys also give
        # overlapping concurrent batches a consistent unique-index lock order.
        with self.session.begin():
            for event in sorted(events, key=lambda event: event.event_key):
                self.repository.add(event)


class ConversationService:
    """Persist verified customer messages and prepare idempotent bot actions."""

    def __init__(self, session: Session, sender: OutboundSender | None = None):
        self.session = session
        self.inbox = InboxRepository(session)
        self.repository = ConversationRepository(session)
        self.sender = sender

    def receive(self, events: list[InboxEvent]) -> None:
        if not any(event.kind == "message" for event in events):
            return
        for event in sorted(events, key=lambda item: item.event_key):
            prepared = self._prepare(event)
            if prepared is not None and self.sender is not None:
                self._deliver(*prepared)

    def _prepare(self, event: InboxEvent) -> tuple[UUID, OutboundAction] | None:
        with self.session.begin():
            inbox_event = self.inbox.ensure(event)
            if inbox_event.processed_at is not None:
                return None
            if event.kind != "message":
                self.inbox.mark_processed(inbox_event)
                return None

            message = event.payload["value"]["messages"][0]
            recipient = message["from"]
            external_id = message["id"]
            incoming = self._incoming(message)
            content = self._content(message, incoming)
            conversation = self.repository.get_or_create(recipient)
            if (
                self.repository.add_inbound(
                    conversation_id=conversation.id,
                    external_message_id=external_id,
                    content=content,
                )
                is None
            ):
                self.inbox.mark_processed(inbox_event)
                return None
            if conversation.bot_paused:
                self.inbox.mark_processed(inbox_event)
                return None

            decision = decide(conversation.flow_step, incoming, flow_data=conversation.flow_data)
            if not decision.should_respond:
                self.inbox.mark_processed(inbox_event)
                return None
            conversation.flow_step = decision.step
            if decision.handoff:
                conversation.bot_paused = True
            if decision.reset:
                conversation.flow_data = {}
            else:
                updates = dict(decision.updates)
                if (
                    conversation.flow_step == "event_type"
                    and isinstance(incoming, ButtonReply)
                    and incoming.id.strip().casefold() in {"request_quote", "quote"}
                ):
                    updates["request_reference"] = f"PEC-{secrets.token_hex(5).upper()}"
                conversation.flow_data = {
                    **(conversation.flow_data or {}),
                    **updates,
                }
            action = OutboundAction(
                event_key=event.event_key,
                recipient=recipient,
                text=decision.text,
                buttons=decision.buttons,
            )
            outbound = self.repository.add_outbound(
                conversation_id=conversation.id,
                event_key=event.event_key,
                content=json.dumps(
                    {"text": action.text, "buttons": action.buttons},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            self.inbox.mark_processed(inbox_event)
            return outbound.id, action

    def _deliver(self, message_id: UUID, action: OutboundAction) -> None:
        try:
            external_id = self.sender(action)
        except Exception:
            with self.session.begin():
                self.repository.mark_failed(message_id)
            return
        with self.session.begin():
            self.repository.mark_sent(message_id, external_id)

    @staticmethod
    def _incoming(message: dict) -> IncomingText | ButtonReply:
        if message.get("type") == "interactive":
            reply = message.get("interactive", {}).get("button_reply", {})
            return ButtonReply(id=reply["id"], title=reply.get("title"))
        return IncomingText(body=message.get("text", {}).get("body", ""))

    @staticmethod
    def _content(message: dict, incoming: IncomingText | ButtonReply) -> str:
        if isinstance(incoming, IncomingText):
            return incoming.body
        return json.dumps(
            {"id": incoming.id, "title": incoming.title},
            ensure_ascii=False,
            separators=(",", ":"),
        )
