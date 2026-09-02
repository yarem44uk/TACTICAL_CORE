"""WO-038 — Audio-to-canonical-event orchestrator.

:class:`AudioEventOrchestrator` is the integration glue that turns one audio
segment into a durably persisted canonical Event:

    receive -> decode -> transcribe -> callsign -> EventFactory -> repository.save

It reuses:
  * :class:`app.event.event.Event` (canonical Event model)
  * :class:`app.event_sources.factory.event_factory.EventFactory`
  * :class:`app.event_repository.durable.sqlalchemy_event_repository.SQLAlchemyEventRepository`

It does NOT introduce a second event model, journal, API, or persistence system.

Chronology (WO-038 §12): the event's ``timestamp`` is the occurrence time
(``occurred_at``), never silently replaced by ingestion time.  ``ingested_at`` is
``Event.created_at`` and ``canonical_seq`` is assigned by the durable repository.
"""

from __future__ import annotations

import logging
from typing import Any

from app.audio.audio_config import AudioConfig
from app.audio.audio_segment import AudioSegment
from app.audio.callsign import CallsignDetector
from app.audio.decoder import AudioDecoder
from app.audio.multicast_receiver import MulticastAudioReceiver
from app.audio.transcriber import DeterministicTestTranscriber
from app.event.event import Event
from app.event.event_types import EventType
from app.event_sources.factory.event_factory import EventFactory

logger = logging.getLogger(__name__)


def segment_to_raw(
    segment: AudioSegment,
    config: AudioConfig,
    decoder: AudioDecoder,
    transcriber: DeterministicTestTranscriber,
    callsign_detector: CallsignDetector,
) -> dict[str, Any]:
    """Turn one audio segment into an EventFactory-compatible raw dict.

    Steps: decode (ffmpeg -> PCM), transcribe (through the STT seam), detect
    callsigns (deterministic).  The original transcript is always preserved.

    The raw dict carries ``timestamp`` (occurrence time) so the EventFactory
    maps it to ``Event.timestamp``; all other fields land in ``Event.payload``.
    """
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
    """Wires the WO-038 vertical slice from audio receive to durable event.

    Args:
        config: The :class:`AudioConfig`.
        event_factory: The canonical :class:`EventFactory`.
        repository: The durable ``SQLAlchemyEventRepository`` (``save``).
        decoder: Optional :class:`AudioDecoder` (defaults to a new instance).
        transcriber: Optional :class:`DeterministicTestTranscriber` (STT seam).
        callsign_detector: Optional :class:`CallsignDetector`.
        event_type: Optional canonical :class:`EventType` for the produced event.
    """

    def __init__(
        self,
        config: AudioConfig,
        event_factory: EventFactory,
        repository: Any,
        *,
        decoder: AudioDecoder | None = None,
        transcriber: DeterministicTestTranscriber | None = None,
        callsign_detector: CallsignDetector | None = None,
        event_type: EventType | None = None,
    ) -> None:
        self._config = config
        self._event_factory = event_factory
        self._repository = repository
        self._decoder = decoder or AudioDecoder(
            sample_rate=config.sample_rate, channels=config.channels
        )
        self._transcriber = transcriber or DeterministicTestTranscriber()
        self._callsign_detector = callsign_detector or CallsignDetector()
        self._event_type = event_type
        self._receiver: MulticastAudioReceiver | None = None

    # -- segment -> raw -----------------------------------------------------

    def build_raw(self, segment: AudioSegment) -> dict[str, Any]:
        """Decode/transcribe/callsign one segment into a raw event dict."""
        return segment_to_raw(
            segment,
            self._config,
            self._decoder,
            self._transcriber,
            self._callsign_detector,
        )

    # -- segment -> canonical Event -> durable ------------------------------

    def process_segment(self, segment: AudioSegment) -> Event:
        """Build a canonical Event from a segment and persist it durably.

        Returns:
            The canonical Event that was persisted.

        Raises:
            Any exception from the event factory / repository.  The caller
            (receiver hook / test) decides how to isolate a failure; the
            receiver hook never lets a single bad segment crash the Core.
        """
        raw = self.build_raw(segment)
        event = self._event_factory.create_event(
            raw_data=raw,
            source_name=self._config.source_name,
            event_type=self._event_type,
        )
        self._repository.save(event)
        return event

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
        """Receiver hook: process one segment and persist its canonical event.

        A failure is logged and isolated (a bad segment never crashes the Core),
        mirroring the WO-038 source-failure rule.
        """
        try:
            self.process_segment(segment)
        except Exception:
            logger.exception("WO-038 orchestrator dropped segment %s", segment.content_id)
