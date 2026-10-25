"""Live RSS for the agent (pinni/feeds.py); no network: a saved copy of the Yle News feed."""

from datetime import datetime, timezone
from pathlib import Path

from pinni import feeds, newsroom

YLE = Path(__file__).parent / "fixtures" / "yle_news.xml"
NOW = datetime(2026, 10, 25, 6, 0, tzinfo=timezone.utc)


def places(client, headers):
    return client.get("/v1/places", headers=headers).json()


def test_parse_yle(client, anonymous):
    headers, _ = anonymous()
    items = feeds.parse(feeds.FEEDS[0], YLE.read_bytes(), places(client, headers), now=NOW)
    # The 2022 item is too old.
    assert [i["url"] for i in items] == ["https://yle.fi/a/74-20252995?origin=rss", "https://yle.fi/a/74-20253071?origin=rss",
                                         "https://yle.fi/a/74-1?origin=rss"]
    week, taxi, clinic = items
    assert week["place"] == "helsinki" and week["source"] == "Yle News"
    assert week["publishedAt"] == "2026-10-23T16:05:20+03:00"
    assert taxi["category"] == "transport"
    assert clinic["place"] == "linnanmaa" and clinic["category"] == "health"
    assert clinic["description"] == "The new  walk-in  clinic opens on Monday."


def test_round_with_live_news(app, client, login, monkeypatch, valid):
    """The agent writes up what the feed says, links the article, and keeps its date and place;
    red-risk news (health here) waits for an editor."""
    monkeypatch.setattr(feeds, "read_all", lambda p, *a: feeds.parse(feeds.FEEDS[0], YLE.read_bytes(), p, now=NOW))
    state = app.state
    settings = type(state.settings)(**{**state.settings.__dict__, "agent_live": True})
    conn = newsroom.db.connect(settings.db_path)
    counts = newsroom.run(conn, state.contract, settings)
    assert counts["live"] and counts["gathered"] == 3
    admin = login("admin")
    ids = [i["id"] for i in client.get("/v1/admin/agent/stories", headers=admin).json()]
    written = client.get("/v1/stories", params={"ids": ",".join(ids)}, headers=admin).json()
    stories = {s["sources"][0]["url"]: s for s in written if s["sources"][0].get("url", "").startswith("https://yle.fi")}
    assert len(stories) == 3
    taxi = stories["https://yle.fi/a/74-20253071?origin=rss"]
    valid("story.schema.json", taxi)
    assert taxi["status"] == "published" and taxi["verification"]["verifiedBy"] == "Pinni agent (Yle News)"
    assert taxi["publishedAt"] == "2026-10-23T15:39:00+03:00"
    assert taxi["placeId"] == "helsinki" and taxi["scale"] == "city"
    helsinki = next(p for p in places(client, admin) if p["id"] == "helsinki")
    assert taxi["location"] == {"coordinate": helsinki["center"], "radiusMeters": 0}
    clinic = stories["https://yle.fi/a/74-1?origin=rss"]
    assert clinic["status"] == "inReview" and clinic["risk"] == "red"


def test_live_news_takes_down_sample_news(app, client, login, monkeypatch):
    state = app.state
    conn = newsroom.db.connect(state.settings.db_path)
    newsroom.run(conn, state.contract, state.settings)  # samples, as without a network
    admin = login("admin")
    listed = client.get("/v1/admin/agent/stories", headers=admin).json()
    kept = next(i["id"] for i in listed if i["status"] == "published")
    samples = [kept] + [i["id"] for i in listed if i["status"] in ("published", "inReview") and i["id"] != kept]
    # An editor kept one: that decision stays.
    assert client.post(f"/v1/admin/stories/{kept}/decision", json={"action": "approve"}, headers=admin).status_code == 200

    monkeypatch.setattr(feeds, "read_all", lambda p, *a: feeds.parse(feeds.FEEDS[0], YLE.read_bytes(), p, now=NOW))
    settings = type(state.settings)(**{**state.settings.__dict__, "agent_live": True})
    counts = newsroom.run(conn, state.contract, settings)
    assert counts["retired"] == len(samples) - 1
    status = {i["id"]: i["status"] for i in client.get("/v1/admin/agent/stories", headers=admin).json()}
    assert status[kept] == "published"
    assert all(status[s] == "rejected" for s in samples[1:])


DATE = __import__("re").compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(Z|[+-]\d\d:\d\d)$")


def dates(value, key=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from dates(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from dates(v, key)
    elif isinstance(value, str) and (key == "at" or key.endswith("At")):
        yield key, value


def test_every_time_the_app_reads_is_whole_seconds(app, client, login, monkeypatch):
    """The app's ISO 8601 decoder fails on fractions of a second, and one bad story stops the
    whole feed from loading."""
    monkeypatch.setattr(feeds, "read_all", lambda p, *a: feeds.parse(feeds.FEEDS[0], YLE.read_bytes(), p, now=NOW))
    state = app.state
    conn = newsroom.db.connect(state.settings.db_path)
    newsroom.run(conn, state.contract, state.settings)
    newsroom.run(conn, state.contract, type(state.settings)(**{**state.settings.__dict__, "agent_live": True}))
    matti, mira = login("matti"), login("mira")
    report = client.post("/v1/reports", json={"kind": "newsTip", "category": "cityLife", "text": "The Tuira sauna opens again."},
                         headers=matti).json()
    client.get(f"/v1/admin/reports/{report['id']}", headers=mira)
    client.post(f"/v1/admin/reports/{report['id']}/decision", json={"action": "sendBack"}, headers=mira)
    ids = [s["id"] for s in newsroom.db.docs(conn, "SELECT doc FROM stories")]
    stories = client.get("/v1/stories", params={"ids": ",".join(ids[:100])}, headers=mira).json()
    stories += client.get("/v1/stories", params={"ids": ",".join(ids[100:])}, headers=mira).json() if ids[100:] else []
    bad = [(s["id"], k, v) for s in stories for k, v in dates(s) if not DATE.match(v)]
    assert not bad, bad[:5]


def test_psoas_news_is_for_psoas_tenants():
    """Stories from the PSOAS feed carry housing:psoas, both new ones (as_read) and ones read before
    the feed said so (drafts.feed_affects at startup)."""
    from pinni import drafts
    item = {"url": "https://psoas.fi/en/x", "publishedAt": "2026-10-20T10:00:00+03:00", "place": "oulu",
            "affects": ["housing:psoas"]}
    story = {"sources": [{"name": "PSOAS", "url": item["url"]}], "affects": ["student"]}
    newsroom.as_read(story, {item["url"]: item}, {"oulu": {"kind": "city"}})
    assert story["affects"] == ["housing:psoas", "student"]
    old = {"sources": [{"name": "PSOAS", "url": "https://psoas.fi/en/y"}]}
    drafts.feed_affects(old)
    assert old["affects"] == ["housing:psoas"]
    yle = {"sources": [{"name": "Yle News"}]}
    drafts.feed_affects(yle)
    assert "affects" not in yle
