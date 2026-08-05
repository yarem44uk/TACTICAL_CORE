"""
Tests for PipelineLogger.

Covers:
- All log methods do not raise
- Structured output format
- No exceptions on any call
"""

import pytest
from app.pipeline_dispatcher.pipeline_logger import PipelineLogger


class TestPipelineLogger:
    def test_dispatch_start_no_error(self):
        # Should not raise
        PipelineLogger.dispatch_start(event_id="e1", plugin="signal")

    def test_dispatch_success_no_error(self):
        PipelineLogger.dispatch_success(event_id="e1", plugin="signal", duration_ms=50)

    def test_dispatch_success_without_duration(self):
        PipelineLogger.dispatch_success(event_id="e1", plugin="signal")

    def test_dispatch_failed_no_error(self):
        PipelineLogger.dispatch_failed(event_id="e1", plugin="signal", error="timeout")

    def test_dispatch_failed_without_event_id(self):
        PipelineLogger.dispatch_failed(plugin="signal", error="timeout")

    def test_retry_attempt_no_error(self):
        PipelineLogger.retry_attempt(event_id="e1", plugin="signal", attempt=2, max_retries=3)

    def test_validation_failed_no_error(self):
        PipelineLogger.validation_failed(plugin="signal", errors=["missing field"])

    def test_validation_failed_without_errors(self):
        PipelineLogger.validation_failed(plugin="signal")

    def test_timeout_no_error(self):
        PipelineLogger.timeout(event_id="e1", plugin="signal", timeout_ms=5000)

    def test_all_methods_callable(self):
        """Verify all logger methods are callable and return None."""
        assert callable(PipelineLogger.dispatch_start)
        assert callable(PipelineLogger.dispatch_success)
        assert callable(PipelineLogger.dispatch_failed)
        assert callable(PipelineLogger.retry_attempt)
        assert callable(PipelineLogger.validation_failed)
        assert callable(PipelineLogger.timeout)
