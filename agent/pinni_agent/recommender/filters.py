"""Hard filter enforcement for recommendation engine."""
from typing import Any, Dict, List, Set


def get_user_hard_filters(profile: Dict[str, Any], events: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """Aggregate hard filters from stated profile and interaction events ('notForMe', 'reject')."""
    hf = profile.get("hardFilters") or {}
    blocked_categories = set(hf.get("categories") or [])
    blocked_tags = set(hf.get("tags") or [])
    blocked_sources = set(hf.get("sources") or [])
    blocked_stories: Set[str] = set()

    for ev in events:
        etype = ev.get("type")
        sid = ev.get("storyId")
        if etype in ("notForMe", "reject") and sid:
            blocked_stories.add(sid)

    return {
        "categories": blocked_categories,
        "tags": blocked_tags,
        "sources": blocked_sources,
        "stories": blocked_stories,
    }


def should_filter_story(story: Dict[str, Any], hard_filters: Dict[str, Set[str]]) -> bool:
    """Check if story violates any hard filter rule.

    Hard filters must ALWAYS hold: once blocked or rejected, never show.
    """
    sid = story.get("id")
    if sid in hard_filters["stories"]:
        return True

    category = story.get("category")
    if category in hard_filters["categories"]:
        return True

    tags = set(story.get("tags") or [])
    if tags & hard_filters["tags"]:
        return True

    sources = {s.get("name") for s in story.get("sources") or []}
    if sources & hard_filters["sources"]:
        return True

    return False
