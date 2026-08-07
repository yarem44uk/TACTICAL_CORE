from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from uuid import UUID

from ..graph_node import GraphNode
from ..graph_edge import GraphEdge


class IEntityGraph(ABC):
    """Core interface for Entity Graph operations."""

    @abstractmethod
    def create_node(self, node: GraphNode) -> None: ...

    @abstractmethod
    def remove_node(self, node_id: UUID) -> bool: ...

    @abstractmethod
    def create_edge(self, edge: GraphEdge) -> None: ...

    @abstractmethod
    def remove_edge(self, edge_id: UUID) -> bool: ...

    @abstractmethod
    def neighbors(self, node_id: UUID) -> List[GraphNode]: ...

    @abstractmethod
    def outgoing(self, node_id: UUID) -> List[GraphEdge]: ...

    @abstractmethod
    def incoming(self, node_id: UUID) -> List[GraphEdge]: ...

    @abstractmethod
    def shortest_path(self, source_id: UUID, target_id: UUID) -> Optional[List[UUID]]: ...

    @abstractmethod
    def subgraph(self, root_id: UUID, depth: int = 1) -> Dict[UUID, List[UUID]]: ...
