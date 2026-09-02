"""WO-039-A — In-process G.711 A-law (PCMA) decoder.

The verified real radio stream uses RTP payload type 8 (G.711 A-law / PCMA).
Per WO-039-A §8, the A-law decoder must be an in-process, deterministic,
dependency-free implementation — ffmpeg is NOT the primary decoder for the
PT=8 path.

This module decodes raw G.711 A-law bytes to 16-bit linear PCM (``S16LE``).
It is a pure function of its input: the same A-law byte always yields the same
PCM sample (deterministic).  The decode is validated against the reference
ffmpeg ``alaw`` decoder.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import struct

# The A-law transmitted value has the sign bit inverted (XOR mask 0x55) per
# ITU-T G.711.  Decoding first inverts this mask, then expands the
# exponent/mantissa into a 16-bit linear sample.
_ALAW_XOR_MASK = 0x55


def alaw_decode_byte(value: int) -> int:
    """Decode a single G.711 A-law byte to a signed 16-bit linear sample.

    Args:
        value: An A-law byte (0..255).

    Returns:
        The linear PCM sample as a signed int (range approx -32256..32256).

    Note:
        Matches the reference ffmpeg ``alaw2linear`` decoder exactly.
    """
    a = value ^ _ALAW_XOR_MASK
    t = (a & 0x0F) << 4
    segment = (a & 0x70) >> 4
    if segment == 0:
        t += 8
    elif segment == 1:
        t += 0x108
    else:
        t += 0x108
        t <<= segment - 1
    return t if (a & 0x80) else -t


def alaw_to_pcm(alaw_bytes: bytes) -> bytes:
    """Decode an A-law payload to interleaved 16-bit little-endian PCM.

    Args:
        alaw_bytes: The raw G.711 A-law payload bytes (one sample per byte).

    Returns:
        PCM ``S16LE`` bytes.  Each input byte produces exactly one 2-byte
        little-endian sample.  An empty input returns ``b""``.

    Note:
        The verified stream is mono / 8000 Hz, so the output is a single
        interleaved channel; ``alaw_to_pcm`` does not itself re-channelize.
        Channel/sample-rate metadata is carried by the caller (receiver /
        adapter).
    """
    if not alaw_bytes:
        return b""
    return struct.pack(
        f"<{len(alaw_bytes)}h", *(alaw_decode_byte(b) for b in alaw_bytes)
    )


def alaw_encode_byte(sample: int) -> int:
    """Encode a signed 16-bit linear sample to one G.711 A-law byte.

    Args:
        sample: A signed linear PCM sample (approx -32768..32767).

    Returns:
        The A-law byte (0..255).

    Note:
        Lossy (matches ITU-T G.711 quantization).  Used by the RTP simulator
        to produce real A-law payloads from PCM for the loopback tests.
    """
    sample = int(sample)
    # A-law transmitted code has the sign bit inverted (ITU-T G.711): a
    # non-negative sample carries the sign bit SET so that after the 0x55
    # XOR in the decoder, bit 7 is 1 (positive).
    sign = 0x80 if sample >= 0 else 0x00
    if sample < 0:
        sample = -sample
    sample = min(sample, 0x7FFF)
    if sample < 256:
        alaw = sample >> 4
    else:
        segment = 0
        while sample > 511:
            sample >>= 1
            segment += 1
        alaw = ((sample >> 4) & 0x0F) | ((segment + 1) << 4)
    if sign:
        alaw |= 0x80
    return alaw ^ _ALAW_XOR_MASK


def pcm_to_alaw(pcm_bytes: bytes) -> bytes:
    """Encode interleaved 16-bit little-endian PCM to G.711 A-law bytes.

    Args:
        pcm_bytes: PCM ``S16LE`` bytes (one sample per 2 bytes).

    Returns:
        A-law bytes (one byte per input sample).  An empty input returns
        ``b""``.
    """
    if not pcm_bytes:
        return b""
    count = len(pcm_bytes) // 2
    samples = struct.unpack(f"<{count}h", pcm_bytes[: count * 2])
    return bytes(alaw_encode_byte(s) for s in samples)
