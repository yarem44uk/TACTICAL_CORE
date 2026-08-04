"""
Plugin Validator.

Validates plugins before loading and registration.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.contracts.plugin import IPlugin
from app.plugins.exceptions import PluginValidationError
from app.plugins.sdk.base import BasePlugin
from app.plugins.discovery.plugin_discovery import DiscoveredPlugin
from app.plugins.loader.plugin_loader import LoadedPlugin

logger = logging.getLogger(__name__)

# Valid characters for plugin_id
VALID_PLUGIN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$')

# Required fields in manifest
REQUIRED_MANIFEST_FIELDS = {"id", "name", "version"}

# Standard capabilities
STANDARD_CAPABILITIES = {
    "events:publish",
    "events:subscribe",
    "database:read",
    "database:write",
    "filesystem:read",
    "filesystem:write",
    "network:http",
    "network:websocket",
    "microphone:read",
    "camera:read",
    "messages:send",
    "messages:receive",
    "code:execute",
    "logs:view",
    "config:modify",
    "plugins:manage",
    "*",
}


@dataclass
class ValidationResult:
    """Result of plugin validation."""

    is_valid: bool
    plugin_id: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_valid": self.is_valid,
            "plugin_id": self.plugin_id,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class PluginValidator:
    """
    Validates plugins before loading and registration.

    Checks:
    - Manifest format and required fields
    - Plugin ID format
    - BasePlugin inheritance
    - SDK compatibility
    - Capability validation

    Usage:
        >>> validator = PluginValidator()
        >>> result = validator.validate_manifest(discovered)
        >>> if result.is_valid:
        ...     loaded = loader.load(discovered)
    """

    def __init__(self) -> None:
        """Initialize the plugin validator."""
        self._errors: List[str] = []
        self._warnings: List[str] = []

    def validate_manifest(self, discovered: DiscoveredPlugin) -> ValidationResult:
        """
        Validate plugin manifest.

        Args:
            discovered: DiscoveredPlugin to validate.

        Returns:
            ValidationResult with validation status.
        """
        self._errors = []
        self._warnings = []

        # Check required fields
        if not discovered.plugin_id:
            self._errors.append("Plugin ID is required")

        if not discovered.plugin_name:
            self._errors.append("Plugin name is required")

        if not discovered.version:
            self._errors.append("Plugin version is required")

        # Validate plugin_id format
        if discovered.plugin_id and not self._is_valid_plugin_id(discovered.plugin_id):
            self._errors.append(f"Invalid plugin ID format: {discovered.plugin_id}")

        # Validate version format (semver-like)
        if discovered.version and not self._is_valid_version(discovered.version):
            self._warnings.append(f"Non-standard version format: {discovered.version}")

        # Check for required manifest file
        if not discovered.has_manifest_json and not discovered.has_plugin_py:
            self._warnings.append("No manifest file found (manifest.json or plugin.py)")

        return ValidationResult(
            is_valid=len(self._errors) == 0,
            plugin_id=discovered.plugin_id or "unknown",
            errors=self._errors,
            warnings=self._warnings,
        )

    def validate_base_plugin(self, loaded: LoadedPlugin) -> ValidationResult:
        """
        Validate that a loaded plugin is a valid BasePlugin.

        Args:
            loaded: LoadedPlugin to validate.

        Returns:
            ValidationResult with validation status.
        """
        self._errors = []
        self._warnings = []

        if loaded.error:
            self._errors.append(f"Plugin failed to load: {loaded.error}")
            return ValidationResult(
                is_valid=False,
                plugin_id=loaded.discovered.plugin_id,
                errors=self._errors,
                warnings=self._warnings,
            )

        if not isinstance(loaded.plugin, (BasePlugin, IPlugin)):
            self._errors.append("Plugin is not an instance of BasePlugin or IPlugin")

        # Check plugin_id
        if not loaded.plugin.plugin_id:
            self._errors.append("Plugin has no plugin_id")

        # Check plugin_name
        if not loaded.plugin.plugin_name:
            self._errors.append("Plugin has no plugin_name")

        return ValidationResult(
            is_valid=len(self._errors) == 0,
            plugin_id=loaded.discovered.plugin_id,
            errors=self._errors,
            warnings=self._warnings,
        )

    def validate_sdk_compatibility(self, loaded: LoadedPlugin) -> ValidationResult:
        """
        Validate SDK compatibility.

        Args:
            loaded: LoadedPlugin to validate.

        Returns:
            ValidationResult with validation status.
        """
        self._errors = []
        self._warnings = []

        if not loaded.plugin:
            self._errors.append("Plugin instance is None")
            return ValidationResult(
                is_valid=False,
                plugin_id=loaded.discovered.plugin_id,
                errors=self._errors,
                warnings=self._warnings,
            )

        # Check if plugin has required methods
        required_methods = ["on_load", "on_start", "on_stop"]
        for method in required_methods:
            if not hasattr(loaded.plugin, method):
                self._errors.append(f"Plugin missing required method: {method}")

        # Check if plugin has optional but recommended methods
        recommended_methods = ["on_health_check", "on_reload"]
        for method in recommended_methods:
            if not hasattr(loaded.plugin, method):
                self._warnings.append(f"Plugin missing recommended method: {method}")

        return ValidationResult(
            is_valid=len(self._errors) == 0,
            plugin_id=loaded.discovered.plugin_id,
            errors=self._errors,
            warnings=self._warnings,
        )

    def validate_capabilities(self, discovered: DiscoveredPlugin) -> ValidationResult:
        """
        Validate plugin capabilities.

        Args:
            discovered: DiscoveredPlugin to validate.

        Returns:
            ValidationResult with validation status.
        """
        self._errors = []
        self._warnings = []

        # Check permissions
        for permission in discovered.permissions:
            if permission not in STANDARD_CAPABILITIES:
                self._warnings.append(f"Non-standard capability: {permission}")

        return ValidationResult(
            is_valid=True,  # Non-standard capabilities are warnings, not errors
            plugin_id=discovered.plugin_id,
            errors=self._errors,
            warnings=self._warnings,
        )

    def validate_full(self, discovered: DiscoveredPlugin, loaded: LoadedPlugin) -> ValidationResult:
        """
        Perform full validation of a plugin.

        Args:
            discovered: DiscoveredPlugin to validate.
            loaded: LoadedPlugin to validate.

        Returns:
            ValidationResult with combined validation status.
        """
        # Run all validations
        manifest_result = self.validate_manifest(discovered)
        base_result = self.validate_base_plugin(loaded)
        sdk_result = self.validate_sdk_compatibility(loaded)
        capabilities_result = self.validate_capabilities(discovered)

        # Combine results
        all_errors = (
            manifest_result.errors +
            base_result.errors +
            sdk_result.errors +
            capabilities_result.errors
        )
        all_warnings = (
            manifest_result.warnings +
            base_result.warnings +
            sdk_result.warnings +
            capabilities_result.warnings
        )

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            plugin_id=discovered.plugin_id,
            errors=all_errors,
            warnings=all_warnings,
        )

    def _is_valid_plugin_id(self, plugin_id: str) -> bool:
        """Validate plugin ID format."""
        return bool(VALID_PLUGIN_ID_PATTERN.match(plugin_id))

    def _is_valid_version(self, version: str) -> bool:
        """Validate version format (semver-like)."""
        # Simple check: must have at least major.minor
        return bool(re.match(r'^\d+\.\d+', version))
