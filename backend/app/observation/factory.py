"""Observation Factory.

Factory for creating Observation model instances from ObservationCreate schemas.
Handles Observation creation and initialization.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from app.intelligence.observation.model import Observation
from app.intelligence.observation.schema import ObservationCreate


logger = logging.getLogger(__name__)


class ObservationFactoryError(Exception):
    """Raised when observation creation fails."""

    pass


class ObservationFactory:
    """Factory for creating Observation model instances.

    This factory is responsible for:
    1. Creating Observation model instances from validated ObservationCreate schemas
    2. Assigning UUIDs
    3. Setting initial processing status
    4. Providing default values

    Usage:
        >>> factory = ObservationFactory()
        >>> observation = factory.create_observation(observation_create)
    """

    def __init__(self):
        """Initialize the factory."""
        self._default_status = "received"

    def create_observation(
        self,
        observation_create: ObservationCreate,
        observation_id: Optional[UUID] = None,
    ) -> Observation:
        """Create an Observation model instance.

        Args:
            observation_create: Validated ObservationCreate schema.
            observation_id: Optional custom UUID (default: generated).

        Returns:
            Observation model instance (not persisted).

        Raises:
            ObservationFactoryError: If creation fails.
        """
        try:
            observation = Observation.from_observation_create(
                observation_create=observation_create,
                observation_id=observation_id or uuid4(),
            )

            # Ensure initial status
            observation.processing_status = self._default_status

            logger.debug(
                f"Created Observation {observation.id} "
                f"of type {observation.observation_type}"
            )

            return observation

        except Exception as e:
            logger.error(f"Failed to create Observation: {e}")
            raise ObservationFactoryError(f"Observation creation failed: {e}") from e

    def create_observation_from_dict(
        self,
        observation_dict: Dict[str, Any],
        observation_id: Optional[UUID] = None,
    ) -> Observation:
        """Create an Observation from a dictionary.

        Args:
            observation_dict: Dictionary with observation data.
            observation_id: Optional custom UUID.

        Returns:
            Observation model instance.

        Raises:
            ObservationFactoryError: If creation fails.
        """
        try:
            # Create ObservationCreate from dict
            observation_create = ObservationCreate.model_validate(observation_dict)

            return self.create_observation(
                observation_create=observation_create,
                observation_id=observation_id,
            )

        except Exception as e:
            logger.error(f"Failed to create Observation from dict: {e}")
            raise ObservationFactoryError(f"Observation creation failed: {e}") from e

    def set_processing_status(
        self,
        observation: Observation,
        status: str,
    ) -> Observation:
        """Set the processing status of an observation.

        Args:
            observation: The observation to update.
            status: New status value.

        Returns:
            The updated observation.
        """
        observation.processing_status = status
        return observation

    def get_default_status(self) -> str:
        """Get the default processing status.

        Returns:
            Default status string.
        """
        return self._default_status
