"""
TACTICAL CORE — Radio Adapter Payload Normalizer
WO-013-007

Adapter-local helper that normalizes raw radio transmission payloads into
raw dictionaries compatible with the canonical EventFactory.

This is an INDEPENDENT implementation. It reuses the field SEMANTICS of
the legacy Radio connector (frequency, callsign, timestamp, source,
signal_strength, modulation) but does NOT import or depend on
`app.connectors.radio`. It never touches EventBus, the API layer, the
database, or the event pipeline.

The normalized raw dict is shaped for `EventFactory.create_event`:

    timestamp      -> Event.timestamp        (normalized to UTC by factory)
    correlation_id -> Event.metadata.correlation_id
    all other keys -> Event.payload
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Field names that the EventFactory recognizes as timestamp keys and moves
# into metadata. Kept local to this helper for clarity.
_TIMESTAMP_KEYS = ("timestamp", "time", "datetime", "date", "ts", "created_at")

# Basic frequency format accepted by the legacy Radio parser (decimal MHz,
# optionally with a unit suffix, or bare Hz). Mirrors legacy semantics.
_FREQUENCY_RE = re.compile(
    r"^\d+(\.\d+)?\s*(MHz|kHz|Hz)?\s*$",
    re.IGNORECASE,
)


class RadioParseError(Exception):
    """Raised when a radio payload cannot be normalized.

    A single malformed transmission raising this error is isolated and
    dropped by the adapter's read path without killing the adapter
    runtime.
    """


class RadioPayloadNormalizer:
    """Normalizes raw radio transmissions into EventFactory-compatible dicts.

    This mirrors the field semantics of the legacy Radio connector while
    remaining fully independent of it (no cross-import).
    """

    def __init__(self) -> None:
        self._required_fields = ("frequency", "callsign")

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single raw radio transmission into a raw event dict.

        Args:
            payload: Raw radio transmission payload (dict).

        Returns:
            A raw dict suitable for `EventFactory.create_event`. The dict
            carries a recognized timestamp key plus the radio fields.

        Raises:
            RadioParseError: If the payload is empty, lacks required
                fields, has an invalid frequency, or has an invalid
                signal_strength. The caller isolates this error per-message.
        """
        if not isinstance(payload, dict) or not payload:
            raise RadioParseError("Radio payload is empty or not a dict")

        missing = [f for f in self._required_fields if payload.get(f) is None]
        if missing:
            raise RadioParseError(
                f"Radio payload missing required fields: {missing}"
            )

        frequency = str(payload["frequency"])
        callsign = str(payload["callsign"])

        if not self._is_valid_frequency(frequency):
            raise RadioParseError(f"Invalid frequency format: {frequency}")

        signal_strength = payload.get("signal_strength")
        if signal_strength is not None:
            if (
                not isinstance(signal_strength, int)
                or signal_strength < 0
                or signal_strength > 100
            ):
                raise RadioParseError(
                    "Invalid signal_strength (must be 0-100)"
                )

        # Build the raw event dict. The timestamp key is preserved so the
        # EventFactory normalizes it to a UTC datetime and moves it to
        # metadata; all other fields land in Event.payload.
        raw: dict[str, Any] = {
            "frequency": frequency,
            "callsign": callsign,
        }

        source = payload.get("source")
        if source is not None:
            raw["source"] = str(source)

        modulation = payload.get("modulation")
        if modulation is not None:
            raw["modulation"] = str(modulation)

        if signal_strength is not None:
            raw["signal_strength"] = signal_strength

        # Preserve timestamp through the factory-recognized keys.
        if "timestamp" in payload:
            raw["timestamp"] = payload["timestamp"]
        else:
            # Fall back to any other factory-recognized timestamp key.
            for key in _TIMESTAMP_KEYS:
                if key in payload:
                    raw[key] = payload[key]
                    break

        # Preserve an optional correlation identifier for EventMetadata.
        if "correlation_id" in payload and payload["correlation_id"] is not None:
            raw["correlation_id"] = payload["correlation_id"]

        return raw

    @staticmethod
    def _is_valid_frequency(frequency: str) -> bool:
        """Validate frequency format (mirrors legacy Radio semantics).

        Args:
            frequency: Frequency string to validate.

        Returns:
            True if valid format.
        """
        if not frequency:
            return False
        return bool(_FREQUENCY_RE.match(frequency.strip()))

    def normalize_batch(
        self, payloads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize a batch of payloads, isolating malformed ones.

        Returns only the successfully normalized raw dicts. Malformed
        transmissions are logged and skipped so a single bad message
        cannot break the batch/read path.
        """
        raw_events: list[dict[str, Any]] = []
        for idx, payload in enumerate(payloads):
            try:
                raw_events.append(self.normalize(payload))
            except RadioParseError as exc:
                logger.warning("Radio payload %d dropped: %s", idx, exc)
        return raw_events
