"""The backend implements every path in contract/openapi.yaml."""

import re

import yaml


def test_every_contract_path_is_served(app, contract):
    spec = yaml.safe_load((contract.dir / "openapi.yaml").read_text(encoding="utf-8"))
    served = {
        (method, re.sub(r"\{[^}]+\}", "{}", path))
        for path, ops in app.openapi()["paths"].items()
        for method in ops
    }
    missing = []
    for path, ops in spec["paths"].items():
        for method in ops:
            if method in ("get", "post", "put", "patch", "delete") and (method, re.sub(r"\{[^}]+\}", "{}", path)) not in served:
                missing.append(f"{method.upper()} {path}")
    assert not missing, missing


def test_errors_use_contract_shape(client):
    r = client.get("/v1/me")
    assert r.status_code == 401
    assert set(r.json()) == {"code", "message"}
    r = client.get("/v1/nope")
    assert r.status_code == 404
    assert set(r.json()) == {"code", "message"}
