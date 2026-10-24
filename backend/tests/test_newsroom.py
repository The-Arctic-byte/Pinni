"""The agent running next to the backend: profiles in, drafts in the editor queue, approved stories
in the reader's feed (pinni/newsroom.py)."""

import re

from pinni import db, newsroom

SWIFT_DATE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(Z|[+-]\d\d:\d\d)$")


def test_agent_round_from_admin_page_to_feed(client, login):
    editor = login("admin")
    assert client.post("/v1/admin/agent/run", headers=login("sara")).status_code == 403
    r = client.post("/v1/admin/agent/run", headers=editor)
    assert r.status_code == 200
    counts = r.json()
    assert counts["written"] and counts["queued"] == counts["written"]

    drafts = [i for i in client.get("/v1/admin/queue", headers=editor).json() if i["kind"] == "agentDraft"]
    stories = [client.get(f"/v1/stories/{i['id']}", headers=editor).json() for i in drafts]
    agent = [s for s in stories if s["origin"] == "agent" and s["risk"] != "red"]
    assert agent
    # The app's date decoder reads whole seconds only.
    assert all(SWIFT_DATE.match(s[k]) for s in agent for k in ("createdAt", "updatedAt"))

    story = agent[0]
    r = client.post(f"/v1/admin/stories/{story['id']}/decision", json={"action": "approve"}, headers=editor)
    assert r.status_code == 200, r.text
    feed = client.get("/v1/feed?limit=100", headers=login("sara")).json()
    assert story["id"] in [i["storyId"] for i in feed["items"]]

    # The next round leaves the editor's decision alone.
    again = client.post("/v1/admin/agent/run", headers=editor).json()
    assert again["alreadyDecided"] == 1
    assert client.get(f"/v1/stories/{story['id']}", headers=editor).json()["status"] == "published"


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
