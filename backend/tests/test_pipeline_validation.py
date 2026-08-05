"""
Tests for EventValidator and ValidationError.

Covers:
- Required fields validation
- Field type validation
- Event size limits
- Batch validation
- ValidationError raising
"""

import pytest
from app.pipeline_dispatcher.validation import (
    EventValidator,
    ValidationError,
    ValidationResult,
)


class TestValidationResult:
    def test_valid_by_default(self):
        result = ValidationResult()
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_add_error_marks_invalid(self):
        result = ValidationResult()
        result.add_error("missing field")
        assert result.valid is False
        assert "missing field" in result.errors

    def test_bool_true_when_valid(self):
        assert bool(ValidationResult()) is True

    def test_bool_false_when_invalid(self):
        r = ValidationResult()
        r.add_error("err")
        assert bool(r) is False


class TestEventValidator:
    def test_valid_event_passes(self):
        validator = EventValidator()
        result = validator.validate({"event_type": "test", "title": "Test Event"})
        assert result.valid is True

    def test_missing_event_type_fails(self):
        validator = EventValidator()
        result = validator.validate({"title": "Test Event"})
        assert result.valid is False
        assert any("event_type" in e for e in result.errors)

    def test_missing_title_fails(self):
        validator = EventValidator()
        result = validator.validate({"event_type": "test"})
        assert result.valid is False
        assert any("title" in e for e in result.errors)

    def test_missing_both_fields_fails(self):
        validator = EventValidator()
        result = validator.validate({"payload": {}})
        assert result.valid is False
        assert len(result.errors) == 2

    def test_non_string_event_type_fails(self):
        validator = EventValidator()
        result = validator.validate({"event_type": 123, "title": "Test"})
        assert result.valid is False
        assert any("must be a string" in e for e in result.errors)

    def test_event_type_too_long_fails(self):
        validator = EventValidator()
        long_type = "x" * 501
        result = validator.validate({"event_type": long_type, "title": "Test"})
        assert result.valid is False
        assert any("exceeds maximum length" in e for e in result.errors)

    def test_title_too_long_fails(self):
        validator = EventValidator()
        long_title = "x" * 501
        result = validator.validate({"event_type": "test", "title": long_title})
        assert result.valid is False
        assert any("exceeds maximum length" in e for e in result.errors)

    def test_non_dict_payload_warns(self):
        validator = EventValidator()
        result = validator.validate({"event_type": "test", "title": "Test", "payload": "not a dict"})
        assert result.valid is True  # warnings don't invalidate
        assert len(result.warnings) == 1

    def test_event_exceeds_max_size(self):
        validator = EventValidator(max_event_size=100)
        large = {"event_type": "test", "title": "T" * 200}
        result = validator.validate(large)
        assert result.valid is False
        assert any("exceeds maximum size" in e for e in result.errors)

    def test_custom_required_fields(self):
        validator = EventValidator(required_fields=("event_type", "title", "source"))
        result = validator.validate({"event_type": "test", "title": "Test"})
        assert result.valid is False
        assert any("source" in e for e in result.errors)

    def test_validate_required_raises_on_failure(self):
        validator = EventValidator()
        with pytest.raises(ValidationError):
            validator.validate_required({"title": "Test"})

    def test_validate_required_no_error_on_pass(self):
        validator = EventValidator()
        # Should not raise
        validator.validate_required({"event_type": "test", "title": "Test"})

    def test_plugin_label_in_validation(self):
        validator = EventValidator()
        result = validator.validate({"event_type": "test", "title": "Test"}, plugin="signal")
        assert result.valid is True

    def test_empty_event_data_fails(self):
        validator = EventValidator()
        result = validator.validate({})
        assert result.valid is False
        assert len(result.errors) == 2  # missing event_type and title
