"""Observation Engine.

The Observation Engine is the single entry point for all intelligence
observations inside TACTICAL CORE, as defined by ENTITY-001 Constitutional
Architecture.

This module implements the immutable Observation subsystem:
- Observation: The atomic unit of intelligence capture (immutable)
- ObservationEngine: Main processing engine
- ObservationValidator: Schema and rule validation
- ObservationRepository: Persistence layer
- ObservationEventBus: Internal event coordination

Usage:
    >>> from app.intelligence.observation import ObservationEngine
    >>> engine = ObservationEngine(session)
    >>> response, rejection = engine.ingest(observation_data)
    >>> if response:
    ...     print(f"Observation {response.id} created")

Author: Tactical Core Engineering Team
Version: 1.0
"""

# Core types
from app.intelligence.observation.types import (
    ObservationType,
    SourceType,
    ProcessingStatus,
    ObservationEventType,
    ConfidenceLevel,
)

# Schema definitions
from app.intelligence.observation.schema import (
    ProvenanceData,
    ObservationCreate,
    ObservationResponse,
    ObservationList,
    ObservationReject,
)

# Validator
from app.intelligence.observation.validator import (
    ObservationValidator,
    ObservationValidationError,
    DuplicateObservationError,
    InvalidTimestampError,
    UnsupportedObservationTypeError,
    validate_observation_schema,
)

# Model
from app.intelligence.observation.model import Observation

# Repository
from app.intelligence.observation.repository import ObservationRepository

# Events
from app.intelligence.observation.events import (
    ObservationEvent,
    ObservationReceivedEvent,
    ObservationValidatedEvent,
    ObservationRejectedEvent,
    ObservationStoredEvent,
    ObservationForwardedEvent,
    ObservationFailedEvent,
    ObservationEventBus,
    get_observation_event_bus,
)

# Main engine
from app.intelligence.observation.engine import (
    ObservationEngine,
    ObservationEngineError,
    StorageError,
    PipelineError,
    process_observation,
)


__all__ = [
    # Types
    "ObservationType",
    "SourceType",
    "ProcessingStatus",
    "ObservationEventType",
    "ConfidenceLevel",
    # Schema
    "ProvenanceData",
    "ObservationCreate",
    "ObservationResponse",
    "ObservationList",
    "ObservationReject",
    # Validator
    "ObservationValidator",
    "ObservationValidationError",
    "DuplicateObservationError",
    "InvalidTimestampError",
    "UnsupportedObservationTypeError",
    "validate_observation_schema",
    # Model
    "Observation",
    # Repository
    "ObservationRepository",
    # Events
    "ObservationEvent",
    "ObservationReceivedEvent",
    "ObservationValidatedEvent",
    "ObservationRejectedEvent",
    "ObservationStoredEvent",
    "ObservationForwardedEvent",
    "ObservationFailedEvent",
    "ObservationEventBus",
    "get_observation_event_bus",
    # Engine
    "ObservationEngine",
    "ObservationEngineError",
    "StorageError",
    "PipelineError",
    "process_observation",
]


# WO-007-003: Validation Framework
from app.intelligence.observation.validation_framework import (
    ValidationStatus,
    ValidationCategory,
    ValidationIssue,
    ValidationResult,
    SchemaValidator,
    TimestampValidator,
    SourceValidator,
    IntegrityValidator,
    ConstitutionalValidator,
    ObservationValidationFramework,
    validate_observation,
)
