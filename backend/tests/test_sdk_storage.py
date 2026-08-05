"""
Plugin SDK - Storage Tests.

Tests for PluginStorage key-value store.
"""

import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, "/opt/data/tactical_core_github/backend")

import pytest
from app.plugins.sdk.storage import PluginStorage


class TestPluginStorage:
    """PluginStorage unit tests."""

    def _make(self, tmpdir: Path) -> PluginStorage:
        return PluginStorage(plugin_id="test-store", storage_path=str(tmpdir))

    def test_initial_state_is_empty(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        assert s.keys() == []
        assert s.get("nonexistent") is None

    def test_set_and_get(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        s.set("key1", "value1")
        assert s.get("key1") == "value1"

    def test_default_value(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        assert s.get("missing", "default") == "default"

    def test_delete_existing(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        s.set("k", "v")
        assert s.delete("k") is True
        assert s.get("k") is None

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        assert s.delete("nope") is False

    def test_has_key(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        s.set("x", 1)
        assert s.has("x") is True
        assert s.has("y") is False

    def test_keys(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        s.set("a", 1)
        s.set("b", 2)
        assert sorted(s.keys()) == ["a", "b"]

    def test_clear(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        s.set("a", 1)
        s.set("b", 2)
        s.clear()
        assert s.keys() == []

    def test_persist_and_reload(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        s.set("data", {"nested": True})
        s.persist()
        # Reload from disk
        s2 = PluginStorage(plugin_id="test-store", storage_path=str(tmp_path))
        assert s2.get("data") == {"nested": True}

    def test_reset_removes_file(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        s.set("k", "v")
        s.persist()
        s.reset()
        assert not s.storage_path.exists()
        assert s.keys() == []

    def test_storage_isolation_by_plugin_id(self, tmp_path: Path) -> None:
        s1 = PluginStorage(plugin_id="plugin-a", storage_path=str(tmp_path))
        s2 = PluginStorage(plugin_id="plugin-b", storage_path=str(tmp_path))
        s1.set("shared", "from_a")
        s2.set("shared", "from_b")
        assert s1.get("shared") == "from_a"
        assert s2.get("shared") == "from_b"

    def test_stores_complex_types(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        s.set("list", [1, 2, 3])
        s.set("dict", {"a": 1})
        assert s.get("list") == [1, 2, 3]
        assert s.get("dict") == {"a": 1}

    def test_to_dict(self, tmp_path: Path) -> None:
        s = self._make(tmp_path)
        s.set("k", "v")
        d = s.to_dict()
        assert d["plugin_id"] == "test-store"
        assert d["key_count"] == 1

    def test_corrupted_file_loads_empty(self, tmp_path: Path) -> None:
        (tmp_path / "test-store.json").write_text("NOT JSON")
        s = self._make(tmp_path)
        assert s.keys() == []
