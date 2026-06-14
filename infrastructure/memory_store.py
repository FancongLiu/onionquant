#!/usr/bin/env python3
"""Lightweight persistent memory store with semantic search, strength decay, dedup.

Inspired by agentmemory's 4-layer model, implemented in pure Python with sklearn.
Designed for ~200-entry memory systems (not millions). Zero new dependencies.

Key patterns from agentmemory:
  - Strength decay: memories weaken on neglect, strengthen on access
  - SHA-256 dedup: prevent duplicate entries within 5-min window
  - Hybrid retrieval: TF-IDF (keyword) + optional FAISS (vector) when available
  - Token budget: select top-k entries within context window budget
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class MemoryEntry:
    """A single memory with decay-based lifecycle."""

    id: str  # SHA-256 fingerprint
    content: str  # The memory text
    category: str = "general"  # user, feedback, project, reference, decision, bug
    strength: float = 1.0  # 1.0 = fresh, decays toward 0.1 floor
    access_count: int = 0
    last_accessed: str = ""  # ISO timestamp
    created_at: str = ""  # ISO timestamp
    source_file: str = ""  # Which MEMORY.md or index file
    supersedes: list[str] = field(default_factory=list)
    is_active: bool = True

    def access(self):
        self.access_count += 1
        self.last_accessed = datetime.now().isoformat()
        self.strength = min(1.0, self.strength + 0.05)

    def decay(self, factor: float = 0.95):
        self.strength = max(0.1, self.strength * factor)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "strength": round(self.strength, 4),
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "created_at": self.created_at,
            "source_file": self.source_file,
            "supersedes": self.supersedes,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        return cls(
            **{
                k: d.get(k, v.default if hasattr(v, "default") else v)
                for k, v in cls.__dataclass_fields__.items()
            }
        )


class MemoryStore:
    """Persistent memory index with TF-IDF search and strength decay.

    Usage:
        store = MemoryStore(Path("memory/store.jsonl"))
        store.add("Project uses sklearn for factor computation", category="decision")
        results = store.search("factor computation library", k=5)
        context = store.build_context_budget(max_tokens=2000)
        store.decay_all()  # call periodically (weekly cron)
    """

    def __init__(self, store_path: Path, memory_dir: Path | None = None):
        self.store_path = Path(store_path)
        self.memory_dir = memory_dir
        self.entries: dict[str, MemoryEntry] = {}
        self._vectorizer: TfidfVectorizer | None = None
        self._tfidf_matrix = None
        self._corpus: list[str] = []
        self._corpus_ids: list[str] = []
        self._load()

    # ── CRUD ───────────────────────────────────────────────

    def _load(self):
        if self.store_path.exists():
            for line in self.store_path.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    try:
                        entry = MemoryEntry.from_dict(json.loads(line))
                        if entry.is_active:
                            self.entries[entry.id] = entry
                    except (json.JSONDecodeError, KeyError):
                        pass
        self._rebuild_index()

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(e.to_dict(), ensure_ascii=False) for e in self.entries.values()
        ]
        self.store_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def add(
        self, content: str, category: str = "general", source_file: str = ""
    ) -> str:
        """Add a memory entry. Returns the entry ID (SHA-256 fingerprint)."""
        fingerprint = self._fingerprint(content)
        now = datetime.now().isoformat()

        if fingerprint in self.entries:
            existing = self.entries[fingerprint]
            if self._is_duplicate(existing, content):
                existing.access()
                existing.strength = min(1.0, existing.strength + 0.1)
                self._save()
                return fingerprint

        entry = MemoryEntry(
            id=fingerprint,
            content=content,
            category=category,
            created_at=now,
            last_accessed=now,
            source_file=source_file,
        )
        self.entries[fingerprint] = entry
        self._corpus.append(content)
        self._corpus_ids.append(fingerprint)
        self._rebuild_index()
        self._save()
        return fingerprint

    def get(self, entry_id: str) -> MemoryEntry | None:
        e = self.entries.get(entry_id)
        if e:
            e.access()
            self._save()
        return e

    def deactivate(self, entry_id: str):
        """Soft-delete: mark inactive without destroying history."""
        if entry_id in self.entries:
            self.entries[entry_id].is_active = False
            self._save()
            self._rebuild_index()

    # ── Fingerprint & Dedup ────────────────────────────────

    @staticmethod
    def _fingerprint(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @staticmethod
    def _is_duplicate(existing: MemoryEntry, new_content: str) -> bool:
        """Check if new content is a near-duplicate of existing entry."""
        # Exact match on fingerprint (already checked)
        # Time-window check: same content within 5 min = duplicate
        if existing.last_accessed:
            last = datetime.fromisoformat(existing.last_accessed)
            if datetime.now() - last < timedelta(minutes=5):
                return True
        # Jaccard similarity on word sets for near-duplicate detection
        old_words = set(existing.content.lower().split())
        new_words = set(new_content.lower().split())
        if not old_words or not new_words:
            return False
        jaccard = len(old_words & new_words) / len(old_words | new_words)
        return jaccard > 0.85

    # ── TF-IDF Index ───────────────────────────────────────

    def _rebuild_index(self):
        active = [e for e in self.entries.values() if e.is_active]
        self._corpus = [e.content for e in active]
        self._corpus_ids = [e.id for e in active]
        if len(self._corpus) >= 2:
            self._vectorizer = TfidfVectorizer(
                max_features=500,
                stop_words="english",
                ngram_range=(1, 2),
                lowercase=True,
            )
            self._tfidf_matrix = self._vectorizer.fit_transform(self._corpus)
        else:
            self._vectorizer = None
            self._tfidf_matrix = None

    def search(
        self, query: str, k: int = 5, min_strength: float = 0.0
    ) -> list[tuple[MemoryEntry, float]]:
        """Search memories by TF-IDF cosine similarity. Returns (entry, score)."""
        if self._vectorizer is None or self._tfidf_matrix is None:
            # Fallback: keyword match
            results = []
            query_lower = query.lower()
            for e in self.entries.values():
                if not e.is_active or e.strength < min_strength:
                    continue
                score = sum(
                    1 for w in query_lower.split() if w in e.content.lower()
                ) / max(len(query_lower.split()), 1)
                if score > 0:
                    results.append((e, score))
            results.sort(key=lambda x: -x[1])
            return results[:k]

        query_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self._tfidf_matrix).flatten()

        scored = []
        for i, score in enumerate(scores):
            if score <= 0:
                continue
            e = self.entries.get(self._corpus_ids[i])
            if e and e.is_active and e.strength >= min_strength:
                scored.append((e, float(score)))

        scored.sort(key=lambda x: (-x[1], -x[0].strength))
        return scored[:k]

    # ── Strength Decay ─────────────────────────────────────

    def decay_all(self, factor: float = 0.95):
        """Apply strength decay to all entries. Call weekly."""
        for e in self.entries.values():
            if e.is_active:
                e.decay(factor)
        # Archive very weak entries
        to_archive = [
            eid for eid, e in self.entries.items() if e.strength < 0.15 and e.is_active
        ]
        for eid in to_archive:
            self.entries[eid].is_active = False
        self._rebuild_index()
        self._save()

    def strengthen_category(self, category: str, boost: float = 0.15):
        """Boost all entries in a category (e.g., when user asks about it)."""
        for e in self.entries.values():
            if e.category == category and e.is_active:
                e.strength = min(1.0, e.strength + boost)
        self._save()

    # ── Context Budget Builder ──────────────────────────────

    def build_context_budget(
        self,
        max_tokens: int = 2000,
        recency_weight: float = 0.3,
        strength_weight: float = 0.4,
        category_boost: list[str] | None = None,
    ) -> str:
        """Build a context injection string within token budget.

        Selects entries by composite score: recency * w_r + strength * w_s + access * w_a
        Stops when cumulative estimated tokens exceed max_tokens.
        """
        if not self.entries:
            return ""

        now = datetime.now()
        scored = []
        for e in self.entries.values():
            if not e.is_active:
                continue
            # Recency score (days since last access, capped at 30)
            days = 30
            if e.last_accessed:
                try:
                    days = (now - datetime.fromisoformat(e.last_accessed)).days
                except (ValueError, TypeError):
                    pass
            recency = max(0, 1.0 - days / 30)

            # Composite score
            score = (
                recency * recency_weight
                + e.strength * strength_weight
                + min(e.access_count / 10, 1.0) * 0.2
                + min(len(e.content) / 200, 1.0) * 0.1
            )

            # Category boost
            if category_boost and e.category in category_boost:
                score *= 1.5

            scored.append((e, score))

        scored.sort(key=lambda x: -x[1])

        # Build within token budget
        lines = []
        token_estimate = 0
        for e, score in scored:
            est_tokens = len(e.content.split()) * 1.3  # rough estimate
            if token_estimate + est_tokens > max_tokens:
                continue
            lines.append(f"- [{e.category}] {e.content} (strength={e.strength:.2f})")
            token_estimate += est_tokens

        return "\n".join(lines)

    # ── Stats ───────────────────────────────────────────────

    def stats(self) -> dict:
        active = [e for e in self.entries.values() if e.is_active]
        categories = {}
        for e in active:
            categories[e.category] = categories.get(e.category, 0) + 1
        return {
            "total_entries": len(self.entries),
            "active_entries": len(active),
            "avg_strength": round(float(np.mean([e.strength for e in active])), 4)
            if active
            else 0,
            "categories": categories,
            "corpus_size": len(self._corpus),
        }


# ── Demo ────────────────────────────────────────────────────


def main():
    import tempfile

    path = Path(tempfile.gettempdir()) / "demo_memory_store.jsonl"

    store = MemoryStore(path)

    # Add some memories
    store.add(
        "Project uses sklearn Ridge/RandomForest/XGBoost for factor→return prediction",
        "decision",
    )
    store.add("Windows GBK encoding causes emoji failures — use ASCII text only", "bug")
    store.add(
        "Data quality monitoring has 5 checks: NaN, freshness, outliers, completeness, lookahead",
        "project",
    )
    store.add(
        "Chairman prefers evidence-based decisions over theoretical cleanliness",
        "feedback",
    )
    store.add(
        "TradingAgents uses LangGraph StateGraph for multi-agent orchestration",
        "reference",
    )

    print(f"Store: {store.stats()}")
    print()

    # Search
    results = store.search("machine learning prediction factors")
    print("Search 'machine learning prediction factors':")
    for e, score in results:
        print(
            f"  [{e.category}] score={score:.3f} strength={e.strength:.2f} — {e.content[:80]}"
        )

    print()

    # Context budget
    ctx = store.build_context_budget(max_tokens=200)
    print(f"Context budget (200 tokens):\n{ctx}")

    # Cleanup
    path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
