"""Read-only operational status exposed through the assistant settings service."""

import json

from sqlalchemy.orm import Session

from parrilladas.modules.assistant.schemas import AdvisorNotificationView

from .repository import ConversationRepository


class HandoffStatusService:
    def __init__(self, session: Session):
        self.session = session

    def recent(self) -> list[AdvisorNotificationView]:
        rows = ConversationRepository(self.session).recent_advisor_notifications()
        return [
            AdvisorNotificationView(
                reference=row.reference,
                status=row.delivery_status,
                reason=json.loads(row.content).get("failure_reason"),
                created_at=row.created_at,
            )
            for row in rows
        ]
