"""WO-037-02 — Operator Application Foundation (ADR-011).

The operator process is a separate, read-only FastAPI + uvicorn application
that consumes the authoritative durable repositories (events, entities,
relations). It is a CONSUMER of the durable engine, never part of it: the
durable engine must remain fully operational if the operator process is absent.

This package does NOT import or start the durable engine (``backend/main.py``,
``EventPipeline``, ``DurableDeliveryDispatcher``, ``ReconstructionService``).
"""

from __future__ import annotations

from app.operator.app import create_operator_app
from app.operator.router import router
from app.operator.service import OperatorService

__all__ = [
    "create_operator_app",
    "router",
    "OperatorService",
]
