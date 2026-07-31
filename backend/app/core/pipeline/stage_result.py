"""
Pipeline Stage Result.

Defines the result object returned by each processing stage.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID


@dataclass
class StageError:
    """
    Represents an error that occurred during stage execution.
    
    Attributes:
        stage_name: Name of the stage that failed.
        error_code: Machine-readable error code.
        message: Human-readable error message.
        details: Additional error context.
        timestamp: When the error occurred.
        recoverable: Whether the pipeline can continue.
    """
    
    stage_name: str
    error_code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recoverable: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "stage_name": self.stage_name,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "recoverable": self.recoverable,
        }


@dataclass
class StageResult:
    """
    Result of a single pipeline stage execution.
    
    Attributes:
        stage_name: Name of the executed stage.
        success: Whether the stage completed successfully.
        execution_time_ms: Time taken to execute in milliseconds.
        output: The stage output/event data.
        errors: List of errors encountered.
        warnings: List of warnings encountered.
        metadata: Additional stage-specific metadata.
    """
    
    stage_name: str
    success: bool = True
    execution_time_ms: float = 0.0
    output: Optional[Dict[str, Any]] = None
    errors: List[StageError] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_error(
        self,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
    ) -> None:
        """Add an error to the result."""
        error = StageError(
            stage_name=self.stage_name,
            error_code=error_code,
            message=message,
            details=details or {},
            recoverable=recoverable,
        )
        self.errors.append(error)
        self.success = False
    
    def add_warning(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Add a warning to the result."""
        self.warnings.append({
            "message": message,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0
    
    @property
    def is_recoverable(self) -> bool:
        """Check if errors are recoverable."""
        return all(e.recoverable for e in self.errors)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "stage_name": self.stage_name,
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
            "output": self.output,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class PipelineResult:
    """
    Aggregated result of the entire pipeline execution.
    
    Attributes:
        event_id: UUID of the processed event.
        success: Whether all recoverable stages completed.
        total_execution_time_ms: Total pipeline execution time.
        stages: List of individual stage results.
        total_stages: Total number of stages.
        completed_stages: Number of stages that completed.
        failed_stages: Number of stages that failed.
    """
    
    event_id: UUID
    success: bool = True
    total_execution_time_ms: float = 0.0
    stages: List[StageResult] = field(default_factory=list)
    total_stages: int = 0
    completed_stages: int = 0
    failed_stages: int = 0
    
    def add_stage_result(self, result: StageResult) -> None:
        """Add a stage result to the pipeline result."""
        self.stages.append(result)
        self.total_execution_time_ms += result.execution_time_ms
        self.completed_stages += 1
        if not result.success:
            self.failed_stages += 1
            if not result.is_recoverable:
                self.success = False
    
    def get_stage_result(self, stage_name: str) -> Optional[StageResult]:
        """Get result for a specific stage."""
        for result in self.stages:
            if result.stage_name == stage_name:
                return result
        return None
    
    @property
    def all_stages_succeeded(self) -> bool:
        """Check if all stages completed successfully."""
        return self.failed_stages == 0
    
    @property
    def stage_count(self) -> int:
        """Get number of stages executed."""
        return len(self.stages)
    
    @property
    def error_count(self) -> int:
        """Get total number of errors across all stages."""
        return sum(len(s.errors) for s in self.stages)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": str(self.event_id),
            "success": self.success,
            "total_execution_time_ms": self.total_execution_time_ms,
            "stages": [s.to_dict() for s in self.stages],
            "total_stages": self.total_stages,
            "completed_stages": self.completed_stages,
            "failed_stages": self.failed_stages,
        }