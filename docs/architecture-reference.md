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
