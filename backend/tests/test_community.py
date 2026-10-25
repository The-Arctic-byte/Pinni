import json

from pinni.config import BACKEND

MOCK = BACKEND.parent / "contract" / "mock"


def test_suggested_channels(client, login, anonymous, valid):
    headers = login("sara")
    suggestions = client.get("/v1/channels/suggested", headers=headers).json()
    valid("channel.schema.json#/$defs/Suggestion", suggestions)
    joined = {c["id"] for c in client.get("/v1/channels", headers=headers).json()}
    assert suggestions and not joined & {s["channelId"] for s in suggestions}
    assert [s["score"] for s in suggestions] == sorted((s["score"] for s in suggestions), reverse=True)
    # A channel in a language Sara does not read is not pushed to her.
    ids = [s["channelId"] for s in suggestions]
    assert "ukrainians-oulu" not in ids or ids[-1] == "ukrainians-oulu"

    # Cold start: no profile, no similar people -> the most popular channels.
    new, _ = anonymous()
    cold = client.get("/v1/channels/suggested", headers=new).json()
    valid("channel.schema.json#/$defs/Suggestion", cold)
    assert all(s["reason"]["en"] == "Popular in Oulu" for s in cold)
    counts = {c["id"]: c["memberCount"] for c in json.loads((MOCK / "channels.json").read_text(encoding="utf-8"))}
    assert [counts[s["channelId"]] for s in cold] == sorted((counts[s["channelId"]] for s in cold), reverse=True)


def test_joined_and_by_id(client, login, valid):
    headers = login("sara")
    joined = client.get("/v1/channels", headers=headers).json()
    valid("channel.schema.json", joined)
    # As in the app's mock: joinChannel events plus the channels the reader posted in.
    posts = json.loads((MOCK / "channel-posts.json").read_text(encoding="utf-8"))
    assert {c["id"] for c in joined} == {"persian-oulu"} | {p["channelId"] for p in posts if p["authorId"] == "u-sara"}
    some = client.get("/v1/channels", params={"ids": "student-sports,psoas-residents"}, headers=headers).json()
    assert [c["id"] for c in some] == ["student-sports", "psoas-residents"]
    every = client.get("/v1/channels", params={"all": "true"}, headers=headers).json()
    valid("channel.schema.json", every)
    assert len(every) == len(json.loads((MOCK / "channels.json").read_text(encoding="utf-8")))


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


def test_replies(client, login, valid):
    headers = login("sara")
    url = "/v1/channels/persian-oulu/posts"
    parent = client.post(url, json={"text": "Who knows a good dentist?"}, headers=headers).json()
    r = client.post(url, json={"text": "Try Oral.", "replyToId": parent["id"]}, headers=headers)
    assert r.status_code == 201
    reply = r.json()
    valid("channel.schema.json#/$defs/Post", reply)
    assert reply["replyToId"] == parent["id"]
    assert reply["id"] in [p["id"] for p in client.get(url, headers=headers).json()]
    # A reply needs text, stays one level deep, and stays in its channel.
    assert client.post(url, json={"storyId": "lidl-ideapark", "replyToId": parent["id"]}, headers=headers).status_code == 422
    assert client.post(url, json={"text": "x", "replyToId": reply["id"]}, headers=headers).status_code == 422
    assert client.post(url, json={"text": "x", "replyToId": "nope"}, headers=headers).status_code == 404
    # The author hears about replies from others, not about their own.
    assert not [n for n in client.get("/v1/notifications", headers=headers).json() if n["kind"] == "channelPost"]
    matti = login("matti")
    client.put("/v1/channels/persian-oulu/membership", headers=matti)
    assert client.post(url, json={"text": "Oral is good.", "replyToId": parent["id"]}, headers=matti).status_code == 201
    notes = [n for n in client.get("/v1/notifications", headers=headers).json() if n["kind"] == "channelPost"]
    valid("notification.schema.json", notes)
    assert len(notes) == 1 and notes[0]["channelId"] == "persian-oulu"


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
