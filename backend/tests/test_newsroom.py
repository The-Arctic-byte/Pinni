"""The agent running next to the backend: profiles in, drafts in the editor queue, approved stories
in the reader's feed (pinni/newsroom.py)."""

import json
import re

from pinni import db, newsroom
from pinni.config import BACKEND

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
        # The app's date decoder reads whole seconds only.
        assert all(SWIFT_DATE.match(s[k]) for k in ("createdAt", "updatedAt", "publishedAt"))

    # Red risk (safety, health, ...) still waits for an editor.
    drafts = [i for i in client.get("/v1/admin/queue", headers=editor).json() if i["kind"] == "agentDraft"]
    queued = [client.get(f"/v1/stories/{i['id']}", headers=editor).json() for i in drafts]
    new = [s for s in queued if s["id"] not in MOCK_IDS]
    assert len(new) == counts["queued"] and all(s["risk"] == "red" for s in new)

    # The next round changes nothing that is already out.
    again = client.post("/v1/admin/agent/run", headers=editor).json()
    assert again["unchanged"] == counts["published"]


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
