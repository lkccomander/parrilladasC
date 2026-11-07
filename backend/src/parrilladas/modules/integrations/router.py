from typing import Annotated

from fastapi import APIRouter, Depends, Request

from parrilladas.integrations.whatsapp.client import MetaClient
from parrilladas.modules.accounts.dependencies import Admin, Csrf
from parrilladas.modules.integrations.schemas import WhatsAppIntegrationStatus
from parrilladas.modules.integrations.service import IntegrationService

router = APIRouter(prefix="/integrations/whatsapp", tags=["integrations"])


def integration_service(request: Request) -> IntegrationService:
    return IntegrationService(request.app.state.settings, MetaClient(request.app.state.meta_http))


Service = Annotated[IntegrationService, Depends(integration_service)]


@router.get("", response_model=WhatsAppIntegrationStatus)
def integration_status(context: Admin, service: Service) -> WhatsAppIntegrationStatus:
    return service.status()


@router.post("/check", response_model=WhatsAppIntegrationStatus)
def check_connection(context: Admin, csrf: Csrf, service: Service) -> WhatsAppIntegrationStatus:
    return service.check()
