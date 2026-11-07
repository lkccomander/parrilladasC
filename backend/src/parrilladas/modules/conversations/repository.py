from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from parrilladas.modules.conversations.contracts import InboxEvent
from parrilladas.modules.conversations.models import WhatsAppInboxEvent


class InboxRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, event: InboxEvent) -> None:
        self.session.execute(
            insert(WhatsAppInboxEvent)
            .values(event_key=event.event_key, kind=event.kind, payload=event.payload)
            .on_conflict_do_nothing(index_elements=[WhatsAppInboxEvent.event_key])
        )
