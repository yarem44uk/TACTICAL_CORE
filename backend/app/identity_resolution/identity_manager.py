from __future__ import annotations
import threading
from typing import Any, Dict, List, Optional
from .interfaces.i_identity_manager import IIdentityManager
from .interfaces.i_identity_repository import IIdentityRepository
from .identity_key import IdentityKey
from .matching import IdentityMatching

class IdentityManager(IIdentityManager):
    def __init__(self, repository: IIdentityRepository | None = None) -> None:
        from .memory_identity_repository import MemoryIdentityRepository
        self._repository = repository or MemoryIdentityRepository()
        self._lock = threading.RLock()

    def resolve_identity(self, source: str, external_id: str, entity_type: str) -> Optional[str]:
        key = IdentityKey(source, external_id, entity_type).to_string()
        data = self._repository.get(key)
        return data.get("entity_id") if data else None

    def register_external_id(self, entity_id: str, source: str, external_id: str, entity_type: str) -> None:
        key = IdentityKey(source, external_id, entity_type).to_string()
        with self._lock:
            existing = self._repository.get(key)
            if not existing:
                data: Dict[str, Any] = {
                    "identity_key": key,
                    "entity_id": entity_id,
                    "source": source,
                    "external_id": external_id,
                    "entity_type": entity_type,
                    "aliases": [],
                }
                self._repository.save(data)

    def register_alias(self, entity_id: str, alias: str) -> None:
        with self._lock:
            normalized_alias = IdentityMatching.normalize(alias)
            all_data = self._repository.list_all()
            for item in all_data:
                if item["entity_id"] == entity_id:
                    if normalized_alias not in [IdentityMatching.normalize(a) for a in item["aliases"]]:
                        item["aliases"].append(alias)
                        self._repository.save(item)
                    return

    def merge_identity(self, primary_entity_id: str, secondary_entity_id: str) -> None:
        with self._lock:
            all_data = self._repository.list_all()
            secondary_items = [item for item in all_data if item["entity_id"] == secondary_entity_id]
            primary_items = [item for item in all_data if item["entity_id"] == primary_entity_id]
            primary_aliases = set()
            for p in primary_items:
                primary_aliases.update(IdentityMatching.normalize(a) for a in p.get("aliases", []))
            for s in secondary_items:
                s["entity_id"] = primary_entity_id
                for alias in s.get("aliases", []):
                    norm = IdentityMatching.normalize(alias)
                    if norm not in primary_aliases:
                        primary_aliases.add(norm)
                        for p in primary_items:
                            p["aliases"].append(alias)
                            self._repository.save(p)
                self._repository.save(s)

    def lookup(self, search_term: str) -> List[str]:
        normalized_term = IdentityMatching.normalize(search_term)
        all_data = self._repository.list_all()
        results: List[str] = []
        for item in all_data:
            if item.get("entity_id") == search_term:
                results.append(item["entity_id"])
            elif normalized_term in [IdentityMatching.normalize(a) for a in item.get("aliases", [])]:
                results.append(item["entity_id"])
        return list(set(results))
