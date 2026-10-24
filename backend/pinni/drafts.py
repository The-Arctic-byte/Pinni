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


def save_agent_story(conn: sqlite3.Connection, contract: Contract, story: dict) -> dict:
    """Store one agent story. It goes to the editor queue (inReview) unless the agent published it
    and it may be published without a human: never red risk, never with the publish rules broken."""
    story = _whole_seconds(_without_nulls(story))
    story["origin"] = "agent"
    if story.get("status") != "published" or story.get("risk") == "red" or publish_problems(story):
        story["status"] = "inReview"
        story.pop("publishedAt", None)
        story.pop("verification", None)
    story["updatedAt"] = db.now()
    contract.check("story.schema.json", story)
    existing = db.get_doc(conn, "stories", story["id"])
    if existing and existing["status"] in ("published", "rejected"):
        # An editor already decided; the agent does not overwrite that.
        return existing
    with conn:
        db.put_story(conn, story)
        step = "publish" if story["status"] == "published" else "route"
        message = "Published by the agent" if step == "publish" else "Draft sent to the editor queue"
        db.audit(conn, AGENT, step, message, story_id=story["id"])
    return story
