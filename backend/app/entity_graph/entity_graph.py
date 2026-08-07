from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Dict, List, Optional
from uuid import UUID

from .graph_node import GraphNode
from .graph_edge import GraphEdge
from .interfaces.i_entity_graph import IEntityGraph
from .interfaces.i_graph_repository import IGraphRepository


logger = logging.getLogger(__name__)


class EntityGraph(IEntityGraph):
    """Implementation of Entity Graph with thread-safe operations and graph algorithms."""

    def __init__(self, repository: IGraphRepository | None = None) -> None:
        from .memory_graph_repository import MemoryGraphRepository
        self._repo = repository or MemoryGraphRepository()
        self._lock = threading.RLock()

    def create_node(self, node: GraphNode) -> None:
        with self._lock:
            existing = self._repo.get_node(str(node.node_id))
            if existing:
                raise ValueError(f"Node {node.node_id} already exists")
            self._repo.save_node(node)
            logger.debug("Node created: %s", node.node_id)

    def remove_node(self, node_id: UUID) -> bool:
        with self._lock:
            node = self._repo.get_node(str(node_id))
            if not node:
                return False
            # Remove connected edges
            edges = self._repo.list_edges()
            for edge in edges:
                if edge.source_node == str(node_id) or edge.target_node == str(node_id):
                    self._repo.delete_edge(str(edge.edge_id))
            return self._repo.delete_node(str(node_id))

    def create_edge(self, edge: GraphEdge) -> None:
        with self._lock:
            src = self._repo.get_node(edge.source_node)
            tgt = self._repo.get_node(edge.target_node)
            if not src or not tgt:
                raise ValueError(f"Edge requires existing nodes: {edge.source_node} -> {edge.target_node}")
            # Check duplicate
            for e in self._repo.list_edges():
                if e.source_node == edge.source_node and e.target_node == edge.target_node:
                    raise ValueError(f"Edge {edge.source_node} -> {edge.target_node} already exists")
            self._repo.save_edge(edge)
            logger.debug("Edge created: %s -> %s", edge.source_node, edge.target_node)

    def remove_edge(self, edge_id: UUID) -> bool:
        with self._lock:
            return self._repo.delete_edge(str(edge_id))

    def neighbors(self, node_id: UUID) -> List[GraphNode]:
        with self._lock:
            neighbor_ids = set()
            for e in self._repo.list_edges():
                if e.source_node == str(node_id):
                    neighbor_ids.add(e.target_node)
                elif e.target_node == str(node_id):
                    neighbor_ids.add(e.source_node)
            return [self._repo.get_node(nid) for nid in neighbor_ids if self._repo.get_node(nid)]

    def outgoing(self, node_id: UUID) -> List[GraphEdge]:
        with self._lock:
            return [e for e in self._repo.list_edges() if e.source_node == str(node_id)]

    def incoming(self, node_id: UUID) -> List[GraphEdge]:
        with self._lock:
            return [e for e in self._repo.list_edges() if e.target_node == str(node_id)]

    def shortest_path(self, source_id: UUID, target_id: UUID) -> Optional[List[UUID]]:
        """BFS to find shortest path."""
        with self._lock:
            if source_id == target_id:
                return [source_id]
            visited = {source_id}
            queue = deque([(source_id, [source_id])])
            while queue:
                current, path = queue.popleft()
                for e in self._repo.list_edges():
                    if e.source_node == str(current):
                        neighbor = UUID(e.target_node)
                        if neighbor not in visited:
                            new_path = path + [neighbor]
                            if neighbor == target_id:
                                return new_path
                            visited.add(neighbor)
                            queue.append((neighbor, new_path))
            return None

    def subgraph(self, root_id: UUID, depth: int = 1) -> Dict[UUID, List[UUID]]:
        """BFS subgraph extraction up to specified depth."""
        with self._lock:
            result: Dict[UUID, List[UUID]] = {root_id: []}
            current_level = {root_id}
            for _ in range(depth):
                next_level: Dict[UUID, List[UUID]] = {}
                for node in current_level:
                    neighbors_of_node = []
                    for e in self._repo.list_edges():
                        if e.source_node == str(node):
                            neighbor = UUID(e.target_node)
                            neighbors_of_node.append(neighbor)
                            if neighbor not in result:
                                next_level[neighbor] = []
                    result[node] = neighbors_of_node
                current_level = set(next_level.keys())
                result.update(next_level)
            return result
