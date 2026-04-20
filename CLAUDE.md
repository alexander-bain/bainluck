# CLAUDE.md - Project Guidelines for Claude Code

## Project Overview

**Bain Luck** is a visual-first sports odds experience that translates betting markets into intuitive win probabilities. Users see "60% vs 40%" instead of "-150 / +130".

**North Star**: The cleanest odds visualization tool on the internet.
**Target User**: Casual sports fans watching games who want context, not betting advice.
**Live Site**: https://bainluck.com

---

## The #1 Technical Challenge: Semantic Matching

The core magic of Bain Luck is **perfect semantic understanding** of every event, market, and source — then grouping and matching them so the user sees one unified view. This is the hardest technical problem in the product and the biggest leverage point.

There are 3 layers of matching, each with its own measurement:

| Layer | What it does | Measurement | Target | Monitor |
|-------|-------------|-------------|--------|---------|
| **Event ↔ Source** | Links ESPN, StatPal, Odds API data to the same game | Source count per event (admin dashboard) | >3 sources on live events | `/api/admin/dashboard` |
| **Market ↔ Event** | Links Kalshi/Polymarket game props to event records | Link rate by sport (link-rate endpoint) | >80% for major sports | `/api/admin/prediction-markets/link-rate` |
| **Market ↔ Grid** | Places championship/futures markets in correct grid cells | Grid fill rate (playoffs endpoint) | >90% per column | `/api/playoffs/{league}` |

**Philosophy**: If we're at 40% on a metric, we need to distinguish "40% of markets that SHOULD match" vs "40% including markets that CAN'T match (e.g., no event exists)". The link-rate endpoint already filters to sports-only markets. **Any metric below target for markets that SHOULD match is a bug, not a feature gap.**

---

## Linked Reference Docs

| Doc | Purpose | When to update |
|-----|---------|---------------|
| `docs/backlog.md` | All outstanding work items (SINGLE SOURCE OF TRUTH) | When items ship, are added, or reprioritized |
| `docs/architecture-reference.md` | Core system design: aggregation, resilience, charts, tasks, admin | When architecture changes |
| `docs/gotchas-reference.md` | Extended gotchas (items 16-39+) | When new gotchas discovered |
| `docs/quality-audit.md` | Audit script usage, check catalog | When checks added/removed |
| `docs/feature-reference.md` | Detailed feature documentation | When features ship |
| `docs/completed-features.md` | Shipped features log | When features ship |

---

## Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+), 3,149 tests | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis (dual workers: realtime + background) | Heroku Redis |
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
- **OpenAI** — GPT-4o-mini for LLM classification (~$5/mo)
- **Firebase Auth** — Google + Apple Sign-In (free tier)

---

## Development Workflow

- **Both auto-deploy from GitHub**: `git push origin master` deploys backend (Heroku) and frontend (Vercel)
- **Database migrations**: `alembic revision --autogenerate -m "description"`, applied on Heroku release
- **Backend tests**: `cd backend && python3 -m pytest tests/ -v` (3,149 tests as of April 20)
- **Frontend tests**: `cd frontend && npx jest`

### Key Admin URLs
```
https://bainluck.com/admin              — Operations dashboard
https://api.bainluck.com/docs           — API docs (Swagger)
https://api.bainluck.com/api/admin/prediction-markets/link-rate?secret=$ADMIN_SECRET  — Link rate health
```

---

## Project Structure

```
bainluck/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── models/models.py     # SQLAlchemy models (26 models)
│   │   ├── routes/              # API endpoints
│   │   ├── services/            # External API clients + event_registry.py
│   │   ├── config/              # win_prob_sources.py, league_configs.py
│   │   ├── tasks/               # Celery tasks (23 modules)
│   │   └── utils/               # Pure logic (sport_keys.py, prediction_market_matching.py, etc.)
│   ├── alembic/                 # Database migrations
│   └── tests/                   # 3,149 pytest items
├── frontend/
│   ├── app/                     # Next.js app router (30+ pages)
│   ├── components/              # React components (RelatedFutures, OddsChart, etc.)
│   └── lib/                     # API client, types, utilities
├── ios/Bain Luck/               # iOS app (SwiftUI, 54 Swift files)
└── docs/                        # Documentation
```

---

## Core Architecture

**Event Registry** (`services/event_registry.py`): Unified `find_or_create_event()` with 4-step cascade: exact source ID → cross-source ID → structured match (sport + time ± 4h + teams) → create. All 5 source tasks wired up. ESPN is a first-class source.

**Probability Aggregation** (`utils/aggregation.py`): `compute_aggregate_probability()` reads from `Event.win_probability_sources` JSONB. Source weights: betting 3.0, ESPN 1.5, stat_model 1.0, Kalshi/Polymarket/MLB 0.8. All sources write via `select+update` pattern (NOT ORM attribute assignment — silently fails due to session caching).

**Prediction Market Matching** (`tasks/prediction_market_matching.py`): Hourly task links Kalshi/Polymarket game markets to events. Three-phase: Link (Pass 1 ticker scan + Pass 2 general scan) → Re-validate (Phase 1.5) → Snapshot writing (Phase 2). Per-market commit to avoid deadlocks with live polling task. Link rate tracked at `/api/admin/prediction-markets/link-rate`.

**Source-Agnostic Resilience**: System works when any single source goes dark (validated during March 2026 Odds API quota exhaustion).

---

## Product Priorities (ordered)

1. **Best aggregated event probabilities** — Best way to see event probabilities aggregated across sportsbooks
2. **Odds vs algorithms** — Compare event probabilities to algorithm probabilities (win probability models)
3. **Cross-source comparison** — Compare across ALL probability sources (DataGolf, FanGraphs, etc.)
4. **Related futures** — See related futures, both out of curiosity and to understand 2nd-order impact
5. **Team/league-level odds** — Compare odds for entire teams or leagues
6. **Discovery & engagement** — Discover and interact with events with interesting odds

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
futures_markets     — Championship/award/prop markets (market_tier, event_id, sport_id)
futures_outcomes    — Individual outcomes within markets
teams               — Team data (ESPN colors/logos, rosters, alternate_names)
team_identity_mapping — Cross-source team identity index
```

**Key columns**: `Event.win_probability_sources` (JSONB, all 6 sources), `FuturesMarket.market_tier` (1-5), `FuturesMarket.event_id` (nullable FK — game props linked to events), `FuturesMarket.llm_sport_category`.

---

## Sport Key Architecture

`utils/sport_keys.py` is the **single source of truth** for all sport key translation maps. Imports nothing (zero circular-import risk). Key maps: `SPORT_LEAGUE_MAP` (28 entries), `KALSHI_TICKER_TO_SPORT_KEY` (~150 entries), `KALSHI_FUTURES_TICKER_TO_SPORT_KEY` (~250 entries), `SPORT_PREFIX_TO_LLM_CATEGORY` (11 entries).

---

## Gotchas (Top 15 — full list in `docs/gotchas-reference.md`)

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
| Admin dashboard | https://bainluck.com/admin |
| Link rate health | `GET /api/admin/prediction-markets/link-rate` |
| API docs | https://api.bainluck.com/docs |
| Backlog | `docs/backlog.md` |
| Shipped features | `docs/completed-features.md` |
| Architecture | `docs/architecture-reference.md` |
| Gotchas (full) | `docs/gotchas-reference.md` |
| Quality audit | `docs/quality-audit.md` |
