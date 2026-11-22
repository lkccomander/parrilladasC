import json
from unittest.mock import Mock

import pytest

from parrilladas.modules.assistant.errors import ExtractionUnavailable
from parrilladas.modules.assistant.schemas import EventDetails
from parrilladas.modules.assistant.service import AssistantService
from parrilladas.modules.conversations.contracts import ButtonReply, IncomingText
from parrilladas.modules.conversations.flow import decide
from parrilladas.modules.conversations.natural_language import natural_language_decision

MESSAGE = "Quiero parrillada para 20 personas el 20 de diciembre de 2027 en Alajuela."
DETAILS = {
    "event_date": "2027-12-20",
    "guest_count": 20,
    "location": "Alajuela",
    "service_type": "parrilla",
}


def provider(details=None, **extra):
    return Mock(
        extract=Mock(
            return_value=json.dumps(
                {
                    "intent": "quote",
                    "details": details or DETAILS,
                    "date_evidence": "20 de diciembre de 2027",
                    **extra,
                }
            )
        )
    )


def test_complete_request_is_reviewed_before_customer_confirmation_and_remains_terminal():
    model = provider()
    assistant = AssistantService(model, enabled=True)
    decision = natural_language_decision("menu", IncomingText(MESSAGE), {}, assistant)
    assert decision.step == "nl_review"
    assert decision.updates["_nl_draft"] == DETAILS
    assert "no confirma precio" in decision.text
    data = {**decision.updates, "request_reference": "PEC-SYNTHETIC"}
    confirmed = natural_language_decision("nl_review", ButtonReply("nl_confirm"), data, assistant)
    assert confirmed.step == "submitted"
    assert confirmed.updates["_nl_confirmed"] is True
    assert confirmed.updates["event_date"] == "2027-12-20"
    assert "PEC-SYNTHETIC" in confirmed.text
    assert natural_language_decision("submitted", IncomingText(MESSAGE), data, assistant) is None
    assert model.extract.call_count == 1


def test_natural_language_quote_button_requests_contact_name():
    assistant = AssistantService(provider(), enabled=True)
    opening = natural_language_decision("menu", ButtonReply("request_quote"), {}, assistant)
    assert opening.text == "¿Cuál es el nombre de la persona de contacto?"
    data = dict(opening.updates)
    answer = natural_language_decision("nl_collect", IncomingText("María Pérez"), data, assistant)
    assert answer.updates["_nl_contact_name"] == "María Pérez"
    assert "fecha" in answer.text.casefold()


def test_short_answers_include_the_requested_field_and_keep_previous_data():
    model = provider({"guest_count": 20}, date_evidence=None)
    assistant = AssistantService(model, enabled=True)
    data = {"_nl_draft": {**DETAILS, "guest_count": None}}
    decision = natural_language_decision("nl_collect", IncomingText("20"), data, assistant)
    assert model.extract.call_args.args[0].requested_field == "guest_count"
    assert decision.step == "nl_review"
    assert decision.updates["_nl_draft"] == DETAILS


def test_correction_needs_explicit_acceptance_and_another_final_confirmation():
    model = provider({"guest_count": 30}, date_evidence=None)
    assistant = AssistantService(model, enabled=True)
    data = {"_nl_draft": DETAILS}
    decision = natural_language_decision(
        "nl_review", IncomingText("Seremos 30 personas"), data, assistant
    )
    assert decision.step == "nl_changes"
    assert decision.updates["_nl_draft"]["guest_count"] == 20
    assert decision.updates["_nl_changes"]["guest_count"] == 30
    assert "20 → 30" in decision.text
    accepted = natural_language_decision(
        "nl_changes", ButtonReply("nl_apply_changes"), dict(decision.updates), assistant
    )
    assert accepted.step == "nl_review"
    assert accepted.updates["_nl_draft"]["guest_count"] == 30
    assert "_nl_confirmed" not in accepted.updates
    rejected = natural_language_decision(
        "nl_changes", ButtonReply("nl_keep_details"), dict(decision.updates), assistant
    )
    assert rejected.updates["_nl_draft"]["guest_count"] == 20


def test_date_without_literal_year_evidence_is_asked_again():
    model = provider(date_evidence=None)
    decision = natural_language_decision(
        "menu",
        IncomingText("parrillada para diciembre"),
        {},
        AssistantService(model, enabled=True),
    )
    assert decision.step == "nl_collect"
    assert decision.updates["_nl_draft"]["event_date"] is None
    assert "día, mes y año" in decision.text


def test_model_error_offers_guided_fallback_without_pausing_or_losing_details():
    model = Mock(extract=Mock(side_effect=ExtractionUnavailable("unavailable")))
    decision = natural_language_decision(
        "nl_review",
        IncomingText("cambiar invitados"),
        {"_nl_draft": DETAILS},
        AssistantService(model, enabled=True),
    )
    assert not decision.handoff
    assert ("nl_guided", "Continuar sin IA") in decision.buttons
    assert not decision.updates


def test_switch_off_still_allows_review_confirmation_without_a_model_call():
    decision = natural_language_decision(
        "nl_review", ButtonReply("nl_confirm"), {"_nl_draft": DETAILS}, AssistantService()
    )
    assert decision.step == "submitted"


def test_guided_conversations_and_advisor_requests_do_not_call_the_model():
    model = provider()
    assistant = AssistantService(model, enabled=True)
    assert natural_language_decision("event_date", IncomingText(MESSAGE), {}, assistant) is None
    assert natural_language_decision("menu", IncomingText("ASESOR"), {}, assistant).handoff
    assert (
        natural_language_decision("menu", ButtonReply("quote"), {}, assistant).step == "nl_collect"
    )
    model.extract.assert_not_called()


def test_partial_review_cannot_submit_and_invalid_button_cannot_apply_changes():
    data = {"_nl_draft": EventDetails(guest_count=20).model_dump(mode="json")}
    decision = natural_language_decision(
        "nl_review", ButtonReply("nl_confirm"), data, AssistantService()
    )
    assert decision.step == "nl_collect"
    decision = natural_language_decision(
        "nl_changes", ButtonReply("confirm"), data, AssistantService()
    )
    assert decision.step == "nl_changes"
    assert "_nl_confirmed" not in decision.updates


def test_draft_whose_date_has_passed_needs_a_new_date_before_confirmation():
    data = {"_nl_draft": {**DETAILS, "event_date": "2000-01-01"}}
    decision = natural_language_decision(
        "nl_review", ButtonReply("nl_confirm"), data, AssistantService()
    )
    assert decision.step == "nl_collect"
    assert decision.updates["_nl_draft"]["event_date"] is None


def test_unrecognized_interactive_payload_is_safe_text_instead_of_poisoning_the_queue():
    from parrilladas.modules.conversations.service import ConversationService

    assert ConversationService._incoming(
        {"type": "interactive", "interactive": {"list_reply": {"id": "unknown"}}}
    ) == IncomingText("")
    assert ConversationService._incoming({"type": "text", "text": "invalid"}) == IncomingText("")


@pytest.mark.parametrize("message", ["hola", MESSAGE, "quiero más información", "ASESOR"])
def test_natural_language_opening_matches_guided_flow_without_calling_model(message):
    model = Mock(extract=Mock(side_effect=ExtractionUnavailable("unavailable")))
    incoming = IncomingText(message)
    decision = natural_language_decision(
        "start", incoming, {}, AssistantService(model, enabled=True)
    )
    assert decision == decide("start", incoming)
    model.extract.assert_not_called()


def test_partial_spanish_date_asks_only_year_and_combines_follow_up():
    model = provider({"event_date": "2027-12-12"}, date_evidence="Diciembre 12")
    assistant = AssistantService(model, enabled=True)
    opening = natural_language_decision("menu", ButtonReply("nl_continue"), {}, assistant)
    data = {**opening.updates, "request_reference": "PEC-SYNTHETIC"}
    partial = natural_language_decision("nl_collect", IncomingText("Diciembre 12"), data, assistant)
    assert "año" in partial.text and "12 de diciembre" in partial.text
    assert "día, mes y año" not in partial.text
    assert partial.updates["_nl_draft"]["event_date"] is None
    data.update(partial.updates)
    completed = natural_language_decision("nl_collect", IncomingText("2027"), data, assistant)
    assert completed.updates["_nl_draft"]["event_date"] == "2027-12-12"
    assert completed.text == "¿Para cuántas personas necesitas el servicio?"
    model.extract.assert_not_called()


@pytest.mark.parametrize("text", ["Diciembre 12", "12 de diciembre", "el 12 de diciembre."])
def test_partial_date_keeps_other_event_details_and_can_resume_after_menu(text):
    assistant = AssistantService(provider(), enabled=True)
    data = {"_nl_draft": {**DETAILS, "event_date": None}}
    partial = natural_language_decision("nl_collect", IncomingText(text), data, assistant)
    data.update(partial.updates)
    menu = natural_language_decision("nl_collect", ButtonReply("nl_menu"), data, assistant)
    assert not menu.updates
    resumed = natural_language_decision("nl_collect", ButtonReply("nl_continue"), data, assistant)
    assert resumed.text == "¿De qué año sería el 12 de diciembre?"
    data.update(resumed.updates)
    completed = natural_language_decision("nl_collect", IncomingText("en 2027"), data, assistant)
    assert completed.step == "nl_review"
    assert completed.updates["_nl_draft"] == {**DETAILS, "event_date": "2027-12-12"}


@pytest.mark.parametrize(
    ("text", "reason"),
    [("31 de febrero", "no existe"), ("12 de diciembre de 2000", "ya pasó")],
)
def test_invalid_or_past_date_does_not_advance_or_lose_event_details(text, reason):
    data = {"_nl_draft": {**DETAILS, "event_date": None}}
    assistant = AssistantService(provider(), enabled=True)
    decision = natural_language_decision("nl_collect", IncomingText(text), data, assistant)
    assert decision.step == "nl_collect" and reason in decision.text
    data.update(decision.updates)
    assert data["_nl_draft"] == {**DETAILS, "event_date": None}
    assert data.get("_nl_date_parts") is None


def test_leap_day_is_validated_against_supplied_year_and_never_assumed():
    assistant = AssistantService(provider(), enabled=True)
    partial = natural_language_decision("nl_collect", IncomingText("29 de febrero"), {}, assistant)
    assert partial.updates["_nl_draft"]["event_date"] is None
    invalid = natural_language_decision(
        "nl_collect", IncomingText("2027"), partial.updates, assistant
    )
    assert "no existe" in invalid.text
    valid = natural_language_decision(
        "nl_collect", IncomingText("2028"), partial.updates, assistant
    )
    assert valid.updates["_nl_draft"]["event_date"] == "2028-02-29"


def test_explicit_complete_date_replaces_pending_parts_without_merging_old_day():
    assistant = AssistantService(provider(), enabled=True)
    partial = natural_language_decision("nl_collect", IncomingText("Diciembre 12"), {}, assistant)
    decision = natural_language_decision(
        "nl_collect", IncomingText("15 de enero de 2028"), partial.updates, assistant
    )
    assert decision.updates["_nl_draft"]["event_date"] == "2028-01-15"
    assert decision.updates["_nl_date_parts"] is None


def test_yes_to_parrillada_question_advances_to_review_without_submitting():
    model = provider({"service_type": None}, date_evidence=None)
    assistant = AssistantService(model, enabled=True)
    draft = {
        "event_date": "2027-06-03",
        "guest_count": 7,
        "location": "Guachipelín",
        "service_type": None,
    }
    data = {"_nl_draft": draft, "request_reference": "PEC-SYNTHETIC"}
    question = natural_language_decision("nl_collect", ButtonReply("nl_continue"), data, assistant)
    assert question.text == "¿Te interesa nuestro servicio de parrillada?"
    decision = natural_language_decision("nl_collect", IncomingText("Si"), data, assistant)
    assert decision.step == "nl_review"
    assert decision.updates["_nl_draft"] == {**draft, "service_type": "parrilla"}
    assert not decision.updates.get("_nl_confirmed")
    assert not decision.handoff


@pytest.mark.parametrize("answer", ["Sí", "SI", "sí, claro", "Claro", "De acuerdo", "Así es"])
@pytest.mark.parametrize("guided", [False, True])
def test_contextual_service_acceptance_works_with_or_without_ai(answer, guided):
    model = Mock(extract=Mock(side_effect=ExtractionUnavailable("unavailable")))
    data = {"_nl_draft": {**DETAILS, "service_type": None}, "_nl_guided": guided}
    decision = natural_language_decision(
        "nl_collect", IncomingText(answer), data, AssistantService(model, enabled=True)
    )
    assert decision.step == "nl_review"
    assert decision.updates["_nl_draft"] == DETAILS
    assert not decision.updates.get("_nl_confirmed")
    model.extract.assert_not_called()


@pytest.mark.parametrize("answer", ["No", "No gracias", "No me interesa"])
def test_declining_service_preserves_draft_and_offers_options_without_handoff(answer):
    model = Mock(extract=Mock(side_effect=ExtractionUnavailable("unavailable")))
    decision = natural_language_decision(
        "nl_collect",
        IncomingText(answer),
        {"_nl_draft": {**DETAILS, "service_type": None}},
        AssistantService(model, enabled=True),
    )
    assert decision.step == "nl_collect" and not decision.updates
    assert "Conservé los datos" in decision.text
    assert ("nl_advisor", "Hablar con asesor") in decision.buttons
    assert not decision.handoff
    model.extract.assert_not_called()


@pytest.mark.parametrize("step", ["nl_collect", "nl_review", "nl_changes"])
def test_yes_does_not_accept_other_fields_pending_corrections_or_final_submission(step):
    model = provider({"service_type": None}, date_evidence=None)
    draft = (
        DETAILS if step != "nl_collect" else {**DETAILS, "guest_count": None, "service_type": None}
    )
    data = {"_nl_draft": draft}
    if step == "nl_changes":
        data["_nl_changes"] = {**DETAILS, "guest_count": 30}
    decision = natural_language_decision(
        step, IncomingText("Sí"), data, AssistantService(model, enabled=True)
    )
    assert decision.step == step
    assert not decision.updates.get("_nl_confirmed")
    if step == "nl_collect":
        assert decision.updates["_nl_draft"]["service_type"] is None
        assert decision.updates["_nl_draft"]["guest_count"] is None
    if step == "nl_changes":
        assert not decision.updates


def test_yes_with_more_event_data_still_uses_extraction_and_correction_review():
    model = provider({"guest_count": 30}, date_evidence=None)
    decision = natural_language_decision(
        "nl_collect",
        IncomingText("Sí, pero seremos 30 personas"),
        {"_nl_draft": {**DETAILS, "service_type": None}},
        AssistantService(model, enabled=True),
    )
    assert decision.step == "nl_changes"
    assert decision.updates["_nl_changes"]["guest_count"] == 30
    assert decision.updates["_nl_draft"]["guest_count"] == 20
    assert model.extract.call_count == 1
