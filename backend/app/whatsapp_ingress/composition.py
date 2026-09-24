"""WO-080 — WhatsApp ingress composition (the ingress process's own wiring).

This module wires the SEPARATE ingress process onto the EXISTING canonical
architecture.  It introduces no new pipeline, repository, queue, or store:

    create_production_runtime()            (existing canonical composition)
        -> EventFactory + EventPipeline + DurableCanonicalEventRepository
           + DurableDeliveryDispatcher (transactional outbox)
        -> ObservationService -> Operator Wall

    build_production_adapter_factory()     (existing production AdapterFactory)
        -> register_whatsapp_adapter()     (existing register_type mechanism)

    build_production_source_provider(catalog=[whatsapp definition])
    ProductionSourceRegistrar              (existing registration mechanism)
        -> ProductionRuntime.add_source()  (existing supervisor boundary)
        -> AdapterRuntime("whatsapp")      (existing runtime)

    AdapterRuntime.set_ingest_durability_probe(repository.exists)
        -> read-only existence check on the SAME canonical durable store
           (single DatabaseSessionManager owner; no second store)

Durable delivery is FAIL-CLOSED: ``require_durable_delivery=True`` makes
construction raise when the canonical database is not configured, so the
ingress can never silently start without commit-before-ACK.
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
from app.event_sources.adapters.whatsapp_adapter_registration import (
    register_whatsapp_adapter,
)
from app.event_sources.config.production_source_config import (
    build_production_adapter_factory,
    build_production_source_provider,
    build_whatsapp_source_definition,
)
from app.event_sources.source_registration import ProductionSourceRegistrar

logger = logging.getLogger(__name__)

WHATSAPP_SOURCE_NAME = "whatsapp"


@dataclass
class WhatsAppIngressRuntime:
    """A wired WhatsApp ingress runtime handle.

    Attributes:
        runtime: The canonical ``ProductionRuntime`` (existing composition).
        adapter_runtime: The production ``AdapterRuntime`` for ``whatsapp``,
            obtained from the production supervisor (never hand-built).
        registered: Sorted names of the sources registered into the runtime.
    """

    runtime: ProductionRuntime
    adapter_runtime: Any
    registered: List[str]

    def stop(self) -> None:
        """Stop the ingress runtime deterministically (joins source threads)."""
        self.runtime.stop()


def build_whatsapp_ingress_runtime() -> WhatsAppIngressRuntime:
    """Build the durable canonical runtime for the WhatsApp ingress process.

    Requires the canonical ``DatabaseSessionManager`` to be configured and
    initialised BEFORE this call (the ingress entrypoint does this, mirroring
    ``backend/main.py``), because commit-before-ACK needs the durable store.

    Raises:
        RuntimeError: If durable post-commit delivery cannot be established
            (fail-closed; the ingress refuses to start non-durably).
    """
    runtime = create_production_runtime(require_durable_delivery=True)

    factory = build_production_adapter_factory()
    register_whatsapp_adapter(factory)

    provider = build_production_source_provider(
        catalog=[build_whatsapp_source_definition()]
    )
    registrar = ProductionSourceRegistrar(provider=provider, factory=factory)
    registrar.load()
    registered = registrar.register(runtime)

    adapter_runtime = runtime.supervisor.get_runtime(WHATSAPP_SOURCE_NAME)

    # Commit-before-ACK durability probe: a READ-ONLY existence check on the
    # SAME canonical durable store (single DatabaseSessionManager owner).  It
    # performs no write and creates no second store.
    probe_repository = SQLAlchemyEventRepository(
        session_manager=get_session_manager()
    )
    adapter_runtime.set_ingest_durability_probe(probe_repository.exists)

    # Start the whatsapp source so the runtime is in a healthy, observable
    # state.  The WhatsApp adapter buffers nothing (read_events() -> []); the
    # canonical path is driven synchronously by submit_raw.
    runtime.start_source(WHATSAPP_SOURCE_NAME)

    logger.info(
        "WhatsApp ingress runtime wired: registered=%s, adapter_state=%s",
        registered,
        adapter_runtime.state,
    )
    return WhatsAppIngressRuntime(
        runtime=runtime,
        adapter_runtime=adapter_runtime,
        registered=registered,
    )
