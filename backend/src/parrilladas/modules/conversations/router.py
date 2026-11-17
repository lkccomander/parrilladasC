from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from parrilladas.db.session import get_session
from parrilladas.modules.accounts.dependencies import Authenticated
from parrilladas.modules.conversations.queries import InteractionQueryService
from parrilladas.modules.conversations.schemas import InteractionFilters, InteractionPage

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
