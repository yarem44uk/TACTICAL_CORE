"""Canonical Event → Plugin production dispatcher.

WO-014-002 — Canonical Event to Plugin production wiring.

This module provides the single authoritative production bridge from the
canonical Event pipeline into the plugin layer:

    canonical app.event.Event
        |
        v
    EventPipeline.set_dispatcher(...)
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

Design intent
-------------
``PluginDispatcher`` is a thin adapter between the generic
``EventPipeline`` dispatcher contract (``dispatch(event)``) and the already
approved ``PluginManager.deliver_event(Event)`` API.  It intentionally:

  * carries NO EventBus semantics,
  * adds NO middleware / hooks / persistence / transformation / copying,
  * does NOT duplicate ``PluginManager.deliver_event`` logic (canonical
    validation, RUNNING filtering, registry lookup, per-plugin exception
    isolation, plugin iteration, lifecycle checks).

All delivery semantics are owned by ``PluginManager.deliver_event()``.  This
adapter only forwards the canonical Event to it, preserving exact object
identity (no conversion to dict / EventResult / JSON).
"""

from __future__ import annotations

from typing import Optional

from app.event.event import Event
from app.plugins.manager.plugin_manager import PluginManager, get_plugin_manager


class PluginDispatcher:
    """Dispatcher adapter from EventPipeline into the plugin layer.

    The class exposes the single-method contract expected by
    ``EventPipeline.set_dispatcher``: ``dispatch(event)``.
    """

    def __init__(self, plugin_manager: Optional[PluginManager] = None) -> None:
        """Create a plugin dispatcher.

        Args:
            plugin_manager: The ``PluginManager`` that owns delivery semantics.
                Defaults to the module-level singleton from
                ``get_plugin_manager()`` when not supplied.
        """
        self._plugin_manager: PluginManager = (
            plugin_manager if plugin_manager is not None else get_plugin_manager()
        )

    def dispatch(self, event: Event) -> None:
        """Deliver a canonical Event to the plugin layer.

        Args:
            event: The canonical ``app.event.Event`` to deliver.

        Raises:
            TypeError: If ``event`` is not a canonical ``Event`` instance
                (raised by ``PluginManager.deliver_event``).
        """
        self._plugin_manager.deliver_event(event)
