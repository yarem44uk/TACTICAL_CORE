"""
Plugin Discovery Tests.

Verifies filesystem scanning only — no imports, no validation.
"""
import tempfile
from pathlib import Path

from app.plugins.discovery.discovery import PluginCandidate, discover


def test_discover_empty_directories():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "empty").mkdir()
        candidates = discover([root])
        assert len(candidates) == 0


def test_discover_manifest_json():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_dir = root / "signal"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text('{"plugin_id": "signal"}')
        candidates = discover([root])
        assert len(candidates) == 1
        c = candidates[0]
        assert c.path == plugin_dir
        assert c.candidate_type == "manifest"


def test_discover_plugin_py():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_dir = root / "mqtt"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text('class Plugin: pass')
        candidates = discover([root])
        assert len(candidates) == 1
        c = candidates[0]
        assert c.path == plugin_dir
        assert c.candidate_type == "plugin_py"


def test_discover_prefers_manifest_over_plugin_py():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_dir = root / "radio"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text("{}")
        (plugin_dir / "plugin.py").write_text("")
        candidates = discover([root])
        assert len(candidates) == 1
        assert candidates[0].candidate_type == "manifest"


def test_discover_skips_hidden_and_pycache():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "__pycache__").mkdir()
        (root / ".hidden").mkdir()
        (root / ".venv").mkdir()
        (root / ".git").mkdir()
        candidates = discover([root])
        assert len(candidates) == 0


def test_discover_multiple_plugins():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("signal", "mqtt", "radio"):
            d = root / name
            d.mkdir()
            (d / "manifest.json").write_text(f'{{"plugin_id": "{name}"}}')
        candidates = discover([root])
        ids = [c.path.name for c in candidates]
        assert sorted(ids) == ["mqtt", "radio", "signal"]


def test_discover_multiple_root_paths():
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        root1 = Path(tmp1)
        root2 = Path(tmp2)
        d1 = root1 / "plugin_a"
        d1.mkdir()
        (d1 / "plugin.py").write_text("")
        d2 = root2 / "plugin_b"
        d2.mkdir()
        (d2 / "plugin.py").write_text("")
        candidates = discover([root1, root2])
        assert len(candidates) == 2


def test_discover_no_filesystem_side_effects():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_dir = root / "test"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text("")
        candidates = discover([root])
        # Discovery should not have created any files
        created = list(root.rglob("*"))
        assert len(created) == 2  # plugin_dir + plugin.py
