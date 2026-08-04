"""
Plugin Discovery, Loader, Registry, Validator, and HotReload Tests.

Tests for WO-010-005 Plugin Discovery & PluginManager Integration.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import sys
sys.path.insert(0, "/opt/data/tactical_core_github/backend")

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.plugins.discovery.plugin_discovery import PluginDiscovery, DiscoveredPlugin
from app.plugins.manifest.plugin_manifest import ManifestParser, PluginManifestInfo
from app.plugins.loader.plugin_loader import PluginLoader, LoadedPlugin
from app.plugins.registry.plugin_registry import PluginRegistry, RegisteredPlugin
from app.plugins.validator.plugin_validator import PluginValidator, ValidationResult
from app.plugins.hotreload.hot_reload import PluginHotReload, ReloadResult
from app.plugins.manager.plugin_manager import PluginManager
from app.plugins.sdk.base import BasePlugin, PluginState
from app.plugins.sdk.context import PluginContext


# Test plugin class with configurable ID
class ExamplePlugin(BasePlugin):
    """Example plugin for discovery tests."""

    def __init__(self, plugin_id: str = "example-plugin") -> None:
        self._plugin_id = plugin_id
        super().__init__()

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    @property
    def plugin_name(self) -> str:
        return "Example Plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "An example plugin"


# ===== Discovery Tests =====

class TestPluginDiscovery:
    """Tests for PluginDiscovery."""

    def test_discover_empty_directory(self, tmp_path: Path) -> None:
        """Test discovery in empty directory."""
        discovery = PluginDiscovery([str(tmp_path)])
        discovered = discovery.discover()
        assert len(discovered) == 0

    def test_discover_add_remove_directory(self, tmp_path: Path) -> None:
        """Test adding and removing directories."""
        discovery = PluginDiscovery()
        discovery.add_directory(str(tmp_path))
        assert str(tmp_path) in [str(d) for d in discovery.plugin_directories]
        discovery.remove_directory(str(tmp_path))
        assert str(tmp_path) not in [str(d) for d in discovery.plugin_directories]

    def test_discover_with_manifest_json(self, tmp_path: Path) -> None:
        """Test discovering a plugin with manifest.json."""
        plugin_dir = tmp_path / "my_plugin"
        plugin_dir.mkdir()

        manifest = {
            "id": "my-plugin",
            "name": "My Plugin",
            "version": "1.0.0",
            "description": "A test plugin",
            "api_version": "1.0",
        }
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest))

        discovery = PluginDiscovery([str(tmp_path)])
        discovered = discovery.discover()
        assert len(discovered) == 1
        assert discovered[0].plugin_id == "my-plugin"
        assert discovered[0].has_manifest_json is True

    def test_discover_with_plugin_py(self, tmp_path: Path) -> None:
        """Test discovering a plugin with plugin.py (only, no manifest.json)."""
        plugin_dir = tmp_path / "py_only_plugin"
        plugin_dir.mkdir()

        # plugin.py needs a MANIFEST dict for discovery to work
        plugin_content = """
from app.plugins.sdk.base import BasePlugin

MANIFEST = {
    "id": "py-only-plugin",
    "name": "Py Only Plugin",
    "version": "1.0.0",
    "description": "A plugin defined via plugin.py",
    "api_version": "1.0",
}

class Plugin(BasePlugin):
    PLUGIN_ID = "py-only-plugin"

    @property
    def plugin_id(self) -> str:
        return self.PLUGIN_ID
"""
        (plugin_dir / "plugin.py").write_text(plugin_content)

        discovery = PluginDiscovery([str(tmp_path)])
        discovered = discovery.discover()
        # Discovery finds directory with plugin.py
        assert len(discovered) == 1
        assert discovered[0].has_plugin_py is True


# ===== Manifest Parser Tests =====

class TestManifestParser:
    """Tests for ManifestParser."""

    def test_parse_json_valid(self, tmp_path: Path) -> None:
        """Test parsing a valid manifest.json."""
        manifest = {
            "id": "parse-test",
            "name": "Parse Test",
            "version": "1.0.0",
            "api_version": "1.0",
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest))

        parser = ManifestParser()
        info = parser.parse_json(path)
        assert info.plugin_id == "parse-test"
        assert info.version == "1.0.0"

    def test_parse_json_invalid(self, tmp_path: Path) -> None:
        """Test parsing invalid JSON raises error."""
        parser = ManifestParser()
        path = tmp_path / "bad.json"
        path.write_text("not valid json")
        with pytest.raises(Exception):
            parser.parse_json(path)

    def test_parse_json_missing_required(self, tmp_path: Path) -> None:
        """Test parsing manifest with missing required fields."""
        parser = ManifestParser()
        manifest = {
            "name": "No ID",
            "version": "1.0.0",
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest))
        with pytest.raises(Exception):
            parser.parse_json(path)


# ===== Loader Tests =====

class TestPluginLoader:
    """Tests for PluginLoader."""

    def test_loader_initialization(self) -> None:
        """Test loader initializes correctly."""
        loader = PluginLoader()
        assert len(loader.loaded_plugins) == 0

    def test_load_returns_loaded_plugin(self, tmp_path: Path) -> None:
        """Test that load returns a LoadedPlugin object."""
        loader = PluginLoader()
        discovered = DiscoveredPlugin(
            plugin_id="loader-test",
            plugin_name="Loader Test",
            version="1.0.0",
            author="Test",
            description="Test",
            directory=tmp_path,
        )
        result = loader.load(discovered)
        assert isinstance(result, LoadedPlugin)


# ===== Registry Tests =====

class TestPluginRegistry:
    """Tests for PluginRegistry."""

    def _make_discovered(self, plugin_id: str, tmp_path: Path) -> DiscoveredPlugin:
        return DiscoveredPlugin(
            plugin_id=plugin_id,
            plugin_name="Example",
            version="1.0.0",
            author="Test",
            description="Test",
            directory=tmp_path,
        )

    def test_register_and_get_plugin(self, tmp_path: Path) -> None:
        """Test registering and getting a plugin."""
        registry = PluginRegistry()
        plugin = ExamplePlugin(plugin_id="example-unique-1")
        discovered = self._make_discovered("example-unique-1", tmp_path)
        loaded = LoadedPlugin(plugin=plugin, discovered=discovered)

        registered = registry.register(plugin, discovered, loaded)
        assert registered.plugin_id == "example-unique-1"
        result = registry.get("example-unique-1")
        assert result is not None
        assert result.plugin_id == "example-unique-1"

    def test_unregister_plugin(self, tmp_path: Path) -> None:
        """Test unregistering a plugin."""
        registry = PluginRegistry()
        plugin = ExamplePlugin(plugin_id="example-unreg")
        discovered = self._make_discovered("example-unreg", tmp_path)
        loaded = LoadedPlugin(plugin=plugin, discovered=discovered)

        registry.register(plugin, discovered, loaded)
        assert registry.is_registered("example-unreg")
        registry.unregister("example-unreg")
        assert not registry.is_registered("example-unreg")

    def test_is_registered(self, tmp_path: Path) -> None:
        """Test is_registered check."""
        registry = PluginRegistry()
        assert not registry.is_registered("anything")
        plugin = ExamplePlugin(plugin_id="example-registered-check")
        discovered = self._make_discovered("example-registered-check", tmp_path)
        loaded = LoadedPlugin(plugin=plugin, discovered=discovered)
        registry.register(plugin, discovered, loaded)
        assert registry.is_registered("example-registered-check")

    def test_list_plugins(self, tmp_path: Path) -> None:
        """Test listing all plugins."""
        registry = PluginRegistry()
        for i in range(3):
            plugin = ExamplePlugin(plugin_id=f"example-list-{i}")
            discovered = self._make_discovered(f"example-list-{i}", tmp_path)
            loaded = LoadedPlugin(plugin=plugin, discovered=discovered)
            registry.register(plugin, discovered, loaded)
        assert registry.plugin_count == 3
        listed = registry.list_plugins()
        assert len(listed) == 3

    def test_get_unregistered_plugin(self) -> None:
        """Test getting unregistered plugin."""
        registry = PluginRegistry()
        result = registry.get("nonexistent")
        assert result is None

    def test_get_all_info(self, tmp_path: Path) -> None:
        """Test getting all plugin info."""
        registry = PluginRegistry()
        plugin = ExamplePlugin(plugin_id="example-info")
        discovered = self._make_discovered("example-info", tmp_path)
        loaded = LoadedPlugin(plugin=plugin, discovered=discovered)
        registry.register(plugin, discovered, loaded)
        info = registry.get_all_info()
        assert len(info) == 1


# ===== Validator Tests =====

class TestPluginValidator:
    """Tests for PluginValidator."""

    def _make_discovered(self, plugin_id: str) -> DiscoveredPlugin:
        return DiscoveredPlugin(
            plugin_id=plugin_id,
            plugin_name="Example",
            version="1.0.0",
            author="Test",
            description="Test",
            directory=None,
        )

    def _make_loaded(self, plugin_id: str) -> LoadedPlugin:
        plugin = ExamplePlugin(plugin_id=plugin_id)
        discovered = self._make_discovered(plugin_id)
        return LoadedPlugin(plugin=plugin, discovered=discovered)

    def test_validate_base_plugin_valid(self) -> None:
        """Test validating a valid BasePlugin instance."""
        validator = PluginValidator()
        loaded = self._make_loaded("example-validate-base")
        result = validator.validate_base_plugin(loaded)
        assert result.is_valid is True

    def test_validate_sdk_compatibility(self) -> None:
        """Test validating SDK compatibility."""
        validator = PluginValidator()
        loaded = self._make_loaded("example-validate-sdk")
        result = validator.validate_sdk_compatibility(loaded)
        assert result.is_valid is True

    def test_validate_full(self) -> None:
        """Test full validation pipeline."""
        validator = PluginValidator()
        loaded = self._make_loaded("example-validate-full")
        discovered = self._make_discovered("example-validate-full")
        result = validator.validate_full(discovered, loaded)
        # Full validation result
        assert isinstance(result, ValidationResult)


# ===== HotReload Tests =====

class TestPluginHotReload:
    """Tests for PluginHotReload."""

    def test_reload_result_dataclass(self) -> None:
        """Test ReloadResult dataclass."""
        result = ReloadResult(
            plugin_id="example-reload",
            success=True,
            error=None,
        )
        assert result.success is True
        assert result.plugin_id == "example-reload"

    def test_reload_result_failure(self) -> None:
        """Test ReloadResult with failure."""
        result = ReloadResult(
            plugin_id="example-reload-fail",
            success=False,
            error="Something went wrong",
        )
        assert result.success is False
        assert result.error == "Something went wrong"

    def test_initialization_with_deps(self) -> None:
        """Test PluginHotReload initialization with dependencies."""
        loader = PluginLoader()
        registry = PluginRegistry()
        discovery = PluginDiscovery([])
        validator = PluginValidator()
        reload_mgr = PluginHotReload(
            loader=loader,
            registry=registry,
            discovery=discovery,
            validator=validator,
        )
        # Verify it was initialized (no exception)
        assert reload_mgr is not None


# ===== PluginManager Integration Tests =====

class TestPluginManager:
    """Tests for PluginManager integration."""

    def test_auto_discover_and_register(self, tmp_path: Path) -> None:
        """Test auto-discovering plugins from directory."""
        for i in range(2):
            plugin_dir = tmp_path / f"disc_plugin_{i}"
            plugin_dir.mkdir()
            manifest = {
                "id": f"disc-plugin-{i}",
                "name": f"Disc Plugin {i}",
                "version": "1.0.0",
                "description": f"Plugin {i}",
                "api_version": "1.0",
                "entrypoint": f"plugin:Plugin",
            }
            (plugin_dir / "manifest.json").write_text(json.dumps(manifest))

        manager = PluginManager(plugin_directories=[str(tmp_path)])
        # Discovery should find 2 plugins
        discovered = manager.discovery.discover()
        assert len(discovered) == 2

    def test_register_plugin_manually(self) -> None:
        """Test registering a plugin manually."""
        manager = PluginManager()
        plugin = ExamplePlugin(plugin_id="example-manual")
        manager.register_plugin(plugin)
        result = manager.get_plugin("example-manual")
        assert result.plugin_id == "example-manual"

    def test_unregister_plugin(self) -> None:
        """Test unregistering a plugin."""
        manager = PluginManager()
        plugin = ExamplePlugin(plugin_id="example-unreg-mgr")
        manager.register_plugin(plugin)
        manager.unregister_plugin("example-unreg-mgr")
        result = manager.get_plugin("example-unreg-mgr")
        assert result is None

    def test_enable_disable_plugin(self) -> None:
        """Test enabling and disabling a plugin."""
        manager = PluginManager()
        plugin = ExamplePlugin(plugin_id="example-enable")
        manager.register_plugin(plugin)
        manager.disable_plugin("example-enable")
        manager.enable_plugin("example-enable")
        result = manager.get_plugin("example-enable")
        assert result.plugin_id == "example-enable"

    def test_get_plugin_health(self) -> None:
        """Test getting plugin health."""
        manager = PluginManager()
        plugin = ExamplePlugin(plugin_id="example-health")
        manager.register_plugin(plugin)
        health = manager.get_plugin_health("example-health")
        assert health is not None
        assert "enabled" in health

    def test_get_all_health(self) -> None:
        """Test getting all plugin health."""
        manager = PluginManager()
        plugin1 = ExamplePlugin(plugin_id="example-health-1")
        plugin2 = ExamplePlugin(plugin_id="example-health-2")
        manager.register_plugin(plugin1)
        manager.register_plugin(plugin2)
        health = manager.get_all_health()
        assert health["total"] == 2
        assert len(health["plugins"]) == 2

    def test_plugin_manager_len_and_contains(self) -> None:
        """Test __len__ and __contains__ magic methods."""
        manager = PluginManager()
        assert len(manager) == 0
        assert "anything" not in manager

        plugin = ExamplePlugin(plugin_id="example-magic")
        manager.register_plugin(plugin)
        assert len(manager) == 1
        assert "example-magic" in manager


# ===== End-to-End System Tests =====

class TestPluginSystemE2E:
    """End-to-end system tests."""

    def test_full_plugin_lifecycle(self) -> None:
        """Test full plugin lifecycle: register -> validate -> disable -> enable -> unregister."""
        manager = PluginManager()

        # Register plugin
        plugin = ExamplePlugin(plugin_id="example-e2e-full")
        manager.register_plugin(plugin)

        # Verify registered
        assert len(manager) == 1
        assert "example-e2e-full" in manager

        # Disable and enable
        manager.disable_plugin("example-e2e-full")
        manager.enable_plugin("example-e2e-full")

        # Unregister
        manager.unregister_plugin("example-e2e-full")
        assert len(manager) == 0

    def test_multiple_plugins_lifecycle(self) -> None:
        """Test managing multiple plugins."""
        manager = PluginManager()

        # Register 3 plugins
        for i in range(3):
            plugin = ExamplePlugin(plugin_id=f"example-multi-{i}")
            manager.register_plugin(plugin)

        assert len(manager) == 3

        # Get all health
        health = manager.get_all_health()
        assert health["total"] == 3
        assert len(health["plugins"]) == 3

        # Shutdown all
        manager.shutdown_all()
        assert len(manager) == 3  # Still registered, just stopped
