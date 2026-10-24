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
| `PINNI_SEED_CONTENT` | `true` | Also seed the mock stories, reports, posts, notifications and events. Off: only places, channels and users; the news is what the agent publishes |
| `PINNI_DEV_ACCOUNTS` | `true` | Give the mock personas the dev password |
| `PINNI_NEO4J_URI` | empty | e.g. `bolt://localhost:7687`. Empty = in-memory graph |
| `PINNI_NEO4J_USER` / `PINNI_NEO4J_PASSWORD` | `neo4j` / empty | |
| `PINNI_CHROMA` | `backend/data/chroma` | Directory (embedded), `http(s)://host:port` (server) or `memory` |
| `PINNI_OLLAMA_URL` | empty | e.g. `http://localhost:11434`. Empty = hashing embedder |
| `PINNI_EMBED_MODEL` | `bge-m3` | Ollama embedding model (multilingual) |
| `PINNI_AGENT_EVERY_MINUTES` | `30` | Run the agent at startup and then every N minutes. 0 = only from the editor page |
| `PINNI_AGENT_LLM` | `false` | Let the agent use Ollama (`PINNI_OLLAMA_URL`, its `PINNI_LLM_MODEL`); otherwise its offline heuristics |

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
  domains.py     editor desks (categories an editor reviews)
  drafts.py      intake for Track B supervisor stories -> editor queue (not scheduled yet)
  seed.py        contract/mock -> database
  routers/       auth, reader, community, admin
tests/           one file per router, plus contract coverage
```

## Editor page (C4)

Sign in at `/admin` as an editor or admin (`aino@pinni.test` / `pinni-dev` in development); readers and
members are turned away. The page shows the review queue (agent drafts, community reports, reader flags,
red risk first), each item with its agent trail, and lets the editor approve, reject, send back, keep a
report as a lead (with a note to the reporter) or edit a story as JSON. The audit log has its own tab.
Each editor works a desk: the categories they review. The queue, decisions and audit log are limited
to those categories (403 outside them); an editor with no categories and every admin see everything.
Admins set desks with `PUT /v1/admin/editors/{id}/domains` (`{"categories": [...]}`) and list them with
`GET /v1/admin/editors`; this is backend only, not part of the contract. Development accounts
`leo@pinni.test` (politics, economy, society, world) and `mira@pinni.test` (safety, transport, city life,
housing, work) show it; `aino@pinni.test` sees everything.
It is plain HTML/JS with no build step and only calls the `/v1/admin/*` and `/v1/stories` endpoints.

## Rules the backend enforces

- Only published stories reach readers and members; editors see everything.
- Feeds are sorted by relevance, never break the reader's hard filters, and drop stories they marked "not for me" or rejected.
- Must-see items (red-risk safety, red-risk news from your home area, stories that affect your group) are never ranked away.
- Readers cannot join channels, post or report (403).
- A red-risk story cannot be published with a tier-3 (unchecked) translation (409).
- Events are append-only and uploads are idempotent by event id.
- Every story on the map is a pin: a story's `radiusMeters` is stored as 0 (`db.as_point`), also for
  mock stories and stories made from reports. Reports keep their area (at least 300 m).
- Reports follow `contract/processes/report-review.md`: the backend sets `sensitive` (always for safety),
  opening a `sent` report moves it to `inReview`, only reports in review can be decided, every step is
  added to `history`, and the reporter is notified of the outcome. Sensitive reports are never published.

## Ranking

`/v1/feed` is ranked by `RecommendationEngine` from Track B (`agent/pinni_agent/recommender`), which
scores each story, decides must-see and writes the "why you see this" reasons. `pinni/recommender.py`
gives it the backend's data through small adapters (profile and events from SQLite, content
similarity from Chroma, what similar people liked from the knowledge graph) and keeps the parts that
follow the contract's place tree here: the `scale`/`placeId` filters and paging.

Channel suggestions blend what similar people follow (60%) with how well the channel fits the profile
(40%: categories, place, language, housing community, popularity); a reader with no profile gets the most
popular channels. `similarMembers` is shown from 20 people up, as the contract requires. As in the app's
mock, readers start as members of the channels they posted in. `GET /v1/channels?all=true` lists every
channel for the app's "More channels" section; it still has to be added to the contract.

Likes and dislikes sent again with `value: 0` (the app's undo) cancel the earlier reaction.

## The agent next to the backend

`newsroom.py` runs the Track B supervisor inside the backend. Each round hands every reader profile to
the agent's profile-based gathering (PSOAS notices for tenants who consented, campus news for students,
the home place, interests and wanted news, the categories they like); the agent selects, explains and
translates, and its stories go through `drafts.save_agent_story`.

News read on news sites needs no editor: it is published at once (`verification.verifiedBy` "Pinni
agent (source)") and lands on the map at its place (its own spot when the source has one, otherwise the
centre of its place, with the place's scale). Red-risk stories (residence, health, money, work, safety)
and stories that break the publish rules wait in the editor queue of the right desk instead, and a
story already out or decided is never overwritten. Reader reports never go through the agent: they
always wait for the editor desk of their category (`contract/processes/report-review.md`). Times are
cut to whole seconds, which is what the app's date decoder reads.

A round runs at startup and every `PINNI_AGENT_EVERY_MINUTES`, and from the editor page (**Run agent**,
`POST /v1/admin/agent/run`). Editors oversee everything the agent wrote, published or not, on the
page's **Agent news** tab (`GET /v1/admin/agent/stories`, within their desk; admins see all): approve,
edit (title, map label, "for you", or the whole JSON) or remove from the app (a reject, which the agent
does not undo). The agent keeps its working files in `data/agent.db`.
`tests/test_newsroom.py` and `tests/test_drafts.py` run the real supervisor offline.
