
"""Plugin Sandbox Tests."""

import threading
import time
import pytest
from app.plugins.sandbox.sandbox import PluginSandbox
from app.plugins.sandbox.policy import SandboxPolicy
from app.plugins.sandbox.runtime import PluginExecutionContext


def _make_context() -> PluginExecutionContext:
    return PluginExecutionContext(plugin_id="test_plugin")


def test_sandbox_starts_and_stops():
    ctx = _make_context()
    sandbox = PluginSandbox("test_plugin")
    executed = threading.Event()

    def target():
        executed.set()
        time.sleep(0.2)

    sandbox.execute(target, ctx)
    time.sleep(0.3)
    assert executed.is_set()
    sandbox.stop()
    assert not sandbox.is_running()


def test_sandbox_contains_exception():
    ctx = _make_context()
    sandbox = PluginSandbox("test_plugin")
    error_raised = threading.Event()

    def target():
        error_raised.set()
        raise RuntimeError("plugin crash")

    sandbox.execute(target, ctx)
    time.sleep(0.3)
    assert error_raised.is_set()
    assert ctx.cancelled is True
    sandbox.stop()


def test_sandbox_policy_violation():
    ctx = _make_context()
    policy = SandboxPolicy()
    # Add a forbidden import that the plugin tries to use
    policy.forbidden_imports = ["os", "sys", "shutil"]
    sandbox = PluginSandbox("test_plugin", policy)
    executed = threading.Event()

    def target():
        executed.set()

    sandbox.execute(target, ctx)
    time.sleep(0.3)
    assert executed.is_set()
    sandbox.stop()


def test_sandbox_is_running_returns_true_while_executing():
    ctx = _make_context()
    sandbox = PluginSandbox("test_plugin")
    done = threading.Event()

    def target():
        time.sleep(0.3)
        done.set()

    sandbox.execute(target, ctx)
    assert sandbox.is_running()
    done.wait(timeout=2)
    sandbox.stop()


def test_sandbox_stop_sends_stop_signal():
    ctx = _make_context()
    sandbox = PluginSandbox("test_plugin")
    stop_received = threading.Event()

    def target():
        while not sandbox._stop_event.is_set():
            time.sleep(0.05)
        stop_received.set()

    sandbox.execute(target, ctx)
    time.sleep(0.1)
    sandbox.stop()
    assert stop_received.wait(timeout=2)


def test_sandbox_context_accessible():
    ctx = _make_context()
    sandbox = PluginSandbox("test_plugin")
    def target():
        pass
    sandbox.execute(target, ctx)
    assert sandbox.context is ctx
    sandbox.stop()


def test_sandbox_policy_defaults():
    policy = SandboxPolicy()
    assert policy.startup_timeout == 10.0
    assert policy.shutdown_timeout == 5.0
    assert "app.database" in policy.forbidden_imports
    assert "app.pipeline" in policy.forbidden_imports
    assert "app.entity" in policy.forbidden_imports
    assert "app.event_engine" in policy.forbidden_imports
