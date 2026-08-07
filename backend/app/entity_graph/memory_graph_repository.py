from __future__ import annotations

import threading
from typing import List, Optional

from .interfaces.i_graph_repository import IGraphRepository
from .graph_node import GraphNode
from .graph_edge import GraphEdge


class MemoryGraphRepository(IGraphRepository):
    """Thread-safe in-memory repository for Graph data."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._lock = threading.RLock()

    def save_node(self, node: GraphNode) -> None:
        with self._lock:
            self._nodes[str(node.node_id)] = node

    def save_edge(self, edge: GraphEdge) -> None:
        with self._lock:
            self._edges[str(edge.edge_id)] = edge

    def delete_node(self, node_id: str) -> bool:
        with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
                return True
            return False

    def delete_edge(self, edge_id: str) -> bool:
        with self._lock:
            if edge_id in self._edges:
                del self._edges[edge_id]
                return True
            return False

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        with self._lock:
            return self._nodes.get(node_id)

    def get_edge(self, edge_id: str) -> Optional[GraphEdge]:
        with self._lock:
            return self._edges.get(edge_id)

    def list_nodes(self) -> List[GraphNode]:
        with self._lock:
            return list(self._nodes.values())

    def list_edges(self) -> List[GraphEdge]:
        with self._lock:
            return list(self._edges.values())

    def lock(self) -> threading.RLock:
        return self._lock
