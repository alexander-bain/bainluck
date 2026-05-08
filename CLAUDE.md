# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Bain Luck** is a prediction market discovery platform that translates betting and prediction markets into intuitive probabilities. Users see "60% vs 40%" instead of "-150 / +130". Started with sports odds, now covers economics, politics, tech, culture, weather, and more via the Discover feed.

**North Star**: The most engaging way to explore what the world thinks will happen.
**Target User**: Casual fans who want probability-first context — not betting advice.
**Live Site**: https://bainluck.com | **Discover Feed**: https://bainluck.com/discover

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
| `docs/gotchas-reference.md` | Extended gotchas (items 16-39+) | When new gotchas discovered |
| `docs/quality-audit.md` | Audit script usage, check catalog | When checks added/removed |
| `docs/hill-climb-guide.md` | Matching accuracy hill-climb playbook | When layers/gotchas change |
| `docs/feature-reference.md` | Detailed feature documentation | When features ship |
| `docs/completed-features.md` | Shipped features log | When features ship |
| `docs/design-system.md` | Visual design system: colors, type, motion, voice, components | When design tokens or patterns change |

---

## Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+), 3,331+ tests | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis (dual workers: realtime + background) | Heroku Redis |
| Frontend | Next.js 14 (React) | Vercel |
| iOS/macOS App | SwiftUI (shared codebase, 60+ Swift files) | TestFlight / direct |

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
- **Firebase Auth** — Google + Apple Sign-In (free tier)

---

## Development Workflow

- **Both auto-deploy from GitHub**: `git push origin master` deploys backend (Heroku) and frontend (Vercel)
- **Database migrations**: `alembic revision --autogenerate -m "description"`, applied on Heroku release
- **Backend tests**: `cd backend && python3 -m pytest tests/ -v` (3,370+ tests)
- **Smoke test (MANDATORY before push)**: `cd backend && python3 -m pytest tests/test_startup.py -v` (<1s, catches import errors)
- **Frontend build (MANDATORY before push)**: `cd frontend && npm run build` — catches BOTH TypeScript AND ESLint errors. Vercel runs this exact command; `tsc --noEmit` alone is NOT sufficient.
- **Frontend tests**: `cd frontend && npx jest`
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
│   │   ├── models/models.py     # SQLAlchemy models (26 models)
│   │   ├── routes/              # API endpoints
│   │   ├── services/            # External API clients + event_registry.py
│   │   ├── config/              # win_prob_sources.py, league_configs.py
│   │   ├── tasks/               # Celery tasks (23 modules)
│   │   └── utils/               # Pure logic (sport_keys.py, prediction_market_matching.py, etc.)
│   ├── alembic/                 # Database migrations
│   └── tests/                   # 3,331 pytest items
├── frontend/
│   ├── app/                     # Next.js app router (30+ pages, incl. /discover, /weather)
│   ├── components/              # React components (DiscoverCard, OddsChart, MarketMap, etc.)
│   └── lib/                     # API client, types, utilities
├── ios/Bain Luck/               # iOS + macOS app (SwiftUI, 60+ Swift files)
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

---

## CI Test Coverage

| Test File | What It Catches | Added |
|-----------|----------------|-------|
| `tests/test_startup.py` | Import errors that crash the web dyno | Original |
| `tests/test_tasks_wiring.py` | Missing/duplicate Celery beat schedule entries | Apr 2026 |
| `tests/test_alembic.py` | Multiple heads, deleted migrations, orphaned revisions | May 7 |
| `.github/workflows/ci.yml` (frontend-build) | ESLint + TypeScript errors blocking Vercel | May 7 |

---

## Session Startup: Health Check

At the start of every session, run a quick production health scan (~10 seconds):

```bash
# 1. Sentry — new/high-frequency errors since last session
# SENTRY_AUTH_TOKEN is in .env.claude — source it first
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://us.sentry.io/api/0/projects/alexander-bain/bainluck/issues/?query=is:unresolved&limit=5&sort=date" \
  | python3 -c "import json,sys; [print(f'  {i[\"shortId\"]:12s} {i[\"count\"]:>5s} evts  {i[\"title\"][:60]}') for i in json.load(sys.stdin)]"

# 2. Heroku — dyno status + DB connections
heroku apps:info -a bainluck 2>&1 | grep "Dynos:"
heroku pg:info -a bainluck 2>&1 | grep "Connections:"

# 3. CI — last 3 runs
gh run list --repo alexander-bain/bainluck --limit 3
```

If any Sentry issue has >100 events in 24h and wasn't in the last triage, flag it immediately. Otherwise, proceed with session work.

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
| Discover feed | https://bainluck.com/discover |
| Prediction stats | https://bainluck.com/discover/stats |
| Admin dashboard | https://bainluck.com/admin |
| Weather page | https://bainluck.com/weather |
| Politics page | https://bainluck.com/politics |
| Entertainment page | https://bainluck.com/entertainment |
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
