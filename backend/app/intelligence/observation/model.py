"""Observation Model.

SQLAlchemy ORM model for observations in Intelligence Core.
Derived from ENTITY-001 Constitutional Architecture.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, String, Text, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class Observation(BaseModel):
    """ORM model for immutable observations.

    Represents the atomic unit of intelligence capture as defined
    by ENTITY-001. Once created, an observation is immutable and
    never modified.

    This model preserves:
    - immutable identifier (id)
    - timestamp
    - source
    - source type
    - evidence payload
    - provenance
    - source confidence
    - processing status

    Attributes:
        id: System-assigned UUID (immutable).
        timestamp: When observation was created in system (immutable).
        source: Source that created this observation.
        source_type: Type of source system.
        observation_type: Classification of observation.
        evidence_payload: The raw intelligence captured (immutable).
        provenance: JSON with complete provenance chain.
        source_confidence: Confidence supplied by source (0.0-1.0).
        processing_status: Current status in lifecycle.
        immutable_id: Optional original immutable ID for deduplication.
        tags: JSON list of tags.
        observation_metadata: Additional metadata.

    Constitution Rules:
    - Observation content never changes
    - Observation provenance never changes
    - Observation timestamp never changes
    - Observation links to Entities never break
    - If created in error, correction is a new Observation
    """

    __tablename__ = "observations"

    __table_args__ = (
        # Index for source-based queries
        Index("ix_observations_source", "source"),
        # Index for observation type filtering
        Index("ix_observations_observation_type", "observation_type"),
        # Index for status queries
        Index("ix_observations_processing_status", "processing_status"),
        # Index for timestamp-based queries
        Index("ix_observations_timestamp", "timestamp"),
        # Unique constraint on immutable_id to prevent duplicates
        UniqueConstraint("immutable_id", name="uq_observations_immutable_id"),
    )

    # Core identification (immutable)
    timestamp: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    """System timestamp when observation was created (immutable)."""

    # Source identification
    source: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    """Source that created this observation."""

    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    """Type of source system (driver, plugin, api, operator, ai, system)."""

    observation_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    """Type classification (radio, signal, atak, rest_api, operator, speech, camera, sensor, other)."""

    # Evidence (immutable after creation)
    evidence_payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    """Raw intelligence data captured (immutable)."""

    # Provenance (immutable)
    provenance: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    """Complete provenance information for traceability."""

    # Confidence
    source_confidence: Mapped[float] = mapped_column(
        nullable=False,
        default=0.5,
    )
    """Source-supplied confidence value between 0.0 and 1.0."""

    # Status tracking
    processing_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="received",
    )
    """Current status: received, validated, rejected, stored, forwarded, processing, failed."""

    # Deduplication
    immutable_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )
    """Optional original immutable ID for deduplication."""

    # Organization
    tags: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    """Tags for categorization."""

    # Additional metadata
    observation_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    """Additional observation metadata."""

    def __repr__(self) -> str:
        """String representation of Observation."""
        return (
            f"Observation(id={self.id}, type={self.observation_type}, "
            f"source={self.source}, status={self.processing_status})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert observation to dictionary.

        Returns:
            Dictionary representation of the observation.
        """
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source": self.source,
            "source_type": self.source_type,
            "observation_type": self.observation_type,
            "evidence_payload": self.evidence_payload,
            "provenance": self.provenance,
            "source_confidence": self.source_confidence,
            "processing_status": self.processing_status,
            "immutable_id": self.immutable_id,
            "tags": self.tags,
            "observation_metadata": self.observation_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_deleted": self.is_deleted,
            "version": self.version,
        }

    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to API response format.

        Returns:
            Dictionary suitable for API response.
        """
        return self.to_dict()

    @classmethod
    def from_observation_create(
        cls,
        observation_create,
        observation_id: Optional[uuid.UUID] = None
    ) -> "Observation":
        """Create an Observation model from ObservationCreate schema.

        Args:
            observation_create: Validated ObservationCreate instance.
            observation_id: Optional custom UUID (default: generated).

        Returns:
            New Observation instance (not persisted).
        """
        return cls(
            id=observation_id or uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            source=observation_create.source,
            source_type=observation_create.source_type,
            observation_type=observation_create.observation_type,
            evidence_payload=observation_create.evidence_payload,
            provenance=observation_create.provenance.model_dump(mode="json"),
            source_confidence=observation_create.source_confidence,
            immutable_id=observation_create.immutable_id,
            tags=observation_create.tags,
            processing_status="received",
        )
