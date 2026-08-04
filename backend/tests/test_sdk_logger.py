"""
Plugin SDK - Logger Tests.

Tests for PluginLogger structured logging.
"""

import logging
import sys
sys.path.insert(0, "/opt/data/tactical_core_github/backend")

import pytest
from app.plugins.sdk.logger import PluginLogger


class TestPluginLogger:
    """PluginLogger unit tests."""

    def _make(self) -> PluginLogger:
        return PluginLogger(
            plugin_id="test-logger",
            plugin_name="Test Logger",
            plugin_version="1.0.0",
            level=logging.DEBUG,
        )

    def test_plugin_id(self) -> None:
        l = self._make()
        assert l.plugin_id == "test-logger"

    def test_log_at_levels(self, caplog) -> None:
        l = self._make()
        caplog.set_level(logging.DEBUG)
        l.debug("debug msg")
        l.info("info msg")
        l.warning("warn msg")
        l.error("err msg")
        l.critical("crit msg")
        assert "debug msg" in caplog.text
        assert "info msg" in caplog.text
        assert "warn msg" in caplog.text
        assert "err msg" in caplog.text
        assert "crit msg" in caplog.text

    def test_log_includes_plugin_id(self, caplog) -> None:
        l = self._make()
        caplog.set_level(logging.INFO)
        l.info("hello")
        assert "test-logger" in caplog.text

    def test_log_with_structured_kwargs(self, caplog) -> None:
        l = self._make()
        caplog.set_level(logging.INFO)
        l.info("action", event_id="evt-1", source="signal")
        assert "action" in caplog.text
        assert "evt-1" in caplog.text

    def test_no_duplicate_handlers(self) -> None:
        """Logger should not accumulate handlers on repeated init."""
        l1 = PluginLogger(plugin_id="dup-test", level=logging.DEBUG)
        count1 = len(l1._logger.handlers)
        l2 = PluginLogger(plugin_id="dup-test", level=logging.DEBUG)
        count2 = len(l2._logger.handlers)
        assert count1 == count2
