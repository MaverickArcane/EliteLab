"""Bounded security rejection evidence without request data or credentials."""
import threading
import time


class SecurityEvents:
    """One warning per status per minute, shared by a listener's threads.

    Only fixed source/status labels enter the log. Paths, addresses, headers,
    bodies and exception messages are deliberately absent. Repeated rejections
    are counted in the next warning instead of filling the staging log.
    """
    REASONS = {400: "invalid_request", 401: "authentication",
               403: "forbidden", 415: "content_type", 503: "capacity"}

    def __init__(self, logger, source):
        self.logger, self.source = logger, source
        self.lock = threading.Lock()
        self.recent = {}

    def rejected(self, status):
        reason = self.REASONS.get(status)
        if reason is None:
            return
        now = time.monotonic()
        with self.lock:
            previous, suppressed = self.recent.get(status, (None, 0))
            if previous is not None and now - previous < 60:
                self.recent[status] = (previous, suppressed + 1)
                return
            self.recent[status] = (now, 0)
        self.logger.warning("security source=%s event=request_rejected reason=%s status=%d suppressed=%d",
                            self.source, reason, status, suppressed)
