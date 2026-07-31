"""
Media Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""


class MediaConfig:
    """Media/Camera module configuration."""

    def __init__(
        self,
        enabled: bool = False,
        mtx_url: str = "http://localhost:8888",
        stream_timeout: int = 300,
        max_cameras: int = 16,
        quality: str = "medium",
        fps: int = 30,
    ) -> None:
        self.enabled = enabled
        self.mtx_url = mtx_url
        self.stream_timeout = stream_timeout
        self.max_cameras = max_cameras
        self.quality = quality
        self.fps = fps

    @property
    def is_enabled(self) -> bool:
        return self.enabled
