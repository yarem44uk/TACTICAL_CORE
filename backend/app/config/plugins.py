"""
Plugins Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""


class PluginsConfig:
    """Plugin system configuration."""

    def __init__(
        self,
        enabled: bool = True,
        path: str = "./plugins",
        scan_interval: int = 60,
        auto_enable: bool = False,
        sandbox_enabled: bool = False,
    ) -> None:
        self.enabled = enabled
        self.path = path
        self.scan_interval = scan_interval
        self.auto_enable = auto_enable
        self.sandbox_enabled = sandbox_enabled

    @property
    def is_enabled(self) -> bool:
        return self.enabled
