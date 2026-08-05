"""
Event Validation for Pipeline Dispatcher.

Validates event data before it enters the pipeline.
Ensures data integrity and format compliance.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when event data fails validation."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.field = field


class ValidationResult:
    """Result of event validation."""

    __slots__ = ("valid", "errors", "warnings")

    def __init__(self) -> None:
        self.valid: bool = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, message: str) -> None:
        self.valid = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def __bool__(self) -> bool:
        return self.valid


class EventValidator:
    """
    Validates event data before pipeline dispatch.

    Checks:
    - Required fields presence
    - Field type validation
    - Event size limits
    - Plugin identification
    """

    REQUIRED_FIELDS: tuple[str, ...] = ("event_type", "title")
    MAX_EVENT_SIZE: int = 10_000  # characters
    MAX_FIELD_LENGTH: int = 500

    def __init__(
        self,
        required_fields: Optional[tuple[str, ...]] = None,
        max_event_size: int = 10_000,
        max_field_length: int = 500,
    ) -> None:
        self.required_fields = required_fields or self.REQUIRED_FIELDS
        self.max_event_size = max_event_size
        self.max_field_length = max_field_length

    def validate(self, event_data: Dict[str, Any], plugin: Optional[str] = None) -> ValidationResult:
        """
        Validate event data.

        Args:
            event_data: Event data dictionary.
            plugin: Optional plugin identifier for logging.

        Returns:
            ValidationResult with errors if invalid.
        """
        result = ValidationResult()
        plugin_label = f"plugin={plugin}: " if plugin else ""

        # Check event size
        event_str = str(event_data)
        if len(event_str) > self.max_event_size:
            result.add_error(f"Event exceeds maximum size ({self.max_event_size} chars)")
            logger.warning(f"EventValidator: {plugin_label}event too large")

        # Check required fields
        for field_name in self.required_fields:
            if field_name not in event_data:
                result.add_error(f"Missing required field: {field_name}")

        # Validate field types
        for field_name in ("event_type", "title"):
            if field_name in event_data:
                value = event_data[field_name]
                if not isinstance(value, str):
                    result.add_error(f"Field '{field_name}' must be a string")
                elif len(value) > self.max_field_length:
                    result.add_error(f"Field '{field_name}' exceeds maximum length ({self.max_field_length})")

        # Check payload
        if "payload" in event_data:
            payload = event_data["payload"]
            if not isinstance(payload, dict):
                result.add_warning("Field 'payload' should be a dictionary")

        if not result.valid:
            logger.warning(
                f"EventValidator: {plugin_label}validation failed: {result.errors}"
            )

        return result

    def validate_required(self, event_data: Dict[str, Any], plugin: Optional[str] = None) -> None:
        """
        Validate event data, raising ValidationError if invalid.

        Args:
            event_data: Event data dictionary.
            plugin: Optional plugin identifier.

        Raises:
            ValidationError: If validation fails.
        """
        result = self.validate(event_data, plugin)
        if not result.valid:
            raise ValidationError(
                f"Event validation failed: {'; '.join(result.errors)}"
            )
