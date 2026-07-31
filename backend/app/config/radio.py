"""
Radio Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""


class RadioConfig:
    """Radio module configuration."""

    def __init__(
        self,
        enabled: bool = False,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        whisper_model: str = "base",
        whisper_device: str = "cpu",
        buffer_duration: int = 30,
    ) -> None:
        self.enabled = enabled
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.whisper_model = whisper_model
        self.whisper_device = whisper_device
        self.buffer_duration = buffer_duration

    @property
    def is_enabled(self) -> bool:
        return self.enabled
