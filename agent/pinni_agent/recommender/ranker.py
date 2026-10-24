"""Scoring, time decay, reasons generator, and ranking logic for news recommendation."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..agent.policy import is_must_see
from ..knowledge.graph import KnowledgeGraph
from ..knowledge.vector_store import VectorStore


def compute_time_decay(timestamp_str: Optional[str], half_life_hours: float = 48.0) -> float:
    """Calculate exponential time decay multiplier between 0.2 and 1.0."""
    if not timestamp_str:
        return 0.8
    try:
        ts = datetime.fromisoformat(timestamp_str)
        now = datetime.now(timezone.utc)
        diff_hours = max(0.0, (now - ts).total_seconds() / 3600.0)
        return float(math.exp(- (diff_hours * math.log(2.0)) / half_life_hours))
    except Exception:
        return 0.8


def score_story(
    story: Dict[str, Any],
    profile: Dict[str, Any],
    events: List[Dict[str, Any]],
    vector_store: VectorStore,
    graph: KnowledgeGraph,
    personalization_factor: float,
    half_life_hours: float = 48.0,
) -> Tuple[float, bool, List[Dict[str, str]]]:
    """Score a single story for a reader.

    Returns:
      (final_relevance_score, must_see_flag, localized_reasons)
    """
    sid = story["id"]
    category = story.get("category", "")
    place_id = story.get("placeId", "")
    base_importance = float(story.get("importance", 0.5))

    # 1. Must-see check
    must_see = is_must_see(story, profile)

    reasons: List[Dict[str, str]] = []

    # 2. Content similarity score
    interests = profile.get("interests", [])
    wanted = profile.get("wantedNews", [])
    profile_query = " ".join(interests + wanted)
    content_sim = 0.5
    if profile_query.strip():
        hits = vector_store.search(query=profile_query, limit=20)
        for h in hits:
            if h.id == sid:
                content_sim = min(1.0, float(h.score) * 20.0)
                break

    # 3. Category preference score
    cat_weights = profile.get("categoryWeights", {})
    cat_pref = float(cat_weights.get(category, 0.5))
    if cat_pref >= 0.7:
        reasons.append({
            "en": f"Matches your interest in {category}",
            "fi": f"Vastaa kiinnostustasi aiheeseen {category}",
            "fa": f"مرتبط با علاقه شما به {category}",
        })

    # 4. Location match score
    home_place = profile.get("homePlaceId")
    followed_places = set(profile.get("followedPlaceIds", []))
    loc_score = 0.5
    if place_id == home_place:
        loc_score = 1.0
        reasons.append({
            "en": f"Happening in your area ({place_id})",
            "fi": f"Tapahtuu alueellasi ({place_id})",
            "fa": f"در منطقه زندگی شما ({place_id})",
        })
    elif place_id in followed_places:
        loc_score = 0.8
        reasons.append({
            "en": f"From a place you follow ({place_id})",
            "fi": f"Seuraamastasi paikasta ({place_id})",
            "fa": f"از مکانی که دنبال می‌کنید ({place_id})",
        })

    # 5. Collaborative filtering score from Knowledge Graph
    collab_boosts = graph.collaborative_story_scores(profile["userId"])
    collab_score = float(collab_boosts.get(sid, 0.0))
    if collab_score > 0.4:
        reasons.append({
            "en": "Popular among readers with similar interests",
            "fi": "Suosittu samankaltaisten lukijoiden keskuudessa",
            "fa": "محبوب میان کاربرانی با علایق مشابه",
        })

    # 6. Interaction signals with time decay
    interaction_score = 0.0
    for ev in events:
        if ev.get("storyId") == sid:
            etype = ev.get("type")
            t_decay = compute_time_decay(ev.get("occurredAt"), half_life_hours)
            if etype == "like":
                interaction_score += 0.4 * t_decay
            elif etype in ("share", "save"):
                interaction_score += 0.3 * t_decay
            elif etype == "dwell":
                val = float(ev.get("value") or 10)
                if val > 60:
                    interaction_score += 0.2 * t_decay
            elif etype == "dislike":
                interaction_score -= 0.5 * t_decay
            elif etype == "skip":
                interaction_score -= 0.2 * t_decay

    # 7. Time decay of the story publication
    pub_at = story.get("publishedAt") or story.get("createdAt")
    story_time_decay = compute_time_decay(pub_at, half_life_hours)

    # 8. Hybrid blending
    # Personal score combination
    personal_score = (
        0.30 * content_sim +
        0.30 * cat_pref +
        0.20 * loc_score +
        0.10 * collab_score +
        0.10 * max(0.0, min(1.0, 0.5 + interaction_score))
    )

    # Cold-start blending:
    # When personalization_factor is low (new user), general importance dominates.
    # When personalization_factor grows, personalized score takes over.
    p = personalization_factor
    blended = ((1.0 - p) * base_importance) + (p * personal_score)

    # Apply story freshness time decay
    final_relevance = blended * (0.5 + 0.5 * story_time_decay)

    # Force must-see boost
    if must_see:
        final_relevance = max(final_relevance, 0.95)
        if not reasons:
            reasons.append({
                "en": "Important update for your community",
                "fi": "Tärkeä ilmoitus yhteisöllesi",
                "fa": "خبر مهم برای جامعه شما",
            })

    if not reasons:
        reasons.append({
            "en": "Top story for everyone in Oulu",
            "fi": "Pääuutinen Oulussa",
            "fa": "خبر برگزیده اولو",
        })

    return round(min(1.0, max(0.05, final_relevance)), 4), must_see, reasons
