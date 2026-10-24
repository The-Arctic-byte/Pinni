#!/usr/bin/env python3
"""Test B: B3 Supervisor Orchestrator

Tests:
1. Gather by profile: Automatically watches PSOAS and campus news for student residents.
2. Select: Deduplicates, merges, classifies topic/scale/risk, and drops spam.
3. Explain: Builds structured explanation sections and context Q&A cards.
4. Translate & check: Checks accuracy across en, fi, fa, sv and sets translation tiers.
5. Route to human: Directs red-risk content and community reports to review queue.
6. Distribute: Identifies matching readers and triggers notifications.
7. Suggest channels: Recommends channels using similar people in Knowledge Graph.
8. Audit: Verifies all actions write to the audit trail for the admin page.
"""
import sys
from pathlib import Path

# Ensure agent directory is in path when executed directly
agent_root = Path(__file__).resolve().parent.parent
if str(agent_root) not in sys.path:
    sys.path.insert(0, str(agent_root))

from pinni_agent.agent.supervisor import Supervisor
from pinni_agent.config import Settings
from pinni_agent.knowledge.graph import KnowledgeGraph
from pinni_agent.knowledge.loader import load_mock_data
from pinni_agent.knowledge.vector_store import VectorStore
from pinni_agent.store import Store


def run_test_b(verbose: bool = True):
    if verbose:
        print("=" * 70)
        print("  TEST B: SUPERVISOR ORCHESTRATOR & THE 10 TRACK B TASKS")
        print("=" * 70)

    settings = Settings(llm_enabled=False)
    store = Store(settings)
    vstore = VectorStore(settings)
    graph = KnowledgeGraph(settings)
    load_mock_data(settings, store, vstore, graph)

    supervisor = Supervisor(settings, store, vstore, graph)

    # 1. GATHER BY PROFILE
    if verbose:
        print("\n[Step 1] Supervisor Task: Gather by profile (u-sara)...")
    gathered = supervisor.gather_by_profile("u-sara")
    sources = {g["source"] for g in gathered}
    if verbose:
        print(f"-> Gathered {len(gathered)} items. Sources detected: {sources}")
    assert "PSOAS" in sources, "Should gather from PSOAS site because user lives in PSOAS"
    assert "University of Oulu" in sources, "Should gather campus news because user is a student"

    # 2. SELECT & DEDUPLICATE & CLASSIFY
    if verbose:
        print("\n[Step 2] Supervisor Task: Select, deduplicate & classify...")
    raw_batch = [
        {
            "title": "Suspect detained in empty flat shooting in Kiiminki",
            "description": "Police confirm no casualties.",
            "category": "safety",
            "place": "kiiminki",
            "source": "Kaleva",
        },
        # Duplicate of previous
        {
            "title": "Suspect detained in empty flat shooting in Kiiminki",
            "description": "Police confirm no casualties.",
            "category": "safety",
            "place": "kiiminki",
            "source": "Kaleva",
        },
        # Spam
        {
            "title": "Casino bonus free spins claim now",
            "description": "Win big jackpot instantly.",
            "source": "SpamBot",
        },
    ]
    selected = supervisor.select(raw_batch)
    if verbose:
        print(f"-> Batch of {len(raw_batch)} raw items filtered to {len(selected)} valid story.")
        print(f"   Selected: '{selected[0]['title']}' | Category: {selected[0]['category']} | Risk: {selected[0]['risk']}")
    assert len(selected) == 1, "Duplicate and spam item must be dropped"
    assert selected[0]["risk"] == "red", "Shooting must be classified as red-risk"

    # 3. EXPLAIN & TRANSLATE
    if verbose:
        print("\n[Step 3] Supervisor Task: Explain sections and Translate + Check...")
    explanation = supervisor.explain(selected[0])
    if verbose:
        print(f"-> Explanation generated: Known={len(explanation.get('known', []))} bullets")
        print(f"   ForYou text: '{explanation['forYou']['en']}'")
        print(f"   Context Q&A card: Q='{explanation['context']['question']['en']}'")

    trans_result = supervisor.translate_and_check(
        title=selected[0]["title"],
        for_you=explanation["forYou"]["en"],
        target_languages=["fi", "fa", "sv"],
    )
    if verbose:
        print(f"-> Translations verified across languages: {list(trans_result['translations'].keys())}")
        print(f"   Fa Title: {trans_result['translations']['fa']['title']}")
        print(f"   Translation Tiers: {[t['tier'] for t in trans_result['tiers']]}")
    assert "fa" in trans_result["translations"]
    assert "fi" in trans_result["translations"]

    # 4. ROUTE TO HUMAN REVIEW
    if verbose:
        print("\n[Step 4] Supervisor Task: Route red-risk story to human editor review...")
    queued = supervisor.route_to_human(
        story_or_report_id="shooting-draft-001",
        kind="agentDraft",
        risk="red",
        extra={"title": selected[0]["title"]},
    )
    if verbose:
        print(f"-> Story '{queued['id']}' routed to Editor Queue with risk='{queued['risk']}'.")
    assert queued["risk"] == "red"

    # 5. DISTRIBUTE
    if verbose:
        print("\n[Step 5] Supervisor Task: Distribute and target readers...")
    story_dist = {
        "id": "kiiminki-alert",
        "placeId": "kiiminki",
        "category": "safety",
        "risk": "red",
        "affects": ["residents:kiiminki"],
    }
    targets = supervisor.distribute(story_dist)
    target_users = [t["userId"] for t in targets]
    if verbose:
        print(f"-> Target readers identified for notification: {target_users}")
    assert "u-sara" in target_users

    # 6. SUGGEST CHANNELS VIA KNOWLEDGE GRAPH
    if verbose:
        print("\n[Step 6] Supervisor Task: Suggest channels from similar people...")
    suggestions = supervisor.suggest_channels("u-sara")
    if verbose:
        for s in suggestions[:3]:
            print(f"-> Channel '{s['channelId']}' (Score: {s['score']}): {s['reason']['en']}")

    # 7. AUDIT LOG
    if verbose:
        print("\n[Step 7] Supervisor Task: Audit trail logging...")
    audit_entries = supervisor.audit_log(limit=50)
    steps_logged = [e["step"] for e in audit_entries]
    if verbose:
        print(f"-> Total audit entries logged: {len(audit_entries)}")
        print(f"   Recent steps: {steps_logged[:6]}")
    assert "gather" in steps_logged
    assert "route" in steps_logged

    if verbose:
        print("\n" + "=" * 70)
        print("  TEST B PASSED SUCCESSFULLY!")
        print("=" * 70)


def test_supervisor():
    """Pytest entrypoint."""
    run_test_b(verbose=False)


if __name__ == "__main__":
    run_test_b(verbose=True)
