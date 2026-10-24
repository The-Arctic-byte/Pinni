from fastapi import APIRouter, Body, Query, Request, Response

from .. import db, ranking, stores
from ..auth import Conn, CurrentUser, Member
from ..errors import ApiError, not_found

router = APIRouter(prefix="/v1", tags=["community"])


def _channel(conn, channel_id: str) -> dict:
    channel = db.get_doc(conn, "channels", channel_id)
    if channel is None:
        raise not_found("Channel")
    return channel


@router.get("/channels/suggested")
def suggested(request: Request, conn: Conn, user: CurrentUser):
    return ranking.suggested_channels(conn, user["id"], graph=stores.graph(request))


@router.get("/channels")
def get_channels(conn: Conn, user: CurrentUser, ids: str | None = Query(None)):
    if ids:
        wanted = [i for i in ids.split(",") if i]
        found = {c["id"]: c for c in (db.get_doc(conn, "channels", i) for i in wanted) if c}
        return [found[i] for i in dict.fromkeys(wanted) if i in found]
    return db.docs(conn, "SELECT c.doc FROM channels c JOIN memberships m ON m.channel_id = c.id "
                         "WHERE m.user_id = ? ORDER BY m.joined_at", (user["id"],))


def _set_membership(conn, user_id: str, channel: dict, join: bool) -> bool:
    if join:
        changed = conn.execute("INSERT OR IGNORE INTO memberships (user_id, channel_id, joined_at) VALUES (?, ?, ?)",
                               (user_id, channel["id"], db.now())).rowcount
    else:
        changed = conn.execute("DELETE FROM memberships WHERE user_id = ? AND channel_id = ?",
                               (user_id, channel["id"])).rowcount
    if changed:
        channel["memberCount"] = max(0, channel["memberCount"] + (1 if join else -1))
        db.put_doc(conn, "channels", channel)
        db.add_event(conn, {"id": db.new_id("ev"), "userId": user_id, "type": "joinChannel" if join else "leaveChannel",
                            "channelId": channel["id"], "context": {"screen": "community"}, "occurredAt": db.now()})
    return bool(changed)


@router.put("/channels/{channel_id}/membership", status_code=204)
def join(request: Request, channel_id: str, conn: Conn, user: Member):
    with conn:
        changed = _set_membership(conn, user["id"], _channel(conn, channel_id), True)
    if changed:
        stores.membership_changed(request, user["id"], channel_id, True)
    return Response(status_code=204)


@router.delete("/channels/{channel_id}/membership", status_code=204)
def leave(request: Request, channel_id: str, conn: Conn, user: CurrentUser):
    with conn:
        changed = _set_membership(conn, user["id"], _channel(conn, channel_id), False)
    if changed:
        stores.membership_changed(request, user["id"], channel_id, False)
    return Response(status_code=204)


@router.get("/channels/{channel_id}/posts")
def get_posts(channel_id: str, conn: Conn, user: CurrentUser):
    _channel(conn, channel_id)
    return db.docs(conn, "SELECT doc FROM posts WHERE channel_id = ? ORDER BY created_at DESC", (channel_id,))


@router.post("/channels/{channel_id}/posts", status_code=201)
def create_post(request: Request, channel_id: str, conn: Conn, user: Member, body: dict = Body(...)):
    _channel(conn, channel_id)
    story_id, text = body.get("storyId"), body.get("text")
    if story_id is None and text is None:
        raise ApiError(422, "invalid", "A post needs storyId or text")
    if story_id is not None:
        story = db.get_doc(conn, "stories", story_id) if isinstance(story_id, str) else None
        if story is None or story["status"] != "published":
            raise not_found("Story")
    post = {"id": db.new_id("post"), "channelId": channel_id, "authorId": user["id"], "likes": 0, "createdAt": db.now()}
    if story_id is not None:
        post["storyId"] = story_id
    if text is not None:
        post["text"] = text
    request.app.state.contract.check("channel.schema.json#/$defs/Post", post)
    with conn:
        db.put_post(conn, post)
        event = {"id": db.new_id("ev"), "userId": user["id"], "type": "postToChannel", "channelId": channel_id,
                 "context": {"screen": "community"}, "occurredAt": post["createdAt"]}
        if story_id is not None:
            event["storyId"] = story_id
        db.add_event(conn, event)
    stores.events_added(request, [event])
    return post


@router.post("/reports", status_code=201)
def create_report(request: Request, conn: Conn, user: Member, body: dict = Body(...)):
    allowed = {"kind", "storyId", "category", "sensitive", "text", "location"}
    extra = set(body) - allowed
    if extra:
        raise ApiError(422, "invalid", f"Unknown fields: {', '.join(sorted(extra))}")
    now = db.now()
    report = {**body, "id": db.new_id("report"), "reporterId": user["id"], "status": "sent",
              "createdAt": now, "updatedAt": now}
    request.app.state.contract.check("report.schema.json", report)
    if "storyId" in report and db.get_doc(conn, "stories", report["storyId"]) is None:
        raise not_found("Story")
    with conn:
        db.put_report(conn, report)
        db.add_event(conn, {"id": db.new_id("ev"), "userId": user["id"], "type": "report",
                            **({"storyId": report["storyId"]} if "storyId" in report else {}),
                            "detail": {"reportId": report["id"]}, "occurredAt": now})
        db.audit(conn, f"user:{user['id']}", "gather", f"New {report['kind']} report ({report['category']})",
                 story_id=report.get("storyId"), report_id=report["id"])
    return report


@router.get("/reports/mine")
def my_reports(conn: Conn, user: CurrentUser):
    return db.docs(conn, "SELECT doc FROM reports WHERE reporter_id = ? ORDER BY created_at DESC", (user["id"],))
