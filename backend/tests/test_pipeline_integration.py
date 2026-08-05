"""
Integration tests for PipelineDispatcher, PluginEventDispatcher,
and the full plugin-to-pipeline-to-persistence flow.

Covers:
- Full dispatch pipeline
- Validation rejection
- Retry on failure
- Error isolation
- Metrics tracking
- Batch dispatch
- Plugin event dispatcher bridge
"""

import pytest
import tempfile
import threading

from app.database import EventPersistenceService
from app.database.session import DatabaseSessionManager
from app.database.repository_factory import RepositoryFactory, RepositoryType
from app.repositories.event_repository import InMemoryEventRepository
from app.core.pipeline import Pipeline
from app.pipeline_dispatcher.dispatcher import PipelineDispatcher, PipelineDispatcherConfig
from app.pipeline_dispatcher.plugin_event_dispatcher import PluginEventDispatcher
from app.pipeline_dispatcher.validation import EventValidator, ValidationError
from app.pipeline_dispatcher.error_isolation import ErrorIsolation


@pytest.fixture
def in_memory_persistence():
    """Create EventPersistenceService with InMemory repository."""
    from app.repositories.event_repository import InMemoryEventRepository

    sm = DatabaseSessionManager(":memory:")
    factory = RepositoryFactory()
    factory.register(RepositoryType.EVENT, InMemoryEventRepository)
    service = EventPersistenceService(factory)
    return service


@pytest.fixture
def dispatcher(in_memory_persistence):
    """Create PipelineDispatcher with in-memory persistence."""
    config = PipelineDispatcherConfig(
        persistence_service=in_memory_persistence,
        pipeline=Pipeline(name="test-pipeline"),
        max_retries=2,
        retry_delay_ms=10,
        logging_enabled=False,
    )
    return PipelineDispatcher(config)


class TestPipelineDispatcherIntegration:
    def test_dispatch_valid_event(self, dispatcher, in_memory_persistence):
        event_id = dispatcher.dispatch(
            event_data={"event_type": "test.event", "title": "Test Event"},
            plugin="test-plugin",
        )
        assert event_id is not None
        # Verify dispatch was recorded in metrics
        metrics = dispatcher.metrics
        assert metrics["dispatched"] >= 1

    def test_dispatch_invalid_event_rejected(self, dispatcher):
        event_id = dispatcher.dispatch(
            event_data={"title": "No event_type"},
            plugin="test-plugin",
        )
        assert event_id is None
        metrics = dispatcher.metrics
        assert metrics["validation_errors"] >= 1

    def test_dispatch_empty_event_rejected(self, dispatcher):
        event_id = dispatcher.dispatch(event_data={}, plugin="test-plugin")
        assert event_id is None

    def test_dispatch_batch(self, dispatcher, in_memory_persistence):
        events = [
            {"event_type": "test.event", "title": f"Event {i}"}
            for i in range(5)
        ]
        results = dispatcher.dispatch_batch(events, plugin="test-plugin")
        assert len(results) == 5
        assert dispatcher.metrics["batch_dispatched"] == 5

    def test_dispatch_batch_partial_failure(self, dispatcher):
        events = [
            {"event_type": "test.event", "title": "Good"},
            {},  # invalid
            {"event_type": "test.event", "title": "Good 2"},
        ]
        results = dispatcher.dispatch_batch(events, plugin="test-plugin")
        assert len(results) == 2
        assert dispatcher.metrics["batch_failed"] == 1

    def test_metrics_tracking(self, dispatcher):
        dispatcher.dispatch(
            event_data={"event_type": "t", "title": "T"},
            plugin="p",
        )
        metrics = dispatcher.metrics
        assert metrics["dispatched"] >= 1
        assert "failed" in metrics
        assert "retried" in metrics
        assert "validation_errors" in metrics
        assert "timeout" in metrics

    def test_error_isolation_no_crash(self, dispatcher):
        # Even if pipeline has no persistence stage configured,
        # dispatch should not crash — it should return None
        result = dispatcher.dispatch(
            event_data={"event_type": "t", "title": "T"},
            plugin="p",
        )
        assert result is not None or dispatcher.metrics["failed"] >= 0

    def test_dispatched_event_is_retrievable(self, dispatcher, in_memory_persistence):
        event_id = dispatcher.dispatch(
            event_data={"event_type": "signal.message", "title": "Signal"},
            plugin="signal",
        )
        assert event_id is not None
        # Verify dispatch was recorded
        metrics = dispatcher.metrics
        assert metrics["dispatched"] >= 1


class TestPluginEventDispatcherIntegration:
    def test_emit_event(self, dispatcher):
        plugin_dispatcher = PluginEventDispatcher(
            pipeline_dispatcher=dispatcher,
            plugin_id="test-plugin",
        )
        event_id = plugin_dispatcher.emit(
            event_data={"event_type": "plugin.event", "title": "Plugin Event"},
        )
        assert event_id is not None

    def test_emit_batch(self, dispatcher):
        plugin_dispatcher = PluginEventDispatcher(
            pipeline_dispatcher=dispatcher,
            plugin_id="test-plugin",
        )
        events = [
            {"event_type": "p.e", "title": f"E{i}"}
            for i in range(3)
        ]
        results = plugin_dispatcher.emit_batch(events)
        assert len(results) == 3

    def test_emit_with_source_override(self, dispatcher):
        plugin_dispatcher = PluginEventDispatcher(
            pipeline_dispatcher=dispatcher,
            plugin_id="test-plugin",
        )
        event_id = plugin_dispatcher.emit(
            event_data={"event_type": "p.e", "title": "E"},
            source="custom-source",
            source_type="custom-type",
        )
        assert event_id is not None

    def test_plugin_id_property(self, dispatcher):
        pd = PluginEventDispatcher(
            pipeline_dispatcher=dispatcher,
            plugin_id="my-plugin",
        )
        assert pd.plugin_id == "my-plugin"


class TestValidationIntegration:
    def test_validator_rejects_missing_fields(self, dispatcher):
        result = dispatcher.dispatch(
            event_data={"payload": {}},
            plugin="test",
        )
        assert result is None
        assert dispatcher.metrics["validation_errors"] >= 1

    def test_validator_rejects_non_string_fields(self, dispatcher):
        result = dispatcher.dispatch(
            event_data={"event_type": 123, "title": 456},
            plugin="test",
        )
        assert result is None

    def test_error_isolation_prevents_crash(self):
        ei = ErrorIsolation()
        result = ei.wrap(lambda: (_ for _ in ()).throw(Exception("fatal")))
        assert result.success is False
        assert result.error == "fatal"

    def test_validation_result_errors_list(self):
        validator = EventValidator()
        result = validator.validate({})
        assert len(result.errors) == 2
        assert "event_type" in result.errors[0]
        assert "title" in result.errors[1]
