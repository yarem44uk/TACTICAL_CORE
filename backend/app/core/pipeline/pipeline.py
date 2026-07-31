"""
Event Processing Pipeline.

Orchestrates ordered execution of processing stages.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Type

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext
from app.core.pipeline.stage_result import PipelineResult, StageResult

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Event processing pipeline with ordered stage execution.

    Manages a collection of stages that process events in sequence.
    Each stage operates on the event data and passes it to the next.

    Attributes:
        name: Pipeline identifier.
        stages: Ordered list of processing stages.
        middleware: List of middleware hooks.

    Usage:
        >>> pipeline = Pipeline(name="event-processing")
        >>> pipeline.add(ValidationStage())
        >>> pipeline.add(PersistenceStage())
        >>> 
        >>> result = pipeline.execute(event_data, context)
    """

    def __init__(
        self,
        name: str = "default",
        strict_order: bool = True,
    ) -> None:
        """
        Initialize the pipeline.

        Args:
            name: Pipeline identifier.
            strict_order: Whether to enforce stage order.
        """
        self._name = name
        self._strict_order = strict_order
        self._stages: List[BaseStage] = []
        self._middleware: List[Callable] = []
        self._enabled = True
        self._stage_by_name: Dict[str, BaseStage] = {}

        logger.info("Pipeline initialized: " + name)

    @property
    def name(self) -> str:
        """Get pipeline name."""
        return self._name

    @property
    def stages(self) -> List[BaseStage]:
        """Get list of stages in order."""
        return list(self._stages)

    @property
    def stage_count(self) -> int:
        """Get number of stages."""
        return len(self._stages)

    @property
    def enabled_stages(self) -> List[BaseStage]:
        """Get only enabled stages."""
        return [s for s in self._stages if s.enabled]

    def add(self, stage: BaseStage, position: Optional[int] = None) -> 'Pipeline':
        """
        Add a stage to the pipeline.

        Args:
            stage: Stage to add.
            position: Optional position to insert at.

        Returns:
            Self for chaining.
        """
        if stage.name in self._stage_by_name:
            raise ValueError("Stage with name " + stage.name + " already exists")

        if position is None:
            self._stages.append(stage)
        else:
            self._stages.insert(position, stage)

        self._stages.sort(key=lambda s: s.order)
        self._stage_by_name[stage.name] = stage

        logger.debug("Stage added: " + stage.name + " at position " + str(len(self._stages)))
        return self

    def remove(self, stage_name: str) -> bool:
        """
        Remove a stage by name.

        Args:
            stage_name: Name of stage to remove.

        Returns:
            True if removed, False if not found.
        """
        stage = self._stage_by_name.get(stage_name)
        if stage is None:
            return False

        self._stages.remove(stage)
        del self._stage_by_name[stage_name]

        logger.debug("Stage removed: " + stage_name)
        return True

    def get_stage(self, stage_name: str) -> Optional[BaseStage]:
        """Get a stage by name."""
        return self._stage_by_name.get(stage_name)

    def enable(self, stage_name: str) -> bool:
        """Enable a stage by name."""
        stage = self._stage_by_name.get(stage_name)
        if stage:
            stage.enabled = True
            return True
        return False

    def disable(self, stage_name: str) -> bool:
        """Disable a stage by name."""
        stage = self._stage_by_name.get(stage_name)
        if stage:
            stage.enabled = False
            return True
        return False

    def reorder(self, stage_order: List[str]) -> None:
        """
        Reorder stages by name list.

        Args:
            stage_order: List of stage names in desired order.
        """
        stage_map = {s.name: s for s in self._stages}
        ordered = []

        for name in stage_order:
            if name in stage_map:
                ordered.append(stage_map[name])

        for stage in self._stages:
            if stage.name not in stage_order:
                ordered.append(stage)

        self._stages = ordered

        for i, stage in enumerate(self._stages):
            stage._order = i

    def add_middleware(self, middleware: Callable) -> 'Pipeline':
        """
        Add middleware hook.

        Args:
            middleware: Callable(stage_name, context, stage_result, phase)

        Returns:
            Self for chaining.
        """
        self._middleware.append(middleware)
        return self

    def execute(
        self,
        event_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
        source: str = "system",
        source_type: str = "system",
        user: Optional[str] = None,
        plugin: Optional[str] = None,
    ) -> PipelineResult:
        """
        Execute the pipeline.

        Args:
            event_data: Event data to process.
            correlation_id: Optional correlation ID.
            source: Event source.
            source_type: Type of source.
            user: Optional user ID.
            plugin: Optional plugin ID.

        Returns:
            PipelineResult with execution outcome.
        """
        if not self._enabled:
            logger.warning("Pipeline " + self._name + " is disabled")
            result = PipelineResult(event_id=uuid.uuid4(), success=False, total_stages=0)
            result.add_stage_result(StageResult(stage_name="pipeline", success=False))
            return result

        event_id = event_data.get("id")
        if event_id and isinstance(event_id, str):
            try:
                event_id = uuid.UUID(event_id)
            except ValueError:
                event_id = uuid.uuid4()
        else:
            event_id = uuid.uuid4()

        context = PipelineContext(
            event_id=event_id,
            event_data=dict(event_data),
            correlation_id=correlation_id,
            source=source,
            source_type=source_type,
            user=user,
            plugin=plugin,
        )

        result = PipelineResult(
            event_id=event_id,
            total_stages=len(self._stages),
        )

        start_time = time.time()

        for stage in self._stages:
            if not stage.enabled:
                continue

            stage_start = time.time()

            try:
                self._call_middleware("before", stage.name, context, None)

                stage_result = stage.execute(context)
                context = context.with_event_data(stage_result.output or context.event_data)
                context = context.with_timing(stage.name, stage_result.execution_time_ms)

                result.add_stage_result(stage_result)

                if stage_result.has_errors and not stage_result.is_recoverable:
                    context = context.with_metadata(cancelled=True)

                self._call_middleware("after", stage.name, context, stage_result)

            except Exception as e:
                logger.error("Stage " + stage.name + " failed: " + str(e))
                error_result = StageResult(stage_name=stage.name, success=False)
                error_result.add_error("STAGE_CRASH", str(e), recoverable=not stage.required)
                result.add_stage_result(error_result)

                self._call_middleware("exception", stage.name, context, error_result)

                if stage.required:
                    context = context.with_metadata(cancelled=True)

        result.total_execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "Pipeline " + self._name + " executed",
            extra={
                "event_id": str(event_id),
                "stages": result.completed_stages,
                "failed": result.failed_stages,
                "duration_ms": result.total_execution_time_ms,
            }
        )

        return result

    def _call_middleware(
        self,
        phase: str,
        stage_name: str,
        context: PipelineContext,
        result: Optional[StageResult],
    ) -> None:
        """Call middleware hooks."""
        for mw in self._middleware:
            try:
                mw(phase, stage_name, context, result)
            except Exception as e:
                logger.error("Middleware failed: " + str(e))

    def validate(self) -> List[str]:
        """
        Validate pipeline configuration.

        Returns:
            List of validation errors.
        """
        errors = []

        for stage in self._stages:
            errors.extend(stage.validate_config())

        for stage in self._stages:
            deps = stage.get_dependencies()
            for dep in deps:
                if dep not in self._stage_by_name:
                    errors.append("Stage " + stage.name + " depends on missing stage: " + dep)

        return errors

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self._name,
            "enabled": self._enabled,
            "stages": [
                {
                    "name": s.name,
                    "enabled": s.enabled,
                    "required": s.required,
                    "order": s.order,
                }
                for s in self._stages
            ],
            "stage_count": len(self._stages),
            "middleware_count": len(self._middleware),
        }
