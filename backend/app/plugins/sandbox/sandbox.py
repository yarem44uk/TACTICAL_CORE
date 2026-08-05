
"""Plugin Sandbox — execution isolation layer."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
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
        # Capture the set of loaded modules BEFORE plugin starts executing.
        # Used by _check_policy to detect newly imported forbidden modules.
        self._modules_before = set(sys.modules.keys())

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
        """Enforce SandboxPolicy runtime constraints.

        Returns:
            True if allowed, False if violation detected.
        """
        # --- Forbidden imports enforcement ---
        # Only check modules that are newly loaded during plugin execution.
        # SecurityValidator already checks source code at load time (AST).
        # Here we catch runtime imports that bypass the validator.
        new_modules = set(sys.modules.keys()) - self._modules_before
        for mod_name in new_modules:
            for forbidden in self.policy.forbidden_imports:
                if mod_name == forbidden or mod_name.startswith(forbidden + "."):
                    logger.error(
                        f"Policy violation for {context.plugin_id}: "
                        f"forbidden import '{mod_name}' detected (rule: '{forbidden}')"
                    )
                    return False

        # --- Execution timeout ---
        if self._context and self._context.started_at:
            elapsed = (self._context.last_heartbeat or self._context.started_at) - self._context.started_at
            if elapsed.total_seconds() > self.policy.execution_timeout:
                logger.error(
                    f"Policy violation for {context.plugin_id}: "
                    f"execution exceeded {self.policy.execution_timeout}s timeout"
                )
                return False

        return True

    def _run_with_isolation(
        self,
        target: Callable[[], None],
        context: PluginExecutionContext,
    ) -> None:
        """Execute target with exception containment, policy enforcement, and runtime watchdog."""
        watchdog_thread: threading.Thread | None = None
        start_time = time.monotonic()

        def _target_wrapper() -> None:
            """Run target with heartbeat tracking."""
            try:
                target()
            except Exception as exc:
                logger.error(
                    f"Sandbox target error for {context.plugin_id}: {exc}",
                    exc_info=True,
                )
                if self._context:
                    self._context.mark_cancelled()
                    self._context.stopped_at = datetime.now(timezone.utc)
                raise

        try:
            # Pre-execution policy check
            if not self._check_policy(context):
                raise RuntimeError(f"Policy violation for plugin {context.plugin_id}")

            # B2: Run target in a sub-thread so the sandbox thread can watchdog it.
            watchdog_thread = threading.Thread(
                target=_target_wrapper,
                daemon=True,
                name=f"sandbox-target-{context.plugin_id}-{context.execution_id}",
            )
            watchdog_thread.start()

            # Runtime watchdog loop — monitors policy, timeout, stop, cancellation.
            while watchdog_thread.is_alive():
                # Check execution timeout
                elapsed = time.monotonic() - start_time
                if elapsed > self.policy.execution_timeout:
                    logger.error(
                        f"Timeout violation for {context.plugin_id}: "
                        f"exceeded {self.policy.execution_timeout}s"
                    )
                    self._stop_event.set()
                    context.mark_cancelled()
                    watchdog_thread.join(timeout=2.0)
                    raise TimeoutError(
                        f"Plugin {context.plugin_id} exceeded execution timeout "
                        f"({self.policy.execution_timeout}s)"
                    )

                # Check stop signal
                if self._stop_event.is_set():
                    logger.info(f"Stop signal received for {context.plugin_id}")
                    context.mark_cancelled()
                    watchdog_thread.join(timeout=self.policy.shutdown_timeout)
                    return

                # Check cancellation token
                if context.cancelled:
                    logger.info(f"Cancelled execution for {context.plugin_id}")
                    watchdog_thread.join(timeout=self.policy.shutdown_timeout)
                    return

                # Periodic policy re-validation
                if not self._check_policy(context):
                    logger.error(
                        f"Runtime policy violation for {context.plugin_id}"
                    )
                    self._stop_event.set()
                    context.mark_cancelled()
                    watchdog_thread.join(timeout=2.0)
                    raise RuntimeError(
                        f"Runtime policy violation for plugin {context.plugin_id}"
                    )

                # Update heartbeat timestamp for timeout tracking
                context.last_heartbeat = datetime.now(timezone.utc)

                # Watchdog interval — 200ms sleep to avoid busy loop
                self._stop_event.wait(timeout=0.2)

            # Target completed normally — final policy check
            if not self._check_policy(context):
                logger.error(f"Post-execution policy violation for {context.plugin_id}")
                context.mark_cancelled()
                raise RuntimeError(
                    f"Post-execution policy violation for plugin {context.plugin_id}"
                )

        except (TimeoutError, RuntimeError):
            raise
        except Exception as exc:
            logger.error(
                f"Sandbox isolation error for {context.plugin_id}: {exc}",
                exc_info=True,
            )
            if self._context:
                self._context.mark_cancelled()
                self._context.stopped_at = datetime.now(timezone.utc)
            raise
