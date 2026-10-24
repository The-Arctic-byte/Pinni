"""Baseline ranking until the recommender (Track B, B4) replaces it.

relevance = (1 - p) * importance + p * personal, where p (personalization) grows with the
reader's events. `personal` mixes the stated profile, learned preferences, content similarity
(vector store) and what similar people liked (knowledge graph). Product rules from the contract
always hold:
- hard filters (categories, tags, sources) and stories the reader rejected are never shown,
- must-see items (safety near you, stories that affect your group) are never ranked away,
- only published stories appear."""

import sqlite3
from datetime import datetime, timezone

from . import db
from .graph import Graph, signal, user_groups
from .vectors import VectorStore, profile_text

EVENTS_FOR_FULL_PERSONALIZATION = 30
MUST_SEE_FLOOR = 0.8
SIMILAR_PEOPLE = 50
# Contract: similarMembers is shown only from 20 people up.
MIN_SIMILAR_MEMBERS = 20
# Share of `personal` per signal. A signal with no data (e.g. no similar people yet) is left out.
PERSONAL_WEIGHTS = {"category": 0.35, "place": 0.3, "tag": 0.1, "content": 0.15, "collaborative": 0.1}

REASONS = {
    "mustSeeHome": {"en": "Safety near your home in {place}", "fi": "Turvallisuus lähellä kotiasi: {place}",
                    "fa": "امنیت نزدیک خانه تو در {place}", "sv": "Säkerhet nära ditt hem i {place}"},
    "mustSeeCity": {"en": "Safety in {place}", "fi": "Turvallisuus: {place}",
                    "fa": "امنیت در {place}", "sv": "Säkerhet i {place}"},
    "affectsYou": {"en": "This affects people like you", "fi": "Tämä koskee kaltaisiasi",
                   "fa": "این خبر روی افرادی مثل تو اثر دارد", "sv": "Det här berör personer som du"},
    "inYourArea": {"en": "In your area", "fi": "Alueellasi", "fa": "در محله تو", "sv": "I ditt område"},
    "placeYouFollow": {"en": "From {place}, which you follow", "fi": "Seuraamastasi paikasta: {place}",
                       "fa": "از {place} که دنبالش می‌کنی", "sv": "Från {place}, som du följer"},
    "category": {"en": "You care about {category}", "fi": "Sinua kiinnostaa: {category}",
                 "fa": "به {category} اهمیت می‌دهی", "sv": "Du bryr dig om {category}"},
    "wanted": {"en": "You asked for news about {tag}", "fi": "Halusit uutisia aiheesta {tag}",
               "fa": "خواستی درباره {tag} خبر بگیری", "sv": "Du ville ha nyheter om {tag}"},
    "similar": {"en": "You liked similar stories", "fi": "Pidit samankaltaisista uutisista",
                "fa": "خبرهای مشابه را پسندیدی", "sv": "Du gillade liknande nyheter"},
    "likedBySimilar": {"en": "Popular with people like you", "fi": "Suosittu kaltaistesi keskuudessa",
                       "fa": "بین افرادی مثل تو محبوب است", "sv": "Populär bland personer som du"},
    "matchesInterests": {"en": "Matches your interests", "fi": "Vastaa kiinnostuksiasi",
                         "fa": "با علاقه‌هایت جور است", "sv": "Passar dina intressen"},
    "opinion": {"en": "Opinion, not news", "fi": "Mielipide, ei uutinen", "fa": "نظر، نه خبر", "sv": "Åsikt, inte nyhet"},
    "topWorld": {"en": "Top story in the world", "fi": "Maailman kärkiuutinen",
                 "fa": "خبر مهم جهان", "sv": "Toppnyhet i världen"},
    "top": {"en": "Top story in {place}", "fi": "Kärkiuutinen: {place}",
            "fa": "خبر مهم در {place}", "sv": "Toppnyhet i {place}"},
}

CATEGORY_NAMES = {
    "economy": {"fi": "talous", "fa": "اقتصاد", "sv": "ekonomi"},
    "society": {"fi": "yhteiskunta", "fa": "جامعه", "sv": "samhälle"},
    "politics": {"fi": "politiikka", "fa": "سیاست", "sv": "politik"},
    "shopping": {"fi": "ostokset", "fa": "خرید", "sv": "shopping"},
    "sport": {"fi": "urheilu", "fa": "ورزش", "sv": "sport"},
    "safety": {"fi": "turvallisuus", "fa": "امنیت", "sv": "säkerhet"},
    "culture": {"fi": "kulttuuri", "fa": "فرهنگ", "sv": "kultur"},
    "transport": {"fi": "liikenne", "fa": "حمل‌ونقل", "sv": "trafik"},
    "education": {"fi": "koulutus", "fa": "آموزش", "sv": "utbildning"},
    "housing": {"fi": "asuminen", "fa": "مسکن", "sv": "boende"},
    "health": {"fi": "terveys", "fa": "سلامت", "sv": "hälsa"},
    "work": {"fi": "työ", "fa": "کار", "sv": "arbete"},
    "environment": {"fi": "ympäristö", "fa": "محیط زیست", "sv": "miljö"},
    "technology": {"fi": "teknologia", "fa": "فناوری", "sv": "teknik"},
    "world": {"fi": "maailma", "fa": "جهان", "sv": "världen"},
    "cityLife": {"fi": "kaupunkielämä", "fa": "زندگی شهری", "sv": "stadsliv"},
}


def _text(key: str, places: dict | None = None, place: str | None = None,
          category: str | None = None, tag: str | None = None) -> dict:
    out = {}
    for lang, template in REASONS[key].items():
        values = {}
        if place:
            name = places[place]["name"]
            values["place"] = name.get(lang, name["en"])
        if category:
            values["category"] = category if lang == "en" else CATEGORY_NAMES[category].get(lang, category)
        if tag:
            values["tag"] = tag
        out[lang] = template.format(**values)
    return out


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


def _events_since_reset(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    row = conn.execute("SELECT learned_reset_at FROM users WHERE id = ?", (user_id,)).fetchone()
    reset = row["learned_reset_at"] if row else None
    events = db.docs(conn, "SELECT doc FROM events WHERE user_id = ? ORDER BY occurred_at", (user_id,))
    if reset:
        cutoff = datetime.fromisoformat(reset)
        events = [e for e in events if datetime.fromisoformat(e["occurredAt"]) > cutoff]
    return events


def learned(conn: sqlite3.Connection, user_id: str) -> dict:
    """What the reader's events say, separate from what they told us in the profile."""
    events = _events_since_reset(conn, user_id)
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


def feed(conn: sqlite3.Connection, user_id: str, scale: str | None, place_id: str | None,
         limit: int, cursor: str | None, graph: Graph | None = None, vectors: VectorStore | None = None) -> dict:
    profile = db.get_doc(conn, "profiles", user_id) or default_profile(user_id)
    places = {p["id"]: p for p in db.docs(conn, "SELECT doc FROM places")}
    stories = db.docs(conn, "SELECT doc FROM stories WHERE status = 'published'")
    l = learned(conn, user_id)
    hf = profile["hardFilters"]
    home = profile.get("homePlaceId")
    home_chain = ancestors(places, home)
    home_city = next((p for p in home_chain if places[p]["kind"] == "city"), "oulu")
    followed = set(profile.get("followedPlaceIds", []))
    learned_places = set(l["topPlaces"])
    groups = user_groups(profile)
    wanted = {t.lower() for t in profile.get("wantedNews", []) + profile.get("interests", [])}
    stated = bool(profile.get("categoryWeights") or profile.get("targetGroups") or home
                  or profile.get("interests") or profile.get("wantedNews"))
    p = max(l["personalization"], 0.5 if stated else 0.0)
    content = vectors.similarity(profile_text(profile, l["topTags"])) if vectors else {}
    liked_by_similar = collaborative(graph, user_id)

    items = []
    for s in stories:
        chain = ancestors(places, s["placeId"])
        if scale and s["scale"] != scale:
            continue
        if place_id and place_id not in chain:
            continue
        if (s["category"] in hf["categories"] or set(s.get("tags", [])) & set(hf["tags"])
                or {src["name"] for src in s["sources"]} & set(hf["sources"]) or s["id"] in l["rejectedStories"]):
            continue

        reasons = []
        must_see = False
        if s["category"] == "safety" and s["scale"] in ("area", "city") and home_city in chain:
            must_see = True
            if home and home in chain:
                reasons.append(_text("mustSeeHome", places, place=home))
            else:
                reasons.append(_text("mustSeeCity", places, place=home_city))
        if set(s.get("affects", [])) & groups:
            must_see = True
            reasons.append(_text("affectsYou"))

        stated_w = profile["categoryWeights"].get(s["category"], 0.5)
        learned_w = l["categories"].get(s["category"])
        category_w = stated_w if learned_w is None else (stated_w + learned_w) / 2
        if home and home in chain and s["scale"] == "area":
            place_w = 1.0
            reasons.append(_text("inYourArea"))
        elif followed & set(chain[:1]):
            place_w = 0.9
            reasons.append(_text("placeYouFollow", places, place=chain[0]))
        elif learned_places & set(chain[:1]) or (home_city in chain and s["scale"] in ("area", "city")):
            place_w = 0.7
        elif s["scale"] == "finland":
            place_w = 0.4
        else:
            place_w = 0.2
        tag_hit = next((t for t in s.get("tags", []) if t.lower() in wanted or t in l["topTags"]), None)
        tag_w = 1.0 if tag_hit else 0.5
        signals = {"category": category_w, "place": place_w, "tag": tag_w,
                   "content": content.get(s["id"], 0.0) if content else None,
                   "collaborative": liked_by_similar.get(s["id"], 0.0) if liked_by_similar else None}
        used = {k: v for k, v in signals.items() if v is not None}
        personal = sum(PERSONAL_WEIGHTS[k] * v for k, v in used.items()) / sum(PERSONAL_WEIGHTS[k] for k in used)
        if s["isOpinion"]:
            personal *= 0.5
        relevance = (1 - p) * s["importance"] + p * personal
        if must_see:
            relevance = max(relevance, MUST_SEE_FLOOR)

        if not reasons:
            if s["isOpinion"]:
                reasons.append(_text("opinion"))
            elif category_w >= 0.7:
                reasons.append(_text("category", category=s["category"]))
            elif tag_hit and tag_hit.lower() in wanted:
                reasons.append(_text("wanted", tag=tag_hit))
            elif tag_hit:
                reasons.append(_text("similar"))
            elif (signals["collaborative"] or 0) >= 0.3:
                reasons.append(_text("likedBySimilar"))
            elif (signals["content"] or 0) >= 0.3:
                reasons.append(_text("matchesInterests"))
            elif s["placeId"] == "world":
                reasons.append(_text("topWorld"))
            else:
                reasons.append(_text("top", places, place=s["placeId"]))
        items.append({"storyId": s["id"], "relevance": round(min(relevance, 1.0), 3),
                      "mustSee": must_see, "reasons": reasons[:2]})

    items.sort(key=lambda i: (-i["relevance"], i["storyId"]))
    start = int(cursor) if cursor and cursor.isdigit() else 0
    page = items[start:start + limit]
    out = {
        "userId": user_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "personalization": round(p, 3),
        "items": page,
    }
    if scale:
        out["scale"] = scale
    if place_id:
        out["placeId"] = place_id
    if start + limit < len(items):
        out["nextCursor"] = str(start + limit)
    return out


def suggested_channels(conn: sqlite3.Connection, user_id: str, graph: Graph | None = None) -> list[dict]:
    """Channels that similar people (knowledge graph) follow, blended with overlap with the
    stated profile so new readers with no similar people still get suggestions."""
    profile = db.get_doc(conn, "profiles", user_id) or default_profile(user_id)
    places = {p["id"]: p for p in db.docs(conn, "SELECT doc FROM places")}
    joined = {r[0] for r in conn.execute("SELECT channel_id FROM memberships WHERE user_id = ?", (user_id,))}
    similar = graph.similar_users(user_id, SIMILAR_PEOPLE * 2) if graph else []
    total = sum(score for _, score in similar)
    weight = dict(similar)
    followers = graph.channel_counts([u for u, _ in similar]) if similar else {}
    my_places = set(ancestors(places, profile.get("homePlaceId"))) | set(profile.get("followedPlaceIds", []))
    out = []
    for c in db.docs(conn, "SELECT doc FROM channels"):
        if c["id"] in joined:
            continue
        cat = max((profile["categoryWeights"].get(k, 0.5) for k in c["categories"]), default=0.5)
        place = 1.0 if c.get("placeId") in my_places else 0.3
        lang = 1.0 if c.get("language") and c["language"] == profile["language"] else 0.5
        housing = profile.get("housing", {}).get("provider")
        community = 1.0 if housing and housing in c["id"] else 0.5
        score = 0.4 * cat + 0.25 * place + 0.2 * lang + 0.15 * community
        people = followers.get(c["id"], [])
        suggestion = {"channelId": c["id"]}
        if total and people:
            score = 0.6 * (sum(weight[u] for u in people) / total) + 0.4 * score
        if len(people) >= MIN_SIMILAR_MEMBERS:
            n = len(people)
            suggestion["similarMembers"] = n
            reason = {"en": f"{n} people like you follow this", "fi": f"{n} kaltaistasi seuraa tätä",
                      "fa": f"{n} نفر مثل تو این را دنبال می‌کنند", "sv": f"{n} personer som du följer den här"}
        elif people:
            reason = {"en": "People like you follow this", "fi": "Kaltaisesi seuraavat tätä",
                      "fa": "افرادی مثل تو این را دنبال می‌کنند", "sv": "Personer som du följer den här"}
        elif c.get("language") and c["language"] == profile["language"]:
            reason = {"en": "In your language", "fi": "Omalla kielelläsi", "fa": "به زبان خودت", "sv": "På ditt språk"}
        elif c.get("placeId") in my_places:
            reason = {"en": "Near you", "fi": "Lähelläsi", "fa": "نزدیک تو", "sv": "Nära dig"}
        else:
            reason = {"en": "Matches your interests", "fi": "Vastaa kiinnostuksiasi",
                      "fa": "با علاقه‌هایت جور است", "sv": "Passar dina intressen"}
        out.append({**suggestion, "score": round(min(score, 1.0), 3), "reason": reason})
    out.sort(key=lambda s: -s["score"])
    return out[:10]

