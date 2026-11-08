"""Read-only Meta diagnostics. Credentials travel only in the Authorization header."""

from dataclasses import dataclass
from typing import Literal

import httpx


@dataclass(frozen=True)
class PhoneLookup:
    outcome: Literal["ok", "access_denied", "rate_limited", "unavailable", "invalid_response"]
    phone_found: bool | None = None


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
