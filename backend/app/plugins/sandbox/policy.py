
"""Plugin Sandbox Policy — execution limits and security rules."""

from dataclasses import dataclass, field


@dataclass
class SandboxPolicy:
    """
    Configurable execution limits for a plugin sandbox.

    Controls timeouts, allowed imports, filesystem access, and network policy.
    """

    # --- Timeouts (seconds) ---
    startup_timeout: float = 10.0
    shutdown_timeout: float = 5.0
    heartbeat_interval: float = 30.0
    heartbeat_timeout: float = 60.0
    execution_timeout: float = 120.0

    # --- Import restrictions ---
    forbidden_imports: list[str] = field(default_factory=lambda: [
        "app.database",
        "app.pipeline",
        "app.entity",
        "app.event_engine",
        "app.repositories",
        "sqlalchemy",
    ])

    # --- Filesystem ---
    allow_filesystem_write: bool = False
    allowed_filesystem_paths: list[str] = field(default_factory=list)

    # --- Network ---
    allow_network: bool = False
    allowed_hosts: list[str] = field(default_factory=list)

    # --- Execution ---
    max_threads: int = 4
    max_memory_mb: int = 256
