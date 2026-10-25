"""Feed ranking by the Track B recommender (agent/pinni_agent/recommender).

The recommender scores stories, decides must-see, and writes the "why you see this" reasons. It
reads its inputs through three small interfaces (store, vector store, knowledge graph); the
adapters below answer them from the backend's own SQLite, Chroma and Neo4j, so there is one
source of truth. Scale/place filtering and paging stay here because they follow the contract's
place tree, which the recommender does not know.

Two things are added on the way in, so the feed follows the reader from the first screen on:
- What the reader said in onboarding counts at once. The recommender only trusts a profile after
  many events and ranks a new reader's feed almost like everyone's; a stated profile gets at least
  STATED_PERSONALIZATION.
- What the reader does moves their category weights (ranking.learned, the same numbers as
  /v1/profile/learned): a like, save or open makes the whole category weigh more, a dislike or
  "not for me" less. The recommender alone only moves the story that was liked.
On the way out, reasons name places and categories instead of giving their ids."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import pinni_agent.agent  # noqa: F401  (must load before .recommender: the agent package imports it back)
from pinni_agent.config import Settings
from pinni_agent.recommender import RecommendationEngine

from . import db
from .graph import Graph
from .ranking import ancestors, collaborative, default_profile, events_since_reset, learned
from .vectors import VectorStore

# The recommender turns a hit's score into content similarity with min(1, score * 20), because its
# own store returns rank-fusion scores. Chroma gives cosine similarity, so hits are scaled down by
# the same factor.
RECOMMENDER_SCORE_SCALE = 20
# Personalization of a reader who told us something in onboarding, before any other event.
STATED_PERSONALIZATION = 0.8
# How far learned behaviour moves a category weight: learned weights run 0..1 around 0.5.
LEARNING_RATE = 1.5
# Weight of a category the reader did not pick, once they picked some in onboarding.
NOT_PICKED = 0.3


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
        profile = db.get_doc(self.conn, "profiles", user_id) or default_profile(user_id)
        categories = {s["category"] for s in self.stories}
        return with_learned_weights(profile, learned(self.conn, user_id)["categories"], categories)

    def list_user_events(self, user_id: str) -> list[dict]:
        return without_undone(events_since_reset(self.conn, user_id))

    def list_stories(self, status: str | None = None) -> list[dict]:
        return [s for s in self.stories if status is None or s["status"] == status]

    def get_story(self, story_id: str) -> dict | None:
        return db.get_doc(self.conn, "stories", story_id)


def with_learned_weights(profile: dict, learned_categories: dict[str, float], categories: set[str]) -> dict:
    """Stated category weights moved by what the reader did. A category the reader did not pick
    weighs NOT_PICKED once they picked some, 0.5 (no opinion) when they picked none."""
    stated = profile.get("categoryWeights", {})
    default = NOT_PICKED if stated else 0.5
    weights = {c: default for c in categories} | stated
    for category, learned_weight in learned_categories.items():
        moved = weights.get(category, default) + LEARNING_RATE * (learned_weight - 0.5)
        weights[category] = round(min(1.0, max(0.0, moved)), 3)
    return {**profile, "categoryWeights": weights}


def has_stated_profile(profile: dict | None) -> bool:
    return bool(profile and (profile.get("categoryWeights") or profile.get("interests")
                             or profile.get("wantedNews") or profile.get("homePlaceId")))


# The app's own category names (App/Resources/Localizable.xcstrings), as they read inside a sentence.
CATEGORY_NAMES = {
    "economy": ("economy", "talous", "اقتصاد"), "society": ("society", "yhteiskunta", "جامعه"),
    "politics": ("politics", "politiikka", "سیاست"), "shopping": ("shopping", "ostokset", "خرید"),
    "sport": ("sport", "urheilu", "ورزش"), "safety": ("safety", "turvallisuus", "ایمنی"),
    "culture": ("culture", "kulttuuri", "فرهنگ"), "transport": ("transport", "liikenne", "حمل\u200cونقل"),
    "education": ("education", "koulutus", "آموزش"), "housing": ("housing", "asuminen", "مسکن"),
    "health": ("health", "terveys", "سلامت"), "work": ("work", "työ", "کار"),
    "environment": ("environment", "ympäristö", "محیط زیست"), "technology": ("technology", "teknologia", "فناوری"),
    "world": ("world", "maailma", "جهان"), "cityLife": ("city life", "kaupunkielämä", "زندگی شهری"),
}
LANGS = ("en", "fi", "fa")


def readable(reasons: list[dict], places: dict) -> list[dict]:
    """Ids in the recommender's reasons become names in each reason's language:
    'Happening in your area (linnanmaa)' -> '(Linnanmaa)', 'interest in cityLife' -> 'city life'."""
    out = []
    for reason in reasons:
        named = dict(reason)
        for lang, text in reason.items():
            if text.endswith(")") and "(" in text:
                place = places.get(text[text.rindex("(") + 1:-1])
                if place:
                    name = place["name"].get(lang) or place["name"]["en"]
                    text = f"{text[:text.rindex('(')]}({name})"
            head, _, last = text.rpartition(" ")
            if last in CATEGORY_NAMES and lang in LANGS:
                text = f"{head} {CATEGORY_NAMES[last][LANGS.index(lang)]}"
            named[lang] = text
        out.append(named)
    return out


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
    stated = has_stated_profile(db.get_doc(conn, "profiles", user_id))
    computed = engine.learner.calculate_personalization_factor
    engine.learner.calculate_personalization_factor = (
        lambda uid: max(computed(uid), STATED_PERSONALIZATION if stated else 0.0))
    ranked = engine.get_feed(user_id, limit=len(stories))
    for item in ranked["items"]:
        item["reasons"] = readable(item["reasons"], places)

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
