"""Tests for MCP tools, source gathering, and vector store indexing."""
import json
import pytest

from pinni_agent.config import Settings
from pinni_agent.knowledge.graph import KnowledgeGraph
from pinni_agent.knowledge.vector_store import VectorStore
from pinni_agent.mcp.client import MCPClient
from pinni_agent.mcp.server import MCPServer
from pinni_agent.mcp.tools.geo import geocode_place
from pinni_agent.mcp.tools.sources import (
    gather_by_user_profile,
    gather_city_of_oulu,
    gather_kaleva_rss,
    gather_psoas_news,
    gather_university_news,
    gather_web_by_preferences_and_location,
    store_gathered_in_vector_db,
)
from pinni_agent.store import Store


@pytest.fixture
def test_setup(tmp_path):
    settings = Settings(
        sqlite_path=str(tmp_path / "test.db"),
        data_dir=tmp_path,
        llm_enabled=False,
    )
    store = Store(settings)
    vstore = VectorStore(settings)
    graph = KnowledgeGraph(settings)
    server = MCPServer(settings=settings, store=store, vector_store=vstore, graph=graph)
    client = MCPClient(server)
    return {
        "settings": settings,
        "store": store,
        "vstore": vstore,
        "graph": graph,
        "server": server,
        "client": client,
    }


def test_source_gathering_by_preferences_and_location():
    # 1. Location match
    items_kiiminki = gather_web_by_preferences_and_location(location="kiiminki")
    assert len(items_kiiminki) > 0
    assert any("kiiminki" in i["title"].lower() or "kiiminki" in i["place"].lower() for i in items_kiiminki)

    # 2. Preference match (e.g. culture)
    items_culture = gather_web_by_preferences_and_location(categories=["culture"])
    assert any(i["category"] == "culture" for i in items_culture)


def test_gather_by_profile_triggers_psoas_and_university(test_setup):
    vstore = test_setup["vstore"]

    # Student profile with PSOAS consent
    sara_profile = {
        "userId": "u-sara",
        "language": "fa",
        "targetGroups": ["student"],
        "homePlaceId": "kiiminki",
        "housing": {"provider": "psoas", "consent": True},
        "interests": ["sports clubs", "persian community"],
        "wantedNews": ["student housing", "residence permits"],
        "categoryWeights": {"safety": 0.9, "housing": 0.8},
    }

    gathered = gather_by_user_profile(sara_profile, vector_store=vstore)
    sources = {i["source"] for i in gathered}

    # Must watch PSOAS and University because of housing and target group
    assert "PSOAS" in sources
    assert "University of Oulu" in sources
    assert "Kaleva" in sources

    # Data must be stored in the vector database
    assert vstore.count() > 0
    hits = vstore.search(query="student housing heating", limit=5)
    assert len(hits) > 0


def test_geocode_place_resolves_contract_places():
    geo_kiiminki = geocode_place("Kiiminki")
    assert geo_kiiminki["id"] == "kiiminki"
    assert geo_kiiminki["scale"] == "area"
    assert geo_kiiminki["coordinate"]["lat"] == 65.131
    assert geo_kiiminki["radiusMeters"] == 1500

    geo_oulu = geocode_place("Oulu")
    assert geo_oulu["id"] == "oulu"
    assert geo_oulu["scale"] == "city"


def test_mcp_server_protocol_and_tool_execution(test_setup):
    server = test_setup["server"]

    # 1. Initialize
    init_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    init_resp = json.loads(server.handle_json_rpc(init_req))
    assert init_resp["result"]["serverInfo"]["name"] == "pinni-mcp-tools"

    # 2. List tools
    list_req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    list_resp = json.loads(server.handle_json_rpc(list_req))
    tools = {t["name"] for t in list_resp["result"]["tools"]}
    assert "gather_news" in tools
    assert "gather_by_profile" in tools
    assert "vector_search" in tools
    assert "geocode_place" in tools
    assert "query_knowledge_graph" in tools
    assert "record_interaction" in tools

    # 3. Call tool: geocode_place
    call_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "geocode_place", "arguments": {"placeName": "Linnanmaa"}},
    })
    call_resp = json.loads(server.handle_json_rpc(call_req))
    content_text = call_resp["result"]["content"][0]["text"]
    geo_data = json.loads(content_text)
    assert geo_data["id"] == "linnanmaa"
    assert geo_data["scale"] == "area"
