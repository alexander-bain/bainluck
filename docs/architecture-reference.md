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
