import json
from uuid import uuid4

from parrilladas.modules.notifications.service import (
    enqueue_confirmation_notifications,
    parse_recipients,
)


class FakeRepository:
    def __init__(self):
        self.rows = []

    def add_outbound(self, **kwargs):
        self.rows.append(kwargs)
        return type("Message", (), {"id": uuid4()})()


def test_parse_recipients_trims_and_deduplicates():
    assert parse_recipients(" +5061, +5061,info@example.com ") == (
        "+5061",
        "info@example.com",
    )


def test_confirmation_notifications_create_whatsapp_and_email_rows():
    repository = FakeRepository()
    enqueue_confirmation_notifications(
        repository,
        conversation_id=uuid4(),
        interaction_id=uuid4(),
        event_key="incoming-1",
        snapshot={"event_date": "2026-12-20", "guest_count": "20", "location": "Alajuela"},
        reference="PEC-ABC123",
        whatsapp_numbers=("+50687200700", "+50683383928"),
        email_recipients=("info@parrillasensucasa.com",),
    )
    assert [row["purpose"] for row in repository.rows] == [
        "confirmation_notification",
        "confirmation_notification",
        "confirmation_notification",
    ]
    assert repository.rows[0]["recipient"] == "50687200700"
    assert json.loads(repository.rows[1]["content"])["channel"] == "whatsapp"
    email = json.loads(repository.rows[2]["content"])
    assert email["channel"] == "email"
    assert email["subject"].endswith("PEC-ABC123")
