"""
Security Configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import List


class SecurityConfig:
    """Security and CORS configuration."""

    def __init__(
        self,
        cors_origins: List[str] = None,
        allowed_hosts: List[str] = None,
        secret_key: str = "change-this",
        jwt_secret: str = "",
        jwt_algorithm: str = "HS256",
        jwt_expiration_minutes: int = 60,
        bcrypt_rounds: int = 12,
    ) -> None:
        self.cors_origins = cors_origins or ["http://localhost:3000", "http://localhost:8080"]
        self.allowed_hosts = allowed_hosts or ["localhost", "127.0.0.1"]
        self.secret_key = secret_key
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.jwt_expiration_minutes = jwt_expiration_minutes
        self.bcrypt_rounds = bcrypt_rounds

    def validate_origins(self) -> List[str]:
        """Validate CORS origins format."""
        errors = []
        for origin in self.cors_origins:
            if not origin.startswith(("http://", "https://")):
                errors.append(f"Invalid CORS origin: {origin}")
        return errors
