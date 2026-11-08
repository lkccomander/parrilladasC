import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from parrilladas.core.config import ApiSettings
from parrilladas.db.session import get_session
from parrilladas.integrations.whatsapp.webhook import (
    InvalidWebhook,
    UnexpectedWebhookAccount,
    parse_events,
    valid_signature,
)
from parrilladas.modules.conversations.service import InboxService

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])
MAX_BODY_BYTES = 1024 * 1024
logger = logging.getLogger(__name__)


def webhook_settings(request: Request) -> ApiSettings:
    if request.method == "GET":
        # Cache for verification, then omit the secret-bearing query from
        # Uvicorn's access log (which reads scope when the response starts).
        _ = request.query_params
        request.scope["query_string"] = b""
    settings: ApiSettings = request.app.state.settings
    if request.method == "GET" and settings.whatsapp_verify_token is None:
        raise HTTPException(status_code=503, detail="WhatsApp verification is disabled")
    if request.method != "GET" and settings.whatsapp_app_secret is None:
        raise HTTPException(status_code=503, detail="WhatsApp intake is disabled")
    return settings


Settings = Annotated[ApiSettings, Depends(webhook_settings)]


@router.get("", response_class=PlainTextResponse)
def verify_subscription(request: Request, settings: Settings) -> str:
    query = request.query_params
    # Reject duplicate parameters rather than choosing one of several tokens.
    if any(
        len(query.getlist(name)) != 1 for name in ("hub.mode", "hub.verify_token", "hub.challenge")
    ):
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    supplied = query["hub.verify_token"].encode()
    expected = settings.whatsapp_verify_token.get_secret_value().encode()
    if (
        query["hub.mode"] != "subscribe"
        or not hmac.compare_digest(supplied, expected)
        or not query["hub.challenge"]
        or len(query["hub.challenge"]) > 1024
    ):
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    return query["hub.challenge"]


@router.post("")
async def receive_webhook(
    request: Request, settings: Settings, session: Annotated[Session, Depends(get_session)]
) -> dict:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Webhook payload too large")
        body.extend(chunk)
    raw = bytes(body)
    signatures = request.headers.getlist("x-hub-signature-256")
    if len(signatures) != 1 or not valid_signature(
        raw, signatures[0], settings.whatsapp_app_secret.get_secret_value()
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        events = parse_events(
            raw, settings.whatsapp_business_account_id, settings.whatsapp_phone_number_id
        )
    except UnexpectedWebhookAccount as error:
        logger.warning(
            "Rejected WhatsApp webhook account mismatch: kind=%s received=%s expected=%s",
            error.kind,
            error.received,
            error.expected,
        )
        raise HTTPException(status_code=403, detail="Unexpected WhatsApp account") from None
    except InvalidWebhook:
        raise HTTPException(status_code=400, detail="Invalid WhatsApp payload") from None
    if events:
        try:
            await run_in_threadpool(InboxService(session).receive, events)
        except SQLAlchemyError:
            # Meta must retry failures, never receive a success before commit.
            raise HTTPException(status_code=503, detail="Webhook storage unavailable") from None
    return {"status": "ok"}
