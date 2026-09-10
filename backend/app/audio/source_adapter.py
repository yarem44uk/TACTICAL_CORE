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
from app.audio.flow_router import FlowRouter
from app.audio.multicast_receiver import MulticastAudioReceiver
from app.audio.orchestrator import segment_to_raw
from app.audio.recorder import TransmissionRecorder
from app.audio.recording_config import RecordingConfig
from app.audio.rtp_receiver import RtpPcmFrame, RtpReceiver
from app.audio.stt_config import SttConfig, SttConfigError
from app.audio.stt_seam import (
    SttEngineError,
    SttEngineUnavailableError,
    build_transcriber,
)
from app.audio.stt_worker import SttJob, SttWorker
from app.contracts.audio import ITranscriber
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
        transcriber: Optional :class:`app.contracts.audio.ITranscriber`.  This is
            the explicit WO-038 TCA1 (non-RTP) test/compatibility seam.  It is
            NOT a production default: when omitted the adapter runs fail-closed
            (no STT) rather than silently substituting
            ``DeterministicTestTranscriber`` (WO-041-CORR F-01).
        callsign_detector: Optional :class:`CallsignDetector`.
    """

    def __init__(
        self,
        definition: SourceDefinition,
        *,
        config: AudioConfig | None = None,
        decoder: AudioDecoder | None = None,
        transcriber: ITranscriber | None = None,
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
        # No production default transcriber (WO-041-CORR F-01): the TCA1
        # (non-RTP) path only transcribes when an explicit transcriber is
        # supplied.  An absent transcriber is fail-closed, never a
        # DeterministicTestTranscriber fallback.
        self._transcriber = transcriber
        self._callsign_detector = callsign_detector or CallsignDetector()
        self._queue: list[dict[str, Any]] = []
        self._queue_lock = threading.Lock()
        self._receiver: Any = None
        self._credentials_ref = definition.credentials_ref
        # WO-039-B / WO-055: per-source recording pipeline.  ``_rec_cfg`` drives
        # both the backward-compat single recorder (``_recorder``, used by
        # direct-drive callers such as WO-052) and the production per-flow
        # recorders created by ``_flow_router`` for the real RTP socket path.
        self._rec_cfg = RecordingConfig.from_source_definition(definition.config)
        self._recording_enabled = self._rec_cfg.enabled
        self._recorder_impl = recorder
        self._flow_router = None
        if self._recorder_impl is None and self._recording_enabled:
            # WO-055: route the RTP socket path by UDP source identity.  Each
            # distinct flow gets its own tracker + TransmissionRecorder so two
            # talkers on one group/port cannot contaminate one another.
            self._flow_router = FlowRouter(
                recorder_factory=self._make_flow_recorder,
                expected_payload_type=self._config.payload_type,
            )

        # WO-041-CORR F-03: the bounded WAV STT worker is the ONLY intended
        # production transcription boundary.  A finalized WAV recording is the
        # STT input; transcript events are derived from the WAV master, never
        # from individual RTP packets.  When a worker is not supplied explicitly
        # it is built from the source STT configuration; a source with STT
        # disabled yields no worker, and STT enabled with no authorized engine
        # yields a fail-closed (UNAVAILABLE) worker.  It is only started when an
        # engine is actually registered (``available``).
        self._stt_worker = stt_worker
        if self._stt_worker is None:
            self._stt_worker = _build_production_stt_worker(
                definition, self._config
            )
        if self._stt_worker is not None:
            # Route transcript events into the adapter's read_events() queue.
            self._stt_worker.on_transcript = self._on_transcript
            if self._stt_worker.available:
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

    @property
    def stt_state(self) -> str:
        """Explicit production STT state (WO-041-CORR).

        Returns ``"DISABLED"`` when STT is disabled for the source (no worker),
        ``"UNAVAILABLE"`` when STT is enabled but no authorized acoustic engine is
        registered (fail-closed, no fake transcript), and ``"AVAILABLE"`` when an
        engine is registered.
        """
        if self._stt_worker is None:
            return "DISABLED"
        return self._stt_worker.state

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
                if self._flow_router is not None:
                    # WO-055: production per-flow isolation for the RTP socket.
                    self._receiver = RtpReceiver(
                        self._config,
                        on_pcm=self._on_pcm,
                        flow_router=self._flow_router,
                    )
                else:
                    self._receiver = RtpReceiver(
                        self._config, on_pcm=self._on_pcm
                    )
            else:
                self._receiver = MulticastAudioReceiver(
                    self._config, on_segment=self._on_segment
                )
        self._receiver.start()

    def stop(self) -> None:
        """Stop the adapter and its receiver.  Idempotent."""
        if self._receiver is not None:
            self._receiver.stop()
        if self._flow_router is not None:
            try:
                self._flow_router.shutdown_all()
            except Exception as exc:  # noqa: BLE001 - never crash stop()
                logger.warning(
                    "MulticastAudioSourceAdapter '%s' flow-router shutdown error: %s",
                    self._definition.name,
                    exc,
                )
        if self._recorder_impl is not None:
            try:
                self._recorder_impl.on_shutdown()
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

        This is the WO-038 ``TCA1`` (non-RTP) test/compatibility path.  A segment
        is only transcribed when an explicit transcriber is supplied.  When no
        transcriber is configured the segment is dropped fail-closed — no fake
        transcript is produced (WO-041-CORR F-01).  Failures are isolated
        per-segment (a bad frame never crashes the Core).
        """
        if self._transcriber is None:
            logger.warning(
                "MulticastAudioSourceAdapter '%s' dropped segment %s: "
                "no STT transcriber (fail-closed)",
                self._definition.name,
                segment.content_id,
            )
            return
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
        """RTP receiver hook: feed the decoded PCM frame to the recorder.

        The authoritative audio accumulation path is the per-source
        :class:`TransmissionRecorder` (VAD -> WAV master).  A finalized recording
        is handed to the :class:`SttWorker` via ``_on_recording`` so the derived
        transcript is produced off the receiver thread.

        WO-041-CORR F-02: NO packet-level transcript/STT event is produced from an
        individual RTP packet.  The legacy per-packet ``_on_segment`` ->
        ``segment_to_raw`` -> deterministic-transcriber path is eliminated for the
        RTP transport; the only STT input is the finalized WAV master.
        """
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

    @property
    def _recorder(self) -> TransmissionRecorder | None:
        """Backward-compat single recorder.

        WO-055 keeps a single ``TransmissionRecorder`` for direct-drive callers
        (e.g. WO-052 exercises ``adapter._recorder`` directly).  It is created
        lazily on first access so the production RTP socket path — which uses the
        per-flow recorders owned by ``_flow_router`` — never instantiates an
        unused recorder.  Returns ``None`` when recording is disabled for the
        source.
        """
        if self._recorder_impl is None and self._recording_enabled:
            self._recorder_impl = TransmissionRecorder(
                self._config, self._rec_cfg, on_recording=self._on_recording
            )
        return self._recorder_impl

    def _make_flow_recorder(self, flow_key: Any) -> TransmissionRecorder | None:
        """Create a per-flow ``TransmissionRecorder`` (WO-055 flow isolation).

        Each distinct UDP source flow on a group/port gets its own recorder, so
        two talkers never share VAD / segmenter / recording state.  The recorder
        feeds finalized recordings through the same ``_on_recording`` hook as the
        backward-compat recorder, so the canonical event path is unchanged.
        """
        return TransmissionRecorder(
            self._config, self._rec_cfg, on_recording=self._on_recording
        )


def make_multicast_audio_adapter(
    definition: SourceDefinition,
) -> MulticastAudioSourceAdapter:
    """Adapter builder compatible with ``AdapterFactory.register_type``.

    Returns a configured, unstarted :class:`MulticastAudioSourceAdapter`.
    """
    return MulticastAudioSourceAdapter(definition=definition)


def _build_production_stt_worker(
    definition: SourceDefinition,
    audio_config: AudioConfig,
) -> SttWorker | None:
    """Build a production :class:`SttWorker` from the source STT configuration.

    Reads the optional ``stt`` block from ``definition.config`` (e.g. ``enabled``,
    ``engine``, ``model_path``, ``language``).

    Returns ``None`` when STT is disabled for the source.  When STT is enabled but
    no authorized acoustic engine is registered (or the configuration is invalid),
    a worker is still created in an explicit ``UNAVAILABLE`` (fail-closed) state —
    it NEVER fabricates a transcript and NEVER falls back to
    ``DeterministicTestTranscriber`` (WO-041-CORR F-01/F-03).

    The worker is engine-neutral and offline: no engine is selected here, no model
    is downloaded, and no network is touched.
    """
    stt_cfg = SttConfig.from_dict(definition.config.get("stt"))
    if not stt_cfg.enabled:
        return None
    transcriber: ITranscriber | None = None
    try:
        transcriber = build_transcriber(stt_cfg)
    except (SttEngineError, SttConfigError) as exc:
        logger.warning(
            "WO-041-CORR STT unavailable for source %r: %s",
            audio_config.source_name,
            exc,
        )
        transcriber = None
    return SttWorker(
        transcriber,
        source=audio_config.source_name,
        language=stt_cfg.language,
    )
