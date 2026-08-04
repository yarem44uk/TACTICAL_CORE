"""
Plugin SDK - Health Tests.

Tests for PluginHealth, HealthStatus, and PluginMetrics.
"""

import asyncio
import sys
sys.path.insert(0, "/opt/data/tactical_core_github/backend")

import pytest
from app.plugins.sdk.health import PluginHealth, HealthStatus, PluginMetrics, HealthReport


class TestHealthStatus:
    """HealthStatus enum tests."""

    def test_health_status_values(self) -> None:
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestPluginHealth:
    """PluginHealth unit tests."""

    def _make(self) -> PluginHealth:
        return PluginHealth(plugin_id="test-health")

    def test_initial_status_is_unknown(self) -> None:
        h = self._make()
        assert h.status == HealthStatus.UNKNOWN

    def test_plugin_id_is_stored(self) -> None:
        h = PluginHealth(plugin_id="my-plugin")
        assert h.plugin_id == "my-plugin"

    def test_set_status(self) -> None:
        h = self._make()
        h.set_status(HealthStatus.HEALTHY, "All good")
        assert h.status == HealthStatus.HEALTHY

    def test_add_check(self) -> None:
        h = self._make()
        h.add_check("ping", lambda: (True, "ok"))
        report = asyncio.get_event_loop().run_until_complete(h.run_checks())
        assert len(report.checks) == 1
        assert report.checks[0].name == "ping"

    def test_run_checks_healthy(self) -> None:
        h = self._make()
        h.add_check("db", lambda: (True, "connected"))
        h.add_check("cache", lambda: (True, "warm"))
        report = asyncio.get_event_loop().run_until_complete(h.run_checks())
        assert report.overall_status == HealthStatus.HEALTHY

    def test_run_checks_unhealthy(self) -> None:
        h = self._make()
        h.add_check("db", lambda: (False, "timeout"))
        report = asyncio.get_event_loop().run_until_complete(h.run_checks())
        assert report.overall_status == HealthStatus.UNHEALTHY

    def test_run_checks_degraded(self) -> None:
        h = self._make()
        h.add_check("db", lambda: (True, "ok"))
        h.add_check("cache", lambda: (False, "miss"))
        report = asyncio.get_event_loop().run_until_complete(h.run_checks())
        assert report.overall_status == HealthStatus.DEGRADED

    def test_run_checks_failure_increments_counter(self) -> None:
        h = self._make()
        h.add_check("db", lambda: (False, "fail"))
        asyncio.get_event_loop().run_until_complete(h.run_checks())
        assert h.consecutive_failures == 1
        asyncio.get_event_loop().run_until_complete(h.run_checks())
        assert h.consecutive_failures == 2

    def test_run_checks_success_resets_counter(self) -> None:
        h = self._make()
        h.add_check("db", lambda: (False, "fail"))
        asyncio.get_event_loop().run_until_complete(h.run_checks())
        assert h.consecutive_failures == 1
        # Replace with healthy check
        h._checks.clear()
        h.add_check("db", lambda: (True, "ok"))
        asyncio.get_event_loop().run_until_complete(h.run_checks())
        assert h.consecutive_failures == 0

    def test_get_report_without_checks(self) -> None:
        h = self._make()
        h.set_status(HealthStatus.HEALTHY)
        report = h.get_report()
        assert report.overall_status == HealthStatus.HEALTHY
        assert report.checks == []

    def test_run_checks_exception_handled(self) -> None:
        h = self._make()
        h.add_check("bad", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        report = asyncio.get_event_loop().run_until_complete(h.run_checks())
        assert report.checks[0].status == HealthStatus.UNHEALTHY
        assert "Check failed" in report.checks[0].message

    def test_async_check_supported(self) -> None:
        async def async_check():
            return (True, "async ok")
        h = self._make()
        h.add_check("async", async_check)
        report = asyncio.get_event_loop().run_until_complete(h.run_checks())
        assert report.checks[0].status == HealthStatus.HEALTHY

    def test_to_dict(self) -> None:
        h = self._make()
        h.set_status(HealthStatus.HEALTHY)
        d = h.to_dict()
        assert d["plugin_id"] == "test-health"
        assert d["status"] == "healthy"


class TestPluginMetrics:
    """PluginMetrics unit tests."""

    def test_increment_events(self) -> None:
        m = PluginMetrics(plugin_id="test")
        m.increment_events(5)
        assert m.total_events_processed == 5

    def test_increment_errors(self) -> None:
        m = PluginMetrics(plugin_id="test")
        m.increment_errors(2)
        assert m.total_errors == 2

    def test_custom_metrics(self) -> None:
        m = PluginMetrics(plugin_id="test")
        m.set_metric("latency_ms", 42)
        assert m.get_metric("latency_ms") == 42
        assert m.get_metric("missing", 0) == 0

    def test_to_dict(self) -> None:
        m = PluginMetrics(plugin_id="test")
        d = m.to_dict()
        assert d["plugin_id"] == "test"
        assert d["total_events_processed"] == 0


class TestHealthReport:
    """HealthReport unit tests."""

    def test_to_dict(self) -> None:
        report = HealthReport(
            plugin_id="test",
            overall_status=HealthStatus.HEALTHY,
            checks=[],
            last_check=None,
        )
        d = report.to_dict()
        assert d["plugin_id"] == "test"
        assert d["overall_status"] == "healthy"
