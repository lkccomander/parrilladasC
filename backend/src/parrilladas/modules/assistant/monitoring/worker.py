"""Small bounded maintenance loop for RAG monitoring operations."""

import logging
from threading import Event, Thread

logger = logging.getLogger(__name__)


class MonitoringWorker:
    def __init__(self, service, *, interval_seconds=300):
        self.service = service
        self.interval_seconds = interval_seconds
        self.stop_event = Event()
        self.thread = Thread(target=self.run, name="rag-monitoring", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.service.maintenance()
            except Exception:
                logger.warning("RAG monitoring maintenance unavailable")
            self.stop_event.wait(self.interval_seconds)
