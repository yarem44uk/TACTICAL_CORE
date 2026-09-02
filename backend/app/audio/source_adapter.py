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
        self._receiver: MulticastAudioReceiver | None = None
        self._credentials_ref = definition.credentials_ref

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
        """Start the adapter and its multicast receiver.  Idempotent."""
        super().start()
        if self._receiver is None:
            self._receiver = MulticastAudioReceiver(
                self._config, on_segment=self._on_segment
            )
        self._receiver.start()

    def stop(self) -> None:
        """Stop the adapter and its receiver.  Idempotent."""
        if self._receiver is not None:
            self._receiver.stop()
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


def make_multicast_audio_adapter(
    definition: SourceDefinition,
) -> MulticastAudioSourceAdapter:
    """Adapter builder compatible with ``AdapterFactory.register_type``.

    Returns a configured, unstarted :class:`MulticastAudioSourceAdapter`.
    """
    return MulticastAudioSourceAdapter(definition=definition)
