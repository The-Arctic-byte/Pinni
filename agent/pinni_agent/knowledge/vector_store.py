"""Vector Database with hybrid BM25 + dense retrieval and Ollama/Hashing embeddings.

Supports:
- Dense embeddings via Ollama (nomic-embed-text) or deterministic 512-d feature hashing fallback.
- BM25 lexical ranking.
- Reciprocal Rank Fusion (RRF) for robust search.
- Metadata filtering (category, scale, place, need, risk).
- Semantic story matching against user profile interests.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..config import Settings, default_settings
from ..llm import OllamaLLM

_TOKEN = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "i", "in", "is", "it", "its", "me", "my", "of", "on", "or", "our", "so", "that",
    "the", "this", "to", "was", "we", "what", "when", "which", "who", "why", "with",
    "you", "your", "do", "does", "did", "can", "could", "should", "would", "about",
    "than", "then", "them", "they", "there", "these", "those", "how", "into", "over",
    "under", "more", "most", "less"
}


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOP_WORDS]


class BM25:
    """Standard BM25 lexical index."""

    def __init__(self, docs: List[str], k1: float = 1.4, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.toks = [tokenize(d) for d in docs]
        self.doc_len = [len(t) for t in self.toks]
        self.avg_len = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        self.tf = [Counter(t) for t in self.toks]
        df = Counter(w for t in self.toks for w in set(t))
        n = len(self.toks)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}

    def scores(self, query: str) -> np.ndarray:
        q = tokenize(query)
        out = np.zeros(len(self.toks), dtype=np.float32)
        if not self.toks:
            return out
        for i, tf in enumerate(self.tf):
            s = 0.0
            for w in q:
                f = tf.get(w, 0)
                if f > 0:
                    idf = self.idf.get(w, 0.0)
                    denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avg_len or 1.0))
                    s += idf * (f * (self.k1 + 1)) / (denom or 1.0)
            out[i] = s
        return out


class HashingEmbedder:
    """Deterministic feature-hashing lexical embedder (512-dim)."""

    dim = 512
    name = "hashing-512"
    semantic = False

    def embed(self, texts: List[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, t in enumerate(texts):
            toks = tokenize(t)
            feats = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
            for f in feats:
                h = int(hashlib.md5(f.encode("utf-8")).hexdigest(), 16)
                out[row, h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
            norm = np.linalg.norm(out[row])
            if norm > 0:
                out[row] /= norm
        return out


class OllamaEmbedder:
    """Semantic embedder backed by Ollama."""

    semantic = True

    def __init__(self, llm: OllamaLLM):
        self.llm = llm
        self.name = f"ollama:{llm.embed_model}"
        self._dim: Optional[int] = None

    def embed(self, texts: List[str]) -> np.ndarray:
        raw = self.llm.embed(texts)
        arr = np.array(raw, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms


@dataclass
class VectorDoc:
    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    vector: Optional[np.ndarray] = None


@dataclass
class SearchHit:
    id: str
    score: float
    metadata: Dict[str, Any]
    dense_rank: Optional[int] = None
    bm25_rank: Optional[int] = None
    fused_score: float = 0.0


class VectorStore:
    """In-memory Vector Store with hybrid BM25 + dense retrieval and metadata filtering."""

    def __init__(self, settings: Optional[Settings] = None, llm: Optional[OllamaLLM] = None):
        self.s = settings or default_settings
        self.llm = llm or OllamaLLM(self.s)
        self.documents: Dict[str, VectorDoc] = {}
        self._embedder = self._init_embedder()
        self._bm25: Optional[BM25] = None
        self._dirty_bm25 = True

    def _init_embedder(self):
        try:
            status = self.llm.status()
            if status.get("available") and status.get("embed_model_ready"):
                return OllamaEmbedder(self.llm)
        except Exception:
            pass
        return HashingEmbedder()

    @property
    def embedder_name(self) -> str:
        return getattr(self._embedder, "name", "unknown")

    def add_story(self, story: Dict[str, Any]) -> None:
        """Index a story from its title, explanation and tags."""
        story_id = story["id"]
        title_en = story.get("title", {}).get("en", "")
        exp = story.get("explanation", {})
        known = " ".join(k.get("en", "") for k in exp.get("known", []))
        for_you = exp.get("forYou", {}).get("en", "")
        tags = " ".join(story.get("tags", []))
        text = f"{title_en}. {known}. {for_you}. Tags: {tags}"

        meta = {
            "type": "story",
            "scale": story.get("scale"),
            "placeId": story.get("placeId"),
            "category": story.get("category"),
            "risk": story.get("risk"),
            "importance": story.get("importance", 0.5),
            "affects": story.get("affects", []),
            "tags": story.get("tags", []),
            "sources": [s.get("name") for s in story.get("sources", [])],
        }
        self.add_document(doc_id=story_id, text=text, metadata=meta)

    def add_document(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        meta = metadata or {}
        vec = self._embedder.embed([text])[0]
        self.documents[doc_id] = VectorDoc(id=doc_id, text=text, metadata=meta, vector=vec)
        self._dirty_bm25 = True

    def _ensure_bm25(self) -> None:
        if self._dirty_bm25 or self._bm25 is None:
            docs = [doc.text for doc in self.documents.values()]
            self._bm25 = BM25(docs)
            self._dirty_bm25 = False

    def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        alpha: float = 0.5,
    ) -> List[SearchHit]:
        """Hybrid search combining dense vector cosine similarity and BM25 using RRF."""
        if not self.documents:
            return []

        doc_keys = list(self.documents.keys())
        doc_list = [self.documents[k] for k in doc_keys]

        # 1. Apply hard metadata filters if provided
        filtered_indices = []
        for idx, doc in enumerate(doc_list):
            m = doc.metadata
            keep = True
            if filters:
                if "category" in filters and m.get("category") != filters["category"]:
                    keep = False
                if "scale" in filters and m.get("scale") != filters["scale"]:
                    keep = False
                if "placeId" in filters and m.get("placeId") != filters["placeId"]:
                    keep = False
                if "risk" in filters and m.get("risk") != filters["risk"]:
                    keep = False
                if "exclude_categories" in filters and m.get("category") in filters["exclude_categories"]:
                    keep = False
                if "exclude_tags" in filters and any(t in filters["exclude_tags"] for t in m.get("tags", [])):
                    keep = False
                if "exclude_sources" in filters and any(s in filters["exclude_sources"] for s in m.get("sources", [])):
                    keep = False
            if keep:
                filtered_indices.append(idx)

        if not filtered_indices:
            return []

        # 2. Dense similarity
        q_vec = self._embedder.embed([query])[0]
        dense_scores = []
        for idx in filtered_indices:
            d_vec = doc_list[idx].vector
            sim = float(np.dot(q_vec, d_vec)) if d_vec is not None else 0.0
            dense_scores.append((idx, sim))
        dense_scores.sort(key=lambda x: x[1], reverse=True)
        dense_ranks = {idx: rank for rank, (idx, _) in enumerate(dense_scores, 1)}

        # 3. BM25 similarity
        self._ensure_bm25()
        bm25_all = self._bm25.scores(query)
        bm25_scores = [(idx, float(bm25_all[idx])) for idx in filtered_indices]
        bm25_scores.sort(key=lambda x: x[1], reverse=True)
        bm25_ranks = {idx: rank for rank, (idx, _) in enumerate(bm25_scores, 1)}

        # 4. Reciprocal Rank Fusion (RRF) with constant k=60
        hits = []
        k_rrf = 60.0
        for idx in filtered_indices:
            d_rank = dense_ranks[idx]
            b_rank = bm25_ranks[idx]
            rrf_score = (alpha / (k_rrf + d_rank)) + ((1.0 - alpha) / (k_rrf + b_rank))
            doc = doc_list[idx]
            hits.append(
                SearchHit(
                    id=doc.id,
                    score=rrf_score,
                    metadata=doc.metadata,
                    dense_rank=d_rank,
                    bm25_rank=b_rank,
                    fused_score=rrf_score,
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def count(self) -> int:
        return len(self.documents)
