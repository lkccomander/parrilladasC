from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from parrilladas.db.session import get_session
from parrilladas.modules.accounts.dependencies import Admin, Csrf

from .preferences import AssistantPreferenceService
from .schemas import (
    AdvisorPreferencesView,
    AdvisorSettings,
    AssistantPreferencesUpdate,
    AssistantPreferencesView,
)

router = APIRouter(prefix="/assistant/preferences", tags=["assistant"])


def preference_service(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AssistantPreferenceService:
    return AssistantPreferenceService(
        session, runtime_available=request.app.state.assistant.enabled
    )


Service = Annotated[AssistantPreferenceService, Depends(preference_service)]


@router.get("", response_model=AssistantPreferencesView)
def preferences(context: Admin, service: Service) -> AssistantPreferencesView:
    return service.get(context.account)


@router.patch("", response_model=AssistantPreferencesView)
def update_preferences(
    data: AssistantPreferencesUpdate, context: Admin, csrf: Csrf, service: Service
) -> AssistantPreferencesView:
    return service.update(context.account, data)


@router.get("/advisor", response_model=AdvisorPreferencesView)
def advisor_preferences(context: Admin, service: Service) -> AdvisorPreferencesView:
    return service.get_advisor(context.account)


@router.patch("/advisor", response_model=AdvisorPreferencesView)
def update_advisor_preferences(
    data: AdvisorSettings, context: Admin, csrf: Csrf, service: Service
) -> AdvisorPreferencesView:
    return service.update_advisor(context.account, data)
