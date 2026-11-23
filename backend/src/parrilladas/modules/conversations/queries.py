import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from parrilladas.modules.accounts.contracts import Role
from parrilladas.modules.accounts.errors import AccessDenied
from parrilladas.modules.accounts.schemas import AccountView
from parrilladas.modules.conversations.models import Interaction
from parrilladas.modules.conversations.repository import ConversationRepository
from parrilladas.modules.conversations.schemas import (
    InteractionDetail,
    InteractionFilters,
    InteractionMessageView,
    InteractionPage,
    InteractionTimeline,
    InteractionTimelinePoint,
    InteractionUpdate,
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

    def interaction_timeline(self, actor: AccountView, days: int) -> InteractionTimeline:
        self._require_operator(actor)
        now = datetime.now(UTC)
        since = now - timedelta(days=days - 1)
        day = func.date(func.timezone("America/Costa_Rica", Interaction.created_at)).label("day")
        with self.session.begin():
            rows = self.session.execute(
                select(day, func.count(Interaction.id))
                .where(Interaction.created_at >= since)
                .group_by(day)
                .order_by(day)
            ).all()
        counts = {row[0]: int(row[1]) for row in rows}
        first_day = (datetime.now(ZoneInfo("America/Costa_Rica")) - timedelta(days=days - 1)).date()
        points = [
            InteractionTimelinePoint(
                day=first_day + timedelta(days=offset),
                count=counts.get(first_day + timedelta(days=offset), 0),
            )
            for offset in range(days)
        ]
        return InteractionTimeline(
            days=days, points=points, total=sum(point.count for point in points)
        )

    def _require_operator(self, actor: AccountView) -> None:
        if not actor.is_active or not (actor.is_admin or Role.SALES in actor.roles):
            raise AccessDenied("Se requiere acceso de Admin o Sales.")

    @staticmethod
    def _details(snapshot: dict | None) -> dict:
        snapshot = snapshot or {}
        draft = snapshot.get("_nl_draft")
        return {**(draft if isinstance(draft, dict) else {}), **snapshot}

    def get_interaction(self, actor: AccountView, interaction_id) -> InteractionDetail | None:
        self._require_operator(actor)
        with self.session.begin():
            row, messages = self.repository.interaction_detail(interaction_id)
            if row is None:
                return None
            interaction, conversation = row
            details = self._details(interaction.snapshot)
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
            return InteractionDetail(
                id=interaction.id,
                reference=interaction.reference,
                status=interaction.status,
                whatsapp_number=conversation.whatsapp_number,
                bot_paused=conversation.bot_paused if interaction.status == "active" else False,
                created_at=interaction.created_at,
                closed_at=interaction.closed_at,
                contact_name=display_text(
                    details.get("contact_name") or details.get("_nl_contact_name")
                ),
                event_date=display_text(details.get("event_date")),
                guest_count=guests,
                location=display_text(details.get("location")),
                service_type=display_text(details.get("service_type")),
                notes=interaction.notes,
                messages=[
                    InteractionMessageView(
                        id=message.id,
                        direction=message.direction,
                        purpose=message.purpose,
                        content=message.content,
                        delivery_status=message.delivery_status,
                        created_at=message.created_at,
                    )
                    for message in messages
                ],
            )

    def update_interaction(
        self, actor: AccountView, interaction_id, data: InteractionUpdate
    ) -> InteractionDetail | None:
        self._require_operator(actor)
        with self.session.begin():
            updated = self.repository.update_interaction(
                interaction_id, status=data.status, notes=data.notes
            )
        if updated is None:
            return None
        return self.get_interaction(actor, interaction_id)
