"""
TACTICAL CORE — Adapter Runtime Restart Policy
WO-013-003

Bounded restart policy for AdapterRuntime.

Restarts are only permitted up to a finite budget. After the budget is
exhausted the runtime transitions to FAILED and is NOT automatically
restarted again. Recovery is manual via supervisor.restart(name).

Restart counter:
    - incremented on runtime-level failure (start/poll-loop failure)
    - reset after a sustained healthy RUNNING period (reset_after_health_seconds)
    - when budget is exhausted -> FAILED
"""

from __future__ import annotations

import threading
import time


class RestartPolicy:
    """Finite-budget restart policy.

    Args:
        max_restarts: Maximum consecutive restarts allowed (finite).
        restart_delay: Seconds to wait before each restart attempt.
        reset_after_health_seconds: Sustained healthy running period (seconds)
            after which the restart counter is reset to zero.
    """

    def __init__(
        self,
        max_restarts: int = 3,
        restart_delay: float = 1.0,
        reset_after_health_seconds: float = 30.0,
    ) -> None:
        if max_restarts < 0:
            raise ValueError("max_restarts must be >= 0")
        if restart_delay < 0:
            raise ValueError("restart_delay must be >= 0")
        self.max_restarts = max_restarts
        self.restart_delay = restart_delay
        self.reset_after_health_seconds = reset_after_health_seconds
        self._lock = threading.Lock()
        self._restart_count = 0
        self._last_healthy_at: float | None = None

    @property
    def restart_count(self) -> int:
        """Current consecutive restart count."""
        with self._lock:
            return self._restart_count

    @property
    def remaining(self) -> int:
        """Remaining restart budget."""
        with self._lock:
            return max(0, self.max_restarts - self._restart_count)

    @property
    def exhausted(self) -> bool:
        """True if the restart budget is exhausted."""
        with self._lock:
            return self._restart_count >= self.max_restarts

    def record_failure(self) -> int:
        """Record a runtime-level failure.

        Returns:
            The new restart count.
        """
        with self._lock:
            self._restart_count += 1
            self._last_healthy_at = None
            return self._restart_count

    def record_health(self) -> None:
        """Record a sustained healthy running period.

        Resets the restart counter once the adapter has been healthy for
        at least reset_after_health_seconds.
        """
        now = time.monotonic()
        with self._lock:
            if self._last_healthy_at is None:
                self._last_healthy_at = now
                return
            if now - self._last_healthy_at >= self.reset_after_health_seconds:
                self._restart_count = 0
                self._last_healthy_at = now

    def reset(self) -> None:
        """Reset the restart counter (manual recovery)."""
        with self._lock:
            self._restart_count = 0
            self._last_healthy_at = None

    def wait_delay(self) -> None:
        """Block for the configured restart delay."""
        if self.restart_delay > 0:
            time.sleep(self.restart_delay)
