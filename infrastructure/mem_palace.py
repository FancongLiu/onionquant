#!/usr/bin/env python3
"""MemPalace: Semantic memory retrieval with room-based organization.

Organizes memories into topical "rooms" and retrieves by semantic similarity
using LSA (Latent Semantic Analysis = TruncatedSVD on TF-IDF vectors).

Design:
  - Rooms = memory types (user, feedback, project, reference)
  - LSA provides meaning-based matching beyond keyword overlap
  - Optional sentence-transformers path for stronger embeddings (auto-detected)
  - Integrates with MemoryStore for strength/decay lifecycle

MemPalace is the "retrieval brain" — MemoryStore is the "storage backbone."
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics.pairwise import cosine_similarity

# ── Optional: sentence-transformers for stronger embeddings ──
try:
    from sentence_transformers import SentenceTransformer

    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False

# ── Frontmatter parser ──────────────────────────────────────


def _parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Parse YAML-style frontmatter from memory files. Returns (meta, body)."""
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].strip()
            for line in parts[1].strip().split("\n"):
                line = line.strip()
                if ":" in line:
                    key, _, val = line.partition(":")
                    meta[key.strip()] = val.strip()
    return meta, body


def _fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# ── Memory entry (lightweight, file-backed) ─────────────────


class MemoryCard:
    """A single memory from a .md file in the memory directory."""

    __slots__ = (
        "id",
        "name",
        "memory_type",
        "description",
        "content",
        "source_file",
        "room",
    )

    def __init__(
        self,
        source_file: Path,
        name: str = "",
        memory_type: str = "reference",
        description: str = "",
        content: str = "",
    ):
        self.id = _fingerprint(str(source_file))
        self.name = name
        self.memory_type = memory_type
        self.description = description
        self.content = content
        self.source_file = str(source_file)
        self.room = memory_type  # room = memory type by default

    @classmethod
    def from_file(cls, path: Path) -> "MemoryCard":
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        return cls(
            source_file=path,
            name=meta.get("name", path.stem),
            memory_type=meta.get("type", "reference"),
            description=meta.get("description", ""),
            content=body,
        )

    @property
    def search_text(self) -> str:
        """Composite text used for indexing: name + description + content."""
        return f"{self.name} {self.description} {self.content}"


# ── MemPalace ───────────────────────────────────────────────


class MemPalace:
    """Semantic memory retrieval with room-based organization.

    Usage:
        palace = MemPalace(memory_dir=Path("memory/"))
        results = palace.search("what does the chairman prefer about decisions?")
        for card, score in results:
            print(f"[{card.room}] {card.name}: {card.description} (score={score:.3f})")

        # Room-scoped search
        results = palace.search("coding style", room="feedback")

        # Build context injection
        ctx = palace.build_context("deployment safety rules", max_tokens=800)
    """

    def __init__(
        self,
        memory_dir: Path,
        use_embeddings: bool = False,
        lsa_components: int = 16,
    ):
        self.memory_dir = Path(memory_dir)
        self.use_embeddings = use_embeddings and _ST_AVAILABLE
        self.lsa_components = min(lsa_components, 64)

        # State
        self.cards: Dict[str, MemoryCard] = {}
        self.rooms: Dict[str, List[str]] = {}  # room_name -> [card_ids]

        # Vector index
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._lsa: Optional[TruncatedSVD] = None
        self._index_matrix = None  # LSA-transformed matrix
        self._index_ids: List[str] = []  # card IDs in index order
        self._st_model = None

        self._load()

    # ── Load ─────────────────────────────────────────────────

    def _load(self):
        """Scan memory directory, parse cards, build index."""
        if not self.memory_dir.exists():
            return

        # Load MEMORY.md to discover cards
        index_md = self.memory_dir / "MEMORY.md"
        known_files: set[str] = set()
        if index_md.exists():
            known_files = self._parse_memory_index(index_md)

        # Also scan for .md files directly
        for md_file in sorted(self.memory_dir.glob("*.md")):
            if md_file.name == "MEMORY.md":
                continue
            known_files.add(str(md_file))

        # Parse each memory file
        for file_path_str in sorted(known_files):
            fp = Path(file_path_str)
            if not fp.exists():
                continue
            try:
                card = MemoryCard.from_file(fp)
                self.cards[card.id] = card
                self.rooms.setdefault(card.room, []).append(card.id)
            except Exception:
                pass

        self._build_index()

    def _parse_memory_index(self, index_path: Path) -> set[str]:
        """Extract file references from MEMORY.md index."""
        files: set[str] = set()
        text = index_path.read_text(encoding="utf-8")
        # Match markdown links: [Title](file.md)
        for match in re.finditer(r"\[([^\]]+)\]\(([^)]+\.md)\)", text):
            rel_path = match.group(2)
            abs_path = self.memory_dir / rel_path
            if abs_path.exists():
                files.add(str(abs_path))
        return files

    def reload(self):
        """Re-scan memory directory and rebuild index."""
        self.cards.clear()
        self.rooms.clear()
        self._load()

    # ── Build index ──────────────────────────────────────────

    def _build_index(self):
        """Build LSA semantic index from card corpus."""
        if len(self.cards) < 2:
            self._index_ids = list(self.cards.keys())
            return

        corpus = []
        ids = []
        for card in self.cards.values():
            corpus.append(card.search_text)
            ids.append(card.id)

        # TF-IDF with character n-grams for subword similarity
        self._vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words="english",
            ngram_range=(1, 3),  # word + bigram + trigram
            analyzer="char_wb",  # character n-grams within word boundaries
            lowercase=True,
            sublinear_tf=True,  # 1 + log(tf) — dampens term frequency
        )
        tfidf = self._vectorizer.fit_transform(corpus)

        # LSA: reduce to latent semantic space
        n_components = min(self.lsa_components, tfidf.shape[1] - 1, len(corpus) - 1)
        if n_components >= 2:
            self._lsa = TruncatedSVD(
                n_components=n_components,
                random_state=42,
            )
            self._index_matrix = self._lsa.fit_transform(tfidf)
        else:
            self._lsa = None
            self._index_matrix = tfidf.toarray()

        self._index_ids = ids

        # Optional: sentence-transformers for stronger embeddings
        if self.use_embeddings:
            try:
                self._st_model = SentenceTransformer(
                    "all-MiniLM-L6-v2", device="cpu"
                )
            except Exception:
                self._st_model = None

    # ── Search ───────────────────────────────────────────────

    def search(
        self,
        query: str,
        k: int = 5,
        room: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[Tuple[MemoryCard, float]]:
        """Semantic search across memories.

        Args:
            query: Natural language query
            k: Max results to return
            room: Optional room filter (user/feedback/project/reference)
            min_score: Minimum similarity threshold

        Returns:
            List of (MemoryCard, score) sorted by descending relevance
        """
        if not self.cards:
            return []

        # Determine candidate pool
        if room and room in self.rooms:
            candidate_ids = set(self.rooms[room])
        else:
            candidate_ids = set(self.cards.keys())

        if not candidate_ids:
            return []

        # If we have a proper index, use semantic search
        if self._lsa is not None and self._vectorizer is not None:
            results = self._semantic_search(query, candidate_ids, k)
        elif self._vectorizer is not None:
            results = self._tfidf_search(query, candidate_ids, k)
        else:
            results = self._keyword_search(query, candidate_ids, k)

        # Filter by min_score
        results = [(c, s) for c, s in results if s >= min_score]
        return results[:k]

    def _semantic_search(
        self, query: str, candidate_ids: set, k: int
    ) -> List[Tuple[MemoryCard, float]]:
        """LSA-based semantic search."""
        # Also try embedding-based if available
        if self._st_model is not None:
            return self._embedding_search(query, candidate_ids, k)

        query_tfidf = self._vectorizer.transform([query])
        query_lsa = self._lsa.transform(query_tfidf)

        scored = []
        for i, card_id in enumerate(self._index_ids):
            if card_id not in candidate_ids:
                continue
            card = self.cards.get(card_id)
            if card is None:
                continue
            score = float(cosine_similarity(query_lsa, self._index_matrix[i : i + 1])[0, 0])
            if score > 0:
                scored.append((card, score))

        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def _tfidf_search(
        self, query: str, candidate_ids: set, k: int
    ) -> List[Tuple[MemoryCard, float]]:
        """TF-IDF cosine similarity search (fallback when LSA can't be built)."""
        query_vec = self._vectorizer.transform([query])
        tfidf_matrix = self._index_matrix  # raw TF-IDF when no LSA

        scored = []
        for i, card_id in enumerate(self._index_ids):
            if card_id not in candidate_ids:
                continue
            card = self.cards.get(card_id)
            if card is None:
                continue
            score = float(cosine_similarity(query_vec, tfidf_matrix[i : i + 1])[0, 0])
            if score > 0:
                scored.append((card, score))

        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def _embedding_search(
        self, query: str, candidate_ids: set, k: int
    ) -> List[Tuple[MemoryCard, float]]:
        """Sentence-transformer embedding search (strongest semantic match)."""
        query_emb = self._st_model.encode([query], normalize_embeddings=True)[0]

        # Build embedding matrix on-demand for candidates
        candidate_list = [
            (cid, self.cards[cid])
            for cid in self._index_ids
            if cid in candidate_ids and cid in self.cards
        ]
        texts = [card.search_text for _, card in candidate_list]
        doc_embs = self._st_model.encode(texts, normalize_embeddings=True)

        scored = []
        for j, (cid, card) in enumerate(candidate_list):
            score = float(np.dot(query_emb, doc_embs[j]))
            if score > 0:
                scored.append((card, score))

        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def _keyword_search(
        self, query: str, candidate_ids: set, k: int
    ) -> List[Tuple[MemoryCard, float]]:
        """Simple keyword overlap fallback (tiny corpus)."""
        query_words = set(query.lower().split())
        scored = []
        for cid in candidate_ids:
            card = self.cards.get(cid)
            if card is None:
                continue
            text_words = set(card.search_text.lower().split())
            if not query_words:
                continue
            score = len(query_words & text_words) / len(query_words)
            if score > 0:
                scored.append((card, score))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    # ── Room operations ──────────────────────────────────────

    def relevant_rooms(self, query: str) -> List[Tuple[str, float]]:
        """Find which rooms are most relevant to a query.

        Returns rooms ranked by relevance score.
        """
        if not self.rooms or len(self.rooms) <= 1:
            return [(room, 1.0) for room in self.rooms]

        # Search broadly, then aggregate scores by room
        results = self.search(query, k=len(self.cards))
        room_scores: Dict[str, float] = {}
        for card, score in results:
            room_scores[card.room] = max(
                room_scores.get(card.room, 0.0), score
            )

        ranked = sorted(room_scores.items(), key=lambda x: -x[1])
        return ranked

    def list_rooms(self) -> Dict[str, int]:
        """Return room name -> card count."""
        return {room: len(ids) for room, ids in self.rooms.items()}

    def get_room_cards(self, room: str) -> List[MemoryCard]:
        """Get all cards in a room."""
        return [self.cards[cid] for cid in self.rooms.get(room, []) if cid in self.cards]

    def get_card(self, card_id: str) -> Optional[MemoryCard]:
        return self.cards.get(card_id)

    # ── Context builder ──────────────────────────────────────

    def build_context(
        self,
        query: str,
        max_tokens: int = 800,
        room: Optional[str] = None,
    ) -> str:
        """Build a context injection string relevant to a query.

        Finds relevant memories, sorts by relevance, and packs them
        into a token budget.
        """
        results = self.search(query, k=len(self.cards), room=room)
        if not results:
            return ""

        lines = []
        token_est = 0
        for card, score in results:
            # Use description as summary, content as body — trim to budget
            snippet = card.description or card.content[:200]
            line = f"- [{card.room}] {card.name}: {snippet}"
            est = len(line.split()) * 1.3
            if token_est + est > max_tokens:
                # Try shorter version
                line_short = f"- [{card.room}] {card.name}"
                est_short = len(line_short.split()) * 1.3
                if token_est + est_short > max_tokens:
                    continue
                line = line_short
                est = est_short
            lines.append(line)
            token_est += est

        return "\n".join(lines)

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "total_cards": len(self.cards),
            "rooms": self.list_rooms(),
            "index_dim": (
                self._index_matrix.shape[1] if self._index_matrix is not None else 0
            ),
            "has_lsa": self._lsa is not None,
            "has_embeddings": self._st_model is not None,
        }


# ── Integration with MemoryStore ─────────────────────────────


def build_palace_from_store(
    memory_dir: Path,
    store_path: Optional[Path] = None,
) -> MemPalace:
    """Factory: build a MemPalace from a memory directory + optional MemoryStore.

    If the memory directory exists and has files, use it directly.
    Otherwise, try to seed from MemoryStore JSONL if available.
    """
    palace = MemPalace(memory_dir=memory_dir)

    # If the memory dir is empty but we have a MemoryStore, seed cards from it
    if len(palace.cards) == 0 and store_path and store_path.exists():
        # Read MemoryStore entries and create cards
        from infrastructure.memory_store import MemoryStore

        ms = MemoryStore(store_path)
        for entry in ms.entries.values():
            if not entry.is_active:
                continue
            # Write each entry as a memory file
            safe_name = re.sub(r"[^\w\-]", "_", entry.content[:40])
            card_path = memory_dir / f"ms_{safe_name}_{entry.id[:8]}.md"
            if not card_path.exists():
                card_path.write_text(
                    f"---\nname: {safe_name}\ntype: {entry.category}\n"
                    f"description: {entry.content[:100]}\n---\n\n{entry.content}\n",
                    encoding="utf-8",
                )
        palace.reload()

    return palace


# ── Demo ────────────────────────────────────────────────────


def main():
    """Demo with sample memories."""
    import tempfile

    tmpdir = Path(tempfile.mkdtemp()) / "memory"
    tmpdir.mkdir(parents=True)

    # Create sample memory files
    memories = {
        "user_profile.md": """---
name: user-profile
description: 董事长角色与偏好
type: user
---

用户自称"董事长"，偏好证据驱动决策，重视安全护栏。
环境: Windows 11 + WSL + Python 3.12。
""",
        "feedback.md": """---
name: feedback-rules
description: 用户反馈规则
type: feedback
---

规则1: 不确定的事情必须先问，不能猜。
规则2: 安全护栏不可妥协 — 付费/敏感文件/密钥必须请示。
规则3: 先操作再回应用户，不要先说再操作。
""",
        "project_state.md": """---
name: project-state
description: 项目当前状态
type: project
---

49个任务完成，3个cron自动巡航。
持仓: DXYZ $28,000 @ ~$47.62。
日耗目标: ¥5-8。
""",
        "key_decisions.md": """---
name: key-decisions
description: 关键架构决策
type: project
---

不手搓铁律: 写代码前必须搜索GitHub/论文/开源。
技术栈: OpenBB + Qlib + Polars + NautilusTrader。
三阶段并行: 快速验证 → 深度构建 → 前沿突破。
""",
        "external_references.md": """---
name: external-references
description: 外部资源引用
type: reference
---

量化工具: NautilusTrader (回测), Qlib (因子), Riskfolio-Lib (风险)
前端: localhost:8765, 隧道: cloudflared
CI: GitHub Actions 每次push触发lint+test
""",
    }

    for fname, content in memories.items():
        (tmpdir / fname).write_text(content, encoding="utf-8")

    # Write MEMORY.md index
    index_lines = ["# MEMORY.md\n"]
    for fname in memories:
        name = fname.replace(".md", "").replace("_", " ")
        index_lines.append(f"- [{name}]({fname}) — description\n")
    (tmpdir / "MEMORY.md").write_text("\n".join(index_lines), encoding="utf-8")

    # Build palace
    palace = MemPalace(memory_dir=tmpdir)

    print(f"Stats: {palace.stats()}")
    print()

    # Test searches
    queries = [
        "董事长喜欢什么样的决策方式？",
        "安全规则是什么？",
        "项目用什么技术栈？",
        "当前持仓是什么？",
        "CI是怎么配置的？",
    ]

    for q in queries:
        print(f"Query: {q}")
        results = palace.search(q, k=3)
        for card, score in results:
            print(f"  [{card.room}] {card.name} (score={score:.3f})")
        print()

    # Test room search
    print("Rooms:", palace.list_rooms())
    print("Relevant rooms for '安全规则':", palace.relevant_rooms("安全规则"))

    # Test context builder
    ctx = palace.build_context("security rules and preferences", max_tokens=300)
    print(f"\nContext (300 tokens):\n{ctx}")

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir.parent)


if __name__ == "__main__":
    main()
