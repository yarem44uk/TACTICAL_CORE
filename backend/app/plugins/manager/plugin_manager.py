"""
Plugin Manager Implementation.

Orchestration ONLY — delegates all work to Discovery, Loader,
Manifest, Validator, Registry, and HotReload.

Must NOT:
  - perform filesystem scanning
  - use importlib / sys.modules
  - parse manifests
  - run validation logic
  - contain registry logic

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.contracts.plugin import IPlugin, IPluginManager

from app.plugins.discovery.discovery import PluginCandidate, discover
from app.plugins.hotreload.hot_reload import reload_plugin
from app.plugins.loader.loader import (
    create_plugin_instance,
    get_plugin_class,
    load_module_from_path,
)
from app.plugins.manifest.manifest import (
    PluginMetadata,
    parse_manifest_json,
)
from app.plugins.registry.registry import (
    FAILED,
    LOADED,
    RUNNING,
    RegistryEntry,
    STOPPED,
    VALIDATED,
    PluginRegistry,
)
from app.plugins.validator.validator import (
    CompatibilityValidator,
    ManifestValidator,
    SecurityValidator,
)
from app.plugins.sandbox.executor import PluginExecutor
from app.plugins.sandbox.policy import SandboxPolicy

logger = logging.getLogger(__name__)


class PluginManager(IPluginManager):
    """
    Orchestrator for the plugin lifecycle.

    Delegates to:
        Discovery  — filesystem scan
        Manifest   — deserialization
        Validator  — manifest / compatibility / security checks
        Loader     — dynamic import + instantiation
        Registry   — passive datastore
        HotReload  — reload with snapshot rollback
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._registry: PluginRegistry = PluginRegistry()
        self._event_bus: Optional[Any] = None
        self._event_engine: Optional[Any] = None
        self._executors: Dict[str, PluginExecutor] = {}

        logger.info("PluginManager initialized")

    # ------------------------------------------------------------------
    # Dependency injection
    # ------------------------------------------------------------------

    def set_event_bus(self, event_bus: Any) -> None:
        """Set the event bus for plugin communication."""
        with self._lock:
            self._event_bus = event_bus

    def set_event_engine(self, event_engine: Any) -> None:
        """Set the event engine for plugin communication."""
        with self._lock:
            self._event_engine = event_engine

    # ------------------------------------------------------------------
    # Discovery  (delegates to app.plugins.discovery)
    # ------------------------------------------------------------------

    def discover(
        self,
        root_paths: List[Path],
        *,
        manifest_name: str = "manifest.json",
        entrypoint_name: str = "plugin.py",
    ) -> List[PluginCandidate]:
        """
        Scan directories for plugin candidates.

        Delegates entirely to the Discovery module.
        """
        candidates = discover(
            root_paths,
            manifest_name=manifest_name,
            entrypoint_name=entrypoint_name,
        )
        logger.info(f"Discovery found {len(candidates)} candidate(s)")
        return candidates

    # ------------------------------------------------------------------
    # Loading pipeline  (orchestrates Manifest → Validator → Loader)
    # ------------------------------------------------------------------

    def load_plugin_from_candidate(self, candidate: PluginCandidate) -> Optional[str]:
        """
        Full loading pipeline for a single discovery candidate.

        1. Manifest: deserialize
        2. Validator: manifest + security + compatibility
        3. Loader: dynamic import + instantiate
        4. Registry: register entry

        Returns plugin_id on success, None on failure.
        """
        with self._lock:
            # 1. Manifest deserialization
            if candidate.candidate_type == "manifest":
                manifest_path = candidate.path / "manifest.json"
                if not manifest_path.is_file():
                    logger.error(f"No manifest.json at {manifest_path}")
                    return None
                metadata = parse_manifest_json(manifest_path)
            else:
                # plugin.py type — build minimal metadata from directory name
                metadata = PluginMetadata(
                    plugin_id=candidate.path.name,
                    name=candidate.path.name.title(),
                    version="0.0.0",
                    sdk_version="1.0",
                    class_name="Plugin",
                    entrypoint="plugin.py",
                )

            # 2. Manifest validation
            valid, errors = ManifestValidator.validate(metadata)
            if not valid:
                logger.error(
                    f"Manifest validation failed for {candidate.path}: {'; '.join(errors)}"
                )
                return None

            # 3. Security validation (AST scan — never executes plugin code)
            source_file = candidate.path / "plugin.py"
            if source_file.is_file():
                valid, errors = SecurityValidator.validate_source(str(source_file))
                if not valid:
                    logger.error(
                        f"Security validation failed for {candidate.path}: "
                        f"{'  '.join(errors)}"
                    )
                    return None

            # 4. Load module and class
            try:
                module = load_module_from_path(candidate.path)
                class_name = metadata.class_name or "Plugin"
                plugin_class = get_plugin_class(module, class_name)
            except (ImportError, FileNotFoundError, AttributeError, TypeError) as exc:
                logger.error(f"Loader failed for {candidate.path}: {exc}")
                return None

            # 5. Compatibility validation
            valid, errors = CompatibilityValidator.validate_class(plugin_class)
            if not valid:
                logger.error(
                    f"Compatibility validation failed for {candidate.path}: "
                    f"{'  '.join(errors)}"
                )
                return None

            # 6. Instantiate plugin
            try:
                plugin_instance = create_plugin_instance(plugin_class, metadata)
            except Exception as exc:
                logger.error(f"Plugin instantiation failed: {exc}")
                return None

            # 7. Register in passive registry
            entry = RegistryEntry(
                plugin_id=metadata.plugin_id,
                plugin_name=metadata.name,
                version=metadata.version,
                instance=plugin_instance,
                status=LOADED,
                loaded_at=datetime.now(timezone.utc),
            )
            self._registry.add(entry)

            # 8. Initialise plugin via contract
            try:
                if hasattr(plugin_instance, "initialize"):
                    plugin_instance.initialize()
                if hasattr(plugin_instance, "register"):
                    plugin_instance.register()
                self._registry.update_status(metadata.plugin_id, LOADED)
            except Exception as exc:
                self._registry.update_error(metadata.plugin_id, str(exc))
                logger.error(
                    f"Plugin registration failed for {metadata.plugin_id}: {exc}"
                )
                return None

            logger.info(f"Plugin loaded: {metadata.plugin_id}")
            return metadata.plugin_id

    # ------------------------------------------------------------------
    # Backward-compatible registration (for existing IPlugin usage)
    # ------------------------------------------------------------------

    def register_plugin(self, plugin: IPlugin) -> None:
        """
        Register a plugin instance directly (backward-compatible).

        Args:
            plugin: Plugin instance to register.

        Raises:
            ValueError: If plugin is already registered.
        """
        with self._lock:
            if self._registry.exists(plugin.plugin_id):
                raise ValueError(
                    f"Plugin {plugin.plugin_id} is already registered"
                )

            try:
                if hasattr(plugin, "initialize"):
                    plugin.initialize()
                plugin.register()

                entry = RegistryEntry(
                    plugin_id=plugin.plugin_id,
                    plugin_name=plugin.plugin_name,
                    version=plugin.version,
                    instance=plugin,
                    status=LOADED,
                    loaded_at=datetime.now(timezone.utc),
                )
                self._registry.add(entry)
                logger.info(
                    f"Plugin registered: {plugin.plugin_id}",
                    extra={"plugin_name": plugin.plugin_name},
                )
            except Exception as e:
                logger.error(
                    f"Failed to register plugin {plugin.plugin_id}: {e}"
                )
                raise

    def unregister_plugin(self, plugin_id: str) -> bool:
        """Unregister a plugin by ID."""
        with self._lock:
            entry = self._registry.find(plugin_id)
            if entry is None:
                logger.warning(f"Plugin not found for unregister: {plugin_id}")
                return False

            try:
                entry.instance.unregister()
                self._registry.remove(plugin_id)
                logger.info(f"Plugin unregistered: {plugin_id}")
                return True
            except Exception as e:
                logger.error(
                    f"Error during plugin unregister {plugin_id}: {e}"
                )
                self._registry.remove(plugin_id)
                return False

    # ------------------------------------------------------------------
    # Query API  (delegates to Registry)
    # ------------------------------------------------------------------

    def get_plugin(self, plugin_id: str) -> Optional[IPlugin]:
        """Get a plugin by ID."""
        with self._lock:
            return self._registry.get_instance(plugin_id)

    def list_plugins(self) -> List[IPlugin]:
        """List all registered plugins."""
        with self._lock:
            return [e.instance for e in self._registry.list()]

    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable a plugin."""
        with self._lock:
            entry = self._registry.find(plugin_id)
            if entry is None:
                return False
            logger.info(f"Plugin enabled: {plugin_id}")
            return True

    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin."""
        with self._lock:
            entry = self._registry.find(plugin_id)
            if entry is None:
                return False
            logger.info(f"Plugin disabled: {plugin_id}")
            return True

    # ------------------------------------------------------------------
    # Hot Reload  (delegates to app.plugins.hot_reload)
    # ------------------------------------------------------------------

    def reload_plugin(
        self,
        plugin_id: str,
        plugin_dir: Path,
        metadata: Optional[PluginMetadata] = None,
    ) -> Dict[str, Any]:
        """
        Hot-reload a plugin with snapshot rollback.

        Delegates to the HotReload module.

        Returns:
            {"success": bool, "error": Optional[str]}
        """
        with self._lock:
            entry = self._registry.find(plugin_id)
            if entry is None:
                return {"success": False, "error": f"Plugin {plugin_id} not found"}

            # Load fresh metadata if not provided
            if metadata is None:
                manifest_path = plugin_dir / "manifest.json"
                if manifest_path.is_file():
                    metadata = parse_manifest_json(manifest_path)
                else:
                    metadata = PluginMetadata(
                        plugin_id=plugin_id,
                        name=entry.plugin_name,
                        version=entry.version,
                        sdk_version="1.0",
                        class_name="Plugin",
                        entrypoint="plugin.py",
                    )

            success, new_entry, error = reload_plugin(
                plugin_dir, entry, metadata
            )

            if success:
                self._registry.add(new_entry)
                logger.info(f"Plugin {plugin_id} hot-reloaded successfully")
            else:
                logger.error(f"Plugin {plugin_id} hot-reload failed: {error}")

            return {"success": success, "error": error}

    # ------------------------------------------------------------------
    # Lifecycle orchestration
    # ------------------------------------------------------------------

    def startup_all(self) -> None:
        """Start all loaded plugins using PluginExecutor."""
        with self._lock:
            for entry in self._registry.list():
                executor = PluginExecutor(entry.plugin_id, SandboxPolicy())
                # B1 fix: on_start() is async; executor.start() expects Callable[[], None].
                # Wrap with asyncio.run() to create an event loop in the sandbox thread.
                if not executor.start(lambda: asyncio.run(entry.instance.on_start())):
                    self._registry.update_status(entry.plugin_id, FAILED)
                    logger.error(f"Failed to start plugin {entry.plugin_id}")
                    continue
                self._executors[entry.plugin_id] = executor
                self._registry.update_status(entry.plugin_id, RUNNING)
                logger.info(f"Plugin {entry.plugin_id} started via executor")

    def shutdown_all(self) -> None:
        """Stop all running plugins using PluginExecutor."""
        with self._lock:
            for plugin_id, executor in list(self._executors.items()):
                executor.stop()
                entry = self._registry.find(plugin_id)
                if entry and entry.status == RUNNING:
                    self._registry.update_status(plugin_id, STOPPED)
                    logger.info(f"Plugin {plugin_id} stopped via executor")
            self._executors.clear()

    # ------------------------------------------------------------------
    # Health reporting
    # ------------------------------------------------------------------

    def get_plugin_health(self, plugin_id: str) -> Dict[str, Any]:
        """Get health status of a plugin."""
        with self._lock:
            entry = self._registry.find(plugin_id)
            if entry is None:
                return {
                    "status": "unknown",
                    "plugin_id": plugin_id,
                    "error": "Plugin not found",
                }

            status = "healthy"
            if entry.status == FAILED:
                status = "unhealthy"
            elif entry.status == STOPPED:
                status = "stopped"

            return {
                "plugin_id": plugin_id,
                "plugin_name": entry.plugin_name,
                "status": status,
                "state": entry.status,
                "enabled": True,
                "version": entry.version,
                "loaded_at": (
                    entry.loaded_at.isoformat() if entry.loaded_at else None
                ),
                "last_error": entry.last_error,
                "error_count": 0,
            }

    def get_all_health(self) -> Dict[str, Any]:
        """Get health status of all plugins."""
        with self._lock:
            plugins_health = {}
            healthy = 0
            unhealthy = 0
            stopped = 0

            for entry in self._registry.list():
                health = self.get_plugin_health(entry.plugin_id)
                plugins_health[entry.plugin_id] = health

                s = health["status"]
                if s == "healthy":
                    healthy += 1
                elif s == "unhealthy":
                    unhealthy += 1
                elif s == "stopped":
                    stopped += 1

            return {
                "total": len(self._registry),
                "healthy": healthy,
                "unhealthy": unhealthy,
                "stopped": stopped,
                "plugins": plugins_health,
            }

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._registry)

    def __contains__(self, plugin_id: str) -> bool:
        with self._lock:
            return self._registry.exists(plugin_id)


# -----------------------------------------------------------------------
# Module-level factory (backward compatible)
# -----------------------------------------------------------------------

_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
