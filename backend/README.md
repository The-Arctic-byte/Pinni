# Pinni backend (Track C)

FastAPI service that implements [`contract/openapi.yaml`](../contract/openapi.yaml).
The contract's JSON Schemas are used directly to validate request bodies, and the tests check every
response against them, so the backend cannot drift from what the app expects.

Status: **C1** — every contract endpoint works on SQLite, seeded from `contract/mock/`.
Neo4j, Chroma and the real recommender (C2, Track B), the admin web page (C4) and APNs (C5) come next.

## Run

```bash
cd backend
uv sync
uv run uvicorn pinni.main:app --reload       # http://localhost:8000/docs
uv run pytest                                # tests
```

Or with Docker, from the repo root:

```bash
docker compose -f backend/compose.yaml up --build
```

On first start the database (`backend/data/pinni.db`) is created and filled from `contract/mock/`.
Delete the file to start over.

## Sign in (development)

- Reader: `POST /v1/auth/anonymous` returns a token. No account needed.
- Mock personas: `POST /v1/auth/login` with `<name>@pinni.test` / `pinni-dev`:
  `sara` and `matti` (members), `aino` (editor), `admin` (admin).
  Pass `anonymousToken` to keep the reader's history.

Send the token as `Authorization: Bearer <token>`.
Turn the dev accounts off with `PINNI_DEV_ACCOUNTS=false` anywhere outside development.

## Settings

| Variable | Default | |
|---|---|---|
| `PINNI_DB_PATH` | `backend/data/pinni.db` | SQLite file |
| `PINNI_CONTRACT_DIR` | `contract/` | Schemas and mock data |
| `PINNI_SEED_MOCK` | `true` | Seed an empty database from `contract/mock/` |
| `PINNI_DEV_ACCOUNTS` | `true` | Give the mock personas the dev password |

## Layout

```text
pinni/
  main.py        app factory, startup (create tables, seed)
  contract.py    loads contract/schemas, validates documents
  db.py          SQLite tables; contract objects stored as JSON documents
  auth.py        tokens (only the hash is stored), scrypt passwords, role checks
  ranking.py     baseline feed ranking and channel suggestions (replaced by B4)
  seed.py        contract/mock -> database
  routers/       auth, reader, community, admin
tests/           one file per router, plus contract coverage
```

## Rules the backend enforces

- Only published stories reach readers and members; editors see everything.
- Feeds are sorted by relevance, never break the reader's hard filters, and drop stories they marked "not for me" or rejected.
- Must-see items (safety in your area or city, stories that affect your group) are never ranked away.
- Readers cannot join channels, post or report (403).
- A red-risk story cannot be published with a tier-3 (unchecked) translation (409).
- Events are append-only and uploads are idempotent by event id.
- Approving a community report creates a published story and notifies the reporter.

## Ranking (temporary)

`relevance = (1 − p) · importance + p · personal`, where `p` grows with the reader's events (full at 30)
and starts at 0.5 when the reader filled in a profile. `personal` mixes stated and learned category weights,
place (home area, followed places, home city) and wanted-news tags. This is a placeholder until the recommender
from Track B (B4) takes over behind the same `/v1/feed` endpoint.
