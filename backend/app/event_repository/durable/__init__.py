"""
Durable Event Repository Package (WO-014-016).

This package provides a durable, SQLAlchemy-backed implementation of the
authoritative ``IEventRepository`` contract for the canonical domain Event
(``app.event.event.Event``).

Scope is strictly confined to this package plus the existing approved database
infrastructure (``app.database``). No canonical domain, pipeline, factory, or
adapter module is coupled to SQLAlchemy here.
"""

from app.event_repository.durable.durable_event_model import DurableCanonicalEvent
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)

__all__ = [
    "DurableCanonicalEvent",
    "SQLAlchemyEventRepository",
]
