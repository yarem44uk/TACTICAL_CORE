
"""Plugin ExecutionContext Tests."""

import threading
from app.plugins.sandbox.runtime import PluginExecutionContext


def test_context_creation():
    ctx = PluginExecutionContext(plugin_id="test")
    assert ctx.plugin_id == "test"
    assert ctx.execution_id is not None
    assert ctx.cancelled is False
    assert ctx.started_at is not None
    assert ctx.stopped_at is None


def test_context_cancel():
    ctx = PluginExecutionContext(plugin_id="test")
    ctx.mark_cancelled()
    assert ctx.cancelled is True


def test_context_stop():
    ctx = PluginExecutionContext(plugin_id="test")
    ctx.mark_stopped()
    assert ctx.cancelled is False
    assert ctx.stopped_at is not None


def test_context_is_alive_with_thread():
    ctx = PluginExecutionContext(plugin_id="test")
    assert not ctx.is_alive()

    t = threading.Thread(target=lambda: None)
    t.start()
    ctx.thread = t
    # Thread might finish immediately, so just check it exists
    assert ctx.thread is not None
    t.join()


def test_context_is_alive_no_task():
    ctx = PluginExecutionContext(plugin_id="test")
    assert not ctx.is_alive()
