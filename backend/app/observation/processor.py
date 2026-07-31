"""Observation Processor.

Processes Canonical Events and creates Observations.
Handles validation, transformation, and persistence coordination.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.intelligence.observation.schema import ObservationCreate
from app.intelligence.observation.model import Observation
from app.intelligence.observation.repository import ObservationRepository
from app.observation.models import (
    CanonicalEvent,
    ObservationResult,
    EVENT_TYPE_MAPPINGS,
)
from app.observation.mapper import EventToObservationMapper, EventMappingError
from app.observation.factory import ObservationFactory, ObservationFactoryError


logger = logging.getLogger(__name__)


class ObservationProcessorError(Exception):
    """Raised when event processing fails."""

    pass


class ObservationProcessor:
    """Processes Canonical Events into Observations.

    The processor coordinates:
    1. Event parsing and validation
    2. Event to Observation mapping
    3. Observation creation via factory
    4. Repository persistence

    This class is the core processing engine for the Observation Service.

    Usage:
        >>> processor = ObservationProcessor(session)
        >>> result = processor.process_event(canonical_event_dict)
        >>> if result.success:
        ...     print(f"Created observation: {result.observation_id}")
    """

    def __init__(
        self,
        session: Session,
        mapper: Optional[EventToObservationMapper] = None,
        factory: Optional[ObservationFactory] = None,
    ):
        """Initialize the processor.

        Args:
            session: SQLAlchemy database session.
            mapper: Optional custom mapper (default: EventToObservationMapper).
            factory: Optional custom factory (default: ObservationFactory).
        """
        self._session = session
        self._repository = ObservationRepository(session)
        self._mapper = mapper or EventToObservationMapper()
        self._factory = factory or ObservationFactory()

    def process_event(
        self,
        event_dict: Dict[str, Any],
    ) -> ObservationResult:
        """Process a canonical event and create an Observation.

        Args:
            event_dict: Event dictionary from Event Bus.

        Returns:
            ObservationResult with processing outcome.
        """
        start_time = time.time()

        try:
            # Parse event
            event = self._parse_event(event_dict)

            # Validate event
            if not self._validate_event(event):
                return ObservationResult(
                    success=False,
                    error_message="Event validation failed",
                    event_id=getattr(event, "event_id", None),
                    event_type=getattr(event, "event_type", None),
                    processing_time_ms=(time.time() - start_time) * 1000,
                )

            # Map event to observation
            observation_create = self._map_event_to_observation(event)

            # Create observation
            observation = self._create_observation(observation_create)

            # Persist observation
            persisted_observation = self._persist_observation(observation)

            processing_time = (time.time() - start_time) * 1000

            logger.info(
                f"Processed event {event.event_id} -> "
                f"Observation {persisted_observation.id} "
                f"in {processing_time:.2f}ms"
            )

            return ObservationResult(
                success=True,
                observation_id=persisted_observation.id,
                event_id=event.event_id,
                event_type=event.event_type,
                processing_time_ms=processing_time,
            )

        except EventMappingError as e:
            logger.warning(f"Event mapping failed: {e}")
            return ObservationResult(
                success=False,
                error_message=str(e),
                event_id=event_dict.get("event_id"),
                event_type=event_dict.get("event_type"),
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        except ObservationFactoryError as e:
            logger.error(f"Observation creation failed: {e}")
            return ObservationResult(
                success=False,
                error_message=str(e),
                event_id=event_dict.get("event_id"),
                event_type=event_dict.get("event_type"),
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Event processing failed: {e}")
            return ObservationResult(
                success=False,
                error_message=f"Processing error: {e}",
                event_id=event_dict.get("event_id"),
                event_type=event_dict.get("event_type"),
                processing_time_ms=(time.time() - start_time) * 1000,
            )

    def process_batch(
        self,
        event_dicts: List[Dict[str, Any]],
    ) -> List[ObservationResult]:
        """Process multiple events.

        Args:
            event_dicts: List of event dictionaries.

        Returns:
            List of ObservationResults.
        """
        results = []
        for event_dict in event_dicts:
            result = self.process_event(event_dict)
            results.append(result)

        logger.info(
            f"Batch processed {len(event_dicts)} events, "
            f"{sum(1 for r in results if r.success)} successful"
        )

        return results

    def _parse_event(self, event_dict: Dict[str, Any]) -> CanonicalEvent:
        """Parse event dictionary into CanonicalEvent.

        Args:
            event_dict: Raw event dictionary.

        Returns:
            CanonicalEvent instance.

        Raises:
            ObservationProcessorError: If parsing fails.
        """
        try:
            return CanonicalEvent.from_dict(event_dict)
        except Exception as e:
            raise ObservationProcessorError(f"Failed to parse event: {e}") from e

    def _validate_event(self, event: CanonicalEvent) -> bool:
        """Validate the parsed event.

        Args:
            event: CanonicalEvent to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Check required fields
        if not event.event_id:
            logger.warning("Event missing event_id")
            return False

        if not event.event_type:
            logger.warning("Event missing event_type")
            return False

        # Check for data
        if not event.data:
            logger.warning(f"Event {event.event_id} has no data")
            return False

        # Get mapping for validation
        mapping = self._mapper.get_mapping(event.event_type)

        # Check required fields per mapping
        if not mapping.is_valid_event(event.data):
            logger.warning(
                f"Event {event.event_id} missing required fields for "
                f"mapping {event.event_type}"
            )
            return False

        return True

    def _map_event_to_observation(
        self,
        event: CanonicalEvent,
    ) -> ObservationCreate:
        """Map event to ObservationCreate.

        Args:
            event: Validated CanonicalEvent.

        Returns:
            ObservationCreate schema.

        Raises:
            EventMappingError: If mapping fails.
        """
        try:
            return self._mapper.map_event_to_observation(event)
        except Exception as e:
            raise EventMappingError(f"Event mapping failed: {e}") from e

    def _create_observation(
        self,
        observation_create: ObservationCreate,
    ) -> Observation:
        """Create Observation model instance.

        Args:
            observation_create: Validated ObservationCreate.

        Returns:
            Observation model instance.

        Raises:
            ObservationFactoryError: If creation fails.
        """
        try:
            return self._factory.create_observation(observation_create)
        except Exception as e:
            raise ObservationFactoryError(f"Observation creation failed: {e}") from e

    def _persist_observation(
        self,
        observation: Observation,
    ) -> Observation:
        """Persist observation to repository.

        Args:
            observation: Observation to persist.

        Returns:
            Persisted observation with ID.
        """
        # BaseRepository.create() expects **kwargs, not a single entity
        # Convert observation to dict and unpack as keyword arguments
        obs_dict = {
            'id': observation.id,
            'timestamp': observation.timestamp,
            'source': observation.source,
            'source_type': observation.source_type,
            'observation_type': observation.observation_type,
            'evidence_payload': observation.evidence_payload,
            'provenance': observation.provenance,
            'source_confidence': observation.source_confidence,
            'processing_status': observation.processing_status,
            'immutable_id': observation.immutable_id,
            'tags': observation.tags,
            'observation_metadata': observation.observation_metadata,
        }
        self._repository.create(**obs_dict)
        self._session.commit()
        return observation

    def get_repository(self) -> ObservationRepository:
        """Get the observation repository.

        Returns:
            ObservationRepository instance.
        """
        return self._repository

    def get_mapper(self) -> EventToObservationMapper:
        """Get the event mapper.

        Returns:
            EventToObservationMapper instance.
        """
        return self._mapper

    def get_factory(self) -> ObservationFactory:
        """Get the observation factory.

        Returns:
            ObservationFactory instance.
        """
        return self._factory
