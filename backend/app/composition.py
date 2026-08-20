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
from typing import Optional

from app.event.event import Event  # noqa: F401  (public type re-export)
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
    pipeline.set_projection(projection_observability.wrap(_project_event_to_entity(entity_bridge)))

    # WO-014-025 — deterministic catch-up driver over the durable event log.
    # Wired so an embedding application can run catch-up on startup/interval.
    catch_up = _build_catch_up(repository, projection_checkpoint, entity_bridge)

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
    from app.event_repository.durable.sqlalchemy_event_repository import (
        SQLAlchemyEventRepository,
    )

    # The catch-up driver needs the durable event repository's sequential
    # retrieval API. When an injected (non-durable) repository is supplied,
    # fall back to a durable repository over the same owner.
    event_repo = repository
    if not isinstance(event_repo, SQLAlchemyEventRepository):
        event_repo = SQLAlchemyEventRepository()
    return ProjectionCatchUp(
        event_repository=event_repo,
        checkpoint_repository=checkpoint_repository,
        projection=_project_event_to_entity(entity_bridge),
    )


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

