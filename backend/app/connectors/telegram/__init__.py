"""Telegram Connector.

Telegram bot/message connector for TACTICAL CORE.
Publishes canonical events to the Event Bus.

Canonical Flow:
    Telegram -> Telegram Connector -> Event Bus -> Observation Service -> Observation

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.connectors.telegram.connector import TelegramConnector, TelegramConnectorError
from app.connectors.telegram.parser import TelegramParser, TelegramParserError
from app.connectors.telegram.models import (
    TelegramMessage,
    TelegramMedia,
    TelegramEvent,
)
from app.connectors.telegram.service import TelegramService, get_telegram_service


__all__ = [
    "TelegramConnector",
    "TelegramConnectorError",
    "TelegramParser",
    "TelegramParserError",
    "TelegramMessage",
    "TelegramMedia",
    "TelegramEvent",
    "TelegramService",
    "get_telegram_service",
]
