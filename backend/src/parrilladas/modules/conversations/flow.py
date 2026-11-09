"""Pure decisions for the Beta 1.00 guided WhatsApp quote flow."""

from collections.abc import Mapping
from types import MappingProxyType

from .contracts import ButtonReply, FlowDecision, IncomingText

GREETING = (
    "¡Hola! Gracias por contactar a *Parrilladas en su Casa* 🔥\n\n"
    "Soy Daniel Navarrete y junto a mi equipo estamos listos para llevar una excelente "
    "experiencia de parrilla a tu casa o evento.\n\n"
    "¿Qué te gustaría hacer hoy?"
)
SERVICES_PLACEHOLDER = "Esta opción estará disponible próximamente."
ADVISOR_PLACEHOLDER = "Un asesor podrá ayudarte próximamente. Escribe ASESOR si necesitas atención."
SUBMITTED = (
    "Gracias. Recibimos tu solicitud. Nuestro equipo revisará la información "
    "y se comunicará contigo por este mismo número."
)

MENU_BUTTONS = (
    ("request_quote", "Solicitar cotización"),
    ("view_services", "Ver servicios"),
    ("talk_to_agent", "Hablar con un asesor"),
)
SERVICE_BUTTONS = (("service_parrilla", "Parrilla"),)
INVALID_ATTEMPTS_KEY = "_invalid_attempts"

_PROMPTS = {
    "event_type": "¿Qué tipo de evento estás organizando?",
    "event_date": "¿Para qué fecha necesitas el servicio?",
    "location": "¿En qué lugar se realizará el evento?",
    "guest_count": "¿Para cuántas personas?",
    "service_type": "¿Qué servicio te interesa?",
}

_INVALID_PROMPTS = {
    "event_type": "Indícanos qué tipo de evento estás organizando, por favor.",
    "event_date": "Indícanos la fecha del evento, por favor.",
    "location": "Indícanos el lugar del evento, por favor.",
    "guest_count": "Indícanos la cantidad aproximada de personas, por favor.",
    "service_type": "Indícanos qué servicio te interesa, por favor.",
}


def _decision(
    step: str,
    text: str,
    *,
    buttons: tuple[tuple[str, str], ...] = (),
    handoff: bool = False,
    updates: dict[str, object] | None = None,
    reset: bool = False,
) -> FlowDecision:
    return FlowDecision(
        step=step,
        text=text,
        buttons=buttons,
        handoff=handoff,
        updates=MappingProxyType(dict(updates or {})),
        reset=reset,
    )


def decide(
    step: str,
    incoming: IncomingText | ButtonReply,
    *,
    flow_data: Mapping[str, object] | None = None,
) -> FlowDecision:
    """Return the next pure flow decision for one normalized customer input."""
    flow_data = flow_data or {}

    def invalid() -> FlowDecision:
        attempts = int(flow_data.get(INVALID_ATTEMPTS_KEY, 0)) + 1
        if attempts >= 3:
            return _decision("menu", GREETING, buttons=MENU_BUTTONS, reset=True)
        text = _INVALID_PROMPTS.get(step, "No reconocí esa opción. Por favor, intenta nuevamente.")
        return _decision(
            step,
            text,
            buttons=SERVICE_BUTTONS if step == "service_type" else (),
            updates={INVALID_ATTEMPTS_KEY: attempts},
        )

    if isinstance(incoming, IncomingText):
        body = incoming.body.strip()
        if body.casefold() == "asesor":
            return _decision(
                step,
                ADVISOR_PLACEHOLDER,
                handoff=True,
                updates={INVALID_ATTEMPTS_KEY: 0},
            )

    if step == "start" and isinstance(incoming, IncomingText):
        return _decision("menu", GREETING, buttons=MENU_BUTTONS, updates={INVALID_ATTEMPTS_KEY: 0})

    if step == "menu" and isinstance(incoming, ButtonReply):
        button_id = incoming.id.strip().casefold()
        if button_id in {"request_quote", "quote"}:
            return _decision(
                "event_type", _PROMPTS["event_type"], updates={INVALID_ATTEMPTS_KEY: 0}
            )
        if button_id in {"view_services", "services"}:
            return _decision(
                "menu",
                SERVICES_PLACEHOLDER,
                buttons=MENU_BUTTONS,
                updates={INVALID_ATTEMPTS_KEY: 0},
            )
        if button_id in {"talk_to_agent", "advisor"}:
            return _decision(
                "menu", ADVISOR_PLACEHOLDER, handoff=True, updates={INVALID_ATTEMPTS_KEY: 0}
            )

    transitions = {
        "event_type": ("event_date", "event_type"),
        "event_date": ("location", "event_date"),
        "location": ("guest_count", "location"),
        "guest_count": ("service_type", "guest_count"),
        "service_type": ("summary", "service_type"),
    }
    if step in transitions and isinstance(incoming, IncomingText):
        body = incoming.body.strip()
        valid = bool(body)
        if step == "guest_count":
            valid = body.isdigit()
        if step == "service_type":
            valid = False
        if valid:
            next_step, field = transitions[step]
            return _decision(
                next_step,
                _PROMPTS.get(next_step, ""),
                buttons=SERVICE_BUTTONS if next_step == "service_type" else (),
                updates={field: body, INVALID_ATTEMPTS_KEY: 0},
            )
        return invalid()

    if step == "service_type" and isinstance(incoming, ButtonReply):
        if incoming.id.strip().casefold() == "service_parrilla":
            return _decision(
                "summary",
                _PROMPTS.get("summary", ""),
                updates={"service_type": "parrilla", INVALID_ATTEMPTS_KEY: 0},
            )
        return invalid()

    if step == "summary" and isinstance(incoming, ButtonReply):
        button_id = incoming.id.strip().casefold()
        if button_id == "confirm":
            return _decision("submitted", SUBMITTED, updates={INVALID_ATTEMPTS_KEY: 0})
        if button_id == "advisor":
            return _decision(
                "summary", ADVISOR_PLACEHOLDER, handoff=True, updates={INVALID_ATTEMPTS_KEY: 0}
            )

    if step in _INVALID_PROMPTS:
        return invalid()
    return invalid()
