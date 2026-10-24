from typing import Annotated

from fastapi import APIRouter, Body, Query, Request, Response

from .. import auth, db, ranking, recommender, stores
from ..auth import Conn, CurrentUser
from ..errors import ApiError, forbidden, not_found
from .auth import preferred_language

router = APIRouter(prefix="/v1", tags=["reader"])


def contract(request: Request):
    return request.app.state.contract


def visible(story: dict, user: dict) -> bool:
    """Readers and members only see published stories; editors see everything."""
    return story["status"] == "published" or auth.at_least(user, "editor")


@router.get("/profile")
def get_profile(request: Request, conn: Conn, user: CurrentUser):
    return db.get_doc(conn, "profiles", user["id"]) or ranking.default_profile(user["id"], preferred_language(request))


@router.put("/profile")
def put_profile(request: Request, conn: Conn, user: CurrentUser, body: dict = Body(...)):
    if body.get("userId") != user["id"]:
        raise forbidden("A profile can only be saved for yourself")
    contract(request).check("profile.schema.json", body)
    body["updatedAt"] = db.now()
    with conn:
        db.put_doc(conn, "profiles", body)
        db.add_event(conn, {"id": db.new_id("ev"), "userId": user["id"], "type": "profileEdit",
                            "detail": {"profile": body}, "context": {"screen": "profile"}, "occurredAt": body["updatedAt"]})
    stores.profile_changed(request, body)
    return body


@router.get("/profile/learned")
def get_learned(conn: Conn, user: CurrentUser):
    return ranking.learned_preferences(conn, user["id"])


@router.delete("/profile/learned", status_code=204)
def reset_learned(request: Request, conn: Conn, user: CurrentUser):
    with conn:
        conn.execute("UPDATE users SET learned_reset_at = ? WHERE id = ?", (db.now(), user["id"]))
    stores.replay_user(request, conn, user["id"])
    return Response(status_code=204)


@router.get("/feed")
def get_feed(request: Request, conn: Conn, user: CurrentUser,
             scale: Annotated[str | None, Query(pattern="^(area|city|finland|world)$")] = None,
             placeId: str | None = None,
             limit: Annotated[int, Query(ge=1, le=100)] = 30,
             cursor: str | None = None):
    return recommender.feed(conn, user["id"], scale, placeId, limit, cursor,
                            graph=stores.graph(request), vectors=stores.vectors(request))


@router.get("/stories")
def get_stories(conn: Conn, user: CurrentUser, ids: str = Query(...)):
    wanted = [i for i in ids.split(",") if i][:100]
    found = {}
    for story_id in wanted:
        story = db.get_doc(conn, "stories", story_id)
        if story and visible(story, user):
            found[story_id] = story
    return [found[i] for i in dict.fromkeys(wanted) if i in found]


@router.get("/stories/{story_id}")
def get_story(story_id: str, conn: Conn, user: CurrentUser):
    story = db.get_doc(conn, "stories", story_id)
    if story is None or not visible(story, user):
        raise not_found("Story")
    return story


@router.get("/places")
def get_places(conn: Conn, user: CurrentUser):
    return db.docs(conn, "SELECT doc FROM places ORDER BY id")


EVENTS_EXAMPLE = [{"id": "ev-test-1", "userId": "u-sara", "type": "notForMe", "storyId": "orpo-kyiv",
                   "occurredAt": "2026-10-24T12:00:00Z"}]


@router.post("/events", status_code=202)
def post_events(request: Request, conn: Conn, user: CurrentUser, body: list = Body(..., examples=[EVENTS_EXAMPLE])):
    if len(body) > 500:
        raise ApiError(422, "invalid", "At most 500 events per batch")
    c = contract(request)
    for i, event in enumerate(body):
        problems = c.errors("event.schema.json", event)
        if problems:
            raise ApiError(422, "invalid", f"[{i}] " + "; ".join(problems[:3]))
        if event["userId"] != user["id"]:
            raise forbidden(f"[{i}] events can only be uploaded for yourself")
    with conn:
        accepted = [e for e in body if db.add_event(conn, e)]
    stores.events_added(request, accepted)
    return {"accepted": len(accepted), "duplicates": len(body) - len(accepted)}


@router.get("/notifications")
def get_notifications(conn: Conn, user: CurrentUser):
    return db.docs(conn, "SELECT doc FROM notifications WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))


@router.post("/notifications/{notification_id}/read", status_code=204)
def read_notification(notification_id: str, conn: Conn, user: CurrentUser):
    n = db.get_doc(conn, "notifications", notification_id)
    if n is None or n["userId"] != user["id"]:
        raise not_found("Notification")
    if "readAt" not in n:
        n["readAt"] = db.now()
        with conn:
            db.put_notification(conn, n)
    return Response(status_code=204)


@router.put("/devices", status_code=204)
def put_device(conn: Conn, user: CurrentUser, body: dict = Body(...)):
    token, platform = body.get("apnsToken"), body.get("platform")
    if not isinstance(token, str) or not token or platform not in ("ios", "macos"):
        raise ApiError(422, "invalid", "apnsToken and platform (ios or macos) are required")
    with conn:
        conn.execute("INSERT OR REPLACE INTO devices (apns_token, user_id, platform, updated_at) VALUES (?, ?, ?, ?)",
                     (token, user["id"], platform, db.now()))
    return Response(status_code=204)
