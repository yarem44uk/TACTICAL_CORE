"""
Metrics Module.

Provides metrics collection for monitoring pipeline performance.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class MetricValue:
    """A single metric value with timestamp."""
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """Thread-safe counter metric."""

    def __init__(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None) -> None:
        """Initialize counter."""
        self._name = name
        self._description = description
        self._labels = labels or {}
        self._lock = threading.Lock()
        self._value = 0

    def increment(self, amount: float = 1) -> None:
        """Increment counter."""
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        """Get current value."""
        with self._lock:
            return self._value

    def reset(self) -> None:
        """Reset counter."""
        with self._lock:
            self._value = 0


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

    def record(self, duration_ms: float) -> None:
        """Record a duration."""
        with self._lock:
            self._total += duration_ms
            self._count += 1
            self._min = min(self._min, duration_ms)
            self._max = max(self._max, duration_ms)

    @property
    def total_ms(self) -> float:
        """Get total duration."""
        with self._lock:
            return self._total

    @property
    def count(self) -> int:
        """Get record count."""
        with self._lock:
            return self._count

    @property
    def average_ms(self) -> float:
        """Get average duration."""
        with self._lock:
            if self._count == 0:
                return 0.0
            return self._total / self._count

    @property
    def min_ms(self) -> float:
        """Get minimum duration."""
        with self._lock:
            return self._min if self._min != float("inf") else 0.0

    @property
    def max_ms(self) -> float:
        """Get maximum duration."""
        with self._lock:
            return self._max


class MetricsCollector:
    """
    Central metrics collector.

    Collects and aggregates metrics from pipeline execution.
    """

    def __init__(self) -> None:
        """Initialize collector."""
        self._lock = threading.Lock()
        self._counters: Dict[str, Counter] = {}
        self._timers: Dict[str, Timer] = {}
        self._values: Dict[str, list] = defaultdict(list)
        self._started_at = datetime.now(timezone.utc)

    def get_counter(self, name: str, description: str = "") -> Counter:
        """Get or create a counter."""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description)
            return self._counters[name]

    def get_timer(self, name: str, description: str = "") -> Timer:
        """Get or create a timer."""
        with self._lock:
            if name not in self._timers:
                self._timers[name] = Timer(name, description)
            return self._timers[name]

    def record_value(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a metric value."""
        with self._lock:
            metric = MetricValue(value=value, labels=labels or {})
            self._values[name].append(metric)

            if len(self._values[name]) > 1000:
                self._values[name] = self._values[name][-1000:]

    def increment(self, name: str, amount: float = 1) -> None:
        """Increment a counter by name."""
        self.get_counter(name).increment(amount)

    def time(self, name: str) -> callable:
        """Context manager for timing."""
        class TimerContext:
            def __init__(tself, collector: MetricsCollector, timer_name: str):
                tself._collector = collector
                tself._timer_name = timer_name
                tself._start = 0.0

            def __enter__(tself):
                tself._start = time.time()
                return tself

            def __exit__(tself, *args):
                duration_ms = (time.time() - tself._start) * 1000
                tself._collector.get_timer(tself._timer_name).record(duration_ms)

        return TimerContext(self, name)

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        with self._lock:
            uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()

            return {
                "uptime_seconds": uptime,
                "counters": {
                    name: counter.value
                    for name, counter in self._counters.items()
                },
                "timers": {
                    name: {
                        "count": timer.count,
                        "total_ms": timer.total_ms,
                        "average_ms": timer.average_ms,
                        "min_ms": timer.min_ms,
                        "max_ms": timer.max_ms,
                    }
                    for name, timer in self._timers.items()
                },
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            for counter in self._counters.values():
                counter.reset()
            self._timers.clear()
            self._values.clear()


_global_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector."""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector
