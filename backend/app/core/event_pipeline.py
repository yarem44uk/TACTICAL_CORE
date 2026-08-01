"""
Event Ingestion Pipeline.

The single runtime processing layer between EventBus and Intelligence modules.
Receives CoreEvent objects only — no knowledge of connectors, protocols, or transport.

Architecture:
    External Connector → EventBus → EventPipeline → Processors

Processors execute sequentially. One processor failure MUST NEVER stop the pipeline.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Priority normalization
# ---------------------------------------------------------------------------

class Priority(str, Enum):
    """Canonical priority levels recognized by the pipeline."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


_PRIORITY_ORDER = {p.value: i for i, p in enumerate(Priority)}


def _normalize_priority(raw: Any) -> str:
    """Normalize an arbitrary priority value to a canonical string.

    Unknown / missing values fall back to 'normal'.
    """
    if raw is None:
        return Priority.NORMAL.value

    if isinstance(raw, Priority):
        return raw.value

    val = str(raw).lower().strip()
    if val in _PRIORITY_ORDER:
        return val
    return Priority.NORMAL.value


# ---------------------------------------------------------------------------
# Timestamp normalization
# ---------------------------------------------------------------------------

def _normalize_timestamp(raw: Any) -> datetime:
    """Normalize an arbitrary timestamp value to UTC datetime.

    Missing or unparseable values default to current UTC time.
    """
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)

    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            pass

    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, AttributeError):
            pass

    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Source normalization
# ---------------------------------------------------------------------------

def _normalize_source(raw: Any) -> str:
    """Normalize source identifier."""
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return "unknown"


# ---------------------------------------------------------------------------
# Pipeline Context — runtime data exchange between processors
# ---------------------------------------------------------------------------

@dataclass
class PipelineContext:
    """Mutable context propagated through the processor chain.

    Processors may attach arbitrary data for downstream processors.
    """

    pipeline_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    event_id: Optional[str] = None
    event_type: Optional[str] = None
    source: str = "unknown"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: str = Priority.NORMAL.value
    processor_results: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.monotonic)
    _cancelled: bool = False

    @property
    def processing_duration_ms(self) -> float:
        """Elapsed processing time in milliseconds."""
        return (time.monotonic() - self.started_at) * 1000.0

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        """Request pipeline to stop processing further processors."""
        self._cancelled = True

    def set_result(self, processor_name: str, result: Any) -> None:
        """Store a processor result for downstream access."""
        self.processor_results[processor_name] = result

    def get_result(self, processor_name: str, default: Any = None) -> Any:
        """Retrieve a stored processor result."""
        return self.processor_results.get(processor_name, default)


# ---------------------------------------------------------------------------
# Processor Protocol
# ---------------------------------------------------------------------------

class EventProcessor(Protocol):
    """Interface that all pipeline processors must implement.

    Processors receive the event and the shared PipelineContext.
    Failures in a processor are isolated — the pipeline continues.
    """

    @property
    def name(self) -> str:
        ...

    async def process(self, event: Any, context: PipelineContext) -> None:
        ...


# ---------------------------------------------------------------------------
# Event Pipeline
# ---------------------------------------------------------------------------

class EventPipeline:
    """Sequential event-processing pipeline.

    Architecture:
        EventBus → process(CoreEvent) → [Processor 1, Processor 2, ...]

    Processors execute in registration order.  Failures in one processor
    are logged and isolated — they do NOT stop the pipeline.

    The pipeline itself is stateless between events.  All per-event state
    lives in PipelineContext.
    """

    def __init__(self, pipeline_name: str = "default") -> None:
        self._pipeline_name = pipeline_name
        self._processors: List[EventProcessor] = []
        self._running = True
        self._statistics = {
            "total_events_processed": 0,
            "total_processors_executed": 0,
            "total_processor_failures": 0,
        }
        logger.info("EventPipeline '%s' initialized", self._pipeline_name)

    # -- public API ---------------------------------------------------------

    def register_processor(self, processor: EventProcessor) -> None:
        """Register a processor.  Duplicate names are rejected."""
        if not self._running:
            raise RuntimeError(f"Pipeline '{self._pipeline_name}' is shut down")
        if processor is None:
            raise ValueError("Processor must not be None")
        for existing in self._processors:
            if existing.name == processor.name:
                raise ValueError(
                    f"Processor '{processor.name}' is already registered"
                )
        self._processors.append(processor)
        logger.debug("Processor '%s' registered", processor.name)

    def remove_processor(self, processor_name: str) -> bool:
        """Remove a processor by name.  Returns True if removed."""
        for i, proc in enumerate(self._processors):
            if proc.name == processor_name:
                self._processors.pop(i)
                logger.debug("Processor '%s' removed", processor_name)
                return True
        return False

    async def process(self, event: Any) -> PipelineContext:
        """Process a single event through the entire processor chain.

        Creates a fresh PipelineContext, normalizes event metadata, then
        executes all registered processors sequentially.

        Returns the final PipelineContext with all processor results.
        """
        if not self._running:
            raise RuntimeError(f"Pipeline '{self._pipeline_name}' is shut down")

        context = self._build_context(event)

        self._statistics["total_events_processed"] += 1

        for processor in self._processors:
            if context.is_cancelled:
                logger.info(
                    "Pipeline '%s' processing cancelled by context", self._pipeline_name
                )
                break
            await self._execute_processor(processor, event, context)

        logger.debug(
            "Pipeline '%s' processed event %s (%.1f ms, %d/%d processors)",
            self._pipeline_name,
            context.event_id,
            context.processing_duration_ms,
            len(context.processor_results),
            len(self._processors),
        )
        return context

    async def shutdown(self) -> None:
        """Graceful shutdown.  Further process() calls raise RuntimeError."""
        self._running = False
        logger.info("Pipeline '%s' shut down", self._pipeline_name)

    @property
    def processor_names(self) -> List[str]:
        """Return the ordered list of registered processor names."""
        return [p.name for p in self._processors]

    @property
    def statistics(self) -> Dict[str, Any]:
        """Pipeline runtime statistics."""
        return dict(self._statistics)

    # -- internal -----------------------------------------------------------

    @staticmethod
    def _build_context(event: Any) -> PipelineContext:
        """Build PipelineContext from event metadata.

        Handles both dict-like events and CoreEvent dataclass objects.
        """
        if isinstance(event, dict):
            raw_id = event.get("id") or event.get("event_id")
            raw_type = event.get("event_type")
            raw_source = event.get("source")
            raw_ts = event.get("timestamp") or event.get("ts")
            raw_priority = event.get("priority")
        else:
            raw_id = getattr(event, "id", None) or getattr(event, "event_id", None)
            raw_type = getattr(event, "event_type", None)
            raw_source = getattr(event, "source", None)
            raw_ts = getattr(event, "timestamp", None) or getattr(event, "ts", None)
            raw_priority = getattr(event, "priority", None)

        return PipelineContext(
            event_id=str(raw_id) if raw_id else str(uuid.uuid4()),
            event_type=str(raw_type) if raw_type else "unknown",
            source=_normalize_source(raw_source),
            timestamp=_normalize_timestamp(raw_ts),
            priority=_normalize_priority(raw_priority),
        )

    async def _execute_processor(
        self, processor: EventProcessor, event: Any, context: PipelineContext
    ) -> None:
        """Execute a single processor with failure isolation."""
        self._statistics["total_processors_executed"] += 1
        try:
            await processor.process(event, context)
        except Exception:
            self._statistics["total_processor_failures"] += 1
            logger.exception(
                "Processor '%s' failed for event %s",
                processor.name,
                context.event_id,
            )
