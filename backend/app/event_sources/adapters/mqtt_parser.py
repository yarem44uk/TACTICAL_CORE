"""
TACTICAL CORE — MQTT Payload Normalizer
WO-013-006

Adapter-local helper that normalizes raw MQTT messages into raw event
dictionaries compatible with the WO-013 EventFactory.

This is an independent implementation. It REUSES the field semantics of
the legacy MQTT connector (topic, payload, qos, retain, client_id,
timestamp) but does NOT import or depend on the legacy connector package
(backend/app/connectors/mqtt/) or its EventBus coupling.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# EventFactory treats these keys as protocol/timestamp keys (moved to
# metadata; the timestamp key drives Event.timestamp normalization).
_TIMESTAMP_KEYS = ("timestamp", "time", "datetime", "date", "ts", "created_at")


class MQTTParseError(ValueError):
    """Raised when an MQTT message cannot be normalized."""


class MQTTPayloadNormalizer:
    """Normalize raw MQTT message data into an EventFactory-compatible dict.

    The normalized dict carries repository-backed MQTT semantics:

        timestamp      -> EventFactory protocol key (drives UTC
                          normalization and moves to metadata)
        topic          -> payload field
        payload        -> payload field
        qos            -> payload field
        retain         -> payload field
        client_id      -> payload field
        correlation_id -> top-level key -> EventFactory metadata
                          correlation_id

    No fields are invented beyond the legacy/repository-backed MQTT
    semantics. The normalizer is synchronous and side-effect free; it
    never accesses EventBus, the database, the API layer, the pipeline,
    or any global application state.
    """

    def normalize(self, message: dict[str, Any]) -> dict[str, Any]:
        """Normalize one MQTT message into a raw event dict.

        Args:
            message: Raw MQTT message data (dict) carrying at minimum a
                topic and a payload.

        Returns:
            A raw dict ready for EventFactory.create_event.

        Raises:
            MQTTParseError: if the message is malformed (missing topic or
                payload, or invalid QoS value).
        """
        if not isinstance(message, dict):
            raise MQTTParseError("MQTT message must be a dict")

        topic = message.get("topic")
        payload = message.get("payload")

        if not topic or not isinstance(topic, str):
            raise MQTTParseError("MQTT message requires a non-empty string 'topic'")
        if payload is None:
            raise MQTTParseError("MQTT message requires a 'payload'")

        qos = message.get("qos", 0)
        if isinstance(qos, bool) or not isinstance(qos, int) or qos not in (0, 1, 2):
            raise MQTTParseError(f"MQTT 'qos' must be 0, 1, or 2 (got {qos!r})")

        retain = bool(message.get("retain", False))
        client_id = message.get("client_id")

        raw: dict[str, Any] = {
            "topic": topic,
            "payload": payload,
            "qos": qos,
            "retain": retain,
        }
        if client_id is not None:
            raw["client_id"] = client_id

        # Timestamp: pass through if present so EventFactory normalizes it.
        timestamp = message.get("timestamp")
        if timestamp is not None:
            raw["timestamp"] = timestamp

        # Correlation id: preserve in metadata via EventFactory contract.
        correlation_id = message.get("correlation_id")
        if correlation_id is not None:
            raw["correlation_id"] = correlation_id

        return raw
