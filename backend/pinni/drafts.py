"""Stories written by the Track B supervisor (agent/pinni_agent/agent/supervisor.py), taken into the
backend so editors review them in the admin queue.

Not scheduled yet: nothing calls this until the agent runs next to the backend. It is kept in step
with the agent's output by tests/test_drafts.py, which runs the real supervisor offline."""

import sqlite3
from datetime import datetime

from . import db
from .contract import Contract
from .routers.admin import publish_problems

AGENT = "agent:supervisor"


def _without_nulls(value):
    """The agent writes missing optional fields as null; the contract leaves them out."""
    if isinstance(value, dict):
        return {k: _without_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_without_nulls(v) for v in value if v is not None]
    return value


def _whole_seconds(value):
    """The agent writes times with microseconds; the app's ISO 8601 decoder only reads whole seconds."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if (k == "at" or k.endswith("At")) and isinstance(v, str):
                try:
                    v = datetime.fromisoformat(v).isoformat(timespec="seconds")
                except ValueError:
                    pass
            out[k] = _whole_seconds(v)
        return out
    if isinstance(value, list):
        return [_whole_seconds(v) for v in value]
    return value


def place_on_map(conn: sqlite3.Connection, story: dict) -> None:
    """The agent knows the place, rarely the spot: a story with no location is a point at the centre
    of its place, and its scale follows the place, so it lands on the map where readers look."""
    place = db.get_doc(conn, "places", story.get("placeId") or "") or db.get_doc(conn, "places", "oulu")
    if place is None:
        return
    story["placeId"] = place["id"]
    if place["kind"] in ("area", "city"):
        story["scale"] = place["kind"]
    if "location" not in story and "center" in place and story["scale"] in ("area", "city"):
        story["location"] = {"coordinate": dict(place["center"]), "radiusMeters": 0}


# Pins show a short label (contract: Story.label); mock labels are a few words, about this long.
LABEL_LENGTH = 20


def short_label(title: str) -> str:
    """Whole words of the title, up to LABEL_LENGTH characters."""
    out = ""
    for word in title.split():
        if len(out) + len(word) + (1 if out else 0) > LABEL_LENGTH:
            break
        out = f"{out} {word}" if out else word
    return out or title[:LABEL_LENGTH]


def fit_for_the_app(story: dict) -> None:
    """Make an agent story look like the rest of the map (App/Views/Map):
    - a point, not an area: the agent's radius is the size of the place, and the app draws any
      radius as a circle that is never grouped into a pin;
    - no fake translations: offline, the agent "translates" by putting a word before the English
      title. Those languages are left out, so the app shows English (LocalizedText falls back to it);
    - a label of whole words, not the title cut after 15 characters."""
    db.as_point(story)
    english = story["title"].get("en", "")
    fake = {lang for lang, text in story["title"].items() if lang != "en" and english and english in text}
    for lang in fake:
        story["title"].pop(lang)
    story["translations"] = [t for t in story.get("translations", []) if t["language"] not in fake]
    story["label"] = {lang: short_label(text) for lang, text in story["title"].items()}


def stories_in_whole_seconds(conn: sqlite3.Connection, contract: Contract) -> int:
    """At startup: stories stored with microseconds (the agent's timeline entries were missed
    before) would stop the app from reading the whole feed."""
    changed = 0
    with conn:
        for story in db.docs(conn, "SELECT doc FROM stories"):
            fixed = _whole_seconds(story)
            if fixed != story:
                contract.check("story.schema.json", fixed)
                db.put_story(conn, fixed)
                changed += 1
    return changed


def unreviewed_english(story: dict) -> None:
    """The agent marks its English as checked by an editor (tier 1, "Aino K.") although no one
    has read it. Until an editor does, it is machine text: tier 3, no reviewer."""
    story["translations"] = [{"language": "en", "tier": 3} if t["language"] == "en" else t
                             for t in story.get("translations", [])]


def _touched_by_editor(conn: sqlite3.Connection, story_id: str) -> bool:
    return conn.execute("SELECT 1 FROM audit WHERE story_id = ? AND actor != ? LIMIT 1",
                        (story_id, AGENT)).fetchone() is not None


def tidy_agent_stories(conn: sqlite3.Connection, contract: Contract) -> int:
    """At startup: bring stories the agent stored before fit_for_the_app existed in line."""
    ids = [r[0] for r in conn.execute("SELECT DISTINCT story_id FROM audit WHERE actor = ? AND story_id IS NOT NULL",
                                      (AGENT,))]
    changed = 0
    with conn:
        for story_id in ids:
            story = db.get_doc(conn, "stories", story_id)
            if story is None or story.get("origin") != "agent":
                continue
            before = dict(story, location=dict(story.get("location") or {}), title=dict(story["title"]),
                          translations=list(story.get("translations", [])))
            fit_for_the_app(story)
            if not _touched_by_editor(conn, story_id):
                unreviewed_english(story)
            if story != before:
                contract.check("story.schema.json", story)
                db.put_story(conn, story)
                changed += 1
    return changed


def save_agent_story(conn: sqlite3.Connection, contract: Contract, story: dict, publish: bool = False) -> dict:
    """Store one agent story.

    publish=True is for news the agent read on news sites (pinni/newsroom.py): it goes straight to
    readers. Otherwise it is published only if the agent marked it published. Either way a red-risk
    story (residence, health, money, work, safety) or one that breaks the publish rules waits in the
    editor queue (inReview) instead."""
    story = _whole_seconds(_without_nulls(story))
    story["origin"] = "agent"
    place_on_map(conn, story)
    fit_for_the_app(story)
    unreviewed_english(story)
    now = db.now()
    wants = publish or story.get("status") == "published"
    if wants and story.get("risk") != "red" and not publish_problems(story):
        story["status"] = "published"
        source = next((s["name"] for s in story.get("sources", []) if s.get("name")), None)
        story["verification"] = {"verifiedBy": f"Pinni agent ({source})" if source else "Pinni agent", "verifiedAt": now}
        story.setdefault("publishedAt", now)
    else:
        story["status"] = "inReview"
        story.pop("publishedAt", None)
        story.pop("verification", None)
    story["updatedAt"] = now
    contract.check("story.schema.json", story)
    existing = db.get_doc(conn, "stories", story["id"])
    if existing and existing["status"] != "draft":
        # Out, decided, or with an editor (who may be editing it): the agent leaves it alone. It
        # rewrites only what an editor sent back to it (draft).
        return existing
    with conn:
        db.put_story(conn, story)
        step = "publish" if story["status"] == "published" else "route"
        message = "Published by the agent" if step == "publish" else "Draft sent to the editor queue"
        db.audit(conn, AGENT, step, message, story_id=story["id"])
    return story
