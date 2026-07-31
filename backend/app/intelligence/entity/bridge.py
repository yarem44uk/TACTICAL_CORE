"""Entity Bridge Module.

This module provides the bridge between Observation and Entity subsystems.
It integrates with the ObservationEngine via the pipeline_forwarder callback.

The bridge:
1. Receives Observations after processing
2. Extracts external identity from evidence_payload
3. Resolves or creates Entity via EntityManager
4. Handles identity mapping
5. Returns success/failure to preserve Observation pipeline

Author: WO-008-009-REWORK Implementation
Version: 1.0
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID

from app.intelligence.entity import (
    Entity,
    EntityData,
    EntityType,
    EntityStatus,
    EntityManager,
)
from app.intelligence.entity.entity_manager import SQLAlchemyEntityRepository
from app.intelligence.observation.model import Observation

logger = logging.getLogger(__name__)


# Mapping from observation sources to entity identity fields
IDENTITY_FIELD_MAPPING = {
    "signal_connector": {
        "identity_fields": ["sender", "message_id"],
        "entity_type": EntityType.CONTACT,
        "callsign_field": "sender",
    },
    "telegram_connector": {
        "identity_fields": ["from_user", "message_id"],
        "entity_type": EntityType.CONTACT,
        "callsign_field": "from_user.username",
    },
    "mqtt_connector": {
        "identity_fields": ["topic", "client_id"],
        "entity_type": EntityType.UNIT,
        "callsign_field": "client_id",
    },
    "radio_connector": {
        "identity_fields": ["callsign", "frequency"],
        "entity_type": EntityType.CONTACT,
        "callsign_field": "callsign",
    },
    "atak_connector": {
        "identity_fields": ["uid", "callsign"],
        "entity_type": EntityType.UNIT,
        "callsign_field": "callsign",
    },
}


class EntityBridgeError(Exception):
    """Raised when entity bridge operations fail."""
    pass


class EntityBridge:
    """Bridge between Observation and Entity subsystems.

    This class integrates with ObservationEngine via pipeline_forwarder.
    It extracts identity from Observations and creates/links Entities.

    Usage:
        >>> from sqlalchemy.orm import Session
        >>> from app.intelligence.entity.bridge import EntityBridge, create_entity_forwarder
        >>>
        >>> # Create bridge with session
        >>> session = get_session()
        >>> bridge = EntityBridge(session)
        >>>
        >>> # Create forwarder callback for ObservationEngine
        >>> forwarder = create_entity_forwarder(session)
        >>>
        >>> # Or use directly as pipeline_forwarder
        >>> engine = ObservationEngine(session, pipeline_forwarder=forwarder)
    """

    def __init__(
        self,
        session: Any,  # SQLAlchemy Session
        identity_mappings: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """Initialize Entity Bridge.

        Args:
            session: SQLAlchemy database session.
            identity_mappings: Optional custom identity field mappings.
        """
        self._session = session
        self._mappings = identity_mappings or IDENTITY_FIELD_MAPPING

        # Create SQL repository and manager
        self._repository = SQLAlchemyEntityRepository(session)
        self._manager = EntityManager(repository=self._repository)

    async def forward(self, observation: Observation) -> bool:
        """Forward observation to entity system.

        This method is called by ObservationEngine via pipeline_forwarder.
        It extracts identity from the observation and creates/links an Entity.

        Args:
            observation: The processed observation.

        Returns:
            True if entity was created/linked, False otherwise.
        """
        try:
            # Step 1: Extract identity from observation
            identity_result = self._extract_identity(observation)

            if identity_result is None:
                # No identity available for this observation
                logger.debug(
                    f"Observation {observation.id} has no extractable identity, "
                    f"skipping entity creation"
                )
                return False

            source, external_id, entity_type, entity_data = identity_result

            # Step 2: Resolve or create entity
            entity, created = await self._manager.resolve_or_create(
                entity_type=entity_type,
                source=source,
                external_id=external_id,
                data=entity_data,
                confidence=observation.source_confidence,
            )

            # Step 3: Log the result
            if created:
                logger.info(
                    f"Created Entity {entity.id} from observation {observation.id}, "
                    f"source={source}, external_id={external_id[:20]}..."
                )
            else:
                logger.debug(
                    f"Resolved existing Entity {entity.id} for observation {observation.id}, "
                    f"source={source}, external_id={external_id[:20]}..."
                )

            return True

        except Exception as e:
            logger.error(
                f"Entity bridge failed for observation {observation.id}: {e}",
                exc_info=True
            )
            # Return False to preserve Observation pipeline
            # Do NOT raise - would break Observation processing
            return False

    def _extract_identity(
        self,
        observation: Observation,
    ) -> Optional[Tuple[str, str, EntityType, Optional[EntityData]]]:
        """Extract external identity from observation.

        Args:
            observation: The observation to extract identity from.

        Returns:
            Tuple of (source, external_id, entity_type, entity_data) or None.
        """
        # Get mapping for this source
        source_mapping = self._mappings.get(observation.source)

        if not source_mapping:
            logger.debug(f"No identity mapping for source: {observation.source}")
            return None

        identity_fields = source_mapping.get("identity_fields", [])
        entity_type = source_mapping.get("entity_type", EntityType.CONTACT)

        # Extract identity values from evidence_payload
        evidence = observation.evidence_payload

        if not isinstance(evidence, dict):
            logger.warning(f"Observation {observation.id} has non-dict evidence_payload")
            return None

        # Build external_id from identity fields
        identity_parts = []
        for field in identity_fields:
            value = self._get_nested_value(evidence, field)
            if value:
                identity_parts.append(str(value))

        if not identity_parts:
            logger.debug(f"No identity fields found in observation {observation.id}")
            return None

        # Create deterministic external_id
        external_id = "|".join(identity_parts)

        # Extract entity data (callsign, name, etc.)
        entity_data = self._extract_entity_data(observation, source_mapping)

        return (observation.source, external_id, entity_type, entity_data)

    def _get_nested_value(self, data: Dict[str, Any], key_path: str) -> Any:
        """Get nested value from dict using dot notation.

        Args:
            data: Dictionary to search.
            key_path: Dot-separated key path (e.g., "from_user.id").

        Returns:
            Value at key path or None.
        """
        keys = key_path.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None

            if value is None:
                return None

        return value

    def _extract_entity_data(
        self,
        observation: Observation,
        source_mapping: Dict[str, Any],
    ) -> Optional[EntityData]:
        """Extract entity data from observation.

        Args:
            observation: The observation.
            source_mapping: Source-specific mapping.

        Returns:
            EntityData instance or None.
        """
        callsign_field = source_mapping.get("callsign_field")

        if not callsign_field:
            return None

        callsign = self._get_nested_value(observation.evidence_payload, callsign_field)

        if callsign:
            return EntityData(callsign=str(callsign))

        return None

    @property
    def manager(self) -> EntityManager:
        """Get the EntityManager instance.

        Returns:
            EntityManager for direct operations.
        """
        return self._manager


def create_entity_forwarder(session: Any) -> callable:
    """Create a pipeline_forwarder callback for ObservationEngine.

    This factory function creates a callback that can be passed to
    ObservationEngine.__init__ as the pipeline_forwarder parameter.

    Args:
        session: SQLAlchemy database session.

    Returns:
        Callable suitable for pipeline_forwarder parameter.
    """
    bridge = EntityBridge(session)

    async def forwarder(observation: Observation) -> bool:
        """Forward observation to entity system.

        Args:
            observation: The processed observation.

        Returns:
            True if entity was created/linked.
        """
        return await bridge.forward(observation)

    return forwarder


# Synchronous version for compatibility
def create_sync_entity_forwarder(session: Any) -> callable:
    """Create a synchronous pipeline_forwarder callback.

    Some contexts may require synchronous callbacks.

    Args:
        session: SQLAlchemy database session.

    Returns:
        Synchronous callable suitable for pipeline_forwarder.
    """
    bridge = EntityBridge(session)

    def forwarder(observation: Observation) -> bool:
        """Forward observation to entity system (sync).

        Args:
            observation: The processed observation.

        Returns:
            True if entity was created/linked.
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a task, fire and forget
                loop.create_task(bridge.forward(observation))
                return True
            else:
                return loop.run_until_complete(bridge.forward(observation))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(bridge.forward(observation))

    return forwarder


