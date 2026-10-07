"""WO-083 — Telegram ingress composition (the ingress process's own wiring).

This module wires the SEPARATE Telegram ingress process onto the EXISTING
canonical architecture.  It introduces no new pipeline, repository, queue, or
store — it mirrors the accepted WO-080 WhatsApp ingress composition exactly:

    create_production_runtime()            (existing canonical composition)
        -> EventFactory + EventPipeline + DurableCanonicalEventRepository
           + DurableDeliveryDispatcher (transactional outbox)
        -> ObservationService -> Operator Wall

    build_production_adapter_factory()     (existing production AdapterFactory)
        -> the ``telegram`` adapter type is ALREADY registered here by
           register_telegram_adapter() (ADR-010 / WO-013-008) — WO-083 adds no
           registration and no factory change

    build_production_source_provider(catalog=[telegram definition])
    ProductionSourceRegistrar              (existing registration mechanism)
        -> ProductionRuntime.add_source()  (existing supervisor boundary)
        -> AdapterRuntime("telegram")      (existing runtime)

    AdapterRuntime.set_ingest_durability_probe(repository.exists)
        -> read-only existence check on the SAME canonical durable store
           (single DatabaseSessionManager owner; no second store)

Durable delivery is FAIL-CLOSED: ``require_durable_delivery=True`` makes
construction raise when the canonical database is not configured, so the
ingress can never silently start without commit-before-ACK.

NOTE — the Telegram source is registered into the ingress process's runtime with
the EXISTING canonical ``TelegramSourceAdapter`` leaf (WO-013-008).  That leaf
already returns RAW DATA only, never touches EventBus/DB/pipeline, and with no
transport injected its queue stays empty (``read_events() -> []``), which is
correct for a synchronous commit-before-ACK ingress driven by ``submit_raw``.
It is NOT the legacy ``app.connectors.telegram`` connector (which imports
``app.core.event_bus``); WO-083 does not use, modify, or depend on that legacy
path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List

from app.bootstrap import ProductionRuntime, create_production_runtime
from app.database.session import get_session_manager
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.event_sources.config.production_source_config import (
    build_production_adapter_factory,
    build_production_source_provider,
    build_telegram_source_definition,
)
from app.event_sources.source_registration import ProductionSourceRegistrar

logger = logging.getLogger(__name__)

TELEGRAM_SOURCE_NAME = "telegram"


@dataclass
class TelegramIngressRuntime:
    """A wired Telegram ingress runtime handle.

    Attributes:
        runtime: The canonical ``ProductionRuntime`` (existing composition).
        adapter_runtime: The production ``AdapterRuntime`` for ``telegram``,
            obtained from the production supervisor (never hand-built).
        registered: Sorted names of the sources registered into the runtime.
    """

    runtime: ProductionRuntime
    adapter_runtime: Any
    registered: List[str]

    def stop(self) -> None:
        """Stop the ingress runtime deterministically (joins source threads)."""
        self.runtime.stop()


def build_telegram_ingress_runtime() -> TelegramIngressRuntime:
    """Build the durable canonical runtime for the Telegram ingress process.

    Requires the canonical ``DatabaseSessionManager`` to be configured and
    initialised BEFORE this call (the ingress entrypoint does this, mirroring
    ``backend/main.py``), because commit-before-ACK needs the durable store.

    Raises:
        RuntimeError: If durable post-commit delivery cannot be established
            (fail-closed; the ingress refuses to start non-durably).
    """
    runtime = create_production_runtime(require_durable_delivery=True)

    # The ``telegram`` adapter type is already registered by the existing
    # production factory (register_telegram_adapter).  No registration here.
    factory = build_production_adapter_factory()

    provider = build_production_source_provider(
        catalog=[build_telegram_source_definition()]
    )
    registrar = ProductionSourceRegistrar(provider=provider, factory=factory)
    registrar.load()
    registered = registrar.register(runtime)

    adapter_runtime = runtime.supervisor.get_runtime(TELEGRAM_SOURCE_NAME)

    # Commit-before-ACK durability probe: a READ-ONLY existence check on the
    # SAME canonical durable store (single DatabaseSessionManager owner).  It
    # performs no write and creates no second store.
    probe_repository = SQLAlchemyEventRepository(
        session_manager=get_session_manager()
    )
    adapter_runtime.set_ingest_durability_probe(probe_repository.exists)

    # Start the telegram source so the runtime is in a healthy, observable
    # state.  The canonical Telegram leaf buffers nothing (read_events() -> []);
    # the canonical path is driven synchronously by submit_raw.
    runtime.start_source(TELEGRAM_SOURCE_NAME)

    logger.info(
        "Telegram ingress runtime wired: registered=%s, adapter_state=%s",
        registered,
        adapter_runtime.state,
    )
    return TelegramIngressRuntime(
        runtime=runtime,
        adapter_runtime=adapter_runtime,
        registered=registered,
    )
