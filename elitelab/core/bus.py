"""A tiny synchronous event bus with glob-style subscriptions.

Event names are dotted: ``journal.FSDJump``, ``state.powerplay.merits``,
``journal.file.Cargo``. Subscribe with an exact name, a prefix wildcard
(``journal.*``) or ``*`` for everything. Handlers run in the emitter's thread
and are isolated from each other: one failing handler never blocks the rest.
"""
import fnmatch
import logging
import threading

log = logging.getLogger("elitelab.bus")


class EventBus:
    def __init__(self):
        self._subs = []          # [(pattern, fn)]
        self._lock = threading.RLock()

    def on(self, pattern, fn):
        """Subscribe ``fn(name, payload)`` to events matching ``pattern``. Returns an unsubscribe callable."""
        with self._lock:
            self._subs.append((pattern, fn))

        def off():
            with self._lock:
                try:
                    self._subs.remove((pattern, fn))
                except ValueError:
                    pass
        return off

    def emit(self, name, payload=None):
        with self._lock:
            subs = list(self._subs)
        for pattern, fn in subs:
            if pattern == name or pattern == "*" or fnmatch.fnmatchcase(name, pattern):
                try:
                    fn(name, payload)
                except Exception:
                    log.exception("handler %r failed on %s", getattr(fn, "__qualname__", fn), name)
