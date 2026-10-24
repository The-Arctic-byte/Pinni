from pinni.seed import DEV_PASSWORD, dev_email


def test_anonymous_session(client, valid):
    r = client.post("/v1/auth/anonymous")
    assert r.status_code == 201
    session = r.json()
    valid("user.schema.json", session["user"])
    assert session["user"]["role"] == "reader"
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {session['token']}"})
    assert me.json() == session["user"]


def test_login(client, valid):
    r = client.post("/v1/auth/login", json={"email": dev_email("u-aino"), "password": DEV_PASSWORD})
    assert r.status_code == 200
    valid("user.schema.json", r.json()["user"])
    assert r.json()["user"]["role"] == "editor"


def test_wrong_password(client):
    r = client.post("/v1/auth/login", json={"email": dev_email("u-sara"), "password": "nope"})
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


def test_bad_token(client):
    assert client.get("/v1/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_login_keeps_anonymous_history(client, anonymous):
    headers, anon_id = anonymous()
    event = {"id": "ev-anon-1", "userId": anon_id, "type": "like", "storyId": "lidl-ideapark",
             "occurredAt": "2026-10-24T10:00:00+03:00"}
    assert client.post("/v1/events", json=[event], headers=headers).status_code == 202
    token = headers["Authorization"].split()[1]
    r = client.post("/v1/auth/login", json={"email": dev_email("u-matti"), "password": DEV_PASSWORD, "anonymousToken": token})
    assert r.status_code == 200
    matti = {"Authorization": f"Bearer {r.json()['token']}"}
    learned = client.get("/v1/profile/learned", headers=matti).json()
    assert any(c["category"] == "shopping" for c in learned["topCategories"])
    # The anonymous token no longer works.
    assert client.get("/v1/me", headers=headers).status_code == 401
    # Events the app queued before signing in still carry the anonymous id; they land on the account.
    late = {**event, "id": "ev-anon-2", "occurredAt": "2026-10-24T10:01:00Z"}
    r = client.post("/v1/events", json=[late], headers=matti)
    assert r.status_code == 202 and r.json()["accepted"] == 1
    # Someone else's id is still refused.
    other, other_id = anonymous()
    assert client.post("/v1/events", json=[{**late, "id": "ev-x", "userId": other_id}], headers=matti).status_code == 403
