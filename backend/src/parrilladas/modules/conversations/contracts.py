from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class InboxEvent:
    event_key: str
    kind: Literal["message", "status", "notification"]
    payload: dict
