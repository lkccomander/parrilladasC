from parrilladas.modules.conversations.contracts import ButtonReply, IncomingText
from parrilladas.modules.conversations.flow import GREETING, MENU_BUTTONS, decide


def test_first_message_opens_the_quote_menu():
    decision = decide("start", IncomingText("hola"))

    assert decision.step == "menu"
    assert decision.text == "¡Hola! Gracias por contactar a Parrilladas en su Casa 🔥"
    assert decision.buttons == (
        ("request_quote", "Solicitar cotización"),
        ("view_services", "Ver servicios"),
        ("talk_to_agent", "Hablar con un asesor"),
    )


def test_menu_buttons_have_the_beta_placeholder_responses():
    assert decide("menu", ButtonReply("quote")).step == "event_type"
    assert decide("menu", ButtonReply("services")).text == (
        "Esta opción estará disponible próximamente."
    )
    assert decide("menu", ButtonReply("advisor")).text == (
        "Un asesor podrá ayudarte próximamente. Escribe ASESOR si necesitas atención."
    )


def test_quote_questions_advance_in_order_and_capture_answers():
    decisions = [
        decide("event_type", IncomingText("corporativo")),
        decide("event_date", IncomingText("15 de diciembre")),
        decide("location", IncomingText("Zona 10")),
        decide("guest_count", IncomingText("80")),
        decide("service_type", ButtonReply("service_parrilla")),
    ]

    assert [decision.step for decision in decisions] == [
        "event_date",
        "location",
        "guest_count",
        "service_type",
        "summary",
    ]
    assert [decision.updates for decision in decisions] == [
        {"event_type": "corporativo", "_invalid_attempts": 0},
        {"event_date": "15 de diciembre", "_invalid_attempts": 0},
        {"location": "Zona 10", "_invalid_attempts": 0},
        {"guest_count": "80", "_invalid_attempts": 0},
        {"service_type": "parrilla", "_invalid_attempts": 0},
    ]


def test_summary_confirmation_submits_the_quote_request():
    decision = decide("summary", ButtonReply("confirm"))

    assert decision.step == "submitted"
    assert decision.text == (
        "Gracias. Recibimos tu solicitud. Nuestro equipo revisará la información "
        "y se comunicará contigo por este mismo número."
    )


def test_advisor_text_is_a_handoff_signal():
    decision = decide("menu", IncomingText("ASESOR"))

    assert decision.handoff is True
    assert decision.step == "menu"


def test_invalid_input_keeps_the_current_step_and_returns_a_safe_prompt():
    decision = decide("guest_count", IncomingText("muchas personas"))

    assert decision.step == "guest_count"
    assert decision.updates == {"_invalid_attempts": 1}
    assert decision.text == "Indícanos la cantidad aproximada de personas, por favor."


def test_service_step_shows_only_the_parrilla_button():
    decision = decide("guest_count", IncomingText("80"))

    assert decision.step == "service_type"
    assert decision.buttons == (("service_parrilla", "Parrilla"),)


def test_parrilla_button_captures_service_and_advances_to_summary():
    decision = decide("service_type", ButtonReply("service_parrilla"))

    assert decision.step == "summary"
    assert decision.updates["service_type"] == "parrilla"


def test_invalid_service_text_repeats_question_and_increments_counter():
    decision = decide("service_type", IncomingText("buffet"), flow_data={"_invalid_attempts": 1})

    assert decision.step == "service_type"
    assert decision.buttons == (("service_parrilla", "Parrilla"),)
    assert decision.updates["_invalid_attempts"] == 2


def test_third_invalid_reply_resets_to_greeting_menu():
    decision = decide("service_type", IncomingText("no sé"), flow_data={"_invalid_attempts": 2})

    assert decision.step == "menu"
    assert decision.text == GREETING
    assert decision.buttons == MENU_BUTTONS
    assert decision.reset is True
    assert decision.updates == {}


def test_valid_reply_clears_invalid_counter():
    decision = decide(
        "service_type", ButtonReply("service_parrilla"), flow_data={"_invalid_attempts": 2}
    )

    assert decision.updates["_invalid_attempts"] == 0


def test_invalid_attempts_are_consecutive_across_valid_steps():
    invalid = decide("guest_count", IncomingText("muchas"), flow_data={"_invalid_attempts": 1})
    valid = decide("guest_count", IncomingText("80"), flow_data=invalid.updates)
    invalid_again = decide("service_type", IncomingText("buffet"), flow_data=valid.updates)

    assert invalid.updates["_invalid_attempts"] == 2
    assert valid.updates["_invalid_attempts"] == 0
    assert invalid_again.updates["_invalid_attempts"] == 1
