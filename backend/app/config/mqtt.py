"""
MQTT Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""


class MQTTConfig:
    """MQTT broker configuration."""

    def __init__(
        self,
        enabled: bool = False,
        broker_url: str = "mqtt://localhost:1883",
        topic_prefix: str = "tactical",
        client_id: str = "tactical-core",
        keepalive: int = 60,
        qos: int = 1,
    ) -> None:
        self.enabled = enabled
        self.broker_url = broker_url
        self.topic_prefix = topic_prefix
        self.client_id = client_id
        self.keepalive = keepalive
        self.qos = qos

    @property
    def is_enabled(self) -> bool:
        return self.enabled
