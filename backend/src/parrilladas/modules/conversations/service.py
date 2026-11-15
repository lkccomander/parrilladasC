import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from parrilladas.modules.assistant.preferences import ACTIVE_TENANT_ID, AssistantPreferenceService
from parrilladas.modules.assistant.service import AssistantService
from parrilladas.modules.conversations.contracts import ButtonReply, InboxEvent, IncomingText
from parrilladas.modules.conversations.flow import decide
from parrilladas.modules.conversations.natural_language import NL_STEPS, natural_language_decision
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

    def __init__(
        self,
        session: Session,
        sender: OutboundSender | None = None,
        *,
        assistant: AssistantService | None = None,
    ):
        self.session = session
        self.inbox = InboxRepository(session)
        self.repository = ConversationRepository(session)
        self.sender = sender
        self.assistant = assistant or AssistantService()

    def receive(self, events: list[InboxEvent]) -> None:
        if not any(event.kind == "message" for event in events):
            return
        for event in sorted(events, key=lambda item: item.event_key):
            prepared = self._prepare(event)
            if prepared is not None and self.sender is not None:
                self._deliver(*prepared)

    def _prepare(self, event: InboxEvent) -> tuple[UUID, OutboundAction] | None:
        with self.session.begin():
            return self._prepare_locked(event)

    def _prepare_locked(self, event: InboxEvent) -> tuple[UUID, OutboundAction] | None:
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
        if conversation.bot_paused or conversation.flow_step == "submitted":
            self.inbox.mark_processed(inbox_event)
            return None

        nl_enabled = self.assistant.enabled and AssistantPreferenceService(
            self.session
        ).requested_for_tenant(ACTIVE_TENANT_ID)
        decision = None
        if nl_enabled:
            decision = natural_language_decision(
                conversation.flow_step, incoming, conversation.flow_data or {}, self.assistant
            )
        elif conversation.flow_step in NL_STEPS:
            decision = natural_language_decision(
                conversation.flow_step, incoming, conversation.flow_data or {}, AssistantService()
            )
        if decision is None:
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
            if decision.step in NL_STEPS and not conversation.flow_data.get("request_reference"):
                updates["request_reference"] = f"PEC-{secrets.token_hex(5).upper()}"
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
                {
                    "text": action.text,
                    "buttons": action.buttons,
                    "handoff_notice": decision.handoff,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        self.inbox.mark_processed(inbox_event)
        return outbound.id, action

    def process_next(
        self, *, not_before: datetime, business_account_id: str, phone_number_id: str
    ) -> bool:
        with self.session.begin():
            if not self.inbox.lock_worker():
                return False
            row = self.inbox.next_pending(not_before)
            if row is None:
                return False
            value = row.payload.get("value", {})
            verified = (
                row.payload.get("business_account_id") == business_account_id
                and value.get("metadata", {}).get("phone_number_id") == phone_number_id
            )
            if row.kind == "message" and verified:
                message = value["messages"][0]
                if int(message["timestamp"]) < int(not_before.timestamp()):
                    self.inbox.mark_processed(row)
                else:
                    self._prepare_locked(InboxEvent(row.event_key, row.kind, row.payload))
            else:
                self.inbox.mark_processed(row)
            return True

    def deliver_next(self, *, not_before: datetime) -> bool:
        with self.session.begin():
            if not self.inbox.lock_worker():
                return False
            selected = self.repository.next_outbound(not_before)
            if selected is None:
                return False
            message, conversation = selected
            payload = json.loads(message.content)
            if conversation.bot_paused and not payload.get("handoff_notice", False):
                message.delivery_status = "cancelled"
                return True
            # Persist BEFORE calling Meta. Crashed/ambiguous attempts remain
            # sending/uncertain and are never automatically sent a second time.
            message.delivery_status = "sending"
            message_id = message.id
            action = OutboundAction(
                event_key=message.event_key,
                recipient=conversation.whatsapp_number,
                text=payload["text"],
                buttons=tuple(tuple(button) for button in payload["buttons"]),
            )
        self._deliver(message_id, action, uncertain_on_failure=True)
        return True

    def _deliver(
        self, message_id: UUID, action: OutboundAction, *, uncertain_on_failure: bool = False
    ) -> None:
        try:
            external_id = self.sender(action)
        except Exception:
            with self.session.begin():
                if uncertain_on_failure:
                    self.repository.mark_uncertain(message_id)
                else:
                    self.repository.mark_failed(message_id)
            return
        with self.session.begin():
            self.repository.mark_sent(message_id, external_id)

    @staticmethod
    def _incoming(message: dict) -> IncomingText | ButtonReply:
        if message.get("type") == "interactive":
            interactive = message.get("interactive")
            reply = interactive.get("button_reply") if isinstance(interactive, dict) else None
            if isinstance(reply, dict) and isinstance(reply.get("id"), str):
                return ButtonReply(id=reply["id"], title=reply.get("title"))
        text = message.get("text")
        body = text.get("body") if isinstance(text, dict) else None
        return IncomingText(body=body if isinstance(body, str) else "")

    @staticmethod
    def _content(message: dict, incoming: IncomingText | ButtonReply) -> str:
        if isinstance(incoming, IncomingText):
            return incoming.body
        return json.dumps(
            {"id": incoming.id, "title": incoming.title},
            ensure_ascii=False,
            separators=(",", ":"),
        )
