"""
Plugin Health Monitoring.

Provides health status tracking and metrics collection for plugins.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


class HealthStatus(Enum):
    """Plugin health status values."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    name: str
    status: HealthStatus
    message: str
    duration_ms: float
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class HealthReport:
    """Aggregated health report for a plugin."""

    plugin_id: str
    overall_status: HealthStatus
    checks: List[HealthCheckResult]
    last_check: Optional[datetime]
    consecutive_failures: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "plugin_id": self.plugin_id,
            "overall_status": self.overall_status.value,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "duration_ms": c.duration_ms,
                    "checked_at": c.checked_at.isoformat(),
                }
                for c in self.checks
            ],
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "consecutive_failures": self.consecutive_failures,
        }


@dataclass
class PluginMetrics:
    """Plugin performance and operational metrics."""

    plugin_id: str
    start_time: Optional[datetime] = None
    total_events_processed: int = 0
    total_errors: int = 0
    last_event_time: Optional[datetime] = None
    last_error_time: Optional[datetime] = None
    custom_metrics: Dict[str, Any] = field(default_factory=dict)

    def increment_events(self, count: int = 1) -> None:
        """Increment event processing counter."""
        self.total_events_processed += count
        self.last_event_time = datetime.now(timezone.utc)

    def increment_errors(self, count: int = 1) -> None:
        """Increment error counter."""
        self.total_errors += count
        self.last_error_time = datetime.now(timezone.utc)

    def set_metric(self, key: str, value: Any) -> None:
        """Set a custom metric value."""
        self.custom_metrics[key] = value

    def get_metric(self, key: str, default: Any = None) -> Any:
        """Get a custom metric value."""
        return self.custom_metrics.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "plugin_id": self.plugin_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "total_events_processed": self.total_events_processed,
            "total_errors": self.total_errors,
            "last_event_time": self.last_event_time.isoformat() if self.last_event_time else None,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
            "custom_metrics": dict(self.custom_metrics),
        }


class PluginHealth:
    """
    Health monitoring for a plugin.

    Tracks health status, manages health checks, and produces
    aggregated health reports.
    """

    def __init__(self, plugin_id: str) -> None:
        """
        Initialize health monitor.

        Args:
            plugin_id: Unique plugin identifier.
        """
        self._plugin_id = plugin_id
        self._status = HealthStatus.UNKNOWN
        self._message = ""
        self._checks: List[tuple[str, Callable]] = []
        self._last_check: Optional[datetime] = None
        self._consecutive_failures = 0
        self._metrics = PluginMetrics(plugin_id=plugin_id)

    @property
    def plugin_id(self) -> str:
        """Plugin identifier."""
        return self._plugin_id

    @property
    def status(self) -> HealthStatus:
        """Current health status."""
        return self._status

    @property
    def last_check(self) -> Optional[datetime]:
        """Last health check timestamp."""
        return self._last_check

    @property
    def metrics(self) -> PluginMetrics:
        """Plugin metrics."""
        return self._metrics

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive health check failures."""
        return self._consecutive_failures

    def add_check(self, name: str, check_fn: Callable) -> None:
        """
        Register a health check function.

        Args:
            name: Unique check name.
            check_fn: Callable that returns (bool, str) tuple of (is_healthy, message).
        """
        self._checks.append((name, check_fn))

    def set_status(self, status: HealthStatus, message: str = "") -> None:
        """
        Manually set health status.

        Args:
            status: New health status.
            message: Optional status message.
        """
        self._status = status
        self._message = message

    async def run_checks(self) -> HealthReport:
        """
        Execute all registered health checks.

        Returns:
            Aggregated health report.
        """
        import asyncio

        results: List[HealthCheckResult] = []
        check_start = datetime.now(timezone.utc)

        for name, check_fn in self._checks:
            start = datetime.now(timezone.utc)
            try:
                result = check_fn()
                if asyncio.iscoroutine(result):
                    result = await result
                is_healthy, message = result
                duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                status = HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY
                results.append(HealthCheckResult(
                    name=name,
                    status=status,
                    message=message,
                    duration_ms=round(duration, 2),
                ))
            except Exception as e:
                duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                results.append(HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {e}",
                    duration_ms=round(duration, 2),
                ))

        # Calculate overall status
        if not results:
            overall = self._status
        elif all(r.status == HealthStatus.HEALTHY for r in results):
            overall = HealthStatus.HEALTHY
            self._consecutive_failures = 0
        elif any(r.status == HealthStatus.UNHEALTHY for r in results):
            unhealthy_count = sum(1 for r in results if r.status == HealthStatus.UNHEALTHY)
            if unhealthy_count == len(results):
                overall = HealthStatus.UNHEALTHY
            else:
                overall = HealthStatus.DEGRADED
            self._consecutive_failures += 1
        else:
            overall = HealthStatus.DEGRADED

        self._status = overall
        self._last_check = datetime.now(timezone.utc)

        return HealthReport(
            plugin_id=self._plugin_id,
            overall_status=overall,
            checks=results,
            last_check=self._last_check,
            consecutive_failures=self._consecutive_failures,
        )

    def get_report(self) -> HealthReport:
        """
        Get the current health report without running checks.

        Returns:
            Current health report snapshot.
        """
        return HealthReport(
            plugin_id=self._plugin_id,
            overall_status=self._status,
            checks=[],
            last_check=self._last_check,
            consecutive_failures=self._consecutive_failures,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert health state to dictionary."""
        return {
            "plugin_id": self._plugin_id,
            "status": self._status.value,
            "message": self._message,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "consecutive_failures": self._consecutive_failures,
            "metrics": self._metrics.to_dict(),
        }
