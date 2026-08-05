"""
Plugin Loader.

SINGLE import authority — the ONLY component permitted to use
``importlib``, ``importlib.util``, ``importlib.reload`` and ``sys.modules``.

Responsibility chain:
    filesystem path  ->  python module  ->  plugin class  ->  plugin instance

Does NOT perform validation.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Optional, Type

from app.plugins.manifest import PluginMetadata, parse_manifest_dict, parse_manifest_json


def load_module_from_path(plugin_dir: Path) -> ModuleType:
    """
    Dynamically import a Python module from a filesystem path.

    Only the Loader may manipulate ``importlib`` / ``sys.modules``.

    Args:
        plugin_dir: Directory containing ``plugin.py`` or similar.

    Returns:
        Loaded module object.
    """
    entrypoint = plugin_dir / "plugin.py"
    if not entrypoint.is_file():
        raise FileNotFoundError(f"No plugin.py in {plugin_dir}")

    module_name = f"tactical_plugins.{plugin_dir.name}"
    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, entrypoint)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {entrypoint}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def get_plugin_class(module: ModuleType, class_name: str) -> Type:
    """
    Extract the plugin class from an already-loaded module.

    Args:
        module: Loaded plugin module.
        class_name: Name of the class to instantiate (from manifest).

    Returns:
        The class object (not an instance).

    Raises:
        AttributeError: If the class is not found.
    """
    if not hasattr(module, class_name):
        raise AttributeError(
            f"Module '{module.__name__}' has no class '{class_name}'"
        )

    cls = getattr(module, class_name)
    if not isinstance(cls, type):
        raise TypeError(
            f"'{class_name}' in {module.__name__} is not a class"
        )

    return cls


def create_plugin_instance(
    plugin_class: Type,
    metadata: PluginMetadata,
    **extra_kwargs: Any,
) -> Any:
    """
    Instantiate a plugin class.

    Only the Loader may create plugin instances.

    BasePlugin expects ``context`` as its single constructor parameter.
    If the subclass overrides ``__init__`` with additional kwargs, they are
    forwarded here.

    Args:
        plugin_class: The plugin class (returned by get_plugin_class).
        metadata: Deserialized manifest metadata (available for subclasses).
        **extra_kwargs: Additional keyword arguments forwarded to __init__.

    Returns:
        A fully initialised plugin instance.
    """
    import inspect
    sig = inspect.signature(plugin_class.__init__)
    params = sig.parameters

    # BasePlugin.__init__ takes (self, context=None)
    # Build kwargs that match the signature
    kwargs: dict[str, Any] = {}
    for pname, param in params.items():
        if pname == "self":
            continue
        if pname == "context":
            kwargs["context"] = extra_kwargs.get("context")
        elif pname in extra_kwargs:
            kwargs[pname] = extra_kwargs[pname]

    return plugin_class(**kwargs)


def reload_module(module: ModuleType) -> ModuleType:
    """
    Hot-reload an already-loaded module.

    Returns:
        The reloaded module object.
    """
    return importlib.reload(module)


def unload_module(module: ModuleType) -> None:
    """
    Remove a module from ``sys.modules`` so it can be freshly imported later.

    This is the ONLY place modules may be removed from sys.modules.
    """
    if module.__name__ in sys.modules:
        del sys.modules[module.__name__]
