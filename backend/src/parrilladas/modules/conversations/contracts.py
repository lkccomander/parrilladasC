from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


@dataclass(frozen=True)
class InboxEvent:
    event_key: str
    kind: Literal["message", "status", "notification"]
    payload: dict


@dataclass(frozen=True)
class IncomingText:
    body: str


@dataclass(frozen=True)
class ButtonReply:
    id: str
    title: str | None = None


@dataclass(frozen=True)
class FlowDecision:
    step: str
    text: str
    buttons: tuple[tuple[str, str], ...] = ()
    handoff: bool = False
    updates: Mapping[str, object] = MappingProxyType({})
    reset: bool = False
