"""Pure decisions for the Beta 1.00 guided WhatsApp quote flow."""

from types import MappingProxyType

from .contracts import ButtonReply, FlowDecision, IncomingText

GREETING = "¡Hola! Gracias por contactar a Parrilladas en su Casa 🔥"
SERVICES_PLACEHOLDER = "Esta opción estará disponible próximamente."
ADVISOR_PLACEHOLDER = "Un asesor podrá ayudarte próximamente. Escribe ASESOR si necesitas atención."
SUBMITTED = (
    "Gracias. Recibimos tu solicitud. Nuestro equipo revisará la información "
    "y se comunicará contigo por este mismo número."
)

MENU_BUTTONS = (
    ("quote", "Solicitar cotización"),
    ("services", "Ver servicios"),
    ("advisor", "Hablar con un asesor"),
)

_PROMPTS = {
    "event_type": "¿Qué tipo de evento estás organizando?",
    "event_date": "¿Para qué fecha necesitas el servicio?",
    "location": "¿En qué lugar se realizará el evento?",
    "guest_count": "¿Para cuántas personas?",
    "service_type": (
        "¿Qué servicio te interesa? Puedes indicar parrillada, buffet, estaciones "
        "o menú personalizado."
    ),
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
    updates: dict[str, str] | None = None,
) -> FlowDecision:
    return FlowDecision(
        step=step,
        text=text,
        buttons=buttons,
        handoff=handoff,
        updates=MappingProxyType(dict(updates or {})),
    )


def decide(step: str, incoming: IncomingText | ButtonReply) -> FlowDecision:
    """Return the next pure flow decision for one normalized customer input."""
    if isinstance(incoming, IncomingText):
        body = incoming.body.strip()
        if body.casefold() == "asesor":
            return _decision(step, ADVISOR_PLACEHOLDER, handoff=True)

    if step == "start" and isinstance(incoming, IncomingText):
        return _decision("menu", GREETING, buttons=MENU_BUTTONS)

    if step == "menu" and isinstance(incoming, ButtonReply):
        button_id = incoming.id.strip().casefold()
        if button_id == "quote":
            return _decision("event_type", _PROMPTS["event_type"])
        if button_id == "services":
            return _decision("menu", SERVICES_PLACEHOLDER, buttons=MENU_BUTTONS)
        if button_id == "advisor":
            return _decision("menu", ADVISOR_PLACEHOLDER, handoff=True)

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
        if valid:
            next_step, field = transitions[step]
            return _decision(next_step, _PROMPTS.get(next_step, ""), updates={field: body})
        return _decision(step, _INVALID_PROMPTS[step])

    if step == "summary" and isinstance(incoming, ButtonReply):
        button_id = incoming.id.strip().casefold()
        if button_id == "confirm":
            return _decision("submitted", SUBMITTED)
        if button_id == "advisor":
            return _decision("summary", ADVISOR_PLACEHOLDER, handoff=True)

    if step in _INVALID_PROMPTS:
        return _decision(step, _INVALID_PROMPTS[step])
    return _decision(step, "No reconocí esa opción. Por favor, intenta nuevamente.")
