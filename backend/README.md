# Pinni backend (Track C)

FastAPI service that implements [`contract/openapi.yaml`](../contract/openapi.yaml).
The contract's JSON Schemas are used directly to validate request bodies, and the tests check every
response against them, so the backend cannot drift from what the app expects.

Status: **C1 + C2 + C4** — every contract endpoint works, with the three databases from the plan,
and the editor page is served at **http://localhost:8000/admin** (source in [`admin/`](../admin)).

- **SQLite**: source of truth. All contract objects, and events (append-only).
- **Knowledge graph** (Neo4j): users, stories, topics, tags, places, channels, sources and who
  interacted with what. Answers "similar people" for channel suggestions and the feed.
- **Vector store** (Chroma): published stories and their embeddings, for content-based ranking.

The graph and the vector store are derived from SQLite and rebuilt from it when empty, so either
can be wiped and rebuilt with a restart. Without Neo4j configured the same graph runs in memory;
without Ollama a hashing embedder stands in for the embedding model. Development and tests need
nothing but Python.

The feed is ranked by the Track B recommender ([`agent/`](../agent)), fed from these stores.

Next: member sign-up (C3), user and source management on the admin page (needs new contract endpoints), APNs (C5), Ollama embeddings once Track B picks the model (B1).

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
| `PINNI_ADMIN_DIR` | `admin/` | Editor page, served at `/admin` |
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
  recommender.py /v1/feed: Track B recommender over the backend's stores
  ranking.py     learned preferences and channel suggestions
  seed.py        contract/mock -> database
  routers/       auth, reader, community, admin
tests/           one file per router, plus contract coverage
```

## Editor page (C4)

Sign in at `/admin` as an editor or admin (`aino@pinni.test` / `pinni-dev` in development); readers and
members are turned away. The page shows the review queue (agent drafts, community reports, reader flags,
red risk first), each item with its agent trail, and lets the editor approve, reject, send back, keep a
report as a lead (with a note to the reporter) or edit a story as JSON. The audit log has its own tab.
It is plain HTML/JS with no build step and only calls the `/v1/admin/*` and `/v1/stories` endpoints.

## Rules the backend enforces

- Only published stories reach readers and members; editors see everything.
- Feeds are sorted by relevance, never break the reader's hard filters, and drop stories they marked "not for me" or rejected.
- Must-see items (red-risk safety, red-risk news from your home area, stories that affect your group) are never ranked away.
- Readers cannot join channels, post or report (403).
- A red-risk story cannot be published with a tier-3 (unchecked) translation (409).
- Events are append-only and uploads are idempotent by event id.
- Approving a community report creates a published story and notifies the reporter.

## Ranking

`/v1/feed` is ranked by `RecommendationEngine` from Track B (`agent/pinni_agent/recommender`), which
scores each story, decides must-see and writes the "why you see this" reasons. `pinni/recommender.py`
gives it the backend's data through small adapters (profile and events from SQLite, content
similarity from Chroma, what similar people liked from the knowledge graph) and keeps the parts that
follow the contract's place tree here: the `scale`/`placeId` filters and paging.

Channel suggestions blend what similar people follow (60%) with profile overlap (40%);
`similarMembers` is shown from 20 people up, as the contract requires.
