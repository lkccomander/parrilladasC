import json
from unittest.mock import Mock

from parrilladas.modules.assistant.errors import ExtractionUnavailable
from parrilladas.modules.assistant.schemas import EventDetails
from parrilladas.modules.assistant.service import AssistantService
from parrilladas.modules.conversations.contracts import ButtonReply, IncomingText
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
    decision = natural_language_decision("start", IncomingText(MESSAGE), {}, assistant)
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
        "start",
        IncomingText("parrillada para diciembre"),
        {},
        AssistantService(model, enabled=True),
    )
    assert decision.step == "nl_collect"
    assert decision.updates["_nl_draft"]["event_date"] is None
    assert "día, mes y año" in decision.text


def test_model_error_hands_existing_nl_draft_to_human_without_losing_details():
    model = Mock(extract=Mock(side_effect=ExtractionUnavailable("unavailable")))
    decision = natural_language_decision(
        "nl_review",
        IncomingText("cambiar invitados"),
        {"_nl_draft": DETAILS},
        AssistantService(model, enabled=True),
    )
    assert decision.handoff
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
