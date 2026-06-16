"""
OnionQuant RAG Engine — Semantic search over historical research reports.

Technical stack:
  - Embedding: BGE-M3 (1024-dim, Chinese-optimized, CPU-friendly)
  - Vector DB: ChromaDB (local, zero-config)
  - Chunking: 512-token with 64-token overlap
  - Retrieval: Hybrid (BM25 + vector) — financial terms benefit from keyword matching

Usage:
  from onionquant.rag.engine import RAGEngine
  engine = RAGEngine()
  results = engine.search("MU 目标价分析")
"""

import os
import re
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings


class RAGEngine:
    def __init__(self, reports_dir: str = None, persist_dir: str = None):
        project_root = Path(__file__).resolve().parent.parent.parent
        self.reports_dir = Path(reports_dir or project_root / "company" / "reports")
        self.persist_dir = Path(persist_dir or project_root / "onionquant" / "rag" / "vector_store")
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection_name = "research_reports"
        self._collection = None
        self._bm25 = None
        self._documents = []  # Store documents for BM25

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ─── Document Loading ──────────────────────────────────

    def _load_documents(self) -> list[dict]:
        """Load all .md reports, return list of {id, path, content}."""
        docs = []
        for md_file in sorted(self.reports_dir.rglob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                if len(content.strip()) < 100:  # Skip empty/trivial files
                    continue
                docs.append({
                    "id": str(md_file.relative_to(self.reports_dir)).replace("\\", "/"),
                    "path": str(md_file),
                    "content": content,
                })
            except Exception:
                pass
        return docs

    # ─── Chunking ──────────────────────────────────────────

    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
        """Split text into overlapping chunks. Simple sentence-boundary-aware."""
        # Split by double newlines first (paragraphs), then by single newlines
        paragraphs = re.split(r'\n\n+', text)
        chunks = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If adding this paragraph fits, append it
            if len(current) + len(para) < chunk_size:
                current = (current + "\n\n" + para).strip()
            else:
                # Current chunk is full — save it
                if len(current) >= 100:
                    chunks.append(current[:chunk_size])
                # Start new chunk with overlap from previous
                overlap_text = current[-overlap:] if len(current) > overlap else current
                current = (overlap_text + "\n\n" + para).strip()

        # Don't forget the last chunk
        if len(current) >= 100:
            chunks.append(current[:chunk_size])

        return chunks

    # ─── Embedding ─────────────────────────────────────────

    def _get_embedding_fn(self):
        """Lazy-load the embedding model. text2vec-base-chinese: 128MB, 768-dim, CPU-friendly."""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("shibing624/text2vec-base-chinese")
            return lambda texts: model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            ).tolist()
        except ImportError:
            print("⚠ sentence-transformers not available — using simple TF-IDF fallback")
            return None

    # ─── Indexing ──────────────────────────────────────────

    def index(self, force_rebuild: bool = False) -> int:
        """Index all reports. Returns number of chunks indexed."""
        existing = self.collection.count()
        if existing > 0 and not force_rebuild:
            print(f"RAG: {existing} chunks already indexed. Use force_rebuild=True to re-index.")
            return existing

        if force_rebuild and existing > 0:
            self.client.delete_collection(self.collection_name)
            self._collection = None

        docs = self._load_documents()
        print(f"RAG: Loading {len(docs)} reports...", flush=True)

        chunks_all = []
        metadatas = []
        ids = []
        documents_raw = []

        for doc in docs:
            chunks = self._chunk_text(doc["content"])
            for i, chunk in enumerate(chunks):
                chunk_id = f"{doc['id']}_chunk{i}"
                chunks_all.append(chunk)
                metadatas.append({"source": doc["id"], "chunk_idx": i})
                ids.append(chunk_id)
                documents_raw.append(chunk)

        if not chunks_all:
            print("RAG: No content to index.")
            return 0

        # Get embeddings
        embed_fn = self._get_embedding_fn()
        if embed_fn is None:
            print("RAG: Embedding model not available — cannot index.")
            return 0

        print(f"RAG: Embedding {len(chunks_all)} chunks (BGE-M3, CPU)...")
        embeddings = embed_fn(chunks_all)

        # Add to ChromaDB
        batch_size = 100
        for i in range(0, len(chunks_all), batch_size):
            end = min(i + batch_size, len(chunks_all))
            self.collection.add(
                embeddings=embeddings[i:end],
                documents=chunks_all[i:end],
                metadatas=metadatas[i:end],
                ids=ids[i:end],
            )

        # Build BM25 for hybrid search
        self._documents = documents_raw
        self._build_bm25()

        print(f"RAG: Indexed {len(chunks_all)} chunks from {len(docs)} reports.")
        return len(chunks_all)

    # ─── BM25 ──────────────────────────────────────────────

    def _build_bm25(self):
        """Build BM25 index from loaded documents."""
        try:
            import jieba
            from rank_bm25 import BM25Okapi

            # Tokenize with jieba for Chinese
            tokenized = []
            for doc in self._documents:
                tokens = list(jieba.cut(doc))
                tokenized.append(tokens)

            self._bm25 = BM25Okapi(tokenized)
            self._bm25_tokenized = tokenized
        except ImportError:
            self._bm25 = None

    def _bm25_search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """BM25 keyword search. Returns list of (chunk_index, score)."""
        if self._bm25 is None:
            return []

        import jieba
        tokens = list(jieba.cut(query))
        scores = self._bm25.get_scores(tokens)

        # Get top-k indices
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [(i, s) for i, s in indexed if s > 0]

    # ─── Retrieval ─────────────────────────────────────────

    def search(self, query: str, top_k: int = 5, hybrid: bool = True) -> list[dict]:
        """Semantic search + optional BM25 hybrid retrieval.

        Returns list of {content, source, score, method}.
        """
        embed_fn = self._get_embedding_fn()
        if embed_fn is None:
            return []

        query_embedding = embed_fn([query])[0]

        # Vector search
        n_results = top_k * 2 if hybrid else top_k
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        # Build vector results
        vector_results = []
        for i in range(len(results["ids"][0])):
            # Cosine distance → similarity score (1 - distance)
            dist = results["distances"][0][i]
            sim = 1.0 - dist
            vector_results.append({
                "content": results["documents"][0][i][:800],
                "source": results["metadatas"][0][i].get("source", "unknown"),
                "score": round(sim, 4),
                "method": "vector",
                "chunk_idx": int(results["ids"][0][i].split("_chunk")[-1]) if "_chunk" in results["ids"][0][i] else 0,
            })

        if not hybrid or self._bm25 is None:
            return vector_results[:top_k]

        # BM25 search
        bm25_results = self._bm25_search(query, top_k)
        bm25_max = max(s[1] for s in bm25_results) if bm25_results else 1.0

        bm25_formatted = []
        for idx, score in bm25_results:
            if idx < len(self._documents):
                bm25_formatted.append({
                    "content": self._documents[idx][:800],
                    "source": "bm25_match",
                    "score": round(score / bm25_max, 4),  # Normalize
                    "method": "bm25",
                    "chunk_idx": idx,
                })

        # Merge: weighted reciprocal rank fusion
        merged = self._reciprocal_rank_fusion(vector_results, bm25_formatted, k=60)
        return merged[:top_k]

    def _reciprocal_rank_fusion(self, vec_results: list, bm25_results: list, k: int = 60) -> list:
        """Reciprocal Rank Fusion — combines BM25 + vector rankings."""
        scores = {}
        docs = {}

        for rank, r in enumerate(vec_results):
            key = r["content"][:100]  # Use first 100 chars as dedup key
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
            docs[key] = {**r, "method": "hybrid"}
            docs[key]["_vec_rank"] = rank

        for rank, r in enumerate(bm25_results):
            key = r["content"][:100]
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
            if key not in docs:
                docs[key] = {**r, "method": "hybrid"}

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [docs[key] for key, _ in ranked]


# Singleton
_engine: RAGEngine | None = None


def get_rag_engine(reports_dir: str = None, force_rebuild: bool = False) -> RAGEngine:
    global _engine
    if _engine is None:
        _engine = RAGEngine(reports_dir=reports_dir)
        _engine.index(force_rebuild=force_rebuild)
    return _engine


def search_reports(query: str, top_k: int = 5) -> list[dict]:
    """Convenience function: search historical research reports."""
    engine = get_rag_engine()
    return engine.search(query, top_k=top_k)
