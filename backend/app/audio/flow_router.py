"""WO-055 — Per-flow (UDP source identity) isolation router.

:class:`FlowRouter` is the production seam that fixes the radio source-identity
defect.  The live :class:`~app.audio.rtp_receiver.RtpReceiver` previously held a
single :class:`~app.audio.rtp_stream.RtpStreamTracker` for the whole socket, so
two independent RTP talkers sharing one multicast group/port were multiplexed
into one tracker and one :class:`~app.audio.recorder.TransmissionRecorder`,
corrupting per-talker sequence/duplicate state and merging transmissions.

This router keys processing by the UDP source identity:

    FlowKey = (src_ip, src_port, dst_port)

so that each distinct UDP flow owns its own RTP tracker and its own recording
pipeline (VAD / segmenter / recorder).  The invariant it enforces is:

    A -> B -> A   preserves independent state.

That is, packets from A always belong to A's flow; B never contaminates A's RTP
tracking or recording state; and when A resumes after B, A's previous state is
still present.

Design constraints honoured:
  * Routing happens BEFORE the PCM frame is created — the frame is never used as
    a routing key, so :class:`~app.audio.rtp_receiver.RtpPcmFrame` is not
    expanded for routing.
  * The recorder is an optional per-flow component; a ``None`` recorder factory
    (or a factory returning ``None``) yields a flow that tracks RTP state but
    does not record.
  * The flow map is bounded by ``max_flows`` and evicts the least-recently-used
    flow deterministically (finalizing its recorder) so memory cannot grow
    without bound.
  * The receiver is single-threaded; a lock on the flow map is sufficient for
    safe get_or_create / eviction on the receiver thread.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.audio.rtp_stream import RtpStreamTracker

# Default bound on concurrently-tracked flows.  A single group/port can carry a
# handful of talkers; this cap is generous but guarantees bounded memory.
DEFAULT_MAX_FLOWS = 64


@dataclass(frozen=True)
class FlowKey:
    """Deterministic UDP flow identity used to isolate radio processing.

    Attributes:
        src_ip: Source IPv4 address from ``recvfrom``.
        src_port: Source UDP port from ``recvfrom``.
        dst_port: The bound destination UDP port (the radio channel).
    """

    src_ip: str
    src_port: int
    dst_port: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "src_ip": self.src_ip,
            "src_port": self.src_port,
            "dst_port": self.dst_port,
        }


@dataclass
class FlowPipeline:
    """Per-flow processing state: an RTP tracker plus an optional recorder."""

    flow_key: FlowKey
    tracker: RtpStreamTracker
    recorder: Any = None
    created_at: float = field(default_factory=lambda: _monotonic())
    last_access: float = field(default_factory=lambda: _monotonic())

    def touch(self) -> None:
        self.last_access = _monotonic()


def _monotonic() -> float:
    """Monotonic clock for LRU bookkeeping (no wall-clock dependency)."""
    import time

    return time.monotonic()


class FlowRouter:
    """Routes UDP source identity to per-flow RTP tracker + recorder pipelines.

    Args:
        recorder_factory: Callable ``(FlowKey) -> recorder|None`` invoked on
            first packet of a new flow.  Returns the per-flow recorder (e.g. a
            :class:`~app.audio.recorder.TransmissionRecorder`) or ``None`` to
            track RTP state without recording.
        expected_payload_type: Optional payload type handed to each new
            :class:`RtpStreamTracker`.
        max_flows: Hard bound on concurrently-tracked flows.  When exceeded the
            least-recently-used flow is evicted (its recorder finalized) so the
            map cannot grow without bound.
    """

    def __init__(
        self,
        recorder_factory: Callable[[FlowKey], Any] | None = None,
        *,
        expected_payload_type: int | None = None,
        max_flows: int = DEFAULT_MAX_FLOWS,
    ) -> None:
        self._recorder_factory = recorder_factory
        self._expected_payload_type = expected_payload_type
        self._max_flows = max(1, int(max_flows))
        self._pipelines: OrderedDict[FlowKey, FlowPipeline] = OrderedDict()
        self._lock = threading.Lock()

    # -- routing ------------------------------------------------------------

    def get_or_create(self, flow_key: FlowKey) -> FlowPipeline:
        """Return the per-flow pipeline for ``flow_key``, creating it on demand.

        Bounded: if the map is at ``max_flows`` the least-recently-used flow is
        evicted (recorder finalized) before the new flow is created.
        """
        with self._lock:
            pipeline = self._pipelines.get(flow_key)
            if pipeline is not None:
                pipeline.touch()
                self._pipelines.move_to_end(flow_key)
                return pipeline
            while len(self._pipelines) >= self._max_flows:
                oldest_key, oldest_pipeline = self._pipelines.popitem(last=False)
                self._finalize_pipeline(oldest_pipeline)
            tracker = RtpStreamTracker(
                expected_payload_type=self._expected_payload_type
            )
            recorder = (
                self._recorder_factory(flow_key)
                if self._recorder_factory is not None
                else None
            )
            pipeline = FlowPipeline(
                flow_key=flow_key, tracker=tracker, recorder=recorder
            )
            self._pipelines[flow_key] = pipeline
            return pipeline

    def has_flow(self, flow_key: FlowKey) -> bool:
        with self._lock:
            return flow_key in self._pipelines

    def flow_count(self) -> int:
        with self._lock:
            return len(self._pipelines)

    def flows(self) -> list[FlowKey]:
        with self._lock:
            return list(self._pipelines.keys())

    # -- lifecycle ----------------------------------------------------------

    def shutdown_all(self) -> None:
        """Finalize and drop every per-flow pipeline (recorder on_shutdown)."""
        with self._lock:
            pipelines = list(self._pipelines.values())
            self._pipelines.clear()
        for pipeline in pipelines:
            self._finalize_pipeline(pipeline)

    # -- observability ------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Aggregate per-flow tracker stats plus a per-flow inventory."""
        with self._lock:
            pipelines = list(self._pipelines.values())
        agg = {
            "packets_received": 0,
            "packets_dropped": 0,
            "duplicates": 0,
            "sequence_gaps": 0,
            "out_of_order": 0,
            "bytes_received": 0,
        }
        flows: list[dict[str, Any]] = []
        for pipeline in pipelines:
            snap = pipeline.tracker.snapshot()
            for key in agg:
                agg[key] += snap.get(key, 0)
            flows.append(
                {
                    "flow": pipeline.flow_key.as_dict(),
                    "tracker": snap,
                    "recording": (
                        pipeline.recorder.snapshot()
                        if pipeline.recorder is not None and hasattr(
                            pipeline.recorder, "snapshot"
                        )
                        else None
                    ),
                }
            )
        return {
            "flow_count": len(pipelines),
            "max_flows": self._max_flows,
            **agg,
            "flows": flows,
        }

    # -- internals ----------------------------------------------------------

    def _finalize_pipeline(self, pipeline: FlowPipeline) -> None:
        """Finalize a pipeline's recorder so eviction never loses a recording."""
        recorder = pipeline.recorder
        if recorder is None:
            return
        shutdown = getattr(recorder, "on_shutdown", None)
        if shutdown is not None:
            try:
                shutdown()
            except Exception:  # noqa: BLE001 - never let eviction crash the router
                pass
