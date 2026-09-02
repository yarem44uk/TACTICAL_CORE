"""WO-038 — Multicast audio source adapter.

:class:`MulticastAudioSourceAdapter` represents the WO-038 multicast UDP audio
source through the EXISTING source/adapter architecture
(``IEventSourceAdapter`` / ``BaseEventSourceAdapter``).  It:

  * owns a :class:`MulticastAudioReceiver` (real UDP multicast receive);
  * on each received frame performs decode -> STT -> callsign detection and
    queues an EventFactory-compatible raw dict;
  * exposes the queued raw dicts via ``read_events()`` so the existing
    ``AdapterRuntime`` -> ``EventFactory`` -> ``EventPipeline`` path can convert
    them into canonical Events and persist them durably.

It is a LEAF component: it never constructs canonical Events itself and never
accesses the event pipeline / database / API directly.

Configuration is consumed exclusively through ``SourceDefinition`` (the ``config``
dict), so no operational address is hardcoded.  The builder
``make_multicast_audio_adapter`` is registered under adapter_type
``"multicast_audio"``.
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
from app.audio.orchestrator import segment_to_raw
from app.audio.recorder import TransmissionRecorder
from app.audio.recording_config import RecordingConfig
from app.audio.rtp_receiver import RtpPcmFrame, RtpReceiver
from app.audio.stt_worker import SttJob, SttWorker
from app.audio.transcriber import DeterministicTestTranscriber
from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
from app.event_sources.config.source_definition import SourceDefinition

logger = logging.getLogger(__name__)

# Stable adapter type identifier for the multicast audio source.
MULTICAST_AUDIO_ADAPTER_TYPE = "multicast_audio"


class MulticastAudioSourceAdapter(BaseEventSourceAdapter):
    """WO-013-style source adapter for multicast UDP audio.

    Args:
        definition: The :class:`SourceDefinition` for this source.  Adapter
            settings are read from ``definition.config`` (multicast_address,
            multicast_port, codec, sample_rate, channels, source_name, ...).
        config: Optional explicit :class:`AudioConfig` (overrides the dict).
        decoder: Optional :class:`AudioDecoder`.
        transcriber: Optional :class:`DeterministicTestTranscriber` (STT seam).
        callsign_detector: Optional :class:`CallsignDetector`.
    """

    def __init__(
        self,
        definition: SourceDefinition,
        *,
        config: AudioConfig | None = None,
        decoder: AudioDecoder | None = None,
        transcriber: DeterministicTestTranscriber | None = None,
        callsign_detector: CallsignDetector | None = None,
        recorder: TransmissionRecorder | None = None,
        stt_worker: SttWorker | None = None,
    ) -> None:
        super().__init__()
        self._definition = definition
        self._config = config or AudioConfig.from_source_definition(
            definition.config
        )
        self._decoder = decoder or AudioDecoder(
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
        )
        self._transcriber = transcriber or DeterministicTestTranscriber()
        self._callsign_detector = callsign_detector or CallsignDetector()
        self._queue: list[dict[str, Any]] = []
        self._queue_lock = threading.Lock()
        self._receiver: Any = None
        self._credentials_ref = definition.credentials_ref
        # WO-039-B: per-source recording pipeline.  Engaged only when the source
        # config enables VAD-driven recording.
        self._recorder = recorder
        if self._recorder is None:
            rec_cfg = RecordingConfig.from_source_definition(definition.config)
            if rec_cfg.enabled:
                self._recorder = TransmissionRecorder(
                    self._config, rec_cfg, on_recording=self._on_recording
                )

        # WO-039-C3: bounded WAV STT worker.  When a worker is supplied it is
        # wired so a finalized recording is transcribed off the receiver thread
        # and the derived transcript event flows through the same read_events()
        # -> EventFactory -> EventPipeline path as the recording event.  It is
        # only created/started when explicitly provided (or built from config),
        # so the legacy per-RTP STT path is never reactivated here.
        self._stt_worker = stt_worker
        if self._stt_worker is not None:
            # Route transcript events into the adapter's read_events() queue.
            self._stt_worker.on_transcript = self._on_transcript
            self._stt_worker.start()

        logger.info(
            "MulticastAudioSourceAdapter '%s' configured "
            "(group=%s:%d, source_name=%r, credentials_ref_present=%s)",
            definition.name,
            self._config.multicast_address,
            self._config.multicast_port,
            self._config.source_name,
            self._credentials_ref is not None,
        )

    # -- interface: source identity -----------------------------------------

    def source_name(self) -> str:
        """Return the canonical source identifier (default ``"radio"``)."""
        return self._config.source_name

    @property
    def adapter_type(self) -> str:
        """Adapter type identifier used for registration."""
        return MULTICAST_AUDIO_ADAPTER_TYPE

    # -- interface: read path -----------------------------------------------

    def read_events(self) -> list[dict[str, Any]]:
        """Return queued audio-derived raw event dicts.

        Each dict is shaped for ``EventFactory.create_event``.  If the adapter
        is not running, returns an empty list.
        """
        if not self._running:
            return []
        with self._queue_lock:
            pending = self._queue
            self._queue = []
        return pending

    def pending_count(self) -> int:
        """Number of queued, not-yet-read raw events."""
        with self._queue_lock:
            return len(self._queue)

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Start the adapter and its receiver.  Idempotent.

        For ``protocol="rtp"`` the adapter uses the real RTP receiver
        (UDP -> RTP -> G.711 A-law -> PCM); otherwise it uses the WO-038
        ``TCA1`` test-frame receiver.
        """
        super().start()
        if self._receiver is None:
            if self._config.is_rtp:
                self._receiver = RtpReceiver(self._config, on_pcm=self._on_pcm)
            else:
                self._receiver = MulticastAudioReceiver(
                    self._config, on_segment=self._on_segment
                )
        self._receiver.start()

    def stop(self) -> None:
        """Stop the adapter and its receiver.  Idempotent."""
        if self._receiver is not None:
            self._receiver.stop()
        if self._recorder is not None:
            try:
                self._recorder.on_shutdown()
            except Exception as exc:  # noqa: BLE001 - never crash stop()
                logger.warning(
                    "MulticastAudioSourceAdapter '%s' recorder shutdown error: %s",
                    self._definition.name,
                    exc,
                )
        if self._stt_worker is not None:
            try:
                self._stt_worker.stop()
            except Exception as exc:  # noqa: BLE001 - never crash stop()
                logger.warning(
                    "MulticastAudioSourceAdapter '%s' STT worker shutdown error: %s",
                    self._definition.name,
                    exc,
                )
        super().stop()
        with self._queue_lock:
            self._queue = []

    # -- internals ----------------------------------------------------------

    def _on_segment(self, segment: AudioSegment) -> None:
        """Receiver hook: decode/STT/callsign one segment and queue the raw dict.

        Failures are isolated per-segment (a bad frame never crashes the Core).
        """
        try:
            raw = segment_to_raw(
                segment,
                self._config,
                self._decoder,
                self._transcriber,
                self._callsign_detector,
            )
        except Exception as exc:  # noqa: BLE001 - isolate a malformed segment
            logger.warning(
                "MulticastAudioSourceAdapter '%s' dropped segment %s: %s",
                self._definition.name,
                segment.content_id,
                exc,
            )
            return
        with self._queue_lock:
            self._queue.append(raw)

    def _on_pcm(self, frame: RtpPcmFrame) -> None:
        """RTP receiver hook: convert a decoded PCM frame into a segment.

        The PCM is already decoded (A-law -> PCM S16LE) so the segment is
        marked ``is_pcm=True`` and no ffmpeg decode is performed downstream.
        A deterministic content id is derived from the SSRC + RTP timestamp so
        distinct frames are distinct and repeated deliveries deduplicate.

        When WO-039-B recording is enabled for the source, the frame is also fed
        to the per-source :class:`TransmissionRecorder`.
        """
        segment = AudioSegment(
            content_id=f"rtp-{frame.ssrc:x}-{frame.timestamp}",
            audio_bytes=frame.pcm,
            occurred_at=frame.received_at,
            received_at=frame.received_at,
            is_pcm=True,
            metadata={
                "rtp": True,
                "sequence_number": frame.sequence_number,
                "timestamp": frame.timestamp,
                "ssrc": frame.ssrc,
                "payload_type": frame.payload_type,
                "sample_rate": frame.sample_rate,
                "channels": frame.channels,
            },
        )
        self._on_segment(segment)
        if self._recorder is not None:
            try:
                self._recorder.on_pcm(frame)
            except Exception as exc:  # noqa: BLE001 - isolate recorder failure
                logger.warning(
                    "MulticastAudioSourceAdapter '%s' recorder error: %s",
                    self._definition.name,
                    exc,
                )

    def _on_recording(self, raw: dict[str, Any]) -> None:
        """WO-039-B recorder hook: queue a finalized-recording raw event dict.

        The raw dict flows through the existing ``read_events()`` -> EventFactory
        -> EventPipeline path (W-039-B §21), reusing the canonical event model.
        When a WO-039-C3 STT worker is present, the finalized recording is ALSO
        handed to the worker (off the RTP receiver thread) so a derived transcript
        event is produced without blocking reception.
        """
        with self._queue_lock:
            self._queue.append(raw)
        if self._stt_worker is not None:
            recording = raw.get("recording", {})
            job = SttJob(
                audio_recording_id=raw["audio_recording_id"],
                wav_path=recording.get("wav_path", ""),
                source=self._config.source_name,
                language=self._stt_worker.language,
                started_at=raw.get("occurred_at"),
                sha256=recording.get("sha256"),
            )
            self._stt_worker.submit(job)

    def _on_transcript(self, raw: dict[str, Any]) -> None:
        """WO-039-C3 STT worker hook: queue a derived transcript raw event dict.

        The transcript event flows through the same ``read_events()`` ->
        EventFactory -> EventPipeline path as the recording event, so it is a
        separate, append-only canonical event (never an UPDATE of the recording
        event).
        """
        with self._queue_lock:
            self._queue.append(raw)


def make_multicast_audio_adapter(
    definition: SourceDefinition,
) -> MulticastAudioSourceAdapter:
    """Adapter builder compatible with ``AdapterFactory.register_type``.

    Returns a configured, unstarted :class:`MulticastAudioSourceAdapter`.
    """
    return MulticastAudioSourceAdapter(definition=definition)
