# Pinni

Local news for Oulu, explained for the people it affects, in their language.

| Part | Folder | What it is |
|---|---|---|
| App (Track A) | `App/`, `Pinni.xcodeproj` | SwiftUI app for iPhone and Mac: map, feed, community, reports |
| Agent (Track B) | `agent/` | Supervisor agent that gathers and explains news, and the feed recommender |
| Backend (Track C) | `backend/`, `admin/` | FastAPI service implementing the contract, with the agent inside it, and the editor page |
| Contract | `contract/` | JSON Schemas, OpenAPI and mock data all three parts follow |

```
reader profiles (app) ──► agent gathers site news ──► published on the map and in feeds
                                     └─ red-risk news (residence, health, safety…) ──► editor
reader reports (app) ──► editor desk of the report's category (/admin) ──► status + notification in the app
```

## Run everything

**1. Backend, agent and editor page**, on any machine with [uv](https://docs.astral.sh/uv/):

```bash
cd backend
uv run uvicorn pinni.main:app --host 0.0.0.0 --port 8000
```

Or with Docker, which also starts Neo4j:

```bash
docker compose -f backend/compose.yaml up --build
```

The first start fills the database from `contract/mock/` (`PINNI_SEED_CONTENT=false` leaves out the
mock news, reports and posts) and runs one agent round; the agent runs
again every 30 minutes and from the editor page. API docs: `http://localhost:8000/docs`. Editor page:
`http://localhost:8000/admin/`. Development accounts use the password `pinni-dev`: `sara@pinni.test`
and `matti@pinni.test` (readers), `admin@pinni.test` (all categories), `mira@pinni.test` (city desk),
`leo@pinni.test` (politics desk). Details in [backend/README.md](backend/README.md).

**2. App**, on a Mac with Xcode: open `Pinni.xcodeproj`, run a Debug build, and in
**Profile → Mock data** enter the backend address (`http://localhost:8000` on the same Mac, or
`http://<backend machine's IP>:8000` on the same network), then relaunch the app. The debug persona
switch signs in as Sara or Matti.

## Tests

```bash
cd backend && uv run pytest     # backend, with the real agent and recommender
```
