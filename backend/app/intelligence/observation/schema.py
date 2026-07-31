"""Observation Schema.

Pydantic v2 models for observation validation and serialization.
Derived from ENTITY-001 Constitutional Architecture.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, ConfigDict


class ProvenanceData(BaseModel):
    """Provenance information for an observation.

    Tracks the origin and chain of custody of the observation.
    This ensures complete traceability as required by the Constitution.
    """

    model_config = ConfigDict(frozen=True)

    driver_id: Optional[str] = Field(
        default=None,
        description="ID of the driver that created this observation",
    )

    device_id: Optional[str] = Field(
        default=None,
        description="ID of the device that captured the source data",
    )

    operator_id: Optional[str] = Field(
        default=None,
        description="ID of the operator who initiated/owned this capture",
    )

    original_timestamp: Optional[datetime] = Field(
        default=None,
        description="When the source data was originally captured",
    )

    capture_method: Optional[str] = Field(
        default=None,
        description="How the data was captured",
    )

    raw_source_reference: Optional[str] = Field(
        default=None,
        description="Reference to original source data location",
    )

    observation_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional observation provenance metadata",
    )


class ObservationCreate(BaseModel):
    """Schema for creating a new observation.

    This is the input schema used by drivers and external systems
    when submitting observations to the Intelligence Core.
    """

    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    source: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Source that created this observation",
    )

    source_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Type of source system",
    )

    evidence_payload: Dict[str, Any] = Field(
        ...,
        description="Raw intelligence data captured",
    )

    observation_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Type classification of the observation",
    )

    immutable_id: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional immutable ID for deduplication",
    )

    provenance: ProvenanceData = Field(
        ...,
        description="Complete provenance information for traceability",
    )

    source_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence supplied by the source",
    )

    tags: List[str] = Field(
        default_factory=list,
        description="Tags for categorization",
    )

    @field_validator('source', 'source_type', 'observation_type')
    @classmethod
    def validate_non_empty_string(cls, v: str) -> str:
        """Validate that string fields are not empty after stripping."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @field_validator('source_confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is within valid range."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v


class ObservationResponse(BaseModel):
    """Schema for observation response.

    This is the output schema returned after successful observation creation.
    It includes the system-assigned fields.
    """

    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
    )

    id: UUID = Field(
        ...,
        description="System-assigned unique identifier",
    )

    timestamp: datetime = Field(
        ...,
        description="System timestamp when observation was created",
    )

    status: str = Field(
        ...,
        description="Current processing status",
    )

    source: str = Field(..., description="Source that created this observation")
    source_type: str = Field(..., description="Type of source system")
    evidence_payload: Dict[str, Any] = Field(..., description="Raw intelligence data")
    observation_type: str = Field(..., description="Type classification")
    immutable_id: Optional[str] = Field(default=None, description="Original immutable ID")
    provenance: ProvenanceData = Field(..., description="Provenance information")
    source_confidence: float = Field(..., ge=0.0, le=1.0, description="Source confidence")
    tags: List[str] = Field(default_factory=list, description="Tags")


class ObservationList(BaseModel):
    """Schema for listing observations with pagination."""

    model_config = ConfigDict(frozen=True)

    items: List[ObservationResponse] = Field(
        ...,
        description="List of observations",
    )

    total: int = Field(
        ...,
        ge=0,
        description="Total number of observations matching filter",
    )

    page: int = Field(
        ...,
        ge=1,
        description="Current page number",
    )

    page_size: int = Field(
        ...,
        ge=1,
        le=1000,
        description="Number of items per page",
    )


class ObservationReject(BaseModel):
    """Schema for observation rejection response."""

    model_config = ConfigDict(frozen=True)

    error_code: str = Field(
        ...,
        description="Machine-readable error code",
    )

    error_message: str = Field(
        ...,
        description="Human-readable error description",
    )

    rejected_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Original data that was rejected",
    )

    validation_errors: List[str] = Field(
        default_factory=list,
        description="List of specific validation failures",
    )
