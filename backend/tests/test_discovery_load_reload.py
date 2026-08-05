"""
Discovery → Load → Reload Integration Tests.

Full lifecycle test: discover candidates → validate → load → reload → unload.
"""
import tempfile
from pathlib import Path

from app.plugins.discovery.discovery import discover
from app.plugins.manager.plugin_manager import PluginManager


def test_full_discovery_load_unload_cycle():
    """Complete lifecycle: discover → load → query → unload."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_dir = root / "integration_test"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text("""
{
    "plugin_id": "integration-test",
    "name": "Integration Test",
    "version": "1.0.0",
    "sdk_version": "1.0",
    "entrypoint": "plugin.py",
    "class": "IntegrationPlugin"
}
""")
        (plugin_dir / "plugin.py").write_text("""
from app.plugins.sdk.base import BasePlugin
from app.contracts.plugin import IPlugin

class IntegrationPlugin(BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "integration-test"
    
    def register(self) -> None:
        pass
    
    def unregister(self) -> None:
        pass
""")

        manager = PluginManager()

        # Discover
        candidates = manager.discover([root])
        assert len(candidates) == 1
        assert candidates[0].path.name == "integration_test"

        # Load
        plugin_id = manager.load_plugin_from_candidate(candidates[0])
        assert plugin_id == "integration-test"

        # Query
        plugin = manager.get_plugin("integration-test")
        assert plugin is not None

        # Health
        health = manager.get_plugin_health("integration-test")
        assert health["plugin_id"] == "integration-test"

        # All health
        all_health = manager.get_all_health()
        assert all_health["total"] == 1

        # Unregister
        result = manager.unregister_plugin("integration-test")
        assert result is True

        # Verify removed
        assert manager.get_plugin("integration-test") is None


def test_discover_load_multiple_plugins():
    """Discover and load multiple plugins."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        for name in ("alpha", "beta", "gamma"):
            plugin_dir = root / name
            plugin_dir.mkdir()
            (plugin_dir / "manifest.json").write_text(
                f'{{"plugin_id": "{name}", "name": "{name.title()}", '
                f'"version": "1.0", "sdk_version": "1.0", '
                f'"entrypoint": "plugin.py", "class_name": "Plugin"}}'
            )
            (plugin_dir / "plugin.py").write_text(f"""
from app.plugins.sdk.base import BasePlugin

class Plugin(BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "{name}"
""")

        manager = PluginManager()
        candidates = manager.discover([root])
        assert len(candidates) == 3

        loaded_ids = []
        for c in candidates:
            pid = manager.load_plugin_from_candidate(c)
            if pid:
                loaded_ids.append(pid)

        assert len(loaded_ids) == 3
        assert sorted(loaded_ids) == ["alpha", "beta", "gamma"]


def test_load_rejects_forbidden_import():
    """Plugins importing forbidden layers are rejected by SecurityValidator."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_dir = root / "bad_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text("""
{
    "plugin_id": "bad-plugin",
    "name": "Bad Plugin",
    "version": "1.0",
    "sdk_version": "1.0",
    "entrypoint": "plugin.py",
    "class_name": "BadPlugin"
}
""")
        (plugin_dir / "plugin.py").write_text("""
import app.database
from app.plugins.sdk.base import BasePlugin

class BadPlugin(BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "bad-plugin"
""")
        manager = PluginManager()
        candidates = manager.discover([root])
        assert len(candidates) == 1

        result = manager.load_plugin_from_candidate(candidates[0])
        assert result is None


def test_load_rejects_missing_manifest_fields():
    """Plugins with incomplete manifest are rejected."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_dir = root / "incomplete"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text("""
{
    "plugin_id": "",
    "name": "",
    "version": "",
    "sdk_version": "",
    "entrypoint": "",
    "class_name": ""
}
""")
        (plugin_dir / "plugin.py").write_text("")
        manager = PluginManager()
        candidates = manager.discover([root])
        result = manager.load_plugin_from_candidate(candidates[0])
        assert result is None


def test_backward_compat_register_plugin():
    """Existing IPlugin registration still works."""
    from app.plugins.signal_reference_plugin import SignalReferencePlugin
    manager = PluginManager()
    plugin = SignalReferencePlugin()
    manager.register_plugin(plugin)
    assert manager.get_plugin("signal-reference-plugin") is plugin
    assert "signal-reference-plugin" in manager
    assert len(manager) == 1
