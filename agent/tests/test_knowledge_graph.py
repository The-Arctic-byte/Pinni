"""Tests for Knowledge Graph projection, user interactions, similar people, and channel suggestions."""
import pytest

from pinni_agent.config import Settings
from pinni_agent.knowledge.graph import KnowledgeGraph
from pinni_agent.knowledge.loader import load_mock_data
from pinni_agent.store import Store


@pytest.fixture
def graph_setup(tmp_path):
    settings = Settings(
        sqlite_path=str(tmp_path / "test.db"),
        data_dir=tmp_path,
        llm_enabled=False,
    )
    store = Store(settings)
    graph = KnowledgeGraph(settings)
    # Seed mock data
    load_mock_data(settings=settings, store=store, graph=graph)
    return {"settings": settings, "store": store, "graph": graph}


def test_knowledge_graph_projection_from_seed(graph_setup):
    graph = graph_setup["graph"]

    # Check that stories, categories, places, and channels exist as nodes
    assert f"story:kiiminki-shooting" in graph.nodes
    assert f"place:kiiminki" in graph.nodes
    assert f"category:safety" in graph.nodes
    assert f"channel:persian-oulu" in graph.nodes
    assert f"user:u-sara" in graph.nodes


def test_user_interactions_recorded_and_visible(graph_setup):
    graph = graph_setup["graph"]

    # Interactions for u-sara from contract/mock/events.json
    interactions = graph.get_user_interactions("u-sara")
    assert len(interactions) > 0

    story_ids = {it["storyId"] for it in interactions}
    assert "kiiminki-shooting" in story_ids

    # Sara joined channel persian-oulu in mock events
    joined = graph.get_user_joined_channels("u-sara")
    assert "persian-oulu" in joined


def test_similar_users_and_channel_suggestions(graph_setup):
    graph = graph_setup["graph"]

    # Record another student user who also follows Linnanmaa and Persian channel
    graph.record_event({
        "id": "ev-test-1",
        "userId": "u-ali",
        "type": "joinChannel",
        "channelId": "persian-oulu",
        "occurredAt": "2026-10-24T10:00:00+03:00",
    })
    graph.record_event({
        "id": "ev-test-2",
        "userId": "u-ali",
        "type": "joinChannel",
        "channelId": "student-housing-exchange",
        "occurredAt": "2026-10-24T10:05:00+03:00",
    })
    graph.record_event({
        "id": "ev-test-3",
        "userId": "u-ali",
        "type": "followPlace",
        "placeId": "kiiminki",
        "occurredAt": "2026-10-24T10:10:00+03:00",
    })

    # Ali and Sara share persian-oulu and kiiminki place
    similar = graph.find_similar_users("u-sara")
    similar_ids = [u for u, _ in similar]
    assert "u-ali" in similar_ids

    # Channel suggestion for Sara should include student-housing-exchange from Ali
    suggestions = graph.suggest_channels("u-sara")
    suggested_channel_ids = [s["channelId"] for s in suggestions]
    assert "student-housing-exchange" in suggested_channel_ids
    assert any(s["score"] > 0 for s in suggestions)
    assert any("en" in s["reason"] for s in suggestions)
