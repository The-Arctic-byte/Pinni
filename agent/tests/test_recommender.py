"""Tests for B4 recommendation model, acceptance criteria, hard filters, and schema validity."""
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from pinni_agent.config import Settings
from pinni_agent.knowledge.graph import KnowledgeGraph
from pinni_agent.knowledge.loader import load_mock_data
from pinni_agent.knowledge.vector_store import VectorStore
from pinni_agent.recommender.engine import RecommendationEngine
from pinni_agent.store import Store


@pytest.fixture
def recommender_setup(tmp_path):
    settings = Settings(
        sqlite_path=str(tmp_path / "test.db"),
        data_dir=tmp_path,
        llm_enabled=False,
    )
    store = Store(settings)
    vstore = VectorStore(settings)
    graph = KnowledgeGraph(settings)
    load_mock_data(settings=settings, store=store, vector_store=vstore, graph=graph)
    engine = RecommendationEngine(settings=settings, store=store, vector_store=vstore, graph=graph)
    return {
        "engine": engine,
        "store": store,
        "vstore": vstore,
        "graph": graph,
        "settings": settings,
    }


def test_b4_acceptance_must_see_always_appears(recommender_setup):
    engine = recommender_setup["engine"]
    feed = engine.get_feed("u-sara")

    # Sara lives in Kiiminki -> kiiminki-shooting is a red-risk area safety story
    must_see_items = [it for it in feed["items"] if it["mustSee"]]
    assert len(must_see_items) > 0
    must_see_ids = [it["storyId"] for it in must_see_items]
    assert "kiiminki-shooting" in must_see_ids


def test_b4_acceptance_hard_filters_always_hold(recommender_setup):
    engine = recommender_setup["engine"]
    store = recommender_setup["store"]

    # In contract/mock/profiles.json, u-matti has hardFilters: {"tags": ["athletics"]}
    # Also in events.json, u-matti has an event type: "notForMe" on storyId: "athletics-euros-2030"
    feed_matti = engine.get_feed("u-matti")
    matti_story_ids = [it["storyId"] for it in feed_matti["items"]]
    assert "athletics-euros-2030" not in matti_story_ids

    # Now add a new notForMe event for u-sara on "lidl-ideapark"
    store.save_event({
        "id": "ev-test-not-for-me",
        "userId": "u-sara",
        "type": "notForMe",
        "storyId": "lidl-ideapark",
        "occurredAt": "2026-10-24T12:00:00+03:00",
    })

    feed_sara_updated = engine.get_feed("u-sara")
    sara_story_ids = [it["storyId"] for it in feed_sara_updated["items"]]
    assert "lidl-ideapark" not in sara_story_ids


def test_b4_acceptance_rankings_change_as_events_are_added(recommender_setup):
    engine = recommender_setup["engine"]
    store = recommender_setup["store"]
    graph = recommender_setup["graph"]

    # u-new starts with 0 events (cold start)
    feed_initial = engine.get_feed("u-new")
    assert feed_initial["personalization"] == 0.0
    initial_ids = [it["storyId"] for it in feed_initial["items"]]

    # Add 5 positive interaction events (likes, dwells) on shopping and culture stories
    test_events = [
        {"id": "ev-new-1", "userId": "u-new", "type": "open", "storyId": "lidl-ideapark", "occurredAt": "2026-10-24T10:00:00+03:00"},
        {"id": "ev-new-2", "userId": "u-new", "type": "dwell", "storyId": "lidl-ideapark", "value": 90, "occurredAt": "2026-10-24T10:02:00+03:00"},
        {"id": "ev-new-3", "userId": "u-new", "type": "like", "storyId": "lidl-ideapark", "occurredAt": "2026-10-24T10:03:00+03:00"},
        {"id": "ev-new-4", "userId": "u-new", "type": "open", "storyId": "muhos-data-centre", "occurredAt": "2026-10-24T10:10:00+03:00"},
        {"id": "ev-new-5", "userId": "u-new", "type": "like", "storyId": "muhos-data-centre", "occurredAt": "2026-10-24T10:12:00+03:00"},
    ]
    for ev in test_events:
        store.save_event(ev)
        graph.record_event(ev)

    feed_after = engine.get_feed("u-new")
    assert feed_after["personalization"] > 0.0

    # Rankings change: interacted stories receive higher relevance
    after_ids = [it["storyId"] for it in feed_after["items"]]
    assert after_ids != initial_ids

    # Lidl ideapark was liked and dwelt on: its rank and relevance increased
    rel_before = next(it["relevance"] for it in feed_initial["items"] if it["storyId"] == "lidl-ideapark")
    rel_after = next(it["relevance"] for it in feed_after["items"] if it["storyId"] == "lidl-ideapark")
    assert rel_after > rel_before


def test_feed_output_validates_against_contract_json_schema(recommender_setup):
    engine = recommender_setup["engine"]
    settings = recommender_setup["settings"]
    feed = engine.get_feed("u-sara")

    # Load schemas and build registry
    contract_schemas = settings.contract_dir / "schemas"
    schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in contract_schemas.glob("*.schema.json")}
    registry = Registry().with_resources(
        (name, Resource.from_contents(s)) for name, s in schemas.items()
    )

    validator = Draft202012Validator(
        {"$ref": "feed.schema.json"},
        registry=registry,
        format_checker=FormatChecker(),
    )

    errors = list(validator.iter_errors(feed))
    assert len(errors) == 0, f"Schema validation failed: {[e.message for e in errors]}"
