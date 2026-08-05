"""
Tests for ErrorIsolation.

Covers:
- Successful operation wrapping
- Exception isolation
- Batch operations
- Error logging
"""

import pytest
from app.pipeline_dispatcher.error_isolation import ErrorIsolation, ErrorIsolationResult


class TestErrorIsolationResult:
    def test_success_result(self):
        r = ErrorIsolationResult(success=True, result="data")
        assert r.success is True
        assert r.result == "data"
        assert r.error is None
        assert bool(r) is True

    def test_failure_result(self):
        r = ErrorIsolationResult(success=False, error="boom")
        assert r.success is False
        assert r.result is None
        assert r.error == "boom"
        assert bool(r) is False


class TestErrorIsolation:
    def test_wrap_success(self):
        ei = ErrorIsolation()
        result = ei.wrap(lambda: "ok")
        assert result.success is True
        assert result.result == "ok"

    def test_wrap_exception_isolated(self):
        ei = ErrorIsolation()
        result = ei.wrap(lambda: 1 / 0)
        assert result.success is False
        assert result.error is not None
        assert "division by zero" in result.error

    def test_wrap_with_plugin_label(self):
        ei = ErrorIsolation()
        result = ei.wrap(lambda: "ok", plugin="signal")
        assert result.success is True

    def test_wrap_exception_does_not_crash(self):
        ei = ErrorIsolation()
        # Should not raise
        result = ei.wrap(lambda: (_ for _ in ()).throw(RuntimeError("crash")))
        assert result.success is False

    def test_wrap_batch_all_success(self):
        ei = ErrorIsolation()
        results = ei.wrap_batch([lambda: 1, lambda: 2, lambda: 3])
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_wrap_batch_partial_failure(self):
        ei = ErrorIsolation()
        results = ei.wrap_batch([lambda: 1, lambda: 1 / 0, lambda: 3])
        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    def test_wrap_with_context(self):
        ei = ErrorIsolation()
        result = ei.wrap(lambda: "ok", plugin="test", context="validation")
        assert result.success is True

    def test_custom_log_level(self):
        ei = ErrorIsolation(log_level="ERROR")
        result = ei.wrap(lambda: 1 / 0)
        assert result.success is False
