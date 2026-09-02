"""WO-038 — Multicast audio source configuration.

Immutable, dataclass-based configuration for the multicast UDP audio source.
It is consumed by :class:`MulticastAudioReceiver` and
:class:`MulticastAudioSourceAdapter`.

No operational address is hardcoded: every address/port/codec/rate/channel is
configured here (or, for the adapter, read from the existing
``SourceDefinition.config`` dict).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class AudioConfig:
    """Configuration for one multicast UDP audio source.

    Attributes:
        multicast_address: IPv4 multicast group address (e.g. ``239.255.0.1``).
        multicast_port: UDP port to bind / send on.
        codec: Input audio codec/format passed to ffmpeg for decode. When
            ``None`` ffmpeg auto-detects (e.g. ``wav``, ``pcm_s16le``, ``mp3``).
        sample_rate: Target PCM sample rate for STT input (Hz).
        channels: Target PCM channel count for STT input.
        source_name: The canonical source identifier used as the Event
            ``source`` and the adapter name. Defaults to ``"radio"`` so the
            operator UI can label it RADIO.
        join_interface: Interface address used to join the multicast group on
            the receiving host. ``127.0.0.1`` is the loopback interface (used by
            tests / same-host simulators).
        receive_buffer: UDP receive buffer size in bytes.
        frame_timeout: Seconds the receiver socket waits for a datagram before
            reporting a transient receive timeout (kept small so source
            interruption is detected promptly without crashing).
        reconnect_delay: Seconds to wait before re-binding after a socket
            interruption.
    """

    multicast_address: str = "239.255.0.1"
    multicast_port: int = 50000
    codec: str | None = None
    sample_rate: int = 16000
    channels: int = 1
    source_name: str = "radio"
    join_interface: str = "127.0.0.1"
    receive_buffer: int = 65536
    frame_timeout: float = 0.5
    reconnect_delay: float = 1.0
    # Optional caller-supplied stable source metadata carried on every event.
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_source_definition(cls, config: dict[str, Any]) -> AudioConfig:
        """Build an ``AudioConfig`` from an opaque ``SourceDefinition.config`` dict.

        Unknown keys are ignored (the config layer treats the dict as opaque).
        Missing keys fall back to defaults.
        """
        if config is None:
            config = {}
        return cls(
            multicast_address=config.get("multicast_address", cls.multicast_address),
            multicast_port=int(config.get("multicast_port", cls.multicast_port)),
            codec=config.get("codec", cls.codec),
            sample_rate=int(config.get("sample_rate", cls.sample_rate)),
            channels=int(config.get("channels", cls.channels)),
            source_name=config.get("source_name", cls.source_name),
            join_interface=config.get("join_interface", cls.join_interface),
            receive_buffer=int(config.get("receive_buffer", cls.receive_buffer)),
            frame_timeout=float(config.get("frame_timeout", cls.frame_timeout)),
            reconnect_delay=float(config.get("reconnect_delay", cls.reconnect_delay)),
            source_metadata=dict(config.get("source_metadata", {})),
        )

    def with_options(self, **kwargs: Any) -> AudioConfig:
        """Return a copy with selected fields overridden (immutable config)."""
        return replace(self, **kwargs)
