"""SQLite backing store and data repository for events, profiles, stories and audit logs."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Settings, default_settings
from .types import AuditEntry, Event, Profile, QueueItem, Story


class Store:
    """Manages SQLite storage for events, profiles, stories, queue, and audit trail."""

    def __init__(self, settings: Optional[Settings] = None):
        self.s = settings or default_settings
        db_path = Path(self.s.sqlite_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stories (
                    id TEXT PRIMARY KEY,
                    status TEXT,
                    scale TEXT,
                    place_id TEXT,
                    category TEXT,
                    risk TEXT,
                    importance REAL,
                    payload JSON,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT PRIMARY KEY,
                    payload JSON,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    type TEXT,
                    story_id TEXT,
                    payload JSON,
                    occurred_at TEXT
                );

                CREATE TABLE IF NOT EXISTS queue (
                    id TEXT PRIMARY KEY,
                    kind TEXT,
                    risk TEXT,
                    payload JSON,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT,
                    actor TEXT,
                    step TEXT,
                    message TEXT,
                    story_id TEXT,
                    report_id TEXT
                );
                """
            )

    # ---- Stories ----

    def save_story(self, story: Dict[str, Any]) -> None:
        sid = story["id"]
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO stories (id, status, scale, place_id, category, risk, importance, payload, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    scale=excluded.scale,
                    place_id=excluded.place_id,
                    category=excluded.category,
                    risk=excluded.risk,
                    importance=excluded.importance,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    sid,
                    story.get("status", "draft"),
                    story.get("scale"),
                    story.get("placeId"),
                    story.get("category"),
                    story.get("risk", "none"),
                    story.get("importance", 0.5),
                    json.dumps(story),
                    story.get("updatedAt", ""),
                ),
            )

    def get_story(self, story_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT payload FROM stories WHERE id = ?", (story_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_stories(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            rows = self.conn.execute("SELECT payload FROM stories WHERE status = ?", (status,)).fetchall()
        else:
            rows = self.conn.execute("SELECT payload FROM stories").fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # ---- Profiles ----

    def save_profile(self, profile: Dict[str, Any]) -> None:
        uid = profile["userId"]
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO profiles (user_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (uid, json.dumps(profile), profile.get("updatedAt", "")),
            )

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT payload FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_profiles(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT payload FROM profiles").fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # ---- Events ----

    def save_event(self, event: Dict[str, Any]) -> None:
        eid = event["id"]
        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO events (id, user_id, type, story_id, payload, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    event["userId"],
                    event["type"],
                    event.get("storyId"),
                    json.dumps(event),
                    event.get("occurredAt", ""),
                ),
            )

    def list_user_events(self, user_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT payload FROM events WHERE user_id = ? ORDER BY occurred_at ASC",
            (user_id,),
        ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # ---- Review Queue (Red-Risk & Community Reports) ----

    def add_to_queue(self, queue_item: Dict[str, Any]) -> None:
        qid = queue_item["id"]
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO queue (id, kind, risk, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind=excluded.kind,
                    risk=excluded.risk,
                    payload=excluded.payload
                """,
                (
                    qid,
                    queue_item["kind"],
                    queue_item.get("risk", "none"),
                    json.dumps(queue_item),
                    queue_item.get("createdAt", ""),
                ),
            )

    def list_queue(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT payload FROM queue ORDER BY created_at DESC").fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # ---- Audit Trail ----

    def log_audit(self, entry: Dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO audit_log (at, actor, step, message, story_id, report_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.get("at"),
                    entry.get("actor", "agent:supervisor"),
                    entry.get("step"),
                    entry.get("message"),
                    entry.get("storyId"),
                    entry.get("reportId"),
                ),
            )

    def list_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT at, actor, step, message, story_id as storyId, report_id as reportId FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
