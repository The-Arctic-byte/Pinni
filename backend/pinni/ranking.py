"""What the reader's events say (learned preferences) and channel suggestions. Feed ranking is
done by the Track B recommender, see recommender.py."""

import math
import sqlite3
from datetime import datetime

from . import db
from .graph import Graph, signal

EVENTS_FOR_FULL_PERSONALIZATION = 30
SIMILAR_PEOPLE = 50
# Contract: similarMembers is shown only from 20 people up.
MIN_SIMILAR_MEMBERS = 20


def ancestors(places: dict, place_id: str | None) -> list[str]:
    """The place itself and every parent up to the world."""
    chain = []
    while place_id and place_id in places and place_id not in chain:
        chain.append(place_id)
        place_id = places[place_id].get("parentId")
    return chain


def default_profile(user_id: str, language: str = "en") -> dict:
    return {
        "userId": user_id, "language": language, "targetGroups": [], "categoryWeights": {},
        "interests": [], "wantedNews": [], "hardFilters": {"categories": [], "tags": [], "sources": []},
        "updatedAt": db.now(),
    }


def events_since_reset(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    row = conn.execute("SELECT learned_reset_at FROM users WHERE id = ?", (user_id,)).fetchone()
    reset = row["learned_reset_at"] if row else None
    events = db.docs(conn, "SELECT doc FROM events WHERE user_id = ? ORDER BY occurred_at", (user_id,))
    if reset:
        cutoff = datetime.fromisoformat(reset)
        events = [e for e in events if datetime.fromisoformat(e["occurredAt"]) > cutoff]
    return events


def learned(conn: sqlite3.Connection, user_id: str) -> dict:
    """What the reader's events say, separate from what they told us in the profile."""
    events = events_since_reset(conn, user_id)
    stories = {s["id"]: s for s in db.docs(conn, "SELECT doc FROM stories")}
    category_score: dict[str, float] = {}
    place_score: dict[str, float] = {}
    tag_score: dict[str, float] = {}
    rejected: set[str] = set()
    signals = 0
    for e in events:
        weight = signal(e)
        if e["type"] in ("followPlace", "placeChipTap") and e.get("placeId"):
            place_score[e["placeId"]] = place_score.get(e["placeId"], 0) + (1.0 if e["type"] == "followPlace" else 0.3)
            signals += 1
        if e["type"] in ("notForMe", "reject"):
            rejected.add(e.get("storyId"))
        story = stories.get(e.get("storyId"))
        if not story or weight == 0:
            continue
        signals += 1
        category_score[story["category"]] = category_score.get(story["category"], 0) + weight
        if weight > 0:
            place_score[story["placeId"]] = place_score.get(story["placeId"], 0) + weight
            for tag in story.get("tags", []):
                tag_score[tag] = tag_score.get(tag, 0) + weight

    def squash(x: float) -> float:
        # 0 signal -> 0.5, strong positive -> 1, strong negative -> 0
        return round(0.5 + 0.5 * (x / (abs(x) + 2)), 3)

    return {
        "personalization": round(min(1.0, signals / EVENTS_FOR_FULL_PERSONALIZATION), 3),
        "categories": {c: squash(v) for c, v in category_score.items()},
        "topPlaces": [p for p, v in sorted(place_score.items(), key=lambda kv: -kv[1]) if v > 0][:5],
        "topTags": [t for t, v in sorted(tag_score.items(), key=lambda kv: -kv[1]) if v > 0][:10],
        "rejectedStories": rejected - {None},
    }


def learned_preferences(conn: sqlite3.Connection, user_id: str) -> dict:
    """LearnedPreferences from the contract."""
    l = learned(conn, user_id)
    top = sorted(l["categories"].items(), key=lambda kv: -kv[1])
    return {
        "personalization": l["personalization"],
        "topCategories": [{"category": c, "weight": w} for c, w in top],
        "topPlaces": l["topPlaces"],
        "topTags": l["topTags"],
    }


def collaborative(graph: Graph | None, user_id: str) -> dict[str, float]:
    """Story id -> share of similar people (weighted by similarity) who liked it, in [0, 1]."""
    if graph is None:
        return {}
    similar = graph.similar_users(user_id, SIMILAR_PEOPLE)
    total = sum(score for _, score in similar)
    if not total:
        return {}
    weight = dict(similar)
    out: dict[str, float] = {}
    for other, ratings in graph.positive_ratings([u for u, _ in similar]).items():
        for story_id in ratings:
            out[story_id] = out.get(story_id, 0.0) + weight[other]
    return {sid: v / total for sid, v in out.items()}


CHANNEL_REASONS = {
    "similarMany": {"en": "{n} people like you follow this", "fi": "{n} kaltaistasi seuraa tätä",
                    "fa": "{n} نفر مثل تو این را دنبال می‌کنند", "sv": "{n} personer som du följer den här"},
    "similar": {"en": "People like you follow this", "fi": "Kaltaisesi seuraavat tätä",
                "fa": "افرادی مثل تو این را دنبال می‌کنند", "sv": "Personer som du följer den här"},
    "housing": {"en": "For residents like you", "fi": "Kaltaisillesi asukkaille",
                "fa": "برای ساکنانی مثل تو", "sv": "För boende som du"},
    "language": {"en": "In your language", "fi": "Omalla kielelläsi", "fa": "به زبان خودت", "sv": "På ditt språk"},
    "near": {"en": "Near you", "fi": "Lähelläsi", "fa": "نزدیک تو", "sv": "Nära dig"},
    "interests": {"en": "Matches your interests", "fi": "Vastaa kiinnostuksiasi",
                  "fa": "با علاقه‌هایت جور است", "sv": "Passar dina intressen"},
    "popular": {"en": "Popular in Oulu", "fi": "Suosittu Oulussa", "fa": "محبوب در اولو", "sv": "Populär i Uleåborg"},
}


def _reason(key: str, n: int | None = None) -> dict:
    return {lang: text.format(n=n) for lang, text in CHANNEL_REASONS[key].items()}


def suggested_channels(conn: sqlite3.Connection, user_id: str, graph: Graph | None = None) -> list[dict]:
    """Channels that similar people (knowledge graph) follow, blended with how well the channel fits
    the stated profile, so new readers with no similar people still get suggestions. A reader with no
    profile at all gets the most popular channels."""
    profile = db.get_doc(conn, "profiles", user_id) or default_profile(user_id)
    places = {p["id"]: p for p in db.docs(conn, "SELECT doc FROM places")}
    joined = {r[0] for r in conn.execute("SELECT channel_id FROM memberships WHERE user_id = ?", (user_id,))}
    similar = graph.similar_users(user_id, SIMILAR_PEOPLE * 2) if graph else []
    total = sum(score for _, score in similar)
    weight = dict(similar)
    followers = graph.channel_counts([u for u, _ in similar]) if similar else {}
    home = profile.get("homePlaceId")
    near = ({home} if home else set()) | set(profile.get("followedPlaceIds", []))
    around = set(ancestors(places, home))
    housing = profile.get("housing", {}).get("provider")
    stated = bool(profile["categoryWeights"] or home or profile.get("targetGroups") or housing)
    channels = db.docs(conn, "SELECT doc FROM channels")
    biggest = max((c["memberCount"] for c in channels), default=0)
    out = []
    for c in channels:
        if c["id"] in joined:
            continue
        popularity = math.log1p(c["memberCount"]) / math.log1p(biggest) if biggest else 0.0
        cat = max((profile["categoryWeights"].get(k, 0.5) for k in c["categories"]), default=0.5)
        place = 1.0 if c.get("placeId") in near else 0.6 if c.get("placeId") in around else 0.3
        # A channel in another language is little use; channels without one are for everyone.
        lang = 0.5 if not c.get("language") else 1.0 if c["language"] == profile["language"] else 0.1
        community = 1.0 if housing and housing in c["id"] else 0.5
        score = (0.3 * cat + 0.2 * place + 0.15 * lang + 0.25 * community + 0.1 * popularity
                 if stated else 0.5 * popularity)
        people = followers.get(c["id"], [])
        suggestion = {"channelId": c["id"]}
        if total and people:
            score = 0.6 * (sum(weight[u] for u in people) / total) + 0.4 * score
        if len(people) >= MIN_SIMILAR_MEMBERS:
            suggestion["similarMembers"] = len(people)
            reason = _reason("similarMany", len(people))
        elif people:
            reason = _reason("similar")
        elif not stated:
            reason = _reason("popular")
        elif community == 1.0:
            reason = _reason("housing")
        elif lang == 1.0:
            reason = _reason("language")
        elif place == 1.0:
            reason = _reason("near")
        elif cat >= 0.7:
            reason = _reason("interests")
        else:
            reason = _reason("popular")
        out.append({**suggestion, "score": round(min(score, 1.0), 3), "reason": reason})
    out.sort(key=lambda s: (-s["score"], s["channelId"]))
    return out[:10]
