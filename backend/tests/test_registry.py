"""
Plugin Registry Tests.

Verifies passive datastore — zero business logic.
"""
import threading

from app.plugins.registry.registry import (
    DISCOVERED,
    FAILED,
    LOADED,
    RUNNING,
    PluginRegistry,
    RegistryEntry,
    STOPPED,
    VALIDATED,
    UNLOADED,
)


def _make_entry(plugin_id="test", status=DISCOVERED):
    return RegistryEntry(
        plugin_id=plugin_id,
        plugin_name="Test Plugin",
        version="1.0",
        instance=object(),
        status=status,
    )


def test_registry_add_and_find():
    reg = PluginRegistry()
    entry = _make_entry("p1")
    reg.add(entry)
    found = reg.find("p1")
    assert found is entry
    assert found.plugin_id == "p1"


def test_registry_add_replaces_existing():
    reg = PluginRegistry()
    e1 = _make_entry("p1", status=LOADED)
    e2 = _make_entry("p1", status=RUNNING)
    reg.add(e1)
    reg.add(e2)
    found = reg.find("p1")
    assert found.status == RUNNING


def test_registry_remove():
    reg = PluginRegistry()
    reg.add(_make_entry("p1"))
    removed = reg.remove("p1")
    assert removed is not None
    assert reg.find("p1") is None


def test_registry_remove_nonexistent():
    reg = PluginRegistry()
    assert reg.remove("missing") is None


def test_registry_exists():
    reg = PluginRegistry()
    assert reg.exists("missing") is False
    reg.add(_make_entry("p1"))
    assert reg.exists("p1") is True


def test_registry_list():
    reg = PluginRegistry()
    e1 = _make_entry("p1")
    e2 = _make_entry("p2")
    reg.add(e1)
    reg.add(e2)
    entries = reg.list()
    assert len(entries) == 2
    ids = [e.plugin_id for e in entries]
    assert "p1" in ids
    assert "p2" in ids


def test_registry_update_status():
    reg = PluginRegistry()
    reg.add(_make_entry("p1", status=DISCOVERED))
    result = reg.update_status("p1", RUNNING)
    assert result is True
    assert reg.find("p1").status == RUNNING


def test_registry_update_status_nonexistent():
    reg = PluginRegistry()
    result = reg.update_status("missing", RUNNING)
    assert result is False


def test_registry_update_error():
    reg = PluginRegistry()
    reg.add(_make_entry("p1", status=RUNNING))
    reg.update_error("p1", "Something broke")
    entry = reg.find("p1")
    assert entry.status == FAILED
    assert entry.last_error == "Something broke"


def test_registry_get_instance():
    reg = PluginRegistry()
    fake_instance = object()
    reg.add(_make_entry("p1"))
    reg.list()[0].instance = fake_instance
    assert reg.get_instance("p1") is fake_instance
    assert reg.get_instance("missing") is None


def test_registry_len_and_contains():
    reg = PluginRegistry()
    assert len(reg) == 0
    assert "p1" not in reg
    reg.add(_make_entry("p1"))
    assert len(reg) == 1
    assert "p1" in reg


def test_registry_thread_safety():
    """Concurrent adds should not lose entries."""
    reg = PluginRegistry()
    num_threads = 50

    def add_entries(thread_id: int):
        for i in range(20):
            unique_id = f"t{thread_id}_p{i:04d}"
            reg.add(_make_entry(unique_id))

    threads = [threading.Thread(target=add_entries, args=(tid,)) for tid in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(reg) == 1000  # 50 * 20


def test_registry_state_constants():
    """Verify all approved states exist."""
    expected = {DISCOVERED, VALIDATED, LOADED, RUNNING, STOPPED, FAILED, UNLOADED}
    assert expected == {"DISCOVERED", "VALIDATED", "LOADED", "RUNNING", "STOPPED", "FAILED", "UNLOADED"}
