import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque

logger = logging.getLogger(__name__)


class CircuitBreakerOpenError(RuntimeError):
    pass


@dataclass
class FailureEvent:
    ts: float


class CircuitBreaker:
    def __init__(self, failure_threshold: int, reset_timeout: int, window_seconds: int):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.window_seconds = window_seconds
        self.state = "CLOSED"
        self.failures: Deque[FailureEvent] = deque()
        self.opened_at = 0.0
        self._lock = threading.Lock()

    def before_call(self) -> None:
        with self._lock:
            now = time.time()
            self._prune(now)
            if self.state == "OPEN":
                if now - self.opened_at >= self.reset_timeout:
                    self._transition("HALF_OPEN")
                else:
                    raise CircuitBreakerOpenError("flight service temporarily unavailable")
            elif self.state == "HALF_OPEN":
                return

    def on_success(self) -> None:
        with self._lock:
            self.failures.clear()
            if self.state != "CLOSED":
                self._transition("CLOSED")

    def on_failure(self) -> None:
        with self._lock:
            now = time.time()
            self.failures.append(FailureEvent(ts=now))
            self._prune(now)
            if self.state == "HALF_OPEN":
                self.opened_at = now
                self._transition("OPEN")
                return
            if len(self.failures) >= self.failure_threshold:
                self.opened_at = now
                self._transition("OPEN")

    def _prune(self, now: float) -> None:
        while self.failures and now - self.failures[0].ts > self.window_seconds:
            self.failures.popleft()

    def _transition(self, new_state: str) -> None:
        logger.warning("circuit breaker transition %s -> %s", self.state, new_state)
        self.state = new_state
