"""Build durable notifications for confirmed requests.

Notifications use the existing conversation outbox so delivery, retries and
idempotency have one operational path for WhatsApp and email.
"""

import json
from collections.abc import Iterable
from uuid import UUID

from parrilladas.modules.conversations.contracts import child_event_key
from parrilladas.modules.conversations.repository import ConversationRepository

PURPOSE = "confirmation_notification"


def parse_recipients(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    values = value.split(",") if isinstance(value, str) else value
    return tuple(dict.fromkeys(item.strip() for item in values if item and item.strip()))


def _body(snapshot: dict[str, object], reference: str, customer_number: str) -> str:
    labels = (
        ("contact_name", "Contacto"),
        ("event_date", "Fecha"),
        ("guest_count", "Personas"),
        ("location", "Lugar"),
        ("service_type", "Servicio"),
    )
    lines = [
        "✨✨ *-- NOTIFICACIÓN --* ✨✨",
        "*Nueva solicitud confirmada*",
        f"*Código:* {reference}",
        f"📲 *Cliente:* +{customer_number.lstrip('+')}",
    ]
    lines.extend(f"{label}: {snapshot.get(key) or 'Pendiente'}" for key, label in labels)
    return "\n".join(lines)[:4000]


def enqueue_confirmation_notifications(
    repository: ConversationRepository,
    *,
    conversation_id: UUID,
    interaction_id: UUID,
    event_key: str,
    snapshot: dict[str, object],
    reference: str,
    customer_number: str,
    whatsapp_numbers: Iterable[str],
    email_recipients: Iterable[str],
) -> None:
    body = _body(snapshot, reference, customer_number)
    for index, number in enumerate(parse_recipients(whatsapp_numbers)):
        repository.add_outbound(
            conversation_id=conversation_id,
            interaction_id=interaction_id,
            event_key=child_event_key(event_key, f"confirmation-whatsapp-{index}-{number}"),
            purpose=PURPOSE,
            recipient=number.lstrip("+"),
            content=json.dumps(
                {"channel": "whatsapp", "text": body, "buttons": []},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    for index, address in enumerate(parse_recipients(email_recipients)):
        repository.add_outbound(
            conversation_id=conversation_id,
            interaction_id=interaction_id,
            event_key=child_event_key(
                event_key, f"confirmation-email-{index}-{address.casefold()}"
            ),
            purpose=PURPOSE,
            recipient=address,
            content=json.dumps(
                {
                    "channel": "email",
                    "subject": f"Nueva solicitud confirmada · {reference}",
                    "text": body,
                    "buttons": [],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
