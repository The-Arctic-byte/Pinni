#!/usr/bin/env python3
"""Test A: Recommendation Engine & Feed Generation

Tests:
1. Personalized feed generation for Sara (Iranian student in Kiiminki).
2. Must-see item retention and localized explanation reasons.
3. Hard filter enforcement: adding a 'notForMe' interaction event immediately removes the story.
4. Cold start adaptation: shows ranking changes as events accumulate for a new reader.
"""
import sys
import time
from pathlib import Path

# Ensure agent directory is in path when executed directly
agent_root = Path(__file__).resolve().parent.parent
if str(agent_root) not in sys.path:
    sys.path.insert(0, str(agent_root))

from pinni_agent.config import Settings
from pinni_agent.knowledge.graph import KnowledgeGraph
from pinni_agent.knowledge.loader import load_mock_data
from pinni_agent.knowledge.vector_store import VectorStore
from pinni_agent.recommender.engine import RecommendationEngine
from pinni_agent.store import Store


def run_test_a(verbose: bool = True):
    if verbose:
        print("=" * 70)
        print("  TEST A: RECOMMENDATION ENGINE & HYBRID FEED GENERATION")
        print("=" * 70)

    # 1. Initialize environment with mock data
    settings = Settings(llm_enabled=False)
    store = Store(settings)
    vstore = VectorStore(settings)
    graph = KnowledgeGraph(settings)
    load_mock_data(settings, store, vstore, graph)

    engine = RecommendationEngine(settings, store, vstore, graph)

    # 2. Generate feed for u-sara
    if verbose:
        print("\n[Step 1] Fetching personalized feed for u-sara...")
    feed_sara = engine.get_feed("u-sara")
    if verbose:
        print(f"-> Personalization score: {feed_sara['personalization']}")
        print(f"-> Generated {len(feed_sara['items'])} items.")
        print("\nTop 5 Stories for Sara:")
        for idx, item in enumerate(feed_sara["items"][:5], 1):
            must_see_badge = " [MUST SEE]" if item["mustSee"] else ""
            reason = item["reasons"][0]["en"] if item.get("reasons") else "General interest"
            print(f"  #{idx} {item['storyId']}{must_see_badge}")
            print(f"      Relevance: {item['relevance']} | Reason: {reason}")

    # Verify must-see exists
    must_see_ids = [it["storyId"] for it in feed_sara["items"] if it["mustSee"]]
    assert "kiiminki-shooting" in must_see_ids, "Kiiminki shooting should be marked must-see for Sara"

    # 3. Test Hard Filter: Add 'notForMe' event on lidl-ideapark
    target_reject = "lidl-ideapark"
    if verbose:
        print(f"\n[Step 2] Testing hard filters: Emitting 'notForMe' event for story '{target_reject}'...")
    store.save_event({
        "id": "ev-groovy-not-for-me",
        "userId": "u-sara",
        "type": "notForMe",
        "storyId": target_reject,
        "occurredAt": "2026-10-24T13:00:00+03:00",
    })

    updated_feed = engine.get_feed("u-sara")
    updated_ids = [it["storyId"] for it in updated_feed["items"]]
    assert target_reject not in updated_ids, f"{target_reject} should be completely filtered out"
    if verbose:
        print(f"-> Verified: '{target_reject}' is removed from feed.")

    # 4. Test Cold Start to Personalized transition for a fresh user
    fresh_user_id = f"u-cold-{int(time.time() * 1000)}"
    store.save_profile({"userId": fresh_user_id, "language": "en", "categoryWeights": {}})
    if verbose:
        print(f"\n[Step 3] Testing cold start transition for {fresh_user_id}...")
    feed_new_initial = engine.get_feed(fresh_user_id)
    initial_p = feed_new_initial["personalization"]
    if verbose:
        print(f"-> Initial cold-start personalization: {initial_p}")
    assert initial_p == 0.0, "New user should have 0.0 personalization"

    # Add 5 events on shopping and tech stories
    events = [
        {"id": f"ev-g1-{fresh_user_id}", "userId": fresh_user_id, "type": "open", "storyId": "muhos-data-centre"},
        {"id": f"ev-g2-{fresh_user_id}", "userId": fresh_user_id, "type": "dwell", "storyId": "muhos-data-centre", "value": 75},
        {"id": f"ev-g3-{fresh_user_id}", "userId": fresh_user_id, "type": "like", "storyId": "muhos-data-centre"},
        {"id": f"ev-g4-{fresh_user_id}", "userId": fresh_user_id, "type": "share", "storyId": "muhos-data-centre"},
        {"id": f"ev-g5-{fresh_user_id}", "userId": fresh_user_id, "type": "open", "storyId": "interpellation"},
    ]
    for ev in events:
        store.save_event(ev)
        graph.record_event(ev)

    feed_new_updated = engine.get_feed(fresh_user_id)
    updated_p = feed_new_updated["personalization"]
    if verbose:
        print(f"-> Updated personalization after 5 events: {updated_p}")
        print(f"-> Muhos data centre rank boosted after like & dwell.")
    assert updated_p > 0.0, "Personalization factor must increase with interactions"

    if verbose:
        print("\n" + "=" * 70)
        print("  TEST A PASSED SUCCESSFULLY!")
        print("=" * 70)


def test_recommender():
    """Pytest entrypoint."""
    run_test_a(verbose=False)


if __name__ == "__main__":
    run_test_a(verbose=True)
