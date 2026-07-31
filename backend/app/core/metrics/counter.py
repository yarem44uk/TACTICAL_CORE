"""
Counter Metric.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import threading


class Counter:
    """Thread-safe counter metric."""

    def __init__(self, name: str, description: str = "") -> None:
        """Initialize counter."""
        self._name = name
        self._description = description
        self._lock = threading.Lock()
        self._value = 0

    @property
    def name(self) -> str:
        """Counter name."""
        return self._name

    @property
    def value(self) -> float:
        """Get current value."""
        with self._lock:
            return self._value

    def increment(self, amount: float = 1) -> None:
        """Increment counter."""
        with self._lock:
            self._value += amount

    def reset(self) -> None:
        """Reset counter."""
        with self._lock:
            self._value = 0
