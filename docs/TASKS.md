# Pinni — Tasks

News for international students in Oulu, on a 3D map. Design source:
[Moi Oulu App Screens](https://claude.ai/artifact/CFNut7bAeGd9GLyFneSCjk) (11 screens).

Rules:
- Work top to bottom. Only the current milestone is detailed; refine the next one just before starting it.
- Each task is done when its "Done when" list is true on a device or simulator.
- Mock data until M4. Do not change the `Story` model after M1 without updating this file first.

---

## M1 — Foundation

### T01 · Theme and icons
Use what the system gives us; no custom colour palette or font.
- Colours: system semantic colours (`.primary`, `.secondary`, `.background`, materials). Automatic light/dark mode.
- One custom colour: `AccentColor` in the asset catalog (mint `#5FD3B5` from the design, tuned for light mode).
- Type: system font and Dynamic Type text styles.
- Icons: SF Symbols for UI controls (tabs, buttons, chevrons). [Thiings](https://www.thiings.co/things) images (licensed) for topic icons and illustrations, added to the asset catalog.

Done when:
- [ ] `AccentColor` set for light and dark.
- [ ] Topic icons from Thiings in `Assets.xcassets`, one per `Topic`.
- [ ] Every screen looks right in both light and dark mode.
- [ ] `Localizable.xcstrings` with en, fi, fa, sv; previews run in Persian (RTL) without layout breaks.

### T02 · Tab shell
Four tabs: Map, Start, Ask, Me (screen 1 tab bar), SF Symbols for tab icons.

Done when:
- [ ] iPhone: `TabView` with the four tabs, accent colour on the selected one.
- [ ] Mac: `NavigationSplitView` — sidebar (Map, Start, Ask, Me + feed), map as detail, inspector slot for a story.
- [ ] Each section shows a placeholder view.

### T03 · Story data model
One model behind the map, feed, story and safety screens.
- `Story`: id, title, summary, topic, need, area, coordinate (area-level, never exact address), whatHappened, whyItMatters, whatItMeans, sources, verifiedBy, verifiedAt, isOpinion, language, updates.
- `Topic` (screen 7): safety, world, opinion, politics, strike, shopping, outage, traffic, economy, environment, sport, cityLife — each with a Thiings image.
- `Need`: safety, information, understanding, usefulness, community — shown as a label, not a colour.
- `MockData` with the stories shown on screens 1, 2, 5, 6.

Done when:
- [ ] Models compile, are `Codable` and `Identifiable`.
- [ ] Mock data covers every topic used in the designs.

---

## M2 — Map (screens 1, 5, 7)

### T04 · 3D map
MapKit, pitched camera over Oulu, realistic elevation, map follows system light/dark.

Done when:
- [ ] Map opens over the user's home area, pitched, buildings in 3D.
- [ ] Asks for "when in use" location with a localized reason string; works without it.
- [ ] "Back to my location" button recentres.

### T05 · Story pins
Pin = Thiings icon (topic) + ring (why shown: accent ring = matches you, dashed = opinion, safety pulses once). Need is shown in the story, not on the pin.

Done when:
- [ ] Mock stories appear as pins; tapping one opens the story (T07).
- [ ] Pins are readable in light and dark mode.

### T06 · Feed bottom sheet + sky layer
Sheet with filter chips (For you, News, Events, Services) and "N things for you today". City-wide stories float at the top ("Above the city").

Done when:
- [ ] Sheet has small / medium / large detents.
- [ ] Chips filter the list and the pins.
- [ ] Greeting header shows day, weather placeholder, sunset.

---

## M3 — Story, Start, Ask (screens 2, 3, 4, 6)

### T07 · Story detail (screens 2, 6)
What happened / Why it matters / What this means for you; safety variant with What we know / Not known yet / What you can do + updates timeline. Verified-by row, sources, Save / Share / Source / Wrong?

### T08 · First 30 days checklist (screen 3)
Progress bar, urgent item with due date and source, task list with done state persisted locally. Checklist depends on profile type (student / worker / family; EU or non-EU).

### T09 · Ask (screen 4)
Question field + voice button, verified-answer card, "Your questions" with Sent → In review → Answered status.

---

## M4 — Real data

### T10 · Personal profile
Profile type (student / worker / family; EU or non-EU), home area, followed topics, interests (persona on screen 5). Drives "For you" and the T08 checklist.

### T11 · Kaleva RSS ingest
Fetch and parse the feed; map items to `Story` (topic, area). Decide where classification runs before starting.

### T12 · Backend
Supabase (already in `.gitignore`): stories, verification, questions. Decide scope before starting.

---

## M5 — Languages & culture (screens 8–11)

### T13 · Language tiers and translated stories (screens 8, 11)
### T14 · Context cards (screen 9)
### T15 · Bilingual view + word of the day (screen 10)

---

## Decisions
- Platforms: iPhone (iOS 18.0+) and native Mac (macOS 15.0+). No iPad or Vision Pro for now.
- Theme: system colours and font, automatic light/dark, `AccentColor` only.
- Icons: SF Symbols for UI, Thiings (licensed) for topics.
- Name: "Pinni" in the UI; "Moi" stays as the greeting.
- Audience: all internationals in Oulu (students, workers, families), not only students. Student content (PSOAS, OYY, ESN) is one profile type, not the default.
- Mac layout: map fills the window; feed in a sidebar (`NavigationSplitView`), story detail in an inspector (`.inspector`). iPhone keeps tabs + bottom sheet.
- Content (M4): Kaleva RSS → AI draft → human editor verifies before publishing.
- UI languages at launch: English (development), Finnish, Persian, Swedish, via one String Catalog. Persian is right-to-left: use leading/trailing, never left/right.
- Location: "when in use" permission to centre the map; home area still chosen in the profile.
- Accounts: none until M4. Profile, checklist and saved stories live on device.
