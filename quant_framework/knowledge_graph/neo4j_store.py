"""Neo4j-backed knowledge graph store for quant relationships.

Stores: stock linkages, factor dependencies, supply chains, sector maps.
Supports fallback to NetworkX when Neo4j is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import networkx as nx

logger = logging.getLogger(__name__)


class QuantGraphStore:
    """Neo4j graph store with NetworkX fallback for quant knowledge."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "",
        database: str = "neo4j",
    ):
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._driver = None
        self._nx = nx.DiGraph()
        self._connected = False
        self._try_connect()

    def _try_connect(self) -> bool:
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
            self._driver.verify_connectivity()
            self._connected = True
            logger.info("Neo4j connected: %s", self._uri)
            return True
        except Exception as e:
            logger.warning("Neo4j unavailable (%s), using NetworkX fallback", e)
            self._connected = False
            self._driver = None
            return False

    @property
    def backend(self) -> str:
        return "neo4j" if self._connected else "networkx"

    # ── Node operations ──────────────────────────────────────────

    def add_node(self, label: str, properties: dict[str, Any]) -> None:
        if self._connected:
            self._run(
                f"MERGE (n:{label} {{id: $id}}) SET n += $props",
                {"id": properties["id"], "props": properties},
            )
        else:
            self._nx.add_node(properties["id"], label=label, **properties)

    def add_nodes_batch(self, label: str, records: list[dict[str, Any]]) -> None:
        for r in records:
            self.add_node(label, r)

    # ── Relationship operations ──────────────────────────────────

    def add_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: Optional[dict[str, Any]] = None,
    ) -> None:
        props = properties or {}
        if self._connected:
            self._run(
                f"""
                MATCH (a {{id: $from_id}})
                MATCH (b {{id: $to_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r += $props
                """,
                {"from_id": from_id, "to_id": to_id, "props": props},
            )
        else:
            edge_data = {"rel_type": rel_type, **props}
            self._nx.add_edge(from_id, to_id, **edge_data)

    def add_relationships_batch(
        self,
        triples: list[tuple[str, str, str, Optional[dict[str, Any]]]],
    ) -> None:
        for from_id, to_id, rel_type, props in triples:
            self.add_relationship(from_id, to_id, rel_type, props)

    # ── Query ────────────────────────────────────────────────────

    def query_neighbors(self, node_id: str, depth: int = 2) -> dict[str, Any]:
        """Return subgraph around a node."""
        if self._connected:
            records = self._run(
                f"""
                MATCH (n {{id: $id}})-[r*1..{depth}]-(m)
                RETURN DISTINCT m.id AS related, type(r[0]) AS rel
                """,
                {"id": node_id},
            )
            return {"node": node_id, "related": [dict(r) for r in records]}
        else:
            if node_id not in self._nx:
                return {"node": node_id, "related": []}
            nodes = set()
            for _depth in range(1, depth + 1):
                for src, dst in self._nx.edges():
                    if src == node_id:
                        nodes.add(dst)
                    elif dst == node_id:
                        nodes.add(src)
            return {"node": node_id, "related": [{"id": n} for n in nodes]}

    def get_full_graph(self) -> nx.DiGraph:
        """Return full graph as NetworkX DiGraph."""
        if self._connected:
            g = nx.DiGraph()
            nodes = self._run("MATCH (n) RETURN n.id AS id, labels(n) AS labels, n")
            for n in nodes:
                g.add_node(n["id"], **(n.get("n") or {}))
            edges = self._run(
                "MATCH (a)-[r]->(b) RETURN a.id AS src, b.id AS dst, type(r) AS rel, r"
            )
            for e in edges:
                g.add_edge(e["src"], e["dst"], rel_type=e["rel"])
            return g
        return self._nx.copy()

    def clear(self) -> None:
        if self._connected:
            self._run("MATCH (n) DETACH DELETE n")
        else:
            self._nx.clear()

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._connected = False

    # ── Internal ─────────────────────────────────────────────────

    def _run(self, query: str, params: Optional[dict] = None):
        if not self._driver:
            raise RuntimeError("Neo4j not connected")
        with self._driver.session(database=self._database) as session:
            return list(session.run(query, params or {}))


# ── Pre-built query helpers ──────────────────────────────────────


def query_stock_supply_chain(graph: QuantGraphStore, ticker: str) -> list[dict]:
    """Get supply chain network for a stock."""
    result = graph.query_neighbors(ticker, depth=3)
    return result["related"]


def query_sector_stocks(graph: QuantGraphStore, sector: str) -> list[str]:
    """List all stocks in a given sector."""
    if graph.backend == "neo4j":
        records = graph._run(
            "MATCH (s:Stock {sector: $sector}) RETURN s.id AS ticker",
            {"sector": sector},
        )
        return [r["ticker"] for r in records]
    else:
        return [
            n
            for n, d in graph._nx.nodes(data=True)
            if d.get("label") == "Stock" and d.get("sector") == sector
        ]


def query_factor_tree(graph: QuantGraphStore, factor_name: str) -> dict:
    """Get factor → sub-factor dependency tree."""
    result = graph.query_neighbors(factor_name, depth=2)
    return {"factor": factor_name, "dependencies": result["related"]}
