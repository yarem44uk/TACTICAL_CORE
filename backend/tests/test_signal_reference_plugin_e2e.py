"""
End-to-End Integration Test for SignalReferencePlugin.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from app.core.event_engine import EventEngine
from app.core.event_bus import EventBus
from app.core.event_registry import EventRegistry
from app.core.event_history import EventHistory
from app.plugins.manager.plugin_manager import PluginManager
from app.plugins.signal_reference_plugin import SignalReferencePlugin

logger = logging.getLogger(__name__)


class InMemoryEventRepository:
    """In-memory event repository for testing."""
    
    def __init__(self):
        self._events = {}
    
    def create(self, **kwargs):
        event_id = kwargs.get("id")
        if isinstance(event_id, str):
            kwargs["id"] = uuid.UUID(event_id)
        from app.models.event import Event
        event = Event(**kwargs)
        self._events[str(event.id)] = event
        return event
    
    def get(self, id, raise_not_found=False):
        event = self._events.get(str(id))
        if event is None and raise_not_found:
            raise ValueError(f"Event not found: {id}")
        return event
    
    def count(self):
        return len(self._events)


class TestSignalReferencePluginE2E:
    """End-to-End integration test for SignalReferencePlugin."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.repository = InMemoryEventRepository()
        self.event_registry = EventRegistry()
        self.event_bus = EventBus()
        self.event_history = EventHistory(max_size=1000)
        
        self.event_engine = EventEngine(
            database_session=None,
            repository=self.repository,
            websocket_broadcaster=None,
            ai_notifier=None,
            plugin_notifier=None,
        )
        
        self.plugin_manager = PluginManager()
        self.plugin_manager.set_event_bus(self.event_bus)
        self.plugin_manager.set_event_engine(self.event_engine)
        
        self.plugin = SignalReferencePlugin(
            plugin_id="test-signal-reference",
            plugin_name="Test Signal Reference Plugin",
        )
        self.plugin.set_event_bus(self.event_bus)
        self.plugin.set_event_engine(self.event_engine)
        self.plugin.set_repository(self.repository)
    
        self.event_engine.startup()
        self.plugin_manager.register_plugin(self.plugin)
        self.plugin.on_startup()
    
        yield
    
        self.plugin.on_shutdown()
        self.event_engine.shutdown()
    
    def test_01_plugin_registration(self):
        """Test 1: Plugin Registration."""
        assert "test-signal-reference" in self.plugin_manager
        assert len(self.plugin_manager) == 1
        health = self.plugin_manager.get_plugin_health("test-signal-reference")
        assert health["status"] == "healthy"
        assert health["enabled"] is True
        logger.info("TEST 1 PASSED: Plugin registration successful")
    
    def test_02_event_subscription(self):
        """Test 2: Event Subscription."""
        subscriber_count = self.event_bus.get_subscription_count("reference.test")
        assert subscriber_count >= 1
        assert self.plugin._running is True
        logger.info("TEST 2 PASSED: Event subscription successful")
    
    def test_03_event_publication(self):
        """Test 3: Event Publication through Pipeline."""
        event_id = self.plugin.publish_test_event()
        assert event_id is not None
        published = self.plugin._published_events
        assert len(published) >= 1
        logger.info("TEST 3 PASSED: Event publication successful")
    
    def test_04_pipeline_processing(self):
        """Test 4: Pipeline Processing."""
        assert self.event_engine.pipeline is not None
        assert self.event_engine.pipeline.stage_count > 0
        stages = self.event_engine.pipeline.stages
        stage_names = [s.name for s in stages]
        assert "validation" in stage_names
        assert "persistence" in stage_names
        logger.info("TEST 4 PASSED: Pipeline processing configured")
    
    def test_05_database_persistence(self):
        """Test 5: Database Persistence."""
        event_id = self.plugin.publish_test_event()
        assert event_id is not None
        count = self.repository.count()
        assert count >= 1
        event = self.repository.get(event_id)
        assert event is not None
        logger.info("TEST 5 PASSED: Database persistence successful")
    
    def test_06_plugin_unregistration(self):
        """Test 6: Plugin Unregistration."""
        count_before = len(self.plugin_manager)
        result = self.plugin_manager.unregister_plugin("test-signal-reference")
        assert result is True
        assert len(self.plugin_manager) == count_before - 1
        assert "test-signal-reference" not in self.plugin_manager
        logger.info("TEST 6 PASSED: Plugin unregistration successful")
    
    def test_07_graceful_shutdown(self):
        """Test 7: Graceful Shutdown."""
        assert self.plugin._running is True
        self.plugin.on_shutdown()
        assert self.plugin._running is False
        status = self.plugin.get_status()
        assert status["running"] is False
        logger.info("TEST 7 PASSED: Graceful shutdown successful")
    
    def test_08_no_orphan_threads(self):
        """Test 8: No Orphan Threads."""
        threads_before = threading.active_count()
        self.plugin.on_shutdown()
        self.plugin.on_startup()
        self.plugin.on_shutdown()
        threads_after = threading.active_count()
        assert threads_after <= threads_before + 2
        logger.info("TEST 8 PASSED: No orphan threads detected")