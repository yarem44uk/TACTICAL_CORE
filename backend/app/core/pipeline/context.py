"""
Pipeline Context Module.

Immutable context object that carries event data and execution state through the pipeline.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class PipelineContext:
    """
    Immutable context for pipeline execution.
    
    Contains event data and execution metadata.
    Once created, cannot be modified (frozen=True).
    Use with_metadata() to create modified copies.
    """
    
    event_id: uuid.UUID
    event_data: Dict[str, Any]
    correlation_id: Optional[str] = None
    parent_event_id: Optional[uuid.UUID] = None
    source: str = 'system'
    source_type: str = 'system'
    user: Optional[str] = None
    plugin: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Execution tracking
    cancelled: bool = False
    stage_errors: Dict[str, List[Dict]] = field(default_factory=dict)
    stage_warnings: Dict[str, List[Dict]] = field(default_factory=dict)
    stage_timings: Dict[str, float] = field(default_factory=dict)
    
    def with_metadata(self, **kwargs: Any) -> 'PipelineContext':
        """Create new context with additional metadata."""
        new_metadata = dict(self.metadata)
        new_metadata.update(kwargs)
        return PipelineContext(
            event_id=self.event_id,
            event_data=self.event_data,
            correlation_id=self.correlation_id,
            parent_event_id=self.parent_event_id,
            source=self.source,
            source_type=self.source_type,
            user=self.user,
            plugin=self.plugin,
            metadata=new_metadata,
            created_at=self.created_at,
            cancelled=self.cancelled,
            stage_errors=dict(self.stage_errors),
            stage_warnings=dict(self.stage_warnings),
            stage_timings=dict(self.stage_timings),
        )
    
    def with_event_data(self, data: Dict[str, Any]) -> 'PipelineContext':
        """Create new context with modified event data."""
        return PipelineContext(
            event_id=self.event_id,
            event_data={**self.event_data, **data},
            correlation_id=self.correlation_id,
            parent_event_id=self.parent_event_id,
            source=self.source,
            source_type=self.source_type,
            user=self.user,
            plugin=self.plugin,
            metadata=dict(self.metadata),
            created_at=self.created_at,
            cancelled=self.cancelled,
            stage_errors=dict(self.stage_errors),
            stage_warnings=dict(self.stage_warnings),
            stage_timings=dict(self.stage_timings),
        )
    
    def add_error(self, stage_name: str, error: Dict[str, Any]) -> 'PipelineContext':
        """Add an error from a stage."""
        errors = dict(self.stage_errors)
        errors.setdefault(stage_name, []).append(error)
        return PipelineContext(
            event_id=self.event_id,
            event_data=self.event_data,
            correlation_id=self.correlation_id,
            parent_event_id=self.parent_event_id,
            source=self.source,
            source_type=self.source_type,
            user=self.user,
            plugin=self.plugin,
            metadata=dict(self.metadata),
            created_at=self.created_at,
            cancelled=self.cancelled,
            stage_errors=errors,
            stage_warnings=dict(self.stage_warnings),
            stage_timings=dict(self.stage_timings),
        )
    
    def add_timing(self, stage_name: str, duration_ms: float) -> 'PipelineContext':
        """Record stage execution time."""
        timings = dict(self.stage_timings)
        timings[stage_name] = duration_ms
        return PipelineContext(
            event_id=self.event_id,
            event_data=self.event_data,
            correlation_id=self.correlation_id,
            parent_event_id=self.parent_event_id,
            source=self.source,
            source_type=self.source_type,
            user=self.user,
            plugin=self.plugin,
            metadata=dict(self.metadata),
            created_at=self.created_at,
            cancelled=self.cancelled,
            stage_errors=dict(self.stage_errors),
            stage_warnings=dict(self.stage_warnings),
            stage_timings=timings,
        )
    
    def with_timing(self, stage_name: str, duration_ms: float) -> 'PipelineContext':
        """Record stage execution time (alias for add_timing)."""
        return self.add_timing(stage_name, duration_ms)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": str(self.event_id),
            "event_data": self.event_data,
            "correlation_id": self.correlation_id,
            "source": self.source,
            "source_type": self.source_type,
            "user": self.user,
            "plugin": self.plugin,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "stage_timings": self.stage_timings,
        }