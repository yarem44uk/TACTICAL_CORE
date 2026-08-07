from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_status import EventStatus
from app.event_repository.interfaces.i_event_repository import IEventRepository
from app.event_service.interfaces.i_event_service import IEventService

logger = logging.getLogger(__name__)


class EventService(IEventService):
    """
    High-level service for event operations.

    Coordinates event persistence, retrieval, archiving, and statistics
    through IEventRepository. Thread-safe via RLock. No global state.
    """

    def __init__(self, repository: IEventRepository) -> None:
        self._repository = repository
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # IEventService implementation
    # ------------------------------------------------------------------

    def save_event(self, event: Event) -> None:
        """Persist a single event."""
        with self._lock:
            self._repository.save(event)
            logger.info("Event saved: %s", event.event_id)

    def save_events(self, events: List[Event]) -> None:
        """Persist multiple events atomically."""
        with self._lock:
            for event in events:
                self._repository.save(event)
            logger.info("Saved %d events", len(events))

    def get_event(self, event_id: str) -> Optional[Event]:
        """Retrieve a single event by ID."""
        with self._lock:
            result = self._repository.get(event_id)
            logger.debug("Event retrieved: %s (%s)", event_id, "found" if result else "not found")
            return result

    def get_events(self) -> List[Event]:
        """Retrieve all events."""
        with self._lock:
            events = self._repository.list_all()
            logger.debug("Retrieved %d events", len(events))
            return events

    def archive_event(self, event_id: str) -> bool:
        """
        Archive an event by creating a new archived copy.

        Events are immutable, so archiving means creating a duplicate
        with archived status metadata and removing the original.
        """
        with self._lock:
            original = self._repository.get(event_id)
            if original is None:
                logger.warning("Cannot archive non-existent event: %s", event_id)
                return False

            archived_metadata = EventMetadata(
                tags=["archived"],
                properties={"original_event_id": event_id},
                correlation_id=original.metadata.correlation_id,
            )
            archived_event = Event(
                event_id=event_id,
                entity_id=original.entity_id,
                event_type=original.event_type,
                timestamp=original.timestamp,
                source=original.source,
                payload=dict(original.payload),
                metadata=archived_metadata,
                created_at=original.created_at,
            )

            deleted = self._repository.delete(event_id)
            if deleted:
                self._repository.save(archived_event)
                logger.info("Event archived: %s", event_id)
            else:
                logger.error("Failed to delete event before archiving: %s", event_id)

            return deleted

    def exists(self, event_id: str) -> bool:
        """Check whether an event exists."""
        with self._lock:
            result = self._repository.exists(event_id)
            logger.debug("Event exists check [%s]: %s", event_id, result)
            return result

    def statistics(self) -> Dict[str, Any]:
        """Return aggregate statistics over stored events."""
        with self._lock:
            events = self._repository.list_all()

            total = len(events)

            type_counts: Dict[str, int] = {}
            source_counts: Dict[str, int] = {}

            for event in events:
                type_key = str(event.event_type)
                type_counts[type_key] = type_counts.get(type_key, 0) + 1

                source_key = event.source
                source_counts[source_key] = source_counts.get(source_key, 0) + 1

            return {
                "total_events": total,
                "by_type": type_counts,
                "by_source": source_counts,
            }

    def export(self) -> List[Dict[str, Any]]:
        """Export all events as serialisable dictionaries."""
        with self._lock:
            events = self._repository.list_all()
            exported = [event.to_dict() for event in events]
            logger.info("Exported %d events", len(exported))
            return exported

    def import_events(self, data: List[Dict[str, Any]]) -> int:
        """Import events from serialised dictionaries. Returns count of imported events."""
        with self._lock:
            count = 0
            for item in data:
                try:
                    event = Event.from_dict(item)
                    self._repository.save(event)
                    count += 1
                except (KeyError, ValueError, TypeError) as exc:
                    logger.warning("Skipping invalid event during import: %s", exc)

            logger.info("Imported %d/%d events", count, len(data))
            return count
