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
    """

    pipeline: EventPipeline
    plugin_manager: PluginManager
    plugin_dispatcher: PluginDispatcher


def create_event_runtime(
    plugin_manager: Optional[PluginManager] = None,
) -> EventRuntime:
    """Assemble the authoritative production Event -> Plugin composition.

    This is the single production composition root for the canonical path.
    It wires the pipeline to the plugin layer through the WO-014-002
    ``PluginDispatcher``, exactly once.

    Args:
        plugin_manager: Optional ``PluginManager`` to compose.  Defaults to
            the global singleton returned by ``get_plugin_manager()``.

    Returns:
        An ``EventRuntime`` handle exposing the wired pipeline, manager and
        dispatcher.  ``handle.pipeline.process(event)`` delivers the
        canonical ``Event`` to every registered + RUNNING plugin.
    """
    manager = (
        plugin_manager if plugin_manager is not None else get_plugin_manager()
    )

    pipeline = EventPipeline()
    dispatcher = PluginDispatcher(plugin_manager=manager)
    pipeline.set_dispatcher(dispatcher)

    return EventRuntime(
        pipeline=pipeline,
        plugin_manager=manager,
        plugin_dispatcher=dispatcher,
    )
