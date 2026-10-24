import pytest
from fastapi.testclient import TestClient

from pinni.config import BACKEND, Settings
from pinni.main import create_app
from pinni.seed import DEV_PASSWORD, dev_email


@pytest.fixture
def app(tmp_path):
    settings = Settings(db_path=tmp_path / "test.db", contract_dir=BACKEND.parent / "contract",
                        seed_mock=True, dev_accounts=True)
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def contract(app):
    return app.state.contract


@pytest.fixture
def valid(contract):
    """valid(ref, doc_or_list) asserts the response matches the contract schema."""

    def check(ref: str, doc):
        for item in doc if isinstance(doc, list) else [doc]:
            problems = contract.errors(ref, item)
            assert not problems, problems

    return check


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def login(client):
    """login("sara") -> headers for that mock persona."""

    def do(user_id: str) -> dict:
        r = client.post("/v1/auth/login", json={"email": dev_email(f"u-{user_id}"), "password": DEV_PASSWORD})
        assert r.status_code == 200, r.text
        return auth_header(r.json()["token"])

    return do


@pytest.fixture
def anonymous(client):
    def do() -> tuple[dict, str]:
        r = client.post("/v1/auth/anonymous")
        assert r.status_code == 201
        body = r.json()
        return auth_header(body["token"]), body["user"]["id"]

    return do
