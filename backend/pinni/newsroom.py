"""Runs the Track B supervisor (agent/pinni_agent/agent/supervisor.py) next to the backend.

The agent gathers news for what readers asked for: every stored profile goes to its profile-based
gathering (housing provider, student, home place, interests, wanted news, liked categories). News
read on news sites needs no editor: drafts.save_agent_story publishes it straight away, on the map at
its place. Only red-risk stories and ones that break the publish rules wait in the editor queue.
Reader reports never come through here on their own; they always go to the editor desk of their
category. An editor can hand one to the agent ("Send to agent"): draft_from_report writes it up as a
story that waits for that editor's approval, and is never published by the agent.

The agent keeps its own working files in data/agent.db. With PINNI_AGENT_LLM=1 it uses Ollama
(PINNI_OLLAMA_URL); otherwise it runs its offline heuristics, which need nothing installed."""

import logging
import sqlite3

import pinni_agent.agent  # noqa: F401  (load order, see pinni/recommender.py)
from pinni_agent.agent.supervisor import Supervisor
from pinni_agent.config import Settings as AgentSettings
from pinni_agent.mcp.tools import sources as agent_sources
from pinni_agent.mcp.tools.sources import gather_by_user_profile, retrieve_web_information

from . import db, feeds, graph as kg
from .config import Settings
from .contract import Contract
from .drafts import AGENT, _whole_seconds, _without_nulls, fit_for_the_app, place_on_map, save_agent_story, unreviewed_english

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


def as_read(story: dict, by_url: dict[str, dict], places: dict[str, dict]) -> None:
    """Dates and place as the feed gave them. The agent stamps its sources with the time it read
    them, and its geocoder puts places it does not know at the centre of Oulu."""
    item = next((by_url[s["url"]] for s in story.get("sources", []) if s.get("url") in by_url), None)
    if item is None:
        return
    for source in story["sources"]:
        source["publishedAt"] = item["publishedAt"]
    story["publishedAt"] = item["publishedAt"]
    story["placeId"] = item["place"]
    if item.get("affects"):
        story["affects"] = sorted(set(story.get("affects", [])) | set(item["affects"]))
    kind = places.get(item["place"], {}).get("kind")
    story["scale"] = kind if kind in ("area", "city") else "finland" if item["place"] == "finland" else "world"
    story.pop("location", None)  # drafts.place_on_map puts area and city stories at the centre of their place


SAMPLE_URLS = {i["url"] for pool in (agent_sources.SAMPLE_KALEVA_ITEMS, agent_sources.SAMPLE_CITY_OULU_ITEMS,
                                      agent_sources.SAMPLE_PSOAS_ITEMS, agent_sources.SAMPLE_CAMPUS_ITEMS)
               for i in pool if i.get("url")}


def retire_samples(conn: sqlite3.Connection) -> int:
    """Once real news comes in, the agent takes down what it wrote from its sample sources (their
    links do not exist). Only stories no editor has touched: an editor's decision stays."""
    retired = 0
    with conn:
        for story in db.docs(conn, "SELECT doc FROM stories WHERE status IN ('published', 'inReview')"):
            if story.get("origin") != "agent" or not any(s.get("url") in SAMPLE_URLS for s in story.get("sources", [])):
                continue
            if conn.execute("SELECT 1 FROM audit WHERE story_id = ? AND actor != ? LIMIT 1", (story["id"], AGENT)).fetchone():
                continue
            db.put_story(conn, dict(story, status="rejected", updatedAt=db.now()))
            db.audit(conn, AGENT, "review", "Taken down: written from a sample source, now that real news comes in",
                     story_id=story["id"])
            retired += 1
    return retired


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
    places = {p["id"]: p for p in db.docs(conn, "SELECT doc FROM places")}
    live = feeds.read_all(list(places.values())) if settings.agent_live else []
    items = live or gather(conn)
    stories = Supervisor(agent_settings(settings)).process_incoming_news(items)
    counts = {"gathered": len(items), "written": len(stories), "queued": 0, "published": 0, "unchanged": 0,
              "live": bool(live)}
    by_url = {i["url"]: i for i in live}
    for story in stories:
        if live:
            as_read(story, by_url, places)
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
    if live:
        counts["retired"] = retire_samples(conn)
    log.info("Newsroom round: %s", counts)
    return counts



COMMUNITY_SOURCE = "Pinni community report"
HEADLINE_LENGTH = 90


def headline(text: str) -> str:
    """The report's first sentence, as a working title for the agent."""
    text = " ".join(text.split())
    first = next((text[:i + 1] for i, ch in enumerate(text) if ch in ".!?" and i > 10), text)
    return first if len(first) <= HEADLINE_LENGTH else first[:HEADLINE_LENGTH - 1].rstrip() + "…"


def report_draft(conn: sqlite3.Connection, report_id: str) -> dict | None:
    """The agent's open draft (inReview or draft) written from this report, if any."""
    return next((s for s in db.docs(conn, "SELECT doc FROM stories WHERE status IN ('inReview', 'draft')")
                 if s.get("community", {}).get("reportId") == report_id), None)


def draft_from_report(conn: sqlite3.Connection, contract: Contract, settings: Settings, report: dict,
                      place_id: str) -> dict | None:
    """The agent writes a news tip up as a story (title, label, explanation, place, translations it
    can make). The story is origin community, links the report and waits in the editor queue: an
    editor approves it, which also publishes the report. None when the agent drops the tip."""
    item = {"title": headline(report["text"]), "description": report["text"], "source": COMMUNITY_SOURCE,
            "category": report["category"], "place": place_id}
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    written = Supervisor(agent_settings(settings)).process_incoming_news([item])
    if not written:
        return None
    story = _whole_seconds(_without_nulls(written[0]))
    now = db.now()
    previous = report_draft(conn, report["id"])
    story.update({
        "id": previous["id"] if previous else db.new_id("community"),
        "status": "inReview",
        "origin": "community",
        "category": report["category"],
        "community": {"reportId": report["id"], "confirmations": 0},
        # The reader's text is the only source; there is no link to give.
        "sources": [{"name": COMMUNITY_SOURCE, "publishedAt": report["createdAt"]}],
        "createdAt": previous["createdAt"] if previous else now,
        "updatedAt": now,
    })
    story.pop("location", None)
    if report.get("location"):
        # A pin at the centre of the reported area, as for stories published straight from a report.
        story["location"] = {"coordinate": dict(report["location"]["coordinate"]), "radiusMeters": 0}
    for key in ("publishedAt", "verification"):
        story.pop(key, None)
    place_on_map(conn, story)
    fit_for_the_app(story)
    unreviewed_english(story)
    contract.check("story.schema.json", story)
    with conn:
        db.put_story(conn, story)
        db.audit(conn, AGENT, "explain", "Wrote a draft from the reader's report; it waits for an editor",
                 story_id=story["id"], report_id=report["id"])
    return story
