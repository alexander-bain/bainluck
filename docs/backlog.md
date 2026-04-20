# Backlog (SINGLE SOURCE OF TRUTH)

All outstanding work items for Bain Luck. Shipped items live in `docs/completed-features.md`.

---

## Current Priority: Semantic Matching Excellence

The product's magic depends on **perfectly understanding every event, market, and source** — then grouping and matching them so the user sees one unified view. This is the #1 technical priority and the area with the most measurable room for improvement.

**Matching health dashboard:** `GET /api/admin/prediction-markets/link-rate` + admin dashboard at `/admin`

**Current state (April 20, 2026):**

| Sport | Kalshi open | Polymarket open | Target | Status |
|-------|------------|----------------|--------|--------|
| Tennis | 95.9% | 0.3% | >90% K, accept PM | **Kalshi: GOOD** |
| Basketball | 56.8% | 88.2% | >85% | Needs work |
| Baseball | 76.7% | 71.2% | >85% | Close |
| Hockey | 52.1% | 50.0% | >80% | Needs work |
| MMA | 77.3% | 25.0% | >80% | Kalshi close, PM needs investigation |
| Soccer | 33.7% | 98.4% | varies | PM great, Kalshi limited by minor league coverage |
| Esports | 13.5% | 3.9% | ~20% | Structural limit — no event source |
| Golf | 1.4% | — | N/A | Not a bug — futures use grid, not event_id |
| Football | 0.0% | — | N/A | Offseason |

**Key principle:** Distinguish "should match but doesn't" (bug) from "can't match because no event exists" (acceptable). Any sport with >100 open markets and <80% link rate on markets that SHOULD match is a problem.

---

## Tier 1 — High Leverage, Do Next

### 1. Improve Game Prop Link Rate (1C continuation)

**Goal:** Push basketball, baseball, hockey to >85% open link rate.

**What's already shipped (April 19-20):**
- Ticker-derived team names for game props
- ILIKE pattern expansion (`_expand_team_search_terms`)
- `_SPORT_ABBREV_SUFFIX` derived from all ~150 ticker prefixes
- `_TICKER_DATE_RE` fixed for digit-containing prefixes
- `sport_id` propagation on all linking paths + Phase 1.5 backfill
- `llm_sport_category` correction from ticker on link + backfill
- " - More Markets" suffix stripping, "Game N:" prefix stripping
- City abbreviation map (65 entries)
- Phase 2 deadlock fix (per-market commit)
- Matching frequency 4h → 1h, limit 200 → 500
- Link rate dashboard + API endpoint
- `POST /admin/prediction-markets/fix-sport-categories` bulk fix endpoint
- 324 prediction market matching tests

**Remaining sub-items (in priority order):**

#### 1a. Basketball 57% → 85%+
**Problem:** Markets created before events exist (Kalshi creates props 2-7 days ahead of Odds API discovery). Hourly re-scanning should close this gap naturally — monitor for 3-5 days. If rate doesn't climb, the issue is team name matching failures on specific markets.
**Action:** Monitor. If still <75% by April 25, run the debug endpoint filtered to basketball and diagnose specific failing markets.

#### 1b. Hockey 52% → 80%+
**Problem:** Despite city abbreviation map, many NHL props still fail. Likely remaining abbreviated team names not in `_CITY_ABBREV_TO_NAME`, or playoff series naming patterns not handled.
**Fix:** Sample 20 unlinked open NHL markets via debug endpoint. Identify failing name patterns. Add to abbreviation map or stripping logic.
**Files:** `utils/prediction_market_matching.py` (_CITY_ABBREV_TO_NAME, _expand_team_search_terms)

#### 1c. MMA Polymarket 25% → 70%+
**Problem:** Unknown — couldn't sample MMA-specific markets from the debug endpoint (random sample across all 21K unlinked Polymarket). Need targeted investigation.
**Fix:** Add sport filter to debug endpoint OR direct DB query. Then diagnose name patterns.
**Files:** `routes/admin.py` (debug endpoint), `utils/prediction_market_matching.py`

#### 1d. Kalshi team aliases for championship grids (R3)
**Problem:** Kalshi uses "A's", "Los Angeles D", "New York Y" as outcome labels in championship/playoff markets. These don't match our team names, causing sparse Playoff Path cards.
**Fix:** Write admin endpoint that queries Kalshi playoff qualifier markets, extracts all 30 outcome names per sport, and adds missing ones as `Team.alternate_names`. Do for MLB, NBA, NHL, NFL.
**Files:** `routes/admin.py` (new endpoint), `Team.alternate_names` column

---

### 2. Player Prop Headshots (R1)
**Status:** Name matching shipped April 19 (stat suffix stripping). Headshots still not appearing — the API response doesn't include `espn_player_id` or `headshot_url` from the `player_metadata` dict built in `routes/events.py`.
**Fix:** 2 lines in backend (add fields to response dict) + 2 lines in frontend (pass props through to PlayerStatCard).
**Files:** `routes/events.py` (~L3050), `frontend/components/RelatedFutures.tsx` (StatPropsSection)
**Parallel Safety:** Yellow

---

### 3. Name Normalization Consolidation
6 independent team/name normalization implementations → 1 canonical module. Mechanical refactor, no behavior changes.
**Files:** `utils/name_normalization.py`, `routes/playoffs.py`, `routes/golf.py`, `routes/oscars.py`, `services/datagolf_api.py`, `tasks/mlb_sync.py`
**Parallel Safety:** Yellow

---

### 4. API Client Base Class
7 API services duplicate identical `__init__`, `close()`, HTTP client management. Extract `BaseAPIClient`.
**Files:** `services/base_api.py` (new), all 7 service files
**Parallel Safety:** Yellow

---

## Tier 2 — Important But Bigger Scope

### 5. Break Up God Functions
5 functions over 400 lines. Do one per session:
- **5a.** `get_playoff_grid()` (847 lines in `routes/playoffs.py`) → extract to `services/playoff_grid.py`
- **5b.** `get_related_futures()` (771 lines in `routes/events.py`) → extract to `services/related_futures.py`
- **5c.** `_sync_espn_live_events()` (804 lines in `tasks/espn_sync.py`) → extract helper functions
- **5d.** `_match_prediction_markets()` (650+ lines in `tasks/prediction_market_matching.py`) → simplify with Event Registry
**Parallel Safety:** Yellow (one function at a time)

### 6. Golf Data Quality
1 remaining bug: Tour misclassification (Hainan = Asian Tour, not PGA Tour) — seasonal, not reproducible.
All other 6 bugs fixed (April 17-19).

### 7. Site Navigation Hierarchy (B1)
`/basketball/nba` hierarchy instead of flat `/playoffs/nba`. Blocked on golf strategy decisions.
**Parallel Safety:** Red (restructures frontend routing)

### 8. Playoff Series Matchup Markets
Polymarket has rich playoff series markets ("Celtics vs Cavaliers"). Need: stage classification, grid column, event detail display, trend charts.
**Files:** `config/league_configs.py`, `utils/tournament_stages.py`, `routes/playoffs.py`

---

## Tier 3 — Valuable But Can Wait

| Item | What | Depends on |
|------|------|-----------|
| **Evolution Chart** | Combined multi-source probability trend line | Source coverage (#1 shipped) |
| **Line Movement v2** | Causal analysis, key moment identification | Nothing |
| **Freshness-Weighted Blending** | Time-decay for stale prediction market prices | More eval data |
| **DS/Analytics Infrastructure** | Analytical columns, `v_completed_events` view, Brier scores | Migration slot |
| **Golf Tournament Related Futures** | "Bigger Picture" section on tournament detail | Nothing |
| **Golf Evolution Chart** | Tournament-aware time ranges, round markers | Nothing |

---

## Tier 4 — Someday / Maybe

- Entity pages (`/[sport]/[league]/[team]`) — SEO upside, depends on B1
- Win totals column in championship grid
- Awards/props cards on league pages (MVP, DPOY, ROY)
- TV Mode v2 — Design complete, prototype exists
- "The Market Was Wrong" v2 — AI narrative generation
- Related Futures Phase 5 — Bidirectional: futures detail shows relevant events
- iOS beyond parity — App Store, widgets, background refresh, push, share extension
- Apple Watch / Apple TV apps
- Weather visualization — prediction market weather maps

---

## Shipped Architecture (Reference)

| Initiative | Status | Key files |
|-----------|--------|-----------|
| Event Registry | Shipped April 16 | `services/event_registry.py` |
| League Context Service (B2) | Shipped April 14-15 | `services/league_context.py` |
| Trade Volume (B4) | Shipped April 14-15 | Internal signal only |
| Game Prop Linking (1C core) | Shipped April 19-20 | `tasks/prediction_market_matching.py`, `utils/prediction_market_matching.py` |
| API Contract Tests (#4) | Shipped April 19 | `tests/integration/` |
| External API Fixture Tests (#9) | Shipped April 19 | `tests/test_service_*.py`, `tests/fixtures/` |
| ESPN Source Coverage (#1) | Shipped April 16 | All 6 sources write to `win_probability_sources` |

---

## Housekeeping

- **April 21**: Remove WrestleMania code (throwaway prediction game, event is over)
- **May 1**: Delete `frontend/_to-delete/` and `docs/archive/` if nothing broke
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches (old feature/claude branches from Jan-Mar 2026)
