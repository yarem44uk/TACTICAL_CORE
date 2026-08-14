"""
TACTICAL CORE — WO-014-013
Source Ingestion Boundary — Contract Closure

This suite is a STRUCTURAL / CONTRACT-LEVEL guard, not a functional
happy-path test. It locks down the constitutional ingestion seam:

    IEventSourceAdapter.read_events()
        -> RAW dict
        -> EventFactory.create_event(raw, source_name)   [AdapterRuntime._process_raw]
        -> canonical immutable Event
        -> IEventPipeline.process(event)

Architectural invariants enforced (WO-014-013):

    INV-1  Single RAW -> EventFactory seam: the only production caller of
           EventFactory.create_event(...) for RAW ingestion is
           backend/app/event_sources/runtime/adapter_runtime.py (_process_raw).
    INV-2  Adapters produce RAW only: source adapters return raw dicts and
           never construct canonical Event instances.
    INV-3  EventFactory owns normalization: adapters must not re-implement
           EventFactory normalization.
    INV-4  Pipeline receives canonical Event only via AdapterRuntime ->
           EventFactory -> EventPipeline; adapters never hand RAW to pipeline.
    INV-5  Single lifecycle owner: only AdapterRuntime owns the source thread.
    INV-6  No bypass: no source adapter has a direct production dependency on
           EventPipeline, EventBus, PluginManager, application API, or DB.

The test is deliberately structural: it reads the production source and
asserts the seam and ownership boundaries so that an accidental second
ingestion seam, an adapter that starts constructing Events, or an adapter
that reaches the pipeline directly will FAIL the contract.

Design constraints honoured (WO-014-013 §5):
  * no network, no background threads, no timers/schedulers
  * no eval/exec/subprocess/shell
  * no temporary files, no repository mutation
  * production source read via Path.read_text() / inspect only
"""

from __future__ import annotations

import inspect
import io
import re
import tokenize
from pathlib import Path

import pytest

# --- Paths ---------------------------------------------------------------

# backend/tests/test_wo014013_source_ingestion_boundary.py
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent
_APP_DIR = _BACKEND_DIR / "app"

_RUNTIME_MOD = _APP_DIR / "event_sources" / "runtime" / "adapter_runtime.py"
_FACTORY_MOD = _APP_DIR / "event_sources" / "factory" / "event_factory.py"
_ADAPTERS_DIR = _APP_DIR / "event_sources" / "adapters"

# Source-adapter production modules. Parsers are included because they are the
# RAW-normalization step and must also remain leaf components (INV-2/INV-3).
_ADAPTER_MODULES = sorted(
    p.name
    for p in _ADAPTERS_DIR.iterdir()
    if p.suffix == ".py" and not p.name.startswith("__")
)


def _read(path: Path) -> str:
    """Read a production source file as text (structural scan only)."""
    assert path.is_file(), f"production file missing: {path}"
    return path.read_text(encoding="utf-8")


def _code_only(src: str) -> str:
    """Return the module source with docstrings, string literals and comments
    blanked out, preserving the exact positions/whitespace of all real code.

    This lets the structural scans reason about *real* code (imports, calls,
    thread spawns) without false positives from docstring prose that merely
    describes the intended data flow (e.g. an adapter docstring saying
    '-> EventFactory.create_event()').
    """
    lines = src.splitlines(keepends=True)
    chars = list(src)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            ttype = tok.type
            if ttype in (tokenize.COMMENT, tokenize.STRING):
                start, end = tok.start, tok.end
                # blank out the token across its span (line, col -> line, col)
                for line_idx in range(start[0] - 1, end[0]):
                    line_start = sum(len(l) for l in lines[:line_idx])
                    line_len = len(lines[line_idx])
                    c0 = start[1] if line_idx == start[0] - 1 else 0
                    c1 = end[1] if line_idx == end[0] - 1 else line_len - 1
                    for ci in range(c0, c1):
                        if chars[line_start + ci] not in "\r\n":
                            chars[line_start + ci] = " "
    except Exception:
        return src
    return "".join(chars)


def _import_statements(src: str) -> list[str]:
    """Return the real import/from lines in a module (code only)."""
    code = _code_only(src)
    imports: list[str] = []
    for m in re.finditer(r"(?:^|\s)((?:import|from)\s+\S[^\n]*)", code):
        imports.append(m.group(1))
    return imports


# --- Test-1: canonical EventFactory seam exists --------------------------

def test_ingestion_seam_calls_event_factory_create_event():
    """INV-1/INV-3: the runtime ingestion path routes RAW through
    EventFactory.create_event(...) before handing the result to the pipeline."""
    code = _code_only(_read(_RUNTIME_MOD))

    assert "_process_raw" in _read(_RUNTIME_MOD), (
        "AdapterRuntime must expose the canonical RAW->Event seam (_process_raw)."
    )

    # The seam must invoke the factory by its injected interface attribute.
    assert re.search(r"self\._factory\.create_event\s*\(", code), (
        "AdapterRuntime._process_raw must call self._factory.create_event(...)."
    )

    # The canonical order RAW -> EventFactory -> Event -> Pipeline must appear
    # within the same seam body (INV-5 canonical order).
    assert re.search(r"self\._factory\.create_event\s*\(", code), "factory call missing"
    assert re.search(r"self\._pipeline\.process\s*\(", code), (
        "AdapterRuntime must forward the canonical Event to the pipeline "
        "(self._pipeline.process(...))."
    )


# --- Test-2: adapters do not construct Event directly --------------------

def test_adapters_do_not_construct_event_directly():
    """INV-2: adapters produce RAW dicts only; they must not import or
    instantiate the canonical Event class."""
    # Names that would indicate an adapter building a canonical Event itself.
    forbidden = ("from app.event.event import", "Event(", "Event(")

    for mod in _ADAPTER_MODULES:
        code = _code_only(_read(_ADAPTERS_DIR / mod))
        # Canonical Event construction would require importing the Event layer.
        if "from app.event" in code or "import Event" in code:
            pytest.fail(
                f"{mod}: adapter must not import the canonical Event layer (INV-2)."
            )
        # `Event(` as a constructor call (not part of EventFactory/EventType).
        if re.search(r"\bEvent\s*\(", code):
            pytest.fail(f"{mod}: adapter must not construct Event directly (INV-2).")


# --- Test-3: adapters do not call pipeline / EventBus directly -----------

def test_adapters_do_not_touch_pipeline_or_bus():
    """INV-4/INV-6: adapters must not import or call EventPipeline or
    EventBus directly."""
    forbidden_imports = (
        "event_pipeline",
        "i_event_pipeline",
        "event_bus",
        "i_event_bus",
    )
    forbidden_calls = (".process(", ".publish(", ".register(", "EventBus(", "EventPipeline(")

    for mod in _ADAPTER_MODULES:
        src = _read(_ADAPTERS_DIR / mod)
        code = _code_only(src)

        for token in forbidden_imports:
            # match import statements referencing the pipeline/bus module
            for imp in _import_statements(src):
                if token in imp:
                    pytest.fail(
                        f"{mod}: adapter imports forbidden component '{token}' (INV-6)."
                    )

        for call in forbidden_calls:
            if call in code:
                pytest.fail(
                    f"{mod}: adapter must not call '{call}' directly (INV-4/6)."
                )


# --- Test-4: single production EventFactory caller -----------------------

def test_single_production_event_factory_caller():
    """INV-1: exactly one production module calls EventFactory.create_event
    for RAW ingestion — adapter_runtime.py. A second ingestion seam must fail
    this contract."""
    production_py = [
        p for p in _APP_DIR.rglob("*.py")
        if p.name != "__init__.py"
    ]

    callers: list[str] = []
    for path in production_py:
        src = path.read_text(encoding="utf-8")
        code = _code_only(src)
        # Only genuine invocations of the factory's create_event method
        # (docstring prose that merely describes the flow is excluded).
        if re.search(r"\.create_event\s*\(", code):
            callers.append(str(path.relative_to(_APP_DIR)))

    # The EventFactory definition itself may reference its own method name.
    factory_path = _FACTORY_MOD.relative_to(_APP_DIR)
    runtime_path = _RUNTIME_MOD.relative_to(_APP_DIR)

    # Remove the factory's own definition site (def create_event).
    callers = [c for c in callers if c != str(factory_path)]
    # Remove the interface abstract declaration.
    iface = (_APP_DIR / "event_sources" / "interfaces" / "i_event_factory.py").relative_to(_APP_DIR)
    callers = [c for c in callers if c != str(iface)]

    assert callers == [str(runtime_path)], (
        f"Expected exactly one production create_event caller "
        f"({runtime_path}), got: {callers} (INV-1 single-seam)."
    )


# --- Test-5: canonical order RAW -> EventFactory -> Event -> Pipeline -----

def test_canonical_order_within_runtime():
    """INV-5 canonical order: within AdapterRuntime, the factory is invoked
    and its result is forwarded to the pipeline in the same seam body, and the
    factory call textually precedes the pipeline call."""
    src = _read(_RUNTIME_MOD)
    code = _code_only(src)
    # Find the _process_raw method body.
    match = re.search(
        r"def _process_raw\(.*?\n(.*?)(?=\n    def |\Z)",
        code,
        re.DOTALL,
    )
    assert match, "AdapterRuntime._process_raw method body not found."

    body = match.group(1)
    factory_pos = body.find("self._factory.create_event(")
    pipeline_pos = body.find("self._pipeline.process(")
    assert factory_pos != -1, "create_event call missing from _process_raw (INV-5)."
    assert pipeline_pos != -1, "pipeline.process call missing from _process_raw (INV-5)."
    assert factory_pos < pipeline_pos, (
        "RAW -> EventFactory must precede Pipeline in the seam (INV-5)."
    )


# --- Test-6: adapter remains a leaf --------------------------------------

def test_adapters_remain_leaf_components():
    """INV-2/INV-5/INV-6: adapters must not own lifecycle, spawn threads, or
    import runtime/registry orchestration. The single thread owner is
    AdapterRuntime."""
    forbidden_runtime_imports = (
        "adapter_runtime",
        "adapter_supervisor",
        "source_registry",
        "production_control",
        "threading.Thread",
    )

    for mod in _ADAPTER_MODULES:
        src = _read(_ADAPTERS_DIR / mod)
        code = _code_only(src)

        for token in forbidden_runtime_imports:
            for imp in _import_statements(src):
                if token in imp:
                    pytest.fail(
                        f"{mod}: adapter must not import orchestration "
                        f"'{token}' (INV-5/6 leaf rule)."
                    )

        # Adapters must not spawn their own threads.
        if re.search(r"threading\.Thread\s*\(|Thread\s*\(", code):
            pytest.fail(f"{mod}: adapter must not spawn threads (INV-5).")


# --- Structural scan of the single lifecycle owner -----------------------

def test_single_lifecycle_owner_is_adapter_runtime():
    """INV-5: only AdapterRuntime may spawn the source thread. No adapter
    spawns a thread, and no other runtime-layer module owns a thread for a
    source."""
    runtime_src = _read(_RUNTIME_MOD)
    runtime_code = _code_only(runtime_src)
    assert "threading.Thread(" in runtime_code, (
        "AdapterRuntime must be the single lifecycle owner (thread spawn)."
    )

    for mod in _ADAPTER_MODULES:
        code = _code_only(_read(_ADAPTERS_DIR / mod))
        if re.search(r"threading\.Thread\s*\(|Thread\s*\(", code):
            pytest.fail(f"{mod}: adapter must not spawn threads (INV-5).")


# --- No-bypass: no adapter reaches PluginManager / API / DB ---------------

def test_adapters_have_no_plugin_api_db_bypass():
    """INV-6: adapters must have no direct dependency on PluginManager,
    application API, or database persistence."""
    forbidden_imports = (
        "plugin_manager",
        "i_plugin_manager",
        "app.api",
        "database",
        "event_service",
    )

    for mod in _ADAPTER_MODULES:
        src = _read(_ADAPTERS_DIR / mod)
        for token in forbidden_imports:
            for imp in _import_statements(src):
                if token in imp:
                    pytest.fail(
                        f"{mod}: adapter must not import '{token}' (INV-6)."
                    )
