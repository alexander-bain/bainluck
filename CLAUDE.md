# CLAUDE.md - Project Guidelines for Claude Code

## Project Overview

**Bain Luck** is a visual-first sports odds experience that translates betting markets into intuitive win probabilities. Users see "60% vs 40%" instead of "-150 / +130".

**North Star**: The cleanest odds visualization tool on the internet.
**Target User**: Casual sports fans watching games who want context, not betting advice.
**Live Site**: https://bainluck.com

---

## Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+) | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis | Heroku Redis |
| Frontend | Next.js 14 (React) | Vercel |
| iOS App | SwiftUI | TestFlight (active development) |

**Key External Services:**
- **The Odds API** — Sports odds data (~$119/mo, 5M monthly quota — monitor closely)
- **Kalshi** — Prediction market data (free, API key required)
- **Polymarket** — Prediction market data (free, no API key)
- **StatPal** — Schedules, rosters, injuries, play-by-play (~$99/mo)
- **DataGolf** — Golf predictions, live in-play probabilities, leaderboards (~$30/mo)
- **MLB Stats API** — Live baseball win probability (free, no key)
- **ESPN** — Team colors, logos, live game data, win probability (free, undocumented)
- **TMDB** — Movie posters/headshots for Oscars page (free, Bearer token)
- **OpenAI** — GPT-4o-mini for LLM classification (~$5/mo)
- **Firebase Auth** — Google + Apple Sign-In, personalization (free tier)
- **Google Analytics 4** — User analytics (free)

---

## Project Structure

```
bainluck/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── models/models.py     # SQLAlchemy models (26 models)
│   │   ├── routes/              # API endpoints
│   │   │   ├── events.py        # Events API (search, detail, history, related futures)
│   │   │   ├── feed.py          # Unified feed (events + futures ranked)
│   │   │   ├── futures.py       # Championship odds, probability timeline
│   │   │   ├── playoffs.py      # Championship grids
│   │   │   ├── golf.py          # Golf category landing page
│   │   │   ├── march_madness.py # NCAA Tournament landing pages (men's + women's)
│   │   │   ├── oscars.py        # Oscars landing page
│   │   │   ├── oscars_pool.py   # Oscars pool game (private prediction pools)
│   │   │   ├── auth.py          # Auth endpoints
│   │   │   ├── user.py          # User data (pins, teams, onboarding, preferences)
│   │   │   ├── admin.py         # Admin/debug endpoints (~7000 lines)
│   │   │   ├── market_moves.py  # "Market Was Wrong" endpoint
│   │   │   ├── sports.py        # Sports listing
│   │   │   └── health.py        # Health check
│   │   ├── services/            # External API clients
│   │   │   ├── odds_api.py, kalshi_api.py, espn_api.py, mlb_api.py
│   │   │   ├── statpal_api.py, polymarket_api.py, datagolf_api.py
│   │   │   ├── firebase_auth.py, llm.py, team_identity.py, database.py
│   │   ├── config/
│   │   │   ├── win_prob_sources.py  # Win probability source registry
│   │   │   └── league_configs.py   # Championship grid configurations
│   │   ├── tasks/               # Celery tasks (23 modules)
│   │   │   ├── __init__.py      # Celery app, task definitions, beat schedule
│   │   │   ├── config.py, base.py, snapshots.py, redis_state.py
│   │   │   ├── odds_polling.py, excitement_index.py, futures.py
│   │   │   ├── kalshi.py, espn_sync.py, sports.py, retention.py
│   │   │   ├── roster_sync.py, team_linking.py, prediction_market_matching.py
│   │   │   ├── matching_audit.py, mlb_sync.py, statpal_sync.py
│   │   │   ├── polymarket.py, datagolf.py, taxonomy.py
│   │   │   ├── march_madness.py, team_identity_backfill.py
│   │   └── utils/               # Pure logic modules (24 modules)
│   │       ├── excitement_index.py, highlights.py, odds_math.py
│   │       ├── aggregation.py, win_probability.py, odds_filtering.py
│   │       ├── futures_categorization.py, futures_highlights.py
│   │       ├── line_movement.py, personalization.py
│   │       ├── prediction_market_matching.py, series_probability.py
│   │       ├── market_grouping.py, market_classification.py
│   │       ├── sport_keys.py, team_linking.py, name_normalization.py
│   │       ├── event_taxonomy.py, league_classification.py
│   │       ├── feed_reasons.py, pulse.py, seed_matchups.py
│   │       └── tournament_stages.py
│   ├── alembic/                 # Database migrations
│   └── tests/                   # 2747 pytest items
├── frontend/
│   ├── app/                     # Next.js app router (30+ pages)
│   │   ├── sport/               # Sport hierarchy pages
│   │   │   ├── page.tsx         # /sport — all sports index
│   │   │   ├── [sport]/page.tsx # /sport/{sport} — sport hub (leagues + showcase events)
│   │   │   └── [sport]/[league]/page.tsx  # /sport/{sport}/{league} — league showcase (grid + evolution + tournaments)
│   ├── components/              # React components
│   │   ├── TournamentProgressionTable.tsx  # Championship grid with inline data bars
│   │   ├── TournamentCard.tsx   # Golf/cup tournament cards (includes CupCard variant)
│   │   ├── EvolutionView.tsx    # Evolution chart container (time ranges, stage pills, sidebar)
│   │   ├── EvolutionChart.tsx   # Recharts line chart for probability timelines
│   │   └── EvolutionLeaderboard.tsx  # Sidebar with team/player selection
│   ├── lib/                     # API client, types, utilities
│   └── hooks/                   # Custom React hooks
├── ios/Bain Luck/               # iOS app (SwiftUI, 54 Swift files)
│   └── Bain Luck/
│       ├── Views/               # Screen-level views (16 views)
│       ├── Components/          # Reusable UI components
│       ├── Models/              # Data models (Decodable)
│       └── Services/            # APIClient, AuthManager, etc.
└── docs/                        # Documentation (23 docs)
```

---

## Key URLs

| Environment | URL |
|-------------|-----|
| Production Frontend | https://bainluck.com |
| Production API | https://api.bainluck.com |
| API Docs | https://api.bainluck.com/docs |
| Admin Dashboard | https://bainluck.com/admin |

**Heroku App Name:** `bainluck` (for CLI: `heroku logs -a bainluck`)

---

## Development Workflow

Development happens primarily through **Claude Code**. No local dev environment needed.

- **Backend** and **frontend** auto-deploy from `master` via Heroku and Vercel
- **Both auto-deploy from GitHub**: `git push origin master` is sufficient (Heroku auto-deploy confirmed working April 2, 2026)
- **Database migrations**: `alembic revision --autogenerate -m "description"`, applied on Heroku release
- **Backend tests**: `cd backend && python3 -m pytest tests/ -v`
- **Frontend tests**: `cd frontend && npx jest`

### Querying the Production API
```bash
curl "https://api.bainluck.com/api/events?sport=americanfootball_nfl"
curl "https://api.bainluck.com/api/events/search?q=celtics"
curl "https://api.bainluck.com/api/admin/ei/status?secret=$ADMIN_SECRET"
```

---

## Environment Variables

### Backend (Heroku Config Vars)
`ODDS_API_KEY`, `KALSHI_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `ADMIN_SECRET`, `SENTRY_DSN`, `STATPAL_API_KEY`, `DATAGOLF_API_KEY`, `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `APPLE_SERVICES_ID`

### Frontend (Vercel)
`NEXT_PUBLIC_API_URL` = `https://api.bainluck.com`, `NEXT_PUBLIC_FIREBASE_*` (API_KEY, AUTH_DOMAIN, PROJECT_ID), `NEXT_PUBLIC_GA_MEASUREMENT_ID`, `NEXT_PUBLIC_TMDB_API_KEY`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID`

---

## Key Features (Summary)

For detailed documentation of each feature, see `docs/feature-reference.md`.

| Feature | Key Files | Notes |
|---------|-----------|-------|
| **Excitement Index (EI)** | `utils/excitement_index.py`, `EIBadge.tsx` | 1-100 score using GEI formula. Recalc: `POST /api/admin/ei/recalculate` |
| **Highlights/Feed Ranking** | `utils/highlights.py`, `utils/feed_reasons.py` | 4-tier league system, Level 1+2 scoring, personalization |
| **Multi-Source Win Probability** | `config/win_prob_sources.py`, `OddsChart.tsx` | Betting odds, ESPN, Kalshi, Polymarket, MLB, stat model, DataGolf |
| **Prediction Market Matching** | `utils/prediction_market_matching.py`, `tasks/prediction_market_matching.py` | Links Kalshi/Polymarket game markets to events |
| **Auth & Personalization** | `firebase_auth.py`, `utils/personalization.py` | Google + Apple Sign-In, onboarding, team favorites, sport affinities, personalized feed scoring |
| **Championship Grids** | `config/league_configs.py`, `routes/playoffs.py`, `TournamentProgressionTable.tsx` | NBA, NHL, NCAA, Golf grids with Kalshi noise filter + monotonicity enforcement. Inline data bars (MoneyPuck-style) with sqrt scaling. Per-column `market_id` for evolution chart stage switching |
| **March Madness** | `routes/march_madness.py`, `tasks/march_madness.py` | NCAA Tournament pages (men's + women's) with bracket data, upset detection, seed matchups |
| **Golf Integration** | `routes/golf.py`, `tasks/datagolf.py`, `services/datagolf_api.py` | DataGolf live in-play probabilities, leaderboards, schedule across 5 tours. Men's/women's major separation via `_womens` key suffix |
| **Oscars Pool** | `routes/oscars_pool.py`, `routes/oscars.py` | Private prediction pools with odds-adjusted scoring |
| **Related Futures** | `routes/events.py` (related-futures), `RelatedFutures.tsx` | "Bigger Picture" — championship/award/stat prop context |
| **Sport Page Hierarchy** | `app/sport/`, `routes/sports.py`, `sport_keys.py:SPORT_HIERARCHY` | 3-level URL: `/sport/{sport}` hub → `/sport/{sport}/{league}` showcase → event detail. League pages embed championship grid + evolution chart with stage pills |
| **Evolution Chart** | `EvolutionView.tsx`, `EvolutionChart.tsx`, `EvolutionLeaderboard.tsx` | Multi-outcome probability timeline. Time ranges (Season/7d/24h/Today). Stage pills for grid columns (Win/Conference/Playoffs). `entityLabel` prop for Teams vs Players. `keepPreviousData` prevents blank on range switch |
| **Cup Cards** | `TournamentCard.tsx:CupCard` | Head-to-head layout for Ryder Cup, Presidents Cup etc. — teams left/right with colored probability bar |
| **Snapshot Retention** | `tasks/retention.py` | Pure SQL collapse, constant memory. Write-time dedup |
| **Canonical Identity** | `services/team_identity.py`, `utils/sport_keys.py` | 5-step resolution cascade, supplements fuzzy matching |
| **Name Normalization** | `utils/name_normalization.py` | Single source of truth for team name matching. City abbreviation expansion (LA, NY, OKC, etc.) |
| **Market Grouping** | `utils/market_grouping.py` | Source hierarchy + threshold variant detection |
| **Taxonomy Tags** | `utils/event_taxonomy.py`, `tasks/taxonomy.py` | Deterministic event_tags and market_tags computed every 2 min |
| **Futures Highlights** | `utils/futures_highlights.py` | Interestingness scoring (0-100) for futures in the unified feed |
| **Admin/Ops Dashboard** | `frontend/app/admin/page.tsx`, `routes/admin.py` | Quota tracking, source coverage, DB storage, worker metrics, task activity |
| **Quota Guard** | `tasks/redis_state.py` | Circuit breaker for Odds API: LIVE_ONLY (50K) → FULL_STOP (20K) with conservation mode |

---

## iOS App Patterns

**Critical patterns** (violating these causes build errors):
- All model structs: `nonisolated struct X: Decodable, Sendable` (NOT `Codable`, NOT without `nonisolated`)
- ViewModels: `final class XViewModel: ObservableObject` — NO `@MainActor` on class, only on async methods
- API client uses `snake_case` JSON decoding via `keyDecodingStrategy = .convertFromSnakeCase`
- SwiftUI Charts for odds chart (`import Charts`)
- SPM dependencies: `GoogleSignIn-iOS`, `firebase-ios-sdk`

---

## API Patterns

```python
# Probabilities as decimals (0.0-1.0)
{"home_probability": 0.65, "away_probability": 0.35}

# Timestamps in ISO 8601
{"commence_time": "2026-02-03T19:00:00+00:00"}

# EI (serves both "ei" and "pulse" keys for backward compat)
{"ei": {"score": 75, "label": "Exciting", "metadata": {"raw_ei": 3.45, "lead_changes": 4}}}
```

**Event Statuses:** `scheduled`, `live`, `completed`, `closed`

---

## Database Schema (Key Tables)

```
events              — Games with teams, scores, EI, event_tags (JSONB)
odds_snapshots      — Historical odds per bookmaker (write-time dedup)
odds_aggregated     — Pre-aggregated odds for retention
win_prob_snapshots  — Multi-source win probability history
espn_snapshots      — ESPN live data snapshots (CASCADE delete)
score_snapshots     — Score history per event
scoring_plays       — Individual scoring events (plays)
futures_markets     — Championship/award/prop markets (market_tags JSONB)
futures_outcomes    — Individual outcomes within markets
futures_odds_snapshots — Futures probability history
teams               — Team data (ESPN colors/logos, rosters)
team_identity_mapping — Cross-source team identity index
users               — Firebase UID, email, profile
user_preferences    — Sport affinities, onboarding state
user_favorites      — Team relationships (follow/local/alma_mater/rival)
user_pins           — Server-side pin storage (uses target_id, NOT event_id)
line_movement_analyses — Cached LLM line movement explanations
matching_overrides  — Admin-curated matching overrides for grids
ei_percentiles      — EI percentile lookup table
oscars_pools/members/picks — Oscars pool game data
tournaments/tournament_odds — Tournament tracking
venues              — Venue data
```

**Key identity columns:** `Event.statpal_fixture_id` (nullable `external_id` for schedule-first), `Event.commence_time_source`, `Team.statpal_team_id`, `Event.raw_ei` / `ei_metadata`, `Event.event_tags` (JSONB)

**Important FK note:** Deleting events requires clearing FKs in: `scoring_plays`, `odds_snapshots`, `odds_aggregated`, `score_snapshots`, `espn_snapshots`, `win_prob_snapshots`, `line_movement_analyses`, `futures_markets` (chain through outcomes/odds). `user_pins` uses `target_id` not `event_id`.

---

## Sport Key Architecture

`utils/sport_keys.py` is the **single source of truth** for all sport key translation maps. It imports nothing from the codebase (zero circular-import risk).

Key maps (10 dicts + 7 accessor functions):
- `SPORT_LEAGUE_MAP` (28 entries) — Odds API key → ESPN (sport, league) tuple
- `ESPN_SPORT_MAPPING` (25 entries) — Odds API key → ESPN path string
- `KALSHI_TICKER_TO_SPORT_KEY` (38 entries) — Kalshi ticker prefix → Odds API sport key
- `KALSHI_TICKER_TO_DISPLAY_LABEL` (27 entries) — ticker → display name
- `SPORT_PREFIX_TO_LLM_CATEGORY` (11 entries) — prefix → LLM category
- `LLM_CATEGORY_TO_SPORT_PREFIX` (16 entries) — reverse mapping

Kalshi-only sports (no Odds API coverage): `esports`, `icehockey_ncaa`, `icehockey_ahl`, `boxing_boxing`, various regional soccer/basketball leagues.

---

## Code Style

- **Python**: Type hints, Black formatting, Ruff linting
- **TypeScript**: Strict mode, interfaces in `lib/types.ts`
- **Swift**: `nonisolated struct` for models, `@MainActor` only on async methods
- **Commits**: Descriptive messages, reference session URLs

### Frontend Design System (MANDATORY)

The site is **light mode only**. Never use dark Tailwind color classes. Always use the design system tokens defined in `globals.css`:

| What | Use | NEVER use |
|------|-----|-----------|
| Page background | (inherits from body) | `bg-gray-950`, `bg-gray-900`, `bg-black` |
| Card background | `bg-surface-card` | `bg-gray-800`, `bg-gray-900` |
| Elevated surface | `bg-surface-elevated` | `bg-gray-800/50` |
| Primary text | `text-text-primary` | `text-white` |
| Secondary text | `text-text-secondary` | `text-gray-300`, `text-gray-400` |
| Muted text | `text-text-muted` | `text-gray-500`, `text-gray-600` |
| Borders | `border-surface-border` | `border-gray-800`, `border-gray-700` |
| Live accent | `text-accent-live` / `bg-accent-live/15` | `text-green-400`, `bg-green-500/20` |
| Brand accent | `text-accent-brand` | `text-blue-400` |
| Danger | `text-accent-danger` | `text-red-400` |

When creating new pages or components, copy the color patterns from existing pages (e.g., `app/page.tsx`, `app/playoffs/[sport]/page.tsx`). Never default to dark mode.

### Analytics Instrumentation (MANDATORY)

Every frontend page MUST include 3 GA4 hooks before any conditional return:
```tsx
usePageTracking({ pageType: 'my_page_type', pageTitle: 'Page Title' });
useScrollDepth({ pageType: 'my_page_type' });
useEngagementTime({ pageType: 'my_page_type' });
```
Add page type to `frontend/lib/analytics/types.ts` (3 places).

---

## Deployment

Both backend and frontend auto-deploy from `master`.

- **Backend (Heroku)**: Auto-deploys from GitHub `master` — runs `alembic upgrade head` on release
- **Frontend (Vercel)**: Auto-deploys from GitHub `master` (auto-preview for PRs)

---

## Quota Guard System

The Odds API quota (5M/month) is the project's most constrained resource. A circuit breaker in `tasks/redis_state.py` prevents exhaustion:

| Remaining | Mode | Behavior |
|-----------|------|----------|
| >50K | Normal | All sports poll at configured intervals |
| 20K-50K | LIVE_ONLY | Only live games polled, no discovery/futures |
| <20K | FULL_STOP | All polling stopped EXCEPT priority sports (NBA, MLB, NCAAB) in conservation mode |

**Conservation mode** (FULL_STOP + priority sport): h2h only, US region only, 10-min interval, live games only.

The guard auto-expires on `QUOTA_GUARD_EXPIRY` (set to billing cycle reset date). Update this date each month.

**Billing model**: The Odds API charges per `events_returned * market_types * regions` per HTTP call, NOT per call. Requesting h2h + spreads + totals with us + us2 regions costs 6x per event vs h2h-only with us-only.

**Tier-aware polling** (implemented April 2026):
| Tier | Window | Markets | Regions | Cost vs Full |
|------|--------|---------|---------|-------------|
| Live | In-progress | h2h,spreads,totals | us,us2 | 1x (baseline) |
| Soon | 0-2h pre-game | h2h,spreads,totals | us | ~0.5x |
| Later | 2-6h pre-game | h2h | us | ~0.17x |

**Adaptive slowdown**: Per-sport Redis counter tracks consecutive unchanged polls. After 3 unchanged → 5min interval. After 6 unchanged → 10min interval. Resets instantly when odds change. Live tier exempt.

---

## Product Priorities (ordered)

1. **Best aggregated event probabilities** — Best way to see event probabilities aggregated across sportsbooks
2. **Odds vs algorithms** — Best way to compare event probabilities to algorithm probabilities (win probability models)
3. **Cross-source comparison** — Best way to compare across ALL probability sources (DataGolf, MoneyPuck, FanGraphs, etc.)
4. **Related futures** — Best way to see related futures, both out of curiosity and to understand 2nd-order impact
5. **Team/league-level odds** — Best way to compare odds for entire teams or leagues
6. **Discovery & engagement** — Best way to discover and interact with events with interesting odds (possibly beyond sports; possibly as a game)

### Operational (April 2026)
- **Quota management** — Conservation mode deployed. Quota resets monthly on the 1st. Update `QUOTA_GUARD_EXPIRY` in `redis_state.py` each cycle.
- **Data quality** — Reclassified 4078 misclassified events, purged 195 orphan pm_ events, expanded Kalshi ticker mappings (18→38)

### Golf (April 2026)
- **Golf product strategy**: `docs/golf-product-strategy.md`
- **Evolution chart shipped**: Interactive line chart with position toggle, time range, fullscreen, player sidebar
- **Tournament detail page**: `/categories/golf/tournaments/[slug]` — leaderboard grid, bubble watch, evolution chart
- **Masters data quality (April 13 audit)**: Evolution chart has 0 snapshots (no history during R1-R4). Leaderboard shows Rory as winner but tournament `status` is null. LIVE badge stale. ATP Monte-Carlo "Masters" markets contaminating golf. X-axis duplication and missing round markers unverifiable (no chart data to render).

### Backlog (SINGLE SOURCE OF TRUTH)

All outstanding items live here. `TODO.md` is archived; `trip-recap-and-next-steps.md` is historical reference only.

**Architecture (planned April 13, 2026 — see `plans/ancient-humming-blossom.md`)**
- **B1: Site navigation** — Move from `/playoffs/[sport]` to `/[sport]/[league]` hierarchy. Team sports get grid+games+futures tabs. Individual sports (golf, tennis) get tour hub → tournament detail. Sport hub pages list sub-leagues.
- **B2: League context service** — Extract matching logic from `playoffs.py` into reusable `market_discovery.py` + `team_resolution.py`. Cache per-league team standings in Redis. Enrich event detail API with dynamic championship/playoff probabilities. Orphaned event detection.
- **B3: Eval page v2** — Group by market (not per-team). Three card types: market-column assignment, source disagreement, interesting futures. Decisions flow downstream to grid builder + feed ranking. Gamification phase 2 (points, levels, leaderboard).
- **B4: Trade volume** — Store Kalshi/Polymarket volume on `FuturesMarket` (5 nullable columns). Use for feed ranking, grid confidence weighting, eval context. Internal signal only — never user-facing.

**HIGH-PRIORITY follow-ups**
- **Market tier tagging in Kalshi/Polymarket tasks** — Most `FuturesMarket` records have `market_tier=NULL`, making it impossible to efficiently filter championships from game props. The Kalshi/Polymarket tasks should use `MarketMatchingRule` from `league_configs.py` to set `market_tier` during upsert. This unblocks Related Futures showing awards, win totals, and game props without massive ILIKE scans.
- **Evolution chart: combined probability trend** — Chart currently shows single-source data; grid shows merged/grouped. Chart should show merged probability trend. Requires time-series computation of aggregate — data pipeline question.
- **`/[sport]/[league]/[team]` entity pages** — `/basketball/nba/celtics` aggregates all content for a team: games, futures, related markets, championship timeline. Good for SEO + My Stuff integration.
- **Golf round markers on charts** — R1/R2/R3/R4 start times as vertical markers. Minimum: midnight each tournament day. Ideal: actual start-of-play.
- **Golf LIVE badge fix** — Date-based validation, not just leaderboard existence. Currently false-positive for completed tournaments.
- **Live tournament Kalshi/Polymarket polling** — Futures polls run every 4h (Kalshi) / 1h (Polymarket), way too slow for live golf tournaments. Game-level `poll_live_prediction_markets` runs every 2min but only covers event-matched markets, not tournament futures. Need a "live tournament" polling mode: detect active tournament via DataGolf leaderboard, poll its Kalshi/Polymarket markets every 5-10 min during play. Same pattern could apply to any high-interest futures (NBA playoffs, Super Bowl week).

**Golf data quality (still open)**
- Tour misclassification (Hainan = Asian Tour, not PGA Tour)
- "Augusta National Invitational" ghost tournament
- Categories page chart showing "Yes" (Polymarket binary, not Kalshi player market)
- "To win" label on card probabilities
- H2H matchups on tournament detail (stop filtering `" vs "` markets in `golf.py` ~L608)
- Make Cut column on tournament detail page
- ATP Monte-Carlo "Masters" markets leaking into golf data

**Data quality / Blending**
- **Freshness-weighted source blending** — Stale prediction market prices weighted equally with fresh model data. Need time-decay weighting. Design notes in `.claude/projects/-Users-bain-bainluck/memory/project_freshness_blending.md`.
- Sport-specific EI normalization (different ceilings per sport)

**Sport/League pages**
- Win totals column in championship grid
- Awards/props cards on league pages (MVP, DPOY, ROY)
- Season state indicators on evolution chart (Trade Deadline, All-Star Break, etc.)
- Team landing pages (clickable from grid team names)
- SEO: sitemap, structured data for `/sport/*` routes

**DS/Analytics infrastructure**
- Add `ended_at`, `final_home_probability`, `event_results`, `season` columns to events
- Denormalize `sport_group` on events
- Normalize `ei_metadata` from Text to proper columns
- Create `v_completed_events` analytical view
- First analysis: "Who's Right?" Brier score source accuracy

**Features**
- TV Mode v2 (prototype at `docs/tv-mode-prototype.jsx`)
- Non-sports categories: audit existing markets, weather visualization, politics timelines
- "The Market Was Wrong" v2 — AI narrative + personalization

**Housekeeping**
- **May 1, 2026**: Delete `frontend/_to-delete/` if nothing broke
- **May 1, 2026**: Delete `docs/archive/` if nothing referenced
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`

See `docs/completed-features.md` for shipped features.
See Ideas Backlog in `docs/PRD.md` for longer-term ideas.

---


## Probability Aggregation (Core Data Flow)

The BainLuck aggregated probability is the product's most important output. Everything flows toward it.

### `compute_aggregate_probability()` (`utils/aggregation.py`)

Three-tier fallback:
1. **`Event.win_probability_sources`** (JSONB) — multi-source weighted average
2. **`Event.espn_win_prob_home`** — ESPN-only fallback
3. **`Event.opening_home_probability`** — pre-game opening odds

Source weights: `betting: 3.0, espn: 1.5, stat_model: 1.0, kalshi: 0.8, polymarket: 0.8, mlb: 0.8`

### Data Flow

```
Sources (ESPN, Kalshi, Polymarket, Odds API, stat model, DataGolf, MLB)
  → win_prob_snapshots table (per-source, timestamped)
  → Event.win_probability_sources JSONB (latest per-source)
  → compute_aggregate_probability() (weighted average)
  → Feed cards, event detail hero, OddsChart
```

### Feed vs Event Detail API

Both MUST use `compute_aggregate_probability()`. The feed API (`routes/feed.py`) calls `_compute_aggregate_probability()` at line ~500. The event detail API (`routes/events.py`) returns `current_odds` from odds_snapshots with a fallback to `compute_aggregate_probability()`. If you add a new probability display, always use the aggregate — never raw odds_snapshots alone.

### Frontend Probability Display

- **Live events**: Show current aggregate probability
- **Finished events**: Show opening odds (`opening_home_probability`), fall back to current aggregate. Never show 100%/0% completion probabilities — skip chart values >95%/<5% for finished events.
- **FeedCard.tsx**: `displayHomeProb` logic handles this (lines ~274-276)

---

## Source-Agnostic Resilience

The system MUST work when any single source goes dark. This was validated during March 2026 Odds API quota exhaustion (10/5M remaining for 4 days).

### Design Principles

1. **Events don't require Odds API** — StatPal creates events with `sport_id` FK but `external_id=None`. These are fully functional.
2. **Prediction market matching works by team name + time** — `_find_matching_event()` uses ILIKE on team names + commence_time window. No `external_id` required on the event.
3. **ESPN/StatPal data flows independently** — Score snapshots, ESPN history, and win_prob_snapshots from ESPN all write independently of Odds API polling.
4. **Chart domains derive from game timeline** — `commenceTime` for start, last ESPN/score data timestamp for end. Charts NEVER depend solely on odds data for their time range.

### What Each Source Provides

| Source | Provides | Independent? |
|--------|----------|-------------|
| Odds API | Sportsbook odds, event discovery | No — quota-constrained |
| ESPN | Win prob, scores, periods, team data | Yes — free, no quota |
| StatPal | Schedules, play-by-play, rosters | Yes — separate API key |
| Kalshi | Prediction market prices, game markets | Yes — free |
| Polymarket | Prediction market prices | Yes — free, no key |
| DataGolf | Golf predictions, leaderboards | Yes — separate API key |

---

## Chart Architecture (Event Detail Page)

### OddsChart (`components/OddsChart.tsx`)
- Multi-source win probability chart (betting, ESPN, Kalshi, Polymarket, stat model)
- Reports its rendered domain via `onRenderedDomain` callback → `oddsChartDomain` state
- Period boundaries (Q1, HT, Q3, etc.) rendered as vertical `ReferenceLine` markers

### ScoreDifferentialChart (`components/ScoreDifferentialChart.tsx`)
- Projected spread (from sportsbook odds) vs actual score difference
- Domain derived from **game timeline**: `commenceTime` for start, last data timestamp for end
- `chartEndTime` from OddsChart can extend (never shrink) the domain for live games
- Also shows Kalshi/Polymarket implied spreads as flat lines

### Period Boundaries (`lib/periodMarkers.ts`)
- `derivePeriodBoundaries()` extracts game state transitions from ESPN/win_prob/scoring_plays
- `normalizePeriodLabel()` converts "6:55 - 1st Quarter" → "Q1", "Halftime" → "HT", etc.
- Both charts receive and render the same boundaries

### Binary Spread Derivation (`utils/binary_spread.py`)
- Derives implied spread from Kalshi/Polymarket "Team wins by X+" binary contracts
- Interpolates the 50% probability crossover point
- Also derives implied total and projected final score

### Related Futures / Bigger Picture (`components/RelatedFutures.tsx`)
- "Bigger Picture" section on event detail page
- `classifyPlayoffStage()`: Conference patterns MUST be checked before championship patterns (otherwise "Eastern Conference Champion" matches "champion" and inflates championship odds)
- 4-level hierarchy: Win Prob → Projected Score → Game Markets → Season Context
- Content wrapped in `max-w-2xl` on desktop to prevent stretching

---

## Celery Tasks Architecture

All task names pinned with `name="app.tasks.*"`. Thin wrappers in `__init__.py` call `run_async()` on async implementations. Key tasks:
- `poll_all_odds` (30-60s) — odds polling with per-sport Redis gating and quota guard
- `sync_espn_live_events` (60s) — ESPN live data, team enrichment
- `discover_events` (15min beat, tiered per-sport) — event discovery
- `poll_futures` / `poll_kalshi` / `poll_polymarket` — futures polling
- `match_prediction_markets` (15min) — link game markets to events
- `poll_live_prediction_markets` (2min) — live price updates
- `poll_datagolf` (hourly) — golf predictions + pre-tournament odds
- `poll_datagolf_live` (5min, Redis-gated) — in-play golf probabilities
- `update_event_tags` (2min) — taxonomy tag computation
- `sync_mm_bracket` — NCAA Tournament bracket data from ESPN
- `collapse_snapshots` (daily) — pure SQL retention
- `calculate_ei` — Excitement Index computation

New tasks go in `tasks/` submodule with async impl + thin wrapper in `__init__.py`:
```python
# __init__.py:
@celery_app.task(bind=True, name="app.tasks.my_task")
def my_task(self):
    from app.tasks.my_module import _my_task_impl
    return run_async(_my_task_impl())
```

---

## Admin Dashboard & Cleanup Endpoints

The admin dashboard at `/admin` (frontend) shows quota, source coverage, DB storage, worker metrics.

Key admin API endpoints (all require `?secret=$ADMIN_SECRET`):
- `POST /api/admin/cleanup/reclassify-events` — move misclassified pm_ events to correct sport based on Kalshi ticker
- `POST /api/admin/cleanup/merge-duplicate-events` — merge pm_ duplicates into real events (sport filter + limit)
- `POST /api/admin/cleanup/purge-orphan-pm-events` — delete pm_ events with no snapshot data
- `POST /api/admin/ei/recalculate` — force EI recalculation
- `GET /api/admin/source-coverage` — per-sport source matching percentages

---

## Quality Audit System ("Quality Ratchet")

A self-reinforcing data quality loop. The goal: define a problem once, it's fixed forever. New issues get added to the quality definition so they're caught going forward.

### The Script
`backend/scripts/audit_matching_quality.py` — comprehensive page health audit with deterministic + LLM checks.

```bash
# Quick scan (free, ~5s):
python3 scripts/audit_matching_quality.py --skip-llm --save

# Full audit with LLM + compare against last baseline:
OPENAI_API_KEY=... python3 scripts/audit_matching_quality.py --compare --save

# Grid-only or event-only:
python3 scripts/audit_matching_quality.py --skip-event --grid nba --skip-llm
python3 scripts/audit_matching_quality.py --skip-grid --event-id 12086896 --skip-llm
```

### Health Score
- Starts at 100, penalized per finding: 🔴 critical = −10, 🟡 warning = −3, 🔵 info = −1
- `--save` persists results to `scripts/audit_results/` with timestamps
- `--compare` shows delta vs last run: ✅ FIXED / 🆕 NEW / ⏳ PERSISTENT findings

### The Practice (MANDATORY)
When fixing ANY data quality, matching, grouping, or display issue:
1. **Run the audit BEFORE** your fix: `python3 scripts/audit_matching_quality.py --skip-llm --save`
2. **Make your fix** (code changes)
3. **Add a check** to the audit script that catches this class of issue (deterministic preferred, LLM if semantic understanding needed)
4. **Run the audit AFTER** your fix: `python3 scripts/audit_matching_quality.py --skip-llm --compare --save`
5. **Verify** the score improved and the finding shows as ✅ FIXED

### When to Use Deterministic vs LLM Checks
- **Deterministic** (preferred): Probability sums, missing data fields, fill rates, source disagreements, monotonicity, duplicates, trend anomalies. These are free, instant, and 100% reliable.
- **LLM** (semantic): Label clarity ("is this name understandable to a casual fan?"), team-market matching ("is this player on this team?"), category correctness. These cost ~$0.01/run but can have false positives — tune the prompt and re-run.

### Current Checks
| Check | Type | Category | What it catches |
|-------|------|----------|----------------|
| `hero_probability_sum` | Deterministic | Event | Home + away odds not summing to ~100% |
| `feed_detail_mismatch` | Deterministic | Event | Feed vs detail page probability inconsistency |
| `missing_team_logo` | Deterministic | Event | Missing logos in event data |
| `matchup_prob_sum` | Deterministic | Futures | Matchup probs inflated (NegRisk market sum check) |
| `duplicate_label` | Deterministic | Futures | Same market from same source appearing twice |
| `cross_source_visual_dupe` | Deterministic | Futures | Same label from different sources (visual clutter) |
| `win_total_resolved` | Deterministic | Futures | Near-resolved win total thresholds (noise) |
| `label_clarity` | LLM | Futures | Unclear/misleading market labels |
| `team_matching` | LLM | Futures | Market incorrectly associated with team |
| `game_state_missing` | Deterministic | Event | Live/completed event with no period boundaries for charts |
| `game_state_weak_source` | Deterministic | Event | Period data only from fallback sources |
| `grid_fill_rate` | Deterministic | Grid | Columns with low data coverage |
| `grid_single_source` | Deterministic | Grid | Columns using only 1 source when more available |
| `grid_team_identity` | Deterministic | Grid | Teams missing logo, team_id, record |
| `grid_source_disagreement` | Deterministic | Grid | >15pp source disagreement |
| `grid_monotonicity` | Deterministic | Grid | Later round prob > earlier round prob |
| `grid_universal_decline` | Deterministic | Grid | >75% of teams trending same direction |
| `grid_prob_sum` | Deterministic | Grid | Championship probs not summing to ~100% |

### Adding New Checks
Add a function to the audit script following the pattern:
```python
def check_my_new_issue(data: dict, report: AuditReport):
    """Check for [description of the issue]."""
    if problem_detected:
        report.add(AuditFinding(
            check="my_new_issue",
            severity=SEVERITY_WARNING,  # critical/warning/info
            category="grid",            # event_detail/related_futures/grid
            description="Human-readable description of the problem",
            details={"key": "value"},   # Stable keys for fingerprinting
        ))
```
Then call it from `audit_event_detail()` or `audit_championship_grid()`. Update this table.

---

## Gotchas & Tips

1. **Alembic revision IDs must be <=32 characters** — `alembic_version.version_num` is `VARCHAR(32)`
2. **Alembic uses psycopg2, not asyncpg** — intentional for Heroku release phase
3. **Admin endpoints require mounting** in both `main.py` AND `routes/__init__.py`
4. **EI scores are cached** — changing the algorithm requires force-recalculate endpoint
5. **`sport_keys.py` imports nothing** — pure data module, zero circular-import risk
6. **Team identity service supplements, not replaces** — don't remove fuzzy matching fallbacks
7. **`Event.external_id` is nullable** — StatPal creates events without Odds API ID
8. **Safari breaks Firebase Google Auth** — use GIS `initTokenClient` + backend custom token fallback
9. **The Odds API bills per `events * market_types * regions`**, NOT per HTTP call. Monitor quota constantly.
10. **`event.period` can contain clock prefixes** (e.g., `"6:55 - 1st Quarter"`) — strip before parsing
11. **Feed loading is auth-gated intentionally** — do NOT pre-fetch anonymous feed for logged-in users
12. **Heroku auto-deploy from GitHub is working** (confirmed April 2, 2026) — `git push origin master` deploys both frontend (Vercel) and backend (Heroku)
13. **iOS models must be `Decodable` not `Codable`** and prefixed with `nonisolated` for Sendable conformance
14. **iOS ViewModels: NO `@MainActor` on class** — only on individual async methods
15. **`Event.sport_id` is an integer FK** to `sports.id`, NOT a string. Filter by sport key using `Sport.key` join/subquery.
16. **Deleting events requires FK cleanup** — must delete from 8+ tables before removing the event row. Use raw SQL, not ORM `db.delete()`, to avoid autoflush FK violations.
17. **Kalshi auto-creates pm_ events** when no matching event exists. Guard added to prevent new duplicates, but historical orphans need cleanup via admin endpoints.
18. **Quota guard expiry date** must be updated monthly in `redis_state.py` (`QUOTA_GUARD_EXPIRY`).
19. **Name normalization** — ALL team name matching goes through `utils/name_normalization.py`. City abbreviations (LA→Los Angeles, NY→New York, etc.) are expanded before token overlap scoring.
20. **Championship grid data quality** — Kalshi 0.45-0.65 noise filter, monotonicity enforcement (P(round N) >= P(round N+1)), esports "Masters" pattern can leak into golf.
21. **Frontend-only changes don't need Heroku push** — Only `git push origin master` needed. Vercel auto-deploys. Heroku push is only required when backend code changes.
22. **Never show 100%/0% probabilities for finished events** — Post-game completion probabilities (winner=100%) must be filtered. Use opening odds or aggregate probability instead.
23. **Chart domain must derive from game timeline** — Use `commenceTime` + last ESPN/score data timestamp. Never constrain chart domain solely from odds data (which may be sparse during API outages).
24. **`classifyPlayoffStage()` order matters** — Conference patterns must be checked BEFORE championship patterns in `RelatedFutures.tsx`. "Eastern Conference Champion" contains "champion" and will misclassify as "Championship" if checked in wrong order.
25. **`compute_aggregate_probability()` is the single source of truth** — Both feed API and event detail API must use it. Never display raw odds_snapshots without aggregate fallback.
26. **Bash heredocs with Python** — When piping Python code via bash, use `python3 << 'PYEOF'` (quoted heredoc) to prevent shell variable expansion and `!=` escaping issues.
27. **Golf market filtering** — `_NON_WINNER_MARKET_RE` in `routes/golf.py` filters out "compete in", "make the cut", "top N finishers" etc. from headline probabilities. Only outright winner/champion markets should appear in card hero probabilities.
28. **Evolution chart position/stage pills** — `EvolutionView.tsx` supports `positionOptions` prop for switching markets. Golf uses Top 20/10/5/Win from Kalshi. Team sports use grid column market_ids (Make Playoffs/Conference/Championship). Pass `entityLabel="Teams"` for team sports.
29. **Golf tour classification** — Many events are mislabeled as "PGA Tour" when they're DP World Tour, Asian Tour, etc. DataGolf provides the correct `tour` field. Fix needed.
30. **Golf "LIVE" badge** — `isTournamentLive()` in the tournament page checks DataGolf leaderboard status. Can false-positive when leaderboard data exists but tournament hasn't started. Needs date-based validation.
31. **Men's/women's golf major separation** — `_normalize_tournament()` returns the same key for both. The grouping loop in `golf.py` appends `_womens` suffix when `_WOMENS_RE` matches the market name. `TOURNAMENT_DISPLAY_NAMES` and `TOURNAMENT_ORDER` have entries for both variants.
32. **Championship grid inline data bars** — `TournamentProgressionTable.tsx` uses sqrt-scaled horizontal bars instead of background color heat maps. Bar width = `sqrt(prob) / sqrt(0.4) * 100%`. Font weight varies: semibold >10%, normal 1-10%, faded <1%.
33. **Evolution chart SWR caching** — 7d/24h/today share the same SWR cache key (same fetched data, filtered client-side). Only "Season" triggers a separate fetch (4320h). `keepPreviousData: true` prevents blank during re-fetch.
34. **Grid columns include market_id** — `playoffs.py` returns `market_id` on each column (most common market_id from that column's data). Frontend uses these to build stage pills for the evolution chart.
35. **Cup card detection** — `TournamentCard.tsx:_isCupEvent()` checks tournament key for ryder/presidents/walker/solheim. When a cup has exactly 2 golfers (teams), renders `CupCard` with left/right layout + probability bar instead of leader/chasers.

---

## Quick Reference

| What | Where |
|------|-------|
| API docs | https://api.bainluck.com/docs |
| Admin dashboard | https://bainluck.com/admin |
| Sports hub | https://bainluck.com/sport |
| NBA league page | https://bainluck.com/sport/basketball/nba |
| Golf | https://bainluck.com/categories/golf |
| Golf strategy | `docs/golf-product-strategy.md` |
| Playoffs | https://bainluck.com/playoffs |
| March Madness | https://bainluck.com/march-madness |
| EI Hall of Fame | https://bainluck.com/ei/hall-of-fame |
| Oscars | https://bainluck.com/oscars |
| Debug endpoints | `/api/events/debug/*` |
| Admin endpoints | `/api/admin/*` |
| Feature docs | `docs/feature-reference.md` |
| Shipped features | `docs/completed-features.md` |
| PRD / Roadmap | `docs/PRD.md` |
| Architecture plans | `.claude/plans/ancient-humming-blossom.md` |
| Trip recap (historical) | `docs/trip-recap-and-next-steps.md` |
