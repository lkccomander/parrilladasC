"""Explicit metadata registry for migrations; keep imports out of db.base."""

from parrilladas.modules.accounts.models import Account
from parrilladas.modules.conversations.models import Conversation, Message
from parrilladas.modules.leads.models import Lead
from parrilladas.modules.quotes.models import Quote
from parrilladas.modules.reminders.models import Reminder

__all__ = ["Account", "Conversation", "Lead", "Message", "Quote", "Reminder"]
