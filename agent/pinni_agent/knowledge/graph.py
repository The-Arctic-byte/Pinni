"""Knowledge Graph: schema, projection from events/profiles/stories, and queries.

Nodes:
  User {user:<id>}
  Story {story:<id>}
  Category {category:<name>}
  Place {place:<id>}
  Channel {channel:<id>}
  Source {source:<name>}
  Tag {tag:<name>}

Relationships:
  (Story)-[:BELONGS_TO]->(Category)
  (Story)-[:LOCATED_AT]->(Place)
  (Story)-[:PUBLISHED_BY]->(Source)
  (Story)-[:HAS_TAG]->(Tag)
  (User)-[:PERFORMED {type, weight, ts}]->(Story)
  (User)-[:FOLLOWS]->(Place)
  (User)-[:JOINED]->(Channel)
  (User)-[:INTERESTED_IN {weight}]->(Category)
  (User)-[:SIMILAR_TO {score}]->(User)

The supervisor accesses this graph to inspect interactions, query relationships,
find similar readers, and suggest channels.
"""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ..config import Settings, default_settings
from ..types import Event, Profile, Story


@dataclass
class GraphNode:
    uid: str
    label: str
    props: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    src: str
    rel: str
    dst: str
    props: Dict[str, Any] = field(default_factory=dict)


class KnowledgeGraph:
    """Knowledge graph engine with in-memory graph and optional Neo4j projection."""

    def __init__(self, settings: Optional[Settings] = None):
        self.s = settings or default_settings
        self.nodes: Dict[str, GraphNode] = {}
        self.out_edges: Dict[str, List[GraphEdge]] = defaultdict(list)
        self.in_edges: Dict[str, List[GraphEdge]] = defaultdict(list)
        self._neo4j_driver = None
        self._init_neo4j()

    def _init_neo4j(self) -> None:
        try:
            from neo4j import GraphDatabase
            self._neo4j_driver = GraphDatabase.driver(
                self.s.neo4j_uri,
                auth=(self.s.neo4j_user, self.s.neo4j_password),
            )
            # Test connectivity
            self._neo4j_driver.verify_connectivity()
        except Exception:
            # Fallback gracefully to in-memory graph
            self._neo4j_driver = None

    @property
    def has_neo4j(self) -> bool:
        return self._neo4j_driver is not None

    # ---- Graph Primitives ----

    def merge_node(self, uid: str, label: str, props: Optional[Dict[str, Any]] = None) -> None:
        p = props or {}
        if uid in self.nodes:
            self.nodes[uid].props.update(p)
        else:
            self.nodes[uid] = GraphNode(uid=uid, label=label, props=p)

        if self._neo4j_driver:
            try:
                with self._neo4j_driver.session() as session:
                    query = f"MERGE (n:{label} {{uid: $uid}}) SET n += $props"
                    session.run(query, uid=uid, props=p)
            except Exception:
                pass

    def merge_edge(
        self,
        src: str,
        rel: str,
        dst: str,
        props: Optional[Dict[str, Any]] = None,
    ) -> None:
        p = props or {}
        # Remove existing edge of same rel to update props
        self.out_edges[src] = [e for e in self.out_edges[src] if not (e.rel == rel and e.dst == dst)]
        self.in_edges[dst] = [e for e in self.in_edges[dst] if not (e.rel == rel and e.src == src)]

        edge = GraphEdge(src=src, rel=rel, dst=dst, props=p)
        self.out_edges[src].append(edge)
        self.in_edges[dst].append(edge)

        if self._neo4j_driver:
            try:
                with self._neo4j_driver.session() as session:
                    query = (
                        "MATCH (a {uid: $src}), (b {uid: $dst}) "
                        f"MERGE (a)-[r:{rel}]->(b) SET r += $props"
                    )
                    session.run(query, src=src, dst=dst, props=p)
            except Exception:
                pass

    # ---- Domain Projections ----

    def record_story(self, story: Dict[str, Any]) -> None:
        sid = f"story:{story['id']}"
        self.merge_node(
            sid,
            "Story",
            {
                "id": story["id"],
                "scale": story.get("scale"),
                "placeId": story.get("placeId"),
                "category": story.get("category"),
                "risk": story.get("risk"),
                "importance": story.get("importance", 0.5),
            },
        )

        # Category
        cat = story.get("category")
        if cat:
            cid = f"category:{cat}"
            self.merge_node(cid, "Category", {"name": cat})
            self.merge_edge(sid, "BELONGS_TO", cid)

        # Place
        place_id = story.get("placeId")
        if place_id:
            pid = f"place:{place_id}"
            self.merge_node(pid, "Place", {"id": place_id})
            self.merge_edge(sid, "LOCATED_AT", pid)

        # Sources
        for src in story.get("sources", []):
            s_name = src.get("name")
            if s_name:
                s_uid = f"source:{s_name.lower().replace(' ', '-')}"
                self.merge_node(s_uid, "Source", {"name": s_name})
                self.merge_edge(sid, "PUBLISHED_BY", s_uid)

        # Tags
        for tag in story.get("tags", []):
            t_uid = f"tag:{tag.lower()}"
            self.merge_node(t_uid, "Tag", {"name": tag})
            self.merge_edge(sid, "HAS_TAG", t_uid)

    def record_profile(self, profile: Dict[str, Any]) -> None:
        user_id = profile["userId"]
        u_uid = f"user:{user_id}"
        self.merge_node(
            u_uid,
            "User",
            {
                "id": user_id,
                "language": profile.get("language", "en"),
                "homePlaceId": profile.get("homePlaceId"),
                "homeCountryCode": profile.get("homeCountryCode"),
                "targetGroups": profile.get("targetGroups", []),
            },
        )

        # Category weights
        for cat, w in profile.get("categoryWeights", {}).items():
            cid = f"category:{cat}"
            self.merge_node(cid, "Category", {"name": cat})
            self.merge_edge(u_uid, "INTERESTED_IN", cid, {"weight": float(w)})

        # Followed places
        for pid in profile.get("followedPlaceIds", []):
            p_uid = f"place:{pid}"
            self.merge_node(p_uid, "Place", {"id": pid})
            self.merge_edge(u_uid, "FOLLOWS", p_uid)

    def record_event(self, event: Dict[str, Any]) -> None:
        """Handle interaction event and project into knowledge graph."""
        user_id = event["userId"]
        u_uid = f"user:{user_id}"
        self.merge_node(u_uid, "User", {"id": user_id})

        etype = event["type"]
        ts = event.get("occurredAt", "")
        story_id = event.get("storyId")
        channel_id = event.get("channelId")
        place_id = event.get("placeId")
        val = event.get("value")

        if story_id:
            s_uid = f"story:{story_id}"
            self.merge_node(s_uid, "Story", {"id": story_id})

            # Interaction weight mapping
            weight = 0.5
            if etype == "like":
                weight = 1.0
            elif etype == "share" or etype == "save":
                weight = 0.9
            elif etype == "open":
                weight = 0.4
            elif etype == "dwell":
                # value is seconds, cap at 120s
                seconds = float(val or 10)
                weight = min(1.0, 0.3 + (seconds / 120.0) * 0.7)
            elif etype == "skip":
                weight = -0.3
            elif etype == "dislike":
                weight = -0.7
            elif etype in ("reject", "notForMe"):
                weight = -1.0

            self.merge_edge(
                u_uid,
                "PERFORMED",
                s_uid,
                {"type": etype, "weight": weight, "ts": ts, "value": val},
            )

        if channel_id:
            c_uid = f"channel:{channel_id}"
            self.merge_node(c_uid, "Channel", {"id": channel_id})
            if etype == "joinChannel":
                self.merge_edge(u_uid, "JOINED", c_uid, {"ts": ts})
            elif etype == "leaveChannel":
                # Remove edge
                self.out_edges[u_uid] = [e for e in self.out_edges[u_uid] if not (e.rel == "JOINED" and e.dst == c_uid)]

        if place_id:
            p_uid = f"place:{place_id}"
            self.merge_node(p_uid, "Place", {"id": place_id})
            if etype == "followPlace":
                self.merge_edge(u_uid, "FOLLOWS", p_uid, {"ts": ts})
            elif etype == "unfollowPlace":
                self.out_edges[u_uid] = [e for e in self.out_edges[u_uid] if not (e.rel == "FOLLOWS" and e.dst == p_uid)]

    # ---- Queries for Supervisor & Recommendation ----

    def get_user_interactions(self, user_id: str) -> List[Dict[str, Any]]:
        u_uid = f"user:{user_id}"
        out = []
        for e in self.out_edges.get(u_uid, []):
            if e.rel == "PERFORMED" and e.dst.startswith("story:"):
                sid = e.dst.split("story:")[1]
                out.append({"storyId": sid, **e.props})
        return out

    def get_user_followed_places(self, user_id: str) -> List[str]:
        u_uid = f"user:{user_id}"
        return [e.dst.split("place:")[1] for e in self.out_edges.get(u_uid, []) if e.rel == "FOLLOWS"]

    def get_user_joined_channels(self, user_id: str) -> List[str]:
        u_uid = f"user:{user_id}"
        return [e.dst.split("channel:")[1] for e in self.out_edges.get(u_uid, []) if e.rel == "JOINED"]

    def find_similar_users(self, user_id: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """Find users with similar preferences, followed places, and channel memberships."""
        u_uid = f"user:{user_id}"
        if u_uid not in self.nodes:
            return []

        # Collect target user features
        my_channels = set(self.get_user_joined_channels(user_id))
        my_places = set(self.get_user_followed_places(user_id))
        my_pos_stories = {
            e.dst for e in self.out_edges.get(u_uid, [])
            if e.rel == "PERFORMED" and e.props.get("weight", 0) > 0
        }
        my_features = my_channels | {f"place:{p}" for p in my_places} | my_pos_stories

        all_users = [
            uid.split("user:")[1] for uid in self.nodes.keys()
            if uid.startswith("user:") and uid != u_uid
        ]

        scored: List[Tuple[str, float]] = []
        for other in all_users:
            other_uid = f"user:{other}"
            other_channels = set(self.get_user_joined_channels(other))
            other_places = set(self.get_user_followed_places(other))
            other_pos_stories = {
                e.dst for e in self.out_edges.get(other_uid, [])
                if e.rel == "PERFORMED" and e.props.get("weight", 0) > 0
            }
            other_features = other_channels | {f"place:{p}" for p in other_places} | other_pos_stories

            union = my_features | other_features
            if not union:
                scored.append((other, 0.0))
                continue
            intersection = my_features & other_features
            jaccard = len(intersection) / len(union)
            scored.append((other, jaccard))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def suggest_channels(self, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Suggest channels followed by similar users (satisfies B3 channel suggestion requirement)."""
        joined = set(self.get_user_joined_channels(user_id))
        similar = self.find_similar_users(user_id, top_k=5)

        channel_counts: Dict[str, List[str]] = defaultdict(list)
        for other_id, sim in similar:
            if sim > 0:
                for ch in self.get_user_joined_channels(other_id):
                    if ch not in joined:
                        channel_counts[ch].append(other_id)

        suggestions = []
        for ch, supporters in channel_counts.items():
            ch_node = self.nodes.get(f"channel:{ch}")
            title = ch_node.props.get("title", ch) if ch_node else ch
            count = len(supporters)
            sample_person = supporters[0]
            reason_en = f"{count} readers with similar interests follow this"
            reason_fi = f"{count} samankaltaisista kiinnostuksen kohteista pitävää lukijaa seuraa tätä"
            reason_fa = f"{count} کاربر با علایق مشابه این کانال را دنبال می‌کنند"
            suggestions.append({
                "channelId": ch,
                "score": round(min(1.0, count * 0.35), 2),
                "reason": {
                    "en": reason_en,
                    "fi": reason_fi,
                    "fa": reason_fa,
                },
                "similarUsersCount": count,
            })

        suggestions.sort(key=lambda s: s["score"], reverse=True)
        return suggestions[:limit]

    def collaborative_story_scores(self, user_id: str) -> Dict[str, float]:
        """Compute collaborative recommendation boost based on what similar people liked."""
        similar = self.find_similar_users(user_id, top_k=5)
        story_scores: Dict[str, float] = defaultdict(float)

        for other_id, sim in similar:
            if sim <= 0:
                continue
            interactions = self.get_user_interactions(other_id)
            for it in interactions:
                sid = it["storyId"]
                w = it.get("weight", 0.0)
                if w > 0:
                    story_scores[sid] += sim * w

        # Normalize to [0, 1]
        if story_scores:
            max_v = max(story_scores.values())
            if max_v > 0:
                for sid in story_scores:
                    story_scores[sid] = min(1.0, story_scores[sid] / max_v)
        return dict(story_scores)
