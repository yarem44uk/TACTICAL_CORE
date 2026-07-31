"""Event to Observation Mapper.

Maps Canonical Events to Observation objects.
Handles event type detection and field transformation.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID, uuid4

from app.intelligence.observation.schema import ObservationCreate, ProvenanceData
from app.observation.models import (
    CanonicalEvent,
    ObservationMapping,
    EVENT_TYPE_MAPPINGS,
    DEFAULT_MAPPING,
)


logger = logging.getLogger(__name__)


class EventMappingError(Exception):
    """Raised when event mapping fails."""

    pass


class EventToObservationMapper:
    """Maps Canonical Events to ObservationCreate schemas.

    This mapper is responsible for:
    1. Determining the correct ObservationType for an event
    2. Extracting and transforming event fields
    3. Creating the ProvenanceData for the observation
    4. Generating the evidence payload

    Usage:
        >>> mapper = EventToObservationMapper()
        >>> observation_create = mapper.map_event_to_observation(canonical_event)
    """

    def __init__(self, custom_mappings: Optional[Dict[str, ObservationMapping]] = None):
        """Initialize the mapper.

        Args:
            custom_mappings: Optional custom event type mappings.
        """
        self._mappings = {**EVENT_TYPE_MAPPINGS}
        if custom_mappings:
            self._mappings.update(custom_mappings)

    def get_mapping(self, event_type: str) -> ObservationMapping:
        """Get the mapping for an event type.

        Args:
            event_type: The canonical event type.

        Returns:
            ObservationMapping for the event type.
        """
        # Exact match
        if event_type in self._mappings:
            return self._mappings[event_type]

        # Pattern matching for wildcard support
        for pattern, mapping in self._mappings.items():
            if pattern != "*" and self._matches_pattern(event_type, pattern):
                return mapping

        # Default fallback
        return DEFAULT_MAPPING

    @staticmethod
    def _matches_pattern(event_type: str, pattern: str) -> bool:
        """Check if event type matches a pattern.

        Args:
            event_type: The event type to check.
            pattern: The pattern to match against.

        Returns:
            True if matches.
        """
        if pattern == "*":
            return True
        if pattern.startswith("*."):
            return event_type.endswith(pattern[1:])
        if pattern.endswith(".*"):
            return event_type.startswith(pattern[:-1])
        return event_type == pattern

    def map_event_to_observation(
        self,
        event: CanonicalEvent,
        custom_immutable_id: Optional[str] = None,
    ) -> ObservationCreate:
        """Map a Canonical Event to an ObservationCreate schema.

        Args:
            event: The canonical event to map.
            custom_immutable_id: Optional immutable ID override.

        Returns:
            ObservationCreate schema ready for persistence.

        Raises:
            EventMappingError: If mapping fails.
        """
        mapping = self.get_mapping(event.event_type)

        # Build evidence payload from event data
        evidence_payload = self._build_evidence_payload(event, mapping)

        # Build provenance
        provenance = self._build_provenance(event)

        # Determine immutable ID
        immutable_id = custom_immutable_id or event.event_id

        # Determine confidence
        confidence = event.data.get(
            "confidence",
            event.metadata.get("confidence", mapping.default_confidence),
        )

        # Create ObservationCreate
        observation_create = ObservationCreate(
            source=event.source,
            source_type=mapping.source_type,
            evidence_payload=evidence_payload,
            observation_type=mapping.observation_type,
            immutable_id=immutable_id,
            provenance=provenance,
            source_confidence=confidence,
            tags=self._extract_tags(event, mapping),
        )

        logger.debug(
            f"Mapped event {event.event_id} ({event.event_type}) "
            f"to observation type {mapping.observation_type}"
        )

        return observation_create

    def _build_evidence_payload(
        self,
        event: CanonicalEvent,
        mapping: ObservationMapping,
    ) -> Dict[str, Any]:
        """Build the evidence payload from event data.

        Args:
            event: The canonical event.
            mapping: The observation mapping.

        Returns:
            Evidence payload dictionary.
        """
        payload = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "original_timestamp": event.timestamp.isoformat(),
            "raw_data": event.data,
        }

        # Apply field mapping
        for event_field, obs_field in mapping.field_mapping.items():
            if event_field in event.data:
                payload[obs_field] = event.data[event_field]

        return payload

    def _build_provenance(self, event: CanonicalEvent) -> ProvenanceData:
        """Build provenance data from event metadata.

        Args:
            event: The canonical event.

        Returns:
            ProvenanceData with provenance information.
        """
        return ProvenanceData(
            driver_id=event.metadata.get("driver_id"),
            device_id=event.metadata.get("device_id"),
            operator_id=event.metadata.get("operator_id"),
            original_timestamp=event.timestamp,
            capture_method=f"event_bus:{event.event_type}",
            raw_source_reference=f"event://{event.source}/{event.event_id}",
            observation_metadata={
                "event_source": event.source,
                "correlation_id": event.metadata.get("correlation_id"),
                "trace_id": event.metadata.get("trace_id"),
            },
        )

    def _extract_tags(
        self,
        event: CanonicalEvent,
        mapping: ObservationMapping,
    ) -> list:
        """Extract tags from event.

        Args:
            event: The canonical event.
            mapping: The observation mapping.

        Returns:
            List of tags.
        """
        tags = [mapping.observation_type, event.source]

        # Add any tags from event metadata
        if "tags" in event.metadata:
            tags.extend(event.metadata["tags"])

        return list(set(tags))  # Remove duplicates

    def is_supported_event_type(self, event_type: str) -> bool:
        """Check if an event type is supported.

        Args:
            event_type: The event type to check.

        Returns:
            True if the event type has a mapping.
        """
        return event_type in self._mappings

    def get_supported_event_types(self) -> list:
        """Get list of supported event types.

        Returns:
            List of supported event type strings.
        """
        return [
            k for k in self._mappings.keys() if k != "*"
        ]
