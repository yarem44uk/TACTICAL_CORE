"""
Hot Reload Module.

Implements the approved reload algorithm with mandatory snapshot rollback.

Sequence (WO-010-005-R1):
    STOP → CREATE SNAPSHOT → UNLOAD → LOAD NEW → VALIDATE → START
    SUCCESS → DELETE SNAPSHOT
    FAILURE  → RESTORE SNAPSHOT → START PREVIOUS VERSION

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

from app.plugins.loader.loader import (
    create_plugin_instance,
    get_module,
    get_plugin_class,
    load_module_from_path,
    unload_module,
)
from app.plugins.manifest.manifest import (
    PluginMetadata,
    parse_manifest_dict,
    parse_manifest_json,
)
from app.plugins.registry.registry import (
    FAILED,
    LOADED,
    RUNNING,
    RegistryEntry,
    STOPPED,
    VALIDATED,
)
from app.plugins.validator.validator import (
    CompatibilityValidator,
    ManifestValidator,
    SecurityValidator,
)

logger = logging.getLogger(__name__)


@dataclass
class ReloadSnapshot:
    """Lightweight snapshot of a plugin's state before a hot reload attempt.

    Does NOT copy the plugin instance, threads, locks, sockets, or DB connections.
    Stores only the metadata needed to restore the previous registry entry.
    """

    plugin_id: str
    plugin_name: str
    version: str
    status: str
    module_name: str
    metadata: PluginMetadata
    instance: Any = field(default=None, repr=False)


def _validate_plugin(
    metadata: PluginMetadata,
    plugin_class: type,
    source_path: str,
) -> Tuple[bool, List[str]]:
    """Run the full validation pipeline on a candidate plugin."""
    errors: List[str] = []

    # 1. Manifest validation
    valid, err = ManifestValidator.validate(metadata)
    errors.extend(err)

    # 2. Security validation (AST — never executes plugin code)
    valid, err = SecurityValidator.validate_source(source_path)
    errors.extend(err)

    # 3. Compatibility validation (BasePlugin inheritance)
    if valid:
        valid, err = CompatibilityValidator.validate_class(plugin_class)
        errors.extend(err)

    # 4. SDK version compatibility
    if valid:
        valid, err = CompatibilityValidator.validate_sdk_version(metadata.sdk_version)
        errors.extend(err)

    return len(errors) == 0, errors


def _stop_plugin(instance: Any) -> None:
    """Gracefully stop a plugin instance."""
    try:
        if hasattr(instance, "on_shutdown"):
            instance.on_shutdown()
    except Exception as exc:
        logger.warning(f"Error stopping plugin: {exc}")


def _start_plugin(instance: Any) -> Tuple[bool, Optional[str]]:
    """Start a plugin instance. Returns (success, error_message)."""
    try:
        if hasattr(instance, "on_startup"):
            instance.on_startup()
        return True, None
    except Exception as exc:
        return False, str(exc)


def reload_plugin(
    plugin_dir: Path,
    current_entry: RegistryEntry,
    metadata: PluginMetadata,
) -> Tuple[bool, RegistryEntry, Optional[str]]:
    """
    Hot-reload a plugin with mandatory snapshot rollback.

    Returns:
        (success, entry, error_message)
    """
    # 1. STOP current plugin
    logger.info(f"Hot reload: stopping plugin {current_entry.plugin_id}")
    _stop_plugin(current_entry.instance)

    # 2. CREATE SNAPSHOT (lightweight — no deepcopy of instance/locks/sockets)
    snapshot = ReloadSnapshot(
        plugin_id=current_entry.plugin_id,
        plugin_name=current_entry.plugin_name,
        version=current_entry.version,
        status=current_entry.status,
        module_name=f"tactical_plugins.{current_entry.plugin_id}",
        metadata=metadata,
        instance=current_entry.instance,
    )

    # 3. UNLOAD old module
    old_module_name = snapshot.module_name
    try:
        old_mod = get_module(old_module_name)
        if old_mod is not None:
            unload_module(old_mod)
    except Exception as exc:
        logger.warning(f"Unload warning: {exc}")

    try:
        # 4. LOAD NEW module
        module = load_module_from_path(plugin_dir)

        # 5. Get class from manifest
        plugin_class = get_plugin_class(module, metadata.class_name)

        # 6. VALIDATE
        source_file = str(plugin_dir / "plugin.py")
        is_valid, errors = _validate_plugin(metadata, plugin_class, source_file)
        if not is_valid:
            raise ValueError(f"Validation failed: {'; '.join(errors)}")

        # 7. CREATE new instance
        new_instance = create_plugin_instance(plugin_class, metadata)

        # 8. START new instance
        success, err = _start_plugin(new_instance)
        if not success:
            raise RuntimeError(f"Startup failed: {err}")

        # SUCCESS — create updated entry
        new_entry = RegistryEntry(
            plugin_id=current_entry.plugin_id,
            plugin_name=metadata.name,
            version=metadata.version,
            instance=new_instance,
            status=RUNNING,
        )

        logger.info(f"Hot reload: plugin {current_entry.plugin_id} reloaded successfully")
        return True, new_entry, None

    except Exception as exc:
        # ROLLBACK — restore previous version
        logger.error(f"Hot reload failed for {current_entry.plugin_id}: {exc}")
        logger.info(f"Rolling back plugin {current_entry.plugin_id}")

        try:
            _start_plugin(snapshot.instance)
        except Exception as restore_err:
            logger.error(f"Rollback restore failed: {restore_err}")
            return False, current_entry, f"Reload failed and rollback failed: {exc}"

        return False, current_entry, str(exc)
