"""Model Context Protocol (MCP) tool server implementation.

Exposes news gathering, geocoding, vector database, knowledge graph, and publishing tools
via standard MCP JSON-RPC 2.0 specification.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable, Dict, List, Optional

from ..config import Settings, default_settings
from ..knowledge.graph import KnowledgeGraph
from ..knowledge.vector_store import VectorStore
from ..recommender.engine import RecommendationEngine
from ..store import Store
from .tools.geo import geocode_place
from .tools.publishing import assess_risk, create_story_draft, route_to_human_queue
from .tools.sources import (
    gather_by_user_profile,
    gather_city_of_oulu,
    gather_kaleva_rss,
    gather_psoas_news,
    gather_university_news,
    gather_web_by_preferences_and_location,
    retrieve_web_information,
    store_gathered_in_vector_db,
)
from .tools.stores import get_user_event_history, query_knowledge_graph, vector_search


class MCPServer:
    """MCP standard server providing tool discovery and execution."""

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
        self.recommender = RecommendationEngine(self.s, self.store, self.vector_store, self.graph)
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.handlers: Dict[str, Callable] = {}
        self._register_tools()

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable,
    ) -> None:
        self.tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }
        self.handlers[name] = handler

    def _register_tools(self) -> None:
        # 1. gather_news
        self.register_tool(
            name="gather_news",
            description="Gather news from online sources (Kaleva RSS, City of Oulu, PSOAS, University) based on location and topic preferences.",
            input_schema={
                "type": "object",
                "properties": {
                    "preferences": {"type": "array", "items": {"type": "string"}},
                    "location": {"type": "string", "description": "Area, city or place name"},
                    "categories": {"type": "array", "items": {"type": "string"}},
                    "source": {"type": "string", "enum": ["all", "kaleva", "oulu", "psoas", "university"]},
                },
            },
            handler=self._handle_gather_news,
        )

        # 2. gather_by_profile
        self.register_tool(
            name="gather_by_profile",
            description="Add and gather sources based on a person's profile (e.g. PSOAS tenant -> PSOAS site, university student -> campus news) and store in vector database.",
            input_schema={
                "type": "object",
                "required": ["userId"],
                "properties": {
                    "userId": {"type": "string"},
                },
            },
            handler=self._handle_gather_by_profile,
        )

        # 3. store_in_vector_db
        self.register_tool(
            name="store_in_vector_db",
            description="Store news items or documents in the vector database with embeddings and metadata.",
            input_schema={
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {"type": "array", "items": {"type": "object"}},
                },
            },
            handler=self._handle_store_in_vector_db,
        )

        # 4. vector_search
        self.register_tool(
            name="vector_search",
            description="Hybrid vector and lexical BM25 search over news stories and documents.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "category": {"type": "string"},
                    "scale": {"type": "string"},
                    "placeId": {"type": "string"},
                    "risk": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
            handler=self._handle_vector_search,
        )

        # 5. geocode_place
        self.register_tool(
            name="geocode_place",
            description="Resolve a place name into canonical placeId, scale, coordinate (lat, lon) and radiusMeters.",
            input_schema={
                "type": "object",
                "required": ["placeName"],
                "properties": {
                    "placeName": {"type": "string"},
                },
            },
            handler=lambda args: geocode_place(args["placeName"]),
        )

        # 6. query_knowledge_graph
        self.register_tool(
            name="query_knowledge_graph",
            description="Query user interactions, relationships, similar people and channel suggestions from the Knowledge Graph.",
            input_schema={
                "type": "object",
                "required": ["queryType"],
                "properties": {
                    "queryType": {
                        "type": "string",
                        "enum": ["user_interactions", "similar_readers", "suggested_channels", "collaborative_stories"],
                    },
                    "userId": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
            handler=self._handle_query_knowledge_graph,
        )

        # 7. record_interaction
        self.register_tool(
            name="record_interaction",
            description="Record a reader interaction event in SQLite and project into the Knowledge Graph.",
            input_schema={
                "type": "object",
                "required": ["id", "userId", "type"],
                "properties": {
                    "id": {"type": "string"},
                    "userId": {"type": "string"},
                    "type": {"type": "string"},
                    "storyId": {"type": "string"},
                    "channelId": {"type": "string"},
                    "placeId": {"type": "string"},
                    "value": {"type": "number"},
                },
            },
            handler=self._handle_record_interaction,
        )

        # 8. create_draft
        self.register_tool(
            name="create_draft",
            description="Create a story draft, assess risk, and route red-risk stories to human editor queue.",
            input_schema={
                "type": "object",
                "required": ["story"],
                "properties": {
                    "story": {"type": "object"},
                    "trail": {"type": "array", "items": {"type": "object"}},
                },
            },
            handler=lambda args: create_story_draft(self.store, args["story"], args.get("trail")),
        )

        # 9. route_to_human
        self.register_tool(
            name="route_to_human",
            description="Route a red-risk story or community report to the editor review queue.",
            input_schema={
                "type": "object",
                "required": ["id", "kind", "risk"],
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["agentDraft", "communityReport", "readerFlag"]},
                    "risk": {"type": "string", "enum": ["none", "amber", "red"]},
                    "trail": {"type": "array", "items": {"type": "object"}},
                },
            },
            handler=lambda args: route_to_human_queue(
                self.store, args["id"], args["kind"], args["risk"], args.get("trail")
            ),
        )

        # 10. suggest_channels
        self.register_tool(
            name="suggest_channels",
            description="Suggest community channels based on what similar people follow in the Knowledge Graph.",
            input_schema={
                "type": "object",
                "required": ["userId"],
                "properties": {
                    "userId": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
            },
            handler=lambda args: self.graph.suggest_channels(args["userId"], args.get("limit", 5)),
        )

        # 11. retrieve_web_news
        self.register_tool(
            name="retrieve_web_news",
            description="Retrieve and scrape news/information from websites based on tags, words (keywords), URLs, and location, and store them in the vector database.",
            input_schema={
                "type": "object",
                "properties": {
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "words": {"type": ["string", "array"], "description": "Search keywords or query phrase"},
                    "urls": {"type": "array", "items": {"type": "string"}, "description": "Specific website URLs to scrape"},
                    "location": {"type": "string"},
                    "categories": {"type": "array", "items": {"type": "string"}},
                    "store_in_vector_db": {"type": "boolean", "default": True},
                },
            },
            handler=self._handle_retrieve_web_news,
        )

        # 12. recommend_news_for_user
        self.register_tool(
            name="recommend_news_for_user",
            description="Recommend personalized news stories for a user based on Knowledge Graph collaborative filtering, user interaction history, vector profile matching, and hard filters.",
            input_schema={
                "type": "object",
                "required": ["userId"],
                "properties": {
                    "userId": {"type": "string"},
                    "scale": {"type": "string"},
                    "placeId": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                    "includeStories": {"type": "boolean", "default": True},
                },
            },
            handler=self._handle_recommend_news_for_user,
        )

    # ---- Tool Handlers ----

    def _handle_retrieve_web_news(self, args: Dict[str, Any]) -> Dict[str, Any]:
        store_vec = args.get("store_in_vector_db", True)
        items = retrieve_web_information(
            tags=args.get("tags"),
            words=args.get("words"),
            urls=args.get("urls"),
            location=args.get("location"),
            categories=args.get("categories"),
            vector_store=self.vector_store if store_vec else None,
        )
        return {
            "retrievedCount": len(items),
            "storedInVectorDb": store_vec,
            "items": items,
        }

    def _handle_recommend_news_for_user(self, args: Dict[str, Any]) -> Dict[str, Any]:
        user_id = args["userId"]
        limit = args.get("limit", 10)
        scale = args.get("scale")
        place_id = args.get("placeId")
        include_stories = args.get("includeStories", True)

        feed_page = self.recommender.get_feed(
            user_id=user_id,
            scale=scale,
            place_id=place_id,
            limit=limit,
        )
        if include_stories:
            for item in feed_page.get("items", []):
                story = self.store.get_story(item["storyId"])
                if story:
                    item["story"] = story
        return feed_page

    def _handle_gather_news(self, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        src = args.get("source", "all")
        if src == "kaleva":
            return gather_kaleva_rss()
        elif src == "oulu":
            return gather_city_of_oulu()
        elif src == "psoas":
            return gather_psoas_news()
        elif src == "university":
            return gather_university_news()
        return gather_web_by_preferences_and_location(
            preferences=args.get("preferences"),
            location=args.get("location"),
            categories=args.get("categories"),
        )

    def _handle_gather_by_profile(self, args: Dict[str, Any]) -> Dict[str, Any]:
        user_id = args["userId"]
        profile = self.store.get_profile(user_id)
        if not profile:
            return {"error": f"Profile for user '{user_id}' not found", "items": []}
        items = gather_by_user_profile(profile, vector_store=self.vector_store)
        return {"userId": user_id, "gatheredCount": len(items), "items": items}

    def _handle_store_in_vector_db(self, args: Dict[str, Any]) -> Dict[str, Any]:
        items = args.get("items", [])
        stored = store_gathered_in_vector_db(items, self.vector_store)
        return {"storedCount": stored, "totalDocs": self.vector_store.count()}

    def _handle_vector_search(self, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        return vector_search(
            vector_store=self.vector_store,
            query=args["query"],
            category=args.get("category"),
            scale=args.get("scale"),
            place_id=args.get("placeId"),
            risk=args.get("risk"),
            limit=args.get("limit", 10),
        )

    def _handle_query_knowledge_graph(self, args: Dict[str, Any]) -> Any:
        return query_knowledge_graph(
            graph=self.graph,
            query_type=args["queryType"],
            user_id=args.get("userId"),
            limit=args.get("limit", 10),
        )

    def _handle_record_interaction(self, args: Dict[str, Any]) -> Dict[str, Any]:
        self.store.save_event(args)
        self.graph.record_event(args)
        return {"status": "recorded", "eventId": args["id"]}

    # ---- JSON-RPC MCP Interface ----

    def list_tools(self) -> List[Dict[str, Any]]:
        return list(self.tools.values())

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        if name not in self.handlers:
            raise ValueError(f"Tool '{name}' not found")
        args = arguments or {}
        return self.handlers[name](args)

    def handle_json_rpc(self, request_str: str) -> str:
        """Process a single JSON-RPC 2.0 MCP request string."""
        try:
            req = json.loads(request_str)
        except Exception as e:
            return json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            })

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "pinni-mcp-tools", "version": "0.1.0"},
                },
            }
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.list_tools()},
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                result = self.call_tool(tool_name, tool_args)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                        ]
                    },
                }
            except Exception as e:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": str(e)},
                }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found"},
            }

        return json.dumps(resp)

    def run_stdio(self) -> None:
        """Run MCP stdio event loop."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            resp = self.handle_json_rpc(line)
            sys.stdout.write(resp + "\n")
            sys.stdout.flush()
