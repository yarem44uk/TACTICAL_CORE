"""
Storage Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from pathlib import Path


class StorageConfig:
    """File storage configuration."""

    def __init__(
        self,
        root: Path = Path("./storage"),
        audio: Path = Path("./storage/audio"),
        video: Path = Path("./storage/video"),
        attachments: Path = Path("./storage/attachments"),
        logs: Path = Path("./storage/logs"),
        cache: Path = Path("./storage/cache"),
    ) -> None:
        self.root = root
        self.audio = audio
        self.video = video
        self.attachments = attachments
        self.logs = logs
        self.cache = cache

    def ensure_directories(self) -> None:
        """Create all storage directories if they don't exist."""
        for directory in [self.root, self.audio, self.video, 
                          self.attachments, self.logs, self.cache]:
            directory.mkdir(parents=True, exist_ok=True)
