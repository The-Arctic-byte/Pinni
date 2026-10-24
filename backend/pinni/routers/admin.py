"""Editor and admin endpoints, used by the admin web page (C4)."""

import math
from typing import Annotated

from fastapi import APIRouter, Body, Query, Request

from .. import db, stores
from ..auth import Conn, Editor
from ..errors import ApiError, not_found

router = APIRouter(prefix="/v1/admin", tags=["admin"])

RISK_ORDER = {"red": 0, "amber": 1, "none": 2}
ACTIONS = ("approve", "reject", "sendBack", "keepAsLead")

NOTICES = {
    "reportPublished": (
        {"en": "Your report was published", "fi": "Ilmoituksesi julkaistiin", "fa": "گزارشت منتشر شد", "sv": "Din rapport publicerades"},
        {"en": "An editor checked your report and published it. Thanks for helping!",
         "fi": "Toimittaja tarkisti ilmoituksesi ja julkaisi sen. Kiitos avusta!",
         "fa": "ویراستار گزارشت را بررسی و منتشر کرد. ممنون که کمک کردی!",
         "sv": "En redaktör granskade och publicerade din rapport. Tack för hjälpen!"},
    ),
    "reportRejected": (
        {"en": "Your report was not published", "fi": "Ilmoitustasi ei julkaistu", "fa": "گزارشت منتشر نشد", "sv": "Din rapport publicerades inte"},
        {"en": "An editor reviewed your report and decided not to publish it.",
         "fi": "Toimittaja kävi ilmoituksesi läpi eikä julkaissut sitä.",
         "fa": "ویراستار گزارشت را بررسی کرد و تصمیم گرفت منتشرش نکند.",
         "sv": "En redaktör granskade din rapport och valde att inte publicera den."},
    ),
    "reportEditorLead": (
        {"en": "Your report went to the editor", "fi": "Ilmoituksesi meni toimittajalle", "fa": "گزارشت پیش ویراستار رفت", "sv": "Din rapport gick till redaktören"},
        {"en": "Your report is kept as an editor lead and will be checked before anything is written.",
         "fi": "Ilmoituksesi jää toimittajan vihjeeksi, ja se tarkistetaan ennen kuin mitään kirjoitetaan.",
         "fa": "گزارشت به‌عنوان سرنخ پیش ویراستار ماند و قبل از نوشتن هر خبری بررسی می‌شود.",
         "sv": "Din rapport sparas som ett tips och kontrolleras innan något skrivs."},
    ),
}


def _actor(user: dict) -> str:
    return f"user:{user['id']}"


def _decision(body: dict) -> tuple[str, str | None]:
    action, note = body.get("action"), body.get("note")
    if action not in ACTIONS:
        raise ApiError(422, "invalid", f"action must be one of {', '.join(ACTIONS)}")
    if note is not None and not isinstance(note, str):
        raise ApiError(422, "invalid", "note must be a string")
    return action, note


def publish_problems(story: dict) -> list[str]:
    """Product rules for a published story that the schema cannot express."""
    problems = []
    if story["risk"] == "red":
        unchecked = [t["language"] for t in story["translations"] if t["tier"] == 3]
        if unchecked:
            problems.append(f"red-risk story has unchecked (tier 3) translations: {', '.join(unchecked)}")
    if not any(t["language"] == "en" for t in story["translations"]):
        problems.append("English translation tier missing")
    if story["scale"] in ("area", "city") and "location" not in story:
        problems.append("area/city stories need a location")
    return problems


def _notify(conn, user_id: str, kind: str, report: dict, story_id: str | None = None, note: str | None = None) -> None:
    title, body = NOTICES[kind]
    body = dict(body)
    if note:
        body = {lang: f"{text} {note}" for lang, text in body.items()}
    n = {"id": db.new_id("notif"), "userId": user_id, "kind": kind, "title": title, "body": body,
         "reportId": report["id"], "createdAt": db.now()}
    if story_id:
        n["storyId"] = story_id
    db.put_notification(conn, n)


def _get_story(conn, story_id: str) -> dict:
    story = db.get_doc(conn, "stories", story_id)
    if story is None:
        raise not_found("Story")
    return story


@router.get("/queue")
def queue(conn: Conn, user: Editor):
    items = []
    for s in db.docs(conn, "SELECT doc FROM stories WHERE status = 'inReview'"):
        items.append({"kind": "agentDraft", "id": s["id"], "risk": s["risk"], "createdAt": s["createdAt"],
                      "trail": _trail(conn, story_id=s["id"])})
    stories = {s["id"]: s for s in db.docs(conn, "SELECT doc FROM stories")}
    for r in db.docs(conn, "SELECT doc FROM reports WHERE status IN ('sent', 'inReview')"):
        if r["kind"] == "problem":
            risk = stories.get(r.get("storyId"), {}).get("risk", "none")
            kind = "readerFlag"
        else:
            risk = "red" if r["sensitive"] else "none"
            kind = "communityReport"
        items.append({"kind": kind, "id": r["id"], "risk": risk, "createdAt": r["createdAt"],
                      "trail": _trail(conn, report_id=r["id"])})
    items.sort(key=lambda i: (RISK_ORDER[i["risk"]], i["createdAt"]))
    return items


def _trail(conn, story_id: str | None = None, report_id: str | None = None) -> list[dict]:
    column, value = ("story_id", story_id) if story_id else ("report_id", report_id)
    rows = conn.execute(f"SELECT * FROM audit WHERE {column} = ? ORDER BY seq", (value,))
    return [db.audit_entry(r) for r in rows]


@router.patch("/stories/{story_id}")
def edit_story(request: Request, story_id: str, conn: Conn, user: Editor, body: dict = Body(...)):
    _get_story(conn, story_id)
    if body.get("id") != story_id:
        raise ApiError(422, "invalid", "id in the body must match the path")
    body["updatedAt"] = db.now()
    request.app.state.contract.check("story.schema.json", body)
    if body["status"] == "published":
        problems = publish_problems(body)
        if problems:
            raise ApiError(409, "notPublishable", "; ".join(problems))
    with conn:
        db.put_story(conn, body)
        db.audit(conn, _actor(user), "review", "Story edited", story_id=story_id)
    stores.story_changed(request, body)
    return body


@router.post("/stories/{story_id}/decision")
def decide_story(request: Request, story_id: str, conn: Conn, user: Editor, body: dict = Body(...)):
    action, note = _decision(body)
    story = _get_story(conn, story_id)
    now = db.now()
    if action == "keepAsLead":
        raise ApiError(422, "invalid", "keepAsLead only applies to reports")
    if action == "approve":
        problems = publish_problems(story)
        if problems:
            raise ApiError(409, "notPublishable", "; ".join(problems))
        story["status"] = "published"
        story["verification"] = {"verifiedBy": user.get("displayName", user["id"]), "verifiedAt": now}
        story.setdefault("publishedAt", now)
    elif action == "reject":
        story["status"] = "rejected"
    else:  # sendBack: back to the agent
        story["status"] = "draft"
    story["updatedAt"] = now
    request.app.state.contract.check("story.schema.json", story)
    with conn:
        db.put_story(conn, story)
        step = {"approve": "publish", "reject": "review", "sendBack": "route"}[action]
        db.audit(conn, _actor(user), step, f"{action}" + (f": {note}" if note else ""), story_id=story_id)
        report_id = story.get("community", {}).get("reportId")
        report = db.get_doc(conn, "reports", report_id) if report_id else None
        if action == "approve" and report and report["status"] not in ("published", "edited"):
            report.update(status="published", resultStoryId=story_id, updatedAt=now)
            db.put_report(conn, report)
            _notify(conn, report["reporterId"], "reportPublished", report, story_id)
    stores.story_changed(request, story)
    return story


def _nearest_place(conn, location: dict | None) -> dict:
    places = db.docs(conn, "SELECT doc FROM places")
    local = [p for p in places if p["kind"] in ("area", "city") and "center" in p]
    if not location or not local:
        return next((p for p in places if p["id"] == "oulu"), local[0] if local else places[0])
    c = location["coordinate"]

    def distance(p):
        dlat = p["center"]["lat"] - c["lat"]
        dlon = (p["center"]["lon"] - c["lon"]) * math.cos(math.radians(c["lat"]))
        return dlat * dlat + dlon * dlon

    return min(local, key=distance)


def story_from_report(conn, report: dict, editor: dict) -> dict:
    """A minimal published story from a news tip. Editors can refine it afterwards with PATCH;
    once the agents exist (Track B) they write the explanation sections."""
    now = db.now()
    place = _nearest_place(conn, report.get("location"))
    location = report.get("location") or {"coordinate": place["center"], "radiusMeters": 1000}
    text = report["text"].strip()
    title = text if len(text) <= 90 else text[:87].rstrip() + "…"
    label = " ".join(text.split()[:3])
    editor_name = editor.get("displayName", editor["id"])
    return {
        "id": db.new_id("community"),
        "status": "published",
        "origin": "community",
        "scale": "area" if place["kind"] == "area" else "city",
        "placeId": place["id"],
        "location": location,
        "category": report["category"],
        "needs": ["community"],
        "risk": "red" if report["sensitive"] else "none",
        "isOpinion": False,
        "importance": 0.35,
        "label": {"en": label},
        "title": {"en": title},
        "explanation": {"forYou": {"en": text}},
        "sources": [{"name": "Pinni community report", "publishedAt": now}],
        "translations": [{"language": "en", "tier": 1, "reviewedBy": editor_name}],
        "verification": {"verifiedBy": editor_name, "verifiedAt": now},
        "community": {"reportId": report["id"], "confirmations": 0},
        "createdAt": now,
        "updatedAt": now,
        "publishedAt": now,
    }


@router.post("/reports/{report_id}/decision")
def decide_report(request: Request, report_id: str, conn: Conn, user: Editor, body: dict = Body(...)):
    action, note = _decision(body)
    report = db.get_doc(conn, "reports", report_id)
    if report is None:
        raise not_found("Report")
    if report["status"] in ("published", "edited", "rejected"):
        raise ApiError(409, "alreadyDecided", f"Report is already {report['status']}")
    c = request.app.state.contract
    now = db.now()
    story = None
    with conn:
        if action == "approve":
            if report["kind"] == "problem":
                # The editor fixed the story the reader flagged.
                report.update(status="edited", resultStoryId=report["storyId"])
            else:
                story = story_from_report(conn, report, user)
                c.check("story.schema.json", story)
                db.put_story(conn, story)
                db.audit(conn, _actor(user), "publish", "Published from community report",
                         story_id=story["id"], report_id=report_id)
                report.update(status="published", resultStoryId=story["id"])
            notice = "reportPublished"
        elif action == "reject":
            report["status"] = "rejected"
            notice = "reportRejected"
        elif action == "keepAsLead":
            report["status"] = "editorLead"
            notice = "reportEditorLead"
        else:  # sendBack: to the agent for more work
            report["status"] = "inReview"
            notice = None
        if note:
            report["editorNote"] = note
        report["updatedAt"] = now
        c.check("report.schema.json", report)
        db.put_report(conn, report)
        db.audit(conn, _actor(user), "review", f"{action}" + (f": {note}" if note else ""), report_id=report_id)
        if notice:
            _notify(conn, report["reporterId"], notice, report, report.get("resultStoryId"), note)
    if story:
        stores.story_changed(request, story)
    return report


@router.get("/audit")
def get_audit(conn: Conn, user: Editor, limit: Annotated[int, Query(ge=1, le=500)] = 100):
    rows = conn.execute("SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,))
    return [db.audit_entry(r) for r in rows]
