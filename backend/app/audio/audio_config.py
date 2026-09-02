"""WO-038 / WO-039-A — Multicast audio source configuration.

Immutable, dataclass-based configuration for a multicast UDP audio source.
It is consumed by :class:`MulticastAudioReceiver` (WO-038 test-frame mode),
:class:`RtpReceiver` (WO-039-A real RTP mode), and
:class:`MulticastAudioSourceAdapter`.

The real radio stream verified from PCAP (WO-039-A §2) is:

    UDP multicast -> RTP v2 -> PT=8 -> G.711 A-law (PCMA)
    -> 8000 Hz / mono / 160-byte payload / +160 timestamp per packet

Two ``protocol`` modes are supported:

  * ``"tca1"`` — the WO-038 proprietary test-frame format (kept for backward
    compatibility and the deterministic test simulator).  This is NOT the
    production radio transport.
  * ``"rtp"``  — the real production transport (UDP -> RFC 3550 RTP -> A-law).

No operational address is hardcoded: every address/port/codec/rate/channel is
configured here (or, for the adapter, read from the existing
``SourceDefinition.config`` dict).

Author: Tactical Core Engineering Team
Version: 1.1
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
        protocol: ``"tca1"`` (WO-038 test frame) or ``"rtp"`` (real RTP).
        codec: Input audio codec/format.  For ``protocol="rtp"`` this is the
            RTP codec (default ``pcm_alaw``); for ``protocol="tca1"`` it is the
            input format passed to ffmpeg for decode (``None`` = auto-detect).
        payload_type: RTP payload type.  Default 8 (G.711 A-law / PCMA).
        sample_rate: Target PCM sample rate (Hz).  RTP profile default 8000.
        channels: Target PCM channel count.  RTP profile default 1 (mono).
        packetization_ms: Nominal packetization (ms) — 20 for the verified
            stream (160 bytes at 8000 Hz).
        source_name: The canonical source identifier used as the Event
            ``source`` and the adapter name.  Defaults to ``"radio"``.
        join_interface: Interface address used to join the multicast group on
            the receiving host.  ``127.0.0.1`` is the loopback interface (used
            by tests / same-host simulators).
        network_interface: Interface selection for the RTP receiver:
            ``"AUTO"`` (OS default), an explicit IPv4 address, or a named
            interface (best-effort resolution).  Ignored by the TCA1 path.
        bind_address: Local address to bind the receiving socket to.  Empty
            string binds the wildcard (all interfaces).
        receive_buffer: UDP receive buffer size in bytes.
        frame_timeout: Seconds the receiver socket waits for a datagram before
            reporting a transient receive timeout (kept small so source
            interruption is detected promptly without crashing).
        reconnect_delay: Seconds to wait before re-binding after a socket
            interruption.
    """

    multicast_address: str = "239.255.0.1"
    multicast_port: int = 50000
    protocol: str = "tca1"
    codec: str | None = None
    payload_type: int = 8
    sample_rate: int = 16000
    channels: int = 1
    packetization_ms: int = 20
    source_name: str = "radio"
    join_interface: str = "127.0.0.1"
    network_interface: str = "AUTO"
    bind_address: str = ""
    receive_buffer: int = 65536
    frame_timeout: float = 0.5
    reconnect_delay: float = 1.0
    # Optional caller-supplied stable source metadata carried on every event.
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_rtp(self) -> bool:
        """Whether this configuration selects the real RTP transport."""
        return self.protocol == "rtp"

    @classmethod
    def from_source_definition(cls, config: dict[str, Any]) -> AudioConfig:
        """Build an ``AudioConfig`` from an opaque ``SourceDefinition.config`` dict.

        Unknown keys are ignored (the config layer treats the dict as opaque).
        Missing keys fall back to defaults.  When ``protocol`` resolves to
        ``"rtp"`` the RTP-aware defaults (codec ``pcm_alaw``, 8000 Hz, mono,
        20 ms) are applied unless overridden explicitly.
        """
        if config is None:
            config = {}

        protocol = str(config.get("protocol", cls.protocol)).strip().lower()
        if protocol == "rtp":
            codec = config.get("codec", "pcm_alaw")
            sample_rate = int(config.get("sample_rate", 8000))
            channels = int(config.get("channels", 1))
            packetization_ms = int(config.get("packetization_ms", 20))
        else:
            codec = config.get("codec", cls.codec)
            sample_rate = int(config.get("sample_rate", cls.sample_rate))
            channels = int(config.get("channels", cls.channels))
            packetization_ms = int(config.get("packetization_ms", cls.packetization_ms))

        return cls(
            multicast_address=config.get("multicast_address", cls.multicast_address),
            multicast_port=int(config.get("multicast_port", cls.multicast_port)),
            protocol=protocol,
            codec=codec,
            payload_type=int(config.get("payload_type", cls.payload_type)),
            sample_rate=sample_rate,
            channels=channels,
            packetization_ms=packetization_ms,
            source_name=config.get("source_name", cls.source_name),
            join_interface=config.get("join_interface", cls.join_interface),
            network_interface=config.get("network_interface", cls.network_interface),
            bind_address=config.get("bind_address", cls.bind_address),
            receive_buffer=int(config.get("receive_buffer", cls.receive_buffer)),
            frame_timeout=float(config.get("frame_timeout", cls.frame_timeout)),
            reconnect_delay=float(config.get("reconnect_delay", cls.reconnect_delay)),
            source_metadata=dict(config.get("source_metadata", {})),
        )

    def with_options(self, **kwargs: Any) -> AudioConfig:
        """Return a copy with selected fields overridden (immutable config)."""
        return replace(self, **kwargs)
