"""LangChain GraphRAG: auto-extract entities/relationships from documents.

Uses LLMGraphTransformer to convert markdown documents (research reports,
pipeline reports, TASK_TRACKER) into structured graph triples.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class GraphRAGBuilder:
    """Transform project documents into knowledge graph triples."""

    def __init__(self, store=None):
        self._store = store

    # ── Document → Graph extraction ──────────────────────────────

    def ingest_markdown(self, filepath: str | Path) -> list[dict]:
        """Extract entities + relationships from a markdown file.

        Uses rule-based extraction for structured quant docs (pipeline
        reports, research notes) — no LLM call needed for most cases.
        Falls back to LLMGraphTransformer for unstructured docs.
        """
        path = Path(filepath)
        text = path.read_text(encoding="utf-8")

        triples = []
        # Pipeline reports: extract stock → metric → value
        if "pipeline_" in path.name:
            triples.extend(self._extract_pipeline_report(text))
        # Research reports: extract stock → factor → finding
        elif "research" in path.name.lower():
            triples.extend(self._extract_research_report(text))
        # Task tracker: extract task → department → status
        elif "TASK_TRACKER" in path.name:
            triples.extend(self._extract_task_tracker(text))
        # Generic: use LLM
        else:
            triples.extend(self._extract_with_llm(text))

        if self._store:
            self._store.add_relationships_batch(triples)
        return triples

    def _extract_pipeline_report(self, text: str) -> list:
        """Extract (stock, HAS_METRIC, metric_node) from pipeline reports."""
        import re

        triples = []
        # Parse markdown table
        tickers = re.findall(r"\*\*标的\*\*:\s*(.+)", text)
        if tickers:
            ticker_list = [t.strip() for t in tickers[0].split(",")]
            # Find metric rows
            for line in text.split("\n"):
                m = re.match(r"\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
                if m:
                    metric_name = m.group(1).strip()
                    metric_val = m.group(2).strip()
                    if metric_name not in ("指标", "------", ""):
                        for t in ticker_list:
                            metric_id = f"metric_{metric_name}_{t}"
                            triples.append(
                                (
                                    t,
                                    metric_id,
                                    "HAS_METRIC",
                                    {"name": metric_name, "raw_value": metric_val},
                                )
                            )
        return triples

    def _extract_research_report(self, text: str) -> list:
        """Extract stock → factor → finding from research reports."""
        import re

        triples = []
        ticker_pattern = re.findall(r"\b([A-Z]{2,5})\b", text)
        seen = set()
        for t in set(ticker_pattern):
            if t not in seen and 2 <= len(t) <= 5:
                seen.add(t)
                # Find factors near the ticker
                for factor in [
                    "momentum",
                    "volatility",
                    "value",
                    "growth",
                    "quality",
                    "sentiment",
                ]:
                    if factor in text.lower():
                        triples.append(
                            (
                                t,
                                f"factor_{factor}",
                                "EXPOSED_TO",
                                {"source": "research"},
                            )
                        )
        return triples

    def _extract_task_tracker(self, text: str) -> list:
        """Extract task → department → status from TASK_TRACKER.md."""
        import re

        triples = []
        for line in text.split("\n"):
            # Match: | Txxx | task_name | department | priority | status |
            m = re.match(
                r"\|\s*(T\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(P\d)\s*\|\s*(.+?)\s*\|",
                line,
            )
            if m:
                task_id, name, dept, priority, status = m.groups()
                triples.append(
                    (task_id, dept.strip(), "ASSIGNED_TO", {"task": name.strip()})
                )
                triples.append((task_id, f"priority_{priority}", "HAS_PRIORITY", {}))
                if "✅" in status:
                    triples.append(
                        (task_id, "status_done", "HAS_STATUS", {"value": "done"})
                    )
        return triples

    def _extract_with_llm(self, text: str) -> list:
        """Use LangChain LLMGraphTransformer for unstructured text."""
        try:
            from langchain_core.documents import Document
            from langchain_experimental.graph_transformers import LLMGraphTransformer
        except ImportError:
            logger.warning(
                "langchain-experimental not installed, skipping LLM extraction"
            )
            return []

        try:
            doc = Document(page_content=text[:8000])
            transformer = LLMGraphTransformer()
            graphs = transformer.convert_to_graph_documents([doc])
            triples = []
            for g in graphs:
                for edge in g.edges:
                    triples.append(
                        (
                            str(edge.source),
                            str(edge.target),
                            str(edge.relation),
                            edge.properties or {},
                        )
                    )
            return triples
        except Exception as e:
            logger.warning("LLM extraction failed: %s", e)
            return []

    # ── Batch ingestion ──────────────────────────────────────────

    def ingest_directory(self, dirpath: str | Path, glob_pattern: str = "*.md") -> int:
        """Ingest all markdown files in a directory."""
        count = 0
        for f in Path(dirpath).rglob(glob_pattern):
            if f.is_file():
                self.ingest_markdown(f)
                count += 1
        logger.info("Ingested %d files from %s", count, dirpath)
        return count
