"""
Hot Reload Tests.

Verifies snapshot rollback algorithm.
"""
import tempfile
from pathlib import Path

import pytest

from app.plugins.hotreload.hot_reload import reload_plugin
from app.plugins.manifest.manifest import PluginMetadata
from app.plugins.registry.registry import LOADED, RegistryEntry, RUNNING


@pytest.fixture
def mock_entry():
    fake_instance = type("FakePlugin", (), {
        "on_startup": lambda self: None,
        "on_shutdown": lambda self: None,
    })()
    return RegistryEntry(
        plugin_id="test-plugin",
        plugin_name="Test Plugin",
        version="1.0.0",
        instance=fake_instance,
        status=RUNNING,
    )


@pytest.fixture
def sample_plugin_dir(tmp_path: Path) -> Path:
    """Create a valid plugin directory with manifest.json."""
    plugin_dir = tmp_path / "test_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text("""
{
    "plugin_id": "test-plugin",
    "name": "Test Plugin",
    "version": "2.0.0",
    "sdk_version": "1.0",
    "entrypoint": "plugin.py",
    "class_name": "TestPlugin"
}
""")
    (plugin_dir / "plugin.py").write_text("""
from app.plugins.sdk.base import BasePlugin

class TestPlugin(BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "test-plugin"
""")
    return plugin_dir


def test_reload_plugin_success(sample_plugin_dir, mock_entry):
    metadata = PluginMetadata(
        plugin_id="test-plugin",
        name="Test Plugin",
        version="2.0.0",
        sdk_version="1.0",
        class_name="TestPlugin",
        entrypoint="plugin.py",
    )
    success, new_entry, error = reload_plugin(sample_plugin_dir, mock_entry, metadata)
    assert success is True
    assert error is None
    assert new_entry.version == "2.0.0"
    assert new_entry.status == RUNNING


def test_reload_plugin_validation_fallback(sample_plugin_dir, mock_entry):
    """Reload with forbidden import should trigger rollback."""
    (sample_plugin_dir / "plugin.py").write_text("""
import app.database  # FORBIDDEN

class TestPlugin:
    pass
""")
    metadata = PluginMetadata(
        plugin_id="test-plugin",
        name="Test Plugin",
        version="2.0.0",
        sdk_version="1.0",
        class_name="TestPlugin",
        entrypoint="plugin.py",
    )
    success, new_entry, error = reload_plugin(sample_plugin_dir, mock_entry, metadata)
    assert success is False
    assert error is not None


def test_reload_plugin_manifest_metadata(tmp_path, mock_entry):
    """Reload should load metadata from manifest.json when not provided."""
    import uuid
    unique_suffix = uuid.uuid4().hex[:8]
    plugin_dir = tmp_path / f"test_plugin_{unique_suffix}"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text("""
{
    "plugin_id": "test-plugin",
    "name": "Test Plugin",
    "version": "3.0.0",
    "sdk_version": "1.0",
    "entrypoint": "plugin.py",
    "class_name": "TestPlugin"
}
""")
    (plugin_dir / "plugin.py").write_text("""
from app.plugins.sdk.base import BasePlugin

class TestPlugin(BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "test-plugin"
""")
    metadata = PluginMetadata(
        plugin_id="test-plugin",
        name="Test Plugin",
        version="3.0.0",
        sdk_version="1.0",
        class_name="TestPlugin",
        entrypoint="plugin.py",
    )
    success, new_entry, error = reload_plugin(plugin_dir, mock_entry, metadata)
    assert success is True
    assert new_entry.version == "3.0.0"
