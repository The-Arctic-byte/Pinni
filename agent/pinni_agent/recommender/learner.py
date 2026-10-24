"""Learner: processes user interactions, updates Knowledge Graph, and computes learned preferences."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from ..knowledge.graph import KnowledgeGraph
from ..store import Store


class Learner:
    """Continuously updates user profile insights and Knowledge Graph from interaction events."""

    def __init__(self, store: Store, graph: KnowledgeGraph, cold_start_threshold: int = 5):
        self.store = store
        self.graph = graph
        self.cold_start_threshold = cold_start_threshold

    def handle_interaction(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Save interaction event and update Knowledge Graph."""
        user_id = event["userId"]

        # 1. Store in SQLite
        self.store.save_event(event)

        # 2. Update Knowledge Graph
        self.graph.record_event(event)

        # 3. Handle profile modifications from onboarding or edits
        etype = event.get("type")
        if etype == "onboardingAnswer" and event.get("detail"):
            self._apply_onboarding_detail(user_id, event["detail"])
        elif etype == "profileEdit" and event.get("detail"):
            profile = self.store.get_profile(user_id) or {"userId": user_id}
            profile.update(event["detail"])
            self.store.save_profile(profile)
            self.graph.record_profile(profile)

        # 4. Return current learned state
        return self.get_learned_preferences(user_id)

    def _apply_onboarding_detail(self, user_id: str, detail: Dict[str, Any]) -> None:
        profile = self.store.get_profile(user_id) or {"userId": user_id, "language": "en"}
        q = detail.get("question")
        ans = detail.get("answer")

        if q == "categories" and isinstance(ans, dict):
            profile.setdefault("categoryWeights", {}).update(ans)
        elif q == "housing" and isinstance(ans, str):
            profile["housing"] = {"provider": ans, "consent": True}
        elif q == "interests" and isinstance(ans, list):
            profile["interests"] = list(set(profile.get("interests", []) + ans))
        elif q == "targetGroups" and isinstance(ans, list):
            profile["targetGroups"] = list(set(profile.get("targetGroups", []) + ans))

        self.store.save_profile(profile)
        self.graph.record_profile(profile)

    def calculate_personalization_factor(self, user_id: str) -> float:
        """Calculate personalization score in [0.0, 1.0].

        0 = general ranking (new user, cold start)
        1 = fully personal. Grows smoothly with the number of events.
        """
        events = self.store.list_user_events(user_id)
        n = len(events)
        if n == 0:
            return 0.0
        # Smooth exponential saturation: P = 1 - exp(-n / threshold)
        p = 1.0 - math.exp(-float(n) / float(self.cold_start_threshold))
        return round(min(1.0, max(0.0, p)), 3)

    def get_learned_preferences(self, user_id: str) -> Dict[str, Any]:
        """Compute learned preferences for /v1/profile/learned endpoint."""
        p_factor = self.calculate_personalization_factor(user_id)
        events = self.store.list_user_events(user_id)

        cat_counter: Counter[str] = Counter()
        place_counter: Counter[str] = Counter()
        tag_counter: Counter[str] = Counter()

        for ev in events:
            sid = ev.get("storyId")
            pid = ev.get("placeId")
            if pid:
                place_counter[pid] += 1
            if sid:
                story = self.store.get_story(sid)
                if story:
                    cat = story.get("category")
                    if cat:
                        cat_counter[cat] += 1
                    for t in story.get("tags", []):
                        tag_counter[t] += 1

        top_cats = [
            {"category": cat, "weight": round(min(1.0, count * 0.25), 2)}
            for cat, count in cat_counter.most_common(5)
        ]
        top_places = [pl for pl, _ in place_counter.most_common(5)]
        top_tags = [tg for tg, _ in tag_counter.most_common(5)]

        return {
            "personalization": p_factor,
            "topCategories": top_cats,
            "topPlaces": top_places,
            "topTags": top_tags,
        }
