# WhatsApp Guided Quote Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the Beta 1.00 WhatsApp demo flow that greets a new customer once, offers three options, and guides `Solicitar cotización` through five questions and a confirmation.

**Architecture:** Keep webhook validation and routing in `integrations/whatsapp/router.py`, move conversation state transitions into `modules/conversations`, and keep Meta HTTP payloads inside `integrations/whatsapp/client.py`. Persist the inbound event and conversation/message state before sending; use stable event keys and conversation state to prevent duplicate greetings or repeated transitions.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, PostgreSQL, Alembic, Pydantic, httpx, Meta WhatsApp Cloud API, pytest.

## Global Constraints

- No AI, automatic pricing, or automatic availability confirmation in Beta 1.00.
- `Solicitar cotización` is active; `Ver servicios` and `Hablar con un asesor` return “disponible próximamente” responses.
- The quote flow asks type of event, date, location, guest count, and service in that order.
- `ASESOR` must remain a safe human handoff signal.
- Verify Meta signatures against the raw body before processing any event.
- Do not log access tokens, app secrets, customer message bodies, or phone numbers beyond the existing safe diagnostic fields.
- Keep the API as the only service with database credentials and live WhatsApp credentials.
- Use timezone-aware timestamps and explicit transactions; never use `create_all`.
- Run `ruff check backend`, `ruff format --check backend`, `pytest backend/tests`, and `python -m pip check` before handoff.

---

## File Map

- Modify `backend/src/parrilladas/integrations/whatsapp/client.py`: add authenticated outbound Meta message methods for text, image, and interactive reply buttons.
- Modify `backend/src/parrilladas/modules/conversations/contracts.py`: define typed inbound message and bot action contracts.
- Modify `backend/src/parrilladas/modules/conversations/models.py`: add the minimum persisted state needed to identify a customer conversation and its current flow step; preserve existing message and inbox event tables.
- Modify `backend/src/parrilladas/modules/conversations/repository.py`: add transaction-safe conversation/message queries and insert helpers.
- Create `backend/src/parrilladas/modules/conversations/flow.py`: pure state-machine decisions and exact Spanish copy for the Beta flow.
- Modify `backend/src/parrilladas/modules/conversations/service.py`: persist inbound messages, select the next action, and coordinate outbound delivery after persistence.
- Modify `backend/src/parrilladas/integrations/whatsapp/router.py`: pass verified message events to the conversation service while preserving signature, account, and fast-ack behavior.
- Modify `backend/src/parrilladas/integrations/whatsapp/webhook.py`: normalize text and interactive button replies into the conversation contract without logging customer content.
- Modify `backend/src/parrilladas/main.py` and `Dockerfile`: serve the approved greeting image from the API’s public `/assets` path and package it into the image.
- Create `backend/migrations/versions/0004_guided_quote_flow.py` only if the existing schema needs a new column/table after the model review.
- Modify `backend/tests/test_whatsapp.py`: cover outbound payloads, signature/account rejection, first-message idempotency, and safe fallback behavior.
- Create `backend/tests/test_conversations.py`: cover the pure flow state machine and transition copy without network or database dependencies.
- Modify `proyect_brain/PROJECT_ROADMAP.md`: mark only the completed Beta demo items after tests and a real Meta test succeed.

## Interfaces

The implementation must expose these small interfaces so the components remain testable:

```python
class MetaClient:
    def send_text(self, *, version: str, phone_id: str, token: str, recipient: str, body: str) -> str: ...
    def send_image(self, *, version: str, phone_id: str, token: str, recipient: str, image_url: str, caption: str) -> str: ...
    def send_buttons(self, *, version: str, phone_id: str, token: str, recipient: str, body: str, buttons: list[tuple[str, str]]) -> str: ...

class ConversationService:
    def receive(self, events: list[InboxEvent]) -> None: ...
```

The methods return Meta’s outbound message ID and raise a provider-specific safe error containing only status/category, never response bodies or credentials.

---

### Task 1: Add and test the outbound Meta adapter

**Files:**
- Modify: `backend/src/parrilladas/integrations/whatsapp/client.py`
- Test: `backend/tests/test_whatsapp.py`

- [ ] **Step 1: Write failing tests for request shape**

Add MockTransport tests that assert:

```python
assert request.method == "POST"
assert request.url.path == f"/v27.0/{PHONE_ID}/messages"
assert request.headers["Authorization"] == f"Bearer {TOKEN}"
assert request.json() == {
    "messaging_product": "whatsapp",
    "to": RECIPIENT,
    "type": "text",
    "text": {"body": "Hola"},
}
```

Add equivalent assertions for an image payload with a public HTTPS `link` and for interactive reply buttons with `reply.id` and `reply.title`.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_whatsapp.py -k "send_text or send_image or send_buttons" -q
```

Expected: FAIL because the three methods do not exist.

- [ ] **Step 3: Implement the smallest outbound client**

Use one private helper that POSTs to `https://graph.facebook.com/{version}/{phone_id}/messages` with the bearer token and JSON content type. Parse only a string `messages[0].id`; classify non-2xx and malformed responses into a safe exception. Do not include response text in the exception or logs.

Use these payloads:

```python
{"messaging_product": "whatsapp", "to": recipient, "type": "text", "text": {"body": body}}
{"messaging_product": "whatsapp", "to": recipient, "type": "image", "image": {"link": image_url, "caption": caption}}
{
    "messaging_product": "whatsapp", "to": recipient, "type": "interactive",
    "interactive": {
        "type": "button", "body": {"text": body},
        "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": title}} for i, title in buttons]},
    },
}
```

- [ ] **Step 4: Run the focused tests**

Run the command from Step 2. Expected: all outbound payload tests pass, including timeout and malformed-response safety tests.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/parrilladas/integrations/whatsapp/client.py backend/tests/test_whatsapp.py
git commit -m "Add WhatsApp outbound message adapter"
```

### Task 2: Make the greeting asset deployable and test its public URL

**Files:**
- Modify: `backend/src/parrilladas/main.py`
- Modify: `Dockerfile`
- Include: `assets/greeting-grill.png`
- Test: `backend/tests/test_app.py`

- [ ] **Step 1: Confirm the existing asset test is failing or absent**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_app.py -k greeting_asset -q
```

Expected before the route/image is committed: the test is absent or the asset request does not return `200 image/png`.

- [ ] **Step 2: Keep the public asset route narrow**

Mount only the repository `assets` directory at `/assets` and copy only that directory in the image:

```python
ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets"
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
```

The greeting URL must be formed from `API_PUBLIC_BASE_URL`, never from a private Railway hostname.

- [ ] **Step 3: Run the asset test**

Assert `GET /assets/greeting-grill.png` returns `200`, `content-type` begins with `image/png`, and the first eight bytes equal the PNG signature.

- [ ] **Step 4: Commit**

```powershell
git add assets/greeting-grill.png Dockerfile backend/src/parrilladas/main.py backend/tests/test_app.py
git commit -m "Package WhatsApp greeting asset"
```

### Task 3: Add the pure Beta conversation state machine

**Files:**
- Modify: `backend/src/parrilladas/modules/conversations/contracts.py`
- Create: `backend/src/parrilladas/modules/conversations/flow.py`
- Test: `backend/tests/test_conversations.py`

- [ ] **Step 1: Write failing pure tests**

Cover these exact transitions:

```python
assert decide("start", IncomingText("hola")).step == "menu"
assert decide("menu", ButtonReply("quote")).step == "event_type"
assert decide("menu", ButtonReply("services")).text == "Esta opción estará disponible próximamente."
assert decide("menu", ButtonReply("advisor")).text == "Un asesor podrá ayudarte próximamente. Escribe ASESOR si necesitas atención."
assert decide("event_type", IncomingText("corporativo")).step == "event_date"
assert decide("event_date", IncomingText("15 de diciembre")).step == "location"
assert decide("location", IncomingText("Zona 10")).step == "guest_count"
assert decide("guest_count", IncomingText("80")).step == "service_type"
assert decide("service_type", IncomingText("parrillada")).step == "summary"
assert decide("summary", ButtonReply("confirm")).step == "submitted"
assert decide("menu", IncomingText("ASESOR")).handoff is True
```

Also test invalid input returns a safe prompt without changing the current step.

- [ ] **Step 2: Run the tests and verify they fail**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_conversations.py -q
```

Expected: FAIL because the contracts and decision function are not present.

- [ ] **Step 3: Implement pure contracts and decisions**

Use immutable dataclasses for `IncomingText`, `ButtonReply`, and `FlowDecision`. Keep all Spanish copy in `flow.py`. The decision function must accept the current step and one normalized input and return the next step, reply actions, and captured field updates. It must not access SQL, HTTP, environment variables, or clocks.

- [ ] **Step 4: Run the tests**

Expected: all state-machine tests pass with no network or database access.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/parrilladas/modules/conversations/contracts.py backend/src/parrilladas/modules/conversations/flow.py backend/tests/test_conversations.py
git commit -m "Add guided quote conversation state machine"
```

### Task 4: Persist conversation state and process first messages

**Files:**
- Modify: `backend/src/parrilladas/modules/conversations/models.py`
- Modify: `backend/src/parrilladas/modules/conversations/repository.py`
- Modify: `backend/src/parrilladas/modules/conversations/service.py`
- Create if required: `backend/migrations/versions/0004_guided_quote_flow.py`
- Test: `backend/tests/test_whatsapp.py`

- [ ] **Step 1: Write failing database-backed tests**

Using the disposable PostgreSQL fixture, verify:

```python
first = service.receive(events_for("customer-1", "message-1"))
retry = service.receive(events_for("customer-1", "message-1"))
assert count_messages("customer-1") == 1
assert count_outbound_actions("customer-1") == 1
```

Verify a second unique message continues the saved flow step, and verify `bot_paused=True` creates no outbound action.

- [ ] **Step 2: Run the focused tests and verify they fail**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_whatsapp.py -m postgres -k "conversation or first_message" -q
```

Expected: FAIL because there is no conversation processor or outbound action persistence.

- [ ] **Step 3: Implement repository and service boundaries**

Add repository methods that:

- find or create one `Conversation` by WhatsApp number;
- add one inbound `Message` by external provider ID;
- update `flow_step` and captured quote fields in one transaction;
- record an outbound `Message` with `pending`, `sent`, or `failed` delivery status.

The service must check the inbox event’s stable key before executing a transition. It must persist the inbound message and the next flow step before invoking Meta. A duplicate event must return without invoking Meta again.

- [ ] **Step 4: Add the migration only for schema differences**

If the existing `Conversation` table lacks fields required to hold the five captured answers, add nullable typed columns with a reviewed Alembic migration and register nothing through `create_all`. If existing columns can hold the state without ambiguity, do not add a migration.

- [ ] **Step 5: Run the focused database tests**

Expected: first-message processing is idempotent, flow state survives a new service instance, paused conversations do not send, and failed outbound delivery is marked `failed` without exposing provider content.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/parrilladas/modules/conversations backend/migrations/versions/0004_guided_quote_flow.py backend/tests/test_whatsapp.py
git commit -m "Persist guided WhatsApp conversation state"
```

### Task 5: Connect verified webhook events to the conversation processor

**Files:**
- Modify: `backend/src/parrilladas/integrations/whatsapp/webhook.py`
- Modify: `backend/src/parrilladas/integrations/whatsapp/router.py`
- Modify: `backend/src/parrilladas/integrations/whatsapp/client.py`
- Test: `backend/tests/test_whatsapp.py`

- [ ] **Step 1: Write failing end-to-end handler tests**

Use a signed synthetic payload and MockTransport. Assert:

```python
response = client.post("/webhooks/whatsapp", content=raw_body, headers=signed_headers)
assert response.status_code == 200
assert len(meta_calls) == 1
assert meta_calls[0].json()["type"] == "interactive"
```

Add tests for a button reply with `interactive.button_reply.id`, duplicate delivery, invalid signature, account mismatch, and status-only events.

- [ ] **Step 2: Run the tests and verify the new behavior fails**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_whatsapp.py -k "guided or webhook_reply" -q
```

Expected: inbound requests still only persist the inbox event and produce no Meta call.

- [ ] **Step 3: Normalize message inputs**

Extend the webhook models to expose only the fields needed by the flow: external message ID, sender WhatsApp number, text body, and interactive reply ID/title. Keep raw payload persistence for audit, but do not log it.

- [ ] **Step 4: Wire the service after verification and persistence**

Keep this order in `receive_webhook`:

```python
events = parse_events(raw, settings.whatsapp_business_account_id, settings.whatsapp_phone_number_id)
InboxService(session).receive(events)
ConversationService(session, MetaClient(httpx.Client(...)), settings).process(events)
return {"status": "ok"}
```

Use the existing dependency/client lifetime pattern rather than creating a new unrestricted client per event. Preserve `401` for signature failures, `403` for account mismatches, and `503` for durable storage failures.

- [ ] **Step 5: Implement greeting action construction**

For the first customer text, send the public image with the approved greeting and three buttons. If image sending raises the safe outbound error, send the text-only greeting plus the same options. `Ver servicios` and `Hablar con un asesor` are text-only placeholders until their future flows are implemented.

- [ ] **Step 6: Run the focused webhook tests**

Expected: one first-message greeting, no duplicate greeting on retry, correct button payloads, safe fallback, and no response for status events.

- [ ] **Step 7: Commit**

```powershell
git add backend/src/parrilladas/integrations/whatsapp backend/tests/test_whatsapp.py
git commit -m "Connect WhatsApp webhook to guided quote flow"
```

### Task 6: Validate, update roadmap, and run the real Meta demo

**Files:**
- Modify: `proyect_brain/PROJECT_ROADMAP.md`
- Test: existing backend test suite

- [ ] **Step 1: Run all required checks**

```powershell
ruff check backend
ruff format --check backend
.venv\Scripts\python.exe -m pytest backend/tests
.venv\Scripts\python.exe -m pip check
```

Expected: all checks pass; PostgreSQL tests use only the disposable `TEST_DATABASE_URL` database.

- [ ] **Step 2: Confirm deployment configuration without printing secrets**

Verify Railway has the existing WhatsApp credentials, `API_PUBLIC_BASE_URL`, and `WHATSAPP_GRAPH_API_VERSION`; inspect only variable names and safe status, never values.

- [ ] **Step 3: Deploy and verify health**

Push the implementation commits to `main`, wait for GitHub Actions and Railway autodeploy, then confirm `GET /health/ready` returns `200`.

- [ ] **Step 4: Run the controlled Meta test**

Send one new message from the verified test recipient, then confirm Railway logs show one `POST /webhooks/whatsapp 200 OK` and one outbound Graph API `POST` without exposing request headers or bodies. Confirm the customer receives the image, greeting, and buttons.

- [ ] **Step 5: Update the roadmap only after the real test**

Mark the implemented Beta items as complete: first greeting, guided quote questions, confirmation response, and real WhatsApp flow test. Leave leads, human inbox, manual sending, PDF, pricing, and reminders unchecked.

- [ ] **Step 6: Commit and push the final documentation update**

```powershell
git add proyect_brain/PROJECT_ROADMAP.md
git commit -m "Document Beta WhatsApp guided flow validation"
git push origin main
```

## Verification and rollback

If Meta delivery fails, keep the inbound event and mark the outbound message `failed`; do not return a false success for a storage failure. The rollback point is the last commit before Task 5, which preserves verified webhook intake and inbox persistence without automatic customer replies.
