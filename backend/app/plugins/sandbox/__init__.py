
"""
Plugin Sandbox & Isolation.

Execution isolation layer for plugin system.

Modules:
  policy    — SandboxPolicy (execution limits)
  runtime   — PluginExecutionContext (runtime context)
  sandbox   — PluginSandbox (execution isolation)
  executor  — PluginExecutor (start/stop/restart/heartbeat)

Architecture:
  PluginManager (orchestration)
      → PluginExecutor (execution lifecycle)
          → PluginSandbox (isolation)
              → SandboxPolicy (limits)
              → PluginExecutionContext (runtime state)
"""

from app.plugins.sandbox.policy import SandboxPolicy
from app.plugins.sandbox.runtime import PluginExecutionContext
from app.plugins.sandbox.sandbox import PluginSandbox
from app.plugins.sandbox.executor import PluginExecutor

__all__ = [
    "SandboxPolicy",
    "PluginExecutionContext",
    "PluginSandbox",
    "PluginExecutor",
]
