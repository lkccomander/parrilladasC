"""Explicit metadata registry for migrations; keep imports out of db.base."""

from parrilladas.modules.accounts.models import Account, AuthSession, LoginAttempt
from parrilladas.modules.assistant.models import (
    AssistantPreference,
    GeminiTelemetry,
    KnowledgeChunk,
    KnowledgeDocument,
)
from parrilladas.modules.assistant.monitoring.eval_models import (
    RagEvalCase,
    RagEvalCaseResult,
    RagEvalRun,
    RagEvalSet,
)
from parrilladas.modules.assistant.monitoring.ops_models import (
    RagAlert,
    RagIndexCheck,
    RagProbeRun,
)
from parrilladas.modules.assistant.monitoring.trace_models import RagQueryTrace
from parrilladas.modules.conversations.models import (
    Conversation,
    Interaction,
    Message,
    WhatsAppInboxEvent,
)
from parrilladas.modules.leads.models import Lead
from parrilladas.modules.quotes.models import Quote
from parrilladas.modules.reminders.models import Reminder

__all__ = [
    "Account",
    "AuthSession",
    "AssistantPreference",
    "GeminiTelemetry",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "LoginAttempt",
    "Conversation",
    "Interaction",
    "Lead",
    "Message",
    "Quote",
    "Reminder",
    "WhatsAppInboxEvent",
    "RagQueryTrace",
    "RagEvalSet",
    "RagEvalCase",
    "RagEvalRun",
    "RagEvalCaseResult",
    "RagAlert",
    "RagProbeRun",
    "RagIndexCheck",
]
