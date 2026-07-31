"""
Monitoring Contracts.

Interfaces for system monitoring.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"


class IHealthCheck(ABC):
    """
    Interface for health checking.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Health check name."""
        pass

    @abstractmethod
    def check(self) -> HealthStatus:
        """Perform health check and return status."""
        pass

    @abstractmethod
    def get_details(self) -> Dict[str, Any]:
        """Get detailed health information."""
        pass


class IMetricsCollector(ABC):
    """
    Interface for metrics collection.
    """

    @abstractmethod
    def increment(self, name: str, value: float = 1) -> None:
        """Increment a counter."""
        pass

    @abstractmethod
    def gauge(self, name: str, value: float) -> None:
        """Set a gauge value."""
        pass

    @abstractmethod
    def timing(self, name: str, duration_ms: float) -> None:
        """Record a timing."""
        pass

    @abstractmethod
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        pass


class ILogger(ABC):
    """
    Interface for logging.
    """

    @abstractmethod
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        pass

    @abstractmethod
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        pass

    @abstractmethod
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        pass

    @abstractmethod
    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message."""
        pass

    @abstractmethod
    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message."""
        pass


class IHealthChecker(ABC):
    """
    Interface for health checking.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Health checker name."""
        pass

    @abstractmethod
    def check(self) -> "HealthStatus":
        """Perform health check and return status."""
        pass

    @abstractmethod
    def get_details(self) -> Dict[str, Any]:
        """Get detailed health information."""
        pass


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"
