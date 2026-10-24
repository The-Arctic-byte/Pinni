"""Feed ranking by the Track B recommender (agent/pinni_agent/recommender).

The recommender scores stories, decides must-see, and writes the "why you see this" reasons. It
reads its inputs through three small interfaces (store, vector store, knowledge graph); the
adapters below answer them from the backend's own SQLite, Chroma and Neo4j, so there is one
source of truth. Scale/place filtering and paging stay here because they follow the contract's
place tree, which the recommender does not know."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import pinni_agent.agent  # noqa: F401  (must load before .recommender: the agent package imports it back)
from pinni_agent.config import Settings
from pinni_agent.recommender import RecommendationEngine

from . import db
from .graph import Graph
from .ranking import ancestors, collaborative, default_profile, events_since_reset
from .vectors import VectorStore

# The recommender turns a hit's score into content similarity with min(1, score * 20), because its
# own store returns rank-fusion scores. Chroma gives cosine similarity, so hits are scaled down by
# the same factor.
RECOMMENDER_SCORE_SCALE = 20


def without_undone(events: list[dict]) -> list[dict]:
    """Drop likes and dislikes the reader took back (the app resends them with value 0); the
    recommender counts every like event, whatever its value."""
    out: list[dict] = []
    for e in events:
        if e["type"] in ("like", "dislike") and e.get("value") == 0:
            for i in range(len(out) - 1, -1, -1):
                if out[i]["type"] == e["type"] and out[i].get("storyId") == e.get("storyId"):
                    del out[i]
                    break
        else:
            out.append(e)
    return out


class _Store:
    def __init__(self, conn: sqlite3.Connection, user_id: str, stories: list[dict]):
        self.conn = conn
        self.user_id = user_id
        self.stories = stories

    def get_profile(self, user_id: str) -> dict:
        return db.get_doc(self.conn, "profiles", user_id) or default_profile(user_id)

    def list_user_events(self, user_id: str) -> list[dict]:
        return without_undone(events_since_reset(self.conn, user_id))

    def list_stories(self, status: str | None = None) -> list[dict]:
        return [s for s in self.stories if status is None or s["status"] == status]

    def get_story(self, story_id: str) -> dict | None:
        return db.get_doc(self.conn, "stories", story_id)


@dataclass
class _Hit:
    id: str
    score: float


class _Vectors:
    def __init__(self, vectors: VectorStore | None):
        self.vectors = vectors

    def search(self, query: str, limit: int = 10, **_) -> list[_Hit]:
        if not self.vectors:
            return []
        similarity = self.vectors.similarity(query, limit)
        return [_Hit(sid, score / RECOMMENDER_SCORE_SCALE) for sid, score in similarity.items()]


class _Graph:
    def __init__(self, graph: Graph | None):
        self.graph = graph

    def collaborative_story_scores(self, user_id: str) -> dict[str, float]:
        return collaborative(self.graph, user_id)


def feed(conn: sqlite3.Connection, user_id: str, scale: str | None, place_id: str | None,
         limit: int, cursor: str | None, graph: Graph | None = None, vectors: VectorStore | None = None) -> dict:
    places = {p["id"]: p for p in db.docs(conn, "SELECT doc FROM places")}
    stories = [s for s in db.docs(conn, "SELECT doc FROM stories WHERE status = 'published'")
               if (not scale or s["scale"] == scale)
               and (not place_id or place_id in ancestors(places, s["placeId"]))]
    engine = RecommendationEngine(settings=Settings(llm_enabled=False), store=_Store(conn, user_id, stories),
                                  vector_store=_Vectors(vectors), graph=_Graph(graph))
    ranked = engine.get_feed(user_id, limit=len(stories))

    start = int(cursor) if cursor and cursor.isdigit() else 0
    out = {
        "userId": user_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "personalization": ranked["personalization"],
        "items": ranked["items"][start:start + limit],
    }
    if scale:
        out["scale"] = scale
    if place_id:
        out["placeId"] = place_id
    if start + limit < len(ranked["items"]):
        out["nextCursor"] = str(start + limit)
    return out
