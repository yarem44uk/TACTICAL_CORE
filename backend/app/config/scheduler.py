"""
Scheduler Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""


class SchedulerConfig:
    """Background scheduler configuration."""

    def __init__(
        self,
        enabled: bool = True,
        timezone: str = "UTC",
        max_workers: int = 4,
        misfire_grace_time: int = 300,
    ) -> None:
        self.enabled = enabled
        self.timezone = timezone
        self.max_workers = max_workers
        self.misfire_grace_time = misfire_grace_time

    @property
    def is_enabled(self) -> bool:
        return self.enabled
