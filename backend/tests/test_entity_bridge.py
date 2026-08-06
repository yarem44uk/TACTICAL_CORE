"""
EntityBridge Unit Tests.

Tests the EntityBridge component in isolation, verifying:
- EntityUpdateRequest construction
- IEntityBridge interface compliance
- Best-effort error handling (pipeline never broken)
- EntityManager delegation
- Logging behavior on failure

Author: Tactical Core Engineering Team
Version: 1.0
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.entity_bridge import EntityBridge
from app.entity_bridge.interfaces import EntityUpdateRequest, IEntityBridge, IEntityManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_entity_manager() -> IEntityManager:
    """Provide a mocked IEntityManager."""
    mgr = MagicMock(spec=IEntityManager)
    mgr.apply_update.return_value = True
    return mgr  # type: ignore[return-value]


@pytest.fixture
def bridge(mock_entity_manager: IEntityManager) -> EntityBridge:
    """Provide an EntityBridge wired to a mock entity manager."""
    return EntityBridge(entity_manager=mock_entity_manager)


@pytest.fixture
def entity_event() -> dict:
    """A minimal event that triggers an entity update."""
    return {
        "entity_type": "source",
        "entity_id": "src-001",
        "entity": {
            "name": "Test Source",
            "status": "active",
        },
    }


@pytest.fixture
def plain_event() -> dict:
    """An event with no entity information — should be skipped."""
    return {
        "category": "signal",
        "payload": "some raw data",
    }


# ---------------------------------------------------------------------------
# IEntityBridge interface
# ---------------------------------------------------------------------------


class TestIEntityBridgeInterface:
    """Verify EntityBridge implements IEntityBridge correctly."""

    def test_bridge_is_instance_of_interface(self, bridge: EntityBridge) -> None:
        assert isinstance(bridge, IEntityBridge)

    def test_bridge_has_process_event_method(self, bridge: EntityBridge) -> None:
        assert hasattr(bridge, "process_event")
        assert callable(bridge.process_event)


# ---------------------------------------------------------------------------
# EntityUpdateRequest construction
# ---------------------------------------------------------------------------


class TestEntityUpdateRequest:
    """Verify EntityUpdateRequest dataclass behavior."""

    def test_creation_sets_fields(self) -> None:
        req = EntityUpdateRequest(
            entity_type="source",
            entity_id="s-1",
            updates={"name": "X"},
            source_event_id="evt-42",
            correlation_id="corr-1",
        )
        assert req.entity_type == "source"
        assert req.entity_id == "s-1"
        assert req.updates == {"name": "X"}
        assert req.source_event_id == "evt-42"
        assert req.correlation_id == "corr-1"
        assert req.request_id is not None

    def test_to_entity_manager_params(self) -> None:
        req = EntityUpdateRequest(
            entity_type="asset",
            entity_id="a-2",
            updates={"status": "active"},
        )
        params = req.to_entity_manager_params()
        assert params["entity_type"] == "asset"
        assert params["entity_id"] == "a-2"
        assert params["updates"] == {"status": "active"}

    def test_updates_defaults_to_empty_dict(self) -> None:
        req = EntityUpdateRequest(
            entity_type="source",
            entity_id="s-1",
            updates={},
        )
        assert req.updates == {}


# ---------------------------------------------------------------------------
# process_event — happy path
# ---------------------------------------------------------------------------


class TestProcessEventHappyPath:
    """Verify correct delegation when entity data is present."""

    def test_process_event_calls_apply_update(
        self,
        bridge: EntityBridge,
        mock_entity_manager: IEntityManager,
        entity_event: dict,
    ) -> None:
        bridge.process_event(
            event_data=entity_event,
            event_id="evt-1",
            correlation_id="corr-1",
        )
        mock_entity_manager.apply_update.assert_called_once()

    def test_process_event_passes_correct_params(
        self,
        bridge: EntityBridge,
        mock_entity_manager: IEntityManager,
        entity_event: dict,
    ) -> None:
        bridge.process_event(
            event_data=entity_event,
            event_id="evt-1",
            correlation_id="corr-1",
        )
        call_kwargs = mock_entity_manager.apply_update.call_args.kwargs
        assert call_kwargs["entity_type"] == "source"
        assert call_kwargs["entity_id"] == "src-001"

    def test_process_event_no_entity_data_skips(
        self,
        bridge: EntityBridge,
        mock_entity_manager: IEntityManager,
        plain_event: dict,
    ) -> None:
        bridge.process_event(
            event_data=plain_event,
            event_id="evt-2",
        )
        mock_entity_manager.apply_update.assert_not_called()


# ---------------------------------------------------------------------------
# process_event — failure policy
# ---------------------------------------------------------------------------


class TestProcessEventFailurePolicy:
    """Verify best-effort: exceptions are logged, never propagated."""

    def test_entity_manager_raises_is_swallowed(
        self,
        mock_entity_manager: IEntityManager,
        entity_event: dict,
    ) -> None:
        mock_entity_manager.apply_update.side_effect = RuntimeError("db down")
        bridge = EntityBridge(entity_manager=mock_entity_manager)

        # Must not raise
        bridge.process_event(
            event_data=entity_event,
            event_id="evt-3",
        )

    def test_entity_manager_false_is_not_raised(
        self,
        mock_entity_manager: IEntityManager,
        entity_event: dict,
    ) -> None:
        mock_entity_manager.apply_update.return_value = False
        bridge = EntityBridge(entity_manager=mock_entity_manager)

        # Must not raise
        bridge.process_event(
            event_data=entity_event,
            event_id="evt-4",
        )

    def test_exception_is_logged(
        self,
        mock_entity_manager: IEntityManager,
        entity_event: dict,
    ) -> None:
        mock_entity_manager.apply_update.side_effect = RuntimeError("fail")
        bridge = EntityBridge(entity_manager=mock_entity_manager)

        with patch.object(
            logging.getLogger("app.entity_bridge.entity_bridge"),
            "exception",
        ) as mock_log:
            bridge.process_event(
                event_data=entity_event,
                event_id="evt-5",
            )
            mock_log.assert_called()


# ---------------------------------------------------------------------------
# _build_requests
# ---------------------------------------------------------------------------


class TestBuildRequests:
    """Verify internal request building logic."""

    def test_returns_list_of_requests(
        self,
        bridge: EntityBridge,
        entity_event: dict,
    ) -> None:
        result = bridge._build_requests(entity_event, "evt-1", "corr-1")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_returns_entity_update_request(
        self,
        bridge: EntityBridge,
        entity_event: dict,
    ) -> None:
        result = bridge._build_requests(entity_event, "evt-1", "corr-1")
        assert isinstance(result[0], EntityUpdateRequest)

    def test_empty_for_no_entity_data(
        self,
        bridge: EntityBridge,
        plain_event: dict,
    ) -> None:
        result = bridge._build_requests(plain_event, "evt-6", None)
        assert result == []

    def test_preserves_correlation_id(
        self,
        bridge: EntityBridge,
        entity_event: dict,
    ) -> None:
        result = bridge._build_requests(entity_event, "evt-7", "corr-99")
        assert result[0].correlation_id == "corr-99"

    def test_preserves_source_event_id(
        self,
        bridge: EntityBridge,
        entity_event: dict,
    ) -> None:
        result = bridge._build_requests(entity_event, "evt-8", None)
        assert result[0].source_event_id == "evt-8"

    def test_updates_from_nested_entity_key(
        self,
        bridge: EntityBridge,
    ) -> None:
        event = {
            "entity_type": "source",
            "entity_id": "s-1",
            "entity": {"name": "Nested", "extra": "data"},
        }
        result = bridge._build_requests(event, "evt-9", None)
        assert result[0].updates == {"name": "Nested", "extra": "data"}

    def test_updates_fallback_to_event_data_copy(
        self,
        bridge: EntityBridge,
    ) -> None:
        event = {
            "entity_type": "asset",
            "entity_id": "a-1",
            "status": "active",
        }
        result = bridge._build_requests(event, "evt-10", None)
        assert "status" in result[0].updates
