"""
Storage Contracts.

Interfaces for data storage.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, BinaryIO, Dict, List, Optional


class IStorage(ABC):
    """
    Interface for file storage.
    """

    @abstractmethod
    def save(
        self,
        data: bytes,
        path: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Save data to storage.
        Returns the storage path/key.
        """
        pass

    @abstractmethod
    def load(self, path: str) -> Optional[bytes]:
        """Load data from storage."""
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """Delete data from storage."""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if path exists in storage."""
        pass

    @abstractmethod
    def get_url(self, path: str) -> Optional[str]:
        """Get public URL for stored file."""
        pass
