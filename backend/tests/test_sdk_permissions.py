"""
Plugin SDK - Permissions Tests.

Tests for PluginPermissions and Permission.
"""

import sys
sys.path.insert(0, "/opt/data/tactical_core_github/backend")

import pytest
from app.plugins.sdk.permissions import PluginPermissions, Permission, PermissionDecision


class TestPluginPermissions:
    """PluginPermissions unit tests."""

    def _make(self, caps=None) -> PluginPermissions:
        return PluginPermissions(plugin_id="test-perm", capabilities=caps)

    def test_initial_no_capabilities(self) -> None:
        p = self._make()
        assert p.granted_capabilities == []

    def test_initial_with_capabilities(self) -> None:
        p = self._make(["events:publish", "events:subscribe"])
        assert "events:publish" in p.granted_capabilities
        assert "events:subscribe" in p.granted_capabilities

    def test_grant_new_capability(self) -> None:
        p = self._make()
        assert p.grant("events:publish") is True
        assert p.has("events:publish") is True

    def test_grant_existing_capability(self) -> None:
        p = self._make(["events:publish"])
        assert p.grant("events:publish") is False

    def test_grant_with_enum(self) -> None:
        p = self._make()
        assert p.grant(Permission.EVENTS_PUBLISH) is True
        assert p.has("events:publish") is True

    def test_revoke_capability(self) -> None:
        p = self._make(["events:publish"])
        assert p.revoke("events:publish") is True
        assert p.has("events:publish") is False

    def test_revoke_nonexistent(self) -> None:
        p = self._make()
        assert p.revoke("events:publish") is False

    def test_deny_by_default(self) -> None:
        p = self._make()
        assert p.has("events:publish") is False
        assert p.has("database:write") is False

    def test_admin_wildcard(self) -> None:
        p = self._make(["*"])
        assert p.is_admin() is True
        assert p.has("events:publish") is True
        assert p.has("code:execute") is True

    def test_check_returns_decision(self) -> None:
        p = self._make(["events:publish"])
        d = p.check("events:publish")
        assert isinstance(d, PermissionDecision)
        assert d.granted is True

    def test_check_denied(self) -> None:
        p = self._make()
        d = p.check("events:publish")
        assert d.granted is False

    def test_get_permissions(self) -> None:
        p = self._make(["events:publish"])
        perms = p.get_permissions()
        assert perms["events:publish"] is True
        assert perms["database:write"] is False

    def test_clear(self) -> None:
        p = self._make(["events:publish", "events:subscribe"])
        p.clear()
        assert p.granted_capabilities == []
        assert p.is_admin() is False

    def test_to_dict(self) -> None:
        p = self._make(["events:publish"])
        d = p.to_dict()
        assert d["plugin_id"] == "test-perm"
        assert "events:publish" in d["granted"]
        assert d["is_admin"] is False
