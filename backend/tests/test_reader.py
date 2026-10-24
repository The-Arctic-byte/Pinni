import json

import pytest

from pinni.config import BACKEND

CONTRACT = BACKEND.parent / "contract"


def stories_by_id(client, headers, ids):
    r = client.get("/v1/stories", params={"ids": ",".join(ids)}, headers=headers)
    return {s["id"]: s for s in r.json()}


@pytest.mark.parametrize("persona", ["sara", "matti"])
def test_feed_follows_contract_rules(client, login, valid, persona):
    headers = login(persona)
    feed = client.get("/v1/feed", headers=headers).json()
    valid("feed.schema.json", feed)
    rel = [i["relevance"] for i in feed["items"]]
    assert rel == sorted(rel, reverse=True)
    stories = stories_by_id(client, headers, [i["storyId"] for i in feed["items"]])
    assert all(s["status"] == "published" for s in stories.values())
    profile = client.get("/v1/profile", headers=headers).json()
    for s in stories.values():
        assert s["category"] not in profile["hardFilters"]["categories"]
        assert not set(s.get("tags", [])) & set(profile["hardFilters"]["tags"])


def test_safety_near_home_is_must_see(client, login):
    feed = client.get("/v1/feed", headers=login("sara")).json()
    top = feed["items"][0]
    assert top["storyId"] == "kiiminki-shooting" and top["mustSee"]


def test_cold_start_feed(client, anonymous, valid):
    headers, _ = anonymous()
    feed = client.get("/v1/feed", headers=headers).json()
    valid("feed.schema.json", feed)
    assert feed["personalization"] == 0
    assert feed["items"][0]["storyId"] == "kiiminki-shooting"
    assert "finns-party-cuts" not in {i["storyId"] for i in feed["items"]}  # in review


def test_not_for_me_hides_story(client, login):
    ids = {i["storyId"] for i in client.get("/v1/feed", headers=login("matti")).json()["items"]}
    assert "athletics-euros-2030" not in ids


def test_feed_scale_and_paging(client, login, valid):
    headers = login("sara")
    world = client.get("/v1/feed", params={"scale": "world"}, headers=headers).json()
    valid("feed.schema.json", world)
    stories = stories_by_id(client, headers, [i["storyId"] for i in world["items"]])
    assert stories and all(s["scale"] == "world" for s in stories.values())

    first = client.get("/v1/feed", params={"limit": 3}, headers=headers).json()
    assert len(first["items"]) == 3 and "nextCursor" in first
    second = client.get("/v1/feed", params={"limit": 3, "cursor": first["nextCursor"]}, headers=headers).json()
    assert not {i["storyId"] for i in first["items"]} & {i["storyId"] for i in second["items"]}


def test_feed_by_place(client, login):
    headers = login("sara")
    feed = client.get("/v1/feed", params={"placeId": "kiiminki"}, headers=headers).json()
    ids = [i["storyId"] for i in feed["items"]]
    assert {"kiiminki-shooting", "icy-path-kiiminki"} <= set(ids)
    assert all(s["placeId"] == "kiiminki" for s in stories_by_id(client, headers, ids).values())


def test_stories(client, login, valid):
    headers = login("sara")
    story = client.get("/v1/stories/lidl-ideapark", headers=headers).json()
    valid("story.schema.json", story)
    assert client.get("/v1/stories/finns-party-cuts", headers=headers).status_code == 404
    assert client.get("/v1/stories/finns-party-cuts", headers=login("aino")).status_code == 200
    many = client.get("/v1/stories", params={"ids": "orpo-kyiv,lidl-ideapark,missing"}, headers=headers).json()
    assert [s["id"] for s in many] == ["orpo-kyiv", "lidl-ideapark"]
    valid("story.schema.json", many)


def test_places(client, anonymous, valid):
    headers, _ = anonymous()
    places = client.get("/v1/places", headers=headers).json()
    valid("place.schema.json", places)
    assert len(places) == len(json.loads((CONTRACT / "mock" / "places.json").read_text(encoding="utf-8")))


def test_events(client, anonymous):
    headers, user_id = anonymous()
    events = [
        {"id": "ev-t1", "userId": user_id, "type": "open", "storyId": "orpo-kyiv", "occurredAt": "2026-10-24T10:00:00+03:00"},
        {"id": "ev-t2", "userId": user_id, "type": "dwell", "storyId": "orpo-kyiv", "value": 40, "occurredAt": "2026-10-24T10:01:00+03:00"},
    ]
    r = client.post("/v1/events", json=events, headers=headers)
    assert r.status_code == 202 and r.json() == {"accepted": 2, "duplicates": 0}
    assert client.post("/v1/events", json=events, headers=headers).json() == {"accepted": 0, "duplicates": 2}

    bad = [{"id": "ev-t3", "userId": user_id, "type": "dwell", "storyId": "orpo-kyiv", "occurredAt": "2026-10-24T10:00:00+03:00"}]
    assert client.post("/v1/events", json=bad, headers=headers).status_code == 422  # dwell needs value
    other = [{**events[0], "id": "ev-t4", "userId": "u-sara"}]
    assert client.post("/v1/events", json=other, headers=headers).status_code == 403


def test_profile_and_learned(client, anonymous, valid):
    headers, user_id = anonymous()
    profile = client.get("/v1/profile", headers={**headers, "Accept-Language": "fa-IR,fa;q=0.9"}).json()
    valid("profile.schema.json", profile)
    assert profile["language"] == "fa"

    profile["categoryWeights"] = {"sport": 0.9}
    profile["homePlaceId"] = "linnanmaa"
    saved = client.put("/v1/profile", json=profile, headers=headers)
    assert saved.status_code == 200
    valid("profile.schema.json", saved.json())
    assert client.get("/v1/profile", headers=headers).json()["homePlaceId"] == "linnanmaa"

    bad = {**profile, "categoryWeights": {"sport": 3}}
    assert client.put("/v1/profile", json=bad, headers=headers).status_code == 422

    client.post("/v1/events", headers=headers, json=[
        {"id": "ev-l1", "userId": user_id, "type": "like", "storyId": "athletics-euros-2030", "occurredAt": "2026-10-24T10:00:00+03:00"}])
    learned = client.get("/v1/profile/learned", headers=headers).json()
    assert learned["topCategories"][0]["category"] == "sport"
    assert client.delete("/v1/profile/learned", headers=headers).status_code == 204
    assert client.get("/v1/profile/learned", headers=headers).json()["topCategories"] == []


def test_notifications(client, login, valid):
    headers = login("sara")
    notes = client.get("/v1/notifications", headers=headers).json()
    valid("notification.schema.json", notes)
    unread = next(n for n in notes if "readAt" not in n)
    assert client.post(f"/v1/notifications/{unread['id']}/read", headers=headers).status_code == 204
    assert all("readAt" in n for n in client.get("/v1/notifications", headers=headers).json())
    assert client.post(f"/v1/notifications/{unread['id']}/read", headers=login("matti")).status_code == 404


def test_devices(client, anonymous):
    headers, _ = anonymous()
    assert client.put("/v1/devices", json={"apnsToken": "abc", "platform": "ios"}, headers=headers).status_code == 204
    assert client.put("/v1/devices", json={"apnsToken": "abc", "platform": "android"}, headers=headers).status_code == 422
