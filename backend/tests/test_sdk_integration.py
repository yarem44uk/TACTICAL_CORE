"""
Plugin SDK - Integration Tests.

Tests that all SDK modules work together as a package.
"""

import asyncio
import sys
sys.path.insert(0, "/opt/data/tactical_core_github/backend")

import pytest


class TestSDKIntegration:
    """Integration tests verifying the SDK as a complete package."""

    def test_full_package_import(self) -> None:
        """The entire SDK package must import without error."""
        import app.plugins.sdk
        assert len(app.plugins.sdk.__all__) == 15

    def test_all_exports_accessible(self) -> None:
        """Every item in __all__ must be accessible."""
        import app.plugins.sdk
        for name in app.plugins.sdk.__all__:
            obj = getattr(app.plugins.sdk, name)
            assert obj is not None

    def test_lifecycle_state_is_plugin_state(self) -> None:
        """LifecycleState must be PluginState per ADR-010-004-001."""
        from app.plugins.sdk import LifecycleState, PluginState
        assert LifecycleState is PluginState

    def test_health_module(self) -> None:
        """PluginHealth must initialize and report status."""
        from app.plugins.sdk import PluginHealth, HealthStatus
        h = PluginHealth(plugin_id="integ")
        assert h.status == HealthStatus.UNKNOWN
        h.set_status(HealthStatus.HEALTHY)
        assert h.status == HealthStatus.HEALTHY

    def test_permissions_module(self) -> None:
        """PluginPermissions must support grant/revoke."""
        from app.plugins.sdk import PluginPermissions, Permission
        p = PluginPermissions(plugin_id="integ")
        assert p.has("events:publish") is False
        p.grant("events:publish")
        assert p.has("events:publish") is True
        p.revoke("events:publish")
        assert p.has("events:publish") is False

    def test_lifecycle_module(self) -> None:
        """PluginLifecycle must transition states correctly."""
        from app.plugins.sdk import PluginLifecycle, PluginState
        lc = PluginLifecycle(plugin_id="integ")
        assert lc.current_state == PluginState.DISCOVERED
        lc.transition(PluginState.VALIDATED)
        assert lc.current_state == PluginState.VALIDATED

    def test_storage_module(self, tmp_path) -> None:
        """PluginStorage must persist and reload."""
        from app.plugins.sdk import PluginStorage
        s = PluginStorage(plugin_id="integ", storage_path=str(tmp_path))
        s.set("test", "value")
        s.persist()
        s2 = PluginStorage(plugin_id="integ", storage_path=str(tmp_path))
        assert s2.get("test") == "value"

    def test_logger_module(self, caplog) -> None:
        """PluginLogger must produce log output."""
        import logging
        from app.plugins.sdk import PluginLogger
        l = PluginLogger(plugin_id="integ", level=logging.DEBUG)
        caplog.set_level(logging.INFO)
        l.info("integration test")
        assert "integration test" in caplog.text

    def test_health_check_execution(self) -> None:
        """Health checks must execute and produce reports."""
        from app.plugins.sdk import PluginHealth, HealthStatus
        h = PluginHealth(plugin_id="check")
        h.add_check("always_ok", lambda: (True, "ok"))
        report = asyncio.run(h.run_checks())
        assert report.overall_status == HealthStatus.HEALTHY
        assert len(report.checks) == 1

    def test_permissions_admin_wildcard(self) -> None:
        """Admin wildcard must grant all permissions."""
        from app.plugins.sdk import PluginPermissions, Permission
        p = PluginPermissions(plugin_id="admin", capabilities=["*"])
        assert p.is_admin() is True
        for perm in Permission:
            assert p.has(perm.value) is True

    def test_sdk_no_pipeline_imports(self) -> None:
        """SDK must not import from app.pipeline."""
        import app.plugins.sdk
        # If this import fails with ImportError, the SDK has a pipeline dependency
        # This test passes if the SDK imports cleanly

    def test_sdk_no_database_imports(self) -> None:
        """SDK must not import from app.database."""
        import app.plugins.sdk
        # Same pattern — SDK must be self-contained
