def test_admin_needs_editor(client, login, anonymous):
    assert client.get("/v1/admin/queue", headers=login("sara")).status_code == 403
    headers, _ = anonymous()
    assert client.get("/v1/admin/audit", headers=headers).status_code == 403


def test_queue(client, login):
    queue = client.get("/v1/admin/queue", headers=login("aino")).json()
    kinds = {(i["kind"], i["id"]) for i in queue}
    assert ("agentDraft", "finns-party-cuts") in kinds
    assert ("readerFlag", "report-wrong-date") in kinds
    assert queue[0]["risk"] == "red"


def test_red_story_with_unchecked_translation_cannot_be_published(client, login):
    headers = login("aino")
    r = client.post("/v1/admin/stories/finns-party-cuts/decision", json={"action": "approve"}, headers=headers)
    assert r.status_code == 409

    story = client.get("/v1/stories/finns-party-cuts", headers=headers).json()
    story["translations"] = [t if t["language"] != "fa" else {**t, "tier": 1, "reviewedBy": "Aino K."} for t in story["translations"]]
    assert client.patch("/v1/admin/stories/finns-party-cuts", json=story, headers=headers).status_code == 200
    r = client.post("/v1/admin/stories/finns-party-cuts/decision", json={"action": "approve"}, headers=headers)
    assert r.status_code == 200
    published = r.json()
    assert published["status"] == "published" and published["verification"]["verifiedBy"] == "Aino K."
    # Sara (non-EU) now gets it as must-see.
    item = next(i for i in client.get("/v1/feed", headers=login("sara")).json()["items"] if i["storyId"] == "finns-party-cuts")
    assert item["mustSee"]


def _send(client, headers, **report):
    return client.post("/v1/reports", json=report, headers=headers).json()["id"]


def test_publish_report_notifies_reporter(client, login, valid):
    matti = login("matti")
    report_id = _send(client, matti, kind="newsTip", category="transport", text="Road works on Kiimingintie.",
                      location={"coordinate": {"lat": 65.13, "lon": 25.74}, "radiusMeters": 300})

    editor = login("aino")
    early = client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "approve"}, headers=editor)
    assert early.status_code == 409  # still sent: an editor has to open it first
    opened = client.get(f"/v1/admin/reports/{report_id}", headers=editor).json()
    assert opened["status"] == "inReview"
    r = client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "approve"}, headers=editor)
    assert r.status_code == 200
    report = r.json()
    valid("report.schema.json", report)
    assert report["status"] == "published"
    assert [h["status"] for h in report["history"]] == ["sent", "inReview", "published"]
    story = client.get(f"/v1/stories/{report['resultStoryId']}", headers=matti).json()
    valid("story.schema.json", story)
    assert story["placeId"] == "kiiminki" and story["origin"] == "community"

    notes = client.get("/v1/notifications", headers=matti).json()
    assert notes[0]["kind"] == "reportPublished" and notes[0]["reportId"] == report_id
    assert client.get(f"/v1/reports/{report_id}", headers=matti).json()["status"] == "published"
    again = client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "reject"}, headers=editor)
    assert again.status_code == 409


def test_sensitive_report_is_never_published(client, login, valid):
    matti = login("matti")
    report_id = _send(client, matti, kind="newsTip", category="safety", text="Police cars near the school.")
    editor = login("aino")
    client.get(f"/v1/admin/reports/{report_id}", headers=editor)
    report = client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "approve"}, headers=editor).json()
    valid("report.schema.json", report)
    assert report["status"] == "editorLead" and "resultStoryId" not in report
    assert client.get("/v1/notifications", headers=matti).json()[0]["kind"] == "reportEditorLead"


def test_problem_report_marks_story_corrected(client, login, valid):
    matti = login("matti")
    report_id = _send(client, matti, kind="problem", storyId="orpo-kyiv", category="politics", text="Wrong date.")
    editor = login("aino")
    client.get(f"/v1/admin/reports/{report_id}", headers=editor)
    report = client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "approve"}, headers=editor).json()
    valid("report.schema.json", report)
    assert report["status"] == "edited" and report["resultStoryId"] == "orpo-kyiv"
    assert client.get("/v1/notifications", headers=matti).json()[0]["kind"] == "reportCorrected"


def test_keep_as_lead_and_audit(client, login):
    editor = login("aino")
    r = client.post("/v1/admin/reports/report-wrong-date/decision",
                    json={"action": "keepAsLead", "note": "Checking with the city."}, headers=editor)
    report = r.json()
    assert report["status"] == "editorLead" and report["editorNote"] == "Checking with the city."
    assert report["history"][-1] == {"status": "editorLead", "at": report["updatedAt"], "note": "Checking with the city."}
    audit = client.get("/v1/admin/audit", params={"limit": 5}, headers=editor).json()
    assert audit[0]["reportId"] == "report-wrong-date" and audit[0]["actor"] == "user:u-aino"
    bad = client.post("/v1/admin/stories/orpo-kyiv/decision", json={"action": "keepAsLead"}, headers=editor)
    assert bad.status_code == 422


def test_get_report(client, login, valid):
    editor = login("aino")
    report = client.get("/v1/admin/reports/report-sirens", headers=editor).json()
    valid("report.schema.json", report)
    assert report["sensitive"]
    assert client.get("/v1/admin/reports/missing", headers=editor).status_code == 404
    assert client.get("/v1/admin/reports/report-sirens", headers=login("sara")).status_code == 403


def test_admin_page_is_served(client):
    r = client.get("/admin/")
    assert r.status_code == 200 and "Pinni editor" in r.text
    assert client.get("/admin/app.js").status_code == 200
