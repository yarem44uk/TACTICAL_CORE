
"""Plugin Execution Context — runtime state isolated from PluginContext."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class PluginExecutionContext:
    """
    Runtime context for a single plugin execution session.

    Separated from PluginContext (which is the plugin-facing API).
    Contains execution lifecycle metadata and control handles.
    """

    plugin_id: str
    execution_id: str = field(default_factory=lambda: uuid4().hex[:12])
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stopped_at: datetime | None = None
    cancelled: bool = False
    cancel_token: str = field(default_factory=lambda: uuid4().hex[:8])

    # Execution state
    task: object | None = None  # asyncio.Task or threading.Thread
    thread: object | None = None

    def mark_cancelled(self) -> None:
        self.cancelled = True

    def mark_stopped(self) -> None:
        self.stopped_at = datetime.now(timezone.utc)
        self.cancelled = False

    def is_alive(self) -> bool:
        if self.thread is not None:
            return hasattr(self.thread, "is_alive") and self.thread.is_alive()
        if self.task is not None:
            return hasattr(self.task, "done") and not self.task.done()
        return False
