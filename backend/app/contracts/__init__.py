"""
Contracts Module.

This package contains all interfaces (ABCs) for Tactical Core.
Future plugins must depend ONLY on these contracts.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.contracts.plugin import IPlugin, IPluginManager
from app.contracts.event import IEventPublisher, IEventSubscriber
from app.contracts.audio import IAudioSource, IAudioSink, ITranscriber
from app.contracts.messaging import IMessageSource, IMessageSink
from app.contracts.storage import IStorage
from app.contracts.monitoring import IHealthCheck, IMetricsCollector, ILogger
from app.contracts.configuration import IConfigurationProvider

__all__ = [
    # Plugin
    "IPlugin",
    "IPluginManager",
    # Event
    "IEventPublisher",
    "IEventSubscriber",
    # Audio
    "IAudioSource",
    "IAudioSink",
    "ITranscriber",
    # Messaging
    "IMessageSource",
    "IMessageSink",
    # Storage
    "IStorage",
    # Monitoring
    "IHealthCheck",
    "IMetricsCollector",
    "ILogger",
    # Configuration
    "IConfigurationProvider",
]
