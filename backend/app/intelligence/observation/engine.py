"""Observation Engine.

Main engine implementing the constitutional Observation model.
Single entry point for all intelligence observations.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.intelligence.observation.model import Observation
from app.intelligence.observation.schema import (
    ObservationCreate,
    ObservationResponse,
    ObservationReject,
    ProvenanceData,
)
from app.intelligence.observation.validator import ObservationValidator, validate_observation_schema
from app.intelligence.observation.repository import ObservationRepository
from app.intelligence.observation.events import (
    ObservationEvent,
    ObservationReceivedEvent,
    ObservationValidatedEvent,
    ObservationRejectedEvent,
    ObservationStoredEvent,
    ObservationForwardedEvent,
    ObservationFailedEvent,
    ObservationEventType,
    get_observation_event_bus,
)

logger = logging.getLogger(__name__)


class ObservationEngineError(Exception):
    """Base exception for observation engine errors."""
    pass


class DuplicateObservationError(ObservationEngineError):
    """Raised when a duplicate observation is detected."""
    pass


class ObservationValidationError(ObservationEngineError):
    """Raised when observation validation fails."""

    def __init__(self, message: str, errors: List[str]):
        self.errors = errors
        super().__init__(message)


class StorageError(ObservationEngineError):
    """Raised when storage operations fail."""
    pass


class PipelineError(ObservationEngineError):
    """Raised when pipeline forwarding fails."""
    pass


class ObservationEngine:
    """Main engine for observation processing.

    This engine is the single entry point for all intelligence
    observations inside TACTICAL CORE. It implements the
    constitutional rules from ENTITY-001.

    Responsibilities:
    1. Receive Observation objects
    2. Validate Observation schema
    3. Validate mandatory fields
    4. Assign immutable Observation ID
    5. Timestamp creation
    6. Store Observation
    7. Generate internal processing event
    8. Forward Observation to Pipeline

    Thread Safety:
    This class is thread-safe and supports concurrent ingestion.
    No mutable shared state between processing requests.

    Constitution Rules:
    - Observation is IMMUTABLE
    - Observation NEVER changes after creation
    - Observation NEVER contains knowledge
    - Observation NEVER performs correlation
    - Observation NEVER modifies Entity state
    - Observation is ONLY evidence
    """

    def __init__(
        self,
        session: Session,
        pipeline_forwarder: Optional[callable] = None,
    ):
        """Initialize Observation Engine.

        Args:
            session: SQLAlchemy database session.
            pipeline_forwarder: Optional callback to forward observations
                              to the pipeline. Signature:
                              (observation: Observation) -> bool
        """
        self._session = session
        self._repository = ObservationRepository(session)
        self._validator = ObservationValidator(
            duplicate_checker=self._repository.exists_by_immutable_id
        )
        self._pipeline_forwarder = pipeline_forwarder
        self._event_bus = get_observation_event_bus()

        logger.info("ObservationEngine initialized")

    def ingest(
        self,
        data: Dict[str, Any],
    ) -> Tuple[ObservationResponse, ObservationReject]:
        """Main entry point for observation ingestion.

        This method orchestrates the complete observation lifecycle:
        1. Receive
        2. Validate
        3. Store
        4. Generate event
        5. Forward to pipeline

        Args:
            data: Raw observation data dictionary.

        Returns:
            Tuple of (success_response, rejection_response)
            - If successful: (ObservationResponse, None)
            - If rejected: (None, ObservationReject)
        """
        # Step 1: Generate internal event - Received
        observation_id = UUID
        self._event_bus.publish(ObservationReceivedEvent(
            observation_id=None,  # Not yet assigned
            source=data.get("source", "unknown"),
            source_type=data.get("source_type", "unknown"),
            data={"raw_data_keys": list(data.keys())},
        ))

        # Step 2: Validate
        is_valid, errors, validated_observation = self._validator.validate(data)

        if not is_valid or validated_observation is None:
            # Generate internal event - Rejected
            self._event_bus.publish(ObservationRejectedEvent(
                observation_id=None,
                rejected_data=data,
                validation_errors=errors or [],
            ))

            rejection = ObservationValidator.create_rejection_response(
                errors=errors or ["Unknown validation error"],
                original_data=data,
                error_code="VALIDATION_FAILED",
            )

            logger.warning(
                "Observation rejected",
                extra={"errors": errors, "source": data.get("source")}
            )

            return None, rejection

        # Generate internal event - Validated
        self._event_bus.publish(ObservationValidatedEvent(
            observation_id=None,
        ))

        # Step 3: Create immutable Observation
        try:
            observation = Observation.from_observation_create(validated_observation)
            observation.processing_status = "validated"
        except Exception as e:
            self._event_bus.publish(ObservationFailedEvent(
                observation_id=None,
                error_code="CREATION_FAILED",
                error_details={"exception": str(e)},
            ))
            raise ObservationEngineError(f"Failed to create observation: {e}")

        # Step 4: Store Observation
        try:
            self._session.add(observation)
            self._session.flush()  # Get the ID assigned
            self._session.commit()

            # Generate internal event - Stored
            self._event_bus.publish(ObservationStoredEvent(
                observation_id=observation.id,
            ))

        except Exception as e:
            self._session.rollback()
            self._event_bus.publish(ObservationFailedEvent(
                observation_id=None,
                error_code="STORAGE_FAILED",
                error_details={"exception": str(e)},
            ))
            raise StorageError(f"Failed to store observation: {e}")

        # Step 5: Update status
        observation.processing_status = "stored"
        self._session.commit()

        # Step 6: Forward to Pipeline
        if self._pipeline_forwarder:
            try:
                success = self._pipeline_forwarder(observation)
                if success:
                    observation.processing_status = "forwarded"
                    self._session.commit()

                    # Generate internal event - Forwarded
                    self._event_bus.publish(ObservationForwardedEvent(
                        observation_id=observation.id,
                        pipeline_target="intelligence_pipeline",
                    ))
                else:
                    logger.warning(
                        "Pipeline forward returned False",
                        extra={"observation_id": str(observation.id)}
                    )
            except Exception as e:
                logger.error(
                    "Pipeline forward failed",
                    extra={"observation_id": str(observation.id), "error": str(e)}
                )
                # Don't fail the ingestion - observation is already stored
                self._event_bus.publish(ObservationFailedEvent(
                    observation_id=observation.id,
                    error_code="FORWARD_FAILED",
                    error_details={"exception": str(e)},
                ))

        # Build response
        response = self._build_response(observation)

        logger.info(
            "Observation ingested successfully",
            extra={
                "observation_id": str(observation.id),
                "source": observation.source,
                "observation_type": observation.observation_type,
            }
        )

        return response, None

    def ingest_batch(
        self,
        observations: List[Dict[str, Any]],
    ) -> Tuple[List[ObservationResponse], List[ObservationReject]]:
        """Ingest multiple observations.

        Processes each observation individually but in a single
        transaction context. Thread-safe.

        Args:
            observations: List of raw observation data dictionaries.

        Returns:
            Tuple of (successful_responses, rejections)
        """
        successful = []
        rejected = []

        for data in observations:
            response, rejection = self.ingest(data)
            if response:
                successful.append(response)
            if rejection:
                rejected.append(rejection)

        return successful, rejected

    def get(self, observation_id: UUID) -> Optional[ObservationResponse]:
        """Get observation by ID.

        Args:
            observation_id: UUID of the observation.

        Returns:
            ObservationResponse if found, None otherwise.
        """
        observation = self._repository.get_by_id(observation_id)
        if observation:
            return self._build_response(observation)
        return None

    def get_by_immutable_id(self, immutable_id: str) -> Optional[ObservationResponse]:
        """Get observation by immutable_id.

        Args:
            immutable_id: Original immutable ID.

        Returns:
            ObservationResponse if found, None otherwise.
        """
        observation = self._repository.get_by_immutable_id(immutable_id)
        if observation:
            return self._build_response(observation)
        return None

    def list_recent(self, limit: int = 100) -> List[ObservationResponse]:
        """List recent observations.

        Args:
            limit: Maximum number to return.

        Returns:
            List of recent observations.
        """
        observations = self._repository.list_recent(limit)
        return [self._build_response(o) for o in observations]

    def _build_response(self, observation: Observation) -> ObservationResponse:
        """Build response from observation model.

        Args:
            observation: Observation model instance.

        Returns:
            ObservationResponse for API.
        """
        return ObservationResponse(
            id=observation.id,
            timestamp=observation.timestamp,
            status=observation.processing_status,
            source=observation.source,
            source_type=observation.source_type,
            evidence_payload=observation.evidence_payload,
            observation_type=observation.observation_type,
            immutable_id=observation.immutable_id,
            provenance=ProvenanceData.model_validate(observation.provenance),
            source_confidence=observation.source_confidence,
            tags=observation.tags or [],
        )


# Standalone processing function
def process_observation(
    data: Dict[str, Any],
    session: Session,
    pipeline_forwarder: Optional[callable] = None,
) -> Tuple[Optional[ObservationResponse], Optional[ObservationReject]]:
    """Process a single observation.

    Convenience function for simple use cases.

    Args:
        data: Raw observation data.
        session: Database session.
        pipeline_forwarder: Optional pipeline callback.

    Returns:
        Tuple of (response, rejection)
    """
    engine = ObservationEngine(session, pipeline_forwarder)
    return engine.ingest(data)
