# Architecture Reference

Detailed documentation of core system architecture. Read this when working on data flow, charts, tasks, or admin endpoints.

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
  -> win_prob_snapshots table (per-source, timestamped)
  -> Event.win_probability_sources JSONB (latest per-source)
  -> compute_aggregate_probability() (weighted average)
  -> Feed cards, event detail hero, OddsChart
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
- Reports its rendered domain via `onRenderedDomain` callback -> `oddsChartDomain` state
- Period boundaries (Q1, HT, Q3, etc.) rendered as vertical `ReferenceLine` markers

### ScoreDifferentialChart (`components/ScoreDifferentialChart.tsx`)
- Projected spread (from sportsbook odds) vs actual score difference
- Domain derived from **game timeline**: `commenceTime` for start, last data timestamp for end
- `chartEndTime` from OddsChart can extend (never shrink) the domain for live games
- Also shows Kalshi/Polymarket implied spreads as flat lines

### Period Boundaries (`lib/periodMarkers.ts`)
- `derivePeriodBoundaries()` extracts game state transitions from ESPN/win_prob/scoring_plays
- `normalizePeriodLabel()` converts "6:55 - 1st Quarter" -> "Q1", "Halftime" -> "HT", etc.
- Both charts receive and render the same boundaries

### Binary Spread Derivation (`utils/binary_spread.py`)
- Derives implied spread from Kalshi/Polymarket "Team wins by X+" binary contracts
- Interpolates the 50% probability crossover point
- Also derives implied total and projected final score

### Related Futures / Bigger Picture (`components/RelatedFutures.tsx`)
- "Bigger Picture" section on event detail page
- `classifyPlayoffStage()`: Conference patterns MUST be checked before championship patterns (otherwise "Eastern Conference Champion" matches "champion" and inflates championship odds)
- 4-level hierarchy: Win Prob -> Projected Score -> Game Markets -> Season Context
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

- `backfill_winners` (6h) — sets `is_winner` on `FuturesOutcome` from settlement data. Phase 1: source-agnostic from `current_probability` on cleanly-resolved markets. Phase 2: Kalshi API `result='yes'|'no'` for partially-resolved markets.

New tasks go in `tasks/` submodule with async impl + thin wrapper in `__init__.py`:
```python
# __init__.py:
@celery_app.task(bind=True, name="app.tasks.my_task")
def my_task(self):
    from app.tasks.my_module import _my_task_impl
    return run_async(_my_task_impl())
```

---

## Calibration Pipeline

Answers "Do prediction markets predict anything?" by comparing opening probabilities to actual outcomes across all resolved markets.

### Data Sources (3)
- **Kalshi + Polymarket** (`futures_markets` / `futures_outcomes`): `opening_probability` vs `current_probability` on resolved markets. Virtual market reconstruction via `group_id` for Polymarket multi-outcome events.
- **Odds API** (`events` table): `opening_home_probability` / `opening_away_probability` vs `home_score` / `away_score`. Ground truth — no inference needed.

### Key Transformations
- **Virtual market reconstruction**: When 3+ Polymarket markets share a `group_id`, treat as one multi-outcome market (structurally identical to a Kalshi championship market).
- **Inverted field price correction**: In markets with 10+ outcomes, `opening_probability > 0.50` is inverted (stores "No" price). Corrected to `1 - opening_probability`.
- **Threshold dedup**: For non-ME markets (player props), keep one outcome per virtual market (closest to 50%).
- **Clean resolution filter**: Only markets where 80%+ of outcomes resolved to near-0 or near-1.

### Endpoints
- `GET /api/admin/calibration-data` — pre-aggregated buckets for report generation
- `POST /api/admin/backfill-winners` — trigger `is_winner` backfill (supports `dry_run`, `limit`)
- `GET /api/admin/backfill-winners/status` — backfill progress per source

### Files
- `backend/app/tasks/backfill_winners.py` — `is_winner` backfill task
- `backend/app/routes/admin.py` — calibration endpoint (SQL query with virtual market logic)
- `backend/scripts/build_calibration_report_svg.py` — static HTML report generator

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

## League-Scoped Futures (`routes/league_futures.py`)

`GET /api/leagues/{sport_key}` returns all open, non-game-level futures for a specific league, grouped by display section.

### Filtering Strategy

Three layers narrow from sport to league:
1. **`llm_sport_category`** — broad sport match (e.g., `basketball`)
2. **Kalshi ticker prefix** — `KXNBA%` via `LEAGUE_TICKER_PREFIXES` map
3. **Market name patterns** — `NBA%`, `%National Basketball%` via `LEAGUE_NAME_PATTERNS` map
4. **`llm_league`** — direct league match when available (e.g., `nba`)

Any of these matching is sufficient (OR logic).

### Section Assignment (`_assign_section()`)

Markets are assigned to one of 5 sections based on `market_tier`, `category`, and name keywords:

| Section | Criteria | Example |
|---------|----------|---------|
| `series` | Name contains "series" or "vs" at tier 5 | "Celtics vs Cavaliers: Series Winner" |
| `awards` | Tier 3, or category "award"/"mvp" | "NBA MVP Winner" |
| `playoff_props` | Keywords: sweep, game 7, elimination | "Number of Series Sweeps" |
| `season_stats` | Category "season_stat" or stat keywords | "PPG Leader", "Win Total" |
| `novelty` | Everything else | "Luka Doncic back before May 7" |

Championship (tier 1), conference (tier 2), and division (tier 4) markets are **skipped** — they're already on the championship grid.

### Feed Diversity: `_ensure_feed_diversity()` (`routes/feed.py`)

Controls the event-to-futures ratio in the feed. The `event_pct` parameter sets the minimum percentage of slots reserved for events (games).

| Consumer | `event_pct` | Why |
|----------|------------|-----|
| Sports feed (anonymous) | 0.6 | Events are the core product |
| Sports feed (authenticated) | 0.4 | Personalization adds futures relevance |
| Discover feed | 0.15 | Let scoring decide — interesting content regardless of type |
| My Stuff | skipped | Shows everything matching |

The `event_pct` can be overridden via the `event_pct` query parameter on `GET /api/feed`.

### Wild-Ending Boost (`utils/feed_scoring.py`)

Completed events with extreme comeback narratives get boosted in the feed via `ei_metadata`:

| Signal | Threshold | Boost | Example |
|--------|-----------|-------|---------|
| `comeback_factor` ≤ 0.10 | Miracle comeback | +30 | Winner was at 10% with 2 min left |
| `comeback_factor` ≤ 0.20 | Big comeback | +20 | Winner was at 20% at halftime |
| `lead_changes` ≥ 4 | Wild swings | +10 | Lead changed 4+ times |

These stack with the existing EI boost (+25 for EI ≥ 80, +15 for EI ≥ 60). A miracle comeback in a high-EI game could score 65+ additional points, surfacing it prominently in both Sports and Discover feeds.

### Cross-Source Dedup

Uses `canonical_market_key`. When two markets share the same key, keeps the one with more outcomes.

### Discover Quality Pipeline (`routes/feed.py`, `utils/feed_market_quality.py`)

Discover mode is `/api/feed` with `event_pct=0.15`. It builds multiple candidate pools, scores futures/events, applies canonical dedupe, demotes routine events, then applies market-quality caps and first-page category/archetype/story mixing.

Important invariants:
- Deterministic headlines must make the first page understandable without waiting for OpenAI hook enrichment.
- Hook enrichment is bounded to feed-shaped candidates; never run enrichment against the full open-market backlog.
- Quality caps run before response serialization and are measured by `scripts/audit_feed_quality.py`.
- First-page mixing should reorder, not mutate scores. Score mutation belongs in scoring/quality phases.

### Discover Engagement and Personalization

Web and native send first-party Discover events to `POST /api/feed/interactions`. Events are stored in `discover_interactions` with `surface`, `action`, `item_type`, `item_id`, `category`, `score`, `rank`, and `source`.

Admin rollup:
- `GET /api/admin/discover-engagement` groups engagement by surface/category/item type.
- The endpoint also emits promote/investigate/downrank recommendations from open, dismiss, share, and impression rates.
- `/admin/discover-quality` displays those metrics alongside feed quality traces.

Personalization layering:
- Authenticated feed scoring loads recent `discover_interactions` in `_load_personalization_context()`.
- `PersonalizationContext.discover_category_affinities` stores category deltas derived from the last 30 days.
- `compute_event_multiplier()` maps sport keys to Discover categories (`americanfootball_*` → `football`, `icehockey_*` → `hockey`).
- `compute_futures_multiplier()` uses `llm_sport_category`.
- Interaction-derived deltas are capped to `+0.18x` / `-0.15x`; favorites, pins, sport affinities, and quality filters remain the stronger signals.

---

## Polymarket Game Event Decomposition (`tasks/polymarket.py`)

Polymarket game events (e.g., "Magic vs. Pistons") contain ~40 sub-markets: moneyline, spread, O/U, and 20+ player props. These are NOT outcomes of one market — each sub-market has its own `condition_id` and `question`.

### Data Model

```
Polymarket API Event (neg_risk=False, 40 markets)
  └─ Market 1: "Magic vs. Pistons" (condition_id=0x56e, moneyline)
  └─ Market 2: "Spread: Pistons (-9.5)" (condition_id=0x4a0)
  └─ Market 3: "Cade Cunningham: Points O/U 27.5" (condition_id=0x160)
  └─ ...37 more

Our DB (after decomposition):
  FuturesMarket (parent): name="Magic vs. Pistons", group_type="polymarket_event"
  FuturesMarket (sub): name="Magic vs. Pistons", group_type="polymarket_sub_market", event_id=X
  FuturesMarket (sub): name="Spread: Pistons (-9.5)", group_type="polymarket_sub_market", event_id=X
  FuturesMarket (sub): name="Cade Cunningham: Points O/U 27.5", group_type="polymarket_sub_market", event_id=X
```

### Linking Pipeline

1. **Polymarket poll** (hourly): Creates parent + sub-market FuturesMarket rows. Sub-markets inherit `event_id` from parent if already linked.
2. **Matching task** (every 15 min): Links parent by "vs." name pattern → sets `event_id` on parent AND propagates to all sub-markets in the same `group_id`.
3. **Game-markets endpoint**: Finds sub-markets via `event_id` FK, classifies each by name (`_classify_game_market`), routes to player_props/spreads/totals.

### Key Distinction: neg_risk vs game events

| Type | `neg_risk` | Sub-markets are... | Example |
|------|-----------|-------------------|---------|
| Championship | `True` | Outcomes (one candidate each) | "NBA Champion" → 30 team outcomes |
| Game event | `False` | Separate markets (different types) | "Magic vs Pistons" → moneyline + spread + props |

### Backfill Script

`scripts/backfill_polymarket_submarkets.py` — decomposes existing game events, propagates event_ids, reports category breakdown, optionally cleans up crypto markets.

---

## Category Pages Architecture (May 6, 2026)

Three themed landing pages aggregate prediction markets from Kalshi + Polymarket into consumable dashboards: Weather (shipped April 19-20), Politics (shipped May 6), and Entertainment (shipped May 6).

### Common Pattern

All category pages follow the same architecture:
1. **Backend route** (`routes/{category}.py`) — queries `futures_markets` by `llm_sport_category`, filters by data quality rules, groups into sub-themes
2. **Frontend page** (`app/{category}/page.tsx`) — themed hero, SWR data fetch, category-specific styling
3. **Quality filters** — skip resolved markets (≥95% leader for binary, resolution_date past), filter garbage outcomes (pattern matching), sort by interestingness

### Politics Page (`/politics`)

**Backend:** `GET /api/politics` in `routes/politics.py`

**Sub-themes:** Elections (presidential, congressional, gubernatorial), Policy & Legislation, Governance, International Politics

**Quality filters:**
- Skip markets with "Yes/No" leader ≥95% (resolved binary markets)
- Skip markets with resolution_date in the past
- Filter garbage outcomes via pattern matching
- Sort by probability decisiveness (prefer 15-85% range)

**Frontend:** `app/politics/page.tsx` — purple theme (#9333ea), Capitol building imagery, election countdown timers

### Entertainment Page (`/entertainment`)

**Backend:** `GET /api/entertainment` in `routes/entertainment.py`

**Sub-themes:** Awards (Oscars, Grammys, Emmys), Box Office, Music & Culture, Reality TV, Celebrity & Pop Culture

**Quality filters:**
- Same pattern as politics (resolved markets, garbage outcomes, past resolution dates)
- Filter "player A/AB/L" garbage outcomes (Polymarket data quality issue)
- Sort by cultural relevance + probability decisiveness

**Frontend:** `app/entertainment/page.tsx` — pink/magenta theme (#ec4899), spotlight imagery, award season context

### Weather Page (`/weather`) — Shipped April 19-20

**Backend:** 6 endpoints in `routes/weather.py`:
- `GET /api/weather/featured` — Hero rotator (top 5)
- `GET /api/weather/cities` — 49 cities global temperature map
- `GET /api/weather/rain` — NYC 7-day rain forecast
- `GET /api/weather/events` — Hurricane season, tornado markets
- `GET /api/weather/climate` — 2026/2030/2050 horizons
- `GET /api/weather/wildcards` — Rare events (supervolcano, solar storms)

**Data sources:** 521 weather markets from Kalshi + Polymarket

**Frontend:** `app/weather/page.tsx` — interactive map with collision-resolved pins, histogram distribution, continent SVGs

### Key Design Principles

1. **No hardcoded market lists** — Programmatic discovery via `llm_sport_category` + sub-theme patterns
2. **Data quality first** — Aggressive filtering of resolved/stale/garbage data before display
3. **Probability-first UI** — Never show American odds or gambling terminology
4. **Light mode only** — Consistent with site-wide design system
5. **SWR with fallback** — Client fetches live data, falls back to static JSON if API fails

**Files:**
- Backend: `backend/app/routes/{politics,entertainment,weather}.py`
- Frontend: `frontend/app/{politics,entertainment,weather}/page.tsx`
- Shared components: `CombinedMarketCard.tsx` (cross-source comparison), `FuturesCard.tsx` (market display)

---

## Infrastructure & Observability (May 6, 2026)

### Request Observability

Every API request now has a unique `request_id` and logs duration. Request ID middleware (`app/middleware/request_id.py`) generates UUIDs, adds to both response headers and structured logs. Duration logging happens in FastAPI's request hook with millisecond precision.

**Key benefits:**
- Trace requests across services (frontend → backend → DB)
- Identify slow endpoints via log aggregation
- Debug specific user issues by request ID

**Headers:**
- `X-Request-ID` — UUID for request tracing
- Response includes `X-Request-ID` for client correlation

**Logs:**
```json
{"timestamp": "2026-05-06T10:30:00Z", "request_id": "abc123", "path": "/api/feed", "duration_ms": 1234}
```

### Sentry Error Filtering

**PendingRollbackError filtering** — Database transaction conflicts (usually from Celery task concurrency) now filtered from Sentry to preserve 5K/mo free tier quota. These errors are transient and automatically retried by Celery — they were consuming 40% of monthly quota.

**Filter location:** `app/main.py` `before_send` hook checks exception type and message patterns.

### 404 Sport Key Caching

**Problem:** Malformed sport keys (typos in API calls, stale client code) were triggering ~37K unnecessary Odds API quota burns per day — each 404 lookup counted against quota.

**Solution:** Redis cache at `bainluck:404_sport_keys:{key}` with 24h TTL. After first 404, subsequent lookups skip the API entirely.

**Impact:** Saves ~1.1M quota/month (~22% of total monthly quota).

**Files:** `backend/app/tasks/odds_polling.py` (cache check before API call)

### Hook Enrichment Pipeline

**Coverage boost:** 500 markets/batch hourly (was 200 every 2h). Prioritizes markets missing `hook_description` over stale regenerations. Cost ~$1/day for GPT-4o-mini.

**Monitoring:** `GET /api/admin/hook-coverage` shows tier breakdown (feed-visible, important, all), missing hook counts, batch limits, last run timestamp.

**Quality:** Upgraded from 120-char generic sentences to 250-char contextual blurbs using Polymarket email few-shot examples. Tracks `hook_generated_at` + leader probabilities to avoid unnecessary regenerations.

**Files:** `backend/app/tasks/enrich_markets.py`, `backend/app/routes/admin.py` (coverage endpoint)

### Aggregation Quality Monitoring

**Daily task:** Samples 50 live events, logs source diversity metrics. Alerts when >20% of events rely on single source (indicates upstream source outage or matching failure).

**Structured logs:** JSON format with `source_count`, `sources_present`, `aggregate_used` fields for each event.

**Files:** `backend/app/tasks/monitoring.py` (new)

### Source Ingestion Metrics

**Kalshi + Polymarket polling:** Structured logging with `markets_found`, `markets_matched`, `markets_classified`, `markets_rejected` counts per poll.

**Purpose:** Detect regressions in matching/classification logic by comparing run-to-run metrics.

**Files:** `backend/app/tasks/kalshi.py`, `backend/app/tasks/polymarket.py`

---

## ESPN Box Score Pipeline (`tasks/espn_sync.py`)

Box score data (player stats for completed/live games) flows through 4 passes in the ESPN sync task, all in a single session:

```
Pass 1 (live events):     ESPN scoreboard → win_probability_sources + espn_id (Core SQL)
Pass 2 (scheduled):       ESPN scheduled → commence_time, broadcast, importance (ORM)
Pass 3 (completed):       ESPN box score API → box_score_data (raw SQL text, status=completed/closed)
Pass 4 (live box scores): ESPN box score API → box_score_data (raw SQL text, status=live)
```

### Critical: Write Patterns

All writes in the ESPN sync MUST use Core SQL or raw text SQL, NOT ORM attribute assignment. The session mixes ORM reads with Core SQL updates, and ORM dirty tracking silently reverts Core SQL changes on flush. Three instances of this bug were found (gotchas #8, #22, #48).

| Field | Write method | Why |
|-------|-------------|-----|
| `win_probability_sources` | `_sql_update(Event).values(...)` | JSONB, gotcha #8 |
| `espn_id` | Piggybacked on win_prob Core SQL | ORM/Core mixing, gotcha #22 |
| `box_score_data` | `text("UPDATE events SET box_score_data = cast(:bsd AS jsonb) WHERE id = :eid")` | JSONB + ORM/Core mixing |

### Box Score Data Flow to Frontend

```
Event.box_score_data (DB, JSONB)
  → GET /api/events/{id} response: box_score_data.players
    → Frontend: event.box_score_data passed to PlayerPropsDashboard
      → PlayerPropsDashboard: hasBoxScore check → "done" mode with actual stats
```

Without `box_score_data`, PlayerPropsDashboard falls back to "pre" mode (shows probabilities instead of results).
