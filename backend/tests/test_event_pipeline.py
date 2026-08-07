import pytest
import threading
from backend.app.event_pipeline.event_pipeline import EventPipeline

class MockComponent:
    def __init__(self):
        self.calls = []
        
    def dispatch(self, event):
        self.calls.append(('dispatch', event))
        
    def save(self, event):
        self.calls.append(('save', event))
        
    def publish(self, event):
        self.calls.append(('publish', event))

class TestEventPipeline:
    def setup_method(self):
        self.pipeline = EventPipeline()
        self.dispatcher = MockComponent()
        self.repository = MockComponent()
        self.event_bus = MockComponent()
        self.pipeline.set_dispatcher(self.dispatcher)
        self.pipeline.set_repository(self.repository)
        self.pipeline.set_event_bus(self.event_bus)

    def test_process_order(self):
        order = []
        self.pipeline.add_before(lambda e: (order.append('before'), e)[1])
        self.pipeline.add_filter(lambda e: (order.append('filter'), True)[1])
        self.pipeline.add_after(lambda e: (order.append('after'), e)[1])
        
        self.pipeline.process({'type': 'test'})
        
        assert order == ['before', 'filter', 'after']
        assert len(self.dispatcher.calls) == 1
        assert len(self.repository.calls) == 1
        assert len(self.event_bus.calls) == 1

    def test_filter_stops_pipeline(self):
        self.pipeline.add_filter(lambda e: False)
        
        result = self.pipeline.process({'type': 'blocked'})
        
        assert result is False
        assert len(self.dispatcher.calls) == 0
        assert len(self.repository.calls) == 0
        assert len(self.event_bus.calls) == 0

    def test_before_middleware_modifies_event(self):
        self.pipeline.add_before(lambda e: {**e, 'modified': True})
        
        self.pipeline.process({'type': 'test'})
        
        assert self.dispatcher.calls[0][1]['modified'] is True

    def test_after_middleware_modifies_event(self):
        self.pipeline.add_after(lambda e: {**e, 'after': True})
        
        self.pipeline.process({'type': 'test'})
        
        assert self.repository.calls[0][1]['after'] is True

    def test_clear(self):
        self.pipeline.add_before(lambda e: e)
        self.pipeline.add_filter(lambda e: True)
        self.pipeline.add_after(lambda e: e)
        self.pipeline.clear()
        
        self.pipeline.process({'type': 'test'})
        
        assert len(self.dispatcher.calls) == 0
        assert len(self.repository.calls) == 0
        assert len(self.event_bus.calls) == 0

    def test_exception_in_filter(self):
        self.pipeline.add_filter(lambda e: (1/0))
        
        with pytest.raises(ZeroDivisionError):
            self.pipeline.process({'type': 'test'})

    def test_thread_safety(self):
        errors = []
        def add_filters():
            try:
                for _ in range(100):
                    self.pipeline.add_filter(lambda e: True)
            except Exception as ex:
                errors.append(ex)
                
        threads = [threading.Thread(target=add_filters) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
            
        assert len(errors) == 0
        assert len(self.pipeline._filters) == 1000
