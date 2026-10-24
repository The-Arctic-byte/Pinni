from fastapi import APIRouter, Body, Request

from .. import auth, db, stores
from ..auth import Conn, CurrentUser
from ..errors import ApiError

router = APIRouter(prefix="/v1", tags=["auth"])


def preferred_language(request: Request) -> str:
    """First two-letter tag of Accept-Language, e.g. 'fa-IR,fa;q=0.9' -> 'fa'."""
    header = request.headers.get("accept-language", "")
    tag = header.split(",")[0].split(";")[0].strip()[:2].lower()
    return tag if len(tag) == 2 and tag.isalpha() else "en"


@router.post("/auth/anonymous", status_code=201)
def anonymous(conn: Conn):
    user_id = db.new_id("u")
    with conn:
        conn.execute("INSERT INTO users (id, role, created_at) VALUES (?, 'reader', ?)", (user_id, db.now()))
        token = auth.new_session(conn, user_id)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"token": token, "user": db.user_doc(row)}


def _adopt_anonymous(conn, anonymous_id: str, user_id: str) -> None:
    """Move an anonymous reader's history to the account that just signed in."""
    conn.execute("UPDATE events SET user_id = ?, doc = json_set(doc, '$.userId', ?) WHERE user_id = ?",
                 (user_id, user_id, anonymous_id))
    has_profile = conn.execute("SELECT 1 FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
    if not has_profile:
        conn.execute("UPDATE profiles SET user_id = ?, doc = json_set(doc, '$.userId', ?) WHERE user_id = ?",
                     (user_id, user_id, anonymous_id))
    conn.execute("UPDATE devices SET user_id = ? WHERE user_id = ?", (user_id, anonymous_id))
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (anonymous_id,))
    conn.execute("UPDATE users SET merged_into = ? WHERE id = ?", (user_id, anonymous_id))


@router.post("/auth/login")
def login(request: Request, conn: Conn,
          body: dict = Body(..., examples=[{"email": "sara@pinni.test", "password": "pinni-dev"}])):
    email, password = body.get("email"), body.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        raise ApiError(422, "invalid", "email and password are required")
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if row is None or not auth.verify_password(password, row["password_hash"]):
        raise ApiError(401, "unauthorized", "Wrong email or password")
    adopted = None
    with conn:
        anonymous_token = body.get("anonymousToken")
        if isinstance(anonymous_token, str):
            anon = auth.user_for_token(conn, anonymous_token)
            if anon is not None and anon["role"] == "reader" and anon["id"] != row["id"]:
                _adopt_anonymous(conn, anon["id"], row["id"])
                adopted = anon["id"]
        token = auth.new_session(conn, row["id"])
    if adopted:
        stores.replay_user(request, conn, adopted)
        stores.replay_user(request, conn, row["id"])
    return {"token": token, "user": db.user_doc(row)}


@router.get("/me")
def me(user: CurrentUser):
    return user
