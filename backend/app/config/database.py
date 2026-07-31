"""
Database Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from pydantic import Field, field_validator
from typing import Optional


class DatabaseConfig:
    """Database connection configuration."""

    def __init__(
        self,
        url: str = "sqlite:///./storage/database/tactical_core.db",
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
    ) -> None:
        self.url = url
        self.echo = echo
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_recycle = pool_recycle
        self.pool_pre_ping = pool_pre_ping

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        valid_prefixes = ("sqlite:///", "postgresql://", "mysql://", "mssql://")
        if not any(v.startswith(prefix) for prefix in valid_prefixes):
            raise ValueError(f"URL must start with: {valid_prefixes}")
        return v

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite."""
        return self.url.startswith("sqlite:///")

    @property
    def is_postgresql(self) -> bool:
        """Check if using PostgreSQL."""
        return self.url.startswith("postgresql://")
