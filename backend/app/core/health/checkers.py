"""
Health Checkers.

Specific health check implementations.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from app.core.health.component import ComponentHealth, HealthStatus


class BaseHealthChecker(ABC):
    """Base class for health checkers."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def check(self) -> ComponentHealth:
        """Perform the health check."""
        pass


class DatabaseHealthChecker(BaseHealthChecker):
    """Health checker for database connectivity."""

    def __init__(self, session=None) -> None:
        super().__init__("database")
        self._session = session

    def check(self) -> ComponentHealth:
        try:
            if self._session is None:
                return ComponentHealth(
                    name=self._name,
                    status=HealthStatus.WARNING,
                    message="No database session"
                )

            self._session.execute(text("SELECT 1"))
            return ComponentHealth(
                name=self._name,
                status=HealthStatus.HEALTHY,
                message="Database connected"
            )
        except Exception as e:
            return ComponentHealth(
                name=self._name,
                status=HealthStatus.CRITICAL,
                message="Database error: " + str(e)
            )


class PipelineHealthChecker(BaseHealthChecker):
    """Health checker for pipeline."""

    def __init__(self, pipeline=None) -> None:
        super().__init__("pipeline")
        self._pipeline = pipeline

    def check(self) -> ComponentHealth:
        if self._pipeline is None:
            return ComponentHealth(
                name=self._name,
                status=HealthStatus.WARNING,
                message="No pipeline configured"
            )

        enabled = len(self._pipeline.enabled_stages)
        total = self._pipeline.stage_count

        if enabled == 0:
            return ComponentHealth(
                name=self._name,
                status=HealthStatus.WARNING,
                message="No stages enabled"
            )

        return ComponentHealth(
            name=self._name,
            status=HealthStatus.HEALTHY,
            message=f"{enabled}/{total} stages enabled"
        )


class StorageHealthChecker(BaseHealthChecker):
    """Health checker for storage."""

    def __init__(self, storage_path: str = "./storage") -> None:
        super().__init__("storage")
        self._storage_path = storage_path

    def check(self) -> ComponentHealth:
        import os
        from pathlib import Path

        try:
            path = Path(self._storage_path)
            if not path.exists():
                return ComponentHealth(
                    name=self._name,
                    status=HealthStatus.CRITICAL,
                    message="Storage path does not exist"
                )

            if not os.access(path, os.W_OK):
                return ComponentHealth(
                    name=self._name,
                    status=HealthStatus.WARNING,
                    message="Storage path not writable"
                )

            return ComponentHealth(
                name=self._name,
                status=HealthStatus.HEALTHY,
                message="Storage accessible"
            )
        except Exception as e:
            return ComponentHealth(
                name=self._name,
                status=HealthStatus.CRITICAL,
                message=str(e)
            )
