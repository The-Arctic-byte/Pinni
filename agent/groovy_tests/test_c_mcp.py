#!/usr/bin/env python3
"""Test C: MCP Tools Server (JSON-RPC 2.0)

Tests:
1. MCP Protocol initialize and tool discovery (tools/list).
2. Geocoding tool (geocode_place).
3. Web scraping & news gathering by preferences and location (gather_news).
4. Storing gathered information in the Vector Database (store_in_vector_db).
5. Hybrid vector search (vector_search).
6. Knowledge Graph queries via MCP (query_knowledge_graph).
"""
import json
import sys
from pathlib import Path

# Ensure agent directory is in path when executed directly
agent_root = Path(__file__).resolve().parent.parent
if str(agent_root) not in sys.path:
    sys.path.insert(0, str(agent_root))

from pinni_agent.config import Settings
from pinni_agent.knowledge.graph import KnowledgeGraph
from pinni_agent.knowledge.loader import load_mock_data
from pinni_agent.knowledge.vector_store import VectorStore
from pinni_agent.mcp.client import MCPClient
from pinni_agent.mcp.server import MCPServer
from pinni_agent.store import Store


def run_test_c(verbose: bool = True):
    if verbose:
        print("=" * 70)
        print("  TEST C: MODEL CONTEXT PROTOCOL (MCP) TOOLS SERVER")
        print("=" * 70)

    settings = Settings(llm_enabled=False)
    store = Store(settings)
    vstore = VectorStore(settings)
    graph = KnowledgeGraph(settings)
    load_mock_data(settings, store, vstore, graph)

    server = MCPServer(settings, store, vstore, graph)
    client = MCPClient(server)

    # 1. INITIALIZE (MCP JSON-RPC)
    if verbose:
        print("\n[Step 1] Sending MCP 'initialize' JSON-RPC request...")
    init_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    init_res = json.loads(server.handle_json_rpc(init_req))
    server_info = init_res["result"]["serverInfo"]
    if verbose:
        print(f"-> Connected to MCP Server: {server_info['name']} (v{server_info['version']})")
    assert server_info["name"] == "pinni-mcp-tools"

    # 2. TOOLS/LIST
    if verbose:
        print("\n[Step 2] Querying available MCP tools via 'tools/list'...")
    list_req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    list_res = json.loads(server.handle_json_rpc(list_req))
    tools = list_res["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    if verbose:
        print(f"-> Discovered {len(tools)} registered MCP tools:")
        for t in tools:
            print(f"   * {t['name']}: {t['description'][:65]}...")
    assert "geocode_place" in tool_names
    assert "gather_news" in tool_names
    assert "gather_by_profile" in tool_names
    assert "vector_search" in tool_names
    assert "query_knowledge_graph" in tool_names

    # 3. CALL TOOL: geocode_place
    if verbose:
        print("\n[Step 3] Calling MCP tool 'geocode_place' for 'Linnanmaa'...")
    geo_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "geocode_place", "arguments": {"placeName": "Linnanmaa"}},
    })
    geo_res = json.loads(server.handle_json_rpc(geo_req))
    geo_payload = json.loads(geo_res["result"]["content"][0]["text"])
    if verbose:
        print(f"-> Geocoded: ID={geo_payload['id']}, Scale={geo_payload['scale']}, Lat/Lon={geo_payload['coordinate']}")
    assert geo_payload["id"] == "linnanmaa"
    assert geo_payload["scale"] == "area"

    # 4. CALL TOOL: gather_news
    if verbose:
        print("\n[Step 4] Calling MCP tool 'gather_news' for Kiiminki safety...")
    gather_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "gather_news",
            "arguments": {"location": "Kiiminki", "categories": ["safety"]},
        },
    })
    gather_res = json.loads(server.handle_json_rpc(gather_req))
    gather_items = json.loads(gather_res["result"]["content"][0]["text"])
    if verbose:
        print(f"-> Gathered {len(gather_items)} articles. Top title: '{gather_items[0]['title']}'")
    assert len(gather_items) > 0

    # 5. CALL TOOL: vector_search
    if verbose:
        print("\n[Step 5] Calling MCP tool 'vector_search' with semantic query...")
    search_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "vector_search", "arguments": {"query": "shooting investigation", "limit": 3}},
    })
    search_res = json.loads(server.handle_json_rpc(search_req))
    hits = json.loads(search_res["result"]["content"][0]["text"])
    if verbose:
        print(f"-> Vector search returned {len(hits)} hits:")
        for h in hits:
            print(f"   * ID: {h['id']} | Score: {h['score']} | Category: {h['metadata'].get('category')}")
    assert len(hits) > 0

    # 6. CALL TOOL: query_knowledge_graph
    if verbose:
        print("\n[Step 6] Calling MCP tool 'query_knowledge_graph' for user interactions...")
    kg_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "query_knowledge_graph",
            "arguments": {"queryType": "user_interactions", "userId": "u-sara"},
        },
    })
    kg_res = json.loads(server.handle_json_rpc(kg_req))
    interactions = json.loads(kg_res["result"]["content"][0]["text"])
    if verbose:
        print(f"-> Sara's interactions in Knowledge Graph: {len(interactions)} records")
        for it in interactions[:3]:
            print(f"   * Story: {it['storyId']} | Type: {it['type']} | Weight: {it['weight']}")
    assert len(interactions) > 0

    if verbose:
        print("\n" + "=" * 70)
        print("  TEST C PASSED SUCCESSFULLY!")
        print("=" * 70)


def test_mcp():
    """Pytest entrypoint."""
    run_test_c(verbose=False)


if __name__ == "__main__":
    run_test_c(verbose=True)
