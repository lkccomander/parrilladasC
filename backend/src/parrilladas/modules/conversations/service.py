from sqlalchemy.orm import Session

from parrilladas.modules.conversations.contracts import InboxEvent
from parrilladas.modules.conversations.repository import InboxRepository


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
