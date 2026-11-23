from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from parrilladas.db.session import get_session
from parrilladas.modules.accounts.dependencies import Authenticated, Csrf
from parrilladas.modules.conversations.queries import InteractionQueryService
from parrilladas.modules.conversations.schemas import (
    InteractionDetail,
    InteractionFilters,
    InteractionPage,
    InteractionTimeline,
    InteractionUpdate,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def query_service(session: Annotated[Session, Depends(get_session)]) -> InteractionQueryService:
    return InteractionQueryService(session)


@router.get("/interactions", response_model=InteractionPage)
def list_interactions(
    context: Authenticated,
    service: Annotated[InteractionQueryService, Depends(query_service)],
    filters: Annotated[InteractionFilters, Query()],
    response: Response,
) -> InteractionPage:
    response.headers["Cache-Control"] = "no-store"
    return service.list_interactions(context.account, filters)


@router.get("/interactions/timeline", response_model=InteractionTimeline)
def interaction_timeline(
    context: Authenticated,
    service: Annotated[InteractionQueryService, Depends(query_service)],
    response: Response,
    days: int = Query(default=30, ge=7, le=90),
) -> InteractionTimeline:
    response.headers["Cache-Control"] = "no-store"
    return service.interaction_timeline(context.account, days)


@router.get("/interactions/{interaction_id}", response_model=InteractionDetail)
def interaction_detail(
    interaction_id: UUID,
    context: Authenticated,
    service: Annotated[InteractionQueryService, Depends(query_service)],
) -> InteractionDetail:
    detail = service.get_interaction(context.account, interaction_id)
    if detail is None:
        raise HTTPException(404, "Interacción no encontrada.")
    return detail


@router.patch("/interactions/{interaction_id}", response_model=InteractionDetail)
def update_interaction(
    interaction_id: UUID,
    data: InteractionUpdate,
    context: Authenticated,
    csrf: Csrf,
    service: Annotated[InteractionQueryService, Depends(query_service)],
) -> InteractionDetail:
    detail = service.update_interaction(context.account, interaction_id, data)
    if detail is None:
        raise HTTPException(404, "Interacción no encontrada.")
    return detail
