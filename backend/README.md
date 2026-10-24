# Pinni backend (Track C)

FastAPI service that implements [`contract/openapi.yaml`](../contract/openapi.yaml).
The contract's JSON Schemas are used directly to validate request bodies, and the tests check every
response against them, so the backend cannot drift from what the app expects.

Status: **C1 + C2** — every contract endpoint works, with the three databases from the plan:

- **SQLite**: source of truth. All contract objects, and events (append-only).
- **Knowledge graph** (Neo4j): users, stories, topics, tags, places, channels, sources and who
  interacted with what. Answers "similar people" for channel suggestions and the feed.
- **Vector store** (Chroma): published stories and their embeddings, for content-based ranking.

The graph and the vector store are derived from SQLite and rebuilt from it when empty, so either
can be wiped and rebuilt with a restart. Without Neo4j configured the same graph runs in memory;
without Ollama a hashing embedder stands in for the embedding model. Development and tests need
nothing but Python.

Next: the admin web page (C4), APNs (C5), Ollama embeddings once Track B picks the model (B1),
and the real recommender (B4) behind the same `/v1/feed`.

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
Delete `backend/data/` to start over. The compose file also starts Neo4j (browser on http://localhost:7474).

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
| `PINNI_NEO4J_URI` | empty | e.g. `bolt://localhost:7687`. Empty = in-memory graph |
| `PINNI_NEO4J_USER` / `PINNI_NEO4J_PASSWORD` | `neo4j` / empty | |
| `PINNI_CHROMA` | `backend/data/chroma` | Directory (embedded), `http(s)://host:port` (server) or `memory` |
| `PINNI_OLLAMA_URL` | empty | e.g. `http://localhost:11434`. Empty = hashing embedder |
| `PINNI_EMBED_MODEL` | `bge-m3` | Ollama embedding model (multilingual) |

Changing the embedding model empties the vector index; it is rebuilt on the next start.

Run the tests against a real Neo4j (CI does this too):

```bash
PINNI_TEST_NEO4J_URI=bolt://localhost:7687 PINNI_TEST_NEO4J_PASSWORD=... uv run pytest
```

## Layout

```text
pinni/
  main.py        app factory, startup (create tables, seed)
  contract.py    loads contract/schemas, validates documents
  db.py          SQLite tables; contract objects stored as JSON documents
  graph.py       knowledge graph: Neo4j or in-memory, rebuild from SQLite, similar people
  vectors.py     Chroma store and embedders (Ollama or hashing)
  stores.py      keeps graph and vectors in step with SQLite writes
  auth.py        tokens (only the hash is stored), scrypt passwords, role checks
  ranking.py     feed ranking and channel suggestions (until B4)
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
and starts at 0.5 when the reader filled in a profile. `personal` mixes:

| Signal | Weight | From |
|---|---|---|
| category | 0.35 | stated weights averaged with learned ones |
| place | 0.30 | home area, followed places, home city |
| tag | 0.10 | wanted news, interests, learned tags |
| content | 0.15 | vector similarity between the profile and the story |
| collaborative | 0.10 | share of similar people (graph) who liked the story |

A signal with no data yet (no similar people, empty profile) is left out and the rest are re-weighted.
Channel suggestions blend what similar people follow (60%) with profile overlap (40%);
`similarMembers` is shown from 20 people up, as the contract requires.
This stays until the recommender from Track B (B4) takes over behind the same endpoints.
