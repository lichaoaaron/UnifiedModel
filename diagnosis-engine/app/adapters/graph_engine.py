"""
GraphEngineAdapter: abstract interface for graph query operations.
DictGraphEngine: in-memory Python dict implementation.

To swap to Neo4j / TuGraph, implement GraphEngineAdapter with the same methods
and replace DictGraphEngine(...) with Neo4jGraphEngine(...) — no Skill changes needed.

Example future swap:
    from app.adapters.neo4j_graph_engine import Neo4jGraphEngine
    engine = Neo4jGraphEngine(uri="bolt://localhost:7687", user="neo4j", password="...")
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class GraphEngineAdapter(ABC):
    """Abstract interface. All graph engines must implement these methods."""

    @abstractmethod
    def get_nodes(self) -> list[dict[str, Any]]:
        """Return all nodes: [{"id": str, "label": str, ...}]"""

    @abstractmethod
    def get_edges(self) -> list[dict[str, Any]]:
        """Return all edges: [{"src": str, "dest": str, "type": str, "label": str}]"""

    @abstractmethod
    def neighbors(self, node_id: str, relation_type: str | None = None) -> list[str]:
        """Return neighbor node ids reachable from node_id (outgoing edges)."""

    @abstractmethod
    def find_path(self, src: str, dest: str, max_depth: int = 5) -> list[str] | None:
        """BFS shortest path from src to dest. Returns node-id list or None."""

    @abstractmethod
    def query_by_relation(self, relation_type: str) -> list[dict[str, Any]]:
        """Return all edges of given relation_type."""


class DictGraphEngine(GraphEngineAdapter):
    """
    Lightweight in-memory graph engine backed by Python dicts.
    Loaded from UModelYamlAdapter.get_call_graph() output.

    Supports:
      - node/edge enumeration
      - neighbor lookup
      - BFS shortest path
      - relation-type filter

    Swap to Neo4j: implement GraphEngineAdapter and replace this class.
    """

    def __init__(self, graph_data: dict[str, Any]) -> None:
        """
        graph_data format (from UModelYamlAdapter.get_call_graph()):
          {
            "nodes": [{"id": str, "label": str, "domain": str}],
            "edges": [{"src": str, "dest": str, "type": str, "label": str}],
          }
        Also accepts a simpler format with raw service node/edge dicts.
        """
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: list[dict[str, Any]] = []
        # adjacency list: node_id -> list of (dest, edge_dict)
        self._adj: dict[str, list[tuple[str, dict[str, Any]]]] = {}

        for node in graph_data.get("nodes", []):
            nid = node.get("id", "")
            if nid:
                self._nodes[nid] = node
                self._adj.setdefault(nid, [])

        for edge in graph_data.get("edges", []):
            src = edge.get("src", edge.get("source", ""))
            dest = edge.get("dest", edge.get("target", ""))
            if src and dest:
                self._edges.append({**edge, "src": src, "dest": dest})
                self._adj.setdefault(src, []).append((dest, edge))
                self._adj.setdefault(dest, [])  # ensure dest exists in adj

    # ------------------------------------------------------------------
    # GraphEngineAdapter implementation
    # ------------------------------------------------------------------

    def get_nodes(self) -> list[dict[str, Any]]:
        return list(self._nodes.values())

    def get_edges(self) -> list[dict[str, Any]]:
        return self._edges

    def neighbors(self, node_id: str, relation_type: str | None = None) -> list[str]:
        result = []
        for dest, edge in self._adj.get(node_id, []):
            if relation_type is None or edge.get("type") == relation_type:
                result.append(dest)
        return result

    def find_path(self, src: str, dest: str, max_depth: int = 5) -> list[str] | None:
        """BFS shortest path. Returns list of node ids from src to dest, or None."""
        if src not in self._adj or dest not in self._adj:
            return None
        if src == dest:
            return [src]
        visited = {src}
        queue: list[list[str]] = [[src]]
        while queue:
            path = queue.pop(0)
            current = path[-1]
            if len(path) > max_depth:
                continue
            for neighbor, _ in self._adj.get(current, []):
                if neighbor == dest:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return None

    def query_by_relation(self, relation_type: str) -> list[dict[str, Any]]:
        return [e for e in self._edges if e.get("type") == relation_type]

    def stats(self) -> dict[str, int]:
        return {"nodes": len(self._nodes), "edges": len(self._edges)}
