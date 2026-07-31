"""
Configuration Contracts.

Interfaces for configuration management.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IConfigurationProvider(ABC):
    """
    Interface for configuration management.
    """

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        pass

    @abstractmethod
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get all values in a section."""
        pass

    @abstractmethod
    def reload(self) -> None:
        """Reload configuration from source."""
        pass

    @abstractmethod
    def validate(self) -> List[str]:
        """Validate configuration. Returns list of errors."""
        pass
