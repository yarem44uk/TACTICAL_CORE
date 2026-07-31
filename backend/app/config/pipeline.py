"""
Pipeline Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Dict, List


class PipelineStageConfig:
    """Configuration for a single pipeline stage."""

    def __init__(
        self,
        name: str,
        enabled: bool = True,
        required: bool = False,
        order: int = 0,
        options: Dict = None,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self.required = required
        self.order = order
        self.options = options or {}


class PipelineConfig:
    """Pipeline processing configuration."""

    def __init__(
        self,
        name: str = "event-processing",
        max_history_size: int = 10000,
        enable_parallel_dispatch: bool = True,
        max_dispatch_workers: int = 10,
        stages: List[PipelineStageConfig] = None,
    ) -> None:
        self.name = name
        self.max_history_size = max_history_size
        self.enable_parallel_dispatch = enable_parallel_dispatch
        self.max_dispatch_workers = max_dispatch_workers
        self.stages = stages or []

    def get_enabled_stages(self) -> List[PipelineStageConfig]:
        """Get only enabled stages sorted by order."""
        return sorted(
            [s for s in self.stages if s.enabled],
            key=lambda s: s.order
        )

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "max_history_size": self.max_history_size,
            "enable_parallel_dispatch": self.enable_parallel_dispatch,
            "max_dispatch_workers": self.max_dispatch_workers,
            "stages": [
                {"name": s.name, "enabled": s.enabled, "order": s.order}
                for s in self.stages
            ],
        }
