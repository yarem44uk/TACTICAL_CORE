"""
WebSocket Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""


class WebSocketConfig:
    """WebSocket server configuration."""

    def __init__(
        self,
        heartbeat_interval: int = 30,
        message_queue_size: int = 1000,
        max_connections: int = 100,
        ping_timeout: int = 60,
        ping_interval: int = 25,
    ) -> None:
        self.heartbeat_interval = heartbeat_interval
        self.message_queue_size = message_queue_size
        self.max_connections = max_connections
        self.ping_timeout = ping_timeout
        self.ping_interval = ping_interval
