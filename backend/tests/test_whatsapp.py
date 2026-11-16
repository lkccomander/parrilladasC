import copy
import hashlib
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from parrilladas.core.config import ApiSettings
from parrilladas.integrations.whatsapp.client import MetaClient, MetaSendError
from parrilladas.integrations.whatsapp.router import MAX_BODY_BYTES
from parrilladas.integrations.whatsapp.webhook import parse_events
from parrilladas.main import create_app
from parrilladas.modules.accounts.contracts import Role
from parrilladas.modules.accounts.models import Account
from parrilladas.modules.accounts.schemas import AccountCreate, AccountView
from parrilladas.modules.accounts.service import AccountService
from parrilladas.modules.assistant.config import AssistantSettings
from parrilladas.modules.assistant.preferences import AssistantPreferenceService
from parrilladas.modules.assistant.schemas import AssistantPreferencesUpdate
from parrilladas.modules.conversations.flow import GREETING, MENU_BUTTONS
from parrilladas.modules.conversations.models import (
    Conversation,
    Interaction,
    Message,
    WhatsAppInboxEvent,
)
from parrilladas.modules.conversations.repository import InboxRepository
from parrilladas.modules.conversations.service import ConversationService, InboxService
from parrilladas.modules.conversations.worker import ConversationWorker

# Synthetic provider data only; never copy real customer events into fixtures.
SECRET = "synthetic-meta-app-secret"
VERIFY_TOKEN = "synthetic-subscription-token"
WABA = "100000001"
PHONE_ID = "200000001"
RECIPIENT = "15550000002"
TOKEN = "synthetic-meta-access-token"
PATH = "/webhooks/whatsapp"


def settings(**overrides):
    values = dict(
        app_env="test",
        database_url="postgresql+psycopg://test:test@localhost:1/test",
        jwt_secret="test-only-signing-key-at-least-32-characters",
        whatsapp_app_secret=SECRET,
        whatsapp_verify_token=VERIFY_TOKEN,
        whatsapp_business_account_id=WABA,
        whatsapp_phone_number_id=PHONE_ID,
        _env_file=None,
    )
    return ApiSettings(**(values | overrides))


def payload(*ids):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": PHONE_ID},
                            "messages": [
                                {
                                    "id": identifier,
                                    "from": "15550000001",
                                    "timestamp": "1794000000",
                                    "type": "text",
                                    "text": {"body": "Cotización de prueba 🔥"},
                                }
                                for identifier in ids
                            ],
                        },
                    }
                ],
            }
        ],
    }


def encode(data):
    return json.dumps(data, ensure_ascii=False).encode()


def signed(client, body, secret=SECRET):
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        PATH,
        content=body,
        headers={"X-Hub-Signature-256": f"sha256={signature}", "Content-Type": "application/json"},
    )


def test_send_text_uses_messages_endpoint_and_returns_meta_id():
    calls = []

    def meta(request):
        calls.append(request)
        assert request.method == "POST"
        assert request.url.path == f"/v27.0/{PHONE_ID}/messages"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert json.loads(request.content) == {
            "messaging_product": "whatsapp",
            "to": RECIPIENT,
            "type": "text",
            "text": {"body": "Hola"},
        }
        return httpx.Response(200, json={"messages": [{"id": "wamid.text"}]})

    with httpx.Client(transport=httpx.MockTransport(meta)) as http:
        message_id = MetaClient(http).send_text(
            version="v27.0", phone_id=PHONE_ID, token=TOKEN, recipient=RECIPIENT, body="Hola"
        )
    assert message_id == "wamid.text"
    assert len(calls) == 1


def test_send_image_uses_public_link_and_caption():
    def meta(request):
        assert request.method == "POST"
        assert json.loads(request.content) == {
            "messaging_product": "whatsapp",
            "to": RECIPIENT,
            "type": "image",
            "image": {"link": "https://example.com/greeting.png", "caption": "Bienvenido"},
        }
        return httpx.Response(200, json={"messages": [{"id": "wamid.image"}]})

    with httpx.Client(transport=httpx.MockTransport(meta)) as http:
        message_id = MetaClient(http).send_image(
            version="v27.0",
            phone_id=PHONE_ID,
            token=TOKEN,
            recipient=RECIPIENT,
            image_url="https://example.com/greeting.png",
            caption="Bienvenido",
        )
    assert message_id == "wamid.image"


def test_send_buttons_uses_interactive_reply_buttons():
    def meta(request):
        assert request.method == "POST"
        assert json.loads(request.content) == {
            "messaging_product": "whatsapp",
            "to": RECIPIENT,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "¿Qué necesitas?"},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "quote", "title": "Cotización"}},
                        {"type": "reply", "reply": {"id": "advisor", "title": "Asesor"}},
                    ]
                },
            },
        }
        return httpx.Response(200, json={"messages": [{"id": "wamid.buttons"}]})

    with httpx.Client(transport=httpx.MockTransport(meta)) as http:
        message_id = MetaClient(http).send_buttons(
            version="v27.0",
            phone_id=PHONE_ID,
            token=TOKEN,
            recipient=RECIPIENT,
            body="¿Qué necesitas?",
            buttons=[("quote", "Cotización"), ("advisor", "Asesor")],
        )
    assert message_id == "wamid.buttons"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(401, json={"error": {"message": TOKEN}}), "access_denied"),
        (httpx.Response(429, json={"error": {"message": TOKEN}}), "rate_limited"),
        (httpx.Response(503, json={"error": {"message": TOKEN}}), "unavailable"),
        (httpx.Response(200, text=TOKEN), "invalid_response"),
        (httpx.Response(200, json={"messages": []}), "invalid_response"),
    ],
)
def test_outbound_errors_are_safe(response, expected):
    def meta(request):
        return response

    with (
        httpx.Client(transport=httpx.MockTransport(meta)) as http,
        pytest.raises(MetaSendError) as error,
    ):
        MetaClient(http).send_text(
            version="v27.0", phone_id=PHONE_ID, token=TOKEN, recipient=RECIPIENT, body="Hola"
        )
    assert error.value.category == expected
    assert TOKEN not in str(error.value)


def test_outbound_timeout_is_safe():
    def meta(request):
        raise httpx.ReadTimeout(TOKEN, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(meta)) as http,
        pytest.raises(MetaSendError, match="unavailable") as error,
    ):
        MetaClient(http).send_text(
            version="v27.0", phone_id=PHONE_ID, token=TOKEN, recipient=RECIPIENT, body="Hola"
        )
    assert TOKEN not in str(error.value)


@pytest.fixture
def api():
    with TestClient(create_app(settings())) as client:
        yield client


def test_subscription_challenge_requires_correct_token_and_mode(api):
    params = {"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "12345"}
    response = api.get(PATH, params=params)
    assert response.status_code == 200
    assert response.text == "12345"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"] == "no-store"
    for changes in [
        {"hub.mode": "other"},
        {"hub.verify_token": "incorrect"},
        {"hub.verify_token": "\u2603"},
        {"hub.challenge": ""},
    ]:
        response = api.get(PATH, params=params | changes)
        assert response.status_code == 403
        assert VERIFY_TOKEN not in response.text
    assert api.get(PATH).status_code == 403
    assert (
        api.get(PATH, params=[*params.items(), ("hub.verify_token", VERIFY_TOKEN)]).status_code
        == 403
    )


def test_verification_query_is_removed_before_access_logging(api):
    captured = []

    class CaptureScope:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            async def capture(message):
                if message["type"] == "http.response.start":
                    captured.append(scope["query_string"])
                await send(message)

            await self.app(scope, receive, capture)

    with TestClient(CaptureScope(api.app)) as client:
        response = client.get(PATH, params={"hub.verify_token": VERIFY_TOKEN})
    assert response.status_code == 403
    assert captured == [b""]


def test_intake_is_disabled_without_explicit_complete_configuration():
    disabled = settings(
        whatsapp_app_secret=None,
        whatsapp_verify_token=None,
        whatsapp_business_account_id=None,
        whatsapp_phone_number_id=None,
    )
    with TestClient(create_app(disabled)) as client:
        assert client.get(PATH).status_code == 503
        assert signed(client, encode(payload("test"))).status_code == 503
    with pytest.raises(ValidationError, match="all four") as error:
        settings(whatsapp_verify_token=None)
    assert SECRET not in str(error.value)
    assert SECRET not in repr(settings())
    assert VERIFY_TOKEN not in repr(settings())


def test_webhook_is_only_exposed_by_api(client):
    assert client.get(PATH).status_code == 404
    assert client.post(PATH, content=b"{}").status_code == 404


def test_verify_token_alone_enables_handshake_but_keeps_intake_disabled():
    verification_only = settings(
        whatsapp_app_secret=None,
        whatsapp_business_account_id=None,
        whatsapp_phone_number_id=None,
    )
    with TestClient(create_app(verification_only)) as client:
        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "meta-subscription-test",
        }
        response = client.get(PATH, params=params)
        assert response.status_code == 200
        assert response.text == "meta-subscription-test"
        assert client.get(PATH, params=params | {"hub.verify_token": "wrong"}).status_code == 403
        assert signed(client, encode(payload("test"))).status_code == 503


@pytest.mark.parametrize("signature", [None, "", "sha1=abc", "sha256=abc", "sha256=" + "0" * 64])
def test_missing_or_forged_signature_is_rejected_before_database_access(api, signature):
    headers = {} if signature is None else {"X-Hub-Signature-256": signature}
    assert api.post(PATH, content=encode(payload("test")), headers=headers).status_code == 401


def test_signature_is_over_original_bytes_and_headers_are_unambiguous(api):
    body = encode(payload("test"))
    signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert (
        api.post(PATH, content=body + b" ", headers={"X-Hub-Signature-256": signature}).status_code
        == 401
    )
    assert (
        api.post(
            PATH,
            content=body,
            headers=[("X-Hub-Signature-256", signature), ("X-Hub-Signature-256", signature)],
        ).status_code
        == 401
    )


def test_valid_signature_does_not_bypass_payload_or_account_validation(api):
    assert signed(api, b"invalid-json-private-content").status_code == 400
    assert signed(api, b"[]").status_code == 400
    malformed = payload("test")
    malformed["entry"][0]["changes"][0]["value"]["messages"][0].pop("id")
    response = signed(api, encode(malformed))
    assert response.status_code == 400
    assert "Cotización" not in response.text
    other_account = payload("test")
    other_account["entry"][0]["id"] = "999999"
    assert signed(api, encode(other_account)).status_code == 403
    other_number = payload("test")
    other_number["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "999999"
    assert signed(api, encode(other_number)).status_code == 403


def test_body_size_is_bounded_even_without_content_length(api):
    chunks = iter([b"x" * (MAX_BODY_BYTES // 2)] * 3)
    assert api.post(PATH, content=chunks).status_code == 413


def test_storage_failure_is_retryable_and_does_not_expose_data(api, monkeypatch):
    def fail(self, events):
        raise OperationalError("private SQL", {}, Exception("private-password"))

    monkeypatch.setattr(InboxService, "receive", fail)
    response = signed(api, encode(payload("test")))
    assert response.status_code == 503
    assert response.json() == {"detail": "Webhook storage unavailable"}


def test_status_updates_and_unknown_message_types_are_preserved():
    data = payload("test")
    value = data["entry"][0]["changes"][0]["value"]
    value["messages"][0] |= {"type": "image", "image": {"id": "synthetic-media-id"}}
    value["statuses"] = [
        {"id": "sent-test", "timestamp": "1794000001", "status": status}
        for status in ("sent", "delivered", "read")
    ]
    events = parse_events(encode(data), WABA, PHONE_ID)
    assert [event.kind for event in events] == ["message", "status", "status", "status"]
    assert len({event.event_key for event in events}) == 4
    assert events[0].payload["value"]["messages"][0]["image"]["id"] == "synthetic-media-id"
    assert "statuses" not in events[0].payload["value"]
    assert "messages" not in events[1].payload["value"]


def test_provider_errors_are_retained_and_unrelated_subscriptions_are_ignored(api, monkeypatch):
    stored = []
    monkeypatch.setattr(InboxService, "receive", lambda self, events: stored.extend(events))
    data = payload()
    value = data["entry"][0]["changes"][0]["value"]
    value["errors"] = [{"code": 131000, "title": "Synthetic provider failure"}]
    assert signed(api, encode(data)).status_code == 200
    assert len(stored) == 1 and stored[0].kind == "notification"
    assert stored[0].payload["value"]["errors"][0]["code"] == 131000
    data["entry"][0]["changes"][0]["field"] = "account_update"
    assert signed(api, encode(data)).status_code == 200
    assert len(stored) == 1


@pytest.fixture(scope="module")
def inbox_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an empty, disposable PostgreSQL database")
    engine = create_engine(url, hide_parameters=True)
    assert not inspect(engine).get_table_names(), "Use an empty, disposable test database"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("DATABASE_URL", url)
        command.upgrade(config, "head")
        try:
            yield engine, url
        finally:
            command.downgrade(config, "base")
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            engine.dispose()


@pytest.fixture
def inbox_client(inbox_database):
    engine, url = inbox_database
    with Session(engine) as session, session.begin():
        session.execute(delete(WhatsAppInboxEvent))
    with TestClient(create_app(settings(database_url=url))) as client:
        yield client, engine


@pytest.mark.postgres
def test_retries_and_rebatched_messages_are_deduplicated_after_commit(inbox_client):
    client, engine = inbox_client
    original = payload("first", "second")
    assert signed(client, encode(original)).status_code == 200
    assert signed(client, encode(original)).status_code == 200
    assert signed(client, encode(payload("second", "third"))).status_code == 200
    with Session(engine) as session:
        rows = session.scalars(select(WhatsAppInboxEvent)).all()
        assert len(rows) == 3
        assert all(row.processed_at is not None for row in rows)
        assert all(row.created_at.tzinfo is not None for row in rows)
        assert {row.payload["value"]["messages"][0]["id"] for row in rows} == {
            "first",
            "second",
            "third",
        }


@pytest.mark.postgres
def test_concurrent_overlapping_batches_keep_one_copy(inbox_client):
    _, engine = inbox_client

    def receive(ids):
        with Session(engine) as session:
            InboxService(session).receive(parse_events(encode(payload(*ids)), WABA, PHONE_ID))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(receive, [("a", "b"), ("b", "a"), ("a", "c"), ("c", "b")]))
    with Session(engine) as session:
        assert len(session.scalars(select(WhatsAppInboxEvent)).all()) == 3


@pytest.mark.postgres
def test_partial_database_failure_rolls_back_batch_and_retry_succeeds(inbox_client, monkeypatch):
    client, engine = inbox_client
    original = InboxRepository.add
    calls = 0

    def fail_second(self, event):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OperationalError("synthetic failure", {}, Exception("unavailable"))
        original(self, event)

    with monkeypatch.context() as patch:
        patch.setattr(InboxRepository, "add", fail_second)
        assert signed(client, encode(payload("a", "b"))).status_code == 503
    with Session(engine) as session:
        assert session.scalars(select(WhatsAppInboxEvent)).all() == []
    assert signed(client, encode(payload("a", "b"))).status_code == 200
    with Session(engine) as session:
        assert len(session.scalars(select(WhatsAppInboxEvent)).all()) == 2


@pytest.mark.postgres
def test_invalid_later_entry_never_persists_earlier_message(inbox_client):
    client, engine = inbox_client
    data = payload("valid")
    invalid = copy.deepcopy(data["entry"][0])
    invalid["changes"][0]["value"]["messages"][0].pop("timestamp")
    data["entry"].append(invalid)
    assert signed(client, encode(data)).status_code == 400
    with Session(engine) as session:
        assert session.scalars(select(WhatsAppInboxEvent)).all() == []


@pytest.mark.postgres
def test_duplicate_statuses_preserve_each_delivery_transition(inbox_client):
    client, engine = inbox_client
    data = payload()
    value = data["entry"][0]["changes"][0]["value"]
    for status in ("read", "delivered", "sent", "read"):
        value["statuses"] = [{"id": "outbound-test", "status": status, "timestamp": "1794000000"}]
        assert signed(client, encode(data)).status_code == 200
    with Session(engine) as session:
        rows = session.scalars(select(WhatsAppInboxEvent)).all()
        assert len(rows) == 3
        assert {row.payload["value"]["statuses"][0]["status"] for row in rows} == {
            "sent",
            "delivered",
            "read",
        }


@pytest.fixture
def natural_worker(inbox_database, monkeypatch, request):
    engine, url = inbox_database
    with Session(engine) as session, session.begin():
        session.execute(delete(Message))
        session.execute(delete(Interaction))
        session.execute(delete(Conversation))
        session.execute(delete(WhatsAppInboxEvent))
        # Most cases exercise intake after the shared welcome; first-contact
        # cases explicitly request an empty conversation database below.
        if getattr(request, "param", "menu") == "menu":
            session.add(Conversation(whatsapp_number="15550000001", flow_step="menu", flow_data={}))
        actor = session.scalar(select(Account))
        actor = AccountView.model_validate(actor) if actor is not None else None
    if actor is None:
        with Session(engine, expire_on_commit=False) as session:
            actor = AccountService(session).bootstrap_admin(
                AccountCreate(
                    email="nl-worker@example.com",
                    display_name="Synthetic NL Admin",
                    role=Role.ADMIN,
                    password="synthetic-worker-password-123",
                )
            )
    with Session(engine) as session:
        AssistantPreferenceService(session).update(
            actor, AssistantPreferencesUpdate(natural_language_enabled=True)
        )
    model = Mock(
        extract=Mock(
            return_value=json.dumps(
                {
                    "intent": "quote",
                    "details": {
                        "event_date": "2027-12-20",
                        "guest_count": 20,
                        "location": "Alajuela",
                        "service_type": "parrilla",
                    },
                    "date_evidence": "20 de diciembre de 2027",
                }
            )
        )
    )
    outbound = []

    def meta(request):
        outbound.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": f"wamid.nl.{len(outbound)}"}]})

    config = settings(
        database_url=url,
        whatsapp_access_token=TOKEN,
        whatsapp_graph_api_version="v27.0",
        conversation_worker_enabled=True,
        api_public_base_url="https://example.com",
        conversation_processing_start_at=datetime.now(UTC) - timedelta(seconds=2),
    )
    # Execute ticks deterministically, with the exact same worker used in production.
    monkeypatch.setattr(ConversationWorker, "start", lambda self: None)
    monkeypatch.setattr(ConversationWorker, "stop", lambda self: None)
    with httpx.Client(transport=httpx.MockTransport(meta)) as http:
        app = create_app(
            config,
            meta_http=http,
            extractor=model,
            assistant_settings=AssistantSettings(
                app_env="test",
                natural_language_enabled=True,
                google_cloud_project="synthetic",
                google_cloud_location="global",
                gemini_model="synthetic",
                _env_file=None,
            ),
        )
        with TestClient(app) as client:
            yield SimpleNamespace(
                client=client,
                engine=engine,
                model=model,
                outbound=outbound,
                worker=app.state.conversation_worker,
                settings=config,
                actor=actor,
            )


def natural_payload(identifier="nl-first", *, body=None):
    data = payload(identifier)
    message = data["entry"][0]["changes"][0]["value"]["messages"][0]
    message["timestamp"] = str(int(datetime.now(UTC).timestamp()))
    message["text"]["body"] = (
        body or "Quiero parrillada para 20 personas el 20 de diciembre de 2027 en Alajuela."
    )
    return data


@pytest.mark.postgres
def test_live_webhook_commits_before_model_work_and_duplicate_delivery_does_not_repeat(
    natural_worker,
):
    state = natural_worker
    data = natural_payload()
    assert signed(state.client, encode(data)).status_code == 200
    assert signed(state.client, encode(data)).status_code == 200
    state.model.extract.assert_not_called()
    assert not state.outbound
    assert state.worker.tick()
    assert state.model.extract.call_count == 1
    assert len(state.outbound) == 1
    assert not state.worker.tick()
    with Session(state.engine) as session:
        conversation = session.scalar(select(Conversation))
        assert conversation.flow_step == "nl_review"
        assert conversation.flow_data["_nl_draft"]["guest_count"] == 20
        assert not conversation.flow_data.get("_nl_confirmed")
        assert (
            session.scalar(select(Message).where(Message.direction == "outbound")).delivery_status
            == "sent"
        )


@pytest.mark.postgres
@pytest.mark.parametrize("natural_worker", ["start"], indirect=True)
def test_paused_and_submitted_conversations_never_call_gemini(natural_worker):
    state = natural_worker
    with Session(state.engine) as session, session.begin():
        session.add(
            Conversation(
                whatsapp_number="15550000001", bot_paused=True, flow_step="menu", flow_data={}
            )
        )
    assert signed(state.client, encode(natural_payload())).status_code == 200
    state.worker.tick()
    state.model.extract.assert_not_called()
    assert not state.outbound
    with Session(state.engine) as session, session.begin():
        conversation = session.scalar(select(Conversation))
        conversation.bot_paused = False
        conversation.flow_step = "submitted"
    assert signed(state.client, encode(natural_payload("nl-after-close"))).status_code == 200
    state.worker.tick()
    state.model.extract.assert_not_called()
    assert not state.outbound
    assert (
        signed(
            state.client, encode(natural_payload("advisor-after-close", body="ASESOR"))
        ).status_code
        == 200
    )
    state.worker.tick()
    assert not state.outbound


@pytest.mark.postgres
def test_pending_outbound_is_recovered_without_repeating_model_after_worker_restart(natural_worker):
    state = natural_worker
    assert signed(state.client, encode(natural_payload())).status_code == 200
    with Session(state.engine) as session:
        service = ConversationService(session, assistant=state.worker.assistant)
        assert service.process_next(
            not_before=state.settings.conversation_processing_start_at,
            business_account_id=WABA,
            phone_number_id=PHONE_ID,
        )
    assert not state.outbound
    restarted = ConversationWorker(
        state.worker.session_factory,
        sender=state.worker.sender,
        assistant=state.worker.assistant,
        settings=state.settings,
    )
    assert restarted.tick()
    assert len(state.outbound) == 1
    assert state.model.extract.call_count == 1


@pytest.mark.postgres
def test_uncertain_send_pauses_conversation_and_is_never_retried(natural_worker):
    state = natural_worker
    state.worker.sender = Mock(side_effect=MetaSendError("unavailable"))
    assert signed(state.client, encode(natural_payload())).status_code == 200
    state.worker.tick()
    assert not state.worker.tick()
    assert state.worker.sender.call_count == 1
    with Session(state.engine) as session:
        assert session.scalar(select(Conversation)).bot_paused
        assert (
            session.scalar(select(Message).where(Message.direction == "outbound")).delivery_status
            == "uncertain"
        )


@pytest.mark.postgres
@pytest.mark.parametrize("natural_worker", ["start"], indirect=True)
def test_disabled_preference_and_unrecognized_channel_do_not_use_model(natural_worker):
    state = natural_worker
    with Session(state.engine) as session:
        AssistantPreferenceService(session).update(
            state.actor, AssistantPreferencesUpdate(natural_language_enabled=False)
        )
    assert signed(state.client, encode(natural_payload())).status_code == 200
    state.worker.tick()
    state.model.extract.assert_not_called()
    assert len(state.outbound) == 1  # guided greeting
    with Session(state.engine) as session:
        AssistantPreferenceService(session).update(
            state.actor, AssistantPreferencesUpdate(natural_language_enabled=True)
        )
    other = natural_payload("unknown-channel")
    other["entry"][0]["id"] = "999999"
    assert signed(state.client, encode(other)).status_code == 403
    # Re-check persisted routing too, independently of HTTP signature verification.
    event = parse_events(encode(natural_payload("stored-other")), WABA, PHONE_ID)[0]
    event.payload["business_account_id"] = "999999"
    with Session(state.engine) as session:
        InboxService(session).receive([event])
    state.worker.tick()
    state.model.extract.assert_not_called()
    assert len(state.outbound) == 1


@pytest.mark.postgres
def test_old_messages_and_crashed_sending_attempts_are_not_replayed(natural_worker):
    state = natural_worker
    old = natural_payload("old-message")
    old["entry"][0]["changes"][0]["value"]["messages"][0]["timestamp"] = "1000000000"
    assert signed(state.client, encode(old)).status_code == 200
    state.worker.tick()
    state.model.extract.assert_not_called()
    assert not state.outbound
    assert signed(state.client, encode(natural_payload())).status_code == 200
    with Session(state.engine) as session:
        service = ConversationService(session, assistant=state.worker.assistant)
        service.process_next(
            not_before=state.settings.conversation_processing_start_at,
            business_account_id=WABA,
            phone_number_id=PHONE_ID,
        )
    with Session(state.engine) as session, session.begin():
        message = session.scalar(select(Message).where(Message.direction == "outbound"))
        message.delivery_status = "sending"
    state.worker.tick()
    assert not state.outbound


@pytest.mark.postgres
def test_unconfigured_handoff_preserves_case_and_immediately_queues_new_welcome(natural_worker):
    state = natural_worker
    data = natural_payload(body="ASESOR")
    assert signed(state.client, encode(data)).status_code == 200
    state.worker.tick()
    assert len(state.outbound) == 1
    assert "no pudimos confirmar" in state.outbound[0]["text"]["body"]
    state.worker.tick()
    assert len(state.outbound) == 2
    assert state.outbound[1]["interactive"]["body"]["text"].startswith(GREETING)
    state.model.extract.assert_not_called()
    assert signed(state.client, encode(data)).status_code == 200
    assert not state.worker.tick()
    assert len(state.outbound) == 2
    with Session(state.engine) as session:
        cases = session.scalars(select(Interaction).order_by(Interaction.created_at)).all()
        assert len(cases) == 2
        assert cases[0].status == "referred" and cases[1].status == "active"
        assert cases[0].reference != cases[1].reference
        assert not session.scalar(select(Conversation)).bot_paused
        notice = session.scalar(select(Message).where(Message.purpose == "advisor_notification"))
        assert notice.delivery_status == "failed"
    assert signed(state.client, encode(natural_payload("after-handoff"))).status_code == 200
    state.worker.tick()
    assert state.model.extract.call_count == 1
    assert len(state.outbound) == 3


@pytest.mark.postgres
def test_concurrent_workers_prepare_and_send_one_reply(natural_worker):
    state = natural_worker
    assert signed(state.client, encode(natural_payload())).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: state.worker.tick(), range(2)))
    state.worker.tick()
    assert state.model.extract.call_count == 1
    assert len(state.outbound) == 1


@pytest.mark.postgres
def test_customer_confirmation_is_persisted_and_closed_requests_stay_closed(natural_worker):
    state = natural_worker
    assert signed(state.client, encode(natural_payload())).status_code == 200
    state.worker.tick()
    data = natural_payload("nl-confirm")
    message = data["entry"][0]["changes"][0]["value"]["messages"][0]
    message.pop("text")
    message.update(
        type="interactive",
        interactive={"button_reply": {"id": "nl_confirm", "title": "Confirmar datos"}},
    )
    assert signed(state.client, encode(data)).status_code == 200
    state.worker.tick()
    with Session(state.engine) as session:
        conversation = session.scalar(select(Conversation))
        assert conversation.flow_step == "submitted"
        assert conversation.flow_data["_nl_confirmed"] is True
        assert conversation.flow_data["guest_count"] == 20
    assert len(state.outbound) == 2
    assert state.model.extract.call_count == 1
    assert signed(state.client, encode(natural_payload("after-confirmation"))).status_code == 200
    state.worker.tick()
    assert len(state.outbound) == 2
    assert state.model.extract.call_count == 1


@pytest.mark.postgres
def test_human_pause_cancels_a_reply_prepared_before_pause(natural_worker):
    state = natural_worker
    assert signed(state.client, encode(natural_payload())).status_code == 200
    with Session(state.engine) as session:
        service = ConversationService(session, assistant=state.worker.assistant)
        service.process_next(
            not_before=state.settings.conversation_processing_start_at,
            business_account_id=WABA,
            phone_number_id=PHONE_ID,
        )
    with Session(state.engine) as session, session.begin():
        session.scalar(select(Conversation)).bot_paused = True
    state.worker.tick()
    assert not state.outbound
    with Session(state.engine) as session:
        assert (
            session.scalar(select(Message).where(Message.direction == "outbound")).delivery_status
            == "cancelled"
        )


@pytest.mark.postgres
def test_side_questions_keep_live_draft_active_and_advisor_requires_explicit_selection(
    natural_worker,
):
    state = natural_worker
    assert signed(state.client, encode(natural_payload())).status_code == 200
    state.worker.tick()
    with Session(state.engine) as session:
        original = dict(session.scalar(select(Conversation)).flow_data)
    state.model.extract.return_value = json.dumps({"intent": "unsupported", "details": {}})
    assert (
        signed(state.client, encode(natural_payload("side-hour", body="¿Qué hora es?"))).status_code
        == 200
    )
    state.worker.tick()
    with Session(state.engine) as session:
        saved = session.scalar(select(Conversation))
        assert not saved.bot_paused
        assert saved.flow_step == "nl_review"
        assert saved.flow_data == original
    assert len(state.outbound) == 2
    state.model.extract.return_value = json.dumps(
        {
            "intent": "business_question",
            "topic": "menu",
            "details": {},
        }
    )
    assert (
        signed(
            state.client, encode(natural_payload("side-menu", body="¿Qué carnes ofrecen?"))
        ).status_code
        == 200
    )
    state.worker.tick()
    assert "Lomito" in state.outbound[-1]["interactive"]["body"]["text"]
    calls_before = state.model.extract.call_count
    for identifier, button in [("side-continue", "nl_continue"), ("side-advisor", "nl_advisor")]:
        data = natural_payload(identifier)
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        message.pop("text")
        message.update(type="interactive", interactive={"button_reply": {"id": button}})
        assert signed(state.client, encode(data)).status_code == 200
        state.worker.tick()
        with Session(state.engine) as session:
            saved = session.scalar(select(Conversation))
            assert not saved.bot_paused
            if button == "nl_advisor":
                previous = session.scalar(
                    select(Interaction).where(Interaction.status == "referred")
                )
                assert previous.snapshot["_nl_draft"] == original["_nl_draft"]
                assert "_nl_draft" not in saved.flow_data
            else:
                assert saved.flow_data["_nl_draft"] == original["_nl_draft"]
    assert state.model.extract.call_count == calls_before
    state.worker.tick()
    assert len(state.outbound) == 6


@pytest.mark.postgres
@pytest.mark.parametrize("natural_worker", ["start"], indirect=True)
@pytest.mark.parametrize("next_action", ["text", "button"])
def test_natural_language_sends_shared_branded_welcome_then_accepts_intake(
    natural_worker, next_action
):
    state = natural_worker
    greeting = natural_payload("welcome", body="hola")
    assert signed(state.client, encode(greeting)).status_code == 200
    state.worker.tick()
    state.model.extract.assert_not_called()
    assert len(state.outbound) == 1
    first = state.outbound[0]["interactive"]
    assert first["body"]["text"].startswith(GREETING + "\n\nCódigo de interacción: PEC-")
    assert first["header"] == {
        "type": "image",
        "image": {"link": "https://example.com/assets/welcome_header.jpg"},
    }
    assert [
        (button["reply"]["id"], button["reply"]["title"]) for button in first["action"]["buttons"]
    ] == list(MENU_BUTTONS)
    assert signed(state.client, encode(greeting)).status_code == 200
    assert not state.worker.tick()
    assert len(state.outbound) == 1
    if next_action == "button":
        data = natural_payload("welcome-quote-button")
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        message.pop("text")
        message.update(type="interactive", interactive={"button_reply": {"id": "request_quote"}})
        assert signed(state.client, encode(data)).status_code == 200
        state.worker.tick()
        state.model.extract.assert_not_called()
    assert signed(state.client, encode(natural_payload("after-welcome"))).status_code == 200
    state.worker.tick()
    assert state.model.extract.call_count == 1
    with Session(state.engine) as session:
        conversation = session.scalar(select(Conversation))
        assert conversation.flow_step == "nl_review"
        assert conversation.flow_data["_nl_draft"]["guest_count"] == 20
        assert not conversation.bot_paused


def configure_advisor(state):
    from parrilladas.modules.assistant.schemas import AdvisorSettings

    with Session(state.engine) as session:
        AssistantPreferenceService(session).update_advisor(
            state.actor,
            AdvisorSettings(
                enabled=True,
                name="Synthetic Advisor",
                phone="+15550000009",
                template="consulta_para_asesor",
                language="es",
            ),
        )


def drain_worker(state):
    for _ in range(8):
        if not state.worker.tick():
            return
    raise AssertionError("Outbox did not drain")


@pytest.mark.postgres
def test_advisor_template_then_ack_then_new_welcome_preserve_case_and_reject_stale_buttons(
    natural_worker,
):
    state = natural_worker
    configure_advisor(state)
    assert signed(state.client, encode(natural_payload())).status_code == 200
    state.worker.tick()
    with Session(state.engine) as session:
        old = session.scalar(select(Interaction))
        old_id, old_ref = old.id, old.reference
        origin = session.scalar(select(Message).where(Message.direction == "outbound"))
        origin_id = origin.external_message_id
    data = natural_payload("advisor-selected")
    message = data["entry"][0]["changes"][0]["value"]["messages"][0]
    message.pop("text")
    message.update(
        type="interactive",
        context={"id": origin_id},
        interactive={"button_reply": {"id": "nl_advisor"}},
    )
    assert signed(state.client, encode(data)).status_code == 200
    state.worker.tick()
    template = state.outbound[1]
    assert template["type"] == "template" and template["to"] == "15550000009"
    assert template["template"]["name"] == "consulta_para_asesor"
    parameters = template["template"]["components"][0]["parameters"]
    assert parameters[0]["text"] == old_ref
    assert parameters[1]["text"] == "+15550000001"
    assert "Personas: 20" in parameters[2]["text"]
    state.worker.tick()
    assert old_ref in state.outbound[2]["text"]["body"]
    assert "Enviamos tu consulta" in state.outbound[2]["text"]["body"]
    state.worker.tick()
    assert state.outbound[3]["interactive"]["body"]["text"].startswith(GREETING)
    with Session(state.engine) as session:
        archived = session.get(Interaction, old_id)
        following = session.scalar(select(Interaction).where(Interaction.status == "active"))
        assert archived.status == "referred"
        assert archived.snapshot["_nl_draft"]["guest_count"] == 20
        assert following.reference != old_ref
        assert following.reference in state.outbound[3]["interactive"]["body"]["text"]
        assert following.snapshot == {"request_reference": following.reference}
        conversation = session.scalar(select(Conversation))
        assert conversation.flow_step == "menu" and not conversation.bot_paused
        notices = session.scalars(
            select(Message).where(Message.purpose == "advisor_notification")
        ).all()
        assert len(notices) == 1 and notices[0].interaction_id == old_id
    assert signed(state.client, encode(data)).status_code == 200
    assert not state.worker.tick()
    # A new provider delivery of an old interaction's button cannot notify again.
    message["id"] = "stale-advisor-button"
    assert signed(state.client, encode(data)).status_code == 200
    drain_worker(state)
    assert len(state.outbound) == 4
    assert state.model.extract.call_count == 1


@pytest.mark.postgres
@pytest.mark.parametrize(
    "category,expected", [("access_denied", "failed"), ("unavailable", "uncertain")]
)
def test_advisor_send_failure_is_visible_and_does_not_block_new_interaction(
    natural_worker, category, expected
):
    state = natural_worker
    configure_advisor(state)
    original_sender = state.worker.sender
    attempts = []

    def send(action):
        if action.purpose == "advisor_notification":
            attempts.append(action)
            raise MetaSendError(category)
        return original_sender(action)

    state.worker.sender = send
    assert (
        signed(state.client, encode(natural_payload("failed-notice", body="ASESOR"))).status_code
        == 200
    )
    drain_worker(state)
    assert len(attempts) == 1
    assert len(state.outbound) == 2
    assert "no pudimos confirmar" in state.outbound[0]["text"]["body"]
    assert "Enviamos tu consulta" not in state.outbound[0]["text"]["body"]
    with Session(state.engine) as session:
        row = session.scalar(select(Message).where(Message.purpose == "advisor_notification"))
        assert row.delivery_status == expected
        assert not session.scalar(select(Conversation)).bot_paused
    assert signed(state.client, encode(natural_payload("new-after-failure"))).status_code == 200
    drain_worker(state)
    assert len(attempts) == 1
    assert state.model.extract.call_count == 1
    with Session(state.engine) as session:
        report = AssistantPreferenceService(session).get_advisor(state.actor)
        assert report.notifications[0].status == expected


@pytest.mark.postgres
def test_interrupted_advisor_send_recovers_with_honest_ack_without_resending(natural_worker):
    state = natural_worker
    configure_advisor(state)
    assert (
        signed(state.client, encode(natural_payload("crash-advisor", body="ASESOR"))).status_code
        == 200
    )
    with Session(state.engine) as session:
        service = ConversationService(
            session, state.worker.sender, assistant=state.worker.assistant
        )
        assert service.process_next(
            not_before=state.settings.conversation_processing_start_at,
            business_account_id=WABA,
            phone_number_id=PHONE_ID,
        )
    with Session(state.engine) as session, session.begin():
        row = session.scalar(select(Message).where(Message.purpose == "advisor_notification"))
        row.delivery_status = "sending"
        row.attempted_at = datetime.now(UTC) - timedelta(seconds=61)
    drain_worker(state)
    assert len(state.outbound) == 2
    assert all(payload["type"] != "template" for payload in state.outbound)
    assert "no pudimos confirmar" in state.outbound[0]["text"]["body"]


@pytest.mark.postgres
def test_advisor_delivery_webhooks_update_status_without_regression(natural_worker):
    state = natural_worker
    configure_advisor(state)
    assert (
        signed(state.client, encode(natural_payload("status-advisor", body="ASESOR"))).status_code
        == 200
    )
    drain_worker(state)
    with Session(state.engine) as session:
        notification = session.scalar(
            select(Message).where(Message.purpose == "advisor_notification")
        )
        external = notification.external_message_id
    for status in ["delivered", "sent", "read", "failed"]:
        data = natural_payload("status-event")
        value = data["entry"][0]["changes"][0]["value"]
        value.pop("messages")
        value["statuses"] = [
            {"id": external, "status": status, "timestamp": str(int(datetime.now(UTC).timestamp()))}
        ]
        assert signed(state.client, encode(data)).status_code == 200
        drain_worker(state)
    with Session(state.engine) as session:
        report = AssistantPreferenceService(session).get_advisor(state.actor)
        assert report.notifications[0].status == "read"
    assert len(state.outbound) == 3


@pytest.mark.postgres
def test_reply_to_internal_advisor_notice_never_creates_a_customer_request(natural_worker):
    state = natural_worker
    configure_advisor(state)
    assert (
        signed(
            state.client, encode(natural_payload("notify-before-reply", body="ASESOR"))
        ).status_code
        == 200
    )
    drain_worker(state)
    with Session(state.engine) as session:
        notification = session.scalar(
            select(Message).where(Message.purpose == "advisor_notification")
        )
        context_id = notification.external_message_id
    data = natural_payload("advisor-reply", body="recibido")
    message = data["entry"][0]["changes"][0]["value"]["messages"][0]
    message["from"] = "15550000009"
    message["context"] = {"id": context_id}
    assert signed(state.client, encode(data)).status_code == 200
    drain_worker(state)
    assert len(state.outbound) == 3
    state.model.extract.assert_not_called()


def test_template_adapter_sends_only_the_configured_body_parameters():
    def meta(request):
        data = json.loads(request.content)
        assert data["type"] == "template" and data["to"] == "15550000009"
        assert data["template"] == {
            "name": "consulta_para_asesor",
            "language": {"code": "es"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": value}
                        for value in ("PEC-SYNTHETIC", "+15550000001", "Personas: 20")
                    ],
                }
            ],
        }
        return httpx.Response(200, json={"messages": [{"id": "wamid.synthetic-template"}]})

    with httpx.Client(transport=httpx.MockTransport(meta)) as http:
        result = MetaClient(http).send_template(
            version="v27.0",
            phone_id=PHONE_ID,
            token=TOKEN,
            recipient="15550000009",
            name="consulta_para_asesor",
            language="es",
            parameters=("PEC-SYNTHETIC", "+15550000001", "Personas: 20"),
        )
    assert result == "wamid.synthetic-template"


@pytest.mark.postgres
def test_partial_date_and_year_follow_up_survive_separate_worker_ticks(natural_worker):
    state = natural_worker
    data = natural_payload("partial-date-start")
    message = data["entry"][0]["changes"][0]["value"]["messages"][0]
    message.pop("text")
    message.update(type="interactive", interactive={"button_reply": {"id": "nl_continue"}})
    assert signed(state.client, encode(data)).status_code == 200
    state.worker.tick()
    partial = natural_payload("partial-date", body="Diciembre 12")
    assert signed(state.client, encode(partial)).status_code == 200
    state.worker.tick()
    assert "¿De qué año sería el 12 de diciembre?" in state.outbound[-1]["text"]["body"]
    with Session(state.engine) as session:
        saved = session.scalar(select(Conversation))
        assert saved.flow_data["_nl_date_parts"] == {"day": 12, "month": 12}
        reference = saved.flow_data["request_reference"]
    assert signed(state.client, encode(partial)).status_code == 200
    assert not state.worker.tick()
    assert (
        signed(state.client, encode(natural_payload("date-year", body="2027"))).status_code == 200
    )
    state.worker.tick()
    assert "¿Para cuántas personas" in state.outbound[-1]["text"]["body"]
    with Session(state.engine) as session:
        saved = session.scalar(select(Conversation))
        assert saved.flow_data["_nl_draft"]["event_date"] == "2027-12-12"
        assert saved.flow_data["request_reference"] == reference
        assert not saved.bot_paused and saved.flow_step == "nl_collect"
    state.model.extract.assert_not_called()
