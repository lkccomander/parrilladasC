import re

from sqlalchemy.orm import Session

from parrilladas.modules.accounts.contracts import Role
from parrilladas.modules.accounts.errors import AccessDenied
from parrilladas.modules.accounts.schemas import AccountView
from parrilladas.modules.conversations.repository import ConversationRepository
from parrilladas.modules.conversations.schemas import (
    InteractionFilters,
    InteractionPage,
    InteractionView,
)

PAGE_SIZE = 25


def display_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip()[:300] or None


class InteractionQueryService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = ConversationRepository(session)

    def list_interactions(self, actor: AccountView, filters: InteractionFilters) -> InteractionPage:
        if not actor.is_active or not (actor.is_admin or Role.SALES in actor.roles):
            raise AccessDenied("Se requiere acceso de Admin o Sales.")
        search = filters.q.strip()
        if search and re.fullmatch(r"[+\d\s()-]+", search):
            search = re.sub(r"\D", "", search)
        with self.session.begin():
            rows, total = self.repository.list_interactions(
                search=search,
                status=filters.status,
                offset=(filters.page - 1) * PAGE_SIZE,
                limit=PAGE_SIZE,
            )
            items = []
            for interaction, conversation in rows:
                # Show the current draft without changing any confirmed snapshot.
                snapshot = interaction.snapshot or {}
                draft = snapshot.get("_nl_draft")
                details = {**(draft if isinstance(draft, dict) else {}), **snapshot}
                guests = details.get("guest_count")
                if (
                    isinstance(guests, str)
                    and guests.isascii()
                    and guests.isdecimal()
                    and len(guests) <= 9
                ):
                    guests = int(guests)
                if type(guests) is not int or guests < 1:
                    guests = None
                items.append(
                    InteractionView(
                        id=interaction.id,
                        reference=interaction.reference,
                        status=interaction.status,
                        whatsapp_number=conversation.whatsapp_number,
                        bot_paused=conversation.bot_paused
                        if interaction.status == "active"
                        else False,
                        created_at=interaction.created_at,
                        closed_at=interaction.closed_at,
                        contact_name=display_text(
                            details.get("contact_name") or details.get("_nl_contact_name")
                        ),
                        event_date=display_text(details.get("event_date")),
                        guest_count=guests,
                        location=display_text(details.get("location")),
                        service_type=display_text(details.get("service_type")),
                    )
                )
        return InteractionPage(items=items, total=total, page=filters.page, page_size=PAGE_SIZE)
