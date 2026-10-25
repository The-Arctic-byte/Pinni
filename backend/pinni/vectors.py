"""Vector store (Chroma): published stories and their embeddings, for content-based ranking.

Embeddings come from Ollama (a multilingual model, Track B1) when PINNI_OLLAMA_URL is set.
Without it a deterministic hashing embedder is used, so development and tests need no model."""

import hashlib
import json
import math
import re
import secrets
import urllib.request

import chromadb
from chromadb.config import Settings as ChromaSettings

DIMENSIONS = 512
_WORD = re.compile(r"\w+", re.UNICODE)


class HashEmbedder:
    """Bag of words hashed into a fixed vector. Only matches shared words, but needs no model."""

    name = "hash"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * DIMENSIONS
            for word in _WORD.findall(text.lower()):
                h = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "big")
                vec[h % DIMENSIONS] += 1.0 if (h >> 63) & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class OllamaEmbedder:
    def __init__(self, url: str, model: str):
        self.url = url.rstrip("/")
        self.model = model
        self.name = f"ollama:{model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": texts}).encode()
        req = urllib.request.Request(f"{self.url}/api/embed", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())["embeddings"]


def story_text(story: dict) -> str:
    """What a story is about, in English (always present) plus the reader-facing labels."""
    e = story["explanation"]
    parts = [story["title"]["en"], story["label"]["en"], e["forYou"]["en"], story["category"]]
    if "happened" in e:
        parts.append(e["happened"]["en"])
    parts += story.get("tags", [])
    parts += story.get("affects", [])
    return "\n".join(parts)


class VectorStore:
    def __init__(self, client, embedder, collection: str = "stories"):
        self.embedder = embedder
        self.collection = self._open(client, collection)
        if (self.collection.metadata or {}).get("embedder") != embedder.name:
            # Vectors from another model are not comparable; start over (startup re-indexes).
            client.delete_collection(collection)
            self.collection = self._open(client, collection)

    def _open(self, client, name: str):
        return client.get_or_create_collection(
            name, embedding_function=None, configuration={"hnsw": {"space": "cosine"}},
            metadata={"embedder": self.embedder.name},
        )

    def count(self) -> int:
        return self.collection.count()

    def index(self, stories: list[dict]) -> None:
        """Add or update published stories; anything else is removed from the index."""
        published = [s for s in stories if s["status"] == "published"]
        others = [s["id"] for s in stories if s["status"] != "published"]
        if published:
            self.collection.upsert(
                ids=[s["id"] for s in published],
                embeddings=self.embedder.embed([story_text(s) for s in published]),
                documents=[story_text(s) for s in published],
                metadatas=[{"category": s["category"], "scale": s["scale"], "placeId": s["placeId"]} for s in published],
            )
        if others:
            self.collection.delete(ids=others)

    def similarity(self, text: str, limit: int = 100) -> dict[str, float]:
        """Story id -> cosine similarity in [0, 1] to `text`. Empty when there is nothing to compare."""
        n = self.count()
        if not text.strip() or n == 0:
            return {}
        result = self.collection.query(query_embeddings=self.embedder.embed([text]), n_results=min(limit, n),
                                       include=["distances"])
        return {sid: max(0.0, min(1.0, 1 - d)) for sid, d in zip(result["ids"][0], result["distances"][0])}


def connect(settings) -> VectorStore:
    embedder = OllamaEmbedder(settings.ollama_url, settings.embed_model) if settings.ollama_url else HashEmbedder()
    chroma = ChromaSettings(anonymized_telemetry=False)
    collection = "stories"
    if settings.chroma == "memory":
        client = chromadb.EphemeralClient(settings=chroma)
        # Ephemeral clients share one store per process; keep each app's data apart.
        collection = f"stories-{secrets.token_hex(4)}"
    elif settings.chroma.startswith(("http://", "https://")):
        url = settings.chroma.rstrip("/")
        scheme, _, rest = url.partition("://")
        host, _, port = rest.partition(":")
        client = chromadb.HttpClient(host=host, port=int(port or 8000), ssl=scheme == "https", settings=chroma)
    else:
        client = chromadb.PersistentClient(path=settings.chroma, settings=chroma)
    return VectorStore(client, embedder, collection)
