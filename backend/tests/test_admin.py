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
    item = next(i for i in client.get("/v1/feed?limit=100", headers=login("sara")).json()["items"] if i["storyId"] == "finns-party-cuts")
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


def test_editor_domains(client, login):
    admin, aino = login("admin"), login("aino")

    def queue_ids():
        return {i["id"] for i in client.get("/v1/admin/queue", headers=aino).json()}

    assert {"finns-party-cuts", "report-wrong-date"} <= queue_ids()  # no domain: everything
    assert client.put("/v1/admin/editors/u-aino/domains", json={"categories": ["work"]}, headers=aino).status_code == 403
    assert client.put("/v1/admin/editors/u-aino/domains", json={"categories": ["gossip"]}, headers=admin).status_code == 422
    r = client.put("/v1/admin/editors/u-aino/domains", json={"categories": ["work", "safety"]}, headers=admin)
    assert r.json()["categories"] == ["work", "safety"]
    assert client.get("/v1/admin/editors/me", headers=aino).json()["categories"] == ["work", "safety"]

    assert "finns-party-cuts" not in queue_ids() and "report-wrong-date" in queue_ids()
    assert client.post("/v1/admin/stories/finns-party-cuts/decision", json={"action": "reject"},
                       headers=aino).status_code == 403
    assert client.get("/v1/admin/reports/report-icy-path", headers=aino).status_code == 403  # transport
    assert all(e.get("storyId") != "finns-party-cuts" for e in client.get("/v1/admin/audit", headers=aino).json())
    # Admins always see everything.
    assert "finns-party-cuts" in {i["id"] for i in client.get("/v1/admin/queue", headers=admin).json()}

    client.put("/v1/admin/editors/u-aino/domains", json=None, headers=admin)
    assert client.get("/v1/admin/editors/me", headers=aino).json()["categories"] is None
    assert "finns-party-cuts" in queue_ids()


def test_dev_editors_have_domains(client, login):
    leo = {i["id"] for i in client.get("/v1/admin/queue", headers=login("leo")).json()}
    mira = {i["id"] for i in client.get("/v1/admin/queue", headers=login("mira")).json()}
    assert "finns-party-cuts" in leo and "finns-party-cuts" not in mira
    assert "report-wrong-date" in mira and "report-wrong-date" not in leo


def test_older_database_is_upgraded(app, client, login, valid):
    """A database seeded before editor desks and report history still works after an update."""
    from pinni import db
    from pinni.seed import ensure_dev_editors, upgrade_reports

    conn = db.connect(app.state.settings.db_path)
    with conn:
        conn.execute("DELETE FROM users WHERE id = 'u-mira'")
        old = db.get_doc(conn, "reports", "report-wrong-date")
        del old["history"]
        db.put_report(conn, old)
    ensure_dev_editors(conn)
    ensure_dev_editors(conn)  # idempotent
    upgrade_reports(conn)
    conn.close()

    report = client.get("/v1/admin/reports/report-wrong-date", headers=login("mira")).json()
    valid("report.schema.json", report)
    assert [h["status"] for h in report["history"]] == ["sent", "inReview"]


def test_send_to_agent_writes_a_story_for_the_editor(client, login, valid):
    """'Send to agent' on a news tip: the agent writes it up, it waits for the editor, and approving
    it publishes the report with that story. The agent publishes nothing itself."""
    matti, mira = login("matti"), login("mira")
    text = "Bus 4 stop at Linnanmaa is closed because of road works. The temporary stop is 200 m north."
    report_id = _send(client, matti, kind="newsTip", category="transport", text=text,
                      location={"coordinate": {"lat": 65.06, "lon": 25.47}, "radiusMeters": 300})
    client.get(f"/v1/admin/reports/{report_id}", headers=mira)
    r = client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "sendBack"}, headers=mira)
    assert r.status_code == 200 and r.json()["status"] == "inReview"

    queue = client.get("/v1/admin/queue", headers=mira).json()
    drafts = [i for i in queue if i["kind"] == "agentDraft"]
    stories = client.get("/v1/stories", params={"ids": ",".join(i["id"] for i in drafts)}, headers=mira).json()
    draft = next(s for s in stories if s.get("community", {}).get("reportId") == report_id)
    valid("story.schema.json", draft)
    assert draft["status"] == "inReview" and draft["origin"] == "community"
    assert draft["title"]["en"].startswith("Bus 4 stop at Linnanmaa is closed")
    assert draft["location"] == {"coordinate": {"lat": 65.06, "lon": 25.47}, "radiusMeters": 0}
    assert draft["sources"][0]["name"] == "Pinni community report" and "url" not in draft["sources"][0]
    # No one has read it yet: the agent does not get to say an editor did.
    assert {"language": "en", "tier": 3} in draft["translations"]
    trail = next(i for i in drafts if i["id"] == draft["id"])["trail"]
    assert trail[-1]["actor"] == "agent:supervisor"
    # Readers do not see it.
    assert draft["id"] not in {i["storyId"] for i in client.get("/v1/feed?limit=100", headers=matti).json()["items"]}

    # Sending it again rewrites the same draft instead of adding one.
    client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "sendBack"}, headers=mira)
    again = client.get("/v1/admin/queue", headers=mira).json()
    assert sum(i["kind"] == "agentDraft" for i in again) == len(drafts)

    r = client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "approve"}, headers=mira)
    assert r.status_code == 200
    report = r.json()
    assert report["status"] == "published" and report["resultStoryId"] == draft["id"]
    published = client.get(f"/v1/stories/{draft['id']}", headers=matti).json()
    assert published["status"] == "published" and published["verification"]["verifiedBy"] == "Mira (city desk)"
    assert {"language": "en", "tier": 1, "reviewedBy": "Mira (city desk)"} in published["translations"]
    notices = client.get("/v1/notifications", headers=matti).json()
    assert any(n["kind"] == "reportPublished" and n.get("storyId") == draft["id"] for n in notices)


def test_approving_the_agents_story_publishes_the_report(client, login):
    matti, mira = login("matti"), login("mira")
    report_id = _send(client, matti, kind="newsTip", category="cityLife", text="The Tuira sauna opens again on Monday.")
    client.get(f"/v1/admin/reports/{report_id}", headers=mira)
    client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "sendBack"}, headers=mira)
    draft = next(s for s in client.get("/v1/admin/agent/stories", headers=mira).json()
                 if s["id"].startswith("community"))
    r = client.post(f"/v1/admin/stories/{draft['id']}/decision", json={"action": "approve"}, headers=mira)
    assert r.status_code == 200
    report = client.get(f"/v1/reports/{report_id}", headers=matti).json()
    assert report["status"] == "published" and report["resultStoryId"] == draft["id"]


def test_rejecting_a_report_drops_the_agents_story(client, login):
    matti, mira = login("matti"), login("mira")
    report_id = _send(client, matti, kind="newsTip", category="cityLife", text="Street lights are out on Pohjantie.")
    client.get(f"/v1/admin/reports/{report_id}", headers=mira)
    client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "sendBack"}, headers=mira)
    client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "reject", "note": "Not news."}, headers=mira)
    queue = client.get("/v1/admin/queue", headers=mira).json()
    assert not any(i["id"] == report_id for i in queue)
    stories = client.get("/v1/admin/agent/stories", headers=mira).json()
    assert all(s["status"] == "rejected" for s in stories if s["id"].startswith("community"))


def test_sensitive_reports_are_not_given_to_the_agent(client, login):
    matti, mira = login("matti"), login("mira")
    report_id = _send(client, matti, kind="newsTip", category="safety", text="A man with a knife near the station.")
    client.get(f"/v1/admin/reports/{report_id}", headers=mira)
    r = client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "sendBack"}, headers=mira)
    assert r.status_code == 200 and r.json()["status"] == "inReview"
    assert not any(s["id"].startswith("community") for s in client.get("/v1/admin/agent/stories", headers=mira).json())


def test_send_back_rewrites_the_agents_story(client, login):
    matti, mira = login("matti"), login("mira")
    report_id = _send(client, matti, kind="newsTip", category="cityLife", text="The Tuira sauna opens again on Monday.")
    client.get(f"/v1/admin/reports/{report_id}", headers=mira)
    client.post(f"/v1/admin/reports/{report_id}/decision", json={"action": "sendBack"}, headers=mira)
    draft = next(s for s in client.get("/v1/admin/agent/stories", headers=mira).json() if s["id"].startswith("community"))
    r = client.post(f"/v1/admin/stories/{draft['id']}/decision", json={"action": "sendBack", "note": "Shorter."}, headers=mira)
    assert r.status_code == 200
    again = r.json()
    assert again["id"] == draft["id"] and again["status"] == "inReview"
    assert again["community"]["reportId"] == report_id
