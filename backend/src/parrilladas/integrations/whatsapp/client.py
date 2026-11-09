"""Read-only Meta diagnostics. Credentials travel only in the Authorization header."""

from dataclasses import dataclass
from typing import Any, Literal

import httpx


@dataclass(frozen=True)
class PhoneLookup:
    outcome: Literal["ok", "access_denied", "rate_limited", "unavailable", "invalid_response"]
    phone_found: bool | None = None


class MetaSendError(RuntimeError):
    """Safe provider error that never includes Meta response data."""

    def __init__(
        self, category: Literal["access_denied", "rate_limited", "unavailable", "invalid_response"]
    ):
        self.category = category
        super().__init__(f"Meta message send failed: {category}")


class MetaClient:
    def __init__(self, http: httpx.Client):
        self.http = http

    def lookup_phone(
        self, version: str, _account_id: str, phone_id: str, token: str
    ) -> PhoneLookup:
        try:
            response = self.http.get(
                f"https://graph.facebook.com/{version}/{phone_id}",
                params={"fields": "id,display_phone_number"},
                headers={"Authorization": f"Bearer {token}"},
                follow_redirects=False,
                timeout=httpx.Timeout(3.0, connect=1.0),
            )
        except httpx.HTTPError:
            return PhoneLookup("unavailable")
        if response.status_code in {401, 403}:
            return PhoneLookup("access_denied")
        if response.status_code == 429:
            return PhoneLookup("rate_limited")
        if response.status_code >= 500:
            return PhoneLookup("unavailable")
        if 300 <= response.status_code < 400:
            return PhoneLookup("invalid_response")
        try:
            data = response.json()
        except ValueError:
            return PhoneLookup("invalid_response")
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            code = data["error"].get("code")
            if code in (10, 190, 200):
                return PhoneLookup("access_denied")
            if code in (4, 17, 32, 613):
                return PhoneLookup("rate_limited")
            return PhoneLookup("invalid_response")
        if response.status_code != 200:
            return PhoneLookup("invalid_response")
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            return PhoneLookup("invalid_response")
        if data["id"] == phone_id:
            return PhoneLookup("ok", True)
        return PhoneLookup("ok", False)

    def send_text(
        self, *, version: str, phone_id: str, token: str, recipient: str, body: str
    ) -> str:
        return self._send(
            version=version,
            phone_id=phone_id,
            token=token,
            payload={
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": body},
            },
        )

    def send_image(
        self,
        *,
        version: str,
        phone_id: str,
        token: str,
        recipient: str,
        image_url: str,
        caption: str,
    ) -> str:
        return self._send(
            version=version,
            phone_id=phone_id,
            token=token,
            payload={
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "image",
                "image": {"link": image_url, "caption": caption},
            },
        )

    def send_buttons(
        self,
        *,
        version: str,
        phone_id: str,
        token: str,
        recipient: str,
        body: str,
        buttons: list[tuple[str, str]],
        header_image_url: str | None = None,
    ) -> str:
        interactive: dict[str, Any] = {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": button_id, "title": title}}
                    for button_id, title in buttons
                ]
            },
        }
        if header_image_url:
            interactive["header"] = {
                "type": "image",
                "image": {"link": header_image_url},
            }
        return self._send(
            version=version,
            phone_id=phone_id,
            token=token,
            payload={
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "interactive",
                "interactive": interactive,
            },
        )

    def _send(self, *, version: str, phone_id: str, token: str, payload: dict[str, Any]) -> str:
        try:
            response = self.http.post(
                f"https://graph.facebook.com/{version}/{phone_id}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                follow_redirects=False,
                timeout=httpx.Timeout(5.0, connect=1.0),
            )
        except httpx.HTTPError as error:
            raise MetaSendError("unavailable") from error
        if response.status_code in {401, 403}:
            raise MetaSendError("access_denied")
        if response.status_code == 429:
            raise MetaSendError("rate_limited")
        if response.status_code >= 500:
            raise MetaSendError("unavailable")
        if response.status_code < 200 or response.status_code >= 300:
            raise MetaSendError("invalid_response")
        try:
            data = response.json()
        except ValueError as error:
            raise MetaSendError("invalid_response") from error
        if not isinstance(data, dict):
            raise MetaSendError("invalid_response")
        messages = data.get("messages")
        if not isinstance(messages, list) or not messages or not isinstance(messages[0], dict):
            raise MetaSendError("invalid_response")
        message_id = messages[0].get("id")
        if not isinstance(message_id, str) or not message_id:
            raise MetaSendError("invalid_response")
        return message_id
