"""Editor and admin endpoints, used by the admin web page (C4)."""

import math
from typing import Annotated

from fastapi import APIRouter, Body, Query, Request

from .. import db, domains, stores
from ..auth import Admin, Conn, Editor
from ..errors import ApiError, not_found

router = APIRouter(prefix="/v1/admin", tags=["admin"])

RISK_ORDER = {"red": 0, "amber": 1, "none": 2}
CATEGORIES = ("economy", "society", "politics", "shopping", "sport", "safety", "culture", "transport", "education",
              "housing", "health", "work", "environment", "technology", "world", "cityLife")
ACTIONS = ("approve", "reject", "sendBack", "keepAsLead")

NOTICES = {
    "reportPublished": (
        {"en": "Your report was published", "fi": "Ilmoituksesi julkaistiin", "fa": "گزارشت منتشر شد", "sv": "Din rapport publicerades"},
        {"en": "An editor checked your report and published it. Thanks for helping!",
         "fi": "Toimittaja tarkisti ilmoituksesi ja julkaisi sen. Kiitos avusta!",
         "fa": "ویراستار گزارشت را بررسی و منتشر کرد. ممنون که کمک کردی!",
         "sv": "En redaktör granskade och publicerade din rapport. Tack för hjälpen!"},
    ),
    "reportCorrected": (
        {"en": "The story you flagged was corrected", "fi": "Ilmoittamasi uutinen korjattiin",
         "fa": "خبری که گزارش دادی اصلاح شد", "sv": "Nyheten du anmälde har rättats"},
        {"en": "An editor checked your report and corrected the story. Thanks for helping!",
         "fi": "Toimittaja tarkisti ilmoituksesi ja korjasi uutisen. Kiitos avusta!",
         "fa": "ویراستار گزارشت را بررسی کرد و خبر را اصلاح کرد. ممنون که کمک کردی!",
         "sv": "En redaktör granskade din rapport och rättade nyheten. Tack för hjälpen!"},
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


def _set_report_status(report: dict, status: str, now: str, note: str | None = None) -> None:
    """Move a report on and record the step in its history (contract/processes/report-review.md)."""
    step = {"status": status, "at": now}
    if note:
        step["note"] = note
    report["status"] = status
    report["history"].append(step)
    report["updatedAt"] = now


def _get_story(conn, story_id: str) -> dict:
    story = db.get_doc(conn, "stories", story_id)
    if story is None:
        raise not_found("Story")
    return story


@router.get("/queue")
def queue(conn: Conn, user: Editor):
    """The review queue, limited to the editor's domain."""
    scope = domains.Scope(conn, user)
    items = []
    for s in db.docs(conn, "SELECT doc FROM stories WHERE status = 'inReview'"):
        if not scope.covers(s):
            continue
        items.append({"kind": "agentDraft", "id": s["id"], "risk": s["risk"], "createdAt": s["createdAt"],
                      "trail": _trail(conn, story_id=s["id"])})
    stories = {s["id"]: s for s in db.docs(conn, "SELECT doc FROM stories")}
    for r in db.docs(conn, "SELECT doc FROM reports WHERE status IN ('sent', 'inReview')"):
        if not scope.covers(r):
            continue
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
    scope = domains.Scope(conn, user)
    scope.check(_get_story(conn, story_id))
    if body.get("id") != story_id:
        raise ApiError(422, "invalid", "id in the body must match the path")
    body["updatedAt"] = db.now()
    request.app.state.contract.check("story.schema.json", body)
    scope.check(body)  # no moving a story out of your domain
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
    scope = domains.Scope(conn, user)
    scope.check(story)
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
        if (action == "approve" and report and not report["sensitive"]
                and report["status"] in ("sent", "inReview")):
            if report["status"] == "sent":
                _set_report_status(report, "inReview", now)
            report["resultStoryId"] = story_id
            _set_report_status(report, "published", now)
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


def _get_report(conn, report_id: str) -> dict:
    report = db.get_doc(conn, "reports", report_id)
    if report is None:
        raise not_found("Report")
    return report


@router.get("/reports/{report_id}")
def get_report(request: Request, report_id: str, conn: Conn, user: Editor):
    """The first editor to open a sent report moves it to inReview."""
    report = _get_report(conn, report_id)
    scope = domains.Scope(conn, user)
    scope.check(report)
    if report["status"] == "sent":
        _set_report_status(report, "inReview", db.now())
        request.app.state.contract.check("report.schema.json", report)
        with conn:
            db.put_report(conn, report)
            db.audit(conn, _actor(user), "review", "Opened for review", report_id=report_id)
    return report


@router.post("/reports/{report_id}/decision")
def decide_report(request: Request, report_id: str, conn: Conn, user: Editor, body: dict = Body(...)):
    action, note = _decision(body)
    report = _get_report(conn, report_id)
    scope = domains.Scope(conn, user)
    scope.check(report)
    if report["status"] != "inReview":
        raise ApiError(409, "notInReview", f"Only reports in review can be decided; this one is {report['status']}")
    c = request.app.state.contract
    now = db.now()
    story = None
    with conn:
        if action == "sendBack":
            # To the agent for more work; the report stays in review.
            status, notice = None, None
        elif action == "reject":
            status, notice = "rejected", "reportRejected"
        elif action == "keepAsLead" or report["sensitive"]:
            # A sensitive report is never published, even when approved.
            status, notice = "editorLead", "reportEditorLead"
        elif report["kind"] == "problem":
            # The editor fixed the story the reader flagged.
            report["resultStoryId"] = report["storyId"]
            status, notice = "edited", "reportCorrected"
        else:
            story = story_from_report(conn, report, user)
            c.check("story.schema.json", story)
            db.put_story(conn, story)
            db.audit(conn, _actor(user), "publish", "Published from community report",
                     story_id=story["id"], report_id=report_id)
            report["resultStoryId"] = story["id"]
            status, notice = "published", "reportPublished"
        if note:
            report["editorNote"] = note
        if status:
            _set_report_status(report, status, now, note)
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
    """The audit log; an editor with a domain sees only entries about stories and reports in it."""
    scope = domains.Scope(conn, user)
    if not scope.categories:
        rows = conn.execute("SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,))
        return [db.audit_entry(r) for r in rows]
    stories = {s["id"]: s for s in db.docs(conn, "SELECT doc FROM stories")}
    reports = {r["id"]: r for r in db.docs(conn, "SELECT doc FROM reports")}
    out = []
    for row in conn.execute("SELECT * FROM audit ORDER BY seq DESC"):
        story, report = stories.get(row["story_id"]), reports.get(row["report_id"])
        if report is not None or story is not None:
            allowed = scope.covers(report or story)
        else:
            allowed = not (row["story_id"] or row["report_id"])
        if allowed:
            out.append(db.audit_entry(row))
            if len(out) == limit:
                break
    return out


def _editor(conn, user_id: str) -> dict:
    row = conn.execute("SELECT * FROM users WHERE id = ? AND role IN ('editor', 'admin')", (user_id,)).fetchone()
    if row is None:
        raise not_found("Editor")
    return {**db.user_doc(row), "categories": domains.get(conn, user_id)}


@router.get("/editors")
def list_editors(conn: Conn, user: Admin):
    """Editors and admins with the categories they review (backend only, not in the contract)."""
    rows = conn.execute("SELECT id FROM users WHERE role IN ('editor', 'admin') ORDER BY id")
    return [_editor(conn, r["id"]) for r in rows]


@router.get("/editors/me")
def my_domains(conn: Conn, user: Editor):
    return _editor(conn, user["id"])


DOMAINS_EXAMPLE = {"categories": ["politics", "economy"]}


@router.put("/editors/{user_id}/domains")
def set_domains(request: Request, user_id: str, conn: Conn, user: Admin,
                body: dict | None = Body(None, examples=[DOMAINS_EXAMPLE])):
    """Set the categories an editor reviews. Send null or an empty list to let them see everything."""
    _editor(conn, user_id)
    body = body or {}
    if set(body) - {"categories"}:
        raise ApiError(422, "invalid", f"Unknown fields: {', '.join(sorted(set(body) - {'categories'}))}")
    categories = body.get("categories") or []
    if not isinstance(categories, list) or set(categories) - set(CATEGORIES):
        raise ApiError(422, "invalid", f"categories must be from: {', '.join(CATEGORIES)}")
    categories = list(dict.fromkeys(categories)) or None
    with conn:
        domains.put(conn, user_id, categories)
        db.audit(conn, _actor(user), "route",
                 f"Editor domain for {user_id}: {', '.join(categories) if categories else 'everything'}")
    return _editor(conn, user_id)


@router.post("/agent/run")
def run_agent(request: Request, conn: Conn, user: Editor):
    """One newsroom round now: the agent gathers news for readers' profiles; its stories join the queue."""
    from .. import newsroom  # here, not at the top: newsroom -> drafts -> this module

    state = request.app.state
    counts = newsroom.run(conn, state.contract, state.settings, state.graph, state.vectors)
    with conn:
        db.audit(conn, user["id"], "route", f"Ran the agent: {counts['queued']} drafts queued, "
                                             f"{counts['published']} published")
    return counts
