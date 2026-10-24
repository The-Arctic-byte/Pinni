"""Tests for B3 Supervisor Orchestrator and its 10 core functions."""
import pytest

from pinni_agent.agent.supervisor import Supervisor
from pinni_agent.agent.trace import SupervisorTrace
from pinni_agent.config import Settings
from pinni_agent.knowledge.graph import KnowledgeGraph
from pinni_agent.knowledge.loader import load_mock_data
from pinni_agent.knowledge.vector_store import VectorStore
from pinni_agent.store import Store


@pytest.fixture
def supervisor_setup(tmp_path):
    settings = Settings(
        sqlite_path=str(tmp_path / "test.db"),
        data_dir=tmp_path,
        llm_enabled=False,  # deterministic unit testing
    )
    store = Store(settings)
    vstore = VectorStore(settings)
    graph = KnowledgeGraph(settings)
    load_mock_data(settings=settings, store=store, vector_store=vstore, graph=graph)
    supervisor = Supervisor(settings=settings, store=store, vector_store=vstore, graph=graph)
    return {
        "supervisor": supervisor,
        "store": store,
        "vstore": vstore,
        "graph": graph,
    }


def test_supervisor_1_find(supervisor_setup):
    supervisor = supervisor_setup["supervisor"]
    # Find news by place
    hits = supervisor.find(place="kiiminki", limit=5)
    assert len(hits) > 0
    assert any(h["id"] == "kiiminki-shooting" for h in hits)

    # Find news by category
    hits_safety = supervisor.find(category="safety", limit=5)
    assert any(h["id"] == "kiiminki-shooting" for h in hits_safety)


def test_supervisor_2_gather_by_profile(supervisor_setup):
    supervisor = supervisor_setup["supervisor"]
    items = supervisor.gather_by_profile(user_id="u-sara")
    assert len(items) > 0
    sources = {i["source"] for i in items}
    assert "PSOAS" in sources
    assert "University of Oulu" in sources


def test_supervisor_3_select_and_classify(supervisor_setup):
    supervisor = supervisor_setup["supervisor"]

    raw_items = [
        # Normal news item
        {
            "title": "Kiiminki empty flat shooting under investigation",
            "description": "Police arrested one suspect.",
            "category": "safety",
            "place": "kiiminki",
            "source": "Kaleva",
        },
        # Duplicate of the same item
        {
            "title": "Kiiminki empty flat shooting under investigation",
            "description": "Police arrested one suspect.",
            "category": "safety",
            "place": "kiiminki",
            "source": "Kaleva",
        },
        # Irrelevant spam item
        {
            "title": "Online casino bonus win cash fast",
            "description": "Click here to win millions.",
            "source": "SpamBlog",
        },
    ]

    selected = supervisor.select(raw_items)
    # Deduplication and spam dropping: only 1 valid item selected
    assert len(selected) == 1
    item = selected[0]
    assert item["category"] == "safety"
    assert item["risk"] == "red"
    assert item["scale"] in ("area", "city")


def test_supervisor_4_explain(supervisor_setup):
    supervisor = supervisor_setup["supervisor"]
    story_item = {
        "title": "Winter bike lane snow plowing schedule released",
        "description": "City of Oulu announces priority routes for cyclists.",
        "category": "transport",
        "placeId": "oulu",
    }
    exp = supervisor.explain(story_item)
    assert "known" in exp
    assert "happened" in exp
    assert "forYou" in exp
    assert "context" in exp
    assert "question" in exp["context"]
    assert "answer" in exp["context"]


def test_supervisor_5_translate_and_check(supervisor_setup):
    supervisor = supervisor_setup["supervisor"]
    res = supervisor.translate_and_check(
        title="Student housing heating adjustments",
        for_you="Check your radiator settings before November 1st.",
        target_languages=["fi", "fa", "sv"],
    )
    translations = res["translations"]
    assert "en" in translations
    assert "fi" in translations
    assert "fa" in translations
    assert "sv" in translations

    tiers = res["tiers"]
    tier_langs = {t["language"] for t in tiers}
    assert {"en", "fi", "fa", "sv"}.issubset(tier_langs)


def test_supervisor_6_route_to_human(supervisor_setup):
    supervisor = supervisor_setup["supervisor"]
    store = supervisor_setup["store"]

    # Red-risk story must go to human queue
    queue_item = supervisor.route_to_human(
        story_or_report_id="test-shooting-draft",
        kind="agentDraft",
        risk="red",
    )
    assert queue_item["risk"] == "red"
    assert queue_item["kind"] == "agentDraft"

    # Confirm item appears in SQLite queue
    queue = store.list_queue()
    assert any(q["id"] == "test-shooting-draft" for q in queue)


def test_supervisor_7_distribute(supervisor_setup):
    supervisor = supervisor_setup["supervisor"]
    story = {
        "id": "kiiminki-safety-alert",
        "category": "safety",
        "risk": "red",
        "placeId": "kiiminki",
        "affects": ["residents:kiiminki"],
    }
    readers = supervisor.distribute(story)
    # Both Sara and Matti live in Kiiminki and have high safety / local interests
    reader_ids = [r["userId"] for r in readers]
    assert "u-sara" in reader_ids
    assert any(r["kind"] == "mustSee" for r in readers if r["userId"] == "u-sara")


def test_supervisor_8_moderate_community(supervisor_setup):
    supervisor = supervisor_setup["supervisor"]
    report = {
        "id": "report-icy-walkway",
        "category": "transport",
        "sensitive": False,
        "text": "Extremely icy sidewalk near Tuira bridge, two cyclists slipped.",
    }
    res = supervisor.moderate_community(report)
    assert res["reportId"] == "report-icy-walkway"
    assert res["queueItem"]["kind"] == "communityReport"


def test_supervisor_9_suggest_channels(supervisor_setup):
    supervisor = supervisor_setup["supervisor"]
    suggestions = supervisor.suggest_channels(user_id="u-sara")
    assert isinstance(suggestions, list)


def test_supervisor_10_audit_log(supervisor_setup):
    supervisor = supervisor_setup["supervisor"]
    # Run a pipeline step to generate audit events
    supervisor.find(place="oulu")
    supervisor.route_to_human("audit-test-id", "communityReport", "amber")

    logs = supervisor.audit_log(limit=50)
    assert len(logs) > 0
    steps = {l["step"] for l in logs}
    assert "find" in steps
    assert "route" in steps
