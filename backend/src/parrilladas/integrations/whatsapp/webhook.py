"""Meta transport authentication and payload translation; no sales rules."""

import hashlib
import hmac
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from parrilladas.modules.conversations.contracts import InboxEvent

Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=255)]
Timestamp = Annotated[str, Field(strict=True, pattern=r"^[0-9]{1,20}$")]


class InvalidWebhook(ValueError):
    pass


class UnexpectedWebhookAccount(ValueError):
    pass


def valid_signature(body: bytes, signature: str, secret: str) -> bool:
    if not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class Change(BaseModel):
    field: Identifier
    value: dict


class Entry(BaseModel):
    id: Identifier
    changes: list[Change] = Field(min_length=1)


class Envelope(BaseModel):
    object: Literal["whatsapp_business_account"]
    entry: list[Entry] = Field(min_length=1)


class ProviderMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Identifier
    sender: Annotated[str, Field(alias="from", strict=True, pattern=r"^[0-9]{1,32}$")]
    timestamp: Timestamp
    type: Identifier


class ProviderStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Identifier
    status: Annotated[str, Field(strict=True, min_length=1, max_length=32)]
    timestamp: Timestamp


class Metadata(BaseModel):
    phone_number_id: Identifier


class MessageValue(BaseModel):
    messaging_product: Literal["whatsapp"]
    metadata: Metadata
    messages: list[ProviderMessage] = Field(default_factory=list)
    statuses: list[ProviderStatus] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


def event_key(parts: list) -> str:
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def parse_events(body: bytes, business_account_id: str, phone_number_id: str) -> list[InboxEvent]:
    try:
        envelope = Envelope.model_validate_json(body)
        events = []
        for entry in envelope.entry:
            if entry.id != business_account_id:
                raise UnexpectedWebhookAccount
            for change in entry.changes:
                if change.field != "messages":
                    continue
                events.extend(message_events(change.value, business_account_id, phone_number_id))
        return events
    except (ValueError, RecursionError) as error:
        if isinstance(error, UnexpectedWebhookAccount):
            raise
        # Do not propagate Pydantic errors containing customer inputs to HTTP/logs.
        raise InvalidWebhook("Invalid WhatsApp payload") from None


def message_events(value: dict, business_account_id: str, phone_number_id: str) -> list[InboxEvent]:
    parsed = MessageValue.model_validate(value)
    if parsed.metadata.phone_number_id != phone_number_id:
        raise UnexpectedWebhookAccount
    scope = [business_account_id, phone_number_id]
    common = {key: data for key, data in value.items() if key not in {"messages", "statuses"}}
    events = []
    for message in parsed.messages:
        events.append(
            InboxEvent(
                event_key=event_key([*scope, "message", message.id]),
                kind="message",
                payload={
                    "business_account_id": business_account_id,
                    "value": {**common, "messages": [message.model_dump(by_alias=True)]},
                },
            )
        )
    for status in parsed.statuses:
        events.append(
            InboxEvent(
                event_key=event_key([*scope, "status", status.id, status.status, status.timestamp]),
                kind="status",
                payload={
                    "business_account_id": business_account_id,
                    "value": {**common, "statuses": [status.model_dump()]},
                },
            )
        )
    if parsed.errors:
        events.append(
            InboxEvent(
                event_key=event_key([*scope, "notification", common]),
                kind="notification",
                payload={"business_account_id": business_account_id, "value": common},
            )
        )
    return events
