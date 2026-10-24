"""Safety, risk, and editorial policies for the supervisor orchestrator."""
from typing import Any, Dict, List, Optional

RED_RISK_TOPICS = {"residence", "health", "money", "work", "safety"}
AMBER_RISK_TOPICS = {"politics", "transport"}


def determine_risk(category: str, affects: Optional[List[str]] = None, text: str = "") -> str:
    """Classify risk into 'none', 'amber', or 'red' based on contract specification.

    Contract rule: red-risk = residence, health, money, work, safety.
    A human editor must sign before publishing.
    """
    cat = (category or "").lower()
    if cat in RED_RISK_TOPICS:
        return "red"

    aff = [a.lower() for a in (affects or [])]
    if any("residence" in a for a in aff):
        return "red"

    t = text.lower()
    if any(k in t for k in ["permit", "police", "shooting", "eviction", "arrest", "migri"]):
        return "red"

    if cat in AMBER_RISK_TOPICS:
        return "amber"

    return "none"


def determine_translation_tier(language: str, reviewed_by: Optional[str] = None) -> int:
    """Determine translation tier: 1 = editor, 2 = community reviewer, 3 = machine validated."""
    if reviewed_by:
        if "editor" in reviewed_by.lower() or reviewed_by.startswith("Aino"):
            return 1
        return 2
    return 3


def is_must_see(story: Dict[str, Any], profile: Optional[Dict[str, Any]] = None) -> bool:
    """Determine if story is a 'must-see' item that cannot be personalized away.

    Applies to:
    - High-importance safety news near the user (e.g. area shooting in home place).
    - Official legal or status changes affecting the user's target groups (e.g. non-EU permits).
    """
    category = story.get("category")
    risk = story.get("risk")
    affects = story.get("affects", [])
    importance = story.get("importance", 0.0)

    # 1. Safety events
    if category == "safety" and risk == "red":
        return True

    if not profile:
        return importance >= 0.85

    # 2. Targeted group regulations
    home_place = profile.get("homePlaceId")
    if story.get("placeId") == home_place and risk == "red":
        return True

    residence = profile.get("residence", {})
    res_status = residence.get("status") if isinstance(residence, dict) else None
    if res_status and any(res_status in a for a in affects):
        return True

    target_groups = profile.get("targetGroups", [])
    if any(g in affects for g in target_groups):
        return True

    return False
