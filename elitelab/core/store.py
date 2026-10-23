"""Namespaced state store with change notification.

Each module owns one namespace and writes only to it. Every change bumps a
global version, notifies subscribers (the SSE stream uses this) and emits
``state.<ns>.<key>`` on the bus so other modules can react.
"""
import copy
import threading


class Store:
    def __init__(self, bus):
        self._bus = bus
        self._data = {}
        self._version = 0
        self._lock = threading.RLock()
        self._subs = []

    # -- writing ----------------------------------------------------------
    def set(self, ns, key, value):
        """Set one key. Returns True if the value actually changed."""
        with self._lock:
            d = self._data.setdefault(ns, {})
            if key in d and d[key] == value:
                return False
            d[key] = copy.deepcopy(value) if isinstance(value, (dict, list)) else value
            self._version += 1
            ver = self._version
            subs = list(self._subs)
        for fn in subs:
            try:
                fn(ns, key, value, ver)
            except Exception:
                pass
        self._bus.emit(f"state.{ns}.{key}", value)
        return True

    def update(self, ns, mapping):
        """Set several keys; returns the list of keys that changed."""
        return [k for k, v in mapping.items() if self.set(ns, k, v)]

    def delete_ns(self, ns):
        with self._lock:
            self._data.pop(ns, None)

    # -- reading ----------------------------------------------------------
    def get(self, ns, key=None, default=None):
        with self._lock:
            d = self._data.get(ns, {})
            if key is None:
                return copy.deepcopy(d)
            return copy.deepcopy(d.get(key, default))

    def snapshot(self):
        with self._lock:
            snap = copy.deepcopy(self._data)
            snap["_version"] = self._version
            return snap

    @property
    def version(self):
        return self._version

    # -- subscriptions ------------------------------------------------------
    def subscribe(self, fn):
        """``fn(ns, key, value, version)`` on every change. Returns an unsubscribe callable."""
        with self._lock:
            self._subs.append(fn)

        def off():
            with self._lock:
                try:
                    self._subs.remove(fn)
                except ValueError:
                    pass
        return off
