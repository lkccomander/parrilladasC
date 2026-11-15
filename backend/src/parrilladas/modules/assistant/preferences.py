from datetime import UTC, datetime

from sqlalchemy.orm import Session

from parrilladas.modules.accounts.contracts import Role
from parrilladas.modules.accounts.errors import AccessDenied
from parrilladas.modules.accounts.schemas import AccountView

from .repository import AssistantPreferenceRepository
from .schemas import AssistantPreferencesUpdate, AssistantPreferencesView

# Only this business has dashboard accounts. A future tenant resolver must also
# authorize account membership before exposing preferences for another tenant.
ACTIVE_TENANT_ID = "parrilladas"


class AssistantPreferenceService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = AssistantPreferenceRepository(session)

    @staticmethod
    def _require_admin(actor: AccountView) -> None:
        if not actor.is_active or actor.role != Role.ADMIN:
            raise AccessDenied("Se requiere una cuenta Admin activa.")

    @staticmethod
    def _view(row) -> AssistantPreferencesView:
        return AssistantPreferencesView(
            tenant_id=ACTIVE_TENANT_ID,
            natural_language_enabled=row.natural_language_enabled if row else False,
            updated_at=row.updated_at if row else None,
            updated_by=row.updated_by if row else None,
        )

    def get(self, actor: AccountView) -> AssistantPreferencesView:
        self._require_admin(actor)
        with self.session.begin():
            return self._view(self.repository.get(ACTIVE_TENANT_ID))

    def update(
        self, actor: AccountView, data: AssistantPreferencesUpdate
    ) -> AssistantPreferencesView:
        self._require_admin(actor)
        with self.session.begin():
            row = self.repository.save(
                ACTIVE_TENANT_ID,
                enabled=data.natural_language_enabled,
                actor_id=actor.id,
                updated_at=datetime.now(UTC),
            )
            return self._view(row)
