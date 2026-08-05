
"""Plugin Executor Tests."""

import threading
import time
import pytest
from app.plugins.sandbox.executor import PluginExecutor
from app.plugins.sandbox.policy import SandboxPolicy


def test_executor_start_and_stop():
    executor = PluginExecutor("test_plugin")
    started = threading.Event()
    stopped = threading.Event()

    def target():
        started.set()
        time.sleep(0.3)
        stopped.set()

    assert executor.start(target)
    time.sleep(0.1)
    assert executor.is_running()
    assert started.is_set()
    executor.stop()
    assert not executor.is_running()


def test_executor_restart():
    executor = PluginExecutor("test_plugin")
    run_count = [0]
    done = threading.Event()

    def target():
        run_count[0] += 1
        time.sleep(0.2)
        if run_count[0] >= 2:
            done.set()

    executor.start(target)
    time.sleep(0.1)
    assert executor.is_running()
    executor.restart(target)
    done.wait(timeout=2)
    assert run_count[0] == 2
    executor.stop()


def test_executor_double_start_rejected():
    executor = PluginExecutor("test_plugin")
    def target():
        time.sleep(0.1)
    assert executor.start(target)
    assert not executor.start(target)  # Already running
    executor.stop()


def test_executor_stop_when_not_running():
    executor = PluginExecutor("test_plugin")
    assert not executor.stop()


def test_executor_heartbeat_check():
    executor = PluginExecutor("test_plugin")
    def target():
        time.sleep(0.3)
    executor.start(target)
    time.sleep(0.1)
    assert executor.check_heartbeat()
    executor.stop()
    assert not executor.check_heartbeat()


def test_executor_custom_policy():
    policy = SandboxPolicy(startup_timeout=5.0, heartbeat_interval=10.0)
    executor = PluginExecutor("test_plugin", policy)
    assert executor.policy.startup_timeout == 5.0
    assert executor.policy.heartbeat_interval == 10.0
    executor.stop()
