"""
Signal Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""


class SignalConfig:
    """Signal Messenger configuration."""

    def __init__(
        self,
        enabled: bool = False,
        cli_path: str = "/usr/local/bin/signal-cli",
        username: str = "",
        group_name: str = "Tactical Core",
        poll_interval: int = 5,
    ) -> None:
        self.enabled = enabled
        self.cli_path = cli_path
        self.username = username
        self.group_name = group_name
        self.poll_interval = poll_interval

    @property
    def is_enabled(self) -> bool:
        return self.enabled
