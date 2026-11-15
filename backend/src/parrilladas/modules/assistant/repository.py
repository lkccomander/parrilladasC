from datetime import datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import AssistantPreference


class AssistantPreferenceRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, tenant_id: str) -> AssistantPreference | None:
        return self.session.get(AssistantPreference, tenant_id)

    def save(
        self, tenant_id: str, *, enabled: bool, actor_id: UUID, updated_at: datetime
    ) -> AssistantPreference:
        values = {
            "natural_language_enabled": enabled,
            "updated_at": updated_at,
            "updated_by": actor_id,
        }
        statement = (
            insert(AssistantPreference)
            .values(tenant_id=tenant_id, **values)
            .on_conflict_do_update(index_elements=[AssistantPreference.tenant_id], set_=values)
            .returning(AssistantPreference)
        )
        return self.session.scalars(statement, execution_options={"populate_existing": True}).one()
