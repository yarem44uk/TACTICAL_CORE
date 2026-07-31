"""Observation Service.

The Observation Service is the ONLY component responsible for converting
Canonical Events received from the Event Bus into Observation objects.

Canonical Flow:
    External Connector -> Canonical Event -> Event Bus -> Observation Service -> Observation -> Repository

The Observation Service:
1. Subscribes to the Event Bus for Canonical Events
2. Receives Events from all connectors (Signal, Telegram, MQTT, ATAK, etc.)
3. Converts Events to Observations using the EventToObservationMapper
4. Persists Observations to the repository

Usage:
    >>> from app.core.event_bus import EventBus
    >>> from app.observation.service import ObservationService
    >>>
    >>> event_bus = EventBus()
    >>> service = ObservationService(event_bus, session)
    >>> service.start()  # Subscribes to Event Bus
    >>>
    >>> # Events from connectors are now automatically converted to Observations
    >>> service.stop()  # Unsubscribe

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.event_bus import EventBus
from app.core.event_context import EventContext
from app.observation.models import CanonicalEvent, ObservationResult
from app.observation.processor import ObservationProcessor, ObservationProcessorError
from app.observation.mapper import EventToObservationMapper
from app.observation.factory import ObservationFactory


logger = logging.getLogger(__name__)


class ObservationServiceError(Exception):
    """Raised when observation service operations fail."""

    pass


class ObservationService:
    """Service for converting Canonical Events to Observations.

    This service is the single entry point for all event-to-observation
    conversion in the system. It subscribes to the Event Bus and
    processes incoming events.

    Canonical Flow:
        External Connector -> Canonical Event -> Event Bus -> Observation Service -> Observation -> Repository

    Responsibilities:
        - Subscribe to Event Bus for connector event types
        - Receive and validate events
        - Coordinate event processing via ObservationProcessor
        - Handle processing errors gracefully
        - Report processing statistics

    Usage:
        >>> event_bus = EventBus()
        >>> service = ObservationService(event_bus, session)
        >>> service.start()
        >>> # Service now processes events from all connectors
        >>> service.stop()

    Attributes:
        _event_bus: Event Bus instance for subscription.
        _session: Database session for persistence.
        _processor: ObservationProcessor instance.
        _running: Service running state.
        _subscription_id: Event Bus subscription ID.
        _stats: Processing statistics.
    """

    # Event patterns to subscribe to
    DEFAULT_EVENT_PATTERNS = [
        "signal.*",
        "radio.*",
        "atak.*",
        "mqtt.*",
        "telegram.*",
        "rest.*",
        "*",  # Catch all for future connectors
    ]

    def __init__(
        self,
        event_bus: EventBus,
        session: Session,
        event_patterns: Optional[List[str]] = None,
        custom_mapper: Optional[EventToObservationMapper] = None,
        custom_factory: Optional[ObservationFactory] = None,
    ):
        """Initialize the Observation Service.

        Args:
            event_bus: Event Bus instance for subscription.
            session: SQLAlchemy database session.
            event_patterns: Optional custom event patterns to subscribe to.
            custom_mapper: Optional custom EventToObservationMapper.
            custom_factory: Optional custom ObservationFactory.

        Raises:
            ObservationServiceError: If initialization fails.
        """
        self._event_bus = event_bus
        self._session = session
        self._event_patterns = event_patterns or self.DEFAULT_EVENT_PATTERNS

        # Initialize processor with dependencies
        self._processor = ObservationProcessor(
            session=session,
            mapper=custom_mapper,
            factory=custom_factory,
        )

        self._running = False
        self._subscription_id: Optional[str] = None
        self._stats = {
            "events_received": 0,
            "events_processed": 0,
            "events_failed": 0,
            "observations_created": 0,
            "start_time": None,
            "last_event_time": None,
        }

        logger.info("ObservationService initialized")

    @property
    def is_running(self) -> bool:
        """Check if service is running.

        Returns:
            True if service is running.
        """
        return self._running

    @property
    def statistics(self) -> Dict[str, Any]:
        """Get processing statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            **self._stats,
            "uptime_seconds": (
                (datetime.now(timezone.utc) - self._stats["start_time"]).total_seconds()
                if self._stats["start_time"]
                else 0
            ),
        }

    def start(self) -> None:
        """Start the Observation Service.

        Subscribes to the Event Bus for canonical events.
        After this call, incoming events are automatically processed.

        Raises:
            ObservationServiceError: If service fails to start.
        """
        if self._running:
            logger.warning("ObservationService already running")
            return

        try:
            # Subscribe to Event Bus
            self._subscription_id = self._event_bus.subscribe(
                subscriber_id="observation-service",
                handler=self._handle_event,
                patterns=self._event_patterns,
                priority=0,
            )

            self._running = True
            self._stats["start_time"] = datetime.now(timezone.utc)

            logger.info(
                f"ObservationService started, subscribed to patterns: "
                f"{self._event_patterns}"
            )

        except Exception as e:
            logger.error(f"Failed to start ObservationService: {e}")
            raise ObservationServiceError(f"Service start failed: {e}") from e

    def stop(self) -> None:
        """Stop the Observation Service.

        Unsubscribes from the Event Bus and stops processing.
        """
        if not self._running:
            return

        if self._subscription_id:
            # Note: EventBus.subscribe returns subscription_id, but unsubscribe takes subscriber_id
            self._event_bus.unsubscribe("observation-service")

        self._running = False
        logger.info("ObservationService stopped")

    def _handle_event(
        self,
        event: Any,
        context: EventContext,
    ) -> None:
        """Handle incoming event from Event Bus.

        This method is called by the Event Bus when events are published.
        It processes the event and creates an Observation.

        Args:
            event: The event payload (dict or CanonicalEvent).
            context: The event context.
        """
        self._stats["events_received"] += 1
        self._stats["last_event_time"] = datetime.now(timezone.utc)

        try:
            # Convert event to dict if needed
            event_dict = self._event_to_dict(event)

            # Process the event
            result = self._processor.process_event(event_dict)

            if result.success:
                self._stats["events_processed"] += 1
                self._stats["observations_created"] += 1
                logger.debug(
                    f"Created Observation {result.observation_id} "
                    f"from event {result.event_id}"
                )
            else:
                self._stats["events_failed"] += 1
                logger.warning(
                    f"Failed to process event {result.event_id}: "
                    f"{result.error_message}"
                )

        except Exception as e:
            self._stats["events_failed"] += 1
            logger.error(f"Event handling error: {e}")

    def _event_to_dict(self, event: Any) -> Dict[str, Any]:
        """Convert event to dictionary.

        Args:
            event: Event from Event Bus.

        Returns:
            Event as dictionary.
        """
        if isinstance(event, dict):
            return event
        if hasattr(event, "to_dict"):
            return event.to_dict()
        return {"data": event, "event_type": "unknown", "event_id": "unknown"}

    def process_event_manually(
        self,
        event_dict: Dict[str, Any],
    ) -> ObservationResult:
        """Manually process an event without Event Bus subscription.

        This method allows direct event processing for testing
        or when events come from sources other than the Event Bus.

        Args:
            event_dict: Event dictionary to process.

        Returns:
            ObservationResult with processing outcome.
        """
        return self._processor.process_event(event_dict)

    def process_event_sync(
        self,
        event_dict: Dict[str, Any],
    ) -> Optional[UUID]:
        """Synchronously process an event and return observation ID.

        Convenience method for processing events synchronously.

        Args:
            event_dict: Event dictionary to process.

        Returns:
            UUID of created observation, or None if processing failed.
        """
        result = self.process_event_manually(event_dict)
        return result.observation_id if result.success else None

    def health_check(self) -> Dict[str, Any]:
        """Get service health status.

        Returns:
            Health status dictionary.
        """
        return {
            "service": "observation",
            "running": self._running,
            "subscribed": self._subscription_id is not None,
            "patterns": self._event_patterns,
            "statistics": self.statistics,
            "status": "healthy" if self._running else "stopped",
        }

    def get_processor(self) -> ObservationProcessor:
        """Get the underlying processor.

        Returns:
            ObservationProcessor instance.
        """
        return self._processor

    def get_supported_event_types(self) -> List[str]:
        """Get list of supported event types.

        Returns:
            List of supported event type patterns.
        """
        return self._processor.get_mapper().get_supported_event_types()


def get_observation_service(
    event_bus: EventBus,
    session: Session,
) -> ObservationService:
    """Factory function to create ObservationService instance.

    Args:
        event_bus: Event Bus instance.
        session: Database session.

    Returns:
        Configured ObservationService instance.
    """
    return ObservationService(event_bus=event_bus, session=session)
