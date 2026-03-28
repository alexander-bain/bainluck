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
│   ├── app/                     # Next.js app router (26 pages)
│   ├── components/              # React components
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
- **Heroku deploys require direct push**: `git push heroku master` (GitHub auto-deploy doesn't work)
- **Always push to both**: `git push origin master && git push heroku master`
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
| **Championship Grids** | `config/league_configs.py`, `routes/playoffs.py` | NBA, NHL, NCAA, Golf grids with Kalshi noise filter + monotonicity enforcement |
| **March Madness** | `routes/march_madness.py`, `tasks/march_madness.py` | NCAA Tournament pages (men's + women's) with bracket data, upset detection, seed matchups |
| **Golf Integration** | `routes/golf.py`, `tasks/datagolf.py`, `services/datagolf_api.py` | DataGolf live in-play probabilities, leaderboards, schedule across 5 tours |
| **Oscars Pool** | `routes/oscars_pool.py`, `routes/oscars.py` | Private prediction pools with odds-adjusted scoring |
| **Related Futures** | `routes/events.py` (related-futures), `RelatedFutures.tsx` | "Bigger Picture" — championship/award/stat prop context |
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

- **Backend (Heroku)**: `git push heroku master` — runs `alembic upgrade head` on release
- **Frontend (Vercel)**: Push to master triggers build (auto-preview for PRs)

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

---

## Product Priorities (ordered)

1. **Best aggregated event probabilities** — Best way to see event probabilities aggregated across sportsbooks
2. **Odds vs algorithms** — Best way to compare event probabilities to algorithm probabilities (win probability models)
3. **Cross-source comparison** — Best way to compare across ALL probability sources (DataGolf, MoneyPuck, FanGraphs, etc.)
4. **Related futures** — Best way to see related futures, both out of curiosity and to understand 2nd-order impact
5. **Team/league-level odds** — Best way to compare odds for entire teams or leagues
6. **Discovery & engagement** — Best way to discover and interact with events with interesting odds (possibly beyond sports; possibly as a game)

### Operational (Late March 2026)
- **Quota management** — Conservation mode deployed, surviving on ~17K remaining until April 1 reset
- **Data quality** — Reclassified 4078 misclassified events, purged 195 orphan pm_ events, expanded Kalshi ticker mappings (18→38)

### Backlog
- Sport-specific EI normalization (different ceilings per sport)
- Hockey win probability model research (lit search for better models)
- TV Mode v2 (designed, prototype at `tv-mode-prototype.jsx`, plan at `docs/tv-mode-plan.md`)
- Non-sports category display (politics, entertainment tabs)
- "The Market Was Wrong" v2 — AI narrative + personalization
- "Your Team's Season at a Glance" dashboard

See `docs/completed-features.md` for shipped features.
See Ideas Backlog in `docs/PRD.md` for longer-term ideas.

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
12. **Heroku auto-deploy from GitHub does NOT work** — must `git push heroku master` directly
13. **iOS models must be `Decodable` not `Codable`** and prefixed with `nonisolated` for Sendable conformance
14. **iOS ViewModels: NO `@MainActor` on class** — only on individual async methods
15. **`Event.sport_id` is an integer FK** to `sports.id`, NOT a string. Filter by sport key using `Sport.key` join/subquery.
16. **Deleting events requires FK cleanup** — must delete from 8+ tables before removing the event row. Use raw SQL, not ORM `db.delete()`, to avoid autoflush FK violations.
17. **Kalshi auto-creates pm_ events** when no matching event exists. Guard added to prevent new duplicates, but historical orphans need cleanup via admin endpoints.
18. **Quota guard expiry date** must be updated monthly in `redis_state.py` (`QUOTA_GUARD_EXPIRY`).
19. **Name normalization** — ALL team name matching goes through `utils/name_normalization.py`. City abbreviations (LA→Los Angeles, NY→New York, etc.) are expanded before token overlap scoring.
20. **Championship grid data quality** — Kalshi 0.45-0.65 noise filter, monotonicity enforcement (P(round N) >= P(round N+1)), esports "Masters" pattern can leak into golf.

---

## Quick Reference

| What | Where |
|------|-------|
| API docs | https://api.bainluck.com/docs |
| Admin dashboard | https://bainluck.com/admin |
| EI Hall of Fame | https://bainluck.com/ei/hall-of-fame |
| Oscars | https://bainluck.com/oscars |
| Golf | https://bainluck.com/categories/golf |
| Playoffs | https://bainluck.com/playoffs |
| March Madness | https://bainluck.com/march-madness |
| Debug endpoints | `/api/events/debug/*` |
| Admin endpoints | `/api/admin/*` |
| Feature docs | `docs/feature-reference.md` |
| Shipped features | `docs/completed-features.md` |
| PRD / Roadmap | `docs/PRD.md` |
| Championship grids | `docs/championship-grids-project.md` |
