from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from ..graph_node import GraphNode
from ..graph_edge import GraphEdge


class IGraphRepository(ABC):
    """Repository interface for Graph persistence."""

    @abstractmethod
    def save_node(self, node: GraphNode) -> None: ...

    @abstractmethod
    def save_edge(self, edge: GraphEdge) -> None: ...

    @abstractmethod
    def delete_node(self, node_id: str) -> bool: ...

    @abstractmethod
    def delete_edge(self, edge_id: str) -> bool: ...

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[GraphNode]: ...

    @abstractmethod
    def get_edge(self, edge_id: str) -> Optional[GraphEdge]: ...

    @abstractmethod
    def list_nodes(self) -> List[GraphNode]: ...

    @abstractmethod
    def list_edges(self) -> List[GraphEdge]: ...

    @abstractmethod
    def lock(self) -> threading.RLock: ...
