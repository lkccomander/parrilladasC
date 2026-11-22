"""Convert validated extraction proposals into explicit customer review steps."""

import unicodedata
from datetime import date

from pydantic import ValidationError

from parrilladas.modules.assistant.date_parsing import (
    parse_relative_event_week,
    resolve_weekday_in_week,
)
from parrilladas.modules.assistant.schemas import EVENT_FIELDS, EventDetails, ExtractionRequest
from parrilladas.modules.assistant.service import AssistantService
from parrilladas.modules.assistant.telemetry import telemetry_trace

from .contracts import ButtonReply, FlowDecision, IncomingText
from .date_answers import MONTHS, parse_date_answer
from .flow import decide

NL_STEPS = {"nl_collect", "nl_review", "nl_changes"}
REVIEW_BUTTONS = (("nl_confirm", "Confirmar datos"), ("nl_advisor", "Hablar con asesor"))
CHANGE_BUTTONS = (
    ("nl_apply_changes", "Aplicar cambios"),
    ("nl_keep_details", "Conservar datos"),
    ("nl_advisor", "Hablar con asesor"),
)
QUESTIONS = {
    "contact_name": "¿Cuál es el nombre de la persona de contacto?",
    "event_date": "¿Cuál es la fecha del evento? Incluye día, mes y año, por favor.",
    "guest_count": "¿Para cuántas personas necesitas el servicio?",
    "location": "¿En qué lugar se realizará el evento?",
    "service_type": "¿Te interesa nuestro servicio de parrillada?",
}
HELP_BUTTONS = (
    ("nl_continue", "Continuar solicitud"),
    ("nl_menu", "Ver menú"),
    ("nl_advisor", "Hablar con asesor"),
)
INFO_BUTTONS = (
    ("nl_menu", "Ver menú"),
    ("nl_coverage", "Ver cobertura"),
    ("nl_continue", "Solicitar cotización"),
)
FALLBACK_BUTTONS = (
    ("nl_guided", "Continuar sin IA"),
    ("nl_continue", "Volver a mis datos"),
    ("nl_advisor", "Hablar con asesor"),
)
HANDOFF = "Dejaré tu consulta para un asesor. El bot queda en pausa para que pueda atenderte."


def review(details: EventDetails, contact_name: str | None = None) -> FlowDecision:
    contact = " ".join(str(contact_name or "").split())[:120] or "Pendiente"
    return FlowDecision(
        step="nl_review",
        text=(
            "Revisa los datos de tu solicitud:\n\n"
            f"Punto de contacto: {contact}\n"
            f"Fecha: {details.event_date}\n"
            f"Personas: {details.guest_count}\n"
            f"Ubicación: {details.location}\n"
            "Servicio: Parrilla\n\n"
            "¿Confirmas que son correctos? También puedes escribir una corrección.\n"
            "Esta solicitud no confirma precio, reserva ni disponibilidad."
        ),
        buttons=REVIEW_BUTTONS,
        updates={
            "_nl_draft": details.model_dump(mode="json"),
            "_nl_changes": None,
            "_nl_date_parts": None,
            "_nl_week_start": None,
            "_nl_contact_name": contact,
        },
    )


def next_question(
    details: EventDetails,
    date_parts: dict | None = None,
    contact_name: str | None = None,
    require_contact_name: bool = False,
) -> FlowDecision:
    if require_contact_name and not (contact_name or "").strip():
        return FlowDecision(
            step="nl_collect",
            text=QUESTIONS["contact_name"],
            updates={
                "_nl_contact_name": None,
                "_nl_date_parts": None,
                "_nl_week_start": None,
                "_require_contact_name": True,
            },
        )
    today = ExtractionRequest(message="date validation").reference_date
    if details.event_date is not None and details.event_date < today:
        details = details.model_copy(update={"event_date": None})
    missing = [field for field in EVENT_FIELDS if getattr(details, field) is None]
    if not missing:
        return review(details, contact_name)
    question = QUESTIONS[missing[0]]
    if missing[0] == "event_date" and date_parts:
        question = f"¿De qué año sería el {date_parts['day']} de {MONTHS[date_parts['month'] - 1]}?"
    else:
        date_parts = None
    return FlowDecision(
        step="nl_collect",
        text=question,
        updates={
            "_nl_draft": details.model_dump(mode="json"),
            "_nl_changes": None,
            "_nl_date_parts": date_parts,
            "_nl_week_start": None,
        },
    )


def side_reply(step: str, text: str, *, buttons=HELP_BUTTONS) -> FlowDecision:
    # Preserve both the draft and any proposed corrections until explicit acceptance.
    return FlowDecision(step=step, text=text, buttons=buttons)


def continue_request(step: str, data: dict) -> FlowDecision:
    if step == "nl_changes":
        return side_reply(
            step,
            "Tienes una corrección pendiente. ¿Quieres aplicarla o conservar los datos anteriores?",
            buttons=CHANGE_BUTTONS,
        )
    return next_question(
        EventDetails.model_validate(data.get("_nl_draft") or {}),
        data.get("_nl_date_parts"),
        data.get("_nl_contact_name"),
        bool(data.get("_require_contact_name")),
    )


def date_answer(message: str, details: EventDetails, data: dict) -> FlowDecision | None:
    pending_week = data.get("_nl_week_start")
    if isinstance(pending_week, str):
        try:
            resolved = resolve_weekday_in_week(message, date.fromisoformat(pending_week))
        except ValueError:
            resolved = None
        if resolved is not None:
            return next_question(
                details.model_copy(update={"event_date": resolved.value}),
                contact_name=data.get("_nl_contact_name"),
                require_contact_name=bool(data.get("_require_contact_name")),
            )
    parsed = parse_date_answer(message, data.get("_nl_date_parts"))
    if parsed is None:
        return None
    day, month, year = parsed
    try:
        # Leap year permits February 29 until the customer supplies the actual year.
        value = date(year if year is not None else 2000, month, day)
    except ValueError:
        return FlowDecision(
            step="nl_collect",
            text="Esa fecha no existe en el calendario. ¿Qué fecha deseas para tu evento? "
            "Indica día, mes y año, por favor.",
            updates={"_nl_date_parts": None},
        )
    parts = {"day": day, "month": month}
    if year is None:
        return next_question(
            details,
            parts,
            data.get("_nl_contact_name"),
            bool(data.get("_require_contact_name")),
        )
    if value < ExtractionRequest(message="date validation").reference_date:
        return FlowDecision(
            step="nl_collect",
            text=f"El {day} de {MONTHS[month - 1]} de {year} ya pasó. "
            "¿Cuál es la nueva fecha del evento? Incluye el año, por favor.",
            updates={"_nl_date_parts": None},
        )
    return next_question(
        details.model_copy(update={"event_date": value}),
        contact_name=data.get("_nl_contact_name"),
        require_contact_name=bool(data.get("_require_contact_name")),
    )


def service_answer(
    message: str, details: EventDetails, contact_name: str | None = None
) -> FlowDecision | None:
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", message.casefold())
        if not unicodedata.combining(char)
    )
    text = " ".join(text.replace(",", " ").strip("¡!¿?.,;: \n\t").split())
    if text in {
        "si",
        "si claro",
        "si por favor",
        "claro",
        "correcto",
        "de acuerdo",
        "asi es",
        "me interesa",
        "si me interesa",
        "por supuesto",
        "parrilla",
        "parrillada",
    }:
        return next_question(
            details.model_copy(update={"service_type": "parrilla"}),
            contact_name=contact_name,
        )
    if text in {"no", "no gracias", "no me interesa", "por ahora no", "todavia no"}:
        return side_reply(
            "nl_collect",
            "Entendido. Conservé los datos de tu evento. Puedes ver el menú o hablar "
            "con un asesor para revisar lo que necesitas.",
        )
    return None


def guided_answer(step: str, incoming: IncomingText, details: EventDetails) -> FlowDecision:
    """Literal, validated fallback answers; no model is required to advance."""
    if step != "nl_collect":
        return side_reply(
            step,
            "Puedes confirmar los datos o hablar con un asesor.",
            buttons=REVIEW_BUTTONS if step == "nl_review" else CHANGE_BUTTONS,
        )
    field = next((field for field in EVENT_FIELDS if getattr(details, field) is None), None)
    if field is None:
        return review(details)
    value = incoming.body.strip()
    try:
        if field == "event_date":
            value = date.fromisoformat(value)
            if value < ExtractionRequest(message="date validation").reference_date:
                raise ValueError("Past date")
        elif field == "guest_count":
            if not value.isascii() or not value.isdecimal():
                raise ValueError("Use a positive integer")
            value = int(value)
        elif field == "service_type":
            value = "parrilla" if value.casefold() in {"parrilla", "parrillada"} else value
        updated = EventDetails.model_validate({**details.model_dump(), field: value})
    except (ValueError, ValidationError):
        prompt = (
            "Usa el formato AAAA-MM-DD para la fecha."
            if field == "event_date"
            else QUESTIONS[field]
        )
        return FlowDecision(step=step, text=prompt, buttons=HELP_BUTTONS)
    return next_question(updated)


@telemetry_trace
def natural_language_decision(
    step: str,
    incoming: IncomingText | ButtonReply,
    data: dict,
    assistant: AssistantService,
) -> FlowDecision | None:
    """None leaves existing guided conversations and buttons on their current flow."""
    if step == "start" and isinstance(incoming, IncomingText):
        # Both modes share the branded opening before interpreting free text.
        return decide(step, incoming, flow_data=data)
    if step not in NL_STEPS | {"start", "menu"}:
        return None
    if isinstance(incoming, IncomingText) and (
        not incoming.body.strip() or len(incoming.body) > 4000
    ):
        return FlowDecision(step=step, text="Escribe brevemente los datos de tu evento, por favor.")
    if isinstance(incoming, IncomingText) and assistant.requests_human(incoming.body):
        return FlowDecision(step=step, text=HANDOFF, handoff=True)
    if (
        step == "nl_collect"
        and isinstance(incoming, IncomingText)
        and data.get("_require_contact_name")
        and "_nl_contact_name" in data
        and not (data.get("_nl_contact_name") or "").strip()
    ):
        contact_name = " ".join(incoming.body.split())[:120]
        if len(contact_name) < 2:
            return FlowDecision(step=step, text=QUESTIONS["contact_name"])
        details = EventDetails.model_validate(data.get("_nl_draft") or {})
        decision = next_question(
            details,
            data.get("_nl_date_parts"),
            contact_name,
        )
        return FlowDecision(
            step=decision.step,
            text=decision.text,
            buttons=decision.buttons,
            updates={**decision.updates, "_nl_contact_name": contact_name},
        )
    if isinstance(incoming, ButtonReply):
        if incoming.id in {"nl_advisor", "talk_to_agent", "advisor"}:
            return FlowDecision(step=step, text=HANDOFF, handoff=True)
        if incoming.id in {"view_services", "services"}:
            answer = assistant.answer_question("general", tenant_id="parrilladas")
            return side_reply(step, answer.text, buttons=INFO_BUTTONS)
        if incoming.id in {"nl_menu", "nl_coverage"}:
            topic = "menu" if incoming.id == "nl_menu" else "coverage"
            answer = assistant.answer_question(topic, tenant_id="parrilladas")
            return side_reply(step, answer.text)
        if incoming.id in {"nl_continue", "nl_guided"}:
            decision = continue_request(step, data)
            if incoming.id == "nl_guided":
                return FlowDecision(
                    step=decision.step,
                    text="Sigamos con preguntas sencillas. Para fechas usa AAAA-MM-DD.\n\n"
                    + decision.text,
                    buttons=decision.buttons,
                    updates={**decision.updates, "_nl_guided": True},
                )
            return decision
        if step == "menu" and incoming.id in {"quote", "request_quote"}:
            return next_question(EventDetails(), require_contact_name=True)
        if step not in NL_STEPS:
            return None
        details = EventDetails.model_validate(data.get("_nl_draft") or {})
        if step == "nl_review" and incoming.id == "nl_confirm":
            today = ExtractionRequest(message="date validation").reference_date
            if any(getattr(details, field) is None for field in EVENT_FIELDS) or (
                details.event_date is not None and details.event_date < today
            ):
                return next_question(
                    details,
                    require_contact_name=bool(data.get("_require_contact_name")),
                )
            closing = decide("summary", ButtonReply("confirm"), flow_data=data)
            return FlowDecision(
                step="submitted",
                text=closing.text,
                updates={**details.model_dump(mode="json"), "_nl_confirmed": True},
            )
        if step == "nl_changes" and incoming.id == "nl_apply_changes":
            proposed = EventDetails.model_validate(data.get("_nl_changes") or {})
            return next_question(proposed)
        if step == "nl_changes" and incoming.id == "nl_keep_details":
            return next_question(details)
        return FlowDecision(
            step=step,
            text="Selecciona una opción o escribe los datos que deseas corregir.",
            buttons=CHANGE_BUTTONS if step == "nl_changes" else REVIEW_BUTTONS,
        )
    try:
        details = EventDetails.model_validate(data.get("_nl_draft") or {})
        if step == "nl_collect" and details.event_date is None:
            week = parse_relative_event_week(
                incoming.body,
                ExtractionRequest(message="date validation").reference_date,
            )
            if week is not None:
                return FlowDecision(
                    step="nl_collect",
                    text="¿Qué día de esa semana sería? Por ejemplo: martes.",
                    updates={
                        "_nl_week_start": week.week_start.isoformat(),
                        "_nl_date_parts": None,
                    },
                )
            clarified = date_answer(incoming.body, details, data)
            if clarified is not None:
                return clarified
        requested_field = next(
            (field for field in EVENT_FIELDS if getattr(details, field) is None), None
        )
        if step == "nl_collect" and requested_field == "service_type":
            answered = service_answer(incoming.body, details, data.get("_nl_contact_name"))
            if answered is not None:
                return answered
        if data.get("_nl_guided"):
            return guided_answer(step, incoming, details)
        outcome = assistant.extract(
            ExtractionRequest(
                message=incoming.body,
                confirmed=details,
                requested_field=requested_field if step == "nl_collect" else None,
            )
        )
    except ValidationError:
        return side_reply(
            step,
            "No pude recuperar los datos. Un asesor puede ayudarte si lo deseas.",
            buttons=(("nl_advisor", "Hablar con asesor"),),
        )
    if outcome.status == "handoff":
        return FlowDecision(step=step, text=HANDOFF, handoff=True)
    if outcome.status == "knowledge":
        answer = assistant.answer_question(
            outcome.topic, tenant_id="parrilladas", question=incoming.body
        )
        return side_reply(
            step,
            answer.text,
            buttons=INFO_BUTTONS if outcome.topic == "general" else HELP_BUTTONS,
        )
    if outcome.status != "extracted":
        if outcome.reason == "unsupported":
            return side_reply(
                step,
                "Te puedo ayudar con el menú, la cobertura y la solicitud de tu evento. "
                "¿Qué te gustaría consultar?",
            )
        return side_reply(
            step,
            "Ahora no pude interpretar tu mensaje. Tus datos siguen guardados. "
            "Podemos continuar con preguntas sencillas o, si prefieres, con un asesor.",
            buttons=FALLBACK_BUTTONS,
        )
    if not any(getattr(outcome.details, field) is not None for field in EVENT_FIELDS):
        return (
            next_question(
                outcome.details,
                data.get("_nl_date_parts"),
                data.get("_nl_contact_name"),
                bool(data.get("_require_contact_name")),
            )
            if step in NL_STEPS
            else None
        )
    if outcome.changed_fields:
        proposed = outcome.details.model_dump(mode="json")
        changes = outcome.proposed_changes.model_dump(mode="json", exclude_none=True)
        proposed.update(changes)
        labels = {
            "event_date": "Fecha",
            "guest_count": "Personas",
            "location": "Ubicación",
            "service_type": "Servicio",
        }
        lines = [
            f"{labels[field]}: {getattr(details, field)} → {changes[field]}"
            for field in outcome.changed_fields
        ]
        return FlowDecision(
            step="nl_changes",
            text="¿Aplicamos estos cambios?\n\n" + "\n".join(lines),
            buttons=CHANGE_BUTTONS,
            updates={
                "_nl_draft": outcome.details.model_dump(mode="json"),
                "_nl_changes": proposed,
            },
        )
    if step == "nl_changes":
        return continue_request(step, data)
    return next_question(
        outcome.details,
        data.get("_nl_date_parts"),
        data.get("_nl_contact_name"),
        bool(data.get("_require_contact_name")),
    )
