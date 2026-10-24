"""SQLite storage. Contract objects are stored as JSON documents (`doc`) next to the few columns
we query on, so the stored shape is exactly the contract shape.

Events are append-only. Neo4j (knowledge graph) and Chroma (vectors) arrive in C2."""

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    display_name TEXT,
    verified_via TEXT,
    email TEXT UNIQUE,
    password_hash TEXT,
    created_at TEXT NOT NULL,
    learned_reset_at TEXT,
    domains TEXT,  -- editors: JSON list of the categories they review; NULL = everything
    merged_into TEXT  -- anonymous readers who signed in: the account that took their history
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS places (
    id TEXT PRIMARY KEY,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
    user_id TEXT NOT NULL REFERENCES users(id),
    channel_id TEXT NOT NULL REFERENCES channels(id),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (user_id, channel_id)
);
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES channels(id),
    created_at TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    reporter_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    type TEXT NOT NULL,
    story_id TEXT,
    occurred_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_user ON events(user_id, occurred_at);
CREATE TABLE IF NOT EXISTS devices (
    apns_token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    platform TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    step TEXT NOT NULL,
    message TEXT NOT NULL,
    story_id TEXT,
    report_id TEXT
);
"""

# Tables whose rows are a contract document keyed by `key`.
DOC_TABLES = {
    "profiles": "user_id",
    "places": "id",
    "stories": "id",
    "channels": "id",
    "posts": "id",
    "reports": "id",
    "notifications": "id",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    """A contract Id (lowercase slug) for objects the backend creates."""
    return f"{prefix}-{secrets.token_hex(6)}"


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # Databases created before editor domains existed.
    columns = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "domains" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN domains TEXT")
    if "merged_into" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN merged_into TEXT")


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def get_doc(conn: sqlite3.Connection, table: str, key: str) -> dict | None:
    row = conn.execute(f"SELECT doc FROM {table} WHERE {DOC_TABLES[table]} = ?", (key,)).fetchone()
    return json.loads(row["doc"]) if row else None


def docs(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    """Run a query whose first column is `doc` and decode every row."""
    return [json.loads(r[0]) for r in conn.execute(sql, params)]


def put_doc(conn: sqlite3.Connection, table: str, doc: dict, **columns) -> None:
    """Insert or replace a document. `columns` fills the table's other columns."""
    key = DOC_TABLES[table]
    keyfield = "userId" if key == "user_id" else "id"
    cols = {key: doc[keyfield], **columns, "doc": json.dumps(doc, ensure_ascii=False)}
    names = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    conn.execute(f"INSERT OR REPLACE INTO {table} ({names}) VALUES ({marks})", tuple(cols.values()))


def put_story(conn: sqlite3.Connection, story: dict) -> None:
    put_doc(conn, "stories", story, status=story["status"])


def put_report(conn: sqlite3.Connection, report: dict) -> None:
    put_doc(conn, "reports", report, reporter_id=report["reporterId"], status=report["status"], created_at=report["createdAt"])


def put_notification(conn: sqlite3.Connection, n: dict) -> None:
    put_doc(conn, "notifications", n, user_id=n["userId"], created_at=n["createdAt"])


def put_post(conn: sqlite3.Connection, post: dict) -> None:
    put_doc(conn, "posts", post, channel_id=post["channelId"], created_at=post["createdAt"])


def add_event(conn: sqlite3.Connection, event: dict) -> bool:
    """Append an event. Returns False if an event with this id already exists (idempotent upload)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO events (id, user_id, type, story_id, occurred_at, received_at, doc) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (event["id"], event["userId"], event["type"], event.get("storyId"), event["occurredAt"], now(),
         json.dumps(event, ensure_ascii=False)),
    )
    return cur.rowcount == 1


def audit(conn: sqlite3.Connection, actor: str, step: str, message: str,
          story_id: str | None = None, report_id: str | None = None) -> None:
    conn.execute(
        "INSERT INTO audit (at, actor, step, message, story_id, report_id) VALUES (?, ?, ?, ?, ?, ?)",
        (now(), actor, step, message, story_id, report_id),
    )


def audit_entry(row: sqlite3.Row) -> dict:
    entry = {"at": row["at"], "actor": row["actor"], "step": row["step"], "message": row["message"]}
    if row["story_id"]:
        entry["storyId"] = row["story_id"]
    if row["report_id"]:
        entry["reportId"] = row["report_id"]
    return entry


def user_doc(row: sqlite3.Row) -> dict:
    user = {"id": row["id"], "role": row["role"], "createdAt": row["created_at"]}
    if row["display_name"]:
        user["displayName"] = row["display_name"]
    if row["verified_via"]:
        user["verifiedVia"] = row["verified_via"]
    return user
