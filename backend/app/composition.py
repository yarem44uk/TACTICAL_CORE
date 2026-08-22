"""WO-014-003 — Production Composition / Runtime Bootstrap.

Single authoritative production composition root for the canonical
Event -> Plugin path.

    canonical app.event.Event
        |
        v
    EventPipeline.process(event)
        |
        v
    EventPipeline.set_dispatcher(dispatcher)     <-- wired here
        |
        v
    PluginDispatcher.dispatch(event)
        |
        v
    PluginManager.deliver_event(event)
        |
        v
    registered + RUNNING plugins
        |
        v
    plugin.on_event(event)

This module is the ONLY production place that assembles these components
(the pipeline, the plugin dispatcher and the plugin manager).  It is
responsible purely for wiring (instantiate -> configure -> connect).

It does NOT:
  * create / transform / publish events,
  * implement an EventBus,
  * implement plugin lifecycle,
  * implement retry,
  * implement failure isolation,
  * implement middleware,
  * implement persistence,
  * implement business logic.

All of those responsibilities belong to the components it composes
(``EventPipeline``, ``PluginDispatcher``, ``PluginManager``).  Protected
components are used as-is through their existing public APIs; no protected
file is modified here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.event.event import Event  # noqa: F401  (public type re-export)
from app.event.event_types import EventType
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_dispatcher.plugin_dispatcher import PluginDispatcher
from app.plugins.manager.plugin_manager import PluginManager, get_plugin_manager
from app.database.session import get_session_manager
from app.entity_manager import EntityManager
from app.entity_bridge import EntityBridge
from app.entity_read.entity_read_service import EntityReadService
from app.entity_read.projection_observability import ProjectionObservability
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.projection.checkpoint import ProjectionCheckpointRepository
from app.projection.catch_up import ProjectionCatchUp
from app.projection.recovery_health import ProjectionRecoveryHealth
from app.event_bus.event_bus import EventBus
from app.observation.service import ObservationService
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
    deterministic_relation_id,
)
from app.entity_relations.relation_projection import (
    project_relation_from_event,
)
from app.event_delivery.delivery_dispatcher import DurableDeliveryDispatcher


@dataclass(frozen=True)
class EventRuntime:
    """A wired production event-runtime handle.

    Exposes the assembled components of the canonical Event -> Plugin path.
    Calling ``runtime.pipeline.process(canonical_event)`` delivers the event
    to every registered + RUNNING plugin exactly once.

    ``event_service`` (WO-014-018) is the canonical EventService backed by
    the durable canonical repository (``DurableCanonicalEventRepository``),
    so production composition also exposes durable persistence of canonical
    Events behind the authoritative ``IEventRepository`` seam.

    ``entity_manager`` (WO-014-022) is the authoritative Entity owner used
    by the Event -> Entity projection.

    ``entity_read`` (WO-014-024) is a thin, read-only canonical read surface
    over ``entity_manager`` for downstream Entity consumers.

    ``projection_observability`` (WO-014-024) is the projection health/-
    observability signal (last projected event_id, Entity count, projection
    failure count).  Strictly diagnostic; never gates Event persistence.
    """

    pipeline: EventPipeline
    plugin_manager: PluginManager
    plugin_dispatcher: PluginDispatcher
    event_service: EventService
    entity_manager: EntityManager
    entity_read: EntityReadService
    projection_observability: ProjectionObservability
    entity_repository: Optional["object"] = None
    projection_checkpoint: Optional["object"] = None
    catch_up: Optional["object"] = None
    projection_recovery_health: Optional["object"] = None
    event_bus: Optional["object"] = None
    observation_service: Optional["object"] = None
    relation_repository: Optional["object"] = None
    delivery_dispatcher: Optional["object"] = None


def create_event_runtime(
    plugin_manager: Optional[PluginManager] = None,
    repository: Optional[IEventRepository] = None,
) -> EventRuntime:
    """Assemble the authoritative production Event -> Plugin composition.

    This is the single production composition root for the canonical path.
    It wires the pipeline to the plugin layer through the WO-014-002
    ``PluginDispatcher``, exactly once.

    WO-014-018: it also wires a canonical ``EventService`` backed by the
    durable canonical repository (``DurableCanonicalEventRepository``, the
    WO-014-016 SQLAlchemy implementation of ``IEventRepository``) so that the
    authoritative production runtime exposes durable persistence of canonical
    Events. Callers may inject an alternative ``IEventRepository`` for
    testing; by default the durable canonical repository is used.

    WO-014-020: the same durable repository is also wired into the
    ``EventPipeline`` persistence seam via ``pipeline.set_repository(...)``,
    so ``pipeline.process(event)`` durably persists each canonical Event
    through ``IEventRepository`` -> ``DurableCanonicalEventRepository`` ->
    the existing ``DatabaseSessionManager``. The pipeline and the
    ``EventService`` share the same single repository instance.

    Args:
        plugin_manager: Optional ``PluginManager`` to compose.  Defaults to
            the global singleton returned by ``get_plugin_manager()``.
        repository: Optional ``IEventRepository`` to back the canonical
            ``EventService``.  Defaults to a new
            ``DurableCanonicalEventRepository`` (which reuses the existing
            global ``DatabaseSessionManager`` via ``get_session_manager()``).

    Returns:
        An ``EventRuntime`` handle exposing the wired pipeline, manager,
        dispatcher and durable-backed ``event_service``.
        ``handle.pipeline.process(event)`` delivers the canonical ``Event``
        to every registered + RUNNING plugin.
    """
    manager = (
        plugin_manager if plugin_manager is not None else get_plugin_manager()
    )

    pipeline = EventPipeline()
    dispatcher = PluginDispatcher(plugin_manager=manager)
    pipeline.set_dispatcher(dispatcher)

    if repository is None:
        repository = DurableCanonicalEventRepository()
        _ensure_durable_database_ready(repository)
    event_service = EventService(repository=repository)
    pipeline.set_repository(repository)

    # WO-014-022 — Event -> Entity projection (additive wiring).
    # After the canonical Event has been durably persisted through the
    # repository above, the production runtime derives a projected Entity
    # state via EntityBridge -> EntityManager.  The projection is strictly
    # best-effort (EntityBridge never propagates) and isolated from durable
    # Event persistence, which remains the source of truth.
    #
    # WO-014-025 (OPTION A) — durable Entity state + durable projection
    # checkpoint. The production EntityManager is backed by the durable
    # SQLAlchemy Entity repository (single DatabaseSessionManager owner), and a
    # durable projection checkpoint records deterministic catch-up progress.
    entity_repository = _build_durable_entity_repository()
    entity_manager = EntityManager(repository=entity_repository)
    entity_bridge = EntityBridge(entity_manager=entity_manager)
    pipeline.set_projection(_project_event_to_entity(entity_bridge))

    # WO-014-024 — canonical Entity read-side + projection observability
    # (additive wiring).
    #
    # G2: expose a thin, read-only, canonical read surface over the
    # authoritative EntityManager for downstream consumers.
    entity_read = EntityReadService(entity_manager=entity_manager)
    #
    # G3: projection observability/health signal.  The recorder wraps the
    # projection callable so that (a) on success it records the projected
    # event_id + live Entity count, and (b) on failure it increments a
    # projection-failure counter and re-raises, preserving the pipeline's
    # WO-014-023 best-effort isolation.  It is strictly diagnostic and never
    # gates durable Event persistence.
    #
    # WO-014-025: ``last_projected_event_id`` is a read-through of the durable
    # projection checkpoint (survives restart), not an independent source.
    projection_checkpoint = _build_projection_checkpoint()
    projection_observability = ProjectionObservability(
        entity_manager=entity_manager,
        checkpoint_repository=projection_checkpoint,
    )
    # WO-016 — Durable Relation Projection (additive wiring).
    #
    # Downstream of the canonical Entity projection, the production runtime
    # also projects durable Entity RELATIONS from canonical Events.  A single
    # composite projection callable runs the Entity projection first and then
    # the durable Relation projection, so the EventPipeline keeps ONE
    # ``_projection`` seam, ONE event path and ONE dispatch plane.  The durable
    # relation repository reuses the single ``DatabaseSessionManager`` owner
    # (no second engine/sessionmaker/persistence plane).  The relation
    # projection is best-effort (never propagates), so it can never roll back
    # or prevent the already-durable canonical Event.
    relation_repository = _build_durable_relation_repository()
    relation_projector = project_relation_from_event(
        repository=relation_repository
    )

    def _composite_projection(event: Any) -> None:
        # Entity projection first (existing behavior), then durable relation
        # projection (WO-016), then the WO-017 lifecycle cascade, then the
        # WO-018 explicit relation severance.  All are best-effort and
        # isolated; a failure in one never rolls back the already-durable
        # canonical Event.
        _project_event_to_entity(entity_bridge)(event)
        relation_projector(event)
        _project_entity_lifecycle(event)
        _project_relation_severance(event)

    pipeline.set_projection(
        projection_observability.wrap(_composite_projection)
    )

    def _project_entity_lifecycle(event: Any) -> None:
        """WO-017 / ADR-ENTITY-RELATION-LIFECYCLE — deterministic entity-deactivation lifecycle.

        On the canonical ``ENTITY_REMOVED`` event, the referenced entity is
        durably TOMBSTONED (ACTIVE -> TOMBSTONED, no physical delete) and the
        entity-deactivation cascade inactivates (ACTIVE -> INACTIVE) every
        canonical relation referencing that entity.

        Lifecycle semantics (ratified ADR-ENTITY-RELATION-LIFECYCLE):
          * terminal states; no reactivation; no SUPERSEDED; no temporal
            validity; no explicit relation severance; no new EventType.
          * synchronous, deterministic, idempotent, replayable.
          * independent persistence transactions (consistent with the
            verified EVENT/ENTITY/RELATION independent-TX architecture) —
            never a single implicit atomic transaction.
          * best-effort: a failure is logged and never propagates, so it can
            never roll back or prevent the already-durable canonical Event.

        ``entity_id`` is the canonical ``Event.entity_id`` (Entity identity,
        distinct from ``Event.event_id``).  Events without an ``entity_id``
        are skipped deterministically.
        """
        try:
            if getattr(event, "event_type", None) != EventType.ENTITY_REMOVED:
                return
            entity_id = getattr(event, "entity_id", None)
            if not entity_id:
                return
            entity_repository.tombstone(str(entity_id))
            relation_repository.inactivate_for_entity(str(entity_id))
        except Exception:  # noqa: BLE001 - best-effort by design
            import logging

            logging.getLogger(__name__).exception(
                "WO-017 entity lifecycle cascade failed (best-effort, "
                "not propagating). event_id=%s entity_id=%s",
                getattr(event, "event_id", None),
                getattr(event, "entity_id", None),
            )

    def _project_relation_severance(event: Any) -> None:
        """WO-018 — Explicit canonical relation severance projection.

        On the canonical ``RELATION_SEVERED`` event, transition EXACTLY ONE
        deterministic relation ``ACTIVE -> INACTIVE`` (durable terminal),
        identified by the canonical deterministic ``relation_id`` derived from
        the event's relation triple.

        Architectural contract (WO-018 — Explicit Relation Severance):
          * affects ONLY the identified relation — it NEVER mutates either
            endpoint entity lifecycle state and NEVER cascades to other
            relations;
          * distinct from ``ENTITY_REMOVED`` (WO-017), which tombstones an
            entity and cascades to all its relations;
          * idempotent — reprocessing the same severance event is a safe
            no-op (already-INACTIVE relations are untouched);
          * durable — the row is updated in place through the single
            ``DatabaseSessionManager`` owner (no physical delete, no second
            DB/session owner);
          * deterministic identity — uses ``deterministic_relation_id``;
            the ``relation_id`` is never changed and never reactivated
            (INACTIVE is terminal in v1);
          * best-effort — a failure is logged and swallowed, so it can never
            roll back or prevent the already-durable canonical Event.

        The relation triple is read deterministically from the canonical
        payload (``source_entity_id`` [or ``event.entity_id``],
        ``target_entity_id`` / ``related_entity_id``, ``relation_type``),
        matching the established WO-016 relation-projection field contract.
        """
        try:
            if getattr(event, "event_type", None) != EventType.RELATION_SEVERED:
                return
            payload = dict(getattr(event, "payload", None) or {})
            source_entity_id = payload.get("source_entity_id") or getattr(
                event, "entity_id", None
            )
            target_entity_id = payload.get("target_entity_id") or payload.get(
                "related_entity_id"
            )
            relation_type = payload.get("relation_type")
            if not source_entity_id or not target_entity_id or not relation_type:
                import logging

                logging.getLogger(__name__).debug(
                    "WO-018 relation severance skipped (missing relation "
                    "triple). event_id=%s",
                    getattr(event, "event_id", None),
                )
                return
            relation_id = deterministic_relation_id(
                source_entity_id, target_entity_id, relation_type
            )
            relation_repository.sever_relation(relation_id)
        except Exception:  # noqa: BLE001 - best-effort by design
            import logging

            logging.getLogger(__name__).exception(
                "WO-018 relation severance failed (best-effort, "
                "not propagating). event_id=%s",
                getattr(event, "event_id", None),
            )

    # WO-014-025 — deterministic catch-up driver over the durable event log.
    # Wired so an embedding application can run catch-up on startup/interval.
    catch_up = _build_catch_up(repository, projection_checkpoint, entity_bridge)

    # WO-014-027 — production projection / recovery observability.
    #
    # A deterministic, READ-ONLY health/state contract over the durable
    # Event -> Entity projection and its catch-up recovery.  It composes the
    # SAME durable event repository and projection checkpoint used by the
    # production catch-up (single DatabaseSessionManager owner — no second
    # engine/sessionmaker/persistence plane).  It answers: current checkpoint,
    # durable projection backlog, latest recovery status/error, and a
    # deterministic healthy / degraded / recovering classification.
    #
    # The catch-up driver's ``run()`` is wrapped (additively) so that every
    # catch-up pass — including the WO-014-026 startup recovery — records its
    # outcome into the health contract.  The wrapper never alters catch-up
    # semantics (projection-first / checkpoint-second are untouched) and never
    # runs on the pipeline hot path.  Health inspection never advances the
    # checkpoint, never persists events, and never projects entities.
    projection_recovery_health = _build_projection_recovery_health(
        repository, projection_checkpoint
    )
    if catch_up is not None and projection_recovery_health is not None:
        _instrument_catch_up(catch_up, projection_recovery_health)

    # WO-015 — canonical EventBus + ObservationService production wiring.
    #
    # The canonical EventBus (app.event_bus.event_bus.EventBus) is wired into
    # the EventPipeline via set_event_bus(), so pipeline.process(event) reaches
    # the ObservationService with the canonical app.event.event.Event after the
    # durable repository + entity projection.  The ObservationService subscribes
    # to EventType.CUSTOM (the type produced by the production EventFactory for
    # source-adapter events) and adapts each canonical Event into an Observation
    # through the existing ObservationProcessor (single DatabaseSessionManager
    # owner; no second engine/sessionmaker/persistence plane).
    #
    # Observation persistence uses the canonical DatabaseSessionManager when it
    # is configured; otherwise the service is constructed but persistence is
    # left to the embedding application (mirrors the durable lifecycle guards
    # above, and never forces a database to appear in runtime-only tests).
    event_bus = EventBus()
    observation_service = _build_observation_service()
    if observation_service is not None:
        observation_service.subscribe_canonical(event_bus)
        pipeline.set_event_bus(event_bus)

    return EventRuntime(
        pipeline=pipeline,
        plugin_manager=manager,
        plugin_dispatcher=dispatcher,
        event_service=event_service,
        entity_manager=entity_manager,
        entity_read=entity_read,
        projection_observability=projection_observability,
        entity_repository=entity_repository,
        projection_checkpoint=projection_checkpoint,
        catch_up=catch_up,
        projection_recovery_health=projection_recovery_health,
        event_bus=event_bus,
        observation_service=observation_service,
        relation_repository=relation_repository,
    )


def _project_event_to_entity(entity_bridge: EntityBridge):
    """Return a deterministic canonical ``Event`` -> Entity projection callable.

    The returned callable adapts a canonical ``app.event.event.Event`` into
    the ``EntityBridge.process_event`` contract (``event_data`` dict carrying
    ``entity_type`` + ``entity_id``).  The ``entity_type`` is derived
    deterministically from the canonical ``Event.event_type`` value, the
    ``entity_id`` from ``Event.entity_id``, and the entity attribute payload
    from ``Event.payload``.  Events without an ``entity_id`` are skipped by
    the bridge (no projection), which is safe and deterministic.

    Projection failures are swallowed by ``EntityBridge`` (best-effort), so
    they never roll back or prevent the already-durable canonical Event.
    """
    def project(event: Event) -> None:
        entity_bridge.process_event(
            event_data={
                "entity_type": event.event_type.value,
                "entity_id": event.entity_id,
                "entity": dict(event.payload),
            },
            event_id=event.event_id,
            correlation_id=(
                event.metadata.correlation_id if event.metadata else None
            ),
        )
    return project


# ---------------------------------------------------------------------------
# WO-014-017 — Canonical durable repository production composition (additive)
# ---------------------------------------------------------------------------
# This additive composition path wires the canonical EventService to the
# WO-014-016 durable canonical repository behind the authoritative
# IEventRepository seam:
#
#     canonical Event
#         |
#         v
#     EventService(repository=IEventRepository)
#         |
#         v
#     DurableCanonicalEventRepository   (WO-014-016 SQLAlchemy durable impl)
#         |
#         v
#     DurableCanonicalEvent
#         |
#         v
#     existing DatabaseSessionManager
#
# It is strictly ADDITIVE. The existing ``create_event_runtime`` composition
# root and any legacy production default are left untouched. No second DB
# engine, session manager, or repository interface is introduced.
from typing import Optional

from app.event_service.event_service import EventService
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository as DurableCanonicalEventRepository,
)
from app.event_repository.interfaces.i_event_repository import IEventRepository


def _ensure_durable_database_ready(repository: IEventRepository) -> None:
    """Ensure the canonical durable persistence plane's table is ready.

    Closes the WO-014-021 lifecycle gap: the production composition root
    (``create_event_runtime``) wires the durable canonical repository into the
    ``EventPipeline`` persistence seam, but never initialised the durable
    table.  This helper brings the durable table up (via the repository's own
    ``initialize()`` -> ``Base.metadata.create_all`` on the single existing
    ``DatabaseSessionManager`` engine) so that ``pipeline.process(event)`` can
    durably persist out-of-the-box.

    This mirrors the already-approved convention in
    ``durable_build_default_components()``: the canonical database owner
    (``DatabaseSessionManager``) is configured by the embedding application
    (``configure_session_manager`` / ``initialize_database``), and the
    composition initialises the durable table on top of it.  It never
    constructs a second engine, sessionmaker, or database singleton
    (INVARIANT 4).

    Test-safety: if no session manager is configured yet (e.g. runtime-only
    tests that exercise the pipeline without persistence), the table
    initialisation is skipped rather than forcing a database to appear.  Both
    ``DatabaseSessionManager.initialize`` and the repository initialisation are
    internally idempotent, so repeated composition calls are safe.
    """
    if not _session_manager_ready():
        # No CONFIGURED-AND-INITIALISED session manager: persistence is not
        # active for this composition. Leave the lifecycle to the embedding
        # application. (A manager that exists but is not initialised is treated
        # as not ready, so a stale global manager cannot crash composition.)
        return
    repository.initialize()


def _session_manager_ready() -> bool:
    """Return True if the canonical DatabaseSessionManager is configured AND
    initialised (an engine is bound).

    Test-safety: composition that exercises the runtime without persistence
    must not force a database to appear. ``engine`` raises ``RuntimeError``
    when the manager exists but is not initialised, so both "not configured"
    and "configured but not initialised" are correctly treated as not ready.
    Mirrors ``_ensure_durable_database_ready``.
    """
    try:
        get_session_manager().engine
        return True
    except RuntimeError:
        return False


def session_manager_ready() -> bool:
    """Public wrapper for ``_session_manager_ready`` (WO-027 bootstrap wiring)."""
    return _session_manager_ready()


def _build_durable_entity_repository() -> "SQLAlchemyEntityRepository":
    """Build the durable Entity repository over the single DB owner (WO-014-025).

    Constructs ``SQLAlchemyEntityRepository`` (the production durable
    implementation of the Entity ``IRepository`` used by :class:`EntityManager`),
    which reuses the canonical ``DatabaseSessionManager``. Initialises the
    durable ``entities`` table on the shared ``Base.metadata`` when the session
    manager is configured. No second engine/sessionmaker/owner is created.
    """
    repo = SQLAlchemyEntityRepository()
    if _session_manager_ready():
        repo.initialize()
    return repo


def _build_projection_checkpoint() -> "ProjectionCheckpointRepository":
    """Build the durable projection checkpoint over the single DB owner.

    Initialises the ``projection_checkpoint`` table on the shared
    ``Base.metadata`` when the session manager is configured. Single owner.
    """
    repo = ProjectionCheckpointRepository()
    if _session_manager_ready():
        repo.initialize()
    return repo


def _build_durable_relation_repository() -> "SQLAlchemyRelationRepository":
    """Build the durable Entity-relation repository over the single DB owner.

    Constructs ``SQLAlchemyRelationRepository`` (the durable implementation of
    the Relation ``IRelationRepository``), which reuses the canonical
    ``DatabaseSessionManager``.  Initialises the durable ``entity_relations``
    table on the shared ``Base.metadata`` when the session manager is
    configured.  No second engine/sessionmaker/owner is created.
    """
    repo = SQLAlchemyRelationRepository()
    if _session_manager_ready():
        repo.initialize()
    return repo


def _resolve_durable_event_repo(repository: IEventRepository):
    """Resolve the durable canonical event repository for sequential retrieval.

    When an injected (non-durable) ``IEventRepository`` is supplied, fall back
    to a ``SQLAlchemyEventRepository`` over the same canonical
    ``DatabaseSessionManager`` owner.  Used by the catch-up driver and the
    projection/recovery health contract so both observe the SAME durable event
    log (no second owner, no second plane).
    """
    from app.event_repository.durable.sqlalchemy_event_repository import (
        SQLAlchemyEventRepository,
    )

    if isinstance(repository, SQLAlchemyEventRepository):
        return repository
    return SQLAlchemyEventRepository()


def _build_catch_up(
    repository: IEventRepository,
    checkpoint_repository: ProjectionCheckpointRepository,
    entity_bridge: EntityBridge,
) -> Optional[ProjectionCatchUp]:
    """Build the deterministic catch-up driver (WO-014-025 §E).

    Returns ``None`` when persistence is not active (no session manager), so a
    runtime-only composition does not force a database to appear.
    """
    if not _session_manager_ready():
        return None
    event_repo = _resolve_durable_event_repo(repository)
    return ProjectionCatchUp(
        event_repository=event_repo,
        checkpoint_repository=checkpoint_repository,
        projection=_project_event_to_entity(entity_bridge),
    )


def _build_projection_recovery_health(
    repository: IEventRepository,
    checkpoint_repository: ProjectionCheckpointRepository,
) -> Optional[ProjectionRecoveryHealth]:
    """Build the deterministic projection/recovery health contract (WO-014-027).

    Composes the SAME durable event repository and projection checkpoint used
    by the production catch-up, so observability reflects the authoritative
    projection/recovery state.  Returns ``None`` when persistence is not
    active (no session manager) — matching the catch-up driver — so a
    runtime-only composition does not force a database to appear and the
    health contract does not report misleading durable state.
    """
    if not _session_manager_ready():
        return None
    event_repo = _resolve_durable_event_repo(repository)
    return ProjectionRecoveryHealth(
        checkpoint_repository=checkpoint_repository,
        event_repository=event_repo,
    )


def _build_observation_service() -> Optional[ObservationService]:
    """Build the production ObservationService (WO-015).

    Constructs ``ObservationService`` (the canonical Event -> Observation
    component) backed by a session from the canonical
    ``DatabaseSessionManager`` — the single database owner.  The ``observations``
    table lives on the shared ``Base.metadata``, so it is created with the same
    ``create_all`` used by the durable event/entity/checkpoint tables.

    Returns ``None`` when persistence is not active (no session manager), so a
    runtime-only composition does not force a database to appear — mirroring the
    other durable lifecycle guards.  When a session manager is configured, a
    durable observation session is created for the service.  No second engine /
    sessionmaker / persistence plane is introduced.
    """
    if not _session_manager_ready():
        return None
    from app.database.session import get_session_manager

    session = get_session_manager().get_session()
    return ObservationService(event_bus=None, session=session)


def wire_durable_delivery(
    *,
    pipeline: EventPipeline,
    plugin_dispatcher: PluginDispatcher,
    event_bus: EventBus,
    repository: Any,
) -> DurableDeliveryDispatcher:
    """WO-027 — wire the durable post-commit delivery dispatcher.

    Builds a ``DurableDeliveryDispatcher`` backed by the single
    ``DatabaseSessionManager`` (no second DB owner), registers two durable
    consumers (``"plugins"`` -> ``PluginDispatcher.dispatch`` and
    ``"observation"`` -> ``event_bus.publish``), initialises the outbox table,
    and attaches the dispatcher to the pipeline so that ``pipeline.process``
    atomically commits the canonical event + PENDING outbox records, then
    delivers to consumers post-commit via the durable outbox.  Each consumer
    has an independent durable delivery record (AT-LEAST-ONCE, per-consumer
    state; failure of one never blocks the other).
    """
    from app.event_delivery.outbox_repository import SQLAlchemyOutboxRepository
    from app.event_delivery.plugin_idempotency_ledger import PluginDeliveryLedger

    outbox = SQLAlchemyOutboxRepository()
    outbox.initialize()
    dispatcher = DurableDeliveryDispatcher(
        outbox_repository=outbox,
        event_repository=repository,
    )

    def _deliver_plugins(event: Any) -> None:
        # Post-commit fan-out to every registered + RUNNING plugin.  Each
        # plugin is individually isolated by PluginManager.deliver_event.
        plugin_dispatcher.dispatch(event)

    def _deliver_observation(event: Any) -> None:
        event_bus.publish(event)

    dispatcher.register_consumer("plugins", _deliver_plugins)
    dispatcher.register_consumer("observation", _deliver_observation)

    # WO-029 durable plugin-delivery idempotency boundary.  Attach the durable
    # (event_id, plugin_id) ledger to the plugin manager so each running
    # plugin's side effect is executed at most once per canonical event_id
    # (AT-LEAST-ONCE with a durable idempotency boundary).  No second DB owner.
    ledger = PluginDeliveryLedger()
    ledger.initialize()
    plugin_manager = plugin_dispatcher._plugin_manager
    plugin_manager.set_plugin_delivery_ledger(ledger)

    pipeline.set_delivery_dispatcher(dispatcher)
    pipeline.set_outbox_consumer_ids(["plugins", "observation"])
    return dispatcher


def _instrument_catch_up(
    catch_up: ProjectionCatchUp,
    health: ProjectionRecoveryHealth,
) -> None:
    """Additively wrap ``catch_up.run()`` to record its outcome (WO-014-027).

    This is a thin, non-invasive observer: it does NOT modify
    ``ProjectionCatchUp`` itself and does NOT change its semantics
    (projection-first / checkpoint-second / stop-at-first-failure are all
    untouched).  On a successful pass it records the returned ``CatchUpResult``
    (so ``failed>0`` is surfaced as a DEGRADED state); on an exception it
    records the error and re-raises exactly as the caller expects (the
    bootstrap startup path already isolates/logs that exception).
    """
    original_run = catch_up.run

    def observed_run():
        try:
            result = original_run()
        except Exception as exc:  # noqa: BLE001 - re-raised unchanged below
            health.record_recovery(error=exc)
            raise
        health.record_recovery(result=result)
        return result

    catch_up.run = observed_run  # type: ignore[method-assign]


@dataclass(frozen=True)
class DurableEventRuntime:
    """A wired canonical durable event-runtime handle.

    Exposes the canonical EventService backed by the durable canonical
    repository. ``runtime.event_service.save_event(event)`` persists the
    canonical ``Event`` durably; ``get_event`` / ``get_events`` return
    canonical ``Event`` objects.
    """

    event_service: EventService
    repository: IEventRepository


def durable_build_default_components(
    repository: Optional[IEventRepository] = None,
) -> DurableEventRuntime:
    """Assemble the canonical durable EventService composition.

    Constructs an ``EventService`` backed by a ``DurableCanonicalEventRepository``
    (the WO-014-016 SQLAlchemy durable implementation of ``IEventRepository``)
    by default. Callers may inject an alternative ``IEventRepository`` for
    testing.

    Args:
        repository: Optional ``IEventRepository`` to compose. Defaults to a
            new ``DurableCanonicalEventRepository`` (which reuses the existing
            global ``DatabaseSessionManager`` via ``get_session_manager()``).

    Returns:
        A ``DurableEventRuntime`` handle exposing the wired EventService and
        its repository. The durable repository's table is initialised via the
        existing database infrastructure.
    """
    if repository is None:
        repository = DurableCanonicalEventRepository()
        repository.initialize()

    event_service = EventService(repository=repository)

    return DurableEventRuntime(
        event_service=event_service,
        repository=repository,
    )

