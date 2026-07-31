"""
Timer Metric.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import threading


class Timer:
    """Thread-safe timer metric for measuring durations."""

    def __init__(self, name: str, description: str = "") -> None:
        """Initialize timer."""
        self._name = name
        self._description = description
        self._lock = threading.Lock()
        self._total = 0.0
        self._count = 0
        self._min = float("inf")
        self._max = 0.0

    @property
    def name(self) -> str:
        """Timer name."""
        return self._name

    @property
    def total_ms(self) -> float:
        with self._lock:
            return self._total

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    @property
    def average_ms(self) -> float:
        with self._lock:
            if self._count == 0:
                return 0.0
            return self._total / self._count

    @property
    def min_ms(self) -> float:
        with self._lock:
            return self._min if self._min != float("inf") else 0.0

    @property
    def max_ms(self) -> float:
        with self._lock:
            return self._max

    def record(self, duration_ms: float) -> None:
        """Record a duration."""
        with self._lock:
            self._total += duration_ms
            self._count += 1
            self._min = min(self._min, duration_ms)
            self._max = max(self._max, duration_ms)
