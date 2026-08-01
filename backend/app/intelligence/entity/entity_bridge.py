"""Entity Bridge Module.

Connects EventBus to EntityManager for automatic entity creation
and identity resolution from runtime events.

Architecture:
    Plugin Runtime
        │
        ▼
    EventBus
        │
        ▼
    Entity Bridge
        │
        ▼
    EntityManager
        │
        ▼
    Entity Repository

Author: Tactical Core Engineering Team
Version: 1.0
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.event_bus import EventBus
from app.intelligence.entity import (
    Entity,
    EntityManager,
    EntityType,
)

logger = logging.getLogger(__name__)


class EntityBridge:
    """
    Event-driven bridge between EventBus and EntityManager.

    Subscribes to EventBus for supported event types, extracts identity
    information from events, and delegates to EntityManager.resolve_or_create()
    to ensure no duplicate entities are created.

    Stateless — all persistence is delegated to EntityManager/Repository.
    Uses dependency injection for EventBus and EntityManager instances.

    Attributes:
        event_bus: EventBus instance (injected).
        entity_manager: EntityManager instance (injected).
        event_type_map: Maps event types to EntityType.
        source_field: Field name in event payload containing source.
        external_id_field: Field name in event payload containing external_id.
    """

    # Default event type to EntityType mapping
    DEFAULT_EVENT_TYPE_MAP: Dict[str, EntityType] = {
        "signal.message": EntityType.CONTACT,
        "signal.*": EntityType.CONTACT,
        "radio.transmission": EntityType.CONTACT,
        "radio.*": EntityType.CONTACT,
        "mqtt.message": EntityType.ASSET,
        "mqtt.*": EntityType.ASSET,
        "tak.unit": EntityType.UNIT,
        "tak.*": EntityType.UNIT,
    }

    def __init__(
        self,
        event_bus: EventBus,
        entity_manager: EntityManager,
        event_type_map: Optional[Dict[str, EntityType]] = None,
        source_field: str = "source",
        external_id_field: str = "external_id",
    ):
        """
        Initialize EntityBridge.

        Args:
            event_bus: EventBus instance to subscribe to.
            entity_manager: EntityManager instance for entity resolution.
            event_type_map: Custom event type to EntityType mapping.
                Defaults to DEFAULT_EVENT_TYPE_MAP.
            source_field: Field name in event payload for source.
            external_id_field: Field name in event payload for external_id.
        """
        self._event_bus = event_bus
        self._entity_manager = entity_manager
        self._event_type_map = event_type_map or self.DEFAULT_EVENT_TYPE_MAP
        self._source_field = source_field
        self._external_id_field = external_id_field
        self._subscription_id: Optional[str] = None
        self._handler: Optional[Callable] = None

    @property
    def is_subscribed(self) -> bool:
        """Check if the bridge is currently subscribed to the event bus."""
        return self._subscription_id is not None

    def subscribe(self) -> str:
        """
        Subscribe to EventBus for entity-related events.

        Returns:
            Subscription ID.
        """
        self._handler = self._sync_event_handler

        self._subscription_id = self._event_bus.subscribe(
            subscriber_id="entity-bridge",
            handler=self._handler,
            patterns=["signal.*", "radio.*", "mqtt.*", "tak.*"],
            priority=10,
        )

        logger.info(
            "EntityBridge subscribed to EventBus with subscription_id=%s",
            self._subscription_id,
        )
        return self._subscription_id

    def unsubscribe(self) -> None:
        """Unsubscribe from EventBus."""
        if self._subscription_id:
            self._event_bus.unsubscribe("entity-bridge")
            self._subscription_id = None
            logger.info("EntityBridge unsubscribed from EventBus")

    def _sync_event_handler(
        self,
        event: Dict[str, Any],
        context: Any = None,
    ) -> None:
        """
        Synchronous event handler that processes events.

        EventBus calls handlers synchronously. This method runs the
        async _event_handler to completion within the current event loop.

        Args:
            event: Event payload from EventBus.
            context: EventContext from EventBus.
        """
        import nest_asyncio
        try:
            # Allow nested event loops (pytest-asyncio uses nested loops)
            nest_asyncio.apply()
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self._event_handler(event, context))
        except RuntimeError:
            # No event loop available
            asyncio.run(self._event_handler(event, context))

    async def _event_handler(
        self,
        event: Dict[str, Any],
        context: Any = None,
    ) -> None:
        """
        Async handler that processes events and creates entities.

        Extracts source and external_id from the event payload,
        determines the entity type, and delegates to
        EntityManager.resolve_or_create() to ensure no duplicates.

        Args:
            event: Event payload from EventBus.
            context: EventContext from EventBus.
        """
        source = event.get(self._source_field, "")
        external_id = event.get(self._external_id_field, "")

        if not source or not external_id:
            logger.debug(
                "EntityBridge skipping event: missing source or external_id"
            )
            return

        # Determine entity type from event
        entity_type = self._resolve_entity_type(event)

        # Delegate to EntityManager for identity resolution
        try:
            entity, created = await self._entity_manager.resolve_or_create(
                entity_type=entity_type,
                source=source,
                external_id=external_id,
            )

            if created:
                logger.info(
                    "EntityBridge created new entity id=%s source=%s "
                    "external_id=%s type=%s",
                    entity.id,
                    source,
                    external_id,
                    entity_type.value,
                )
            else:
                logger.debug(
                    "EntityBridge resolved existing entity id=%s "
                    "source=%s external_id=%s",
                    entity.id,
                    source,
                    external_id,
                )
        except Exception as e:
            logger.error(
                "EntityBridge error processing event: %s",
                e,
                exc_info=True,
            )

    def _resolve_entity_type(self, event: Dict[str, Any]) -> EntityType:
        """
        Determine EntityType from event payload.

        Checks:
        1. Explicit 'entity_type' in event payload
        2. Event type in mapping
        3. Fallback to CONTACT

        Args:
            event: Event payload.

        Returns:
            EntityType.
        """
        # 1. Explicit entity_type in payload
        if "entity_type" in event:
            try:
                return EntityType(event["entity_type"])
            except ValueError:
                pass

        # 2. Check event type mapping
        event_type_str = event.get("event_type", "")
        if event_type_str and event_type_str in self._event_type_map:
            return self._event_type_map[event_type_str]

        # 3. Fallback
        return EntityType.CONTACT

    async def forward(
        self,
        source: str,
        external_id: str,
        entity_type: Optional[EntityType] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Entity, bool]:
        """
        Programmatically forward identity information to EntityManager.

        This is the synchronous counterpart to the event-driven path.
        Useful for plugins that want to ensure entity existence without
        publishing to EventBus.

        Args:
            source: Source identifier.
            external_id: External identity string.
            entity_type: EntityType. Defaults to CONTACT.
            metadata: Optional additional metadata.

        Returns:
            Tuple of (Entity, created_flag).
        """
        et = entity_type or EntityType.CONTACT
        return await self._entity_manager.resolve_or_create(
            entity_type=et,
            source=source,
            external_id=external_id,
        )
