"""Poll durable inbox/outbox state; no customer action depends on an in-memory queue."""

import logging
from threading import Event, Thread

from parrilladas.modules.conversations.service import ConversationService
from parrilladas.modules.notifications.service import parse_recipients

logger = logging.getLogger(__name__)


class ConversationWorker:
    def __init__(self, session_factory, *, sender, assistant, settings):
        self.session_factory = session_factory
        self.sender = sender
        self.assistant = assistant
        self.settings = settings
        self.stop_event = Event()
        self.thread = Thread(target=self.run, name="conversation-worker", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=45)

    def tick(self) -> bool:
        with self.session_factory() as session:
            service = ConversationService(
                session,
                self.sender,
                assistant=self.assistant,
                quote_flow_id=self.settings.whatsapp_quote_flow_id,
                notification_whatsapp_numbers=(
                    parse_recipients(self.settings.notification_whatsapp_numbers)
                    if self.settings.app_env != "test"
                    else ()
                ),
                notification_email_recipients=(
                    parse_recipients(self.settings.notification_email_recipients)
                    if self.settings.app_env != "test"
                    else ()
                ),
            )
            processed = service.process_next(
                not_before=self.settings.conversation_processing_start_at,
                business_account_id=self.settings.whatsapp_business_account_id,
                phone_number_id=self.settings.whatsapp_phone_number_id,
            )
            sent = service.deliver_next(not_before=self.settings.conversation_processing_start_at)
            return processed or sent

    def run(self):
        while not self.stop_event.is_set():
            try:
                busy = self.tick()
            except Exception as error:
                logger.warning("Conversation worker unavailable: %s", type(error).__name__)
                busy = False
            if not busy:
                self.stop_event.wait(1)
