"""Knowledge graph and vector store: kept in step with SQLite and used by ranking."""

import sqlite3


from pinni import graph as kg
from pinni.vectors import HashEmbedder


def make_members(client, app, anonymous, n, profile_extra, channel=None, like=None):
    """n new members with the given profile fields; optionally join a channel and like a story."""
    db = sqlite3.connect(app.state.settings.db_path)
    for _ in range(n):
        headers, user_id = anonymous()
        db.execute("UPDATE users SET role = 'member' WHERE id = ?", (user_id,))
        db.commit()
        profile = client.get("/v1/profile", headers=headers).json()
        assert client.put("/v1/profile", json={**profile, **profile_extra}, headers=headers).status_code == 200
        if channel:
            assert client.put(f"/v1/channels/{channel}/membership", headers=headers).status_code == 204
        if like:
            event = {"id": f"ev-like-{user_id}", "userId": user_id, "type": "like", "storyId": like,
                     "occurredAt": "2026-10-24T10:00:00+03:00"}
            assert client.post("/v1/events", json=[event], headers=headers).status_code == 202
    db.close()


def test_graph_rebuilt_from_seed(client, app):
    g = app.state.graph
    assert "persian-oulu" in g.joined("u-sara")
    similar = dict(g.similar_users("u-sara"))
    assert similar.get("u-matti", 0) > 0  # same home area


def test_suggestions_from_similar_people(client, app, anonymous, login, valid):
    make_members(client, app, anonymous, 22, {"homePlaceId": "kiiminki", "targetGroups": ["student"]}, channel="student-sports")
    suggestions = client.get("/v1/channels/suggested", headers=login("sara")).json()
    valid("channel.schema.json#/$defs/Suggestion", suggestions)
    top = suggestions[0]
    assert top["channelId"] == "student-sports"
    assert top["similarMembers"] == 22
    assert top["reason"]["en"] == "22 people like you follow this"


def test_feed_uses_what_similar_people_liked(client, app, anonymous, login):
    sara = login("sara")

    def relevance():
        items = client.get("/v1/feed", headers=sara).json()["items"]
        return next(i["relevance"] for i in items if i["storyId"] == "un-climate-report")

    before = relevance()
    make_members(client, app, anonymous, 5, {"homePlaceId": "kiiminki", "targetGroups": ["student"]}, like="un-climate-report")
    assert relevance() > before


def test_feed_uses_content_similarity(client, anonymous):
    headers, _ = anonymous()
    profile = client.get("/v1/profile", headers=headers).json()

    def relevance():
        items = client.get("/v1/feed", headers=headers).json()["items"]
        return next(i["relevance"] for i in items if i["storyId"] == "muhos-data-centre")

    client.put("/v1/profile", json={**profile, "interests": ["football"]}, headers=headers)
    unrelated = relevance()
    client.put("/v1/profile", json={**profile, "interests": ["data centre water"]}, headers=headers)
    assert relevance() > unrelated


def test_published_story_is_indexed(client, app, login):
    vectors = app.state.vectors
    assert "finns-party-cuts" not in vectors.similarity("immigration social security pensions")
    headers = login("aino")
    story = client.get("/v1/stories/finns-party-cuts", headers=headers).json()
    story["translations"] = [{**t, "tier": 1} for t in story["translations"]]
    client.patch("/v1/admin/stories/finns-party-cuts", json=story, headers=headers)
    assert client.post("/v1/admin/stories/finns-party-cuts/decision", json={"action": "approve"}, headers=headers).status_code == 200
    scores = vectors.similarity("immigration social security pensions")
    assert max(scores, key=scores.get) == "finns-party-cuts"


def test_reset_clears_graph_ratings(client, app, anonymous):
    headers, user_id = anonymous()
    event = {"id": "ev-r1", "userId": user_id, "type": "like", "storyId": "orpo-kyiv", "occurredAt": "2026-10-24T10:00:00+03:00"}
    client.post("/v1/events", json=[event], headers=headers)
    assert "orpo-kyiv" in app.state.graph.positive_ratings([user_id])[user_id]
    client.delete("/v1/profile/learned", headers=headers)
    assert app.state.graph.positive_ratings([user_id])[user_id] == {}


def test_graph_failure_does_not_fail_request(client, app, anonymous, monkeypatch):
    def broken(*_):
        raise RuntimeError("graph down")

    monkeypatch.setattr(app.state.graph, "rate", broken)
    headers, user_id = anonymous()
    event = {"id": "ev-f1", "userId": user_id, "type": "like", "storyId": "orpo-kyiv", "occurredAt": "2026-10-24T10:00:00+03:00"}
    assert client.post("/v1/events", json=[event], headers=headers).status_code == 202


def test_signal_weights():
    assert kg.signal({"type": "dwell", "value": 120}) == 0.5
    assert kg.signal({"type": "reject"}) < 0 < kg.signal({"type": "like"})
    assert kg.signal({"type": "zoom"}) == 0


def test_hash_embedder_is_deterministic():
    e = HashEmbedder()
    a, b, c = e.embed(["data centre water", "data centre water", "football match"])
    assert a == b
    assert sum(x * y for x, y in zip(a, b)) > 0.99
    assert abs(sum(x * y for x, y in zip(a, c))) < 0.5


