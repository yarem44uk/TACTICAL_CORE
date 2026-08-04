"""
Plugin Logger.

Structured logging for plugins with plugin identity injection.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Any, Dict, Optional


class PluginLogger:
    """
    Structured logger for plugins.

    Wraps Python logging with automatic plugin context injection.
    Every log record includes plugin_id, plugin_name, and plugin_version.
    """

    def __init__(
        self,
        plugin_id: str,
        plugin_name: Optional[str] = None,
        plugin_version: Optional[str] = None,
        level: int = logging.INFO,
    ) -> None:
        """
        Initialize plugin logger.

        Args:
            plugin_id: Unique plugin identifier.
            plugin_name: Human-readable plugin name.
            plugin_version: Plugin version string.
            level: Logging level (default INFO).
        """
        self._plugin_id = plugin_id
        self._plugin_name = plugin_name or plugin_id
        self._plugin_version = plugin_version or "0.0.0"
        self._logger = logging.getLogger(f"tactical_core.plugin.{plugin_id}")
        self._logger.setLevel(level)

        # Prevent duplicate handlers on repeated initialization
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)-7s %(plugin_id)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    @property
    def plugin_id(self) -> str:
        """Plugin identifier."""
        return self._plugin_id

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        """
        Emit a structured log record with plugin context.

        Args:
            level: Logging level.
            message: Log message.
            **kwargs: Additional structured fields.
        """
        extra: Dict[str, Any] = {
            "plugin_id": self._plugin_id,
        }
        # Remove extra fields from kwargs that are already injected
        kwargs.pop("plugin_id", None)
        kwargs.pop("plugin_name", None)
        kwargs.pop("plugin_version", None)

        if kwargs:
            full_message = f"{message} | {kwargs}"
        else:
            full_message = message

        self._logger.log(level, full_message, extra=extra, stacklevel=3)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error message."""
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log a critical message."""
        self._log(logging.CRITICAL, message, **kwargs)
