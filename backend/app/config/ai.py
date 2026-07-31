"""
AI Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""


class AIConfig:
    """AI module configuration."""

    def __init__(
        self,
        enabled: bool = True,
        model_path: str = "./models",
        confidence_threshold: float = 0.7,
        summary_length: int = 200,
        provider: str = "local",
        api_endpoint: str = "",
        api_key: str = "",
    ) -> None:
        self.enabled = enabled
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.summary_length = summary_length
        self.provider = provider
        self.api_endpoint = api_endpoint
        self.api_key = api_key

    @property
    def is_enabled(self) -> bool:
        return self.enabled
