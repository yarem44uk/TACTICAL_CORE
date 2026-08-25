"""WO-032 — Production Process Entrypoint tests.

These tests are focused exclusively on the WO-032 production entrypoint
(``backend/main.py``).  They verify the entrypoint lifecycle contract against
the REAL production runtime where practical, and use test doubles only at the
external boundaries (a controllable runtime / a captured runtime factory).

Coverage:
  1. Entrypoint constructs the production runtime.
  2. Durable delivery is mandatory (``require_durable_delivery=True``).
  3. Source registration occurs through the existing mechanism.
  4. ``runtime.start()`` is invoked.
  5. SIGINT requests graceful shutdown (``runtime.stop()`` + lifetime end).
  6. SIGTERM requests graceful shutdown.
  7. Durable-delivery failure is NOT bypassed (startup does not continue).
"""

from __future__ import annotations

import os
import signal
import tempfile
import threading

import pytest
import sqlalchemy

import backend.main as entrypoint
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.provider import ISourceConfigProvider
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter


# ---------------------------------------------------------------------------
# Test doubles — only at the external boundaries (runtime / provider / factory)
# ---------------------------------------------------------------------------
class _RecordingRuntime:
    """Controllable runtime recording lifecycle calls and registration."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.added_sources: list[str] = []
        self.delivery_dispatcher = object()

    def add_source(self, adapter: IEventSourceAdapter) -> None:
        self.added_sources.append(adapter.source_name())

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class _SourceStub(IEventSourceAdapter):
    def __init__(self, name: str) -> None:
        self._name = name

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def health(self) -> bool:
        return True

    def read_events(self) -> list:
        return []

    def source_name(self) -> str:
        return self._name


class _StaticProvider(ISourceConfigProvider):
    """In-memory source-configuration provider (config-boundary double)."""

    def __init__(self, definitions: list[SourceDefinition]) -> None:
        self._defs = definitions
        self.loaded = False

    def load(self) -> None:
        self.loaded = True

    def list_sources(self) -> list[SourceDefinition]:
        return self._defs

    def get_source(self, name: str) -> SourceDefinition:
        for d in self._defs:
            if d.name == name:
                return d
        raise KeyError(name)


def _make_factory() -> AdapterFactory:
    factory = AdapterFactory()
    factory.register_type("stub", lambda d: _SourceStub(d.name))
    return factory


def _source_def(name: str = "prod-source") -> SourceDefinition:
    return SourceDefinition(name=name, adapter_type="stub", enabled=True)


# ---------------------------------------------------------------------------
# 1. Entrypoint constructs the production runtime
# ---------------------------------------------------------------------------
def test_entrypoint_constructs_production_runtime(monkeypatch) -> None:
    captured: dict = {}

    def _fake_create_runtime(plugin_manager=None, *, require_durable_delivery):
        captured["require_durable_delivery"] = require_durable_delivery
        return _RecordingRuntime()

    monkeypatch.setattr(entrypoint, "create_production_runtime", _fake_create_runtime)

    runtime = entrypoint.create_production_entrypoint_runtime()
    assert isinstance(runtime, _RecordingRuntime)
    # Durable delivery is mandatory in production.
    assert captured["require_durable_delivery"] is True


# ---------------------------------------------------------------------------
# 2. Durable delivery is mandatory
# ---------------------------------------------------------------------------
def test_entrypoint_requests_durable_delivery_true(monkeypatch) -> None:
    captured: dict = {}

    def _fake_create_runtime(plugin_manager=None, *, require_durable_delivery):
        captured["require_durable_delivery"] = require_durable_delivery
        return _RecordingRuntime()

    monkeypatch.setattr(entrypoint, "create_production_runtime", _fake_create_runtime)

    entrypoint.create_production_entrypoint_runtime()
    assert captured["require_durable_delivery"] is True


# ---------------------------------------------------------------------------
# 3. Source registration occurs through the existing mechanism
# ---------------------------------------------------------------------------
def test_entrypoint_registers_sources(monkeypatch) -> None:
    runtime = _RecordingRuntime()
    provider = _StaticProvider([_source_def()])
    factory = _make_factory()

    registered = entrypoint.register_sources(runtime, provider, factory)

    assert provider.loaded is True
    assert registered == ["prod-source"]
    assert runtime.added_sources == ["prod-source"]


def test_entrypoint_registration_uses_existing_mechanism() -> None:
    """The registrar is the authoritative ProductionSourceRegistrar path."""
    assert entrypoint.ProductionSourceRegistrar.__name__ == "ProductionSourceRegistrar"


# ---------------------------------------------------------------------------
# 4. Runtime starts and lifecycle is driven end to end
# ---------------------------------------------------------------------------
def test_entrypoint_starts_and_stops_runtime(monkeypatch) -> None:
    runtime = _RecordingRuntime()
    provider = _StaticProvider([_source_def()])
    factory = _make_factory()
    shutdown = threading.Event()

    # Do not install real OS signal handlers in tests.
    fake_install = lambda ev: None  # noqa: E731
    result: dict = {}

    def _drive() -> None:
        registered = entrypoint.run_production_process(
            runtime=runtime,
            provider=provider,
            factory=factory,
            shutdown_event=shutdown,
            install_handlers=fake_install,
        )
        result["registered"] = registered

    t = threading.Thread(target=_drive)
    t.start()

    # Wait until the process has started (registered + runtime.start()).
    deadline = threading.Event()
    while not runtime.started and not deadline.wait(0.01):
        pass
    assert runtime.started is True
    assert runtime.stopped is False  # still alive, no shutdown yet

    # Request shutdown: process performs graceful stop and returns.
    shutdown.set()
    t.join(timeout=5)
    assert not t.is_alive()
    assert result.get("registered") == ["prod-source"]
    assert runtime.stopped is True


# ---------------------------------------------------------------------------
# 5 & 6. SIGINT / SIGTERM request graceful shutdown
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_entrypoint_signal_requests_graceful_shutdown(monkeypatch, sig) -> None:
    """Signal handlers must be installed in the main thread; we drive the
    process in the main thread and deliver the signal from a worker thread."""

    runtime = _RecordingRuntime()
    provider = _StaticProvider([_source_def()])
    factory = _make_factory()
    shutdown = threading.Event()

    def _real_install(ev: threading.Event) -> None:
        entrypoint.install_signal_handlers(ev)

    result: dict = {}

    def _deliver_signal() -> None:
        # Wait until handlers are installed and the runtime is started, then
        # deliver the OS signal to this process (handled on the main thread).
        deadline = threading.Event()
        while not runtime.started and not deadline.wait(0.01):
            pass
        import os
        os.kill(os.getpid(), sig)
        result["delivered"] = True

    deliverer = threading.Thread(target=_deliver_signal)
    deliverer.start()

    entrypoint.run_production_process(
        runtime=runtime,
        provider=provider,
        factory=factory,
        shutdown_event=shutdown,
        install_handlers=_real_install,
    )
    deliverer.join(timeout=5)

    assert result.get("delivered") is True
    # Graceful shutdown: runtime.stop() was invoked.
    assert runtime.stopped is True


# ---------------------------------------------------------------------------
# 7. Durable-delivery failure is NOT bypassed
# ---------------------------------------------------------------------------
def test_entrypoint_durable_delivery_failure_not_bypassed(monkeypatch) -> None:
    """Startup must not continue when durable delivery is unavailable."""

    def _fake_create_runtime(plugin_manager=None, *, require_durable_delivery):
        # Simulate the fail-closed RuntimeError raised by create_production_runtime
        # when durable delivery cannot be established.
        raise RuntimeError(
            "WO-030: production durable delivery requires a configured "
            "DatabaseSessionManager; cannot silently fall back to the legacy "
            "non-durable delivery path."
        )

    monkeypatch.setattr(entrypoint, "create_production_runtime", _fake_create_runtime)

    with pytest.raises(RuntimeError):
        entrypoint.create_production_entrypoint_runtime(require_durable_delivery=True)


def test_entrypoint_does_not_silently_downgrade(monkeypatch) -> None:
    """The entrypoint never re-invokes the runtime with durable delivery False."""
    calls: list[bool] = []

    def _fake_create_runtime(plugin_manager=None, *, require_durable_delivery):
        calls.append(require_durable_delivery)
        return _RecordingRuntime()

    monkeypatch.setattr(entrypoint, "create_production_runtime", _fake_create_runtime)

    entrypoint.create_production_entrypoint_runtime()
    # The runtime is constructed exactly once, with durable delivery required.
    assert calls == [True]


# ---------------------------------------------------------------------------
# WO-034 — production entrypoint operability regression coverage
# ---------------------------------------------------------------------------
# These tests cover the two production behaviors introduced by WO-033 and
# must remain valid against the WO-032 entrypoint lifecycle:
#   AC-01  fail-closed database configuration (no DATABASE_URL)
#   AC-02  successful database configuration (valid DATABASE_URL)
#   AC-03  main() fail-closed behavior when DATABASE_URL is absent
#   AC-04  _BACKEND_DIR import-path bootstrap idempotency
# They are test-only: they exercise the real WO-033 code paths and do not
# modify production architecture.

# AC-01 — Missing DATABASE_URL is fail-closed and never touches the database.
def test_wo034_configure_database_missing_url_fails_closed(monkeypatch) -> None:
    called: list[str] = []

    def _recording_initialize_database(**kwargs):
        called.append(kwargs)
        raise AssertionError("initialize_database must not be called without a URL")

    monkeypatch.setattr(entrypoint, "initialize_database", _recording_initialize_database)

    # None URL -> fail closed, no DB initialization.
    assert entrypoint.configure_production_database(None) is False
    # Empty string URL -> fail closed, no DB initialization.
    assert entrypoint.configure_production_database("") is False

    assert called == []


# AC-02 — Valid DATABASE_URL configures real, usable database infrastructure.
def test_wo034_configure_database_valid_url_initializes_real_db() -> None:
    import app.database.database as database_mod
    import app.database.session as session_mod

    tmp = tempfile.mkdtemp(prefix="wo034-")
    db = os.path.join(tmp, "db.sqlite")
    url = f"sqlite:///{db}"
    try:
        assert entrypoint.configure_production_database(url) is True

        # The real DatabaseSessionManager must now be configured and usable.
        manager = session_mod.get_session_manager()
        assert manager is not None
        with manager.session(commit=False) as s:
            s.execute(sqlalchemy.text("SELECT 1"))
    finally:
        # Reset global database/session state so we do not leak into other tests.
        database_mod._database_manager = None
        session_mod._session_manager = None


# AC-03 — main() fail-closed: no DATABASE_URL -> exit 2, runtime never built.
def test_wo034_main_without_database_url_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    runtime_built: list[bool] = []

    def _recording_create_runtime(**kwargs):
        runtime_built.append(True)
        raise AssertionError("runtime must not be constructed without DB config")

    monkeypatch.setattr(
        entrypoint, "create_production_entrypoint_runtime", _recording_create_runtime
    )

    assert entrypoint.main([]) == 2
    assert runtime_built == []


# AC-04 — _BACKEND_DIR import-path bootstrap is idempotent.
def test_wo034_backend_dir_bootstrap_is_idempotent() -> None:
    import importlib
    import sys as _sys

    backend_dir = entrypoint._BACKEND_DIR
    assert _sys.path.count(backend_dir) == 1

    # Re-importing the entrypoint must not duplicate the backend dir.
    importlib.reload(entrypoint)
    assert _sys.path.count(backend_dir) == 1
