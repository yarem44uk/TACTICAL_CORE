"""
Metrics Collector.

Central metrics collection service.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.metrics.counter import Counter
from app.core.metrics.timer import Timer


class MetricsCollector:
    """
    Central metrics collector.

    Collects and aggregates metrics from pipeline execution.
    Thread-safe for concurrent access.
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

    def increment(self, name: str, amount: float = 1) -> None:
        """Increment a counter by name."""
        self.get_counter(name).increment(amount)

    def time(self, name: str):
        """Context manager for timing."""
        return _TimerContext(self, name)

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        with self._lock:
            uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()
            return {
                "uptime_seconds": uptime,
                "counters": {name: c.value for name, c in self._counters.items()},
                "timers": {
                    name: {
                        "count": t.count,
                        "total_ms": t.total_ms,
                        "average_ms": t.average_ms,
                        "min_ms": t.min_ms,
                        "max_ms": t.max_ms,
                    }
                    for name, t in self._timers.items()
                },
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            for counter in self._counters.values():
                counter.reset()
            self._timers.clear()
            self._values.clear()


class _TimerContext:
    """Timer context manager."""

    def __init__(self, collector: MetricsCollector, name: str):
        self._collector = collector
        self._name = name
        self._start = 0.0

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, *args):
        duration_ms = (time.time() - self._start) * 1000
        self._collector.get_timer(self._name).record(duration_ms)


_global_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector."""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector
