"""WO-038 — Audio-to-canonical-event orchestrator.

:class:`AudioEventOrchestrator` is the integration glue that turns one audio
segment into the canonical input for the existing ingestion boundary:

    receive -> decode -> transcribe -> callsign -> raw dict (SourceEnvelope)

It reuses:
  * :class:`app.contracts.audio.ITranscriber` (STT seam)
  * :class:`app.audio.callsign.CallsignDetector`
  * the shared :func:`segment_to_raw` raw-dict builder

WO-048: the orchestrator is a PRODUCER of canonical input ONLY.  It does NOT
construct a canonical :class:`app.event.event.Event` and does NOT persist it.
Event creation, projection and durable persistence belong to the canonical
ingestion boundary (``AdapterRuntime`` -> ``EventFactory`` -> ``EventPipeline``),
so the single ``EventFactory.create_event`` seam (INV-1, WO-014-013) is preserved
and no duplicate persistence is possible.

The raw dicts produced here are exposed via :meth:`read_events` so they can be
drained by the existing ``AdapterRuntime`` and routed through the canonical
pipeline.

Chronology (WO-038 §12): the event's ``timestamp`` is the occurrence time
(``occurred_at``), never silently replaced by ingestion time.  ``ingested_at`` is
``Event.created_at`` and ``canonical_seq`` is assigned by the durable repository.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.audio.audio_config import AudioConfig
from app.audio.audio_segment import AudioSegment
from app.audio.callsign import CallsignDetector
from app.audio.decoder import AudioDecoder
from app.audio.multicast_receiver import MulticastAudioReceiver
from app.contracts.audio import ITranscriber

logger = logging.getLogger(__name__)


def segment_to_raw(
    segment: AudioSegment,
    config: AudioConfig,
    decoder: AudioDecoder,
    transcriber: Any,  # requires the richer transcribe_detailed seam (WO-038 legacy path)
    callsign_detector: CallsignDetector,
) -> dict[str, Any]:
    """Turn one audio segment into an EventFactory-compatible raw dict.

    Steps: decode (ffmpeg -> PCM, or pass-through when the segment already
    carries PCM), transcribe (through the STT seam), detect callsigns
    (deterministic).  The original transcript is always preserved.

    The raw dict carries ``timestamp`` (occurrence time) so the EventFactory
    maps it to ``Event.timestamp``; all other fields land in ``Event.payload``.

    ``transcriber`` MUST be non-``None``; a ``None`` transcriber is a fail-closed
    state and raises rather than fabricating a transcript (WO-041-CORR F-01).
    """
    if transcriber is None:
        raise ValueError("segment_to_raw requires a transcriber (fail-closed)")
    if segment.is_pcm:
        # The segment already carries decoded PCM (WO-039-A real RTP path):
        # no ffmpeg decode is performed for the verified PT=8 / A-law path.
        pcm = segment.audio_bytes
    else:
        pcm = decoder.decode_segment(segment.audio_bytes, config.codec)
    transcript_result = transcriber.transcribe_detailed(
        content_id=segment.content_id,
        audio_data=pcm,
        occurred_at=segment.occurred_at,
        sample_rate=config.sample_rate,
        channels=config.channels,
    )
    callsign_result = callsign_detector.detect(transcript_result.text)

    raw: dict[str, Any] = {
        # ``timestamp`` is a factory-recognized protocol key: it maps to
        # ``Event.timestamp`` (occurrence time).  Serialized to ISO so it is
        # JSON-serialisable in the event metadata.
        "timestamp": segment.occurred_at.isoformat(),
        "occurred_at": segment.occurred_at.isoformat(),
        "content_id": segment.content_id,
        "transcript": transcript_result.text,
        "detected_callsigns": callsign_result.detected_callsigns,
        "confidence": callsign_result.confidence,
        "detection_method": callsign_result.detection_method,
        "stt_metadata": transcript_result.metadata,
        "audio_metadata": dict(config.source_metadata),
    }
    # A single canonical callsign for operator convenience (mirrors radio
    # payload semantics).  Never loses the full callsign list.
    if callsign_result.detected_callsigns:
        raw["callsign"] = callsign_result.detected_callsigns[0]
    return raw


class AudioEventOrchestrator:
    """Wires the WO-038 vertical slice from audio receive to canonical input.

    WO-048: the orchestrator is a PRODUCER of canonical input ONLY.  It builds
    the raw dict (SourceEnvelope) that the existing ingestion boundary
    (``AdapterRuntime`` -> ``EventFactory`` -> ``EventPipeline``) turns into a
    canonical Event.  It does NOT construct a canonical Event and does NOT
    persist it; it does NOT own an ``EventRepository`` and does NOT instantiate
    an ``EventPipeline``.

    Args:
        config: The :class:`AudioConfig`.
        decoder: Optional :class:`AudioDecoder` (defaults to a new instance).
        transcriber: Optional :class:`app.contracts.audio.ITranscriber`.  This is
            the WO-038 TCA1 (non-RTP) test/compatibility seam.  It is NOT a
            production default: when omitted the orchestrator runs fail-closed
            (no STT) rather than silently substituting
            ``DeterministicTestTranscriber`` (WO-041-CORR F-01).
        callsign_detector: Optional :class:`CallsignDetector`.
    """

    def __init__(
        self,
        config: AudioConfig,
        *,
        decoder: AudioDecoder | None = None,
        transcriber: ITranscriber | None = None,
        callsign_detector: CallsignDetector | None = None,
    ) -> None:
        self._config = config
        self._decoder = decoder or AudioDecoder(
            sample_rate=config.sample_rate, channels=config.channels
        )
        self._transcriber = transcriber
        self._callsign_detector = callsign_detector or CallsignDetector()
        self._receiver: MulticastAudioReceiver | None = None
        # WO-048: queue of raw dicts (canonical input) awaiting the ingestion
        # boundary.  Drained via read_events() by an AdapterRuntime.
        self._queue: list[dict[str, Any]] = []
        self._queue_lock = threading.Lock()

    # -- segment -> raw -----------------------------------------------------

    def build_raw(self, segment: AudioSegment) -> dict[str, Any]:
        """Decode/transcribe/callsign one segment into a raw event dict.

        Fail-closed (WO-041-CORR F-01): when no transcriber is configured the
        call raises rather than fabricating a transcript.
        """
        if self._transcriber is None:
            raise ValueError(
                "no STT transcriber configured; cannot transcribe segment (fail-closed)"
            )
        return segment_to_raw(
            segment,
            self._config,
            self._decoder,
            self._transcriber,
            self._callsign_detector,
        )

    # -- segment -> canonical input (SourceEnvelope) -------------------------

    def process_segment(self, segment: AudioSegment) -> dict[str, Any]:
        """Produce the canonical input (raw dict / SourceEnvelope) for the
        ingestion boundary.

        WO-048: this does NOT construct a canonical ``Event`` and does NOT
        persist it.  Event creation, projection and durable persistence belong
        to the canonical pipeline (``AdapterRuntime`` -> ``EventFactory`` ->
        ``EventPipeline``).  The returned dict is shaped for
        ``EventFactory.create_event``.

        Returns:
            The raw dict (SourceEnvelope) for the canonical ingestion boundary.

        Raises:
            ValueError: If no STT transcriber is configured (fail-closed,
                WO-041-CORR F-01).
        """
        return self.build_raw(segment)

    def read_events(self) -> list[dict[str, Any]]:
        """Drain queued canonical-input raw dicts for the ingestion boundary.

        Each dict is shaped for ``EventFactory.create_event``.  Returns an empty
        list when nothing is queued.  This mirrors the
        ``IEventSourceAdapter.read_events()`` contract so an ``AdapterRuntime``
        can consume the orchestrator's output directly.
        """
        with self._queue_lock:
            pending = self._queue
            self._queue = []
        return pending

    def pending_count(self) -> int:
        """Number of queued, not-yet-read canonical-input raw dicts."""
        with self._queue_lock:
            return len(self._queue)

    # -- receiver lifecycle --------------------------------------------------

    def start(self) -> None:
        """Start the multicast receiver and begin processing segments."""
        if self._receiver is not None:
            return
        self._receiver = MulticastAudioReceiver(
            self._config, on_segment=self._on_segment
        )
        self._receiver.start()

    def stop(self) -> None:
        """Stop the multicast receiver."""
        if self._receiver is None:
            return
        self._receiver.stop()
        self._receiver = None

    def is_active(self) -> bool:
        """Whether the receiver is currently running."""
        return self._receiver is not None and self._receiver.is_active()

    def _on_segment(self, segment: AudioSegment) -> None:
        """Receiver hook: produce the canonical-input raw dict and queue it.

        WO-048: the orchestrator never persists.  The queued raw dict is drained
        via :meth:`read_events` by the canonical ingestion boundary
        (``AdapterRuntime``).  A failure is logged and isolated (a bad segment
        never crashes the Core), mirroring the WO-038 source-failure rule.
        """
        try:
            raw = self.process_segment(segment)
        except Exception:
            logger.exception("WO-038 orchestrator dropped segment %s", segment.content_id)
            return
        with self._queue_lock:
            self._queue.append(raw)
