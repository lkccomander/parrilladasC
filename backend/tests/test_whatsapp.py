import copy
import hashlib
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
from parrilladas.modules.conversations.models import WhatsAppInboxEvent
from parrilladas.modules.conversations.repository import InboxRepository
from parrilladas.modules.conversations.service import InboxService

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
