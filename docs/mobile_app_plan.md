# Brevio mobile app — phased build plan

> Working document for the **app layer** that consumes the existing `articles` + `stories` data on Neon. Pipeline (phases 1–5) is complete and producing data; this plan covers everything from "no app" to "PWA installed on a phone, daily-driver-ready" without touching the pipeline.

---

## 0. Decisions baked in before phase 1

| Decision | Choice | Rationale |
|---|---|---|
| **Pipeline scheduler** | Modal (`@modal.Cron`) | Schedule-precise; GitHub Actions cron drifted 30+ min, was deleted |
| **API host** | Modal `@modal.asgi_app` (FastAPI) | Same provider as the cron, 1–3s cold start, free credit covers MVP |
| **PWA framework** | Expo (universal RN, deploys to Web/iOS/Android from one codebase) | UI spec assumes Expo (`expo-vector-icons`, `WebView`); web build deploys as PWA today, native binaries later via EAS Build |
| **PWA hosting** | Cloudflare Pages | Unlimited free bandwidth, fastest edge CDN, no commercial-use restriction |
| **Database** | Neon Postgres (unchanged) | Already provisioned, pgvector + indices in place |
| **Email pipeline** | Keep alive in parallel | One subscriber (you) still gets the daily digest; switch to Resend later if needed |
| **Auth in MVP** | **None** | UI spec explicitly excludes login / accounts / saved stories. Public read-only API gated by static API key (or open if traffic stays low) |
| **Multi-user later** | Yes, but not in MVP | When added: Auth.js + Neon `users` table; defer until there are users to multi-tenant for |
| **Push notifications** | Deferred | UI spec explicitly excludes; design data model to support it later without refactor |
| **Real-time updates** | Deferred | Pipeline runs once a morning; app polls fresh on open |
| **Search** | Deferred | Excluded from UI spec |

---

## 1. Architecture (target state)

```
   ┌────────────────────────────────────────────────────────────────────┐
   │  Modal                                                              │
   │                                                                     │
   │  ┌──────────────────────┐    ┌──────────────────────────────────┐  │
   │  │ @modal.Cron          │    │ @modal.asgi_app(FastAPI)         │  │
   │  │ Daily pipeline       │    │ HTTPS read-API                   │  │
   │  │ (scrape/embed/cluster│    │  GET /api/v1/stories/top         │  │
   │  │  /synthesise/email)  │    │  GET /api/v1/stories/topic/{t}   │  │
   │  │                      │    │  GET /api/v1/stories/all         │  │
   │  │                      │    │  GET /api/v1/stories/{id}        │  │
   │  │                      │    │  GET /api/v1/health              │  │
   │  └──────────┬───────────┘    └──────────┬───────────────────────┘  │
   │             │                            │                          │
   └─────────────┼────────────────────────────┼──────────────────────────┘
                 │                            │
                 ▼                            ▼
         ┌──────────────────────────────────────────┐
         │ Neon Postgres                             │
         │ articles · stories                        │
         │ (existing schema, no new tables for MVP)  │
         └──────────────────────────────────────────┘
                                              ▲
                                              │ HTTPS / JSON
                                              │
   ┌──────────────────────────────────────────┴────────────────────────┐
   │  Cloudflare Pages                                                  │
   │                                                                    │
   │  Expo Web build                                                    │
   │  • Universal codebase (RN)                                         │
   │  • PWA manifest + service worker                                   │
   │  • Installable on iOS/Android via "Add to Home Screen"             │
   │  • Offline cache via service worker + AsyncStorage/IndexedDB       │
   └────────────────────────────────────────────────────────────────────┘
```

**Cost projection at MVP scale**: ~$0–1 / month (Modal free credit + Neon free tier + Cloudflare Pages free + OpenAI pipeline ~$0.50/mo).

---

## 2. What current data supports vs what the UI spec asks for

Quick audit of UI spec → data fit. Drives which features ship in MVP vs which get deferred.

### Covered by existing data (ship in MVP)

| UI element | Backed by |
|---|---|
| Story headline (multi-source) | `stories.synthesis.headline` |
| Story summary text | `stories.synthesis.summary` |
| Key points bullets | `stories.synthesis.key_points` |
| Topic chips | `stories.synthesis.topics` (multi) or `articles.topics` (singleton) |
| Source dots count | `stories.article_count` |
| "N sources" badge | `stories.article_count` |
| Time-ago metadata | `stories.last_seen_at`, `articles.published_at` |
| Timeline (oldest → newest source cards) | `articles WHERE story_id=? ORDER BY published_at ASC` |
| Author per source card | `articles.author` |
| Article URL ("Read on X →") | `articles.url` |
| First-reported date | `MIN(articles.published_at)` per story = `stories.first_seen_at` |
| Singleton headline | `articles.title` |
| Singleton summary fallback | `articles.summary` (LLM-generated per-article) or `raw_metadata.summary` (RSS description) |
| All News chronological sort | `stories.last_seen_at DESC` |
| Topic filtering | `topics @> ARRAY[topic]` |

### Missing — needs backend work (deferred to a later phase, app ships without these)

| UI element | What's missing | Workaround for MVP |
|---|---|---|
| **Source brand colors on dots** | No `display_name` / `brand_color` per source | Hard-code a static map in the app (`'cnbc' → '#005EB8'`, etc.). Defer DB-side metadata to backend phase. |
| **Role badges** (PRIMARY / COVERAGE / COMMENTARY / REACTION) | Articles aren't role-classified | MVP: omit the role badge entirely. Stretch: derive `PRIMARY` = oldest member, no other badges. |
| **"First reported" subtle badge on first source card** | Trivially derived from chronology | Just check if it's the oldest member, render badge in app. **No backend work.** |
| **Author per source card** | `articles.author` exists but isn't always populated | Render conditionally. If null, skip the author line. |
| Source-publisher logo (vs colored dot) | No logo assets | MVP: colored dot only (matches spec). Deferred enhancement. |

### Not in MVP per UI spec (don't build)

Push notifications · Search · Auth/login · Saved/bookmarked stories · Multiple reading modes · Comments/reactions · Audio/TTS · Settings screen · Country filter · Reading streaks · Custom theme toggle. The UI spec explicitly excludes all of these.

---

## 3. Phased build plan

Each phase is **shippable on its own**. You could stop after any phase and have a working artefact.

---

### Phase A — Backend foundation: Modal pipeline + read-API

**Goal**: Replace the (deleted) GitHub Actions cron with a Modal cron, and stand up the read-API on Modal. After this phase, the pipeline runs reliably and the API serves stories as JSON over HTTPS.

#### A1 — Migrate pipeline to Modal cron

- New file `modal_pipeline.py` at repo root: a Modal app that wraps `agent.scheduler.run_pipeline()` in a `@modal.Cron("0 12 * * *")` (or whatever schedule you want).
- Modal Secrets configured: `OPENAI_API_KEY`, `DATABASE_URL` (Neon pooler URL), `SMTP_*` (so the email digest keeps working for now), `DIGEST_TO`.
- The Modal app declares its dependencies via `image = modal.Image.debian_slim().pip_install_from_requirements("requirements.txt")` so the existing `requirements.txt` drives the container build.
- The runner function imports and calls existing code unchanged.
- Smoke test: `modal run modal_pipeline.py` triggers an immediate run; verify Neon writes happen.
- Deploy: `modal deploy modal_pipeline.py`. Cron starts firing on schedule.

**Deliverable**: pipeline running on schedule, no more drift.
**Effort**: ~2 hours.

#### A2 — Build the FastAPI read-API on Modal

- New directory `api/` at repo root with:
  - `main.py` — FastAPI app instance + route registration
  - `routes/stories.py` — the four story endpoints
  - `schemas.py` — Pydantic response models (`StoryListItem`, `StoryDetail`, `SourceCard`, `TopicChip`)
  - `deps.py` — DB session, optional API key gate
- The same `modal_pipeline.py` (or a sibling `modal_api.py`) registers an `@modal.asgi_app()` that returns the FastAPI instance.
- Endpoints, all read-only:
  - `GET /api/v1/health` → `{"ok": true, "version": "..."}`
  - `GET /api/v1/stories/top?limit=50&offset=0` → list, multi-stories first, sorted by `(article_count DESC, last_seen_at DESC)`
  - `GET /api/v1/stories/topic/{topic}?limit=50&offset=0` → filtered by `topics @> ARRAY[topic]`, same sort
  - `GET /api/v1/stories/all?hours=48&limit=100&offset=0` → chronological, sorted by `last_seen_at DESC`, includes singletons
  - `GET /api/v1/stories/{id}` → single story + all member articles in chronological order
- **Singleton handling baked into the API**: the response shape is uniform. When `story.synthesis IS NULL` (singleton), the API fills `headline` from `articles.title`, `summary` from `articles.summary || raw_metadata.summary`, `key_points = []`, `entities = []`, `topics` from `articles.topics`. The app doesn't need conditional rendering.
- CORS: allow the Cloudflare Pages domain (`https://brevio.pages.dev` or custom domain).
- Optional API key: `X-API-Key` header check, key stored as Modal Secret. Can be open for MVP if traffic stays low.

**Deliverable**: an HTTPS URL serving `/api/v1/stories/top` returning JSON.
**Effort**: ~1 day.

#### A3 — Verify with curl + browser

- Hit `https://your-app--api.modal.run/api/v1/health` from anywhere
- Hit `/api/v1/stories/top` and check the response shape matches what the app will need
- Capture the URL and the API key (if used) into env files for the app

**Effort**: ~30 minutes.

#### Backend work explicitly deferred to a later phase

Logged here so they don't get forgotten:

- Source publisher metadata in `config/sources.json`: add `display_name`, `brand_color` per source. (App will hard-code in MVP.)
- Article role classification (`PRIMARY` / `COVERAGE` / `COMMENTARY` / `REACTION`): adds an `articles.role` column, populated either by heuristic (oldest = primary) or LLM. Currently `MIN(articles.published_at)` per story = "first reported" — enough for MVP.
- Per-user state tables (`users`, `user_story_state`): only when auth ships.
- Web Push API subscription endpoints (`POST /api/v1/push/subscribe`): only when push notifications ship.

---

### Phase B — App scaffolding: Expo project + design system

**Goal**: An Expo app that runs on web (PWA), iOS Simulator, and Android Emulator, with the visual design system in place. No content yet — just empty tabs with the right colours, fonts, and navigation chrome.

#### B1 — Expo project bootstrap

- New directory `app/` (or `mobile/` to avoid clashing with the existing `app/database/`) created with `npx create-expo-app@latest brevio --template tabs` (or blank + Expo Router).
- Use **Expo Router** for file-based navigation — natural fit for the 4-tab structure in the spec.
- TypeScript enabled (`--template tabs` defaults to TS).
- Bottom-tabs navigation pre-wired by the template; rename tabs to `Top`, `Topics`, `All`, `About`.
- `.gitignore` updated to exclude `node_modules`, `.expo`, `web-build`.
- Add to monorepo? No — keep the Expo app as a sibling directory under the same repo so backend + frontend live together.

**Deliverable**: `npx expo start` opens a blank app with 4 working tabs.
**Effort**: ~1 hour.

#### B2 — Design tokens + theme

A `mobile/theme.ts` module exporting tokens:

- **Colours**:
  - light: `cream #FAF5EE`, `cardBg #FFFFFF`, `textPrimary #1A1410`, `textMuted #7A6E68`, `accent #EE9970`
  - dark: `bg #1A1410`, `cardBg #2A1F1A`, `textPrimary #F6BFA1`, `textMuted #9B8D85`, `accent #EE9970`
  - source-publisher map: a static `Record<string, string>` of `source_id → brand_color` with sensible fallback to grey. Maintained client-side in MVP.
- **Typography**:
  - serif headlines (load `Lora` via `expo-google-fonts/lora` — single weight 500 + 700 is plenty)
  - sans body (load `Inter` 400/500/600 via `expo-google-fonts/inter`)
  - scale: `displayLg 28pt`, `headline 20pt`, `body 16pt`, `meta 14pt`, `caption 12pt`, `chip 10pt`
- **Spacing**: 4/8/12/16/20/24/32px scale
- **Radius**: card 14px, chip 12px, button 8px
- **Shadow**: none. Use 1px hairline borders or background-contrast for elevation.

A `useTheme()` hook reads from React's `useColorScheme()` and returns the appropriate token set.

**Deliverable**: tokens module + theme hook, used by all later components.
**Effort**: ~3 hours.

#### B3 — Design-system primitives

A `mobile/components/` directory with reusable pieces:

- `<Card>` — rounded container with internal padding, press state, accepts children
- `<TopicChip>` — uppercase peach-text chip, supports active/inactive variants for the Topics tab
- `<SourceDot>` — small filled circle taking a `source` prop, looks up brand colour from the theme map
- `<SourceDotRow>` — row of up to 4 dots + "+N" overflow indicator
- `<MetaLine>` — "5 sources · 2h ago" formatted text
- `<TimeAgo>` — utility that formats `Date | string` into "Just now / 2h ago / Yesterday / Apr 28" per spec §9.2
- `<SerifH1>`, `<SerifH2>`, `<Body>`, `<Caption>` — typography primitives that pick up theme tokens
- `<Pressable>` wrapper that handles the subtle press state (slight bg shift) consistently

**Deliverable**: Storybook-style "components catalogue" route at `/dev/components` that renders every primitive — useful for visual QA without needing real data.
**Effort**: ~1 day.

#### B4 — Data layer: API client + React Query

- `mobile/lib/api.ts` — typed `fetch`-based client. Env-driven base URL (`EXPO_PUBLIC_API_URL`).
- TypeScript types matching the API response shapes from Phase A2.
- React Query (TanStack Query) installed and configured:
  - 5-minute stale time for `/stories/top` (refresh on app focus, on pull-to-refresh)
  - `persister` from `@tanstack/query-async-storage-persister` for offline cache via `AsyncStorage`
- Query hooks: `useTopStories()`, `useTopicFeed(topic)`, `useAllNews()`, `useStoryDetail(id)`.

**Deliverable**: `useTopStories()` returns real data from the Modal API.
**Effort**: ~3 hours.

**End-of-phase-B sanity check**: open the Expo app on your phone via the Expo Go QR code; see 4 empty tabs with correct colours/fonts; tap a debug button on the home tab → see `console.log` of real story data fetched from Modal.

---

### Phase C — The moneymaker: Top Stories tab + Story Detail

**Goal**: the most important screens in the app, end-to-end. Top Stories tab fully populated, Story Detail screen with the timeline. This phase is where you'll spend the most polish-time.

#### C1 — Story card components

Two variants, both built from the design-system primitives:

- **`<MultiStoryCard story={...}>`** — full card with topic chips, headline (3 lines), summary (3 lines + fade), source dot row, "N sources · Xh ago" meta.
  - Fade-out on line 3 of summary: use `react-native-linear-gradient` or a simple `MaskedView` for the gradient. Easy fallback: hard truncation if gradient pixel-pushing is fiddly.
- **`<SingletonCard story={...}>`** — smaller variant: 1 topic chip, headline (3 lines), summary (2 lines + fade), single source dot + publisher name + time inline.
  - Quietly designed to recede visually next to multi-source cards.

A wrapper `<StoryCard>` picks the variant based on `article_count`.

**Effort**: ~1 day.

#### C2 — Top Stories tab

`mobile/app/(tabs)/index.tsx` (Expo Router):

- Header: peach serif "Brevio" logotype + muted date subtitle
- Pull-to-refresh (`RefreshControl`) calling React Query's refetch
- `FlatList` rendering `<StoryCard>` per item, using `useTopStories()`
- Skeleton cards while loading
- Empty state ("Today's digest isn't ready yet")
- Error state ("Couldn't reach Brevio. Pull to retry.")
- Card-tap navigates to `/story/[id]`

**Effort**: ~1 day.

#### C3 — Story Detail screen

`mobile/app/story/[id].tsx`:

- Back button (no title bar)
- Topic chips
- Large serif headline (28pt)
- "5 sources · First reported 4 days ago" meta
- `SUMMARY` section (sans body, line-height 1.6)
- `KEY POINTS` section (bulleted list using `•` and indent)
- `TIMELINE — N SOURCES` section header
- **The timeline**: vertical rail (1px peach line down the left, with filled dots at each card's position). Source cards laid out vertically, oldest first.
  - Each source card: source-name caps + role badge if available + date · time + serif article title + author + "Read on X →" link.
  - For MVP, no role badges (deferred backend work); show "FIRST REPORTED" subtle text on the oldest card.

For singletons (`article_count === 1`):
- Replace the timeline with a simple `SOURCE` section showing one source card.
- If `synthesis IS NULL`, replace SUMMARY/KEY POINTS with the article's `summary` shown as plain body text.

**Effort**: ~2 days.

#### C4 — In-app browser (WebView modal)

`mobile/components/InAppBrowser.tsx`:

- `react-native-webview` opens the article URL
- Slides up from the bottom (`presentation: 'modal'` in Expo Router or `react-native-modal`)
- Top bar: hostname text + close button (X)
- Share button → `expo-sharing` native share sheet
- Thin peach progress bar at top, driven by `onLoadProgress`

**Effort**: ~half day.

#### C5 — Onboarding (first launch only)

- One-screen welcome (spec §8) shown on first launch
- Dismissed by tapping "Start reading"
- Persistence: `AsyncStorage.setItem('seen_onboarding', '1')` after dismissal
- Skipped on every subsequent launch

**Effort**: ~2 hours.

**End-of-phase-C deliverable**: an app where you can scroll Top Stories, tap a multi-source card, see the synthesised headline + summary + key points + chronological timeline of every source, tap a source card, read the article in an in-app browser, navigate back. The core read-loop works.

---

### Phase D — Topics + All News tabs

**Goal**: two more tabs done. The app now has all four nav surfaces functional.

#### D1 — Topics tab

`mobile/app/(tabs)/topics.tsx`:

- Horizontal `ScrollView` of `<TopicChip active={...}>` chips at the top (AI / Technology / Business / Science / General)
- Active chip filled peach + white text
- Below: same `FlatList` of story cards using `useTopicFeed(activeTopic)`
- Within a topic, sort: multi-stories first (by `article_count DESC, last_seen_at DESC`), then singletons (by `last_seen_at DESC`). The API endpoint handles this ordering.

**Effort**: ~half day.

#### D2 — All News tab

`mobile/app/(tabs)/all.tsx`:

- Simple "All News" title + "Last 48 hours" subtitle
- `FlatList` of mixed multi-stories + singletons, sorted by `last_seen_at DESC`
- Pull-to-refresh, skeletons, error states — reuse the same components as Top Stories

**Effort**: ~half day.

**End-of-phase-D**: all four tabs work. The app is feature-complete for the MVP read loop.

---

### Phase E — About tab + visual polish

**Goal**: the smaller surfaces + the polish pass that turns a working app into a shippable app.

#### E1 — About tab

`mobile/app/(tabs)/about.tsx`:

- Centered Brevio icon (64x64)
- Logotype + serif italic tagline ("One story, every source, full timeline.")
- Short description paragraph
- Links: "Read the blog →", "Send feedback →" (`mailto:`), "Privacy →"
- All static, no API calls

**Effort**: ~2 hours.

#### E2 — App icon + splash screen

- Source the peach "B with broken spine + dot" mark in a vector format
- Generate icon set via `expo-icon` (or just provide 1024x1024 PNG and let Expo handle the rest)
- Splash screen: centered icon on cream background

**Effort**: ~2 hours.

#### E3 — Light/dark mode verification

- Walk every screen in both modes
- Verify peach accent looks right against both backgrounds
- Verify all text meets WCAG AA contrast (4.5:1 for body, 3:1 for large headlines)
- Fix any rough edges (the spec is explicit: respect OS theme, no in-app toggle)

**Effort**: ~half day.

#### E4 — Accessibility pass

- Every `<Pressable>` has an `accessibilityLabel` and `accessibilityRole`
- Dynamic type: typography scales with the OS font-size preference
- Screen reader walkthrough of one story detail screen — does the order make sense?

**Effort**: ~half day.

#### E5 — Performance pass

- `FlatList` virtualisation: verify big feeds don't stutter on scroll
- Image-loading: there are no images in MVP per spec, but ensure no unintentional layout thrash
- Bundle size check: `npx expo export --platform web` and see the gzipped JS bundle size

**Effort**: ~half day.

**End-of-phase-E**: app is visually polished, accessible, dark-mode-correct, ready to deploy.

---

### Phase F — Deploy: PWA on Cloudflare Pages

**Goal**: the app lives on a real URL and can be installed on a phone via "Add to Home Screen".

#### F1 — Expo Web production build

- `npx expo export --platform web --output-dir web-build`
- Inspect the output: index.html + assets folder, fully static.
- Verify the build renders correctly in a local server (`npx serve web-build`).

#### F2 — PWA manifest + service worker

- `app.json` `web` section: `manifest` block with name, short_name, theme_color, background_color, icons array (192px, 512px), display: `standalone`, start_url: `/`.
- Service worker: Expo Web doesn't bundle one by default. Add one via either:
  - `next-pwa`-style approach using Workbox + a small generator script, OR
  - Hand-written SW that caches the app shell + uses stale-while-revalidate for `/api/v1/*` requests
- Cache strategy:
  - Static assets (JS, CSS, fonts): cache-first with versioning
  - API responses: stale-while-revalidate, 5-minute TTL
  - Story detail pages: cache-first with revalidation on focus

#### F3 — Cloudflare Pages deployment

- Create a new Pages project, connect to the GitHub repo
- Build settings:
  - Build command: `cd mobile && npx expo export --platform web --output-dir ../web-build`
  - Output directory: `web-build`
  - Environment variables: `EXPO_PUBLIC_API_URL=https://...modal.run`
- First deploy → CF Pages assigns a `*.pages.dev` URL
- Custom domain (optional, free with CF): `brevio.app` or whatever you own

#### F4 — Install on phone, test offline

- Visit the URL on iPhone Safari → "Share → Add to Home Screen"
- Same on Android Chrome → "Install app" prompt
- Verify: opens fullscreen, no browser chrome, splash works
- Turn on airplane mode → open the app → last cached feed should appear

**Effort total for Phase F**: ~1 day.

**End-of-phase-F**: Brevio is installable, openable from your home screen, and works offline.

---

### Phase G — Backend enhancements (gated by app needs, optional)

These are the deferred backend changes called out in §2. None block MVP shipping; sequence them in the order you decide you want each feature in the app.

#### G1 — Source-publisher metadata in `sources.json`

Add per-source fields:
```json
{
  "id": "cnbc",
  "name": "CNBC",
  "display_name": "CNBC",
  "brand_color": "#005EB8",
  ...
}
```

Expose via the API (`/api/v1/sources` or inline on every source card). App switches from hard-coded map to API-driven.

**Effort**: ~half day.

#### G2 — Article role classification

Add `articles.role` column with enum: `PRIMARY`, `COVERAGE`, `COMMENTARY`, `REACTION`. Two routes:

- **Heuristic**: oldest article = `PRIMARY`, others = `COVERAGE` (no LLM cost). Misses commentary vs reaction distinctions.
- **LLM-classified**: add a step to `agent.story_summarizer` that classifies each member article's role within the story. Costs ~5–10 more output tokens per call. Better distinctions.

Recommend: ship heuristic first; upgrade to LLM later if the labelling looks too coarse.

**Effort**: ~1 day (heuristic) or ~2 days (LLM).

#### G3 — Twice-daily Modal cron (optional)

If you want fresher data: change `@modal.Cron("0 12 * * *")` to two crons (morning + evening). Doubles OpenAI cost but stays well under $1/month.

**Effort**: ~10 minutes.

---

### Phase H — Deferred (post-MVP)

When the app has been in your daily-use rotation for a few weeks and you've built opinions about what's missing, these are the natural next steps:

| Feature | When to consider |
|---|---|
| Multi-user (Auth.js + `users` table + per-user state) | When you want to share Brevio with people |
| Saved/bookmarked stories | When you wish you could refer back to a story you read yesterday |
| Web Push notifications | When you want a morning "your digest is ready" ping |
| Native iOS/Android binaries via EAS Build | When the PWA's polish ceiling starts feeling tight |
| Search (semantic via pgvector) | When you find yourself wanting to look up old stories |
| Settings screen (topic preferences, source allow/block) | When more than one person uses Brevio |
| Audio narration / TTS | When commute-mode becomes a real need |

Each of these adds a phase, none of them block MVP.

---

## 4. Summary timeline

| Phase | Deliverable | Effort |
|---|---|---|
| A — Modal pipeline + read-API | API serves stories over HTTPS | ~2 days |
| B — Expo scaffolding + design system | App opens, 4 empty tabs, theme correct | ~2 days |
| C — Top Stories + Story Detail + in-app browser | Core read loop works end-to-end | ~4 days |
| D — Topics + All News tabs | All 4 tabs feature-complete | ~1 day |
| E — About + polish + a11y | Production-quality | ~1.5 days |
| F — Deploy to Cloudflare Pages as PWA | Installable on phone | ~1 day |
| **MVP total** | **Daily-driver PWA** | **~11–12 days** |
| G — Backend enhancements (incremental) | Source colors, role labels, faster cron | ~2 days as needed |
| H — Deferred features | Push, auth, native, etc. | TBD |

At ~2 hours of focused work per day, that's roughly **5–6 weeks calendar time** for the MVP, scaling down with more daily availability.

---

## 5. Costs at each phase (monthly)

| | Modal | Neon | Cloudflare Pages | OpenAI | Total |
|---|---|---|---|---|---|
| Pipeline-only (today + Phase A) | $0 (credit) | $0 | – | ~$0.50 | **~$0.50** |
| + API (end of Phase A) | $0 (credit) | $0 | – | ~$0.50 | **~$0.50** |
| + Deployed PWA (end of Phase F) | $0 (credit) | $0 | $0 | ~$0.50 | **~$0.50** |
| 100 users (organic growth) | $0–2 | $0 | $0 | ~$0.50 | **~$0.50–2** |
| 1,000 users | $5–10 | $19 (Launch tier) | $0 | ~$1 | **~$25–30** |
| 10k users + push + native | $10–30 | $19 | $5 (Pro) | ~$5 | **~$40–60** |

No commercial-use restrictions at any tier of any provider. The whole stack remains essentially free until ~100s of users.

---

## 6. Risks and open decisions

### Will be settled when we hit the relevant phase

- **API key vs fully open API.** Open for MVP keeps things simple; static API key adds one header and a Modal Secret. Decide at Phase A3.
- **Custom domain or `*.pages.dev`?** Free `*.pages.dev` is fine for MVP. Domain registration (~$10/year) makes it feel more polished. Decide at Phase F3.
- **Service worker authoring approach.** Hand-rolled vs Workbox vs Expo's built-in. Decide at Phase F2.

### Worth thinking about now

- **The 92% singleton problem (still real).** UI spec §3.3 addresses it with the visual-hierarchy answer (singleton cards smaller and quieter than multi-source cards). That implementation needs to land cleanly in Phase C — if singletons end up looking *too* small, the All News tab feels punitive; if they look *too* big, the multi-source "wedge" gets lost. Visual QA at the end of Phase C is the gate.
- **Singleton synthesis later?** Currently `min_size=2` in `agent.story_summarizer`. If the singleton cards in the app feel anaemic (raw RSS description is short or absent), revisit the cost-vs-quality call and consider running synthesis on singletons too (~$0.17 backfill, ~$0.01/day going forward).
- **Polling cadence on app open.** Right now: 5-min stale time + refetch on focus. If users keep the app open a lot, this could thrash. Decide based on usage telemetry later.

### Not blocking, but worth tracking

- Expo's Web target has rough edges (some RN components don't render identically across platforms). Plan for ~10–15% extra time on Phase B/C for cross-platform polish.
- Cloudflare Pages build minutes are limited on free tier (~500 builds/month). At MVP scale, plenty; just don't `git push` 50 times in an hour.

---

## 7. Where this plan lives

This document at `docs/mobile_app_plan.md`. Updated as phases ship. Each phase that's been completed should get a status tag (e.g., `[shipped 2026-05-20]`) at its heading.

The current pipeline plan still lives at `~/.claude/plans/write-a-plan-to-snazzy-sphinx.md` (phases 1–5). When Phase A here ships, the pipeline plan can be archived.
