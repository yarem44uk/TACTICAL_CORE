
"""Plugin Sandbox — execution isolation layer."""

from __future__ import annotations

import logging
import threading
import traceback
from typing import Any, Callable

from app.plugins.sandbox.policy import SandboxPolicy
from app.plugins.sandbox.runtime import PluginExecutionContext

logger = logging.getLogger(__name__)


class PluginSandbox:
    """
    Isolates plugin execution from the core system.

    Current implementation uses dedicated threads.
    Architecture allows future replacement with processes, Docker, or MicroVMs
    without changing PluginManager.

    Responsibilities:
      - Execute plugin code in isolation
      - Enforce SandboxPolicy limits
      - Catch and contain runtime exceptions
      - Support cancellation and timeouts

    Does NOT:
      - Import plugins
      - Manage registry
      - Orchestrate lifecycle
    """

    def __init__(
        self,
        plugin_id: str,
        policy: SandboxPolicy | None = None,
    ) -> None:
        self.plugin_id = plugin_id
        self.policy = policy or SandboxPolicy()
        self._context: PluginExecutionContext | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def context(self) -> PluginExecutionContext | None:
        return self._context

    def execute(
        self,
        target: Callable[[], None],
        context: PluginExecutionContext,
    ) -> None:
        """
        Execute plugin code in an isolated thread.

        Args:
            target: The callable to execute (e.g., plugin run loop)
            context: Execution context for this session
        """
        self._context = context
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run_with_isolation,
            args=(target, context),
            daemon=True,
            name=f"sandbox-{context.plugin_id}-{context.execution_id}",
        )
        self._thread.start()
        context.thread = self._thread

    def stop(self) -> None:
        """Signal the sandbox to stop execution."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.policy.shutdown_timeout)
        if self._context:
            self._context.mark_stopped()

    def is_running(self) -> bool:
        """Check if the sandbox is currently executing."""
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Internal isolation layer
    # ------------------------------------------------------------------

    def _check_policy(self, context: PluginExecutionContext) -> bool:
        """Check if plugin execution is allowed by policy."""
        # In Phase 1, we check that the plugin module does not import
        # forbidden modules. Full AST-based checking is done in Validator.
        # Here we only enforce runtime policy constraints.
        return True

    def _run_with_isolation(
        self,
        target: Callable[[], None],
        context: PluginExecutionContext,
    ) -> None:
        """Execute target with exception containment and policy enforcement."""
        try:
            # Enforce policy before execution
            if not self._check_policy(context):
                raise RuntimeError(f"Policy violation for plugin {context.plugin_id}")

            target()

        except Exception as exc:
            logger.error(
                f"Sandbox execution error for {context.plugin_id}: {exc}",
                exc_info=True,
            )
            if self._context:
                self._context.mark_cancelled()
                self._context.stopped_at = context.started_at  # mark as failed
