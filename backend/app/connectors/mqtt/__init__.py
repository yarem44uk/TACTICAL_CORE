"""MQTT Connector.

MQTT sensor/IoT connector for TACTICAL CORE.
Publishes canonical events to the Event Bus.

Canonical Flow:
    MQTT -> MQTT Connector -> Event Bus -> Observation Service -> Observation

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.connectors.mqtt.connector import MQTTConnector, MQTTConnectorError
from app.connectors.mqtt.parser import MQTTParser, MQTTParserError
from app.connectors.mqtt.models import (
    MQTTMessage,
    MQTTEvent,
)
from app.connectors.mqtt.service import MQTTService, get_mqtt_service


__all__ = [
    "MQTTConnector",
    "MQTTConnectorError",
    "MQTTParser",
    "MQTTParserError",
    "MQTTMessage",
    "MQTTEvent",
    "MQTTService",
    "get_mqtt_service",
]
