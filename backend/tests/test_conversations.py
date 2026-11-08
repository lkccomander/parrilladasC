from parrilladas.modules.conversations.contracts import ButtonReply, IncomingText
from parrilladas.modules.conversations.flow import decide


def test_first_message_opens_the_quote_menu():
    decision = decide("start", IncomingText("hola"))

    assert decision.step == "menu"
    assert decision.text == "¡Hola! Gracias por contactar a Parrilladas en su Casa 🔥"
    assert decision.buttons == (
        ("quote", "Solicitar cotización"),
        ("services", "Ver servicios"),
        ("advisor", "Hablar con un asesor"),
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
        decide("service_type", IncomingText("parrillada")),
    ]

    assert [decision.step for decision in decisions] == [
        "event_date",
        "location",
        "guest_count",
        "service_type",
        "summary",
    ]
    assert [decision.updates for decision in decisions] == [
        {"event_type": "corporativo"},
        {"event_date": "15 de diciembre"},
        {"location": "Zona 10"},
        {"guest_count": "80"},
        {"service_type": "parrillada"},
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
    assert decision.updates == {}
    assert decision.text == "Indícanos la cantidad aproximada de personas, por favor."
