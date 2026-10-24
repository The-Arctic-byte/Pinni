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
            if k.endswith("At") and isinstance(v, str):
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


def save_agent_story(conn: sqlite3.Connection, contract: Contract, story: dict, publish: bool = False) -> dict:
    """Store one agent story.

    publish=True is for news the agent read on news sites (pinni/newsroom.py): it goes straight to
    readers. Otherwise it is published only if the agent marked it published. Either way a red-risk
    story (residence, health, money, work, safety) or one that breaks the publish rules waits in the
    editor queue (inReview) instead."""
    story = _whole_seconds(_without_nulls(story))
    story["origin"] = "agent"
    place_on_map(conn, story)
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
