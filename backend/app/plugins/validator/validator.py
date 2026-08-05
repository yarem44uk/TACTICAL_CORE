"""
Plugin Validator.

Split into three independent stages:
  ManifestValidator  — required fields
  CompatibilityValidator — BasePlugin inheritance
  SecurityValidator — forbidden imports

Each validator has one responsibility. No God Validator.
"""

from __future__ import annotations

import ast
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Manifest Validator
# ---------------------------------------------------------------------------

# Fields required by the WO-010-005-R1 Manifest Standard
REQUIRED_MANIFEST_FIELDS = ("plugin_id", "name", "version", "sdk_version", "entrypoint", "class_name")


class ManifestValidator:
    """Validates that manifest data contains all required fields."""

    @staticmethod
    def validate(metadata: object) -> Tuple[bool, List[str]]:
        """
        Check that *metadata* (any object with attribute-style access)
        has all required manifest fields populated.

        Returns:
            (is_valid, list_of_errors)
        """
        errors: List[str] = []

        for attr in REQUIRED_MANIFEST_FIELDS:
            value = getattr(metadata, attr, None)
            if not value:
                errors.append(f"Missing required field: {attr}")

        return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Compatibility Validator
# ---------------------------------------------------------------------------

class CompatibilityValidator:
    """Validates that a plugin class is compatible with the Plugin SDK."""

    # Path to the BasePlugin class — loaded lazily to keep the module importable
    # without the SDK being fully built.
    _base_plugin: Optional[type] = None

    @classmethod
    def _get_base_plugin(cls) -> type:
        if cls._base_plugin is None:
            from app.plugins.sdk.base import BasePlugin  # noqa: PLC0415
            cls._base_plugin = BasePlugin
        return cls._base_plugin

    @staticmethod
    def validate_class(plugin_class: type) -> Tuple[bool, List[str]]:
        """
        Verify that *plugin_class* inherits from BasePlugin.

        Returns:
            (is_valid, list_of_errors)
        """
        errors: List[str] = []
        base = CompatibilityValidator._get_base_plugin()

        if not issubclass(plugin_class, base):
            errors.append(
                f"Class '{plugin_class.__name__}' does not inherit from BasePlugin"
            )

        return len(errors) == 0, errors

    @staticmethod
    def validate_sdk_version(sdk_version: str, expected: str = "1.0") -> Tuple[bool, List[str]]:
        """
        Verify that the plugin's declared SDK version is compatible.

        Returns:
            (is_valid, list_of_errors)
        """
        errors: List[str] = []
        if sdk_version != expected:
            errors.append(
                f"SDK version '{sdk_version}' does not match expected '{expected}'"
            )
        return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Security Validator
# ---------------------------------------------------------------------------

FORBIDDEN_IMPORTS = (
    "app.database",
    "app.pipeline",
    "app.entity",
    "app.event_engine",
)


class SecurityValidator:
    """
    Rejects plugins that import protected layers.

    Uses AST analysis — **never** executes plugin code.
    """

    @staticmethod
    def validate_source(source_path: str) -> Tuple[bool, List[str]]:
        """
        Analyse *source_path* for forbidden imports via AST.

        Args:
            source_path: Path to the plugin Python file.

        Returns:
            (is_valid, list_of_errors)
        """
        errors: List[str] = []
        try:
            with open(source_path, "r", encoding="utf-8") as fh:
                source = fh.read()
            tree = ast.parse(source, filename=source_path)
        except SyntaxError as exc:
            return False, [f"Syntax error: {exc}"]
        except FileNotFoundError:
            return False, [f"Source file not found: {source_path}"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden(alias.name):
                        errors.append(f"Forbidden import: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and _is_forbidden(node.module):
                    errors.append(f"Forbidden import from: {node.module}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_loaded_module(module) -> Tuple[bool, List[str]]:
        """
        Check already-loaded module's namespace for forbidden imports.

        Returns:
            (is_valid, list_of_errors)
        """
        errors: List[str] = []
        for name in dir(module):
            obj = getattr(module, name, None)
            if hasattr(obj, "__module__") and obj.__module__:
                if _is_forbidden(obj.__module__):
                    errors.append(f"Forbidden reference via {name} ({obj.__module__})")
        return len(errors) == 0, errors


def _is_forbidden(module_name: str) -> bool:
    """Check if a module name starts with a forbidden prefix."""
    return any(module_name.startswith(prefix) for prefix in FORBIDDEN_IMPORTS)
