"""Knowledge graph: who interacted with what, for "similar people" queries.

    (:User)-[:RATED {score}]->(:Story)      sum of event signals (likes, opens, rejects, ...)
    (:User)-[:MEMBER_OF]->(:Channel)
    (:User)-[:FOLLOWS]->(:Place)
    (:User)-[:LIVES_IN]->(:Place)
    (:User)-[:IN_GROUP]->(:Group)            target group, residence:nonEu, housing:psoas, ...
    (:Story)-[:ABOUT]->(:Topic)              category
    (:Story)-[:TAGGED]->(:Tag)
    (:Story)-[:IN]->(:Place)
    (:Story)-[:FROM]->(:Source)
    (:Place)-[:PART_OF]->(:Place)
    (:Channel)-[:IN]->(:Place)

SQLite stays the source of truth (events are append-only there); the graph is derived and can be
rebuilt from it at any time (`rebuild`). Without PINNI_NEO4J_URI an in-memory graph with the same
queries is used, which is enough for development and tests."""

import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Protocol

from . import db

# Event weight for a user's rating of a story. Unlisted types carry no taste signal.
SIGNAL = {
    "like": 1.0, "share": 1.0, "save": 1.0, "confirm": 0.5, "open": 0.3, "postToChannel": 0.5,
    "skip": -0.2, "dislike": -1.0, "notForMe": -1.0, "reject": -1.5, "flagWrong": -0.3,
}

# Weights of each kind of overlap between two people.
SHARED_STORY = 1.0
SHARED_CHANNEL = 1.0
SHARED_HOME = 0.5
SHARED_GROUP = 0.5


def signal(event: dict) -> float:
    if event["type"] == "dwell":
        return min(event.get("value", 0) / 60, 1.0) * 0.5
    return SIGNAL.get(event["type"], 0.0)


def user_groups(profile: dict) -> set[str]:
    """Matches Story.affects, e.g. 'residents:kiiminki', 'residence:nonEu', 'student'."""
    groups = set(profile.get("targetGroups", []))
    if profile.get("homePlaceId"):
        groups.add(f"residents:{profile['homePlaceId']}")
    if profile.get("residence"):
        groups.add(f"residence:{profile['residence']['status']}")
    if profile.get("housing"):
        groups.add(f"housing:{profile['housing']['provider']}")
    return groups


class Graph(Protocol):
    def is_empty(self) -> bool: ...
    def upsert_place(self, place: dict) -> None: ...
    def upsert_story(self, story: dict) -> None: ...
    def upsert_channel(self, channel: dict) -> None: ...
    def upsert_profile(self, profile: dict) -> None: ...
    def rate(self, user_id: str, story_id: str, delta: float) -> None: ...
    def set_member(self, user_id: str, channel_id: str, member: bool) -> None: ...
    def set_follow(self, user_id: str, place_id: str, follow: bool) -> None: ...
    def clear_ratings(self, user_id: str) -> None: ...
    def similar_users(self, user_id: str, limit: int = 50) -> list[tuple[str, float]]: ...
    def channel_counts(self, user_ids: list[str]) -> dict[str, list[str]]: ...
    def positive_ratings(self, user_ids: list[str]) -> dict[str, dict[str, float]]: ...
    def joined(self, user_id: str) -> set[str]: ...
    def close(self) -> None: ...


class MemoryGraph:
    """The same model as the Neo4j graph, in dictionaries."""

    def __init__(self):
        self.places: dict[str, str | None] = {}
        self.stories: dict[str, dict] = {}
        self.channels: dict[str, str | None] = {}
        self.ratings: dict[str, dict[str, float]] = defaultdict(dict)
        self.members: dict[str, set[str]] = defaultdict(set)
        self.follows: dict[str, set[str]] = defaultdict(set)
        self.home: dict[str, str] = {}
        self.groups: dict[str, set[str]] = defaultdict(set)

    def is_empty(self) -> bool:
        return not (self.places or self.stories)

    def upsert_place(self, place: dict) -> None:
        self.places[place["id"]] = place.get("parentId")

    def upsert_story(self, story: dict) -> None:
        self.stories[story["id"]] = {"category": story["category"], "placeId": story["placeId"],
                                     "tags": story.get("tags", []), "status": story["status"]}

    def upsert_channel(self, channel: dict) -> None:
        self.channels[channel["id"]] = channel.get("placeId")

    def upsert_profile(self, profile: dict) -> None:
        user_id = profile["userId"]
        if profile.get("homePlaceId"):
            self.home[user_id] = profile["homePlaceId"]
        else:
            self.home.pop(user_id, None)
        self.groups[user_id] = user_groups(profile)
        self.follows[user_id] = set(profile.get("followedPlaceIds", []))

    def rate(self, user_id: str, story_id: str, delta: float) -> None:
        self.ratings[user_id][story_id] = self.ratings[user_id].get(story_id, 0.0) + delta

    def set_member(self, user_id: str, channel_id: str, member: bool) -> None:
        (self.members[user_id].add if member else self.members[user_id].discard)(channel_id)

    def set_follow(self, user_id: str, place_id: str, follow: bool) -> None:
        (self.follows[user_id].add if follow else self.follows[user_id].discard)(place_id)

    def clear_ratings(self, user_id: str) -> None:
        self.ratings.pop(user_id, None)

    def similar_users(self, user_id: str, limit: int = 50) -> list[tuple[str, float]]:
        score: dict[str, float] = defaultdict(float)
        liked = {s for s, v in self.ratings.get(user_id, {}).items() if v > 0}
        for other, rated in self.ratings.items():
            if other != user_id:
                shared = sum(1 for s, v in rated.items() if v > 0 and s in liked)
                if shared:
                    score[other] += SHARED_STORY * shared
        mine = self.members.get(user_id, set())
        for other, channels in self.members.items():
            if other != user_id and mine & channels:
                score[other] += SHARED_CHANNEL * len(mine & channels)
        home = self.home.get(user_id)
        for other, place in self.home.items():
            if other != user_id and home and place == home:
                score[other] += SHARED_HOME
        my_groups = self.groups.get(user_id, set())
        for other, groups in self.groups.items():
            if other != user_id and my_groups & groups:
                score[other] += SHARED_GROUP * len(my_groups & groups)
        return sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]

    def channel_counts(self, user_ids: list[str]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for u in user_ids:
            for c in self.members.get(u, ()):
                out[c].append(u)
        return dict(out)

    def positive_ratings(self, user_ids: list[str]) -> dict[str, dict[str, float]]:
        return {u: {s: v for s, v in self.ratings.get(u, {}).items() if v > 0} for u in user_ids}

    def joined(self, user_id: str) -> set[str]:
        return set(self.members.get(user_id, ()))

    def close(self) -> None:
        pass


class Neo4jGraph:
    def __init__(self, uri: str, user: str, password: str):
        from neo4j import GraphDatabase

        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver.verify_connectivity()
        for label in ("User", "Story", "Place", "Channel", "Topic", "Tag", "Source", "Group"):
            self._run(f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE")

    def _run(self, query: str, **params) -> list[dict]:
        records, _, _ = self.driver.execute_query(query, params, database_="neo4j")
        return [r.data() for r in records]

    def is_empty(self) -> bool:
        return self._run("MATCH (n) RETURN count(n) AS n")[0]["n"] == 0

    def upsert_place(self, place: dict) -> None:
        self._run(
            """
            MERGE (p:Place {id: $id}) SET p.kind = $kind
            WITH p
            OPTIONAL MATCH (p)-[old:PART_OF]->() DELETE old
            WITH DISTINCT p WHERE $parent IS NOT NULL
            MERGE (parent:Place {id: $parent})
            MERGE (p)-[:PART_OF]->(parent)
            """,
            id=place["id"], kind=place["kind"], parent=place.get("parentId"),
        )

    def upsert_story(self, story: dict) -> None:
        self._run(
            """
            MERGE (s:Story {id: $id}) SET s.status = $status, s.importance = $importance
            WITH s
            OPTIONAL MATCH (s)-[old:ABOUT|TAGGED|IN|FROM]->() DELETE old
            WITH DISTINCT s
            MERGE (t:Topic {id: $category}) MERGE (s)-[:ABOUT]->(t)
            MERGE (p:Place {id: $place}) MERGE (s)-[:IN]->(p)
            FOREACH (tag IN $tags | MERGE (g:Tag {id: tag}) MERGE (s)-[:TAGGED]->(g))
            FOREACH (src IN $sources | MERGE (o:Source {id: src}) MERGE (s)-[:FROM]->(o))
            """,
            id=story["id"], status=story["status"], importance=story["importance"], category=story["category"],
            place=story["placeId"], tags=story.get("tags", []), sources=[s["name"] for s in story["sources"]],
        )

    def upsert_channel(self, channel: dict) -> None:
        self._run(
            """
            MERGE (c:Channel {id: $id})
            WITH c
            OPTIONAL MATCH (c)-[old:IN]->() DELETE old
            WITH DISTINCT c WHERE $place IS NOT NULL
            MERGE (p:Place {id: $place}) MERGE (c)-[:IN]->(p)
            """,
            id=channel["id"], place=channel.get("placeId"),
        )

    def upsert_profile(self, profile: dict) -> None:
        self._run(
            """
            MERGE (u:User {id: $id})
            WITH u
            OPTIONAL MATCH (u)-[old:LIVES_IN|IN_GROUP|FOLLOWS]->() DELETE old
            WITH DISTINCT u
            FOREACH (home IN CASE WHEN $home IS NULL THEN [] ELSE [$home] END |
                MERGE (p:Place {id: home}) MERGE (u)-[:LIVES_IN]->(p))
            FOREACH (g IN $groups | MERGE (n:Group {id: g}) MERGE (u)-[:IN_GROUP]->(n))
            FOREACH (f IN $follows | MERGE (p:Place {id: f}) MERGE (u)-[:FOLLOWS]->(p))
            """,
            id=profile["userId"], home=profile.get("homePlaceId"), groups=sorted(user_groups(profile)),
            follows=profile.get("followedPlaceIds", []),
        )

    def rate(self, user_id: str, story_id: str, delta: float) -> None:
        self._run(
            """
            MERGE (u:User {id: $user}) MERGE (s:Story {id: $story})
            MERGE (u)-[r:RATED]->(s) ON CREATE SET r.score = 0.0
            SET r.score = r.score + $delta
            """,
            user=user_id, story=story_id, delta=delta,
        )

    def set_member(self, user_id: str, channel_id: str, member: bool) -> None:
        if member:
            self._run("MERGE (u:User {id: $user}) MERGE (c:Channel {id: $channel}) MERGE (u)-[:MEMBER_OF]->(c)",
                      user=user_id, channel=channel_id)
        else:
            self._run("MATCH (:User {id: $user})-[m:MEMBER_OF]->(:Channel {id: $channel}) DELETE m",
                      user=user_id, channel=channel_id)

    def set_follow(self, user_id: str, place_id: str, follow: bool) -> None:
        if follow:
            self._run("MERGE (u:User {id: $user}) MERGE (p:Place {id: $place}) MERGE (u)-[:FOLLOWS]->(p)",
                      user=user_id, place=place_id)
        else:
            self._run("MATCH (:User {id: $user})-[f:FOLLOWS]->(:Place {id: $place}) DELETE f",
                      user=user_id, place=place_id)

    def clear_ratings(self, user_id: str) -> None:
        self._run("MATCH (:User {id: $user})-[r:RATED]->() DELETE r", user=user_id)

    def similar_users(self, user_id: str, limit: int = 50) -> list[tuple[str, float]]:
        rows = self._run(
            """
            MATCH (me:User {id: $id})
            CALL {
                WITH me
                MATCH (me)-[a:RATED]->(:Story)<-[b:RATED]-(o:User)
                WHERE a.score > 0 AND b.score > 0 AND o <> me
                RETURN o, count(*) * $story AS w
                UNION ALL
                WITH me
                MATCH (me)-[:MEMBER_OF]->(:Channel)<-[:MEMBER_OF]-(o:User) WHERE o <> me
                RETURN o, count(*) * $channel AS w
                UNION ALL
                WITH me
                MATCH (me)-[:LIVES_IN]->(:Place)<-[:LIVES_IN]-(o:User) WHERE o <> me
                RETURN o, $home AS w
                UNION ALL
                WITH me
                MATCH (me)-[:IN_GROUP]->(:Group)<-[:IN_GROUP]-(o:User) WHERE o <> me
                RETURN o, count(*) * $group AS w
            }
            RETURN o.id AS id, sum(w) AS score
            ORDER BY score DESC, id
            LIMIT $limit
            """,
            id=user_id, limit=limit, story=SHARED_STORY, channel=SHARED_CHANNEL, home=SHARED_HOME, group=SHARED_GROUP,
        )
        return [(r["id"], r["score"]) for r in rows]

    def channel_counts(self, user_ids: list[str]) -> dict[str, list[str]]:
        rows = self._run(
            "MATCH (u:User)-[:MEMBER_OF]->(c:Channel) WHERE u.id IN $ids RETURN c.id AS channel, collect(u.id) AS users",
            ids=user_ids,
        )
        return {r["channel"]: r["users"] for r in rows}

    def positive_ratings(self, user_ids: list[str]) -> dict[str, dict[str, float]]:
        rows = self._run(
            "MATCH (u:User)-[r:RATED]->(s:Story) WHERE u.id IN $ids AND r.score > 0 "
            "RETURN u.id AS user, s.id AS story, r.score AS score",
            ids=user_ids,
        )
        out: dict[str, dict[str, float]] = {u: {} for u in user_ids}
        for r in rows:
            out[r["user"]][r["story"]] = r["score"]
        return out

    def joined(self, user_id: str) -> set[str]:
        rows = self._run("MATCH (:User {id: $id})-[:MEMBER_OF]->(c:Channel) RETURN c.id AS id", id=user_id)
        return {r["id"] for r in rows}

    def close(self) -> None:
        self.driver.close()


def record_event(graph: Graph, event: dict) -> None:
    """Apply one event to the graph."""
    t, user = event["type"], event["userId"]
    if event.get("storyId"):
        weight = signal(event)
        if weight:
            graph.rate(user, event["storyId"], weight)
    if t in ("joinChannel", "leaveChannel") and event.get("channelId"):
        graph.set_member(user, event["channelId"], t == "joinChannel")
    if t in ("followPlace", "unfollowPlace") and event.get("placeId"):
        graph.set_follow(user, event["placeId"], t == "followPlace")


def replay_user(conn: sqlite3.Connection, graph: Graph, user_id: str) -> None:
    """Rebuild one user's ratings from SQLite, respecting a learned-preferences reset."""
    graph.clear_ratings(user_id)
    row = conn.execute("SELECT learned_reset_at FROM users WHERE id = ?", (user_id,)).fetchone()
    cutoff = datetime.fromisoformat(row["learned_reset_at"]) if row and row["learned_reset_at"] else None
    profile = db.get_doc(conn, "profiles", user_id)
    if profile:
        graph.upsert_profile(profile)
    for e in db.docs(conn, "SELECT doc FROM events WHERE user_id = ? ORDER BY occurred_at", (user_id,)):
        if e["type"] in ("followPlace", "unfollowPlace"):
            record_event(graph, e)
        elif e.get("storyId") and (cutoff is None or datetime.fromisoformat(e["occurredAt"]) > cutoff):
            weight = signal(e)
            if weight:
                graph.rate(user_id, e["storyId"], weight)
    # Memberships come from their table, which already reflects joins and leaves.
    for (channel_id,) in conn.execute("SELECT channel_id FROM memberships WHERE user_id = ?", (user_id,)):
        graph.set_member(user_id, channel_id, True)


def rebuild(conn: sqlite3.Connection, graph: Graph) -> None:
    """Load everything from SQLite into an empty graph."""
    for p in db.docs(conn, "SELECT doc FROM places"):
        graph.upsert_place(p)
    for s in db.docs(conn, "SELECT doc FROM stories"):
        graph.upsert_story(s)
    for c in db.docs(conn, "SELECT doc FROM channels"):
        graph.upsert_channel(c)
    for (user_id,) in conn.execute("SELECT id FROM users"):
        replay_user(conn, graph, user_id)


def connect(settings) -> Graph:
    if settings.neo4j_uri:
        return Neo4jGraph(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    return MemoryGraph()
