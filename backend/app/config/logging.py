"""
Logging Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from pathlib import Path
from typing import Optional


class LoggingConfig:
    """Logging configuration."""

    def __init__(
        self,
        level: str = "INFO",
        format: str = "json",
        file: Path = Path("./storage/logs/tactical_core.log"),
        max_size: int = 104857600,
        backup_count: int = 10,
        include_thread_name: bool = False,
        include_correlation_id: bool = True,
    ) -> None:
        self.level = level
        self.format = format
        self.file = file
        self.max_size = max_size
        self.backup_count = backup_count
        self.include_thread_name = include_thread_name
        self.include_correlation_id = include_correlation_id

    @property
    def log_format_json(self) -> bool:
        """Check if using JSON format."""
        return self.format.lower() == "json"

    def get_level_int(self) -> int:
        """Get log level as integer for logging module."""
        levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        return levels.get(self.level.upper(), 20)
