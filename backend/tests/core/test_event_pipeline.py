"""
EventPipeline — Integration & Unit Tests.

Covers:
  1.  registration
  2.  removal
  3.  execution order
  4.  context propagation
  5.  processor exception isolation
  6.  duplicate processor rejection
  7.  empty pipeline
  8.  multiple processors
  9.  async processors
  10. shutdown
  11. performance sanity
  12. timestamp normalization
  13. priority normalization
  14. source normalization
  15. cancel propagation
  16. statistics tracking
  17. processor_results exchange
  18. CoreEvent-like object support
  19. dict event support
  20. None processor rejection
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List

import pytest

from app.core.event_pipeline import (
    EventPipeline,
    EventProcessor,
    PipelineContext,
    Priority,
    _normalize_priority,
    _normalize_source,
    _normalize_timestamp,
)


# ---------------------------------------------------------------------------
# Test fixtures & helpers
# ---------------------------------------------------------------------------

class _RecordingProcessor:
    """Simple processor that records calls for verification."""

    def __init__(self, name: str, delay: float = 0, fail: bool = False):
        self._name = name
        self._delay = delay
        self._fail = fail
        self.calls: List[Any] = []

    @property
    def name(self) -> str:
        return self._name

    async def process(self, event: Any, context: PipelineContext) -> None:
        if self._delay:
            await asyncio.sleep(self._delay)
        self.calls.append((event, context))
        if self._fail:
            raise RuntimeError(f"Processor {self._name} failed")


class _ContextWriterProcessor:
    """Processor that writes a result into context."""

    def __init__(self, name: str, key: str, value: Any):
        self._name = name
        self._key = key
        self._value = value

    @property
    def name(self) -> str:
        return self._name

    async def process(self, event: Any, context: PipelineContext) -> None:
        context.set_result(self._key, self._value)


class _CancelProcessor:
    """Processor that cancels the pipeline context."""

    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def process(self, event: Any, context: PipelineContext) -> None:
        context.cancel()


# ---------------------------------------------------------------------------
# 1. Registration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_processor():
    pipeline = EventPipeline("test")
    proc = _RecordingProcessor("proc1")
    pipeline.register_processor(proc)
    assert pipeline.processor_names == ["proc1"]


@pytest.mark.asyncio
async def test_register_multiple_processors():
    pipeline = EventPipeline("test")
    pipeline.register_processor(_RecordingProcessor("a"))
    pipeline.register_processor(_RecordingProcessor("b"))
    pipeline.register_processor(_RecordingProcessor("c"))
    assert pipeline.processor_names == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# 2. Removal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_processor():
    pipeline = EventPipeline("test")
    pipeline.register_processor(_RecordingProcessor("a"))
    pipeline.register_processor(_RecordingProcessor("b"))
    assert pipeline.remove_processor("a") is True
    assert pipeline.processor_names == ["b"]


@pytest.mark.asyncio
async def test_remove_nonexistent_processor():
    pipeline = EventPipeline("test")
    assert pipeline.remove_processor("missing") is False


# ---------------------------------------------------------------------------
# 3. Execution order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execution_order():
    pipeline = EventPipeline("test")
    order: List[str] = []

    class _OrderProcessor:
        def __init__(self, name: str):
            self._name = name

        @property
        def name(self) -> str:
            return self._name

        async def process(self, event: Any, context: PipelineContext) -> None:
            order.append(self._name)

    pipeline.register_processor(_OrderProcessor("first"))
    pipeline.register_processor(_OrderProcessor("second"))
    pipeline.register_processor(_OrderProcessor("third"))
    await pipeline.process({})
    assert order == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# 4. Context propagation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_propagation():
    pipeline = EventPipeline("test")
    ctx_ids: List[str] = []

    class _CtxProcessor:
        def __init__(self, name: str):
            self._name = name

        @property
        def name(self) -> str:
            return self._name

        async def process(self, event: Any, context: PipelineContext) -> None:
            ctx_ids.append(context.pipeline_id)

    pipeline.register_processor(_CtxProcessor("p1"))
    pipeline.register_processor(_CtxProcessor("p2"))
    await pipeline.process({})
    assert len(set(ctx_ids)) == 1  # same context through chain


# ---------------------------------------------------------------------------
# 5. Processor exception isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_processor_exception_isolation():
    pipeline = EventPipeline("test")
    good = _RecordingProcessor("good")
    bad = _RecordingProcessor("bad", fail=True)
    good2 = _RecordingProcessor("good2")
    pipeline.register_processor(good)
    pipeline.register_processor(bad)
    pipeline.register_processor(good2)
    await pipeline.process({"event_type": "test"})
    assert len(good.calls) == 1
    assert len(bad.calls) == 1  # was called despite failure
    assert len(good2.calls) == 1  # pipeline continued


# ---------------------------------------------------------------------------
# 6. Duplicate processor rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_processor_rejected():
    pipeline = EventPipeline("test")
    pipeline.register_processor(_RecordingProcessor("dup"))
    with pytest.raises(ValueError, match="already registered"):
        pipeline.register_processor(_RecordingProcessor("dup"))


# ---------------------------------------------------------------------------
# 7. Empty pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_pipeline():
    pipeline = EventPipeline("test")
    ctx = await pipeline.process({"event_type": "test"})
    assert ctx is not None
    assert ctx.processing_duration_ms >= 0


# ---------------------------------------------------------------------------
# 8. Multiple processors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_processors_execute():
    pipeline = EventPipeline("test")
    procs = [_RecordingProcessor(f"p{i}") for i in range(5)]
    for p in procs:
        pipeline.register_processor(p)
    await pipeline.process({})
    for p in procs:
        assert len(p.calls) == 1


# ---------------------------------------------------------------------------
# 9. Async processors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_processors():
    pipeline = EventPipeline("test")
    proc = _RecordingProcessor("async_proc", delay=0.01)
    pipeline.register_processor(proc)
    await pipeline.process({})
    assert len(proc.calls) == 1


# ---------------------------------------------------------------------------
# 10. Shutdown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shutdown_blocks_new_process():
    pipeline = EventPipeline("test")
    await pipeline.shutdown()
    with pytest.raises(RuntimeError, match="shut down"):
        await pipeline.process({})


@pytest.mark.asyncio
async def test_shutdown_blocks_registration():
    pipeline = EventPipeline("test")
    await pipeline.shutdown()
    with pytest.raises(RuntimeError, match="shut down"):
        pipeline.register_processor(_RecordingProcessor("late"))


# ---------------------------------------------------------------------------
# 11. Performance sanity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_performance_sanity():
    pipeline = EventPipeline("test")
    for i in range(50):
        pipeline.register_processor(_RecordingProcessor(f"perf_{i}", delay=0))
    start = asyncio.get_event_loop().time()
    for _ in range(100):
        await pipeline.process({})
    elapsed = asyncio.get_event_loop().time() - start
    # 5000 processor executions should finish in < 5s
    assert elapsed < 5.0


# ---------------------------------------------------------------------------
# 12. Timestamp normalization
# ---------------------------------------------------------------------------

def test_normalize_timestamp_naive():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    result = _normalize_timestamp(dt)
    assert result.tzinfo is not None
    assert result.tzinfo == timezone.utc


def test_normalize_timestamp_epoch():
    result = _normalize_timestamp(1609459200)
    assert result.year == 2021


def test_normalize_timestamp_iso():
    result = _normalize_timestamp("2025-06-15T10:30:00Z")
    assert result.year == 2025
    assert result.month == 6


def test_normalize_timestamp_unknown():
    result = _normalize_timestamp("not-a-date")
    assert result.year >= 2024


# ---------------------------------------------------------------------------
# 13. Priority normalization
# ---------------------------------------------------------------------------

def test_normalize_priority_known():
    assert _normalize_priority("high") == "high"
    assert _normalize_priority("critical") == "critical"
    assert _normalize_priority("low") == "low"


def test_normalize_priority_default():
    assert _normalize_priority(None) == "normal"
    assert _normalize_priority("unknown") == "normal"


def test_normalize_priority_enum():
    assert _normalize_priority(Priority.HIGH) == "high"


# ---------------------------------------------------------------------------
# 14. Source normalization
# ---------------------------------------------------------------------------

def test_normalize_source():
    assert _normalize_source("Signal") == "signal"
    assert _normalize_source("") == "unknown"
    assert _normalize_source(None) == "unknown"


# ---------------------------------------------------------------------------
# 15. Cancel propagation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_stops_processing():
    pipeline = EventPipeline("test")
    before = _RecordingProcessor("before")
    cancel = _CancelProcessor("cancel")
    after = _RecordingProcessor("after")
    pipeline.register_processor(before)
    pipeline.register_processor(cancel)
    pipeline.register_processor(after)
    await pipeline.process({})
    assert len(before.calls) == 1
    assert len(after.calls) == 0  # cancelled


# ---------------------------------------------------------------------------
# 16. Statistics tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_statistics_tracking():
    pipeline = EventPipeline("test")
    pipeline.register_processor(_RecordingProcessor("a"))
    pipeline.register_processor(_RecordingProcessor("b", fail=True))
    pipeline.register_processor(_RecordingProcessor("c"))
    await pipeline.process({})
    stats = pipeline.statistics
    assert stats["total_events_processed"] == 1
    assert stats["total_processors_executed"] == 3
    assert stats["total_processor_failures"] == 1


# ---------------------------------------------------------------------------
# 17. Processor results exchange
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_processor_results_exchange():
    pipeline = EventPipeline("test")
    pipeline.register_processor(_ContextWriterProcessor("writer", "key1", "value1"))
    pipeline.register_processor(_ContextWriterProcessor("writer2", "key2", 42))
    ctx = await pipeline.process({})
    assert ctx.get_result("key1") == "value1"
    assert ctx.get_result("key2") == 42


# ---------------------------------------------------------------------------
# 18. CoreEvent-like object support
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_coreevent_like_object():
    @dataclass
    class _MockEvent:
        event_id: str
        event_type: str
        source: str
        timestamp: datetime
        priority: str

    pipeline = EventPipeline("test")
    evt = _MockEvent(
        event_id="e-99",
        event_type="radio.tx",
        source="RadioNode",
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        priority="high",
    )
    ctx = await pipeline.process(evt)
    assert ctx.event_id == "e-99"
    assert ctx.event_type == "radio.tx"
    assert ctx.source == "radionode"
    assert ctx.priority == "high"


# ---------------------------------------------------------------------------
# 19. Dict event support
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dict_event_support():
    pipeline = EventPipeline("test")
    evt = {
        "id": "d-42",
        "event_type": "signal.msg",
        "source": "SignalConnector",
        "timestamp": "2025-03-01T08:00:00Z",
        "priority": "critical",
    }
    ctx = await pipeline.process(evt)
    assert ctx.event_id == "d-42"
    assert ctx.event_type == "signal.msg"
    assert ctx.source == "signalconnector"
    assert ctx.priority == "critical"
    assert ctx.timestamp.year == 2025


# ---------------------------------------------------------------------------
# 20. None processor rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_none_processor_rejected():
    pipeline = EventPipeline("test")
    with pytest.raises(ValueError, match="must not be None"):
        pipeline.register_processor(None)


# ---------------------------------------------------------------------------
# 21. Context processing_duration_ms
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_processing_duration():
    pipeline = EventPipeline("test")
    pipeline.register_processor(_RecordingProcessor("slow", delay=0.05))
    ctx = await pipeline.process({})
    assert ctx.processing_duration_ms >= 40  # at least 40ms


# ---------------------------------------------------------------------------
# 22. Context metadata access
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_metadata():
    pipeline = EventPipeline("test")
    pipeline.register_processor(_ContextWriterProcessor("meta", "m1", "v1"))
    ctx = await pipeline.process({})
    ctx.metadata["custom"] = True
    assert ctx.metadata["custom"] is True
