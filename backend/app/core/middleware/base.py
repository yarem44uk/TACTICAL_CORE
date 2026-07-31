"""
Base Middleware.

Abstract base class for pipeline middleware.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional


class BaseMiddleware(ABC):
    """
    Abstract base class for middleware.

    Middleware executes before/after each stage.
    Multiple middleware can be chained.
    """

    def __init__(self, name: Optional[str] = None, enabled: bool = True) -> None:
        """Initialize middleware."""
        self._name = name or self.__class__.__name__
        self._enabled = enabled

    @property
    def name(self) -> str:
        """Get middleware name."""
        return self._name

    @property
    def enabled(self) -> bool:
        """Check if enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable."""
        self._enabled = value

    def __call__(
        self,
        phase: str,
        stage_name: str,
        context: Any,
        result: Optional[Any],
    ) -> None:
        """
        Execute middleware.

        Args:
            phase: "before", "after", or "exception"
            stage_name: Name of executing stage
            context: Pipeline context
            result: Stage result (None for before phase)
        """
        if not self._enabled:
            return

        if phase == "before":
            self.before(stage_name, context)
        elif phase == "after":
            self.after(stage_name, context, result)
        elif phase == "exception":
            self.on_exception(stage_name, context, result)

    def before(self, stage_name: str, context: Any) -> None:
        """Called before stage execution."""
        pass

    def after(self, stage_name: str, context: Any, result: Optional[Any]) -> None:
        """Called after stage execution."""
        pass

    def on_exception(self, stage_name: str, context: Any, result: Optional[Any]) -> None:
        """Called when stage raises an exception."""
        pass


def logging_middleware(
    phase: str,
    stage_name: str,
    context: Any,
    result: Optional[Any],
) -> None:
    """
    Logging middleware function.

    Logs stage execution for debugging.
    """
    import logging
    logger = logging.getLogger("middleware.logging")

    if phase == "before":
        logger.debug("Executing stage: " + stage_name)
    elif phase == "after" and result:
        if result.has_errors:
            logger.warning("Stage " + stage_name + " completed with errors")
        else:
            logger.debug("Stage " + stage_name + " completed in " + 
                        str(result.execution_time_ms) + "ms")
    elif phase == "exception":
        logger.error("Stage " + stage_name + " raised exception")


def performance_middleware(
    phase: str,
    stage_name: str,
    context: Any,
    result: Optional[Any],
) -> None:
    """
    Performance monitoring middleware.

    Tracks stage execution times.
    """
    if phase == "after" and result:
        timing = context.stage_timings
        if stage_name not in timing:
            timing[stage_name] = result.execution_time_ms


def security_middleware(
    phase: str,
    stage_name: str,
    context: Any,
    result: Optional[Any],
) -> None:
    """
    Security middleware.

    Validates event data for security issues.
    """
    import logging
    logger = logging.getLogger("middleware.security")

    if phase == "before":
        data = context.event_data
        sensitive_fields = ["password", "secret", "token", "api_key"]

        for field in sensitive_fields:
            if field in data and data[field]:
                logger.warning("Sensitive field in event data: " + field)
