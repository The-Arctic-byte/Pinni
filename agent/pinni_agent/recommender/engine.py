"""Hybrid recommendation engine for Pinni news feed."""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..config import Settings, default_settings
from ..knowledge.graph import KnowledgeGraph
from ..knowledge.vector_store import VectorStore
from ..store import Store
from ..types import FeedItem, FeedPage
from .filters import get_user_hard_filters, should_filter_story
from .learner import Learner
from .ranker import score_story


class RecommendationEngine:
    """Combines vector content, knowledge graph collaborative filtering, hard rules, and cold start."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        store: Optional[Store] = None,
        vector_store: Optional[VectorStore] = None,
        graph: Optional[KnowledgeGraph] = None,
    ):
        self.s = settings or default_settings
        self.store = store or Store(self.s)
        self.vector_store = vector_store or VectorStore(self.s)
        self.graph = graph or KnowledgeGraph(self.s)
        self.learner = Learner(self.store, self.graph, self.s.cold_start_threshold)

    def get_feed(
        self,
        user_id: str,
        scale: Optional[str] = None,
        place_id: Optional[str] = None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """Generate personalized news feed page conforming to contract/schemas/feed.schema.json."""
        profile = self.store.get_profile(user_id) or {
            "userId": user_id,
            "language": "en",
            "categoryWeights": {},
            "hardFilters": {"categories": [], "tags": [], "sources": []},
        }
        events = self.store.list_user_events(user_id)
        hard_filters = get_user_hard_filters(profile, events)
        personalization = self.learner.calculate_personalization_factor(user_id)

        # 1. Fetch only published stories
        all_published = self.store.list_stories(status="published")

        scored_items: List[Dict[str, Any]] = []
        for story in all_published:
            # Scale or place filter from query parameters
            if scale and story.get("scale") != scale:
                continue
            if place_id and story.get("placeId") != place_id:
                continue

            # Check Hard Filters: must ALWAYS hold
            if should_filter_story(story, hard_filters):
                continue

            relevance, must_see, reasons = score_story(
                story=story,
                profile=profile,
                events=events,
                vector_store=self.vector_store,
                graph=self.graph,
                personalization_factor=personalization,
                half_life_hours=self.s.time_decay_half_life_hours,
            )

            scored_items.append({
                "storyId": story["id"],
                "relevance": relevance,
                "mustSee": must_see,
                "isExploration": False,
                "reasons": reasons,
                "category": story.get("category"),
            })

        # 2. Sort: mustSee first, then relevance descending
        scored_items.sort(key=lambda x: (1 if x["mustSee"] else 0, x["relevance"]), reverse=True)

        # 3. Exploration slot: reserve ~10-15% of feed outside user's top categories
        top_cats = {k for k, v in profile.get("categoryWeights", {}).items() if v >= 0.7}
        if top_cats and len(scored_items) > 3:
            explore_idx = int(len(scored_items) * (1.0 - self.s.exploration_rate))
            if explore_idx < len(scored_items):
                # find an item outside top_cats
                for i in range(explore_idx, len(scored_items)):
                    if scored_items[i]["category"] not in top_cats and not scored_items[i]["mustSee"]:
                        scored_items[i]["isExploration"] = True
                        break

        # Trim to limit and strip internal category key
        final_feed_items = []
        for it in scored_items[:limit]:
            final_feed_items.append({
                "storyId": it["storyId"],
                "relevance": it["relevance"],
                "mustSee": it["mustSee"],
                "isExploration": it["isExploration"],
                "reasons": it["reasons"],
            })

        now_iso = datetime.now(timezone.utc).isoformat()
        feed_page: Dict[str, Any] = {
            "userId": user_id,
            "generatedAt": now_iso,
            "personalization": personalization,
            "items": final_feed_items,
        }
        if scale:
            feed_page["scale"] = scale
        if place_id:
            feed_page["placeId"] = place_id
        return feed_page
