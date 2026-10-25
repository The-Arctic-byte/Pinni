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

## How to run

The app runs by itself on the sample news in `contract/mock/`. Start the backend only when you want the live API, the agent, or the editor page.

### App

On a Mac with Xcode (iOS 18, macOS 15):

1. Open `Pinni.xcodeproj`.
2. Choose the **Pinni** scheme and an iPhone simulator, or My Mac.
3. Run (⌘R).

The first launch is a new reader. Onboarding is four steps, and **Skip** works on each one. After that:

- **iPhone:** the map fills the screen. Drag the news sheet up. **Profile** is in the sheet’s toolbar.
- **Mac:** choose **Profile** in the sidebar.

A Debug build adds **Profile → Mock data**:

- **Reader** switches between the new user, Sara, and Matti. Sara and Matti already have profiles, so they skip onboarding. The choice is remembered.
- **API URL** sends the app to a backend. Type the address and press Return. `http://localhost:8000` works in the simulator and on Mac. A phone on the same Wi-Fi needs the computer’s address, `http://<that-ip>:8000`. Clear the field and press Return to use the sample news again.
- **Restart onboarding** shows the steps again.

To build from the terminal, select Xcode if `xcodebuild` says the developer directory is the Command Line Tools:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcodebuild -project Pinni.xcodeproj -scheme Pinni -destination 'generic/platform=iOS Simulator' build
```

### Backend, agent, and editor

The agent runs inside the backend. Any machine with [uv](https://docs.astral.sh/uv/) (it installs Python 3.12):

```bash
cd backend
uv run uvicorn pinni.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` lets a phone on the same network connect. Or with Docker, which also starts Neo4j, from the repo root:

```bash
docker compose -f backend/compose.yaml up --build
```

The first start fills the database from `contract/mock/` (`PINNI_SEED_CONTENT=false` leaves out the mock news, reports, and posts) and runs one agent round. The agent runs again every 30 minutes, and from the editor page.

- API docs: http://localhost:8000/docs
- Editor page: http://localhost:8000/admin/
- Neo4j browser, Docker only: http://localhost:7474

Development accounts use the password `pinni-dev`. Sign in to the editor as `aino@pinni.test` or `admin@pinni.test`. Reader accounts are `sara@pinni.test` and `matti@pinni.test`. Desk accounts and settings are in [backend/README.md](backend/README.md).

Point the app at this server with **Profile → Mock data → API URL**, as above.

## Tests

```bash
cd backend && uv run pytest     # backend, with the real agent and recommender
cd agent && uv run pytest
```
