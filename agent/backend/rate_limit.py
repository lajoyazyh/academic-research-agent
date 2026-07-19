"""Dependency-free request throttling for costly public API mutations."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self):
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(window_seconds - (now - events[0])))
                return False, retry_after
            events.append(now)
            if len(self._events) > 10_000:
                for stale_key in [name for name, values in self._events.items() if not values or values[-1] <= cutoff][:1000]:
                    self._events.pop(stale_key, None)
            return True, 0


def policy_for(path: str, method: str) -> tuple[str, int, int] | None:
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if path.endswith("/provider/test"):
        return "provider-test", 10, 60
    if "/run/" in path or "/runs/" in path:
        return "agent-run", 8, 60
    if path.endswith("/papers/upload"):
        return "pdf-upload", 10, 900
    if "/chat" in path or path.endswith("/message"):
        return "chat", 30, 60
    return "mutation", 120, 60
