"""The agent running next to the backend: profiles in, drafts in the editor queue, approved stories
in the reader's feed (pinni/newsroom.py)."""

import json
import re
import time
from dataclasses import replace

from fastapi.testclient import TestClient

from pinni import db, newsroom
from pinni.config import BACKEND
from pinni.main import create_app

MOCK_IDS = {s["id"] for s in json.loads((BACKEND.parent / "contract" / "mock" / "stories.json").read_text(encoding="utf-8"))}
SWIFT_DATE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(Z|[+-]\d\d:\d\d)$")


def test_site_news_is_published_on_the_map(client, login):
    editor = login("admin")
    assert client.post("/v1/admin/agent/run", headers=login("sara")).status_code == 403
    r = client.post("/v1/admin/agent/run", headers=editor)
    assert r.status_code == 200
    counts = r.json()
    assert counts["written"] and counts["published"] and counts["queued"] + counts["published"] == counts["written"]

    # Published without an editor, at its place on the map, in readers' feeds.
    feed = client.get("/v1/feed?limit=100", headers=login("sara")).json()
    stories = client.get("/v1/stories", params={"ids": ",".join(i["storyId"] for i in feed["items"])},
                         headers=editor).json()
    # Mock stories are origin agent too, but an editor verified them.
    agent = [s for s in stories if s["verification"]["verifiedBy"].startswith("Pinni agent")]
    assert len(agent) == counts["published"]
    places = {p["id"]: p for p in client.get("/v1/places", headers=editor).json()}
    for s in agent:
        assert s["status"] == "published" and s["risk"] != "red"
        # Its own spot when the source gave one, otherwise the centre of its place.
        here, centre = s["location"]["coordinate"], places[s["placeId"]]["center"]
        assert abs(here["lat"] - centre["lat"]) < 0.1 and abs(here["lon"] - centre["lon"]) < 0.2
        assert s["scale"] == places[s["placeId"]]["kind"]
        # Looks like the rest of the map: a point, a label of whole words, no fake translations.
        assert s["location"]["radiusMeters"] == 0
        assert s["title"]["en"].startswith(s["label"]["en"]) and len(s["label"]["en"]) <= 20
        assert not any(s["title"]["en"] in t for lang, t in s["title"].items() if lang != "en")
        # The app's date decoder reads whole seconds only.
        assert all(SWIFT_DATE.match(s[k]) for k in ("createdAt", "updatedAt", "publishedAt"))

    # Red risk (safety, health, ...) still waits for an editor.
    drafts = [i for i in client.get("/v1/admin/queue", headers=editor).json() if i["kind"] == "agentDraft"]
    queued = [client.get(f"/v1/stories/{i['id']}", headers=editor).json() for i in drafts]
    new = [s for s in queued if s["id"] not in MOCK_IDS]
    assert len(new) == counts["queued"] and all(s["risk"] == "red" for s in new)

    # The next round changes nothing that is already out.
    again = client.post("/v1/admin/agent/run", headers=editor).json()
    assert again["unchanged"] == counts["written"]


def test_agent_gathers_for_reader_profiles(app, client):
    """What the agent reads follows readers' profiles: PSOAS notices only for a PSOAS tenant."""
    conn = db.connect(app.state.settings.db_path)
    matti = db.get_doc(conn, "profiles", "u-matti")
    with conn:
        conn.execute("DELETE FROM profiles WHERE user_id != 'u-matti'")
    assert not any(i["source"] == "PSOAS" for i in newsroom.gather(conn))
    with conn:
        db.put_doc(conn, "profiles", {**matti, "housing": {"provider": "psoas", "consent": True}})
    assert any(i["source"] == "PSOAS" for i in newsroom.gather(conn))
    conn.close()


def test_editor_signs_off_a_red_risk_agent_story(client, login):
    """The editor page path: check the machine translations (PATCH), then approve."""
    editor = login("admin")
    client.post("/v1/admin/agent/run", headers=editor)
    ids = [i["id"] for i in client.get("/v1/admin/queue", headers=editor).json()
           if i["kind"] == "agentDraft" and i["id"] not in MOCK_IDS]
    story = client.get(f"/v1/stories/{ids[0]}", headers=editor).json()
    assert story["risk"] == "red"
    # Offline the agent writes English only (its fake translations are left out). With Ollama it
    # adds machine translations (tier 3), which an editor must check before a red-risk story goes out.
    assert [t["language"] for t in story["translations"]] == ["en"]
    story = {**story, "title": {**story["title"], "fi": "Ammuskelun tutkinta jatkuu Kiimingissä"},
             "translations": story["translations"] + [{"language": "fi", "tier": 3}]}
    assert client.patch(f"/v1/admin/stories/{story['id']}", json=story, headers=editor).status_code == 200
    approve = lambda: client.post(f"/v1/admin/stories/{story['id']}/decision", json={"action": "approve"}, headers=editor)
    assert approve().status_code == 409
    checked = [{"language": t["language"], "tier": 1, "reviewedBy": "Admin"} if t["tier"] == 3 else t
               for t in story["translations"]]
    assert client.patch(f"/v1/admin/stories/{story['id']}", json={**story, "translations": checked},
                        headers=editor).status_code == 200
    # The next agent round leaves the editor's work alone.
    client.post("/v1/admin/agent/run", headers=editor)
    assert client.get(f"/v1/stories/{story['id']}", headers=editor).json()["translations"] == checked
    assert approve().status_code == 200
    feed = client.get("/v1/feed?limit=100", headers=login("sara")).json()
    assert story["id"] in [i["storyId"] for i in feed["items"]]


def test_without_mock_content_the_news_is_the_agents(settings):
    """The delivery setup (PINNI_SEED_CONTENT off): places, channels and personas, no mock news;
    the agent's round at startup fills the map."""
    # In-memory graph: this test starts its own app, without the client fixture's Neo4j cleanup.
    settings = replace(settings, seed_content=False, agent_every_minutes=60, neo4j_uri="")
    with TestClient(create_app(settings)) as client:
        sara = client.post("/v1/auth/login", json={"email": "sara@pinni.test", "password": "pinni-dev"}).json()
        headers = {"Authorization": f"Bearer {sara['token']}"}
        assert client.get("/v1/places", headers=headers).json()
        channels = client.get("/v1/channels", params={"all": "true"}, headers=headers).json()
        assert channels and all(c["memberCount"] == 0 for c in channels)
        assert client.get("/v1/reports/mine", headers=headers).json() == []
        for _ in range(100):  # the round runs next to the server, right after startup
            items = client.get("/v1/feed?limit=100", headers=headers).json()["items"]
            if items:
                break
            time.sleep(0.05)
        assert items and not {i["storyId"] for i in items} & MOCK_IDS
