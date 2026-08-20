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
from app.observation.canonical_adapter import (
    CanonicalEventAdapterError,
    CanonicalEventToObservationAdapter,
)


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
        event_bus: Optional[EventBus] = None,
        session: Session = None,
        event_patterns: Optional[List[str]] = None,
        custom_mapper: Optional[EventToObservationMapper] = None,
        custom_factory: Optional[ObservationFactory] = None,
        custom_adapter: Optional[CanonicalEventToObservationAdapter] = None,
    ):
        """Initialize the Observation Service.

        Args:
            event_bus: Optional legacy Event Bus instance for the pattern-based
                ``start()`` subscription path.  When ``None``, the service is
                used exclusively through the canonical EventBus integration
                (``subscribe_canonical``, WO-015).
            session: SQLAlchemy database session.
            event_patterns: Optional custom event patterns to subscribe to.
            custom_mapper: Optional custom EventToObservationMapper.
            custom_factory: Optional custom ObservationFactory.
            custom_adapter: Optional custom canonical Event -> Observation
                adapter (WO-015). Defaults to a new
                ``CanonicalEventToObservationAdapter``.

        Raises:
            ObservationServiceError: If initialization fails.
        """
        self._event_bus = event_bus
        self._session = session
        self._event_patterns = event_patterns or self.DEFAULT_EVENT_PATTERNS

        # WO-015 — canonical EventBus subscription state.
        # The canonical EventBus is reached through EventPipeline.set_event_bus()
        # and delivers canonical app.event.event.Event objects to subscribers.
        # We track the canonical subscription separately from the legacy
        # pattern-based subscription so the two paths do not interfere.
        self._canonical_subscription = None
        self._canonical_adapter = custom_adapter or CanonicalEventToObservationAdapter()

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

        if self._event_bus is None:
            raise ObservationServiceError(
                "ObservationService.start() requires a legacy EventBus; "
                "use subscribe_canonical() for canonical EventBus integration."
            )

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

        if self._subscription_id and self._event_bus is not None:
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
                # WO-015 defect repair: same shared-session recovery as the
                # canonical path (duplicate IntegrityError leaves the Session
                # in a rolled-back state).
                self._recover_session()

        except Exception as e:
            self._stats["events_failed"] += 1
            logger.error(f"Event handling error: {e}")
            # WO-015 defect repair: a persistence failure (e.g. UNIQUE
            # immutable_id IntegrityError on a duplicate event) leaves the
            # shared SQLAlchemy Session in a rolled-back state. Recover it so
            # the next independent event can be processed.
            self._recover_session()

    def _recover_session(self) -> None:
        """Restore the shared SQLAlchemy Session to a usable transaction state.

        SQLAlchemy requires an explicit ``rollback()`` after a flush/commit
        exception (e.g. IntegrityError) before the Session can be reused.
        Without it, the next event fails with "This Session's transaction has
        been rolled back due to a previous exception during flush", silently
        dropping all subsequent Observations.

        Called only on the failure path so successful processing is unaffected.
        Idempotent and safe: rolling back a session with no failed transaction
        is a harmless no-op.
        """
        if self._session is None:
            return
        try:
            self._session.rollback()
            logger.debug("Recovered shared observation session after failure")
        except Exception as e:  # noqa: BLE001 - best-effort session recovery
            logger.error(f"Failed to recover observation session: {e}")


    # ------------------------------------------------------------------
    # WO-015 — canonical EventBus integration
    # ------------------------------------------------------------------
    def subscribe_canonical(
        self,
        event_bus: Any,
    ) -> object:
        """Subscribe this service to the canonical EventBus.

        The canonical EventBus (``app.event_bus.event_bus.EventBus``) is reached
        through ``EventPipeline.set_event_bus()`` and delivers canonical
        ``app.event.event.Event`` objects to its subscribers.  We subscribe to
        ``EventType.CUSTOM``, which is the type produced by the production
        EventFactory for source-adapter events.

        Args:
            event_bus: The canonical EventBus instance (duck-typed so this does
                not hard-couple the service to one implementation).

        Returns:
            The canonical subscription handle (for later unsubscribe).

        Raises:
            ObservationServiceError: If subscription fails.
        """
        from app.event.event_types import EventType

        if self._canonical_subscription is not None:
            logger.warning("ObservationService already subscribed to canonical EventBus")
            return self._canonical_subscription

        try:
            subscription = event_bus.subscribe(
                EventType.CUSTOM,
                self._handle_canonical_event,
            )
            self._canonical_subscription = subscription
            self._stats["start_time"] = datetime.now(timezone.utc)
            logger.info(
                "ObservationService subscribed to canonical EventBus "
                "(EventType.CUSTOM)"
            )
            return subscription
        except Exception as e:
            logger.error(f"Failed to subscribe to canonical EventBus: {e}")
            raise ObservationServiceError(
                f"Canonical EventBus subscription failed: {e}"
            ) from e

    def unsubscribe_canonical(self, event_bus: Any = None) -> bool:
        """Unsubscribe this service from the canonical EventBus.

        Args:
            event_bus: Optional canonical EventBus to unsubscribe from.  If
                omitted, the subscription is only cleared locally.

        Returns:
            True if a canonical subscription was present and removed.
        """
        if self._canonical_subscription is None:
            return False
        removed = False
        if event_bus is not None:
            try:
                removed = bool(event_bus.unsubscribe(self._canonical_subscription))
            except Exception as e:  # noqa: BLE001 - best-effort unsubscribe
                logger.warning(f"Failed to unsubscribe canonical EventBus: {e}")
        self._canonical_subscription = None
        logger.info("ObservationService unsubscribed from canonical EventBus")
        return removed or True

    @property
    def canonical_subscription(self) -> object:
        """Return the active canonical EventBus subscription (or None)."""
        return self._canonical_subscription

    def _handle_canonical_event(self, event: Any) -> None:
        """Handle a canonical ``app.event.event.Event`` from the canonical EventBus.

        This is the single-argument callback invoked by the canonical EventBus
        (``app.event_bus.event_bus.EventBus``), which delivers canonical Event
        objects directly (no ``context``).  The event is adapted to the
        Observation representation and processed through the existing
        ObservationProcessor, preserving mapping, immutable_id, duplicate
        protection and failure-isolation semantics.

        Args:
            event: The canonical Event object.
        """
        self._stats["events_received"] += 1
        self._stats["last_event_time"] = datetime.now(timezone.utc)

        try:
            event_dict = self._canonical_adapter.to_observation_dict(event)
        except CanonicalEventAdapterError as e:
            self._stats["events_failed"] += 1
            logger.warning(f"Canonical event adaptation failed: {e}")
            return

        try:
            result = self._processor.process_event(event_dict)
            if result.success:
                self._stats["events_processed"] += 1
                self._stats["observations_created"] += 1
                logger.debug(
                    f"Created Observation {result.observation_id} "
                    f"from canonical event {result.event_id}"
                )
            else:
                self._stats["events_failed"] += 1
                logger.warning(
                    f"Failed to process canonical event {result.event_id}: "
                    f"{result.error_message}"
                )
                # WO-015 defect repair: a persistence failure during
                # processing (e.g. UNIQUE immutable_id IntegrityError on a
                # duplicate event) is swallowed by the processor into a
                # success=False result and leaves the shared Session in a
                # rolled-back state. Recover it so the next independent event
                # can still be persisted.
                self._recover_session()
        except Exception as e:
            self._stats["events_failed"] += 1
            logger.error(f"Canonical event handling error: {e}")
            # Best-effort session recovery after an unexpected exception.
            self._recover_session()

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
