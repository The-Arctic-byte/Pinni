def test_suggested_channels(client, login, valid):
    suggestions = client.get("/v1/channels/suggested", headers=login("sara")).json()
    valid("channel.schema.json#/$defs/Suggestion", suggestions)
    ids = [s["channelId"] for s in suggestions]
    assert "persian-oulu" not in ids  # already joined
    assert ids[0] == "psoas-residents"


def test_joined_and_by_id(client, login, valid):
    headers = login("sara")
    joined = client.get("/v1/channels", headers=headers).json()
    valid("channel.schema.json", joined)
    assert [c["id"] for c in joined] == ["persian-oulu"]
    some = client.get("/v1/channels", params={"ids": "student-sports,psoas-residents"}, headers=headers).json()
    assert [c["id"] for c in some] == ["student-sports", "psoas-residents"]


def test_membership(client, login, anonymous):
    reader, _ = anonymous()
    assert client.put("/v1/channels/student-sports/membership", headers=reader).status_code == 403

    headers = login("matti")
    before = client.get("/v1/channels", params={"ids": "student-sports"}, headers=headers).json()[0]["memberCount"]
    assert client.put("/v1/channels/student-sports/membership", headers=headers).status_code == 204
    assert client.put("/v1/channels/student-sports/membership", headers=headers).status_code == 204  # idempotent
    after = client.get("/v1/channels", params={"ids": "student-sports"}, headers=headers).json()[0]["memberCount"]
    assert after == before + 1
    assert client.delete("/v1/channels/student-sports/membership", headers=headers).status_code == 204
    assert client.put("/v1/channels/missing/membership", headers=headers).status_code == 404


def test_posts(client, login, anonymous, valid):
    headers = login("sara")
    posts = client.get("/v1/channels/persian-oulu/posts", headers=headers).json()
    valid("channel.schema.json#/$defs/Post", posts)
    r = client.post("/v1/channels/persian-oulu/posts", json={"storyId": "lidl-ideapark", "text": "New Lidl!"}, headers=headers)
    assert r.status_code == 201
    valid("channel.schema.json#/$defs/Post", r.json())
    assert client.post("/v1/channels/persian-oulu/posts", json={}, headers=headers).status_code == 422
    reader, _ = anonymous()
    assert client.post("/v1/channels/persian-oulu/posts", json={"text": "hi"}, headers=reader).status_code == 403


def test_reports(client, login, anonymous, valid):
    headers = login("matti")
    tip = {"kind": "newsTip", "category": "transport", "text": "Bus 20 is late every morning.",
           "location": {"coordinate": {"lat": 65.06, "lon": 25.47}, "radiusMeters": 300}}
    r = client.post("/v1/reports", json=tip, headers=headers)
    assert r.status_code == 201
    report = r.json()
    valid("report.schema.json", report)
    assert report["status"] == "sent" and report["history"][0]["status"] == "sent" and not report["sensitive"]
    mine = client.get("/v1/reports/mine", headers=headers).json()
    valid("report.schema.json", mine)
    assert report["id"] in {m["id"] for m in mine}
    assert client.get(f"/v1/reports/{report['id']}", headers=headers).json() == report
    assert client.get(f"/v1/reports/{report['id']}", headers=login("sara")).status_code == 404

    problem = {"kind": "problem", "category": "work", "text": "Wrong date?"}
    assert client.post("/v1/reports", json=problem, headers=headers).status_code == 422  # needs storyId
    reader, _ = anonymous()
    assert client.post("/v1/reports", json=tip, headers=reader).status_code == 403


def test_report_rules(client, login):
    headers = login("matti")
    base = {"kind": "newsTip", "category": "transport", "text": "Road works."}
    area = {"coordinate": {"lat": 65.06, "lon": 25.47}, "radiusMeters": 300}
    # The app does not send sensitivity; the backend sets it.
    assert client.post("/v1/reports", json={**base, "sensitive": False}, headers=headers).status_code == 422
    assert client.post("/v1/reports", json={**base, "location": {**area, "radiusMeters": 100}},
                       headers=headers).status_code == 422
    problem = {"kind": "problem", "storyId": "orpo-kyiv", "category": "politics", "text": "Wrong name."}
    assert client.post("/v1/reports", json={**problem, "location": area}, headers=headers).status_code == 422
    safety = client.post("/v1/reports", json={**base, "category": "safety"}, headers=headers).json()
    assert safety["sensitive"]
