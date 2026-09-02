"""WO-038 — Audio segment and multicast frame codec.

An :class:`AudioSegment` is the unit of work carried through the WO-038
pipeline: a real audio payload (bytes), a deterministic ``content_id`` (used by
the test transcriber and event identity), and the occurrence time.

The multicast datagram is framed so a single packet self-describes a segment:

    [4-byte magic "TCA1"]
    [4-byte header length (big-endian)]
    [header JSON bytes]
    [audio payload bytes]

The header JSON carries ``content_id``, optional ``occurred_at`` (ISO-8601 UTC)
and optional ``metadata``.  The audio payload is the real audio stream that is
decoded by ffmpeg before STT.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Magic prefix for a WO-038 multicast audio frame.
_FRAME_MAGIC = b"TCA1"


@dataclass(frozen=True)
class AudioSegment:
    """One received audio segment ready for decode/STT/callsign.

    Attributes:
        content_id: Deterministic identifier for the audio content.  Used by the
            deterministic test transcriber to select a known transcript and by
            the canonical event identity for de-duplication.
        audio_bytes: The raw audio payload (as carried in the multicast frame).
        occurred_at: The occurrence time of the transmission.  When the frame
            carries an explicit ``occurred_at`` it is used; otherwise the
            receive time is used.  Never replaced by ingestion time.
        received_at: When the datagram was received (ingestion reference).
        metadata: Extra per-segment metadata carried on the frame.
    """

    content_id: str
    audio_bytes: bytes
    occurred_at: datetime
    received_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)
    is_pcm: bool = False

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            # Normalise naive timestamps to UTC.
            object.__setattr__(
                self, "occurred_at", self.occurred_at.replace(tzinfo=timezone.utc)
            )
        if self.received_at.tzinfo is None:
            object.__setattr__(
                self, "received_at", self.received_at.replace(tzinfo=timezone.utc)
            )


def encode_frame(
    audio_bytes: bytes,
    content_id: str,
    occurred_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> bytes:
    """Encode an audio segment into a multicast UDP frame.

    Args:
        audio_bytes: The raw audio payload.
        content_id: Deterministic content identifier.
        occurred_at: Optional explicit occurrence time.  When omitted the
            receiver stamps the receive time.
        metadata: Optional extra per-segment metadata.

    Returns:
        The framed bytes ready to send as one UDP datagram.
    """
    header: dict[str, Any] = {
        "content_id": content_id,
        "metadata": metadata or {},
    }
    if occurred_at is not None:
        header["occurred_at"] = occurred_at.isoformat()
    header_bytes = json.dumps(header, ensure_ascii=False).encode("utf-8")
    return (
        _FRAME_MAGIC
        + struct.pack(">I", len(header_bytes))
        + header_bytes
        + audio_bytes
    )


def decode_frame(payload: bytes) -> AudioSegment:
    """Decode a multicast UDP frame into an :class:`AudioSegment`.

    Args:
        payload: The datagram bytes produced by :func:`encode_frame`.

    Returns:
        An :class:`AudioSegment`.

    Raises:
        ValueError: If the payload is malformed (bad magic, truncated header,
            non-JSON header, or a missing ``content_id``).
    """
    if len(payload) < 8 or payload[:4] != _FRAME_MAGIC:
        raise ValueError("malformed WO-038 frame: bad magic/truncated header")
    header_len = struct.unpack(">I", payload[4:8])[0]
    header_end = 8 + header_len
    if header_end > len(payload):
        raise ValueError("malformed WO-038 frame: truncated header")
    try:
        header = json.loads(payload[8:header_end].decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"malformed WO-038 frame: invalid header JSON: {exc}") from exc

    content_id = header.get("content_id")
    if not content_id or not isinstance(content_id, str):
        raise ValueError("malformed WO-038 frame: missing content_id")

    audio_bytes = payload[header_end:]
    occurred_at: datetime | None = None
    raw_occurred = header.get("occurred_at")
    if raw_occurred is not None:
        try:
            occurred_at = datetime.fromisoformat(
                str(raw_occurred).replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        except ValueError as exc:
            raise ValueError(
                f"malformed WO-038 frame: invalid occurred_at: {raw_occurred}"
            ) from exc

    received_at = datetime.now(timezone.utc)
    if occurred_at is None:
        occurred_at = received_at

    metadata = header.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    return AudioSegment(
        content_id=content_id,
        audio_bytes=audio_bytes,
        occurred_at=occurred_at,
        received_at=received_at,
        metadata=metadata,
    )
