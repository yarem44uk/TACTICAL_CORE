from __future__ import annotations
from typing import List

class IdentityMatching:
    @staticmethod
    def normalize(text: str) -> str:
        return text.strip().lower()

    @staticmethod
    def match_aliases(candidates: List[str], target: str) -> List[str]:
        normalized = IdentityMatching.normalize(target)
        return [c for c in candidates if IdentityMatching.normalize(c) == normalized]
