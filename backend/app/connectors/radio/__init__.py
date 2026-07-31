"""Radio Connector.

Radio transmission connector for TACTICAL CORE.
Publishes canonical events to the Event Bus.

Canonical Flow:
    Radio -> Radio Connector -> Event Bus -> Observation Service -> Observation

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.connectors.radio.connector import RadioConnector, RadioConnectorError
from app.connectors.radio.parser import RadioParser, RadioParserError
from app.connectors.radio.models import (
    RadioTransmission,
    RadioEvent,
)
from app.connectors.radio.service import RadioService, get_radio_service


__all__ = [
    "RadioConnector",
    "RadioConnectorError",
    "RadioParser",
    "RadioParserError",
    "RadioTransmission",
    "RadioEvent",
    "RadioService",
    "get_radio_service",
]
