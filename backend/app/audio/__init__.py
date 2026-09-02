"""WO-038 — Multicast Audio -> STT -> Callsign -> Durable Event pipeline.

This package implements the first real end-to-end product vertical slice for
TACTICAL_CORE:

    MULTICAST UDP AUDIO
            |
            v
        RECEIVE (MulticastAudioReceiver)
            |
            v
        DECODE (AudioDecoder, ffmpeg)
            |
            v
        STT (ITranscriber seam -> DeterministicTestTranscriber)
            |
            v
        CALLSIGN DETECTION (CallsignDetector)
            |
            v
        CANONICAL EVENT (EventFactory)
            |
            v
        DURABLE EVENT REPOSITORY (SQLAlchemyEventRepository)
            |
            v
        OPERATOR API / SSE -> OPERATOR UI

It REUSES the existing Canonical Event model, EventFactory, durable repository,
source-adapter architecture (IEventSourceAdapter / SourceDefinition /
AdapterFactory) and operator API/UI.  It introduces NO second event model, NO
second journal, NO second API and NO second persistence system.

The STT seam is implemented by :class:`DeterministicTestTranscriber`, a
deliberately NON-acoustic test transcriber (per WO-038 authorization).  It is
NOT production speech recognition; the `ITranscriber` seam remains so a real
Vosk/Whisper/faster-whisper engine can replace it without touching the Core
event architecture.
"""

from app.audio.alaw import alaw_decode_byte, alaw_encode_byte, alaw_to_pcm, pcm_to_alaw
from app.audio.audio_config import AudioConfig
from app.audio.audio_segment import AudioSegment, decode_frame, encode_frame
from app.audio.callsign import CallsignDetector, CallsignResult
from app.audio.decoder import AudioDecoder
from app.audio.multicast_receiver import MulticastAudioReceiver
from app.audio.orchestrator import AudioEventOrchestrator
from app.audio.rtp import RtpPacket, parse_rtp_packet, validate_rtp_packet
from app.audio.rtp_receiver import RtpPcmFrame, RtpReceiver
from app.audio.rtp_simulator import RtpSimulator, build_rtp_packet
from app.audio.rtp_stream import RtpDisposition, RtpStreamTracker
from app.audio.transcriber import (
    DeterministicTestTranscriber,
    TranscriptResult,
)

__all__ = [
    "AudioConfig",
    "AudioDecoder",
    "AudioEventOrchestrator",
    "AudioSegment",
    "CallsignDetector",
    "CallsignResult",
    "DeterministicTestTranscriber",
    "MulticastAudioReceiver",
    "RtpDisposition",
    "RtpPacket",
    "RtpPcmFrame",
    "RtpReceiver",
    "RtpSimulator",
    "RtpStreamTracker",
    "TranscriptResult",
    "alaw_decode_byte",
    "alaw_encode_byte",
    "alaw_to_pcm",
    "build_rtp_packet",
    "decode_frame",
    "encode_frame",
    "parse_rtp_packet",
    "pcm_to_alaw",
    "validate_rtp_packet",
]
