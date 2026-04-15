# CLAUDE.md - Project Guidelines for Claude Code

## Project Overview

**Bain Luck** is a visual-first sports odds experience that translates betting markets into intuitive win probabilities. Users see "60% vs 40%" instead of "-150 / +130".

**North Star**: The cleanest odds visualization tool on the internet.
**Target User**: Casual sports fans watching games who want context, not betting advice.
**Live Site**: https://bainluck.com

---

## Linked Reference Docs (keep updated proactively!)

These docs contain detailed reference material. **Read them when working in their area. Update them proactively whenever you make changes, ship features, discover gotchas, or learn something new — don't wait to be asked.**

| Doc | Purpose | When to update |
|-----|---------|---------------|
| `docs/backlog.md` | All outstanding work items (SINGLE SOURCE OF TRUTH) | When items ship, are added, or reprioritized. Mark shipped items. Add new ideas/bugs as discovered. |
| `docs/architecture-reference.md` | Core system design: aggregation, resilience, charts, tasks, admin | When architecture changes, new tasks added, new data sources integrated |
| `docs/gotchas-reference.md` | Extended gotchas (items 16-39+) | When new gotchas discovered, old ones resolved, or workarounds change |
| `docs/quality-audit.md` | Audit script usage, check catalog, adding new checks | When checks added/removed, scoring changed, new categories added |
| `docs/feature-reference.md` | Detailed feature documentation | When features ship, behavior changes, or key files move |
| `docs/completed-features.md` | Shipped features log | When features ship — move from backlog to here |

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
│   │   ├── routes/              # API endpoints (events, feed, futures, playoffs, golf, etc.)
│   │   ├── services/            # External API clients (odds, ESPN, Kalshi, DataGolf, etc.)
│   │   ├── config/              # win_prob_sources.py, league_configs.py
│   │   ├── tasks/               # Celery tasks (23 modules)
│   │   └── utils/               # Pure logic modules (24 modules)
│   ├── alembic/                 # Database migrations
│   ├── scripts/                 # Quality audit, data tools
│   └── tests/                   # 2747 pytest items
├── frontend/
│   ├── app/                     # Next.js app router (30+ pages)
│   ├── components/              # React components
│   ├── lib/                     # API client, types, utilities
│   └── hooks/                   # Custom React hooks
├── ios/Bain Luck/               # iOS app (SwiftUI, 54 Swift files)
└── docs/                        # Documentation
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

- **Both auto-deploy from GitHub**: `git push origin master` deploys backend (Heroku) and frontend (Vercel)
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
- `SPORT_LEAGUE_MAP` (28 entries) — Odds API key -> ESPN (sport, league) tuple
- `ESPN_SPORT_MAPPING` (25 entries) — Odds API key -> ESPN path string
- `KALSHI_TICKER_TO_SPORT_KEY` (38 entries) — Kalshi ticker prefix -> Odds API sport key
- `KALSHI_TICKER_TO_DISPLAY_LABEL` (27 entries) — ticker -> display name
- `SPORT_PREFIX_TO_LLM_CATEGORY` (11 entries) — prefix -> LLM category
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

**Adaptive slowdown**: Per-sport Redis counter tracks consecutive unchanged polls. After 3 unchanged -> 5min interval. After 6 unchanged -> 10min interval. Resets instantly when odds change. Live tier exempt.

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
- **Data quality** — Reclassified 4078 misclassified events, purged 195 orphan pm_ events, expanded Kalshi ticker mappings (18->38)

### Backlog

**All outstanding work items live in `docs/backlog.md`** (SINGLE SOURCE OF TRUTH). Update it whenever items are completed, added, or reprioritized.

---

## Core Architecture (summaries — see `docs/architecture-reference.md` for details)

**Probability Aggregation**: `compute_aggregate_probability()` in `utils/aggregation.py` is the single source of truth. Three-tier fallback (win_probability_sources -> ESPN -> opening odds). Source weights: betting 3.0, ESPN 1.5, stat_model 1.0, Kalshi/Polymarket/MLB 0.8. Both feed and event detail APIs MUST use it — never display raw odds_snapshots alone.

**Source-Agnostic Resilience**: System works when any single source goes dark (validated during March 2026 Odds API quota exhaustion). Events don't require Odds API. Prediction markets match by team name + time. ESPN/StatPal flow independently. Chart domains derive from game timeline, not odds data.

**Celery Tasks**: All task names pinned with `name="app.tasks.*"`. Thin wrappers in `__init__.py` call `run_async()` on async implementations. See `docs/architecture-reference.md` for full task list and new-task template.

**Charts**: OddsChart reports domain via callback. ScoreDifferentialChart derives domain from game timeline. Period boundaries shared between charts via `derivePeriodBoundaries()`.

---

## Quality Audit (mandatory practice)

When fixing ANY data quality, matching, grouping, or display issue:
1. Run the audit BEFORE your fix: `python3 scripts/audit_matching_quality.py --skip-llm --save`
2. Make your fix (code changes)
3. Add a check to the audit script that catches this class of issue
4. Run the audit AFTER: `python3 scripts/audit_matching_quality.py --skip-llm --compare --save`
5. Verify the score improved and the finding shows as FIXED

Script usage, check catalog, and templates: `docs/quality-audit.md`

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
9. **The Odds API bills per `events * market_types * regions`**, NOT per HTTP call
10. **`event.period` can contain clock prefixes** (e.g., `"6:55 - 1st Quarter"`) — strip before parsing
11. **Feed loading is auth-gated intentionally** — do NOT pre-fetch anonymous feed for logged-in users
12. **`Event.sport_id` is an integer FK** to `sports.id`, NOT a string. Filter by sport key using `Sport.key` join/subquery.
13. **iOS models must be `Decodable` not `Codable`** and prefixed with `nonisolated` for Sendable conformance
14. **iOS ViewModels: NO `@MainActor` on class** — only on individual async methods
15. **Python 3.12+ redundant imports cause UnboundLocalError** — `from datetime import timedelta` inside a function body shadows the module-level import. Check for this pattern in task files.

Full list (39 items): `docs/gotchas-reference.md`

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
| Backlog | `docs/backlog.md` |
| Architecture | `docs/architecture-reference.md` |
| Gotchas (full) | `docs/gotchas-reference.md` |
| Quality audit | `docs/quality-audit.md` |
| PRD / Roadmap | `docs/PRD.md` |
| Roster team_id plan | `.claude/plans/prancy-seeking-ritchie.md` |
