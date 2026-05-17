# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Bain Luck** is a prediction market discovery platform that translates betting and prediction markets into intuitive probabilities. Users see "60% vs 40%" instead of "-150 / +130". Started with sports odds, now covers economics, politics, tech, culture, weather, and more via the Discover feed.

**North Star**: The most engaging way to explore what the world thinks will happen.
**Target User**: Casual fans who want probability-first context — not betting advice.
**Live Site**: https://bainluck.com (Discover is the default landing page) | **Sports Feed**: https://bainluck.com/sports

---

## The #1 Technical Challenge: Semantic Matching

The core magic of Bain Luck is **perfect semantic understanding** of every event, market, and source — then grouping and matching them so the user sees one unified view. This is the hardest technical problem in the product and the biggest leverage point.

There are 4 layers of matching, measured by `scripts/audit_event_matching.py`:

| Layer | What it measures | Audit | Status (April 24) |
|-------|-----------------|-------|-------------------|
| **L1: Event Existence** | Every game exists with all sources | `--self-check` | ✅ 100% |
| **L2: Market → Event** | Game markets linked via event_id | `--self-check` | ✅ 100% |
| **L3: Futures Surfacing** | Season futures on event detail pages | `--self-check` | ✅ 100% (MLB/NBA/NHL) |
| **L4: Market Completeness** | Every market type showing per game | `--l4-deep` | ✅ Verified live (April 24) |

Plus **Grid Accuracy** (`scripts/audit_grid_accuracy.py`): 51/51 (100%).

**Hill-climb playbook**: `docs/hill-climb-guide.md` — measure → fix biggest bucket → re-measure → repeat.

**Philosophy**: Any metric below target for markets that SHOULD match is a bug, not a feature gap. Distinguish "our bug" from "upstream gap" (Kalshi liquidity, Polymarket coverage).

---

## Linked Reference Docs

| Doc | Purpose | When to update |
|-----|---------|---------------|
| `docs/backlog.md` | All outstanding work items (SINGLE SOURCE OF TRUTH) | When items ship, are added, or reprioritized |
| `docs/architecture-reference.md` | Core system design: aggregation, resilience, charts, tasks, admin | When architecture changes |
| `docs/gotchas-reference.md` | Extended gotchas (items 16-62) | When new gotchas discovered |
| `docs/quality-audit.md` | Audit script usage, check catalog | When checks added/removed |
| `docs/hill-climb-guide.md` | Matching accuracy hill-climb playbook | When layers/gotchas change |
| `docs/feature-reference.md` | Detailed feature documentation | When features ship |
| `docs/completed-features.md` | Shipped features log | When features ship |
| `docs/design-system.md` | Visual design system: colors, type, motion, voice, components | When design tokens or patterns change |

---

## Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+), 3,500+ tests | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis (dual workers: realtime + background) | Heroku Redis |
| Frontend | Next.js 14 (React) | Vercel |
| iOS/macOS App | SwiftUI (shared codebase, 89 Swift files) | TestFlight / direct |

**Key External Services:**
- **The Odds API** — Sports odds data (~$119/mo, 5M monthly quota — monitor closely)
- **Kalshi** — Prediction market data (free, API key required)
- **Polymarket** — Prediction market data (free, no API key)
- **StatPal** — Schedules, rosters, injuries, play-by-play (~$99/mo)
- **DataGolf** — Golf predictions, live in-play probabilities, leaderboards (~$30/mo)
- **MLB Stats API** — Live baseball win probability (free, no key)
- **ESPN** — Team colors, logos, live game data, win probability (free, undocumented)
- **OpenAI** — GPT-4o-mini for LLM classification + market hook descriptions (~$10/mo)
- **Pexels** — Free stock photos for Discover feed cards (200 req/hr)
- **TMDB** — Movie/TV metadata, posters, cast info (free tier, client-side via `frontend/lib/tmdb.ts`)
- **Firebase Auth** — Google + Apple Sign-In (free tier)

---

## Development Workflow

- **Both auto-deploy from GitHub**: `git push origin master` deploys backend (Heroku) and frontend (Vercel)
- **Database migrations**: `alembic revision --autogenerate -m "description"`, applied on Heroku release
- **Backend tests**: `cd backend && python3 -m pytest tests/ -v` (3,500+ tests)
- **Single test**: `cd backend && python3 -m pytest tests/test_feed_scoring.py::TestFeedBaseScoring::test_live_nba -v`
- **Integration tests**: `cd backend && python3 -m pytest tests/integration/ -v` (335+ contract tests)
- **Smoke test (MANDATORY before push)**: `cd backend && python3 -m pytest tests/test_startup.py -v` (<1s, catches import errors)
- **Frontend build (MANDATORY before push)**: `cd frontend && npm run build` — catches BOTH TypeScript AND ESLint errors. Vercel runs this exact command; `tsc --noEmit` alone is NOT sufficient.
- **Frontend tests**: `cd frontend && npx jest` (single: `npx jest --testPathPattern=DiscoverCard`)
- **Procfile validates imports**: Release phase runs `python3 -c "from app.main import app"` before Alembic. If the app can't import, the release fails and the broken code never reaches the web dyno.
- **CI runs both**: GitHub Actions runs backend pytest + frontend `npm run build` on every push to master.

### Key Admin URLs
```
https://bainluck.com/admin              — Operations dashboard
https://api.bainluck.com/docs           — API docs (Swagger)
https://api.bainluck.com/api/admin/prediction-markets/link-rate?secret=$ADMIN_TOKEN  — Link rate health
```

---

## Project Structure

```
bainluck/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── models/models.py     # SQLAlchemy models (30 models)
│   │   ├── routes/              # API endpoints
│   │   ├── services/            # External API clients + event_registry.py
│   │   ├── config/              # win_prob_sources.py, league_configs.py
│   │   ├── tasks/               # Celery tasks (27 modules)
│   │   └── utils/               # Pure logic (sport_keys.py, prediction_market_matching.py, etc.)
│   ├── alembic/                 # Database migrations
│   └── tests/                   # 3,500+ pytest items
├── frontend/
│   ├── app/                     # Next.js app router (30+ pages, incl. /discover, /weather)
│   ├── components/              # React components (DiscoverCard, OddsChart, MarketMap, etc.)
│   └── lib/                     # API client, types, utilities
├── ios/Bain Luck/               # iOS + macOS app (SwiftUI, 89 Swift files)
└── docs/                        # Documentation
```

---

## Core Architecture

**Event Registry** (`services/event_registry.py`): Unified `find_or_create_event()` with 4-step cascade: exact source ID → cross-source ID → structured match (sport + time ± 4h + teams) → create. All 5 source tasks wired up. ESPN is a first-class source.

**Probability Aggregation** (`utils/aggregation.py`): `compute_aggregate_probability()` reads from `Event.win_probability_sources` JSONB. Source weights: betting 3.0, ESPN 1.5, stat_model 1.0, Kalshi/Polymarket/MLB 0.8. All sources write via `select+update` pattern (NOT ORM attribute assignment — silently fails due to session caching).

**Prediction Market Matching** (`tasks/prediction_market_matching.py`): Hourly task links Kalshi/Polymarket game markets to events. Three-phase: Link (Pass 1 ticker scan + Pass 2 general scan) → Re-validate (Phase 1.5) → Snapshot writing (Phase 2). Per-market commit to avoid deadlocks with live polling task. Link rate tracked at `/api/admin/prediction-markets/link-rate`.

**Source-Agnostic Resilience**: System works when any single source goes dark (validated during March 2026 Odds API quota exhaustion).

**Prediction Market Pipeline** (Kalshi/Polymarket → event detail page):
1. `poll_kalshi_markets` (every 2h) / `poll_polymarket_markets` (every 1h) — ingest ALL markets (minus crypto). Both paginate unfiltered.
2. `match_prediction_markets` (every 15 min) — link game markets to events via `event_id` FK. Pass 1: Kalshi ticker scan. Pass 2: Polymarket name matching.
3. `poll_live_prediction_markets` (every 2 min, realtime queue) — live price updates for linked markets.
4. Game-markets endpoint: loads via `event_id` FK + fallback (unlinked markets matching both team names + game ticker prefix or `category="game_prop"`).

**Discover Feed Ranking & Explanation Pipeline** (`routes/feed.py`, `utils/feed_market_quality.py`, `utils/feed_reasons.py`, `scripts/audit_feed_quality.py`):
- The feed builds multiple candidate pools (sports, non-sports volume, movement, enriched, soon-resolving), scores with futures highlights, then applies market-quality caps/diversity before returning cards.
- Quality classifier suppresses narrow commodity/finance ladders, repetitive dated buckets, social-count filler, and weak explanation cards. It separately boosts compelling public stories: politics, geopolitics, Fed/economics, AI/tech, health outbreaks, entertainment, and sports personnel.
- Deterministic futures explanations are now first-class. Do not rely on LLM hooks to make the first page understandable: headlines should name the mover/leader/source disagreement from existing outcome data (e.g., "Yes side up 32.5 points from opening").
- Personalization is intentionally bounded and latency-safe: recent Discover interactions produce small category plus feature/entity/archetype affinities for signed-in users and anonymous sessions. Right swipe is `like` / "more like this"; left swipe is `unlike` / "less like this" and should be treated as a soft downrank, not a permanent hard dismissal.
- LLM enrichment is intentionally bounded and async. `enrich_market_hooks` only targets feed-shaped candidates and Celery runs small batches (`limit=100` every 6h). `enrich_discover_llm_metadata` adds cached structured metadata under `FuturesMarket.market_metadata["discover_llm"]` for feed-shaped candidates (`limit=125` every 6h), and feed ranking consumes only that cached metadata. Never run LLM calls inside `GET /api/feed` or grind through the full open-market backlog (~56K markets).
- Daily LLM eval is advisory only: `evaluate_discover_with_llm` grades the top 50 Discover futures, compares against Polymarket email highlights, and writes `llm_proposed_*` review rows for admin inspection. These rows do not affect ranking unless a human later records an accepted promote/downrank decision.
- Current production audit target: `boring-rate@20=0`, `ladder/bucket-rate@20=0`, `duplicate-family-rate@20=0`, `explanation-coverage@20=20/20`. Use `python3 scripts/audit_feed_quality.py` to measure.

**Themed Dashboard Pages** (politics, entertainment, weather, economics) — all 5 native category pages polished (Politics, Entertainment, Weather, Economics, Preferences):
Each category page follows the same pattern:
- Backend route (`routes/politics.py`, `routes/entertainment.py`) queries `FuturesMarket` by `llm_sport_category` + Kalshi ticker prefixes, classifies into sub-themes, builds structured response with enriched market rows
- `_classify_kind()` assigns rendering hints (`spotify`, `rt`, `boxoffice`, `reality`, `binary`, `multi`, etc.) based on ticker prefix → name regex → outcome count fallback
- `_group_threshold_markets()` groups binary markets sharing an entity but differing by threshold (e.g., multiple "Movie X RT score ≥ N" markets) into heatmap-ready groups
- Frontend: CSS module (`politics.module.css`, `entertainment.module.css`), typed data from `lib/api.ts`, section components with tabbed sub-views
- Markets enriched with: `volume_24h`, `resolution_date`, `image_url`, `hook_description`, per-outcome `probability_change_24h`
- TMDB client (`lib/tmdb.ts`): client-side movie poster lookup with localStorage cache, used by entertainment CoverTile component

**iOS Authentication** (`ios/.../Services/AuthManager.swift`):
Backend-session-token pattern, NOT typical Firebase client auth. iOS SDK handles OAuth popup (Apple native / Google GID SDK) → raw credential sent to Bain Luck backend (`POST /api/auth/apple` or `/api/auth/google-access-token`) → backend verifies with identity provider, creates Firebase user, issues PyJWT session token (HS256, 30-day TTL) → iOS stores in Keychain, sends as `Bearer` on all API calls. Originated as Safari ITP workaround; iOS uses the same flow. Silent Google restore on token expiry. Apple credential revocation checked on foreground.

**Market Grouping via `group_id`** (`FuturesMarket.group_id`):
Markets that belong to the same real-world question (e.g., "Who wins Best Picture?" with 10 nominee sub-markets on Polymarket) share a `group_id`. This powers: Discover feed dedup (one card per question, not 10), cross-source matching on category pages, calibration curve accuracy, and related-market grouping on detail pages. Set during polling (`tasks/polymarket.py`: `f"polymarket:{event.id}"` for multi-market events). `market_metadata->>'polymarket_event_id'` stores the Polymarket event ID for backfilling `group_id` on markets that were ingested before the grouping logic was added.

**Calibration Pipeline** (`routes/calibration.py`, `tasks/backfill_winners.py`):
Public endpoint at `GET /api/calibration` (1h cache) returns pre-aggregated calibration buckets across 3 sources (Kalshi, Polymarket, Odds API) with `price_moved` dimension for trading activity analysis. Uses `calibration_probability` (closing line) not `opening_probability`. Virtual market reconstruction via `(is_grouped OR eligible >= 3)`. `backfill_winners` task (every 6h) runs 7 phases: group_id backfill, null untradeable (≤2 snapshots), closing lines, calibration prices (Parts A/B/C), `is_winner`. `backfill_polymarket_history` (every 6h) fetches historical prices from Polymarket's CLOB API for outcomes with sparse snapshots. Frontend page at `/calibration` with ECE metric and "Does Trading Activity Matter?" section. MCE 2.7pp as of May 14. See `docs/architecture-reference.md` for full details.

**Rage Shake Bug Reporting** (`ios/.../Utils/RageShake.swift`, `routes/admin.py`, `frontend/app/admin/bug-reports/`):
Shake phone or `Cmd+Shift+F` (macOS) → screenshot + app state (page, device, network, user) → `POST /api/feedback/bug-report` → admin page at `/admin/bug-reports`. Auto-diagnosis generates severity (P0-P3), root cause, and a Claude Code prompt with screenshot download command. Status flow: new → reviewed (auto on click) → actioned (added to backlog) / dismissed.

---

## Product Priorities (ordered)

1. **Discover feed** — Social prediction market feed with Higher/Lower games, images, LLM hooks, category filtering, daily challenges, and prediction streaks (`/discover`)
2. **Best aggregated event probabilities** — Probability-first event detail pages with multi-source charts, market maps, player props, and championship path
3. **Cross-source comparison** — Compare across ALL probability sources (sportsbooks, Kalshi, Polymarket, ESPN, stat models)
4. **Related futures** — Season futures, awards, playoff path, and series probability on every event page
5. **Team/league-level odds** — Championship grids + league market sections (series, awards, props)
6. **Multi-platform** — Full parity between web, iOS, and macOS (shared SwiftUI codebase)

**All outstanding work items live in `docs/backlog.md`** (SINGLE SOURCE OF TRUTH).

---

## Quota Guard System

The Odds API quota (5M/month) is the project's most constrained resource. Circuit breaker in `tasks/redis_state.py`:

| Remaining | Mode | Behavior |
|-----------|------|----------|
| >50K | Normal | All sports poll at configured intervals |
| 20K-50K | LIVE_ONLY | Only live games polled |
| <20K | FULL_STOP | All polling stopped except priority sports |

**Sport-tier polling**: Tier 1 (NBA/NHL/MLB/NFL/NCAAB): 32s live, us+us2. Tier 2 (WNBA/EPL/MLS/UCL/MMA/NCAAF): 64s, us. Tier 3 (everything else): 128s, us. Config in `SPORT_POLLING_TIERS`.

---

## Code Style

- **Python**: Type hints, Black formatting, Ruff linting
- **TypeScript**: Strict mode, interfaces in `lib/types.ts`
- **Swift**: `nonisolated struct` for models, `@MainActor` only on async methods

### Frontend Design System (MANDATORY)

The site is **light mode only**. Use design system tokens from `globals.css`: `bg-surface-card`, `text-text-primary`, `text-text-secondary`, `text-text-muted`, `border-surface-border`, `text-accent-live`, `text-accent-brand`, `text-accent-danger`. Never use raw Tailwind dark classes.

### Analytics (MANDATORY)

Every frontend page needs 3 GA4 hooks before any conditional return: `usePageTracking`, `useScrollDepth`, `useEngagementTime`.

---

## Database Schema (Key Tables)

```
events              — Games with teams, scores, EI, win_probability_sources (JSONB)
odds_snapshots      — Historical odds per bookmaker (write-time dedup)
win_prob_snapshots  — Multi-source win probability history
futures_markets     — Championship/award/prop markets (market_tier, event_id, image_url, hook_description)
futures_outcomes    — Individual outcomes within markets
teams               — Team data (ESPN colors/logos, rosters, alternate_names)
team_identity_mapping — Cross-source team identity index
user_predictions    — Higher/Lower guesses (session_id, user_id, market_id, guess, correct)
user_seen_markets   — Tracks which markets a user/session has been shown (dedup in feed)
users               — Firebase Auth users (Google + Apple Sign-In)
```

**Key columns**: `Event.win_probability_sources` (JSONB, all 6 sources), `FuturesMarket.market_tier` (1-5), `FuturesMarket.event_id` (nullable FK — game props linked to events), `FuturesMarket.llm_sport_category`, `FuturesMarket.image_url` (Pexels), `FuturesMarket.hook_description` (LLM-generated).

---

## Sport Key Architecture

`utils/sport_keys.py` is the **single source of truth** for all sport key translation maps. Imports nothing (zero circular-import risk). Key maps: `SPORT_LEAGUE_MAP` (28 entries), `KALSHI_TICKER_TO_SPORT_KEY` (~150 entries), `KALSHI_FUTURES_TICKER_TO_SPORT_KEY` (~250 entries), `SPORT_PREFIX_TO_LLM_CATEGORY` (11 entries).

---

## Gotchas (full list in `docs/gotchas-reference.md`)

1. **Alembic revision IDs must be <=32 characters**
2. **Alembic uses psycopg2, not asyncpg** (intentional for Heroku release phase)
3. **Admin endpoints require mounting** in both `main.py` AND `routes/__init__.py`
4. **`sport_keys.py` imports nothing** — pure data module, zero circular-import risk
5. **`Event.external_id` is nullable** — StatPal creates events without Odds API ID
6. **The Odds API bills per `events * market_types * regions`**, NOT per HTTP call
7. **`Event.sport_id` is an integer FK** to `sports.id`, NOT a string
8. **ORM attribute assignment for JSONB silently fails** — always use SQLAlchemy `update()`
9. **Kalshi `commence_time` is the market RESOLUTION date**, not the game date — use `extract_game_date_from_ticker()`
10. **`llm_sport_category` from Kalshi polling is often wrong** — derive from ticker prefix instead
11. **Phase 2 deadlocks with live polling** — per-market commit + rollback on deadlock detection
12. **iOS models must be `Decodable` not `Codable`** and prefixed with `nonisolated`
13. **iOS ViewModels: NO `@MainActor` on class** — only on individual async methods
14. **Python 3.12+ redundant imports cause UnboundLocalError** — check task files
15. **Safari breaks Firebase Google Auth** — use GIS + backend custom token fallback
16. **`compute_market_tier()` must check name patterns BEFORE `game_prop` category** — Kalshi labels some season markets (division winners, playoff qualifiers) as `category="game_prop"`. Name patterns ("Division Winner", "Make Playoffs") are more reliable than the category field.
17. **Kalshi market backfill must use `status=None`** — live game markets have `status="active"` on Kalshi, not `"open"`. The backfill query for events with 0 nested markets must omit the status filter to pick up active markets.
18. **Kalshi threshold outcomes ("2+", "Aaron Judge: 1+") are OVER probabilities** — don't invert them. Only invert outcomes that explicitly start with "Under" or equal "No".
19. **Don't time-window linked markets** — if the matching task set `event_id`, trust it. Kalshi's `commence_time` is the resolution date (gotcha #9), so a time window on the linked query filters out game totals/spreads. Time windows belong on the FALLBACK query only (unlinked markets matched by team name).
20. **Polymarket midpoint unreliable during blowouts** — when bid/ask spread >15pp, use `lastTradePrice` instead. Skip entirely if `lastTradePrice` is null and no bids exist (zero trading activity = completely stale).
21. **Polymarket game events have nested sub-markets** — A single event ("Magic vs Pistons") contains ~40 sub-markets (moneyline + spread + O/U + player props). Each has its own `condition_id`. The polling task decomposes into separate FuturesMarket rows (not outcomes). NegRisk events (championships) are different — each sub-market IS one candidate.
22. **ORM attribute assignment lost when mixed with Core SQL updates** — Setting `event.field = value` via ORM, then `session.execute(update(Event).where(...).values(...))` via Core SQL can cause the ORM change to silently not persist. Use Core SQL for both. Same class as gotcha #8 but for non-JSONB columns.
23. **`completed_at` is a backend processing timestamp, NOT game-end time** — Can be 30-45 minutes after the last actual game data. For chart domains, use last ESPN data point instead. Don't use for any time-sensitive display.
24. **Kalshi dual markets cause probability oscillation** — Kalshi creates separate "Team A win?" and "Team B win?" markets for the same game. Both get linked to the same Event. Deduplicate by `(event_id, source)` before writing snapshots — one market per event per source.
25. **`CurrentOdds.spread` is unsigned** — The API's `spread` field is just a number (e.g., 8.4) without direction. Use `home_spread` (signed from home team perspective) when available. Fall back to `closestToEvenMargin()` from spreads data, NOT to the unsigned `spread`.
26. **Pexels rate limit is 200 req/hr** — Enrichment script hits this on large batches. Target feed-visible markets first via `enrich_feed_markets.py`, not random `updated_at` ordering.
27. **Never delete a migration file that has already run on Heroku** — The `alembic_version` table stores the current revision ID. If you delete the `.py` file, `alembic upgrade heads` fails with "Can't locate revision," blocking ALL subsequent migrations. The Procfile's `|| echo` makes this silent. Caused a full site outage May 1-2, 2026. CI test `test_alembic.py` guards against this.
28. **Vercel builds run ESLint, not just TypeScript** — `tsc --noEmit` passing does NOT mean the frontend will deploy. Vercel runs `next build` which includes ESLint rules-of-hooks checks. Always run `npm run build` locally before pushing frontend changes. Hooks called after early returns will pass `tsc` but fail `next build`. CI now catches this.
29. **Kalshi market names use abbreviations that fail ILIKE matching** — "A's" doesn't match "Athletics", "Chicago WS" doesn't match "Chicago White Sox". The matching task now prefers ticker-derived team names (mascots) over market name-derived abbreviations. Missing ticker abbreviations (`ATH`, `WSH_MLB`) caused 67 unlinked MLB game markets.
30. **Admin write endpoints need `_check_admin_secret`** — Several admin endpoints (matching override POST/DELETE, eval decision POST, playoffstatus scrape) were shipping without auth. Always add the check for any endpoint that mutates data or burns API quota.
31. **`_is_headline_market` must filter non-US elections** — Polymarket has French, UK, Canadian presidential markets that contain "2028" and "presidential." Without `_NON_US_RE` filtering, the politics hero shows Jean-Luc Mélenchon instead of US candidates. Always require US-specific keywords AND exclude known non-US patterns.
32. **Entertainment `kind` classification: avoid greedy ticker prefixes** — `kxrt` matched any ticker starting with those letters, causing political markets to be classified as Rotten Tomatoes. Use full prefixes (`kxrottentomatoes`) or name-based regex for ambiguous cases.
33. **iPad Stage Manager breaks `connectedScenes.first`** — On iPad with Stage Manager, `UIApplication.shared.connectedScenes.first` can return a background scene. Always filter with `.compactMap { $0 as? UIWindowScene }.first(where: { $0.activationState == .foregroundActive })` and prefer `isKeyWindow`. Applies to Google Sign-In presentation, Apple Sign-In anchor, and any UIKit window access.
34. **Bug report admin status mismatch** — Frontend uses `actioned`/`dismissed` statuses; backend `_VALID_STATUSES` must include them. The PATCH endpoint silently returns 400 if a status isn't in the set, and the frontend doesn't check `res.ok`.
35. **`NWPathMonitor.currentPath` is unsatisfied until started** — Creating `NWPathMonitor()` and immediately reading `.currentPath` always returns `.unsatisfied` (offline). Must call `monitor.start(queue:)` and use `pathUpdateHandler` or `withCheckedContinuation` to get the real network state. All iOS bug reports were showing `network: offline` because of this.
36. **StatPal `season-schedule` puts playoffs in `tournament.week`, not `tournament.match`** — Regular season games are in `tournament.match` (the array our parser originally read). Playoff/postseason games are in `tournament.week` as `[{"stage": "Play Offs", "match": [...]}]`. Both arrays must be parsed in `_extract_match_items()`. Missing this caused ALL playoff games to be silently dropped for months.
37. **StatPal livescores normalizes period to "live"** — StatPal returns game period as the `status` field (e.g., "Q3", "1H", "HT"). The `_normalize_status()` function converts all of these to "live", discarding the period information. Use `raw_status` on `StatPalFixture` to preserve the original value for period markers.
38. **Event merge task must reassign ALL FK tables before delete** — Eight tables have FK references to `events.id`. Only two use `ON DELETE CASCADE` (`espn_snapshots`, `win_prob_snapshots`). The other six (`odds_snapshots`, `score_snapshots`, `scoring_plays`, `odds_aggregated`, `line_movement_analyses`, `futures_markets`) require explicit `UPDATE SET event_id` before the orphan event can be deleted.
58. **Feed probability normalization for independent binary markets** — Kalshi creates separate "Will X win?" binary markets for each candidate. Probabilities can sum well over 100%. Must normalize: `if sum > 1.05: divide each by sum`. Applied in `feed.py` after building `top_outcomes_data`.
59. **Feed staleness threshold: 95% not 97%** — The "effectively resolved" filter originally used leader >= 97%. Lowered to 95% to catch sports futures where a team is eliminated but the market leader is at 90-94%.
60. **Web pin hooks were localStorage-only** — `usePinnedEvents.ts` and `usePinnedFutures.ts` never synced to the server. Pins made on web were invisible on iOS. Fixed: hooks now call server API on every pin/unpin when authenticated.
61. **Celery beat schedule test has an allowlist** — `tests/test_tasks_wiring.py` has `EXPECTED_ENTRIES` set that must include every entry in `celery_app.conf.beat_schedule`. Adding a new scheduled task without updating this set causes CI failure.
62. **Gmail API OAuth refresh tokens via Google Workspace** — Using OAuth2 refresh token (not service account) to send email as `bugs@bainluck.com`. The OAuth Playground redirect URI must NOT have a trailing slash. Config vars: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_SENDER_EMAIL`.
63. **Apple Sign-In audience differs between web and iOS** — Web uses `APPLE_SERVICES_ID` (`com.bainluck.web`) as JWT audience; iOS native uses the app bundle ID (`com.bainluck.Bain-Luck`). The `verify_apple_id_token()` call must accept BOTH as valid audiences. PyJWT's `audience` parameter natively accepts a list. This caused iOS Apple Sign-In to silently 401 for months.
64. **Independent binary market probabilities must be normalized everywhere** — Kalshi creates separate "Will X win?" markets for each candidate. Raw probabilities sum well over 100%. Normalization (`if sum > 1.05: divide each by sum`) is applied in `feed.py`, AND must also be applied in `politics.py` nominee lists and any other ranked display of independent binary markets. Missing this on the Politics page caused Fujimori to show at 98.8%.
65. **Game-markets `period` field must come from the backend** — Kalshi's `_build_game_market_name()` strips period indicators from market names ("2nd Half Total: X at Y" becomes "X at Y"). Frontend/iOS cannot reliably derive 1H vs 2H from the name. Backend must set `period` from the ticker prefix via `_extract_period_from_ticker()`. Without this, 2nd half maps silently disappear.
66. **Polymarket placeholder outcomes have `outcomePrices=["1","0"]`** — Polymarket creates reserved-slot sub-markets ("Player B", "Player S") before real candidates are announced. These have 100% probability and zero trading activity. Filter with `_is_placeholder_outcome()`: name matches "Player [A-Z]" single letter, OR price ≥0.995 with no bestBid and no lastTradePrice.
67. **iOS Decodable models must use `Double` for probability fields** — Backend `round(prob * 100, 1)` returns floats like `72.5`, not integers. Using `Int` in the iOS Decodable model causes the entire response to fail to decode. Always use `Double` (or `Double?` for nullable fields) for any probability, percentage, or numeric score from the API.
68. **PKCanvasView annotation coordinates require explicit frame sizing** — Using `.frame(maxHeight: 300)` without width constraint makes the canvas wider than the rendered image. Touch coordinates then include dead space, and flattening uses wrong scale factors. Always size the canvas to match the image's aspect ratio exactly, disable scroll, and use independent scaleX/scaleY with `UIScreen.main.scale` for retina.
69. **Rapid git pushes crash Heroku** — Each push to master triggers a separate Heroku deploy. Overlapping release phases (import validation + Alembic) can exhaust resources and crash the dyno. Batch commits into single pushes, or use the CI deploy job (`concurrency: cancel-in-progress: true`) which serializes deploys. Caused a 30-minute outage May 15.

---

## CI Test Coverage

| Test File | What It Catches | Added |
|-----------|----------------|-------|
| `tests/test_startup.py` | Import errors that crash the web dyno | Original |
| `tests/test_tasks_wiring.py` | Missing/duplicate Celery beat schedule entries | Apr 2026 |
| `tests/test_alembic.py` | Multiple heads, deleted migrations, orphaned revisions | May 7 |
| `.github/workflows/ci.yml` (frontend-build) | ESLint + TypeScript errors blocking Vercel | May 7 |
| `tests/integration/test_route_feed_scoring.py` | Feed scoring, ordering, event/futures data shape with seeded data | May 8 |
| `tests/integration/test_route_events_seeded.py` | Event detail response shape, game-markets sections, related futures | May 8 |
| `tests/integration/test_route_category_pages.py` | Weather, politics, entertainment, economics API response shapes | May 13 |
| `tests/integration/test_route_futures_browse.py` | Futures browse, categories, movers, compare response shapes | May 15 |
| `tests/integration/test_route_market_moves.py` | Market moves endpoint response shape and param validation | May 15 |
| `tests/test_politics_normalization.py` | Politics probability normalization for independent binary markets | May 15 |
| `tests/test_rate_limit.py` | Rate limiting middleware: thresholds, auth exemption, Redis fallback | May 15 |

---

## Session Startup: Health Check

At the start of every session, run a quick production health scan (~10 seconds):

```bash
source .env.claude

# 1. Sentry — new/high-frequency errors since last session
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://us.sentry.io/api/0/projects/alexander-bain/bainluck/issues/?query=is:unresolved&limit=5&sort=date" \
  | python3 -c "import json,sys; [print(f'  {i[\"shortId\"]:12s} {i[\"count\"]:>5s} evts  {i[\"title\"][:60]}') for i in json.load(sys.stdin)]"

# 2. Heroku — dyno status + DB connections
heroku apps:info -a bainluck 2>&1 | grep "Dynos:"
heroku pg:info -a bainluck 2>&1 | grep "Connections:"

# 3. CI — last 3 runs
gh run list --repo alexander-bain/bainluck --limit 3

# 4. Celery queue health — background queue > 50 = problem
curl -s "https://api.bainluck.com/api/admin/celery-debug?secret=$ADMIN_TOKEN" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); q=d.get('queue_lengths',{}); bg=q.get('background',0); print(f'  Celery queues: bg={bg} rt={q.get(\"realtime\",0)}'); bg>50 and print('  ⚠️  BACKGROUND QUEUE BACKED UP — purge via POST /api/admin/celery-purge-background')"

# 5. is_winner backfill coverage — all sources should be >95%
curl -s "https://api.bainluck.com/api/admin/backfill-winners/status?secret=$ADMIN_TOKEN" \
  | python3 -c "import json,sys; [print(f'  {s[\"source\"]:12s} {round(100*s[\"has_winner\"]/max(s[\"resolved\"],1),1)}% ({s[\"has_winner\"]}/{s[\"resolved\"]})') for s in json.load(sys.stdin)['sources']]"
```

**Thresholds for immediate action:**
- Sentry issue >100 events in 24h → triage now
- Background queue >50 → purge + investigate (see `docs/backlog.md` Celery workstream)
- is_winner coverage <80% on any source → run `POST /api/admin/backfill-winners/probability-only`

**Available tools:** Heroku CLI (`heroku`), Sentry API (`$SENTRY_AUTH_TOKEN`), GitHub CLI (`gh`). All authenticated and working as of April 21, 2026.

---

## Quality Audit (mandatory practice)

When fixing ANY data quality, matching, or display issue:
1. Run audit BEFORE: `python3 scripts/audit_matching_quality.py --skip-llm --save`
2. Make fix
3. Add a check that catches this class of issue
4. Run audit AFTER: `python3 scripts/audit_matching_quality.py --skip-llm --compare --save`

---

## Parallel Work Protocol

- **Green** — iOS, docs, new test files, new utility files
- **Yellow** — Different routes, different tasks
- **Red** — Shared models, migrations, same route/task file
- **Never parallelize**: Two Alembic migrations, two sessions on same route file, two sessions on models.py

---

## Quick Reference

| What | Where |
|------|-------|
| Discover feed (default) | https://bainluck.com (also /discover) |
| Sports feed | https://bainluck.com/sports |
| Prediction stats | https://bainluck.com/discover/stats |
| Admin dashboard | https://bainluck.com/admin |
| Weather page | https://bainluck.com/weather |
| Politics page | https://bainluck.com/politics |
| Entertainment page | https://bainluck.com/entertainment |
| Economics page | https://bainluck.com/economics |
| Calibration page | https://bainluck.com/calibration |
| Calibration API | `GET /api/calibration` (public, 1h cache) |
| Backfill status | `GET /api/admin/backfill-winners/status` |
| Privacy policy | https://bainluck.com/privacy |
| Weather API | `GET /api/weather/{featured,cities,rain,events,climate,wildcards}` |
| Politics API | `GET /api/politics` |
| Entertainment API | `GET /api/entertainment` |
| League markets API | `GET /api/leagues/{sport_key}` (series, awards, props by league) |
| Hook coverage | `GET /api/admin/hook-coverage` |
| Grid health audit | `GET /api/admin/audit/all?secret=$ADMIN_TOKEN` |
| Link rate health | `GET /api/admin/prediction-markets/link-rate` |
| API docs | https://api.bainluck.com/docs |
| Backlog | `docs/backlog.md` |
| Shipped features | `docs/completed-features.md` |
| Architecture | `docs/architecture-reference.md` |
| Gotchas (full) | `docs/gotchas-reference.md` |
| Quality audit | `docs/quality-audit.md` |
| Hill-climb guide | `docs/hill-climb-guide.md` |
