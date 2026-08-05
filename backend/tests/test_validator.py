"""
Plugin Validator Tests.

Verifies the three split validators:
  ManifestValidator, CompatibilityValidator, SecurityValidator
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from app.plugins.validator.validator import (
    CompatibilityValidator,
    ManifestValidator,
    SecurityValidator,
)


# -----------------------------------------------------------------------
# Manifest Validator
# -----------------------------------------------------------------------

def test_manifest_validator_all_fields_present():
    metadata = MagicMock()
    metadata.plugin_id = "test"
    metadata.name = "Test"
    metadata.version = "1.0"
    metadata.sdk_version = "1.0"
    metadata.entrypoint = "plugin.py"
    metadata.class_name = "TestPlugin"

    valid, errors = ManifestValidator.validate(metadata)
    assert valid is True
    assert errors == []


def test_manifest_validator_missing_fields():
    metadata = MagicMock()
    metadata.plugin_id = ""
    metadata.name = "Test"
    metadata.version = ""
    metadata.sdk_version = "1.0"
    metadata.entrypoint = "plugin.py"
    metadata.class_name = ""

    valid, errors = ManifestValidator.validate(metadata)
    assert valid is False
    assert len(errors) == 3  # plugin_id, version, class_name
    assert any("plugin_id" in e for e in errors)
    assert any("version" in e for e in errors)


def test_manifest_validator_none_fields():
    metadata = MagicMock()
    metadata.plugin_id = None
    metadata.name = None
    metadata.version = None
    metadata.sdk_version = None
    metadata.entrypoint = None
    metadata.class_name = None

    valid, errors = ManifestValidator.validate(metadata)
    assert valid is False
    assert len(errors) == 6


# -----------------------------------------------------------------------
# Compatibility Validator
# -----------------------------------------------------------------------

def test_compatibility_validator_valid_baseplugin():
    from app.plugins.sdk.base import BasePlugin
    valid, errors = CompatibilityValidator.validate_class(BasePlugin)
    assert valid is True
    assert errors == []


def test_compatibility_validator_non_baseplugin():
    class NotAPlugin:
        pass

    valid, errors = CompatibilityValidator.validate_class(NotAPlugin)
    assert valid is False
    assert "does not inherit from BasePlugin" in errors[0]


def test_compatibility_validator_subclass_of_baseplugin():
    from app.plugins.sdk.base import BasePlugin

    class MyPlugin(BasePlugin):
        pass

    valid, errors = CompatibilityValidator.validate_class(MyPlugin)
    assert valid is True


def test_sdk_version_valid():
    valid, errors = CompatibilityValidator.validate_sdk_version("1.0", expected="1.0")
    assert valid is True


def test_sdk_version_invalid():
    valid, errors = CompatibilityValidator.validate_sdk_version("2.0", expected="1.0")
    assert valid is False
    assert "2.0" in errors[0]


# -----------------------------------------------------------------------
# Security Validator
# -----------------------------------------------------------------------

def test_security_validator_clean_source():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("""
import logging
from app.plugins.sdk.base import BasePlugin

class Plugin(BasePlugin):
    pass
""")
        f.flush()
        valid, errors = SecurityValidator.validate_source(f.name)
    assert valid is True


def test_security_validator_forbidden_import():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("""
import app.database
from app.pipeline import Pipeline

class Plugin:
    pass
""")
        f.flush()
        valid, errors = SecurityValidator.validate_source(f.name)
    assert valid is False
    assert len(errors) == 2


def test_security_validator_forbidden_from_import():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("""
from app.entity import Entity
""")
        f.flush()
        valid, errors = SecurityValidator.validate_source(f.name)
    assert valid is False
    assert "app.entity" in errors[0]


def test_security_validator_missing_file():
    valid, errors = SecurityValidator.validate_source("/nonexistent/file.py")
    assert valid is False
    assert "not found" in errors[0].lower()


def test_security_validator_syntax_error():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def broken(")
        f.flush()
        valid, errors = SecurityValidator.validate_source(f.name)
    assert valid is False
    assert "syntax" in errors[0].lower()
