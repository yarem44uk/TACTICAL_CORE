"""
Health Manager.

Central health monitoring manager.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from app.core.health.component import ComponentHealth, HealthStatus


class HealthManager:
    """
    Manages system health monitoring.

    Tracks health of all components and provides overall status.
    """

    def __init__(self) -> None:
        """Initialize health manager."""
        self._lock = threading.RLock()
        self._components: Dict[str, ComponentHealth] = {}
        self._started_at = datetime.now(timezone.utc)

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

            if status == HealthStatus.CRITICAL:
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

            if HealthStatus.CRITICAL in statuses:
                return HealthStatus.CRITICAL
            if HealthStatus.OFFLINE in statuses:
                return HealthStatus.OFFLINE
            if HealthStatus.WARNING in statuses:
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
                    name: c.to_dict()
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


_global_health_manager: Optional[HealthManager] = None


def get_health_manager() -> HealthManager:
    """Get global health manager."""
    global _global_health_manager
    if _global_health_manager is None:
        _global_health_manager = HealthManager()
    return _global_health_manager
