from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class IdentityKey:
    source: str
    external_id: str
    entity_type: str

    def to_string(self) -> str:
        return f"{self.source}:{self.external_id}:{self.entity_type}"
