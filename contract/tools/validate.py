# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "jsonschema[format-nongpl]>=4.23",
#   "openapi-spec-validator>=0.7",
#   "pyyaml>=6",
# ]
# ///
"""Validate the contract: schemas, mock data, cross-references and the OpenAPI file.

Run from the repo root:  uv run contract/tools/validate.py
"""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate as validate_openapi
from referencing import Registry, Resource

CONTRACT = Path(__file__).resolve().parent.parent
SCHEMAS = CONTRACT / "schemas"
MOCK = CONTRACT / "mock"

# mock file -> (schema file, JSON pointer inside it or "", is the file a list?)
MOCK_SCHEMAS = {
    "places.json": ("place.schema.json", "", True),
    "stories.json": ("story.schema.json", "", True),
    "users.json": ("user.schema.json", "", True),
    "profiles.json": ("profile.schema.json", "", True),
    "feed-sara.json": ("feed.schema.json", "", False),
    "feed-matti.json": ("feed.schema.json", "", False),
    "feed-new.json": ("feed.schema.json", "", False),
    "events.json": ("event.schema.json", "", True),
    "channels.json": ("channel.schema.json", "", True),
    "channel-suggestions-sara.json": ("channel.schema.json", "/$defs/Suggestion", True),
    "channel-posts.json": ("channel.schema.json", "/$defs/Post", True),
    "reports.json": ("report.schema.json", "", True),
    "notifications.json": ("notification.schema.json", "", True),
}

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_registry() -> tuple[Registry, dict]:
    schemas = {p.name: load(p) for p in sorted(SCHEMAS.glob("*.schema.json"))}
    registry = Registry().with_resources(
        (name, Resource.from_contents(s)) for name, s in schemas.items()
    )
    for name, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as e:  # noqa: BLE001
            fail(f"schemas/{name}: invalid schema: {e}")
        if schema.get("$id") != name:
            fail(f"schemas/{name}: $id must be '{name}'")
    return registry, schemas


def validate_mocks(registry: Registry) -> dict:
    data = {}
    unused = {p.name for p in MOCK.glob("*.json")} - MOCK_SCHEMAS.keys()
    for name in sorted(unused):
        fail(f"mock/{name}: no schema mapped in validate.py")
    for name, (schema_name, pointer, is_list) in MOCK_SCHEMAS.items():
        path = MOCK / name
        if not path.exists():
            fail(f"mock/{name}: missing")
            continue
        doc = load(path)
        data[name] = doc
        validator = Draft202012Validator(
            {"$ref": f"{schema_name}#{pointer}"},
            registry=registry,
            format_checker=FormatChecker(),
        )
        items = doc if is_list else [doc]
        if is_list and not isinstance(doc, list):
            fail(f"mock/{name}: expected a JSON array")
            continue
        for i, item in enumerate(items):
            for err in validator.iter_errors(item):
                where = "/".join(str(p) for p in err.absolute_path)
                label = f"[{i}]" if is_list else ""
                fail(f"mock/{name}{label} {where}: {err.message}")
    return data


def check_references(d: dict) -> None:
    """Rules the schemas cannot express: ids that must exist, and product rules."""
    places = {p["id"] for p in d.get("places.json", [])}
    stories = {s["id"]: s for s in d.get("stories.json", [])}
    users = {u["id"]: u for u in d.get("users.json", [])}
    profiles = {p["userId"]: p for p in d.get("profiles.json", [])}
    channels = {c["id"] for c in d.get("channels.json", [])}
    reports = {r["id"]: r for r in d.get("reports.json", [])}

    def need(kind: str, value, known, where: str) -> None:
        if value is not None and value not in known:
            fail(f"{where}: unknown {kind} '{value}'")

    for name in ("places.json", "stories.json", "users.json", "channels.json", "reports.json", "events.json"):
        ids = [x["id"] for x in d.get(name, [])]
        for dup in {i for i in ids if ids.count(i) > 1}:
            fail(f"mock/{name}: duplicate id '{dup}'")

    for p in d.get("places.json", []):
        need("place", p.get("parentId"), places, f"place {p['id']}.parentId")

    for s in stories.values():
        w = f"story {s['id']}"
        need("place", s["placeId"], places, f"{w}.placeId")
        if s["risk"] == "red" and s["status"] == "published":
            # A red story is only published after a human signed it; the schema already requires verification.
            if not s.get("verification"):
                fail(f"{w}: red-risk story published without verification")
        if s["origin"] == "community":
            need("report", s["community"]["reportId"], reports, f"{w}.community.reportId")
        if s["scale"] in ("area", "city") and "location" not in s:
            fail(f"{w}: area/city stories need a location")
        languages = {t["language"] for t in s["translations"]}
        if "en" not in languages:
            fail(f"{w}: English translation tier missing")
        if s["risk"] == "red" and s["status"] == "published":
            for t in s["translations"]:
                if t["tier"] == 3:
                    fail(f"{w}: red-risk story published with an unchecked (tier 3) {t['language']} translation")

    for u in d.get("profiles.json", []):
        w = f"profile {u['userId']}"
        need("user", u["userId"], users, f"{w}.userId")
        need("place", u.get("homePlaceId"), places, f"{w}.homePlaceId")
        for pid in u.get("followedPlaceIds", []):
            need("place", pid, places, f"{w}.followedPlaceIds")

    for name, doc in d.items():
        if not name.startswith("feed-"):
            continue
        w = f"mock/{name}"
        need("user", doc["userId"], users, f"{w}.userId")
        profile = profiles.get(doc["userId"])
        seen = set()
        for item in doc["items"]:
            sid = item["storyId"]
            need("story", sid, stories, f"{w} item")
            if sid in seen:
                fail(f"{w}: story '{sid}' listed twice")
            seen.add(sid)
            story = stories.get(sid)
            if story and story["status"] != "published":
                fail(f"{w}: '{sid}' is {story['status']}; feeds only contain published stories")
            if story and profile:
                hf = profile["hardFilters"]
                if story["category"] in hf["categories"] or set(story.get("tags", [])) & set(hf["tags"]):
                    fail(f"{w}: '{sid}' breaks the reader's hard filters")
        rel = [i["relevance"] for i in doc["items"]]
        if rel != sorted(rel, reverse=True):
            fail(f"{w}: items must be sorted by relevance, highest first")

    for e in d.get("events.json", []):
        w = f"event {e['id']}"
        need("user", e["userId"], users, f"{w}.userId")
        need("story", e.get("storyId"), stories, f"{w}.storyId")
        need("channel", e.get("channelId"), channels, f"{w}.channelId")
        need("place", e.get("placeId"), places, f"{w}.placeId")

    for c in d.get("channels.json", []):
        need("place", c.get("placeId"), places, f"channel {c['id']}.placeId")
    for s in d.get("channel-suggestions-sara.json", []):
        need("channel", s["channelId"], channels, "channel suggestion")
    for p in d.get("channel-posts.json", []):
        need("channel", p["channelId"], channels, f"post {p['id']}.channelId")
        need("user", p["authorId"], users, f"post {p['id']}.authorId")
        need("story", p.get("storyId"), stories, f"post {p['id']}.storyId")
        author = users.get(p["authorId"])
        if author and author["role"] == "reader":
            fail(f"post {p['id']}: readers cannot post; author must be a member or above")

    for r in reports.values():
        w = f"report {r['id']}"
        need("user", r["reporterId"], users, f"{w}.reporterId")
        need("story", r.get("storyId"), stories, f"{w}.storyId")
        need("story", r.get("resultStoryId"), stories, f"{w}.resultStoryId")
        if r["sensitive"] and r["status"] in ("published", "edited") and not stories.get(r.get("resultStoryId"), {}).get("verification"):
            fail(f"{w}: sensitive report published without editor verification")

    for n in d.get("notifications.json", []):
        w = f"notification {n['id']}"
        need("user", n["userId"], users, f"{w}.userId")
        need("story", n.get("storyId"), stories, f"{w}.storyId")
        need("report", n.get("reportId"), reports, f"{w}.reportId")
        need("channel", n.get("channelId"), channels, f"{w}.channelId")


def check_openapi() -> None:
    path = CONTRACT / "openapi.yaml"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        validate_openapi(spec, base_uri=path.as_uri())
    except Exception as e:  # noqa: BLE001
        fail(f"openapi.yaml: {e}")


def main() -> int:
    registry, _ = build_registry()
    data = validate_mocks(registry)
    check_references(data)
    check_openapi()
    if errors:
        print(f"Contract invalid: {len(errors)} problem(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Contract OK: {len(MOCK_SCHEMAS)} mock files, {len(list(SCHEMAS.glob('*.schema.json')))} schemas, openapi.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
