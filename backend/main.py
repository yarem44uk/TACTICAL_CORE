"""WO-032 — Production Process Entrypoint.

The single authoritative production process entrypoint for TACTICAL CORE.

It turns the already-proven production runtime composition into an actual
long-lived operating-system process:

    process entrypoint
          |
          +-- construct runtime        (create_production_runtime)
          |
          +-- register sources         (existing source-registration mechanism)
          |
          +-- install signal handlers  (SIGINT / SIGTERM)
          |
          +-- runtime.start()
          |
          +-- wait for shutdown signal
          |
          +-- runtime.stop()

WO-032 deliberately does NOT redesign any component.  It consumes the existing
production runtime through its existing public lifecycle API
(``ProductionRuntime.start()`` / ``stop()``) and registers sources through the
existing source-registration mechanism (``app.event_sources.source_registration``).

Durable delivery is FAIL-CLOSED: the production process constructs the runtime
with ``require_durable_delivery=True``.  If durable post-commit delivery cannot
be established (no configured DatabaseSessionManager), ``create_production_runtime``
raises and the process refuses to start rather than silently downgrading to the
legacy non-durable path.
"""

from __future__ import annotations

import logging
import signal
import threading
from typing import Callable, Optional, Sequence

from app.bootstrap import ProductionRuntime, create_production_runtime
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.provider import ISourceConfigProvider
from app.event_sources.source_registration import (
    ProductionSourceRegistrar,
)
from app.plugins.manager.plugin_manager import PluginManager

logger = logging.getLogger(__name__)

# Deterministic production source configuration gap.
#
# The repository provides the authoritative source-registration *mechanism*
# (``ProductionSourceRegistrar`` / ``register_production_sources``) but does not
# ship a concrete production ``ISourceConfigProvider`` (no static source catalog,
# no env/YAML/JSON loader).  WO-032 therefore wires the registration boundary and
# registers whatever enabled source definitions an embedding provider supplies.
# It does NOT fabricate a hidden production source catalog, and it does NOT
# redesign source adapters (out of WO-032 scope).
SOURCE_CONFIGURATION_GAP = True


def create_production_entrypoint_runtime(
    *,
    require_durable_delivery: bool = True,
    plugin_manager: Optional[PluginManager] = None,
) -> ProductionRuntime:
    """Construct the production runtime, requiring durable delivery (fail-closed).

    The production entrypoint ALWAYS requests durable delivery; the
    ``require_durable_delivery`` parameter exists only so focused tests can
    assert the fail-closed path (it defaults to ``True`` for production).

    Args:
        require_durable_delivery: When True (production default), a
            ``RuntimeError`` is raised if durable post-commit delivery cannot be
            established.  Production never silently downgrades.
        plugin_manager: Optional ``PluginManager``; defaults to the global
            singleton (see ``create_production_runtime``).

    Returns:
        A wired ``ProductionRuntime`` ready for source registration + start.

    Raises:
        RuntimeError: If ``require_durable_delivery`` is True and no durable
            delivery dispatcher could be established.
    """
    return create_production_runtime(
        plugin_manager=plugin_manager,
        require_durable_delivery=require_durable_delivery,
    )


def register_sources(
    runtime: ProductionRuntime,
    provider: ISourceConfigProvider,
    factory: AdapterFactory,
) -> list[str]:
    """Register every enabled configured source into the runtime.

    Uses the existing authoritative registration mechanism
    (``ProductionSourceRegistrar``), routing adapters through the runtime's
    existing ``add_source`` boundary into the existing ``AdapterSupervisor``.
    No parallel source framework is introduced.

    Args:
        runtime: The production runtime (an ``add_source`` sink).
        provider: Source-configuration provider supplying ``SourceDefinition``.
        factory: ``AdapterFactory`` able to resolve the configured adapter types.

    Returns:
        Sorted list of registered source names.
    """
    registrar = ProductionSourceRegistrar(provider=provider, factory=factory)
    registrar.load()
    return registrar.register(runtime)


def install_signal_handlers(
    shutdown_event: threading.Event,
    *,
    signals: Sequence[int] = (signal.SIGINT, signal.SIGTERM),
) -> None:
    """Install minimal, safe SIGINT/SIGTERM handlers that request graceful shutdown.

    Each handler simply sets the process-lifetime ``shutdown_event``.  It does
    not call ``os._exit()``, does not terminate abruptly, and never bypasses
    ``ProductionRuntime.stop()`` — the main orchestration loop observes the event
    and performs the graceful ``runtime.stop()``.
    """

    def _request_shutdown(signum: int, frame: Optional[object]) -> None:
        logger.info("Received signal %s; requesting graceful shutdown.", signum)
        shutdown_event.set()

    for sig in signals:
        signal.signal(sig, _request_shutdown)


def run_production_process(
    *,
    runtime: ProductionRuntime,
    provider: ISourceConfigProvider,
    factory: AdapterFactory,
    shutdown_event: threading.Event,
    install_handlers: Callable[[threading.Event], None] = install_signal_handlers,
) -> list[str]:
    """Run the production process lifecycle end to end.

    Minimal responsibility boundary:

        register sources -> install signal handlers -> start -> wait -> stop

    Business logic lives elsewhere; this orchestrator only drives the existing
    lifecycle API.

    Args:
        runtime: The constructed production runtime.
        provider: Source-configuration provider (existing mechanism).
        factory: AdapterFactory resolving configured adapter types.
        shutdown_event: Process-lifetime event; set by a signal handler.
        install_handlers: Callable that installs the signal handlers onto the
            given event (injectable for tests).

    Returns:
        Sorted list of registered source names.
    """
    registered = register_sources(runtime, provider, factory)
    logger.info("Registered production sources: %s", registered)

    install_handlers(shutdown_event)

    runtime.start()
    logger.info("Production runtime started; waiting for shutdown signal.")

    # Remain alive as a long-lived process until a termination signal arrives.
    shutdown_event.wait()

    logger.info("Shutdown requested; stopping production runtime.")
    runtime.stop()
    return registered


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Real production entrypoint invoked by ``python -m backend.main``.

    Constructs the fail-closed production runtime, installs SIGINT/SIGTERM
    handlers, starts, waits, and performs graceful shutdown.

    Returns:
        Process exit code (0 on clean shutdown).
    """
    logging.basicConfig(level=logging.INFO)

    # Fail-closed construction: durable delivery is mandatory.  If the durable
    # post-commit delivery dependency is unavailable, this raises and the
    # process refuses to start.
    runtime = create_production_entrypoint_runtime(require_durable_delivery=True)

    # Source configuration.
    #
    # The repository ships the source-registration mechanism but no concrete
    # production ``ISourceConfigProvider`` (documented SOURCE_CONFIGURATION_GAP).
    # An embedding deployment injects a provider + factory here.  Without one,
    # the process still runs but registers no sources — it never fabricates a
    # hidden source catalog and never redesigns source adapters.
    provider = _production_source_provider()
    if provider is None:
        logger.warning(
            "WO-032 SOURCE_CONFIGURATION_GAP: no production ISourceConfigProvider "
            "configured; the process will start with no registered sources."
        )

    factory = _production_adapter_factory()

    shutdown_event = threading.Event()
    install_signal_handlers(shutdown_event)

    if provider is not None:
        register_sources(runtime, provider, factory)

    runtime.start()
    logger.info("Production runtime started; waiting for shutdown signal.")
    shutdown_event.wait()
    logger.info("Shutdown requested; stopping production runtime.")
    runtime.stop()
    return 0


def _production_source_provider() -> Optional[ISourceConfigProvider]:
    """Return the production source-configuration provider, if configured.

    Returns ``None`` until a concrete production ``ISourceConfigProvider`` is
    supplied by an embedding deployment (see ``SOURCE_CONFIGURATION_GAP``).
    """
    return None


def _production_adapter_factory() -> AdapterFactory:
    """Return the production AdapterFactory.

    Embedding deployments register the concrete source-adapter types they use
    (e.g. ``register_mqtt_adapter``) here.  The entrypoint does not force any
    protocol adapter to appear.
    """
    return AdapterFactory()


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
