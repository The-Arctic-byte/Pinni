"""Editor domains: each editor reviews only the stories and reports in their news categories.

The categories are stored on the user (backend only, not part of the contract User). An editor with
no categories, and every admin, sees everything."""

import json
import sqlite3

from .errors import forbidden


def get(conn: sqlite3.Connection, user_id: str) -> list[str] | None:
    row = conn.execute("SELECT domains FROM users WHERE id = ?", (user_id,)).fetchone()
    return json.loads(row["domains"]) if row and row["domains"] else None


def put(conn: sqlite3.Connection, user_id: str, categories: list[str] | None) -> None:
    conn.execute("UPDATE users SET domains = ? WHERE id = ?", (json.dumps(categories) if categories else None, user_id))


class Scope:
    """What one signed-in editor may see in the admin page."""

    def __init__(self, conn: sqlite3.Connection, user: dict):
        self.categories = None if user["role"] == "admin" else get(conn, user["id"])

    def covers(self, item: dict) -> bool:
        """A story or a report: both carry a category."""
        return not self.categories or item.get("category") in self.categories

    def check(self, item: dict) -> None:
        if not self.covers(item):
            raise forbidden("This is outside your editor domain")
