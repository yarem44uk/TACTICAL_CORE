"""
Base Pipeline Stage.

Abstract base class for all pipeline processing stages.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.core.pipeline.context import PipelineContext
from app.core.pipeline.stage_result import StageResult


class BaseStage(ABC):
    """
    Abstract base class for pipeline stages.

    All processing stages must inherit from this class.
    Each stage handles a specific aspect of event processing.
    Stages are independent and testable.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        enabled: bool = True,
        required: bool = False,
        order: int = 0,
    ) -> None:
        """
        Initialize the stage.

        Args:
            name: Stage identifier.
            enabled: Whether the stage is active.
            required: Whether pipeline fails if stage fails.
            order: Execution order in pipeline.
        """
        self._name = name or self.__class__.__name__
        self._enabled = enabled
        self._required = required
        self._order = order

    @property
    def name(self) -> str:
        """Get stage name."""
        return self._name

    @property
    def enabled(self) -> bool:
        """Check if stage is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable the stage."""
        self._enabled = value

    @property
    def required(self) -> bool:
        """Check if stage is required."""
        return self._required

    @property
    def order(self) -> int:
        """Get execution order."""
        return self._order

    def can_execute(self, context: PipelineContext) -> bool:
        """
        Check if stage can execute given current context.
        Override for conditional execution.
        """
        return self._enabled and not context.cancelled

    def execute(self, context: PipelineContext) -> StageResult:
        """
        Execute the stage processing.

        This method handles timing and error tracking.
        Subclasses should override _execute() for actual logic.

        Args:
            context: Pipeline context with event data.

        Returns:
            StageResult with execution outcome.
        """
        import time
        from datetime import datetime, timezone

        result = StageResult(stage_name=self._name)
        start_time = time.time()

        try:
            if not self.can_execute(context):
                result.add_warning("Stage " + self._name + " skipped")
                return result

            output = self._execute(context)
            result.output = output if output is not None else context.event_data

        except Exception as e:
            result.add_error(
                error_code="STAGE_EXECUTION_ERROR",
                message=str(e),
                details={"stage": self._name},
                recoverable=not self._required,
            )

        result.execution_time_ms = (time.time() - start_time) * 1000

        return result

    @abstractmethod
    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """
        Actual stage processing logic.
        Override this method in subclasses.

        Args:
            context: Pipeline context with event data.

        Returns:
            Modified event data dict, or None to keep existing.
        """
        pass

    def validate_config(self) -> List[str]:
        """
        Validate stage configuration.
        Return list of validation errors.
        """
        return []

    def get_dependencies(self) -> List[str]:
        """
        Get list of stage names this stage depends on.
        Used for ordering validation.
        """
        return []

    def get_subscriptions(self) -> List[str]:
        """
        Get list of event types this stage subscribes to.
        Return empty list to subscribe to all events.
        """
        return []
