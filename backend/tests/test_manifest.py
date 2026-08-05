"""
Plugin Manifest Tests.

Verifies deserialization only — no validation, no imports.
"""
import tempfile
from pathlib import Path

from app.plugins.manifest.manifest import (
    PluginMetadata,
    parse_manifest_dict,
    parse_manifest_json,
)


def test_parse_manifest_json():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        f.write("""
{
    "plugin_id": "test-plugin",
    "name": "Test Plugin",
    "version": "1.0.0",
    "sdk_version": "1.0",
    "author": "Test Author",
    "entrypoint": "plugin.py",
    "class": "TestPlugin",
    "description": "A test plugin",
    "permissions": ["storage", "logger"],
    "subscriptions": ["test.event"],
    "configuration": {"key": "value"},
    "resources": {"config": "config.yaml"},
    "health_check_interval": 30
}
""")
        f.flush()
        metadata = parse_manifest_json(Path(f.name))

    assert isinstance(metadata, PluginMetadata)
    assert metadata.plugin_id == "test-plugin"
    assert metadata.name == "Test Plugin"
    assert metadata.version == "1.0.0"
    assert metadata.sdk_version == "1.0"
    assert metadata.author == "Test Author"
    assert metadata.entrypoint == "plugin.py"
    assert metadata.class_name == "TestPlugin"
    assert metadata.description == "A test plugin"
    assert metadata.permissions == ["storage", "logger"]
    assert metadata.subscriptions == ["test.event"]
    assert metadata.configuration == {"key": "value"}
    assert metadata.resources == {"config": "config.yaml"}
    assert metadata.health_check_interval == 30


def test_parse_manifest_dict():
    data = {
        "plugin_id": "simple",
        "name": "Simple",
        "version": "0.1.0",
        "sdk_version": "1.0",
        "entrypoint": "plugin.py",
        "class": "SimplePlugin",
    }
    metadata = parse_manifest_dict(data)
    assert metadata.plugin_id == "simple"
    assert metadata.name == "Simple"
    assert metadata.class_name == "SimplePlugin"


def test_parse_minimal_manifest():
    data = {
        "plugin_id": "minimal",
        "name": "Minimal",
        "version": "0.0.1",
        "sdk_version": "1.0",
        "entrypoint": "plugin.py",
        "class": "Plugin",
    }
    metadata = parse_manifest_dict(data)
    assert metadata.plugin_id == "minimal"
    assert metadata.author == "Unknown"  # default
    assert metadata.permissions == []  # default
    assert metadata.health_check_interval == 60  # default


def test_parse_empty_dict_produces_empty_metadata():
    metadata = parse_manifest_dict({})
    assert metadata.plugin_id == ""
    assert metadata.name == ""
    assert metadata.version == ""
    assert metadata.sdk_version == ""
    assert metadata.entrypoint == "plugin.py"
    assert metadata.class_name == ""


def test_parse_manifest_json_file_not_found():
    """parse_manifest_json raises FileNotFoundError for missing file."""
    try:
        parse_manifest_json(Path("/nonexistent/manifest.json"))
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        pass


def test_metadata_is_frozen():
    """PluginMetadata should be immutable (frozen dataclass)."""
    m = parse_manifest_dict({
        "plugin_id": "frozen",
        "name": "Frozen",
        "version": "1.0",
        "sdk_version": "1.0",
        "entrypoint": "plugin.py",
        "class": "Plugin",
    })
    try:
        m.plugin_id = "changed"  # noqa: B018
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass  # Expected
