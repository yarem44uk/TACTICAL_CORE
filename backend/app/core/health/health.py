"""
Health Monitoring Module.

Provides health checks for system components.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    consecutive_failures: int = 0


class HealthCheck:
    """A single health check."""

    def __init__(
        self,
        name: str,
        check_fn: Callable[[], bool],
        timeout: float = 5.0,
    ) -> None:
        """Initialize health check."""
        self._name = name
        self._check_fn = check_fn
        self._timeout = timeout

    @property
    def name(self) -> str:
        """Get check name."""
        return self._name

    def execute(self) -> bool:
        """Execute the health check."""
        try:
            return self._check_fn()
        except Exception:
            return False


class HealthManager:
    """
    Manages system health monitoring.

    Tracks health of all components and provides overall status.
    """

    def __init__(self) -> None:
        """Initialize health manager."""
        self._lock = threading.RLock()
        self._components: Dict[str, ComponentHealth] = {}
        self._checks: Dict[str, HealthCheck] = {}
        self._check_interval = 30.0
        self._running = False

    def register_component(
        self,
        name: str,
        status: HealthStatus = HealthStatus.HEALTHY,
        message: str = "",
    ) -> None:
        """Register a component for health tracking."""
        with self._lock:
            self._components[name] = ComponentHealth(
                name=name,
                status=status,
                message=message,
            )

    def register_check(self, check: HealthCheck) -> None:
        """Register a health check."""
        with self._lock:
            self._checks[check.name] = check

    def update_status(
        self,
        component_name: str,
        status: HealthStatus,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update component health status."""
        with self._lock:
            if component_name not in self._components:
                self._components[component_name] = ComponentHealth(
                    name=component_name,
                    status=status,
                    message=message,
                )

            component = self._components[component_name]
            component.status = status
            component.message = message
            component.details = details or {}
            component.last_check = datetime.now(timezone.utc)

            if status in (HealthStatus.CRITICAL, HealthStatus.OFFLINE):
                component.consecutive_failures += 1
            else:
                component.consecutive_failures = 0

    def get_component_health(self, name: str) -> Optional[ComponentHealth]:
        """Get health status of a component."""
        with self._lock:
            return self._components.get(name)

    def get_all_health(self) -> Dict[str, ComponentHealth]:
        """Get health of all components."""
        with self._lock:
            return dict(self._components)

    def get_overall_status(self) -> HealthStatus:
        """Get overall system health."""
        with self._lock:
            if not self._components:
                return HealthStatus.OFFLINE

            statuses = [c.status for c in self._components.values()]

            if any(s == HealthStatus.CRITICAL for s in statuses):
                return HealthStatus.CRITICAL
            if any(s == HealthStatus.OFFLINE for s in statuses):
                return HealthStatus.OFFLINE
            if any(s == HealthStatus.WARNING for s in statuses):
                return HealthStatus.WARNING

            return HealthStatus.HEALTHY

    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report."""
        with self._lock:
            overall = self.get_overall_status()

            return {
                "status": overall.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "components": {
                    name: {
                        "status": c.status.value,
                        "message": c.message,
                        "details": c.details,
                        "last_check": c.last_check.isoformat(),
                        "consecutive_failures": c.consecutive_failures,
                    }
                    for name, c in self._components.items()
                },
                "summary": {
                    "total": len(self._components),
                    "healthy": sum(1 for c in self._components.values() if c.status == HealthStatus.HEALTHY),
                    "warning": sum(1 for c in self._components.values() if c.status == HealthStatus.WARNING),
                    "critical": sum(1 for c in self._components.values() if c.status == HealthStatus.CRITICAL),
                    "offline": sum(1 for c in self._components.values() if c.status == HealthStatus.OFFLINE),
                },
            }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.get_health_report()


_global_health_manager: Optional[HealthManager] = None


def get_health_manager() -> HealthManager:
    """Get global health manager."""
    global _global_health_manager
    if _global_health_manager is None:
        _global_health_manager = HealthManager()
    return _global_health_manager
