"""Knowledge Graph Module.

Provides graph-based knowledge representation for Intelligence Core.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.intelligence.knowledge.knowledge_graph import KnowledgeGraph, GraphStorage, GraphConfig
from app.intelligence.knowledge.nodes import KnowledgeNode, NodeType, NodeProperty
from app.intelligence.knowledge.edges import KnowledgeEdge, EdgeType
from app.intelligence.knowledge.queries import GraphPattern, GraphQuery, GraphQueryBuilder
from app.intelligence.knowledge.inference import InferenceEngine, Rule, Fact

__all__ = [
    "KnowledgeGraph",
    "GraphStorage",
    "GraphConfig",
    "KnowledgeNode",
    "NodeType",
    "NodeProperty",
    "KnowledgeEdge",
    "EdgeType",
    "GraphPattern",
    "GraphQuery",
    "GraphQueryBuilder",
    "InferenceEngine",
    "Rule",
    "Fact",
]
