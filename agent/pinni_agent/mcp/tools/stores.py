"""Store query MCP tools: vector search, knowledge graph queries, and event history."""
from typing import Any, Dict, List, Optional

from ...knowledge.graph import KnowledgeGraph
from ...knowledge.vector_store import VectorStore
from ...store import Store


def vector_search(
    vector_store: VectorStore,
    query: str,
    category: Optional[str] = None,
    scale: Optional[str] = None,
    place_id: Optional[str] = None,
    risk: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Query the vector database for relevant stories and documents with metadata filters."""
    filters = {}
    if category:
        filters["category"] = category
    if scale:
        filters["scale"] = scale
    if place_id:
        filters["placeId"] = place_id
    if risk:
        filters["risk"] = risk

    hits = vector_store.search(query=query, limit=limit, filters=filters)
    return [
        {
            "id": h.id,
            "score": round(h.score, 4),
            "dense_rank": h.dense_rank,
            "bm25_rank": h.bm25_rank,
            "metadata": h.metadata,
        }
        for h in hits
    ]


def query_knowledge_graph(
    graph: KnowledgeGraph,
    query_type: str,
    user_id: Optional[str] = None,
    story_id: Optional[str] = None,
    limit: int = 10,
) -> Any:
    """Read-only knowledge graph query tool for supervisor agent.

    Supported query_types:
    - 'user_interactions': returns story interaction history
    - 'similar_readers': returns users with similar interests & channels
    - 'suggested_channels': returns channels joined by similar people
    - 'collaborative_stories': returns stories with collaborative recommendation boosts
    """
    if query_type == "user_interactions" and user_id:
        return graph.get_user_interactions(user_id)
    elif query_type == "similar_readers" and user_id:
        sims = graph.find_similar_users(user_id, top_k=limit)
        return [{"userId": u, "similarity": round(s, 3)} for u, s in sims]
    elif query_type == "suggested_channels" and user_id:
        return graph.suggest_channels(user_id, limit=limit)
    elif query_type == "collaborative_stories" and user_id:
        return graph.collaborative_story_scores(user_id)
    elif query_type == "story_node" and story_id:
        s_node = graph.nodes.get(f"story:{story_id}")
        return s_node.props if s_node else None
    return {"error": f"Unknown or invalid query_type '{query_type}'"}


def get_user_event_history(
    store: Store,
    user_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Retrieve user event history from SQLite append-only log."""
    events = store.list_user_events(user_id)
    return events[-limit:]
