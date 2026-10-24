"""The Track B supervisor's real output, run offline (no Ollama, no Neo4j), goes through the backend
intake and shows up in the editor queue. Keeps the agent and the backend in step."""

import pinni_agent.agent  # noqa: F401  (load order, see pinni/recommender.py)
from pinni_agent.agent.supervisor import Supervisor
from pinni_agent.config import Settings as AgentSettings
from pinni_agent.mcp.tools.sources import retrieve_web_information

from pinni import db
from pinni.drafts import save_agent_story


def agent_stories(tmp_path) -> list[dict]:
    settings = AgentSettings(llm_enabled=False, sqlite_path=str(tmp_path / "agent.db"),
                             neo4j_uri="bolt://127.0.0.1:1", ollama_url="http://127.0.0.1:1")
    return Supervisor(settings).process_incoming_news(retrieve_web_information())


def test_agent_drafts_reach_the_editor_queue(app, client, login, valid, tmp_path):
    stories = agent_stories(tmp_path)
    assert stories
    conn = db.connect(app.state.settings.db_path)
    saved = [save_agent_story(conn, app.state.contract, s) for s in stories]
    conn.close()
    valid("story.schema.json", saved)
    assert all(s["status"] == "inReview" and s["origin"] == "agent" for s in saved)

    queue = client.get("/v1/admin/queue", headers=login("admin")).json()
    drafts = {i["id"] for i in queue if i["kind"] == "agentDraft"}
    assert {s["id"] for s in saved} <= drafts
    # Editors only see the drafts in their categories.
    leo = {i["id"] for i in client.get("/v1/admin/queue", headers=login("leo")).json()}
    leo_categories = {"politics", "economy", "society", "world"}
    assert {s["id"] for s in saved if s["category"] in leo_categories} == leo & {s["id"] for s in saved}
    # Readers never see an unreviewed draft.
    assert client.get(f"/v1/stories/{saved[0]['id']}", headers=login("sara")).status_code == 404


def test_agent_cannot_publish_red_risk_or_overwrite_a_decision(app, client, login, tmp_path):
    story = agent_stories(tmp_path)[0]
    conn = db.connect(app.state.settings.db_path)
    red = save_agent_story(conn, app.state.contract, {**story, "status": "published", "risk": "red"})
    assert red["status"] == "inReview"
    conn.close()
    editor = login("admin")
    assert client.post(f"/v1/admin/stories/{story['id']}/decision", json={"action": "reject"},
                       headers=editor).status_code == 200
    conn = db.connect(app.state.settings.db_path)
    again = save_agent_story(conn, app.state.contract, story)
    conn.close()
    assert again["status"] == "rejected"
