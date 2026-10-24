"""Publishing and review queue MCP tools."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...store import Store
from ...types import QueueItem, Story

RED_RISK_TOPICS = {"residence", "health", "money", "work", "safety"}


def assess_risk(story_or_report: Dict[str, Any]) -> str:
    """Classify risk as red, amber, or none based on contract rules."""
    category = story_or_report.get("category", "")
    affects = story_or_report.get("affects", [])
    text = str(story_or_report.get("text", "")).lower()
    explicit_risk = story_or_report.get("risk")

    if explicit_risk in ("red", "amber", "none"):
        return explicit_risk

    # Rule: red-risk = residence, health, money, work, safety
    if category in RED_RISK_TOPICS or any("residence" in a for a in affects):
        return "red"
    if any(k in text for k in ["permit", "police", "hospital", "salary", "eviction"]):
        return "red"

    if category in ("politics", "transport"):
        return "amber"

    return "none"


def route_to_human_queue(
    store: Store,
    item_id: str,
    kind: str,
    risk: str,
    trail: Optional[List[Dict[str, Any]]] = None,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Route an item (red-risk draft, community report, or reader flag) to the editor review queue."""
    now = datetime.now(timezone.utc).isoformat()
    queue_item = {
        "id": item_id,
        "kind": kind,
        "risk": risk,
        "createdAt": now,
        "trail": trail or [],
        **(extra_payload or {}),
    }
    store.add_to_queue(queue_item)
    return queue_item


def create_story_draft(
    store: Store,
    story_data: Dict[str, Any],
    trail: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Create a draft story and route to editor queue if red-risk."""
    risk = assess_risk(story_data)
    story_data["risk"] = risk
    story_data["status"] = "draft"
    store.save_story(story_data)

    if risk == "red":
        route_to_human_queue(
            store=store,
            item_id=story_data["id"],
            kind="agentDraft",
            risk="red",
            trail=trail or [],
            extra_payload={"title": story_data.get("title")},
        )
    return story_data
