from __future__ import annotations

import threading
from typing import List

import pytest

from app.entity_graph import EntityGraph, GraphNode, GraphEdge, MemoryGraphRepository
from uuid import UUID


@pytest.fixture
def repository() -> MemoryGraphRepository:
    return MemoryGraphRepository()


@pytest.fixture
def graph(repository: MemoryGraphRepository) -> EntityGraph:
    return EntityGraph(repository=repository)


def _make_node(entity_id: str, entity_type: str = "test") -> GraphNode:
    from uuid import uuid4
    return GraphNode(node_id=uuid4(), entity_id=entity_id, entity_type=entity_type)


def _make_edge(src: GraphNode, tgt: GraphNode, relation_type: str = "connected_to") -> GraphEdge:
    from uuid import uuid4
    return GraphEdge(edge_id=uuid4(), source_node=str(src.node_id), target_node=str(tgt.node_id), relation_type=relation_type)


class TestNodeOperations:
    def test_create_node(self, graph: EntityGraph) -> None:
        node = _make_node("n1")
        graph.create_node(node)
        assert graph.neighbors(node.node_id) == []

    def test_duplicate_node_raises(self, graph: EntityGraph) -> None:
        node = _make_node("n1")
        graph.create_node(node)
        with pytest.raises(ValueError):
            graph.create_node(node)

    def test_remove_node(self, graph: EntityGraph) -> None:
        node = _make_node("n1")
        graph.create_node(node)
        assert graph.remove_node(node.node_id) is True


class TestEdgeOperations:
    def test_create_edge(self, graph: EntityGraph) -> None:
        n1, n2 = _make_node("n1"), _make_node("n2")
        graph.create_node(n1)
        graph.create_node(n2)
        edge = _make_edge(n1, n2)
        graph.create_edge(edge)
        assert len(graph.outgoing(n1.node_id)) == 1

    def test_duplicate_edge_raises(self, graph: EntityGraph) -> None:
        n1, n2 = _make_node("n1"), _make_node("n2")
        graph.create_node(n1)
        graph.create_node(n2)
        edge = _make_edge(n1, n2)
        graph.create_edge(edge)
        with pytest.raises(ValueError):
            graph.create_edge(edge)

    def test_outgoing(self, graph: EntityGraph) -> None:
        n1, n2 = _make_node("n1"), _make_node("n2")
        graph.create_node(n1)
        graph.create_node(n2)
        graph.create_edge(_make_edge(n1, n2))
        assert len(graph.outgoing(n1.node_id)) == 1

    def test_incoming(self, graph: EntityGraph) -> None:
        n1, n2 = _make_node("n1"), _make_node("n2")
        graph.create_node(n1)
        graph.create_node(n2)
        graph.create_edge(_make_edge(n1, n2))
        assert len(graph.incoming(n2.node_id)) == 1


class TestGraphAlgorithms:
    def test_neighbors(self, graph: EntityGraph) -> None:
        n1, n2 = _make_node("n1"), _make_node("n2")
        graph.create_node(n1)
        graph.create_node(n2)
        graph.create_edge(_make_edge(n1, n2))
        nbrs = graph.neighbors(n1.node_id)
        assert len(nbrs) == 1

    def test_shortest_path(self, graph: EntityGraph) -> None:
        n1, n2, n3 = _make_node("n1"), _make_node("n2"), _make_node("n3")
        graph.create_node(n1)
        graph.create_node(n2)
        graph.create_node(n3)
        graph.create_edge(_make_edge(n1, n2))
        graph.create_edge(_make_edge(n2, n3))
        path = graph.shortest_path(n1.node_id, n3.node_id)
        assert path is not None
        assert len(path) == 3
        assert path[0] == n1.node_id
        assert path[-1] == n3.node_id

    def test_subgraph(self, graph: EntityGraph) -> None:
        n1, n2, n3 = _make_node("n1"), _make_node("n2"), _make_node("n3")
        graph.create_node(n1)
        graph.create_node(n2)
        graph.create_node(n3)
        graph.create_edge(_make_edge(n1, n2))
        graph.create_edge(_make_edge(n2, n3))
        sg = graph.subgraph(n1.node_id, depth=2)
        assert n1.node_id in sg
        assert len(sg) == 3


class TestThreadSafety:
    def test_concurrent_create(self, graph: EntityGraph) -> None:
        errors: List[Exception] = []
        def worker(i: int) -> None:
            try:
                graph.create_node(_make_node(f"n{i}"))
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0


class TestRepository:
    def test_persistence(self, repository: MemoryGraphRepository) -> None:
        node = _make_node("persist-n1")
        repository.save_node(node)
        assert repository.get_node(str(node.node_id)) is not None
