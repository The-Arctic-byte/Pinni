# Contract

The single source of truth between the app (Track A), the agents (Track B) and the backend (Track C).
Change this folder first, get the other two tracks to review, then change code.

```text
schemas/     JSON Schema (2020-12), one file per type; shared types in common.schema.json
openapi.yaml API endpoints (OpenAPI 3.1), referencing the schemas
mock/        Sample data valid against the schemas — the app's first data source and the backend's seed
tools/       validate.py
```

Validate before every commit that touches this folder (CI runs it too):

```bash
uv run contract/tools/validate.py
```

It checks the schemas, every mock file against its schema, the OpenAPI file, and rules the schemas cannot express:
ids that must exist, feeds only contain published stories sorted by relevance, hard filters hold,
red-risk stories are never published without a human or with an unchecked translation, readers cannot post.
A new mock file must be added to `MOCK_SCHEMAS` in `validate.py`.

## Types

| Type | Schema | What it is |
|---|---|---|
| Place | `place.schema.json` | Area, city, country, region or world. Map areas and place chips. |
| Story | `story.schema.json` | One explained story, all languages. No per-reader data. |
| FeedPage / FeedItem | `feed.schema.json` | Stories ranked for one reader: relevance, must-see, reasons. |
| Event | `event.schema.json` | One interaction; append-only input for the recommender. |
| Profile | `profile.schema.json` | What the reader told us (onboarding, profile edits). |
| Channel / Suggestion / Post | `channel.schema.json` | Community channels, suggestions from similar people, posts. |
| Report | `report.schema.json` | News tip or problem report, with editor status. |
| Notification | `notification.schema.json` | Report status, must-see, for-you, channel posts. |
| User | `user.schema.json` | Role: reader, member, editor, admin. |

## Conventions

- Ids: lowercase slugs (`kiiminki-shooting`). Timestamps: ISO 8601 with offset.
- `LocalizedText` always has `en`; the app falls back to it.
- The backend ranks, the app only displays: relevance and "why you see this" come in the feed, never computed in the app.
- Locations of stories are areas (`radiusMeters` > 0) whenever the exact point could identify a home.

## Mock data

Stories are the Kaleva headlines from 21–23 Oct 2026 used in the demo, plus sample stories so every
onboarding area has a pin: Oulu centre, Linnanmaa, and Ritaharju. Finland and world stories have a
map point too. People, channels, reports, counts and the community story are sample data.
Coordinates are approximate.
Personas: `u-sara` (new student from Iran, Persian, Kiiminki, non-EU, PSOAS), `u-matti` (Finnish local, Kiiminki),
`u-new` (just installed, no profile: cold start), `u-aino` (editor), `u-admin`.
