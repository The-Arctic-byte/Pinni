"""The feed follows what the reader said in onboarding from the first screen on, and what they do
afterwards (see pinni/recommender.py)."""

import uuid
from datetime import datetime, timezone

CATEGORIES = ("economy", "society", "politics", "shopping", "sport", "safety", "culture", "transport", "education",
              "housing", "health", "work", "environment", "technology", "world", "cityLife")
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def onboard(client, anonymous, categories: list[str]) -> tuple[dict, str]:
    headers, uid = anonymous()
    profile = {"userId": uid, "language": "en", "targetGroups": ["student"], "homePlaceId": "linnanmaa",
               "followedPlaceIds": ["linnanmaa"], "categoryWeights": {c: 0.9 for c in categories},
               "interests": [], "wantedNews": [], "hardFilters": {"categories": [], "tags": [], "sources": []},
               "updatedAt": NOW}
    assert client.put("/v1/profile", json=profile, headers=headers).status_code == 200
    answers = [event(uid, "onboardingAnswer", detail={"question": q}, context={"screen": "onboarding"})
               for q in ("language", "who", "categories", "place")]
    assert client.post("/v1/events", json=answers, headers=headers).status_code == 202
    return headers, uid


def event(uid: str, kind: str, **fields) -> dict:
    return {"id": f"ev-{uuid.uuid4().hex}", "userId": uid, "type": kind, "occurredAt": NOW, **fields}


def ranked(client, headers) -> tuple[dict, list[dict]]:
    feed = client.get("/v1/feed", params={"limit": 100}, headers=headers).json()
    ids = [i["storyId"] for i in feed["items"]]
    stories = {s["id"]: s for s in client.get("/v1/stories", params={"ids": ",".join(ids)}, headers=headers).json()}
    return feed, [stories[i] for i in ids]


def positions(stories: list[dict], categories: set[str]) -> list[int]:
    return [i for i, s in enumerate(stories) if s["category"] in categories]


def test_onboarding_categories_lead_the_feed_at_once(client, anonymous, valid):
    for picked in ({"transport", "cityLife"}, {"culture", "environment"}, {"politics", "economy"}):
        headers, _ = onboard(client, anonymous, sorted(picked))
        feed, stories = ranked(client, headers)
        valid("feed.schema.json", feed)
        assert feed["personalization"] >= 0.8
        rest = [s for s, item in zip(stories, feed["items"]) if not item["mustSee"]]
        assert rest[0]["category"] in picked
        # Next to what was picked, only news from the reader's own area comes this high.
        assert sum(s["category"] in picked for s in rest[:6]) >= 3, (picked, [s["category"] for s in rest[:6]])
        mine, others = positions(rest, picked), positions(rest, set(CATEGORIES) - picked)
        assert sum(mine) / len(mine) < 0.6 * sum(others) / len(others)


def test_the_feed_learns_from_likes(client, anonymous):
    headers, uid = onboard(client, anonymous, ["transport", "cityLife"])
    _, before = ranked(client, headers)
    culture = [s["id"] for s in before if s["category"] == "culture"]
    likes = [event(uid, "like", storyId=sid, value=1) for sid in culture[:3]]
    assert client.post("/v1/events", json=likes, headers=headers).status_code == 202
    feed, after = ranked(client, headers)
    # The stories that were not liked move up too: the whole category weighs more.
    unliked = {sid: i for i, sid in enumerate(s["id"] for s in after)}
    assert all(unliked[sid] < [s["id"] for s in before].index(sid) for sid in culture[3:])
    assert sum(positions(after, {"culture"})) < sum(positions(before, {"culture"}))
    reasons = [r["en"] for item in feed["items"] for r in item["reasons"]]
    assert "Matches your interest in culture" in reasons
    learned = client.get("/v1/profile/learned", headers=headers).json()
    assert learned["topCategories"][0]["category"] == "culture"


def test_reasons_use_names_not_ids(client, anonymous):
    headers, _ = onboard(client, anonymous, ["transport", "cityLife"])
    feed, _ = ranked(client, headers)
    reasons = [r for item in feed["items"] for r in item["reasons"]]
    texts = [r["en"] for r in reasons]
    assert "Happening in your area (Linnanmaa)" in texts
    assert "Matches your interest in city life" in texts
    assert not any("(linnanmaa)" in t or "cityLife" in t for t in texts)
    assert any("لینامآ" in r["fa"] for r in reasons)
