"""Runs the Track B supervisor (agent/pinni_agent/agent/supervisor.py) next to the backend.

The agent gathers news for what readers asked for: every stored profile goes to its profile-based
gathering (housing provider, student, home place, interests, wanted news, liked categories). News
read on news sites needs no editor: drafts.save_agent_story publishes it straight away, on the map at
its place. Only red-risk stories and ones that break the publish rules wait in the editor queue.
Reader reports never come through here; they always go to the editor desk of their category.

The agent keeps its own working files in data/agent.db. With PINNI_AGENT_LLM=1 it uses Ollama
(PINNI_OLLAMA_URL); otherwise it runs its offline heuristics, which need nothing installed."""

import logging
import sqlite3

import pinni_agent.agent  # noqa: F401  (load order, see pinni/recommender.py)
from pinni_agent.agent.supervisor import Supervisor
from pinni_agent.config import Settings as AgentSettings
from pinni_agent.mcp.tools.sources import gather_by_user_profile, retrieve_web_information

from . import db, graph as kg
from .config import Settings
from .contract import Contract
from .drafts import save_agent_story

log = logging.getLogger("pinni.newsroom")

# An address nothing listens on: the agent's own graph falls back to memory at once.
NO_NEO4J = "bolt://127.0.0.1:1"
# Category weight from which a reader counts as wanting that category.
LIKED = 0.7


def agent_settings(settings: Settings) -> AgentSettings:
    return AgentSettings(
        llm_enabled=settings.agent_llm,
        ollama_url=settings.ollama_url or "http://localhost:11434",
        sqlite_path=str(settings.db_path.parent / "agent.db"),
        neo4j_uri=NO_NEO4J,
    )


def gather(conn: sqlite3.Connection) -> list[dict]:
    """Source items for what each reader asked for, each url once. With no profiles yet, the
    agent's general pool."""
    items: list[dict] = []
    profiles = db.docs(conn, "SELECT doc FROM profiles")
    for profile in profiles:
        items += gather_by_user_profile(profile)
        liked = [c for c, w in profile.get("categoryWeights", {}).items() if w >= LIKED]
        if liked or profile.get("homePlaceId"):
            # Location and categories only: with keywords the agent makes up a summary item when
            # nothing matches, and keywords are already in gather_by_user_profile.
            items += retrieve_web_information(location=profile.get("homePlaceId"), categories=liked or None)
    if not profiles:
        items += retrieve_web_information()
    seen: set[str] = set()
    out = []
    for item in items:
        key = item.get("url") or item.get("title")
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def run_round(state) -> dict:
    """A round on its own connection, for the timer in main.py."""
    conn = db.connect(state.settings.db_path)
    try:
        return run(conn, state.contract, state.settings, state.graph, state.vectors)
    finally:
        conn.close()


def run(conn: sqlite3.Connection, contract: Contract, settings: Settings,
        graph: kg.Graph | None = None, vectors=None) -> dict:
    """One newsroom round. Returns what happened, for the admin page and the log."""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    items = gather(conn)
    stories = Supervisor(agent_settings(settings)).process_incoming_news(items)
    counts = {"gathered": len(items), "written": len(stories), "queued": 0, "published": 0, "unchanged": 0}
    for story in stories:
        before = db.get_doc(conn, "stories", story["id"])
        saved = save_agent_story(conn, contract, story, publish=True)
        if before and before["status"] != "draft":
            counts["unchanged"] += 1
            continue
        counts["published" if saved["status"] == "published" else "queued"] += 1
        for store, update in ((graph, lambda g: g.upsert_story(saved)), (vectors, lambda v: v.index([saved]))):
            if store is not None:
                try:
                    update(store)
                except Exception:  # noqa: BLE001  (derived stores catch up on restart)
                    log.exception("Could not index agent story %s", saved["id"])
    log.info("Newsroom round: %s", counts)
    return counts

