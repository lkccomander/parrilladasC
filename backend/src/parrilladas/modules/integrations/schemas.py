from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ConnectionResult(BaseModel):
    status: Literal["ok", "error", "unknown", "not_configured"]
    message: str


class ConnectivityCheck(BaseModel):
    checked_at: datetime
    meta: ConnectionResult
    whatsapp: ConnectionResult


class WhatsAppIntegrationStatus(BaseModel):
    webhook_path: Literal["/webhooks/whatsapp"] = "/webhooks/whatsapp"
    webhook_url: str | None
    webhook_enabled: bool
    webhook_verification_enabled: bool = False
    access_token_configured: bool
    graph_api_version: str | None
    business_account_id: str | None
    phone_number_id: str | None
    check: ConnectivityCheck | None = None
