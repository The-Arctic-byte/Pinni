# Pinni — Tasks

All news for everyone in Oulu (economy, society, politics, shopping, sport, safety, …), internationals first.
A map you zoom from your street out to the world, ranked per person, explained in their language, checked by a human.

Design sources:
- [Moi Oulu live demo](https://claude.ai/artifact/TJhffdxh8SGDXPh9KFJKMz) — scales, tabs, community, editor flow.
- [Moi Oulu App Screens](https://claude.ai/artifact/CFNut7bAeGd9GLyFneSCjk) — story layout, context cards, bilingual view, language tiers.
- Visual style: Flighty — colour-coded map, 3D map, glanceable cards.

Rules:
- Phase 0 (the contract) is done by all three members together before any track starts.
- After that the three tracks run in parallel. Nobody changes the contract alone: update `contract/` first, then code.
- The app ships its first version on mock data that follows the contract exactly, so switching to the real API is a config change.
- Only the current phase is detailed; refine the next one just before starting it.

---

## Team

| Track | Owner | Builds |
|---|---|---|
| A · App | [Member A] | iPhone + Mac app (SwiftUI), map, onboarding, community, profile, mock data |
| B · Agents | [Member B] | LangChain supervisor, MCP tools, source gathering, recommendation model |
| C · Backend | [Member C] | FastAPI, the three databases, auth + roles, admin web page, notifications, Ollama hosting |

## Architecture

```text
 iPhone / Mac app ──HTTPS──▶ FastAPI backend ─────────────▶ Admin web page (editor / admin)
   (mock first)                 │      ▲
                                │      │ approve / edit / reject
                                ▼      │
                     Supervisor agent (LangChain + MCP) ──▶ Ollama (Qwen, small, quantized)
                       │        │         │
                       ▼        ▼         ▼
                 SQLite      Knowledge   Vector DB
                 (events)    graph       (news + embeddings)
                             (interactions, similar people)
```

Repo layout (monorepo):

```text
App/        SwiftUI app (iPhone + Mac)
backend/    Python: FastAPI, agents, recommender, databases
admin/      Admin web page (served by the backend)
contract/   Shared JSON schemas, API spec, mock data — the single source of truth
docs/       This file and design notes
```

---

## Phase 0 — Contract (all three, first)

### T00 · Freeze the contract
Write `contract/` so all three tracks can work without waiting for each other.
- `Story`: id, scale (area / city / finland / world / place), place (city, country, …) for stories with no point, location (optional, area-level), topic, category colour key, need, isOpinion, risk (none / amber / red), label, title, explanation sections (known, happened, notKnown, forYou, context, actionPlace, timeline), originals, sources, status (draft / in review / published / rejected), verifiedBy, translations with tier, isCommunityReport, mapObject (e.g. stadium, for 3D).
- `Event` (interaction): userId, storyId?, type (open, dwell, like, dislike, reject, share, follow, join channel, report, zoom, map tap, skip), value, timestamp.
- `Profile`: target group, language, area, housing (e.g. PSOAS, with consent), category weights, interests, wanted news, hard filters.
- `Channel`, `Report`, `Notification`, `User` + role (reader, member, editor, admin).
- API list: feed, story, places, events (batch upload), profile, channels, reports, notifications, auth.
- `contract/mock/`: mock data for every type, valid against the schemas. Track A loads it; Track C seeds from it.

Done when:
- [x] Draft: `contract/` schemas, `openapi.yaml`, mock data, `tools/validate.py`, CI workflow.
- [ ] JSON Schemas + OpenAPI file reviewed by all three.
- [x] Mock data validates against the schemas locally (`uv run contract/tools/validate.py`).
- [ ] CI workflow (`.github/workflows/contract.yml`) seen green on GitHub.

---

## Track A · App (first version on mock data)

### A1 · Theme, icons, localization
- System colours and font, automatic light/dark, `AccentColor` for selection and relevance.
- Category colours **only on the map** (pins, areas, 3D objects), Flighty-style.
- SF Symbols for UI; Thiings (licensed) for topic icons.
- `Localizable.xcstrings`: en, fi, fa, sv. RTL safe (Persian).

Status:
- [x] `AccentColor` (light `#12806A`, dark `#5FD3B5`); category map colours in `Category+Style.swift`.
- [x] String Catalog with fi / fa / sv for every current UI string — marked "needs review" for native speakers.
- [x] App runs in Persian with right-to-left layout; story text follows the story's language direction.
- [ ] Thiings topic images (SF Symbols stand in via `Category.symbolName`).

### A2 · App shell
Tabs: Map · News · Community · Profile. Report button on the map and on every story.
Mac: `NavigationSplitView` sidebar, map as detail, story in `.inspector`.

Status: [x] tabs (iPhone) and sidebar (Mac) with placeholder Map, News, Community, Profile. Report button and inspector come with A7/A11.

### A3 · Mock data layer
`NewsService` protocol with a mock implementation that reads `contract/mock/`. The real API implementation comes in Integration.

Status: [x] Swift models for every contract type (`App/Models`), all 13 mock files decode; `contract/mock` is bundled as a project folder, so contract changes reach the app on the next build. Debug persona switch (Sara / Matti / new user) in Profile.

### A4 · Onboarding
Steps, in order:
1. Language (with tier label).
2. Who you are (target group: student, worker, family, local, …).
3. Most important categories: pick the ones that matter most; everything else keeps normal priority.
4. Area, home country, residence and housing (optional, with consent: e.g. PSOAS → the agent also gathers PSOAS news).
Every step can be skipped. Answers become the initial profile and the first events.
"What do you want to hear about most" and "What are you into" were dropped as redundant with categories; the recommender learns the rest from use.
The contract's `wantedNews` and `interests` stay and are sent empty (candidates to drop at contract review).

Status:
- [x] Four steps on a `NavigationStack`: iOS uses the system back button; macOS sheets get a Back button in the bottom bar. Shown on first launch (full screen on iPhone, sheet on Mac).
- [x] iOS / macOS 26+: soft scroll edge effect on all edges; Skip / Continue sit in a `safeAreaBar` (bar background on older OS).
- [x] `OnboardingAnswers` → `Profile` + one `onboardingAnswer` event per step (skipped steps logged as skipped); output validates against the contract.
- [x] Picked categories get weight 0.9; the rest are left out (= neutral). Residence and housing are only stored with consent.
- [x] Profile saved through `NewsService.save` (mock keeps it across relaunch); feed reloads in the chosen language.
- [x] Strings in fi / fa / sv (needs native review); Persian layout checked in the simulator.
- [ ] Events are dropped by the mock until A8 adds the local queue.
- Debug: Profile → "Restart onboarding"; launch argument `-onboardingStep <step>` opens a step directly.

### A5 · Map
- Four scales: Area, City (3D, pitched) · Finland · World. Pinch and a segmented control.
- Colour-coded pins by category; size + accent ring = relevance.
- 3D map objects for some stories: e.g. a stadium for a sport event, more later (concert hall, campus, …).
- Safety stories as an area circle, never a point.

### A6 · Place chips (news without a point)
A strip like the demo with places: "Oulu", "Finland", "EU", "World", and the reader's home country. Tapping one shows that place's news ranked for the reader.

### A7 · Feed, News tab, story detail
- Sheet / sidebar with stories of the current scale, sorted by relevance.
- "Most important" slot that is never personalized away (safety near you, official changes that affect you).
- Story detail with the explanation sections, sources, verified-by, language switch (mine · EN · FI ⇄).
- Like, dislike, "not for me" (hard filter), share, report.

### A8 · Interaction tracking
Log every event from T00 (open, dwell time, likes, skips, zoom, map taps, …) locally; batch-upload once the API exists.

### A9 · Community
- Suggested channels ("people like you follow…"), join / leave.
- Post or share a story to a channel; send to others.
- Evaluate news: like / dislike, "is this accurate?", reject.

### A10 · Profile
Edit everything from onboarding, see and reset what the app has learned, language, notification settings, my reports with status.

### A11 · Report
Report a story or submit news, by topic. Shows status: Sent → Editor review → Published / Edited / Rejected. Local notification on publish (push in Integration).

---

## Track B · Agents and recommendation

### B1 · Ollama + LangChain baseline
Qwen small model (≈4B, 4-bit) via `ChatOllama`. Multilingual embedding model via Ollama. All model names in config so they can be swapped.

### B2 · MCP tool servers
- Sources: Kaleva RSS, City of Oulu, PSOAS website, university news, … (one tool per source, added when a profile needs it).
- Geo: place name → area / scale / place.
- Stores: vector search, knowledge graph queries, event history (read-only for the agent).
- Publishing: create draft, send to human review.

### B3 · Supervisor (orchestrator)
One supervisor that routes work to sub-agents / tools:
- **Find**: news by preferences, by location, by recommendation, by place (city, country).
- **Gather by profile**: add sources from a person's profile (lives in PSOAS → watch PSOAS site; studies at the university → campus news).
- **Select**: deduplicate, merge, classify topic / need / scale / risk, drop irrelevant items with a logged reason.
- **Explain**: write the explanation sections and context cards per language.
- **Translate + check**: translate, back-translate, compare with sources, set tier.
- **Route to human**: anything red-risk (residence, health, money, work, safety) and all community reports go to the editor queue.
- **Distribute**: pick target readers, trigger notifications.
- **Moderate community**: triage reports, apply hard filters from rejects.
- **Suggest channels**: from similar people in the knowledge graph.
- **Audit**: every step writes to a log the admin page can show.

### B4 · Recommendation model
Hybrid, updated continuously:
- Content: profile vector vs story embeddings (vector DB).
- Collaborative: what similar people read and follow (knowledge graph).
- Rules: hard filters (rejected topics, "not for me"), must-see items (safety near you, official changes for your group).
- Signals: explicit (onboarding, likes, dislikes, rejects, follows, joined channels) and implicit (opens, dwell time, skips, shares, zoom level, map taps), with time decay.
- Cold start: new users see mostly general importance + onboarding answers. Personal weight grows with the number of events.
- Exploration: a small share of stories outside the profile, so the model can learn.

Done when (B4):
- [ ] Offline test on mock events: rankings change as events are added; hard filters always hold; must-see items always appear.

---

## Track C · Backend, data, admin

### C1 · FastAPI skeleton
Endpoints from T00, serving the contract mock data first. Docker Compose with backend, Ollama, knowledge graph.

### C2 · Databases
- **SQLite**: events and profile changes (append-only), the input for preference updates.
- **Knowledge graph** (Neo4j): user ↔ story ↔ topic ↔ place ↔ channel ↔ source interactions; "similar people" queries.
- **Vector DB** (Chroma): stories + embeddings for retrieval and content-based ranking.

### C3 · Auth and roles
Reader (no account needed to read), member (to report, post, join channels), editor, admin.

### C4 · Admin web page
- Editor: review queue (agent drafts, community reports, reader flags), edit, approve, reject, send back to agent.
- Admin: users and roles, sources, hard-filter rules, audit log.
- Only editors and admins can sign in.

### C5 · Notifications
APNs push: story published (reporter), high-relevance story approved (target readers).

---

## Integration (all three)
- App switches from mock to the real API.
- Events flow app → SQLite → recommender → knowledge graph → feed.
- End-to-end: report from the app → admin approves → reporter gets a notification.

---

## Backlog
- First 30 days checklist (canvas screen 3).
- Ask with verified answers (canvas screen 4).

---

## Decisions
- Platforms: iPhone (iOS 18.0+) and native Mac (macOS 15.0+).
- Theme: system colours and font, automatic light/dark, `AccentColor`. Category colours only on the map.
- Icons: SF Symbols for UI, Thiings (licensed) for topics.
- Name: "Pinni"; "Moi" stays as the greeting.
- Audience: everyone in Oulu, internationals first. All news categories.
- Zoom = geographic scale. Size and ring = relevance. Scale is not importance.
- First impression is not personalized: most-important news first, personalization grows with use.
- Content: sources → supervisor agent → human editor signs before publishing.
- LLM: small Qwen model on Ollama on our server; the app only talks to our API.
- Backend: FastAPI (Python), SQLite + Neo4j + Chroma. Supabase dropped.
- UI languages: English (development), Finnish, Persian, Swedish.
- Accounts: reading needs no account; members sign in to report, post, join channels.
- Privacy: the profile is stored on the backend under an anonymous id so the recommender can use it; housing and residence are optional and need consent; story locations are areas; report locations rounded to street.

## Open questions
- Member names for Tracks A, B, C.
- Where the backend server runs (university VM, own machine, cloud) — decides Ollama hardware.
- Is a 4B model good enough for Persian and Finnish explanations? Test in B1 before committing; keep the model swappable.
