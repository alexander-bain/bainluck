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
│   │   ├── models/models.py     # SQLAlchemy models
│   │   ├── routes/              # API endpoints
│   │   │   ├── events.py        # Events API (search, detail, history, related futures)
│   │   │   ├── feed.py          # Unified feed (events + futures ranked)
│   │   │   ├── futures.py       # Championship odds, probability timeline
│   │   │   ├── playoffs.py      # Championship grids
│   │   │   ├── golf.py          # Golf category landing page
│   │   │   ├── oscars.py        # Oscars landing page
│   │   │   ├── auth.py          # Auth endpoints
│   │   │   ├── user.py          # User data (pins, teams, onboarding, preferences)
│   │   │   ├── admin.py         # Admin/debug endpoints
│   │   │   ├── market_moves.py  # "Market Was Wrong" endpoint
│   │   │   ├── sports.py        # Sports listing
│   │   │   └── health.py        # Health check
│   │   ├── services/            # External API clients
│   │   │   ├── odds_api.py, kalshi_api.py, espn_api.py, mlb_api.py
│   │   │   ├── statpal_api.py, polymarket_api.py
│   │   │   ├── firebase_auth.py, llm.py, team_identity.py, database.py
│   │   ├── config/
│   │   │   ├── win_prob_sources.py  # Win probability source registry
│   │   │   └── league_configs.py   # Championship grid configurations
│   │   ├── tasks/               # Celery tasks (18+ modules)
│   │   │   ├── __init__.py      # Celery app, task definitions, beat schedule
│   │   │   ├── config.py, base.py, snapshots.py, redis_state.py
│   │   │   ├── odds_polling.py, excitement_index.py, futures.py
│   │   │   ├── kalshi.py, espn_sync.py, sports.py, retention.py
│   │   │   ├── roster_sync.py, team_linking.py, prediction_market_matching.py
│   │   │   ├── matching_audit.py, mlb_sync.py, statpal_sync.py
│   │   │   └── polymarket.py
│   │   └── utils/               # Pure logic modules
│   │       ├── excitement_index.py, highlights.py, odds_math.py
│   │       ├── aggregation.py, win_probability.py, odds_filtering.py
│   │       ├── futures_categorization.py, line_movement.py
│   │       ├── prediction_market_matching.py, series_probability.py
│   │       ├── market_grouping.py, sport_keys.py, team_linking.py
│   │       └── event_taxonomy.py, feed_reasons.py
│   ├── alembic/                 # Database migrations
│   └── tests/                   # 2500+ pytest items
├── frontend/
│   ├── app/                     # Next.js app router pages
│   ├── components/              # React components
│   ├── lib/                     # API client, types, utilities
│   └── hooks/                   # Custom React hooks
├── ios/Bain Luck/               # iOS app (SwiftUI, 46+ Swift files)
│   └── Bain Luck/
│       ├── Views/               # Screen-level views
│       ├── Components/          # Reusable UI components
│       ├── Models/              # Data models (Decodable)
│       └── Services/            # APIClient, AuthManager, etc.
└── docs/                        # Documentation
    ├── feature-reference.md     # Detailed feature documentation
    ├── completed-features.md    # Shipped features log
    ├── PRD.md                   # Product requirements
    └── championship-grids-project.md
```

---

## Key URLs

| Environment | URL |
|-------------|-----|
| Production Frontend | https://bainluck.com |
| Production API | https://api.bainluck.com |
| API Docs | https://api.bainluck.com/docs |

**Heroku App Name:** `bainluck` (for CLI: `heroku logs -a bainluck`)

---

## Development Workflow

Development happens primarily through **Claude Code**. No local dev environment needed.

- **Backend** and **frontend** auto-deploy from `master` via Heroku and Vercel
- **Heroku deploys require direct push**: `git push heroku master` (GitHub auto-deploy doesn't work)
- **Always push to both**: `git push origin master && git push heroku master`
- **Database migrations**: `alembic revision --autogenerate -m "description"`, applied on Heroku release
- **Backend tests**: `cd backend && python -m pytest tests/ -v`
- **Frontend tests**: `cd frontend && npx jest`

### Querying the Production API
```bash
curl "https://api.bainluck.com/api/events?sport=americanfootball_nfl"
curl "https://api.bainluck.com/api/events/search?q=celtics"
curl "https://api.bainluck.com/api/admin/ei/status"
```

---

## Environment Variables

### Backend (Heroku Config Vars)
`ODDS_API_KEY`, `KALSHI_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `ADMIN_SECRET`, `SENTRY_DSN`, `STATPAL_API_KEY`, `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `APPLE_SERVICES_ID`

### Frontend (Vercel)
`NEXT_PUBLIC_API_URL` = `https://api.bainluck.com`, `NEXT_PUBLIC_FIREBASE_*` (API_KEY, AUTH_DOMAIN, PROJECT_ID), `NEXT_PUBLIC_GA_MEASUREMENT_ID`, `NEXT_PUBLIC_TMDB_API_KEY`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID`

---

## Key Features (Summary)

For detailed documentation of each feature, see `docs/feature-reference.md`.

| Feature | Key Files | Notes |
|---------|-----------|-------|
| **Excitement Index (EI)** | `utils/excitement_index.py`, `EIBadge.tsx` | 1-100 score using GEI formula. Recalc: `POST /api/admin/ei/recalculate` |
| **Highlights/Feed Ranking** | `utils/highlights.py`, `utils/feed_reasons.py` | 4-tier league system, Level 1+2 scoring, personalization |
| **Multi-Source Win Probability** | `config/win_prob_sources.py`, `OddsChart.tsx` | Betting odds, ESPN, Kalshi, Polymarket, MLB, stat model |
| **Prediction Market Matching** | `utils/prediction_market_matching.py`, `tasks/prediction_market_matching.py` | Links Kalshi/Polymarket game markets to events (291 tests) |
| **Auth & Personalization** | `firebase_auth.py`, `routes/auth.py`, `routes/user.py` | Google + Apple Sign-In, onboarding, team favorites, sport affinities |
| **Championship Grids** | `config/league_configs.py`, `routes/playoffs.py` | NBA, NHL, NCAA, Golf grids (78 tests) |
| **Related Futures** | `routes/events.py` (related-futures), `RelatedFutures.tsx` | "Bigger Picture" — championship/award/stat prop context |
| **Snapshot Retention** | `tasks/retention.py` | Pure SQL collapse, constant memory. Write-time dedup |
| **Canonical Identity** | `services/team_identity.py`, `utils/sport_keys.py` | 5-step resolution cascade, supplements fuzzy matching |
| **Market Grouping** | `utils/market_grouping.py` | Source hierarchy + threshold variant detection (315 tests) |
| **Golf/Oscars Pages** | `routes/golf.py`, `routes/oscars.py` | Cross-source odds aggregation with enrichment |

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
events              — Games with teams, scores, EI
odds_snapshots      — Historical odds per bookmaker (write-time dedup)
win_prob_snapshots  — Multi-source win probability history
futures_markets     — Championship/award/prop markets
futures_outcomes    — Individual outcomes within markets
futures_odds_snapshots — Futures probability history
teams               — Team data (ESPN colors/logos, rosters)
users               — Firebase UID, email, profile
user_preferences    — Sport affinities, onboarding state
user_favorites      — Team relationships (follow/local/alma_mater/rival)
user_pins           — Server-side pin storage
team_identity_mapping — Cross-source team identity index
```

**Key identity columns:** `Event.statpal_fixture_id` (nullable `external_id` for schedule-first), `Event.commence_time_source`, `Team.statpal_team_id`, `Event.raw_ei` / `ei_metadata`

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

## Current Priorities (March 2026)

### Active
1. **Data retention / worker memory** — Phase 1 shipped (pure SQL collapse). Phase 2 if OOM persists: pre-game thinning, `odds_aggregated` table, futures cleanup post-resolution
2. **Database size strategy** — Evaluating tiered retention, pre-game thinning, cold storage
3. **Monitoring** — Task-level metrics shipped. Need: alerting (Slack webhook on critical), more tasks tracked

### Next
- Sport-specific EI normalization (different ceilings per sport)
- TV Mode v2 (designed, prototype at `tv-mode-prototype.jsx`, plan at `docs/tv-mode-plan.md`)
- Related futures Phase 5 — bidirectional: futures detail pages show relevant events
- Non-sports category display (politics, entertainment, crypto tabs)
- "The Market Was Wrong" v2 — AI narrative + personalization
- "Your Team's Season at a Glance" dashboard

See `docs/completed-features.md` for shipped features.
See Ideas Backlog in `docs/PRD.md` for longer-term ideas.

---

## Celery Tasks Architecture

All task names pinned with `name="app.tasks.*"`. Thin wrappers in `__init__.py` call `run_async()` on async implementations. Key tasks:
- `poll_all_odds` (30-60s) — odds polling with per-sport Redis gating
- `sync_espn_live_events` (60s) — ESPN live data, team enrichment
- `discover_events` (15min beat, tiered per-sport) — event discovery
- `poll_futures` / `poll_kalshi` / `poll_polymarket` — futures polling
- `match_prediction_markets` (15min) — link game markets to events
- `poll_live_prediction_markets` (2min) — live price updates
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

## Gotchas & Tips

1. **Alembic revision IDs must be <=32 characters** — `alembic_version.version_num` is `VARCHAR(32)`
2. **Alembic uses psycopg2, not asyncpg** — intentional for Heroku release phase
3. **Admin endpoints require mounting** in both `main.py` AND `routes/__init__.py`
4. **EI scores are cached** — changing the algorithm requires force-recalculate endpoint
5. **`sport_keys.py` imports nothing** — pure data module, zero circular-import risk
6. **Team identity service supplements, not replaces** — don't remove fuzzy matching fallbacks
7. **`Event.external_id` is nullable** — StatPal creates events without Odds API ID
8. **Safari breaks Firebase Google Auth** — use GIS `initTokenClient` + backend custom token fallback. Apple uses `signInWithPopup` which works (Firebase routes through its own domain)
9. **The Odds API bills per `events * market_types * regions`**, NOT per HTTP call. Monitor quota constantly. Feb 2026 exhausted full 5M quota.
10. **`event.period` can contain clock prefixes** (e.g., `"6:55 - 1st Quarter"`) — strip before parsing
11. **Feed loading is auth-gated intentionally** — do NOT pre-fetch anonymous feed for logged-in users
12. **Heroku auto-deploy from GitHub does NOT work** — must `git push heroku master` directly
13. **iOS models must be `Decodable` not `Codable`** and prefixed with `nonisolated` for Sendable conformance
14. **iOS ViewModels: NO `@MainActor` on class** — only on individual async methods

---

## Quick Reference

| What | Where |
|------|-------|
| API docs | https://api.bainluck.com/docs |
| EI Hall of Fame | https://bainluck.com/ei/hall-of-fame |
| Oscars | https://bainluck.com/oscars |
| Golf | https://bainluck.com/categories/golf |
| Playoffs | https://bainluck.com/playoffs |
| Debug endpoints | `/api/events/debug/*` |
| Admin endpoints | `/api/admin/*` |
| Feature docs | `docs/feature-reference.md` |
| Shipped features | `docs/completed-features.md` |
| PRD / Roadmap | `docs/PRD.md` |
| Championship grids | `docs/championship-grids-project.md` |
