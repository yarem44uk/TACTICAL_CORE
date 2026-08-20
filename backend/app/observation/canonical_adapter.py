"""Canonical Event -> Observation adapter (WO-015).

WO-015 migrates ObservationService from the legacy ``app.core.event_bus``
EventBus to the canonical ``app.event_bus.event_bus.EventBus`` reached through
``EventPipeline.set_event_bus()``.  The canonical EventBus delivers canonical
``app.event.event.Event`` objects to subscribers; the Observation subsystem
consumes its own ``app.observation.models.CanonicalEvent`` representation
(``data`` payload, connector-style ``event_type`` strings, plain-dict
``metadata``).

This adapter performs the smallest explicit, deterministic translation between
the two representations, entirely inside the Observation boundary:

    canonical app.event.event.Event
        |
        v
    CanonicalEventToObservationAdapter.to_observation_dict(event)
        |
        v
    observation CanonicalEvent / observation processing
        |
        v
    Observation

Mapping:

    canonical.event_id            -> event_id
    canonical.source              -> source  (e.g. "signal", "mqtt", ...)
    canonical.payload             -> data    (observation payload)
    canonical.timestamp           -> timestamp
    canonical.metadata            -> metadata (flattened plain dict)
    canonical.source              -> event_type derivation
                                     signal   -> "signal.message"
                                     radio    -> "radio.transmission"
                                     atak     -> "atak.map_object"
                                     mqtt     -> "mqtt.message"
                                     telegram -> "telegram.message"
                                     (fallback -> canonical.event_type value)

``immutable_id`` is preserved as the canonical ``event_id`` by the existing
mapper (``EventToObservationMapper.map_event_to_observation``), unchanged.

No source adapter, EventFactory, canonical Event, or legacy EventBus code is
modified or removed.  This module is additive and narrowly scoped to the
Observation boundary.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.event.event import Event

# Deterministic canonical source name -> observation event_type mapping.
# Mirrors EVENT_TYPE_MAPPINGS in app.observation.models.
_SOURCE_TO_EVENT_TYPE: Dict[str, str] = {
    "signal": "signal.message",
    "radio": "radio.transmission",
    "atak": "atak.map_object",
    "mqtt": "mqtt.message",
    "telegram": "telegram.message",
}


class CanonicalEventAdapterError(Exception):
    """Raised when a canonical Event cannot be adapted for Observation."""


class CanonicalEventToObservationAdapter:
    """Translate a canonical ``app.event.event.Event`` for the Observation layer.

    The adapter is stateless and deterministic: the same canonical Event always
    produces the same observation payload.  It never mutates the canonical
    Event and never touches persistence.
    """

    def __init__(
        self,
        source_to_event_type: Optional[Dict[str, str]] = None,
    ) -> None:
        self._source_to_event_type = {
            **_SOURCE_TO_EVENT_TYPE,
            **(source_to_event_type or {}),
        }

    def derive_event_type(self, event: Event) -> str:
        """Derive the observation event-type string from a canonical Event.

        Uses ``Event.source`` (the connector name) as the primary key.  Falls
        back to the canonical ``Event.event_type`` value so that canonical
        Events with a non-CUSTOM type still map deterministically.
        """
        source = getattr(event, "source", "") or ""
        mapped = self._source_to_event_type.get(source)
        if mapped is not None:
            return mapped
        event_type = getattr(event, "event_type", None)
        if event_type is not None:
            value = getattr(event_type, "value", str(event_type))
            if value:
                return value
        return "custom"

    def _flatten_metadata(self, event: Event) -> Dict[str, Any]:
        """Flatten canonical EventMetadata into a plain dict for the mapper.

        The Observation mapper reads ``metadata.get(...)`` for confidence,
        tags, correlation_id, trace_id, driver_id, device_id, operator_id.
        The canonical EventMetadata carries ``tags``, ``properties`` (dict,
        including ``source_name`` and any extra properties) and
        ``correlation_id``.  We merge them so all of those reads succeed.
        """
        metadata_obj = getattr(event, "metadata", None)
        flattened: Dict[str, Any] = {}
        if metadata_obj is not None:
            properties = getattr(metadata_obj, "properties", None)
            if isinstance(properties, dict):
                flattened.update(properties)
            tags = getattr(metadata_obj, "tags", None)
            if tags is not None:
                flattened["tags"] = list(tags)
            correlation_id = getattr(metadata_obj, "correlation_id", None)
            if correlation_id is not None:
                flattened["correlation_id"] = correlation_id
        return flattened

    def to_observation_dict(self, event: Event) -> Dict[str, Any]:
        """Adapt a canonical Event into the observation-layer dict.

        The returned dict is shaped for
        ``ObservationProcessor.process_event`` /
        ``app.observation.models.CanonicalEvent.from_dict``:
        keys ``event_id``, ``event_type``, ``timestamp``, ``source``, ``data``,
        ``metadata``.

        Raises:
            CanonicalEventAdapterError: If the canonical Event is malformed.
        """
        if not hasattr(event, "event_id") or not getattr(event, "event_id", None):
            raise CanonicalEventAdapterError(
                "Canonical Event is missing a non-empty event_id"
            )

        payload = getattr(event, "payload", None)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            # Deterministic fallback: wrap scalar payloads.
            payload = {"value": payload}

        timestamp = getattr(event, "timestamp", None)

        return {
            "event_id": event.event_id,
            "event_type": self.derive_event_type(event),
            "timestamp": timestamp,
            "source": getattr(event, "source", "") or "",
            "data": dict(payload),
            "metadata": self._flatten_metadata(event),
        }
