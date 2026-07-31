"""Radio transmission parser.

Parses incoming radio transmission data into RadioTransmission objects.
Handles various formats and validates required fields.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.connectors.radio.models import RadioTransmission


logger = logging.getLogger(__name__)


class RadioParserError(Exception):
    """Raised when radio transmission parsing fails."""

    pass


class RadioParser:
    """Parses radio transmission data into RadioTransmission objects.

    Radio transmission contract requires:
    - frequency: Radio frequency identifier
    - callsign: Radio callsign identifier
    """

    def __init__(self):
        """Initialize the parser."""
        pass

    def parse(
        self,
        frequency: str,
        callsign: str,
        timestamp: Optional[datetime] = None,
        source: Optional[str] = None,
        signal_strength: Optional[int] = None,
        modulation: Optional[str] = None,
    ) -> RadioTransmission:
        """Parse radio transmission components into a RadioTransmission.

        Args:
            frequency: Radio frequency identifier.
            callsign: Radio callsign identifier.
            timestamp: Optional transmission timestamp.
            source: Optional source device or channel.
            signal_strength: Optional signal strength (0-100).
            modulation: Optional modulation type.

        Returns:
            RadioTransmission object.

        Raises:
            RadioParserError: If parsing fails.
        """
        # Validate required fields
        if not frequency:
            raise RadioParserError("Empty frequency")

        if not callsign:
            raise RadioParserError("Empty callsign")

        # Validate frequency format (basic check)
        if not self._is_valid_frequency(frequency):
            raise RadioParserError(f"Invalid frequency format: {frequency}")

                # Parse timestamp
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        elif isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                # Convert timezone-aware datetime to UTC
                timestamp = timestamp.astimezone(timezone.utc)
        elif isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif isinstance(timestamp, str):
            ts = timestamp.replace("Z", "+00:00")
            try:
                timestamp = datetime.fromisoformat(ts)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                else:
                    # Convert timezone-aware datetime to UTC
                    timestamp = timestamp.astimezone(timezone.utc)
            except ValueError:
                try:
                    timestamp = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
                except ValueError:
                    timestamp = datetime.now(timezone.utc)
        
        # Validate signal strength if provided
        if signal_strength is not None:
            if not isinstance(signal_strength, int) or signal_strength < 0 or signal_strength > 100:
                raise RadioParserError("Invalid signal_strength (must be 0-100)")

        # Create transmission
        transmission = RadioTransmission(
            frequency=frequency,
            callsign=callsign,
            timestamp=timestamp,
            source=source,
            signal_strength=signal_strength,
            modulation=modulation,
            raw_payload={
                "frequency": frequency,
                "callsign": callsign,
            },
        )

        logger.debug(
            f"Parsed radio transmission: frequency={transmission.frequency}, "
            f"callsign={transmission.callsign}"
        )

        return transmission

    def _is_valid_frequency(self, frequency: str) -> bool:
        """Validate frequency format.

        Args:
            frequency: Frequency string to validate.

        Returns:
            True if valid format.
        """
        if not frequency:
            return False

        # Accept common frequency formats:
        # - "155.5" (decimal MHz)
        # - "155.5 MHz"
        # - "155500000" (Hz)
        # - "155.500" (decimal with 3 digits)

        # Basic validation: should have digits and optionally decimal point
        import re
        pattern = r'^\d+(\.\d+)?\s*(MHz|kHz|Hz|kHz)?\s*$'
        return bool(re.match(pattern, frequency.strip(), re.IGNORECASE))

    def parse_dict(self, transmission_dict: Dict[str, Any]) -> RadioTransmission:
        """Parse radio transmission from dictionary.

        Args:
            transmission_dict: Dictionary containing transmission data.

        Returns:
            RadioTransmission object.

        Raises:
            RadioParserError: If required fields are missing.
        """
        # Validate required fields
        if "frequency" not in transmission_dict:
            raise RadioParserError("Missing required field: frequency")
        if "callsign" not in transmission_dict:
            raise RadioParserError("Missing required field: callsign")

        return self.parse(
            frequency=transmission_dict["frequency"],
            callsign=transmission_dict["callsign"],
            timestamp=transmission_dict.get("timestamp"),
            source=transmission_dict.get("source"),
            signal_strength=transmission_dict.get("signal_strength"),
            modulation=transmission_dict.get("modulation"),
        )
