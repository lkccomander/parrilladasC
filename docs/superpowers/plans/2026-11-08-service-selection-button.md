# Service Selection Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a WhatsApp `Parrilla` button to the quote flow and restart a conversation after three consecutive invalid replies.

**Architecture:** Keep decisions in the pure conversation flow. Pass the persisted `flow_data` into the decision function so the invalid-attempt counter survives retries and restarts; use a `reset` flag on `FlowDecision` so `ConversationService` can clear collected data atomically before showing the greeting menu again. Reuse the existing `OutboundAction.buttons` and Meta interactive-button sender.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, Pydantic, pytest, Ruff, WhatsApp Cloud API interactive reply buttons.

## Global Constraints

- Keep business rules in `backend/src/parrilladas/modules/conversations`, not in the webhook router or Meta adapter.
- Preserve explicit transaction boundaries and inbox idempotency.
- Do not add a database migration; store only the fallback counter in the existing JSON `conversations.flow_data` field.
- Do not log tokens, secrets, customer message bodies, or phone numbers.
- Keep prices manual and do not add automatic customer messages beyond the approved flow.

---

### Task 1: Extend the pure flow decision contract

**Files:**
- Modify: `backend/src/parrilladas/modules/conversations/contracts.py`
- Modify: `backend/src/parrilladas/modules/conversations/flow.py`
- Test: `backend/tests/test_conversations.py`

**Interfaces:**
- `decide(step: str, incoming: IncomingText | ButtonReply, *, flow_data: Mapping[str, object] | None = None) -> FlowDecision`
- `FlowDecision.reset: bool` defaults to `False`.
- The service-flow button is exactly `("service_parrilla", "Parrilla")`.

- [ ] **Step 1: Write failing tests for the button and invalid counter**

Add tests covering the approved behavior:

```python
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


def test_valid_reply_clears_invalid_counter():
    decision = decide(
        "service_type", ButtonReply("service_parrilla"), flow_data={"_invalid_attempts": 2}
    )

    assert decision.updates["_invalid_attempts"] == 0
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_conversations.py -q
```

Expected: failures because `FlowDecision` has no `reset` field, `decide` does not accept `flow_data`, and the service button is not implemented.

- [ ] **Step 3: Implement the minimal pure-flow changes**

Add `reset: bool = False` to `FlowDecision`. Add the keyword-only `flow_data` argument to `decide`, define:

```python
SERVICE_BUTTONS = (("service_parrilla", "Parrilla"),)
INVALID_ATTEMPTS_KEY = "_invalid_attempts"
```

When `guest_count` receives valid text, return the `service_type` prompt with `SERVICE_BUTTONS`. At `service_type`, accept only `ButtonReply("service_parrilla")`, update `service_type` to `parrilla` and the counter to `0`, and advance to `summary`. For invalid input, increment the counter; return the same step with the service prompt and button until the count reaches three. On the third invalid reply, return the greeting, `MENU_BUTTONS`, step `menu`, `reset=True`, and no customer data updates. Apply the same counter behavior to other invalid fallbacks without changing valid transitions.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run the same pytest command. Expected: all conversation-flow tests pass.

- [ ] **Step 5: Commit the pure-flow change**

```powershell
git add backend/src/parrilladas/modules/conversations/contracts.py backend/src/parrilladas/modules/conversations/flow.py backend/tests/test_conversations.py
git commit -m "Add Parrilla service button to quote flow"
```

### Task 2: Persist and apply the reset atomically

**Files:**
- Modify: `backend/src/parrilladas/modules/conversations/service.py`
- Test: `backend/tests/test_conversations.py` or `backend/tests/test_whatsapp.py`

**Interfaces:**
- `ConversationService._prepare` remains the transaction boundary.
- `ConversationService` passes `conversation.flow_data` to `decide`.

- [ ] **Step 1: Add a service-level regression test**

Use the existing disposable database fixture pattern to verify that a message producing `reset=True` changes the stored conversation to `flow_step == "menu"` and `flow_data == {}` while still creating exactly one outbound action.

- [ ] **Step 2: Run the regression test and verify it fails**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_whatsapp.py -k reset -q
```

Expected: failure because the service currently does not pass `flow_data` or clear it when a decision requests a reset.

- [ ] **Step 3: Implement the transaction update**

Change the decision call to:

```python
decision = decide(conversation.flow_step, incoming, flow_data=conversation.flow_data)
if decision.reset:
    conversation.flow_data = {}
else:
    conversation.flow_data = {
        **(conversation.flow_data or {}),
        **dict(decision.updates),
    }
conversation.flow_step = decision.step
```

For non-reset decisions, keep the existing collected quote fields and apply the decision updates. For reset decisions, persist an empty JSON object and the new `menu` step in the same transaction before creating the outbound message record.

- [ ] **Step 4: Run the regression and full conversation tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_conversations.py backend/tests/test_whatsapp.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit the persistence change**

```powershell
git add backend/src/parrilladas/modules/conversations/service.py backend/tests/test_whatsapp.py
git commit -m "Reset WhatsApp flow after invalid replies"
```

### Task 3: Validate, push, and verify Railway

**Files:**
- No source files unless a test exposes an implementation defect.

- [ ] **Step 1: Run project checks**

```powershell
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m ruff format --check backend
.\.venv\Scripts\python.exe -m pytest backend/tests
.\.venv\Scripts\python.exe -m pip check
```

Expected: Ruff and format pass, all tests pass, and pip reports no broken requirements.

- [ ] **Step 2: Inspect the final diff and preserve unrelated work**

```powershell
git diff origin/main...HEAD --stat
git status --short
```

Do not stage `.railway/railway.ts`, `.codebase-memory/`, `diagrams/`, or `proyect_brain/privacy.md` unless separately requested.

- [ ] **Step 3: Push the implementation**

```powershell
git push origin main
```

Expected: GitHub Actions starts and Railway waits for CI before deploying API and Admin.

- [ ] **Step 4: Verify deployment and runtime behavior**

```powershell
railway status
railway logs --service api --lines 120
```

Expected: API and Postgres are online, webhook requests return `200 OK`, and no new `NoReferencedTableError` or unhandled flow exception appears.

- [ ] **Step 5: Perform the manual WhatsApp acceptance test**

Send a quote request through the Costa Rica WhatsApp number, answer the first four questions, confirm that the service question displays only the `Parrilla` button, press it, and verify that the summary follows. Send three invalid replies in a row at a question and verify that the bot returns to the greeting menu.

## Self-review

- The approved button requirement is covered by Tasks 1 and 3.
- The three-invalid-replies reset requirement is covered by Tasks 1, 2, and 3.
- No migration is needed because the counter is stored in existing JSONB.
- No placeholder steps or unresolved names remain; the only deployment dependency is the existing CI/Railway pipeline.
