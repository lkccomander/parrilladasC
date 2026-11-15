"""Convert validated extraction proposals into explicit customer review steps."""

from pydantic import ValidationError

from parrilladas.modules.assistant.schemas import EVENT_FIELDS, EventDetails, ExtractionRequest
from parrilladas.modules.assistant.service import AssistantService

from .contracts import ButtonReply, FlowDecision, IncomingText
from .flow import decide

NL_STEPS = {"nl_collect", "nl_review", "nl_changes"}
REVIEW_BUTTONS = (("nl_confirm", "Confirmar datos"), ("nl_advisor", "Hablar con asesor"))
CHANGE_BUTTONS = (
    ("nl_apply_changes", "Aplicar cambios"),
    ("nl_keep_details", "Conservar datos"),
    ("nl_advisor", "Hablar con asesor"),
)
QUESTIONS = {
    "event_date": "¿Cuál es la fecha del evento? Incluye día, mes y año, por favor.",
    "guest_count": "¿Para cuántas personas necesitas el servicio?",
    "location": "¿En qué lugar se realizará el evento?",
    "service_type": "¿Te interesa nuestro servicio de parrillada?",
}
HANDOFF = "Dejaré tu consulta para un asesor. El bot queda en pausa para que pueda atenderte."


def review(details: EventDetails) -> FlowDecision:
    return FlowDecision(
        step="nl_review",
        text=(
            "Revisa los datos de tu solicitud:\n\n"
            f"Fecha: {details.event_date}\n"
            f"Personas: {details.guest_count}\n"
            f"Ubicación: {details.location}\n"
            "Servicio: Parrilla\n\n"
            "¿Confirmas que son correctos? También puedes escribir una corrección.\n"
            "Esta solicitud no confirma precio, reserva ni disponibilidad."
        ),
        buttons=REVIEW_BUTTONS,
        updates={"_nl_draft": details.model_dump(mode="json"), "_nl_changes": None},
    )


def next_question(details: EventDetails) -> FlowDecision:
    today = ExtractionRequest(message="date validation").reference_date
    if details.event_date is not None and details.event_date < today:
        details = details.model_copy(update={"event_date": None})
    missing = [field for field in EVENT_FIELDS if getattr(details, field) is None]
    if not missing:
        return review(details)
    return FlowDecision(
        step="nl_collect",
        text=QUESTIONS[missing[0]],
        updates={"_nl_draft": details.model_dump(mode="json"), "_nl_changes": None},
    )


def natural_language_decision(
    step: str,
    incoming: IncomingText | ButtonReply,
    data: dict,
    assistant: AssistantService,
) -> FlowDecision | None:
    """None leaves existing guided conversations and buttons on their current flow."""
    if step == "submitted":
        return None
    if isinstance(incoming, IncomingText) and incoming.body.strip().casefold() == "asesor":
        return FlowDecision(step=step, text=HANDOFF, handoff=True)
    if isinstance(incoming, ButtonReply):
        if incoming.id in {"nl_advisor", "talk_to_agent", "advisor"}:
            return FlowDecision(step=step, text=HANDOFF, handoff=True)
        if step == "menu" and incoming.id in {"quote", "request_quote"}:
            return next_question(EventDetails())
        if step not in NL_STEPS:
            return None
        details = EventDetails.model_validate(data.get("_nl_draft") or {})
        if step == "nl_review" and incoming.id == "nl_confirm":
            today = ExtractionRequest(message="date validation").reference_date
            if any(getattr(details, field) is None for field in EVENT_FIELDS) or (
                details.event_date is not None and details.event_date < today
            ):
                return next_question(details)
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
    if step not in NL_STEPS | {"start", "menu"}:
        return None
    if not incoming.body.strip() or len(incoming.body) > 4000:
        return FlowDecision(step=step, text="Escribe brevemente los datos de tu evento, por favor.")
    try:
        details = EventDetails.model_validate(data.get("_nl_draft") or {})
        requested_field = next(
            (field for field in EVENT_FIELDS if getattr(details, field) is None), None
        )
        outcome = assistant.extract(
            ExtractionRequest(
                message=incoming.body,
                confirmed=details,
                requested_field=requested_field if step == "nl_collect" else None,
            )
        )
    except ValidationError:
        return FlowDecision(step=step, text=HANDOFF, handoff=True)
    if outcome.status == "handoff":
        return FlowDecision(step=step, text=HANDOFF, handoff=True)
    if outcome.status != "extracted":
        if step not in NL_STEPS:
            return None
        return FlowDecision(
            step=step,
            text="No pude interpretar el mensaje. Un asesor podrá revisar tu solicitud.",
            handoff=True,
        )
    if not any(getattr(outcome.details, field) is not None for field in EVENT_FIELDS):
        return next_question(outcome.details) if step in NL_STEPS else None
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
    return next_question(outcome.details)
