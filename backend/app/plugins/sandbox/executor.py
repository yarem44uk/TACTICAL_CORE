
"""Plugin Executor — execution lifecycle management."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from app.plugins.sandbox.policy import SandboxPolicy
from app.plugins.sandbox.runtime import PluginExecutionContext
from app.plugins.sandbox.sandbox import PluginSandbox

logger = logging.getLogger(__name__)


class PluginExecutor:
    """
    Manages plugin execution lifecycle.

    Responsibilities:
      - start plugin execution
      - stop plugin execution
      - restart plugin execution
      - monitor heartbeat

    Delegates isolation to PluginSandbox.
    Does NOT handle discovery, loading, registry, or orchestration.
    """

    def __init__(
        self,
        plugin_id: str,
        policy: SandboxPolicy | None = None,
    ) -> None:
        self.plugin_id = plugin_id
        self.policy = policy or SandboxPolicy()
        self._sandbox = PluginSandbox(plugin_id, self.policy)
        self._context: PluginExecutionContext | None = None
        self._lock = threading.RLock()
        self._heartbeat_thread: threading.Thread | None = None
        self._running = False

    @property
    def sandbox(self) -> PluginSandbox:
        return self._sandbox

    @property
    def context(self) -> PluginExecutionContext | None:
        return self._context

    def start(self, target: Callable[[], None]) -> bool:
        """
        Start plugin execution in sandbox.

        Args:
            target: The plugin run loop callable

        Returns:
            True if started successfully, False otherwise
        """
        with self._lock:
            if self._running:
                logger.warning(f"Plugin {self.plugin_id} already running")
                return False

            self._context = PluginExecutionContext(plugin_id=self.plugin_id)
            self._running = True

            try:
                self._sandbox.execute(target, self._context)
                self._start_heartbeat()
                logger.info(f"Plugin {self.plugin_id} started (execution: {self._context.execution_id})")
                return True
            except Exception as exc:
                self._running = False
                logger.error(f"Failed to start plugin {self.plugin_id}: {exc}")
                return False

    def stop(self) -> bool:
        """
        Stop plugin execution gracefully.

        Returns:
            True if stopped successfully, False otherwise
        """
        with self._lock:
            if not self._running:
                return False

            self._running = False
            self._stop_heartbeat()
            self._sandbox.stop()
            logger.info(f"Plugin {self.plugin_id} stopped")
            return True

    def restart(self, target: Callable[[], None]) -> bool:
        """
        Restart plugin execution.

        Args:
            target: The plugin run loop callable

        Returns:
            True if restarted successfully, False otherwise
        """
        self.stop()
        time.sleep(0.1)  # Brief pause for cleanup
        return self.start(target)

    def is_running(self) -> bool:
        """Check if plugin is currently running."""
        return self._running and self._sandbox.is_running()

    def check_heartbeat(self) -> bool:
        """
        Check if plugin is still responsive.

        Returns:
            True if alive, False if unresponsive
        """
        if not self._running:
            return False
        return self._sandbox.is_running()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_heartbeat(self) -> None:
        """Start heartbeat monitoring thread."""
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"heartbeat-{self.plugin_id}",
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        """Stop heartbeat monitoring."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)

    def _heartbeat_loop(self) -> None:
        """Periodic heartbeat check."""
        while self._running:
            time.sleep(self.policy.heartbeat_interval)
            if self._running and not self.check_heartbeat():
                logger.warning(f"Heartbeat timeout for plugin {self.plugin_id}")
                self._running = False
                if self._context:
                    self._context.mark_cancelled()
                break
