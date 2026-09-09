"""
TACTICAL CORE — WO-050
Canonical Ingestion Contract Hardening

This is an ARCHITECTURAL CONTRACT suite (WO-050).  It makes the canonical
ingestion contract continuously enforceable by tests:

    Adapter / Source
           │
           │ RAW
           ▼
    AdapterRuntime          <- sole RAW → canonical Event boundary
           │
           ▼
    EventFactory            <- sole canonical Event construction boundary
           │
           │ Canonical Event
           ▼
    EventPipeline           <- sole canonical lifecycle / persistence path
           │
           ├── Durable Event Repository
           ├── Projection
           └── Checkpoint

Primary rule enforced here:

    Sources and adapters produce RAW input only. AdapterRuntime is the sole
    RAW→Canonical Event boundary. EventFactory is the sole canonical Event
    construction boundary. EventPipeline is the sole canonical
    lifecycle/persistence path.

Design constraints (WO-050 §3, §6):
  * structural checks use AST inspection (no regex-only rules, no line
    numbers, no private-attribute / formatting / comment assertions);
  * behavioural checks use the real runtime seams (AdapterRuntime ->
    EventFactory -> EventPipeline), not mocks that bypass the seam;
  * the suite protects architectural ownership, not implementation trivia;
  * no network, no background threads, no subprocess, no repository mutation.

Pre-existing note: one unrelated production module
(``intelligence/event_bus/intelligence_bus.py``) does not parse as valid
Python.  It is part of the known legacy failure set and is unrelated to the
canonical ingestion contract.  The AST scans in this suite skip unparseable
modules rather than masking the contract with a false positive.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.audio.audio_config import AudioConfig
from app.audio.audio_segment import AudioSegment
from app.audio.callsign import CallsignDetector
from app.audio.orchestrator import AudioEventOrchestrator
from app.audio.transcriber import DeterministicTestTranscriber
from app.event.event import Event
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_pipeline.interfaces.i_event_pipeline import IEventPipeline
from app.event_sources.adapters.radio_source_adapter import RadioSourceAdapter
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.identity.event_identity import EventIdentityResolver
from app.event_sources.interfaces.i_event_factory import IEventFactory
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime

# --- Paths ------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_APP_DIR = _THIS_DIR.parent / "app"
_ADAPTERS_DIR = _APP_DIR / "event_sources" / "adapters"
_RUNTIME_PATH = _APP_DIR / "event_sources" / "runtime" / "adapter_runtime.py"
_FACTORY_PATH = _APP_DIR / "event_sources" / "factory" / "event_factory.py"
_ORCHESTRATOR_PATH = _APP_DIR / "audio" / "orchestrator.py"

# Module fragments that indicate an adapter / runtime step has reached outside
# the canonical ingestion boundary into a component it must NOT own.
_FORBIDDEN_OWNERSHIP = (
    "event_pipeline",
    "event_repository",
    "repositories",
    "projection",
    "checkpoint",
    "durable",
)


# --- AST helpers (structural contract inspection) ---------------------------


def _parse(path: Path) -> ast.Module | None:
    """Parse a module into an AST, returning None for unparseable modules."""
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        # Unrelated legacy module that does not parse; skip it rather than
        # let a pre-existing failure mask the canonical ingestion contract.
        return None


def _module_imports(tree: ast.Module) -> set[str]:
    """Return the absolute module names imported by the module (any depth)."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _calls_attribute(tree: ast.Module, attr: str) -> list[ast.Call]:
    """Return Call nodes that invoke ``<obj>.attr(...)``."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
    ]


def _constructs(tree: ast.Module, name: str) -> list[ast.Call]:
    """Return Call nodes that construct ``name(...)`` (bare-name call)."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


def _adapter_paths() -> list[Path]:
    """All source-adapter production modules (leaf components).

    Only ``*_source_adapter.py`` modules are actual source adapters (they
    implement ``read_events`` / ``source_name``).  The ``*_adapter_registration.py``
    helpers are registration factories, not adapters, and are excluded.
    """
    return sorted(
        p
        for p in _ADAPTERS_DIR.iterdir()
        if p.suffix == ".py"
        and not p.name.startswith("__")
        and p.name.endswith("_source_adapter.py")
    )


def _production_modules() -> list[Path]:
    """All production modules, excluding package ``__init__`` files."""
    return sorted(p for p in _APP_DIR.rglob("*.py") if p.name != "__init__.py")


def _canonical_event_import(imports: set[str]) -> list[str]:
    """The set of canonical Event-layer imports (``app.event``)."""
    return [i for i in imports if i == "app.event" or i.startswith("app.event.")]


# --- Runtime seam helpers ---------------------------------------------------


class _FakeAdapter(IEventSourceAdapter):
    """Minimal IEventSourceAdapter exposing a fixed list of raw dicts."""

    def __init__(self, raws: list[dict[str, Any]]) -> None:
        self._raws = list(raws)
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def health(self) -> bool:
        return True

    def read_events(self) -> list[dict[str, Any]]:
        raws = self._raws
        self._raws = []
        return raws

    def source_name(self) -> str:
        return "test"


class _RecordingPipeline(IEventPipeline):
    """Records the objects passed to ``process`` (asserts canonical type)."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def process(self, event: Any) -> bool:
        self.events.append(event)
        return True

    def add_filter(self, filter_func):  # pragma: no cover - interface stub
        return None

    def remove_filter(self, filter_func):  # pragma: no cover - interface stub
        return None

    def add_before(self, middleware):  # pragma: no cover - interface stub
        return None

    def add_after(self, middleware):  # pragma: no cover - interface stub
        return None

    def clear(self) -> None:  # pragma: no cover - interface stub
        return None


class _SpyRepository:
    """Records canonical Events passed to ``save`` (persistence seam spy)."""

    def __init__(self) -> None:
        self.saved: list[Event] = []

    def save(self, event: Event) -> None:
        self.saved.append(event)


class _SpyProjection:
    """Records canonical Events passed to the projection callable."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def __call__(self, event: Event) -> None:
        self.events.append(event)


class _CountingFactory(IEventFactory):
    """Wraps a real EventFactory and counts ``create_event`` invocations."""

    def __init__(self, inner: EventFactory) -> None:
        self._inner = inner
        self.calls = 0

    def create_event(self, *args, **kwargs) -> Event:
        self.calls += 1
        return self._inner.create_event(*args, **kwargs)


def _raw() -> dict[str, Any]:
    return {
        "timestamp": "2026-09-09T10:00:00+00:00",
        "callsign": "Alpha-1",
        "frequency": "145.500",
    }


def _audio_cfg() -> AudioConfig:
    return AudioConfig(
        multicast_address="239.255.0.1",
        multicast_port=50000,
        codec="wav",
        source_name="radio",
    )


def _audio_segment() -> AudioSegment:
    occ = datetime(2026, 9, 9, 10, 31, 4, tzinfo=timezone.utc)
    return AudioSegment(
        content_id="bureviy-2",
        audio_bytes=b"pcm",
        occurred_at=occ,
        received_at=occ,
    )


def _make_orchestrator() -> AudioEventOrchestrator:
    return AudioEventOrchestrator(
        _audio_cfg(),
        transcriber=DeterministicTestTranscriber(
            phrase_map={"bureviy-2": "Буревій-2, прийом."}, default_text=""
        ),
        callsign_detector=CallsignDetector(callsigns=["Буревій-2"]),
    )


# =============================================================================
# CONTRACT-1 — RAW SOURCE OUTPUT
# =============================================================================


def test_contract1_adapters_produce_raw_only() -> None:
    """Adapters return RAW dicts and never import / construct canonical Event."""
    for path in _adapter_paths():
        tree = _parse(path)
        assert tree is not None, f"{path.name}: adapter must be valid Python"
        event_imports = _canonical_event_import(_module_imports(tree))
        assert not event_imports, (
            f"{path.name}: adapter imports canonical Event layer {event_imports} "
            "(CONTRACT-1)"
        )
        assert not _constructs(tree, "Event"), (
            f"{path.name}: adapter constructs canonical Event directly (CONTRACT-1)"
        )
        # Adapters expose RAW via read_events(); that is the only RAW entry.
        methods = {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert "read_events" in methods, (
            f"{path.name}: adapter must implement read_events() (CONTRACT-1)"
        )


# =============================================================================
# CONTRACT-2 — SINGLE RAW→EVENT SEAM
# =============================================================================


def test_contract2_single_raw_event_seam() -> None:
    """Exactly one production caller of ``EventFactory.create_event(...)``."""
    callers: list[str] = []
    for path in _production_modules():
        tree = _parse(path)
        if tree is None:
            continue  # unrelated legacy module; cannot host a working seam
        if _calls_attribute(tree, "create_event"):
            callers.append(str(path.relative_to(_APP_DIR)))

    expected = ["event_sources/runtime/adapter_runtime.py"]
    assert callers == expected, (
        "Exactly one production RAW→EventFactory caller is required "
        f"(CONTRACT-2); expected {expected}, got {callers}"
    )


# =============================================================================
# CONTRACT-3 — FACTORY OWNS NORMALIZATION
# =============================================================================


def test_contract3_factory_owns_normalization() -> None:
    """Canonical Event construction/normalization belongs to EventFactory."""
    # EventFactory must import the canonical Event layer (it is the boundary).
    factory_imports = _module_imports(_parse(_FACTORY_PATH) or ast.Module(body=[]))
    assert _canonical_event_import(factory_imports), (
        "EventFactory must import the canonical Event layer (CONTRACT-3)"
    )
    # No adapter may import the canonical Event layer or construct an Event.
    for path in _adapter_paths():
        tree = _parse(path)
        assert tree is not None, f"{path.name}: adapter must be valid Python"
        event_imports = _canonical_event_import(_module_imports(tree))
        assert not event_imports, (
            f"{path.name}: adapter must not duplicate canonical normalization "
            f"(imports {event_imports}) (CONTRACT-3)"
        )
        assert not _constructs(tree, "Event"), (
            f"{path.name}: adapter must not construct canonical Event (CONTRACT-3)"
        )


# =============================================================================
# CONTRACT-4 — PIPELINE RECEIVES CANONICAL EVENTS
# =============================================================================


def test_contract4_pipeline_receives_canonical_event() -> None:
    """The pipeline receives a canonical ``Event``, never a RAW dict."""
    pipeline = _RecordingPipeline()
    runtime = AdapterRuntime(
        adapter=_FakeAdapter([_raw()]),
        factory=EventFactory(),
        pipeline=pipeline,
    )
    runtime._process_raw(_raw())

    assert len(pipeline.events) == 1, "pipeline must receive exactly one event"
    assert isinstance(pipeline.events[0], Event), (
        "EventPipeline must receive a canonical Event, not a RAW dict (CONTRACT-4)"
    )


def test_contract4_durable_path_rejects_raw_dict() -> None:
    """The durable boundary rejects non-canonical (RAW dict) input."""
    pipeline = EventPipeline()
    with pytest.raises(TypeError):
        pipeline._process_durable({"timestamp": "2026-09-09T10:00:00+00:00"})


# =============================================================================
# CONTRACT-5 — SINGLE LIFECYCLE OWNER
# =============================================================================


def test_contract5_single_lifecycle_owner() -> None:
    """AdapterRuntime owns the source lifecycle; adapters own none of it."""
    # Adapters must not import or own pipeline / repository / projection /
    # checkpoint components.
    for path in _adapter_paths():
        tree = _parse(path)
        assert tree is not None, f"{path.name}: adapter must be valid Python"
        bad = [
            i
            for i in _module_imports(tree)
            if any(frag in i for frag in _FORBIDDEN_OWNERSHIP)
        ]
        assert not bad, (
            f"{path.name}: adapter owns a lifecycle component {bad} (CONTRACT-5)"
        )
    # AdapterRuntime is the single thread owner.
    runtime = _parse(_RUNTIME_PATH)
    assert runtime is not None
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "Thread"
        for node in ast.walk(runtime)
    ), "AdapterRuntime must be the single lifecycle (thread) owner (CONTRACT-5)"


# =============================================================================
# CONTRACT-6 — NO DIRECT SOURCE PERSISTENCE
# =============================================================================


def test_contract6_no_direct_source_persistence() -> None:
    """No adapter directly persists a canonical Event."""
    for path in _adapter_paths():
        tree = _parse(path)
        assert tree is not None, f"{path.name}: adapter must be valid Python"
        bad_imports = [
            i
            for i in _module_imports(tree)
            if any(frag in i for frag in ("event_repository", "repositories", "durable"))
        ]
        assert not bad_imports, (
            f"{path.name}: adapter imports persistence {bad_imports} (CONTRACT-6)"
        )
        assert not _calls_attribute(tree, "save"), (
            f"{path.name}: adapter calls repository.save() directly (CONTRACT-6)"
        )


# =============================================================================
# CONTRACT-7 — AUDIO IS A NORMAL SOURCE
# =============================================================================


def test_contract7_audio_is_normal_source() -> None:
    """Audio obeys the same contract: producer-only, RAW via the seam."""
    tree = _parse(_ORCHESTRATOR_PATH)
    assert tree is not None, "AudioOrchestrator must be valid Python"
    imports = _module_imports(tree)
    assert not _canonical_event_import(imports), (
        "AudioOrchestrator must not import the canonical Event layer (CONTRACT-7)"
    )
    assert not _calls_attribute(tree, "create_event"), (
        "AudioOrchestrator must not call EventFactory.create_event (CONTRACT-7)"
    )
    assert not _constructs(tree, "Event"), (
        "AudioOrchestrator must not construct a canonical Event (CONTRACT-7)"
    )
    assert not _constructs(tree, "EventPipeline"), (
        "AudioOrchestrator must not instantiate an EventPipeline (CONTRACT-7)"
    )
    assert not _calls_attribute(tree, "save"), (
        "AudioOrchestrator must not persist directly (CONTRACT-7)"
    )

    # Runtime seam check: the orchestrator is a RAW producer only.
    orch = _make_orchestrator()
    raw = orch.process_segment(_audio_segment())
    assert isinstance(raw, dict), "orchestrator must produce a RAW dict"
    assert not hasattr(orch, "_repository"), (
        "AudioOrchestrator must not own a repository (CONTRACT-7)"
    )
    assert not hasattr(orch, "_event_factory"), (
        "AudioOrchestrator must not own an EventFactory (CONTRACT-7)"
    )


# =============================================================================
# CONTRACT-8 — SINGLE PERSISTENCE PATH
# =============================================================================


def test_contract8_single_persistence_path() -> None:
    """One canonical event entering the pipeline -> exactly one durable save."""
    pipeline = EventPipeline()
    repo = _SpyRepository()
    pipeline.set_repository(repo)
    runtime = AdapterRuntime(
        adapter=_FakeAdapter([_raw()]),
        factory=EventFactory(identity_resolver=EventIdentityResolver()),
        pipeline=pipeline,
    )
    runtime._process_raw(_raw())

    assert len(repo.saved) == 1, (
        "one canonical event must produce exactly one durable save (CONTRACT-8)"
    )
    assert isinstance(repo.saved[0], Event)


# =============================================================================
# CONTRACT-9 — RAW CROSSES EVENTFACTORY EXACTLY ONCE
# =============================================================================


def test_contract9_raw_crosses_factory_exactly_once() -> None:
    """RAW crosses EventFactory exactly once per logical event."""
    pipeline = EventPipeline()
    repo = _SpyRepository()
    pipeline.set_repository(repo)
    factory = _CountingFactory(EventFactory(identity_resolver=EventIdentityResolver()))
    runtime = AdapterRuntime(
        adapter=_FakeAdapter([_raw()]),
        factory=factory,
        pipeline=pipeline,
    )
    runtime._process_raw(_raw())

    assert factory.calls == 1, (
        "RAW must cross EventFactory.create_event exactly once (CONTRACT-9)"
    )
    assert len(repo.saved) == 1


# =============================================================================
# CONTRACT-10 — PROJECTION THROUGH THE CANONICAL PIPELINE
# =============================================================================


def test_contract10_projection_through_canonical_pipeline() -> None:
    """Projection runs through EventPipeline, not an adapter-side bypass."""
    pipeline = EventPipeline()
    repo = _SpyRepository()
    proj = _SpyProjection()
    pipeline.set_repository(repo)
    pipeline.set_projection(proj)
    runtime = AdapterRuntime(
        adapter=_FakeAdapter([_raw()]),
        factory=EventFactory(identity_resolver=EventIdentityResolver()),
        pipeline=pipeline,
    )
    runtime._process_raw(_raw())

    assert len(proj.events) == 1, (
        "projection must run through the canonical pipeline (CONTRACT-10)"
    )
    assert isinstance(proj.events[0], Event)
    # Projection runs on the canonical pipeline AFTER durable persistence.
    assert len(repo.saved) == 1


# =============================================================================
# CONTRACT-11 — CHECKPOINT ADVANCEMENT AFTER CANONICAL BOUNDARY
# =============================================================================


def test_contract11_checkpoint_not_in_ingestion_path() -> None:
    """Checkpoint ownership is downstream of the canonical ingestion boundary."""
    guarded = [*_adapter_paths(), _RUNTIME_PATH, _FACTORY_PATH, _ORCHESTRATOR_PATH]
    for path in guarded:
        tree = _parse(path)
        assert tree is not None, f"{path.name}: module must be valid Python"
        bad = [
            i
            for i in _module_imports(tree)
            if "checkpoint" in i or "ProjectionCheckpoint" in i
        ]
        assert not bad, (
            f"{path.relative_to(_APP_DIR)}: ingestion path imports checkpoint "
            f"component {bad} (CONTRACT-11)"
        )


# =============================================================================
# CONTRACT-12 — REPRESENTATIVE NON-AUDIO ADAPTER FOLLOWS THE CONTRACT
# =============================================================================


def test_contract12_non_audio_adapter_follows_contract() -> None:
    """A representative non-audio adapter obeys RAW→Runtime→Factory→Pipeline."""
    adapter = RadioSourceAdapter(
        SourceDefinition(name="radio-1", adapter_type="radio", config={"channel": "A"})
    )
    adapter.start()
    accepted = adapter.ingest(
        {
            "frequency": "145.500",
            "callsign": "Alpha-1",
            "timestamp": "2026-09-09T10:00:00+00:00",
        }
    )
    assert accepted, "radio adapter must accept a valid raw payload"
    raws = adapter.read_events()
    assert len(raws) == 1 and isinstance(raws[0], dict), (
        "adapter must expose RAW dicts via read_events() (CONTRACT-12)"
    )

    pipeline = EventPipeline()
    repo = _SpyRepository()
    pipeline.set_repository(repo)
    runtime = AdapterRuntime(
        adapter=adapter,
        factory=EventFactory(identity_resolver=EventIdentityResolver()),
        pipeline=pipeline,
    )
    runtime._process_raw(raws[0])

    assert len(repo.saved) == 1, (
        "non-audio RAW must reach exactly one durable save via the seam (CONTRACT-12)"
    )
    assert isinstance(repo.saved[0], Event)
    assert repo.saved[0].source == "radio"
