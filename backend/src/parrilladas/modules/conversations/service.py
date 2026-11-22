import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from parrilladas.modules.assistant.preferences import ACTIVE_TENANT_ID, AssistantPreferenceService
from parrilladas.modules.assistant.service import AssistantService
from parrilladas.modules.conversations.contracts import (
    ButtonReply,
    FlowReply,
    InboxEvent,
    IncomingText,
    child_event_key,
)
from parrilladas.modules.conversations.flow import GREETING, MENU_BUTTONS, decide
from parrilladas.modules.conversations.models import Conversation
from parrilladas.modules.conversations.natural_language import NL_STEPS, natural_language_decision
from parrilladas.modules.conversations.repository import ConversationRepository, InboxRepository
from parrilladas.modules.notifications.service import (
    enqueue_confirmation_notifications,
)


@dataclass(frozen=True)
class OutboundAction:
    event_key: str
    recipient: str
    text: str
    buttons: tuple[tuple[str, str], ...]
    purpose: str = "customer"
    template_name: str | None = None
    template_language: str | None = None
    template_parameters: tuple[str, ...] = ()
    flow_id: str | None = None
    channel: str = "whatsapp"
    subject: str | None = None


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
        quote_flow_id: str | None = None,
        notification_whatsapp_numbers: tuple[str, ...] = (),
        notification_email_recipients: tuple[str, ...] = (),
    ):
        self.session = session
        self.inbox = InboxRepository(session)
        self.repository = ConversationRepository(session)
        self.sender = sender
        self.assistant = assistant or AssistantService()
        self.quote_flow_id = quote_flow_id
        self.notification_whatsapp_numbers = notification_whatsapp_numbers
        self.notification_email_recipients = notification_email_recipients

    def receive(self, events: list[InboxEvent]) -> None:
        if not any(event.kind == "message" for event in events):
            return
        for event in sorted(events, key=lambda item: item.event_key):
            prepared = self._prepare(event)
            if prepared is not None and self.sender is not None:
                self._deliver(*prepared)
                # Inline webhook mode must also drain confirmation notifications;
                # the durable worker performs the same work asynchronously.
                for _ in range(8):
                    if not self.deliver_next(not_before=datetime.min.replace(tzinfo=UTC)):
                        break
            elif self.sender is not None:
                # Legacy inline mode drains only this event's newly queued handoff.
                for _ in range(3):
                    if not self.deliver_next(
                        not_before=datetime.min.replace(tzinfo=UTC), event_prefix=event.event_key
                    ):
                        break

    def _prepare(self, event: InboxEvent) -> tuple[UUID, OutboundAction] | None:
        with self.session.begin():
            return self._prepare_locked(event)

    def _restart_submitted(self, conversation: Conversation) -> None:
        # Preserve legacy requests too, even if they predate interaction tracking.
        reference = (conversation.flow_data or {}).get("request_reference")
        previous = self.repository.interaction_for_reference(conversation.id, reference)
        if previous is None:
            previous = self.repository.active_interaction(conversation)
        if previous.status == "active":
            previous.snapshot = dict(conversation.flow_data or {})
            previous.status = "submitted"
            previous.closed_at = datetime.now(UTC)
            self.session.flush()
        conversation.flow_step = "start"
        conversation.flow_data = {}

    def _prepare_locked(self, event: InboxEvent) -> tuple[UUID, OutboundAction] | None:
        inbox_event = self.inbox.ensure(event)
        if inbox_event.processed_at is not None:
            return None
        if event.kind != "message":
            if event.kind == "status":
                for status in event.payload.get("value", {}).get("statuses", []):
                    self.repository.update_advisor_status(status["id"], status["status"])
            self.inbox.mark_processed(inbox_event)
            return None

        message = event.payload["value"]["messages"][0]
        recipient = message["from"]
        external_id = message["id"]
        incoming = self._incoming(message)
        content = self._content(message, incoming)
        conversation = self.repository.get_or_create(recipient)
        inbound = self.repository.add_inbound(
            conversation_id=conversation.id,
            external_message_id=external_id,
            content=content,
        )
        if inbound is None:
            self.inbox.mark_processed(inbox_event)
            return None
        if conversation.bot_paused:
            self.inbox.mark_processed(inbox_event)
            return None
        advisor = AssistantPreferenceService(self.session).advisor_for_tenant(ACTIVE_TENANT_ID)
        context = message.get("context")
        context_id = context.get("id") if isinstance(context, dict) else None
        origin = self.repository.outbound_context(context_id) if context_id else None
        if origin and origin.purpose == "advisor_notification" and origin.recipient == recipient:
            # Replies to internal notices never become new customer requests.
            self.inbox.mark_processed(inbox_event)
            return None
        if conversation.flow_step == "submitted":
            if not isinstance(incoming, IncomingText) or not incoming.body.strip():
                if origin and origin.conversation_id == conversation.id:
                    inbound.interaction_id = origin.interaction_id
                self.inbox.mark_processed(inbox_event)
                return None
            self._restart_submitted(conversation)
        interaction = self.repository.active_interaction(conversation)
        inbound.interaction_id = interaction.id
        if (
            isinstance(incoming, ButtonReply)
            and origin
            and (
                origin.conversation_id != conversation.id
                or (origin.interaction_id and origin.interaction_id != interaction.id)
            )
        ):
            if origin.conversation_id == conversation.id:
                inbound.interaction_id = origin.interaction_id
            self.inbox.mark_processed(inbox_event)
            return None

        nl_enabled = self.assistant.enabled and AssistantPreferenceService(
            self.session
        ).requested_for_tenant(ACTIVE_TENANT_ID)
        decision = None
        if isinstance(incoming, FlowReply):
            allowed = {
                "event_type",
                "contact_name",
                "event_date",
                "location",
                "guest_count",
                "service_type",
            }
            form_data = {
                key: str(value).strip()[:120]
                for key, value in incoming.data.items()
                if key in allowed and value is not None and str(value).strip()
            }
            if form_data.get("guest_count", "").isdigit() and form_data.get("event_date"):
                conversation.flow_data = {
                    **(conversation.flow_data or {}),
                    **form_data,
                    "_invalid_attempts": 0,
                }
                decision = decide(
                    "service_type",
                    ButtonReply("service_parrilla"),
                    flow_data=conversation.flow_data,
                )
            else:
                # Never pass an unvalidated Flow payload to the natural
                # language extractor; ask for the missing form fields instead.
                decision = decide(
                    conversation.flow_step,
                    IncomingText(""),
                    flow_data=conversation.flow_data,
                )
        if nl_enabled:
            decision = decision or natural_language_decision(
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
        if decision.handoff:
            self._handoff(event.event_key, conversation, interaction, advisor)
            self.inbox.mark_processed(inbox_event)
            return None
        conversation.flow_step = decision.step
        if decision.reset:
            conversation.flow_data = {"request_reference": interaction.reference}
        else:
            conversation.flow_data = {**(conversation.flow_data or {}), **dict(decision.updates)}
        interaction.snapshot = dict(conversation.flow_data)
        if decision.step == "submitted":
            interaction.status = "submitted"
            interaction.closed_at = datetime.now(UTC)
            enqueue_confirmation_notifications(
                self.repository,
                conversation_id=conversation.id,
                interaction_id=interaction.id,
                event_key=event.event_key,
                snapshot=dict(conversation.flow_data or {}),
                reference=interaction.reference,
                whatsapp_numbers=self.notification_whatsapp_numbers,
                email_recipients=self.notification_email_recipients,
            )
        text = decision.text
        if text == GREETING and decision.buttons == MENU_BUTTONS:
            text += f"\n\nCódigo de interacción: *{interaction.reference}*"
        action = OutboundAction(
            event_key=event.event_key,
            recipient=recipient,
            text=text,
            buttons=decision.buttons,
            flow_id=(self.quote_flow_id if decision.step == "event_type" else None),
        )
        outbound = self.repository.add_outbound(
            conversation_id=conversation.id,
            event_key=event.event_key,
            interaction_id=interaction.id,
            content=json.dumps(
                {
                    "text": action.text,
                    "buttons": action.buttons,
                    "flow_id": action.flow_id,
                    "channel": action.channel,
                    "subject": action.subject,
                    "handoff_notice": decision.handoff,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        self.inbox.mark_processed(inbox_event)
        return outbound.id, action

    def _handoff(self, event_key, conversation, interaction, advisor) -> None:
        self.repository.cancel_pending(interaction.id)
        interaction.snapshot = dict(conversation.flow_data or {})
        interaction.status = "referred"
        interaction.closed_at = datetime.now(UTC)
        self.session.flush()
        details = interaction.snapshot.get("_nl_draft") or interaction.snapshot

        def detail_value(key: str) -> object:
            if key == "contact_name":
                return interaction.snapshot.get("contact_name") or interaction.snapshot.get(
                    "_nl_contact_name"
                )
            return details.get(key)

        summary = "; ".join(
            f"{label}: {detail_value(key) or 'Pendiente'}"
            for key, label in [
                ("contact_name", "Contacto"),
                ("event_date", "Fecha"),
                ("guest_count", "Personas"),
                ("location", "Lugar"),
                ("service_type", "Servicio"),
            ]
        )[:800]
        messages = [
            " ".join(value.split())[:200]
            for value in self.repository.recent_customer_texts(interaction.id)
            if value.strip().casefold() != "asesor" and not value.startswith('{"id":')
        ]
        if messages:
            summary = (
                summary[:350] + "; Mensajes recientes: " + " / ".join(reversed(messages[:2]))
            )[:800]
        reason = None
        if not advisor.enabled:
            reason = "not_configured"
        elif advisor.phone.lstrip("+") == conversation.whatsapp_number:
            reason = "same_recipient"
        notification = self.repository.add_outbound(
            conversation_id=conversation.id,
            interaction_id=interaction.id,
            event_key=child_event_key(event_key, "advisor"),
            purpose="advisor_notification",
            recipient=advisor.phone.lstrip("+") if advisor.phone else None,
            delivery_status="failed" if reason else "pending",
            content=json.dumps(
                {
                    "text": "",
                    "buttons": [],
                    "failure_reason": reason,
                    "template_name": advisor.template,
                    "template_language": advisor.language,
                    "template_parameters": [
                        interaction.reference,
                        "+" + conversation.whatsapp_number,
                        summary,
                    ],
                },
                ensure_ascii=False,
            ),
        )
        acknowledgement = self.repository.add_outbound(
            conversation_id=conversation.id,
            interaction_id=interaction.id,
            event_key=child_event_key(event_key, "ack"),
            depends_on_id=notification.id,
            content=json.dumps(
                {
                    "text": (
                        "Enviamos tu consulta al asesor. Te responderá desde su propio WhatsApp "
                        "tan pronto esté disponible.\n"
                        f"Código de consulta: *{interaction.reference}*"
                    ),
                    "buttons": [],
                    "advisor_ack": True,
                    "fallback_text": (
                        f"Tu consulta quedó registrada con el código {interaction.reference}, "
                        "pero no pudimos confirmar el aviso al asesor en este momento. "
                        "Conservamos los datos para su revisión."
                    ),
                },
                ensure_ascii=False,
            ),
        )
        conversation.flow_data = {}
        conversation.flow_step = "menu"
        conversation.bot_paused = False
        following = self.repository.active_interaction(conversation)
        following.snapshot = dict(conversation.flow_data)
        self.repository.add_outbound(
            conversation_id=conversation.id,
            interaction_id=following.id,
            event_key=child_event_key(event_key, "welcome"),
            depends_on_id=acknowledgement.id,
            content=json.dumps(
                {
                    "text": GREETING + f"\n\nCódigo de interacción: *{following.reference}*",
                    "buttons": MENU_BUTTONS,
                },
                ensure_ascii=False,
            ),
        )

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
            elif verified and row.kind == "status":
                self._prepare_locked(InboxEvent(row.event_key, row.kind, row.payload))
            else:
                self.inbox.mark_processed(row)
            return True

    def deliver_next(self, *, not_before: datetime, event_prefix: str | None = None) -> bool:
        with self.session.begin():
            if not self.inbox.lock_worker():
                return False
            self.repository.recover_advisor_attempts(datetime.now(UTC) - timedelta(seconds=60))
            selected = self.repository.next_outbound(not_before, event_prefix)
            if selected is None:
                return False
            message, conversation = selected
            payload = json.loads(message.content)
            if conversation.bot_paused and not payload.get("handoff_notice", False):
                message.delivery_status = "cancelled"
                return True
            # Persist BEFORE calling Meta. Crashed/ambiguous attempts remain
            # sending/uncertain and are never automatically sent a second time.
            if payload.get("advisor_ack"):
                parent = self.repository.get_message(message.depends_on_id)
                if parent.delivery_status not in {"sent", "delivered", "read"}:
                    payload["text"] = payload["fallback_text"]
                    message.content = json.dumps(payload, ensure_ascii=False)
            message.delivery_status = "sending"
            message.attempted_at = datetime.now(UTC)
            message_id = message.id
            action = OutboundAction(
                event_key=message.event_key,
                recipient=message.recipient or conversation.whatsapp_number,
                text=payload["text"],
                buttons=tuple(tuple(button) for button in payload["buttons"]),
                purpose=message.purpose,
                template_name=payload.get("template_name"),
                template_language=payload.get("template_language"),
                template_parameters=tuple(payload.get("template_parameters", [])),
                flow_id=payload.get("flow_id"),
                channel=payload.get("channel", "whatsapp"),
                subject=payload.get("subject"),
            )
        self._deliver(message_id, action, uncertain_on_failure=True)
        return True

    def _deliver(
        self, message_id: UUID, action: OutboundAction, *, uncertain_on_failure: bool = False
    ) -> None:
        try:
            external_id = self.sender(action)
        except Exception as error:
            with self.session.begin():
                if action.purpose in {"advisor_notification", "confirmation_notification"}:
                    row = self.repository.get_message(message_id)
                    row.delivery_status = (
                        "failed"
                        if getattr(error, "category", None) in {"access_denied", "rate_limited"}
                        else "uncertain"
                    )
                    row.content = json.dumps(
                        {**json.loads(row.content), "failure_reason": "send_failed"},
                        ensure_ascii=False,
                    )
                elif uncertain_on_failure:
                    self.repository.mark_uncertain(message_id)
                else:
                    self.repository.mark_failed(message_id)
            return
        with self.session.begin():
            self.repository.mark_sent(message_id, external_id)

    @staticmethod
    def _incoming(message: dict) -> IncomingText | ButtonReply | FlowReply:
        if message.get("type") == "interactive":
            interactive = message.get("interactive")
            nfm_reply = interactive.get("nfm_reply") if isinstance(interactive, dict) else None
            if isinstance(nfm_reply, dict):
                raw = nfm_reply.get("response_json")
                if isinstance(raw, str):
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = None
                    if isinstance(data, dict):
                        return FlowReply(data=data)
            reply = interactive.get("button_reply") if isinstance(interactive, dict) else None
            if isinstance(reply, dict) and isinstance(reply.get("id"), str):
                return ButtonReply(id=reply["id"], title=reply.get("title"))
        text = message.get("text")
        body = text.get("body") if isinstance(text, dict) else None
        return IncomingText(body=body if isinstance(body, str) else "")

    @staticmethod
    def _content(message: dict, incoming: IncomingText | ButtonReply | FlowReply) -> str:
        if isinstance(incoming, IncomingText):
            return incoming.body
        if isinstance(incoming, FlowReply):
            return json.dumps({"flow_reply": dict(incoming.data)}, ensure_ascii=False)
        return json.dumps(
            {"id": incoming.id, "title": incoming.title},
            ensure_ascii=False,
            separators=(",", ":"),
        )
