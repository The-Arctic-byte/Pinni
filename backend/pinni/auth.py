"""Bearer tokens and roles.

Tokens are random strings; only their SHA-256 is stored, so a leaked database cannot be replayed.
Roles are ordered: reader < member < editor < admin."""

import hashlib
import hmac
import secrets
import sqlite3
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .errors import ApiError, forbidden

ROLES = ["reader", "member", "editor", "admin"]


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(candidate.hex(), digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(conn: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at) VALUES (?, ?, ?)",
        (_token_hash(token), user_id, db.now()),
    )
    return token


def user_for_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
        (_token_hash(token),),
    ).fetchone()


def get_conn(request: Request):
    conn = db.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


# Declared so /docs shows an "Authorize" button; errors stay in the contract's shape below.
bearer = HTTPBearer(auto_error=False)


def current_user(conn: Conn, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> dict:
    if credentials is None or not credentials.credentials:
        raise ApiError(401, "unauthorized", "Missing bearer token; get one from POST /v1/auth/anonymous")
    row = user_for_token(conn, credentials.credentials.strip())
    if row is None:
        raise ApiError(401, "unauthorized", "Unknown or expired token")
    return db.user_doc(row)


CurrentUser = Annotated[dict, Depends(current_user)]


def at_least(user: dict, role: str) -> bool:
    return ROLES.index(user["role"]) >= ROLES.index(role)


def require(role: str):
    def check(user: CurrentUser) -> dict:
        if not at_least(user, role):
            raise forbidden(f"This needs the {role} role; you are a {user['role']}")
        return user

    return Depends(check)


Member = Annotated[dict, require("member")]
Editor = Annotated[dict, require("editor")]
Admin = Annotated[dict, require("admin")]
