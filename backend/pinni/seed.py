"""Fill an empty database from contract/mock so the API answers with the same data the app uses.

Feeds and channel suggestions are not seeded: the backend computes them."""

import sqlite3

from . import db, domains
from .auth import hash_password
from .contract import Contract

# Development sign-in for the mock personas: <id without "u-">@pinni.test / DEV_PASSWORD.
DEV_PASSWORD = "pinni-dev"


# Development editors with a domain (backend only; contract/mock has one editor who sees everything).
DEV_EDITORS = [
    {"id": "u-leo", "displayName": "Leo (politics desk)", "categories": ["politics", "economy", "society", "world"]},
    {"id": "u-mira", "displayName": "Mira (city desk)", "categories": ["safety", "transport", "cityLife", "housing", "work"]},
]


def dev_email(user_id: str) -> str:
    return f"{user_id.removeprefix('u-')}@pinni.test"


def seed(conn: sqlite3.Connection, contract: Contract, dev_accounts: bool) -> None:
    m = contract.mock
    with conn:
        for p in m("places.json"):
            db.put_doc(conn, "places", p)
        for u in m("users.json"):
            signs_in = dev_accounts and u["role"] != "reader"
            conn.execute(
                "INSERT INTO users (id, role, display_name, verified_via, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (u["id"], u["role"], u.get("displayName"), u.get("verifiedVia"),
                 dev_email(u["id"]) if signs_in else None,
                 hash_password(DEV_PASSWORD) if signs_in else None,
                 u["createdAt"]),
            )
        if dev_accounts:
            for e in DEV_EDITORS:
                conn.execute(
                    "INSERT INTO users (id, role, display_name, email, password_hash, created_at) VALUES (?, 'editor', ?, ?, ?, ?)",
                    (e["id"], e["displayName"], dev_email(e["id"]), hash_password(DEV_PASSWORD), db.now()),
                )
                domains.put(conn, e["id"], e["categories"])
        for p in m("profiles.json"):
            db.put_doc(conn, "profiles", p)
        for s in m("stories.json"):
            db.put_story(conn, s)
        for c in m("channels.json"):
            db.put_doc(conn, "channels", c)
        for r in m("reports.json"):
            db.put_report(conn, r)
        for p in m("channel-posts.json"):
            db.put_post(conn, p)
        for n in m("notifications.json"):
            db.put_notification(conn, n)
        for e in m("events.json"):
            db.add_event(conn, e)
            if e["type"] == "joinChannel":
                # memberCount in channels.json already includes these members.
                conn.execute(
                    "INSERT OR IGNORE INTO memberships (user_id, channel_id, joined_at) VALUES (?, ?, ?)",
                    (e["userId"], e["channelId"], e["occurredAt"]),
                )
        db.audit(conn, "agent:seed", "gather", "Database seeded from contract/mock")
