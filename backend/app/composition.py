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
    """

    pipeline: EventPipeline
    plugin_manager: PluginManager
    plugin_dispatcher: PluginDispatcher
    event_service: EventService


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
    event_service = EventService(repository=repository)

    return EventRuntime(
        pipeline=pipeline,
        plugin_manager=manager,
        plugin_dispatcher=dispatcher,
        event_service=event_service,
    )


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

