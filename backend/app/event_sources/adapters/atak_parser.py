"""
TACTICAL CORE — ATAK/TAK Adapter Payload Normalizer
WO-013-009

Adapter-local helper that normalizes raw ATAK/TAK CoT (Cursor on Target)
payloads into raw dictionaries compatible with the canonical EventFactory.

This is an INDEPENDENT implementation. It reuses the field SEMANTICS of
the legacy ATAK CoT message shape (uid, type, time, lat, lon, how, detail)
but does NOT import or depend on any legacy connector. It never touches
EventBus, the API layer, the database, or the event pipeline.

The normalized raw dict is shaped for `EventFactory.create_event`:

    timestamp      -> Event.timestamp        (normalized to UTC by factory)
    correlation_id -> Event.metadata.correlation_id
    all other keys -> Event.payload

Parser output is DOMAIN-ONLY data (a plain dict). It never constructs or
returns canonical `Event` objects; Event construction is performed by
EventFactory through AdapterRuntime.

The parser is deterministic and defensive:
    - accepts the supported ATAK/TAK CoT input representation (dict shape)
    - validates the minimum required structure (uid, type, coordinates)
    - normalizes source data according to adapter conventions
    - rejects malformed input safely (raises AtakParseError)
    - never contains credentials
    - never persists data
    - never dispatches events directly
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Field names that the EventFactory recognizes as timestamp keys and moves
# into metadata. Kept local to this helper for clarity.
_TIMESTAMP_KEYS = ("timestamp", "time", "datetime", "date", "ts", "created_at")


class AtakParseError(Exception):
    """Raised when an ATAK/TAK CoT payload cannot be normalized.

    A single malformed message raising this error is isolated and dropped
    by the adapter's ingest path without killing the adapter runtime.
    """


class AtakPayloadNormalizer:
    """Normalizes raw ATAK/TAK CoT payloads into EventFactory-compatible dicts.

    ATAK/TAK interoperability is based on CoT (Cursor on Target) messages.
    The supported input representation is a plain dict carrying the core
    CoT event attributes:

        uid    - unique event identifier (required)
        type   - CoT event type, e.g. "a-u-G" for unknown ground (required)
        time   - event timestamp (required, ISO-8601 string or epoch number)
        lat    - latitude in decimal degrees (required)
        lon    - longitude in decimal degrees (required)
        how    - method used to transmit / derive the event (optional)
        stale  - event expiry timestamp (optional)
        detail - dict of additional event attributes (optional)

    Coordinates are validated as finite numbers within valid ranges and
    normalized to float.
    """

    def __init__(self) -> None:
        # Required CoT event attributes.
        self._required_fields = ("uid", "type", "lat", "lon")
        self._lat_range = (-90.0, 90.0)
        self._lon_range = (-180.0, 180.0)

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single raw ATAK/TAK CoT message into a raw event dict.

        Args:
            payload: Raw ATAK/TAK CoT message payload (dict). Expected to
                carry the CoT attributes: `uid`, `type`, `time`, `lat`,
                `lon`, and optional `how`, `stale`, `detail`.

        Returns:
            A raw dict suitable for `EventFactory.create_event`. The dict
            carries a recognized timestamp key plus the CoT event fields.

        Raises:
            AtakParseError: If the payload is empty, lacks required fields,
                or carries invalid (non-numeric / out-of-range) coordinates.
                The caller isolates this error per-message.
        """
        if not isinstance(payload, dict) or not payload:
            raise AtakParseError("ATAK/TAK payload is empty or not a dict")

        uid = payload.get("uid")
        event_type = payload.get("type")
        lat = self._to_float(payload.get("lat"), "lat")
        lon = self._to_float(payload.get("lon"), "lon")

        missing = [
            f for f, v in (
                ("uid", uid),
                ("type", event_type),
                ("lat", lat),
                ("lon", lon),
            )
            if v is None
        ]
        if missing:
            raise AtakParseError(
                f"ATAK/TAK payload missing required fields: {missing}"
            )

        # Static-analysis guard: lat/lon are guaranteed non-None here because
        # any None value was collected into `missing` above and raised.
        if lat is None or lon is None:
            raise AtakParseError("ATAK/TAK payload missing lat/lon")

        if not (self._lat_range[0] <= lat <= self._lat_range[1]):
            raise AtakParseError(
                f"ATAK/TAK lat {lat} out of range {self._lat_range}"
            )
        if not (self._lon_range[0] <= lon <= self._lon_range[1]):
            raise AtakParseError(
                f"ATAK/TAK lon {lon} out of range {self._lon_range}"
            )

        # Build the raw event dict. The timestamp key is preserved so the
        # EventFactory normalizes it to a UTC datetime and moves it to
        # metadata; all other fields land in Event.payload.
        raw: dict[str, Any] = {
            "uid": str(uid),
            "type": str(event_type),
            "lat": lat,
            "lon": lon,
        }

        # Optional transmission method.
        how = payload.get("how")
        if how is not None:
            raw["how"] = str(how)

        # Optional event expiry timestamp (CoT "stale").
        stale = payload.get("stale")
        if stale is not None:
            raw["stale"] = stale

        # Optional event attributes (CoT "detail").
        detail = payload.get("detail")
        if isinstance(detail, dict) and detail:
            raw["detail"] = dict(detail)

        # Preserve timestamp through the factory-recognized keys. Prefer
        # the CoT "time" attribute, then any other recognized timestamp key.
        if "time" in payload and payload["time"] is not None:
            raw["timestamp"] = payload["time"]
        elif "timestamp" in payload:
            raw["timestamp"] = payload["timestamp"]
        else:
            for key in _TIMESTAMP_KEYS:
                if key in payload:
                    raw[key] = payload[key]
                    break

        # Preserve an optional correlation identifier for EventMetadata.
        if "correlation_id" in payload and payload["correlation_id"] is not None:
            raw["correlation_id"] = payload["correlation_id"]

        return raw

    @staticmethod
    def _to_float(value: Any, field: str) -> float | None:
        """Coerce a coordinate to a finite float, or None if unusable."""
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number:  # NaN
            return None
        if number in (float("inf"), float("-inf")):
            return None
        return number

    def normalize_batch(
        self, payloads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize a batch of payloads, isolating malformed ones.

        Returns only the successfully normalized raw dicts. Malformed
        messages are logged and skipped so a single bad message cannot
        break the batch/read path.
        """
        raw_events: list[dict[str, Any]] = []
        for idx, payload in enumerate(payloads):
            try:
                raw_events.append(self.normalize(payload))
            except AtakParseError as exc:
                logger.warning("ATAK/TAK payload %d dropped: %s", idx, exc)
        return raw_events
