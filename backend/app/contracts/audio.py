"""
Audio Contracts.

Interfaces for audio processing.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class IAudioSource(ABC):
    """
    Interface for audio input sources.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Source identifier."""
        pass

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Audio sample rate in Hz."""
        pass

    @property
    @abstractmethod
    def channels(self) -> int:
        """Number of audio channels."""
        pass

    @abstractmethod
    def start(self) -> None:
        """Start audio capture."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop audio capture."""
        pass

    @abstractmethod
    def is_active(self) -> bool:
        """Check if source is active."""
        pass


class IAudioSink(ABC):
    """
    Interface for audio output.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Sink identifier."""
        pass

    @abstractmethod
    def write(self, audio_data: bytes) -> None:
        """Write audio data."""
        pass

    @abstractmethod
    def flush(self) -> None:
        """Flush audio buffer."""
        pass


class ITranscriber(ABC):
    """
    Interface for speech-to-text transcription.
    """

    @property
    @abstractmethod
    def model(self) -> str:
        """Transcription model name."""
        pass

    @abstractmethod
    def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
    ) -> str:
        """Transcribe audio to text."""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if transcriber is ready."""
        pass



class IVAD(ABC):
    """
    Interface for voice activity detection.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """VAD name."""
        pass

    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if VAD is enabled."""
        pass

    @abstractmethod
    def detect(self, audio_data: bytes) -> bool:
        """
        Detect if voice is present in audio.

        Returns:
            True if voice detected, False otherwise.
        """
        pass

    @abstractmethod
    def get_energy_level(self, audio_data: bytes) -> float:
        """
        Get energy level of audio.

        Returns:
            Energy level as float.
        """
        pass
