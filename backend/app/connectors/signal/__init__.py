"""
Signal Connector Module.

Receives Signal messages and publishes normalized Events to the Event Bus.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.connectors.signal.connector import SignalConnector, SignalConnectorError
from app.connectors.signal.models import SignalMessage, SignalEvent, Attachment
from app.connectors.signal.parser import SignalParser, SignalParserError
from app.connectors.signal.service import SignalService, get_signal_service

__all__ = [
    # Connector
    "SignalConnector",
    "SignalConnectorError",
    # Models
    "SignalMessage",
    "SignalEvent",
    "Attachment",
    # Parser
    "SignalParser",
    "SignalParserError",
    # Service
    "SignalService",
    "get_signal_service",
]
