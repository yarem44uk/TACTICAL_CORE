"""
Error Isolation for Pipeline Dispatcher.

Prevents plugin or pipeline errors from crashing the dispatcher.
Wraps dispatch operations in error handling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ErrorIsolationResult:
    """Result of an error-isolated operation."""

    __slots__ = ("success", "result", "error")

    def __init__(
        self, success: bool, result: Any = None, error: Optional[str] = None
    ) -> None:
        self.success = success
        self.result = result
        self.error = error

    def __bool__(self) -> bool:
        return self.success


class ErrorIsolation:
    """
    Wraps pipeline operations to isolate errors.

    Ensures that failures in plugins, validation, or persistence
    never crash the dispatcher or the event engine.
    """

    def __init__(self, log_level: str = "WARNING") -> None:
        self._log_level = log_level

    def wrap(
        self,
        operation: Callable[[], Any],
        plugin: Optional[str] = None,
        context: Optional[str] = None,
    ) -> ErrorIsolationResult:
        """
        Execute an operation with error isolation.

        Args:
            operation: Callable to execute.
            plugin: Optional plugin identifier for logging.
            context: Optional context description.

        Returns:
            ErrorIsolationResult with success status and result or error.
        """
        plugin_label = f"plugin={plugin}" if plugin else ""
        context_label = f" context={context}" if context else ""
        label = f"({plugin_label}{context_label})" if plugin or context else ""

        try:
            result = operation()
            return ErrorIsolationResult(success=True, result=result)

        except Exception as exc:  # noqa: BLE001
            log_msg = f"ErrorIsolation: operation failed {label}: {exc}"
            log_fn = getattr(logger, self._log_level.lower(), logger.warning)
            log_fn(log_msg)

            return ErrorIsolationResult(
                success=False,
                result=None,
                error=str(exc),
            )

    def wrap_batch(
        self,
        operations: list[Callable[[], Any]],
        plugin: Optional[str] = None,
        context: Optional[str] = None,
    ) -> list[ErrorIsolationResult]:
        """
        Execute multiple operations with error isolation.

        Each operation is isolated independently.

        Args:
            operations: List of callables.
            plugin: Optional plugin identifier.
            context: Optional context description.

        Returns:
            List of ErrorIsolationResult.
        """
        results = []
        for op in operations:
            result = self.wrap(op, plugin=plugin, context=context)
            results.append(result)
        return results
