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

### 0. Mystery Shopper Critical Fixes — ALL SHIPPED (April 22)

M1+M3: Golf 100%/0% + LIVE badges, M2: Mobile spinner, M4: Boring props filter,
M11/M12: Period markets + spreads on event detail, Cross-sport prop contamination,
Economics >100% distributions, Weather stale featured market.
Full report: `Manus/mystery_shopper.md`.

---

### 0e. Wire Manus audit results into /health skill — IN PROGRESS
Manus health audit suite built (`Manus/prompts/`, `scripts/manus_health_suite.py`). Next: update the `/health` skill to read `Manus/audit_results/latest/` and surface last audit date + score alongside Sentry/Heroku/CI checks. Flag if last audit is >7 days old.
**Files:** `/health` skill definition, `scripts/manus_health_suite.py`

### 0f. Polymarket CLOB V2 migration — MONITOR (April 28, 2026)
Manus flagged CLOB V2 migration. Investigated April 22: both Gamma and CLOB APIs still working with current field names. We use NO SDK — all raw httpx. CLOB is only used for price history backfill (not critical path). Real risk is if **Gamma API** (`gamma-api.polymarket.com`) changes field names or pagination. Monitor around April 28.
**Action:** Re-test both endpoints on April 27. If Gamma breaks, update field mappings in `services/polymarket_api.py`.
**Files:** `services/polymarket_api.py`, `tasks/polymarket.py`

### ~~0g. Kalshi API base URL migration~~ — FALSE ALARM
Already using `api.elections.kalshi.com`. Verified April 22.

### ~~0h. DataGolf deprecated endpoint~~ — FALSE ALARM
We don't use `live-strokes-gained`. We use `preds/in-play`. Verified April 22.

---

### 0t. Chart Timing Quality — 3 Issues (April 22, 2026)

Discovered via `scripts/audit_event_timing.py` — 45 completed events audited across 17 sport/league combos.
Full audit baseline: `scripts/audit_results/timing_latest.json`. Manus visual prompt: `Manus/prompts/chart_timing_audit.md`.

#### ~~0t-1. Prediction Market Snapshots Bleed Past Game End~~ — SHIPPED (April 22)

Fixed in two passes:
1. `smartEndTime` excludes kalshi/polymarket/aggregate_line — only ESPN + stat_model used as game-end signals. Backend PM matching Phase 2 no longer writes snapshots for completed events.
2. Added `completed_at` column to Event model. Set from ESPN ("post"/"final"), Odds API (`completed` flag), StatPal (`statpal_end_time`), and staleness detection. History API returns `completed_at`; frontend uses it as authoritative chart end boundary. No guessing — if we don't know when the game ended, we don't clip.

Result: NBA duration 4.32x→1.07x, MLB 3.31x→0.88x, findings 113→64.

#### 0t-2. 47% of Events Have Zero Period Markers

**Problem:** 21/45 completed events have no game state indicators (period/quarter/inning vertical lines on charts). All are non-ESPN events: soccer, tennis, KBO/NPB baseball. No markers = no context.

**Current coverage:** ESPN-matched events have markers via `espn_history.period` + `game_state_backfill.py`. Non-ESPN events have nothing.

**Fix options (needs investigation):**
- Can StatPal provide period/half data for these events?
- Can we match more events to ESPN? (the coverage gap might be addressable)
- For sports like soccer, official APIs (e.g., API-Football) provide halftime timestamps we could consume.
- Do NOT generate synthetic/guessed markers — only use authoritative sources.

**Files:** `backend/app/tasks/game_state_backfill.py`, `backend/app/routes/events.py` (history endpoint period_markers derivation)
**Parallel Safety:** Green (new logic, no existing code modified)

#### 0t-3. 96% Chart Domain Mismatch (Odds vs Score Charts)

**Problem:** Odds chart and score differential chart have different x-axis domains on almost every event. Two flavors:
- **No score data at all** (17 events) — non-ESPN events without ScoreSnapshots, so score chart is empty
- **Massive end divergence** (17 events) — odds chart extends to next-day Kalshi/Polymarket data, score chart stops at game end

**Root cause:** Fix 0t-1 (prediction market bleed) will resolve the massive-end-divergence flavor. The no-score-data flavor is structural — those events only have Odds API data (no ESPN), and Odds API score polling is disabled for ESPN-covered sports (but these are non-ESPN events that never get scores at all).

**Fix:** After 0t-1 ships, re-run audit to measure remaining mismatch. If still >20%, investigate whether `onRenderedDomain` callback timing is an issue.

**Files:** `frontend/components/OddsChart.tsx` (onRenderedDomain), `frontend/components/ScoreDifferentialChart.tsx:339-366`
**Parallel Safety:** Green

#### 0t-bonus. Soccer EFL/League 2: 53-Minute Late Start

**Problem:** 4 EFL Championship and League 2 events show data starting 53 minutes after `commence_time`. Likely a timezone or commence_time source issue specific to English lower-league soccer.

**Fix:** Investigate `commence_time_source` for these events. If it's Odds API, check whether their times are off by ~1 hour (BST/UTC confusion).

**Files:** `backend/app/services/event_registry.py`, `backend/app/tasks/sports.py`
**Parallel Safety:** Green

---

### 1. Improve Game Prop Link Rate (1C continuation)

**Goal:** Push basketball, baseball, hockey to >85% open link rate.

**What's already shipped (April 19-20):**
- Ticker-derived team names, ILIKE pattern expansion, city abbreviation map (65 entries)
- `sport_id` propagation, `llm_sport_category` correction from ticker
- Matching frequency 4h → 1h, limit 200 → 500
- Link rate dashboard + API endpoint
- 324 prediction market matching tests

**Remaining sub-items (in priority order):**

#### 1a. Basketball 57% → 85%+
**Action:** Monitor. If still <75% by April 25, diagnose specific failing markets via debug endpoint.

#### 1b. Hockey 52% → 80%+
**Fix:** Sample 20 unlinked open NHL markets. Identify failing name patterns. Add to abbreviation map.
**Files:** `utils/prediction_market_matching.py`

#### 1c. MMA Polymarket 25% → 70%+
**Fix:** Add sport filter to debug endpoint, then diagnose name patterns.

#### 1d. Kalshi team aliases for championship grids (R3)
**Fix:** Admin endpoint to extract all 30 Kalshi outcome names per sport, add as `Team.alternate_names`.

---

## Active Sentry Issues (April 22, 2026)

**Monitor / low priority:**
| ID | Events | Status |
|----|--------|--------|
| N+1 Query warnings (GA, HN, FY, 5, 3, J1, JD, G7) | various | Sentry performance warnings, not errors. Address during deeper god function refactoring. |
| Redis ConnectionError (E, JJ, M, EQ) | various | Transient Redis connection drops. Heroku Redis recovers automatically. |
| WorkerLost/SIGTERM (1, 2) | 1,868 | Normal Celery worker recycling (max-memory-per-child). Not a bug. |
| TimeLimitExceeded (J, K) | 917 | Polymarket poll exceeds 300s occasionally. Increase time limit or optimize. |
| aussierules_other (JP) | 4 | Unknown sport key. Add to `sport_keys.py` mapping. |
| PendingRollbackError (JN) | 3 | Session in bad state after prior error. Related to session-during-API pattern. |
| DataGolf errors (HV, HW, HY) | various | DataGolf API 400s for `opp` (non-PGA) tours. Known limitation. |

**Session-leak audit:** 2 files still hold sessions during API calls (`odds_polling.py:462→613`, `espn_sync.py:~254→325`). Fix during deeper god function refactoring.

---

## Triage Process

**Cadence:** Weekly Sentry scan. Production-down alerts get immediate attention.

**3 buckets:** (1) **Fix now** — user-visible or >10 events/day → Tier 1. (2) **Backlog** — recurring but low-frequency → Tier 2/3. (3) **Archive** — handled exceptions, digests, transient → resolve in Sentry.

**Preventing silent CI breakage:** Enable GitHub branch protection on `master` requiring CI status check. Repo → Settings → Branches → Require status checks.

**Tools available:** Heroku CLI (`heroku`), Sentry API (`$SENTRY_AUTH_TOKEN`), GitHub CLI (`gh`). Session health check in CLAUDE.md runs at every session start.

---

## Mystery Shopper Findings (April 22, 2026 — Manus AI Audit)

Manus visited every major page on bainluck.com as a first-time user. Full report: `Manus/mystery_shopper.md`.

### Critical (user-facing, broken)

| # | Finding | Page | Severity | Root cause hypothesis |
|---|---------|------|----------|----------------------|
| M1 | **Golf tournaments: 100%/0% probability** — single golfer at 100%, all others at 0% across Zurich Classic, Volvo China Open, and future majors | Golf, Feed | **CRITICAL** | DataGolf prob=1.0 for completed event winners leaking into upcoming events, OR stale tournament data not rotating after event completion |
| M2 | **Event detail doesn't load on mobile** — 375px viewport shows endless "Loading event..." spinner | Event Detail | **CRITICAL** | JavaScript execution issue on mobile — likely chart rendering timeout or memory issue with large datasets |
| M3 | **Future golf majors marked as "LIVE"** — PGA Championship, U.S. Open, The Open all showing LIVE status | Feed, Golf | **HIGH** | DataGolf schedule matching incorrectly marking future events as current |
| M4 | **Player props showing 97-98% uninteresting thresholds** — "2 home runs: 98% chance" for every player | Event Detail | **HIGH** | No filter for props where the interesting side is <5%. Shows the "No" probability instead of hiding boring props |

### Warning (data quality, confusing but not broken)

| # | Finding | Page | Severity | Root cause hypothesis |
|---|---------|------|----------|----------------------|
| M5 | **Tiger Woods -57.5% daily change** on a future event | Feed | Medium | Stale trend data from a resolved market being shown on an upcoming market |
| M6 | **Weather: LA showing 33°F** in April | Weather | Medium | Possible C/F conversion error or wrong city data |
| M7 | **Economics: recession showing "30" without %** | Economics | Medium | Missing percentage suffix in display component |
| M8 | **Economics: CPI distribution sums >100%** | Economics | Medium | Independent binary markets visualized as a single distribution |
| M9 | **Weather: "NYC temperature Apr 15" still featured** — 7 days stale | Weather | Medium | Featured markets not auto-rotating after resolution |
| M10 | **Event detail: "Projected final: 3 – -1"** — confusing spread notation | Event Detail | Low | Spread displayed as score instead of "+ / -" format |
| M11 | **Half/quarter/period markets not displayed** even when Kalshi has them | Event Detail | **HIGH** | Market types not classified into displayable category — `KXNBAHALF` etc. recently added to ticker map but not routed to UI |
| M12 | **Halftime/spread markets missing from event detail** — only moneyline + total + player props shown | Event Detail | **HIGH** | Related futures endpoint may filter these out or classify them as non-displayable |

### Manus Data Coverage Audit (in progress)

Task 9 running: Manus is checking 3 live games (NBA, NHL, MLB) to compare what Kalshi/Polymarket have vs. what bainluck.com actually displays. Results pending at: https://manus.im/app/M2sAukWQRoYsUMLsu5QfaE

---

## Tier 2 — Important But Bigger Scope

### 2. God Functions — Deeper Extraction (continuation of Item 6)

**First pass shipped April 21 (5 functions, 82 new tests, 4 new utility modules):**

| Function | Lines | Extracted to | Tests |
|----------|-------|-------------|-------|
| `_score_events` (feed.py) | 466→~300 | `utils/feed_scoring.py` — `compute_base_score()`, `format_event_data()`, `TAG_BOOSTS` | 15 |
| `_sync_espn_live_events` (espn_sync.py) | 897 | 5 module-level helpers: `_espn_names_match_any()`, `get_event_name_variations()`, `get_espn_name_variants()`, `espn_team_matches()` | 16 |
| `get_playoff_grid` (playoffs.py) | 862→~780 | `utils/playoff_grid.py` — `normalize_column_sums()`, `compute_movers()`, `sort_teams_by_championship()`, `is_valid_grid_outcome()` | 25 |
| `get_related_futures` (events.py) | 783→~750 | `utils/related_futures.py` — `dedup_by_merge_group()`, `build_futures_entry()` | 11 |
| `_poll_all_odds` (odds_polling.py) | 638 | `utils/polling_config.py` — `determine_api_params()`, `compute_effective_interval()` | 15 |

**Remaining targets (lower priority — tightly coupled to DB/API):**
| Lines | Function | File | Notes |
|-------|----------|------|-------|
| 686 | `get_golf` | `routes/golf.py` | Golf landing page. Helpers already module-level. Hard to split without DB refactor. |
| 649 | `_match_prediction_markets` | `tasks/prediction_market_matching.py` | Already has 324 tests. Well-structured phases. Low urgency. |
| 595 | `operations_dashboard` | `routes/admin.py` | Admin-only. Low user impact. |
| 580 | `get_playoff_grid` | `routes/futures.py` | Possible duplicate of playoffs.py version — investigate consolidation. |
| 549 | `_build_golf_tour_grid` | `routes/playoffs.py` | Golf-specific grid. |
| 406 | `_get_march_madness_data` | `routes/march_madness.py` | Seasonal — only relevant during March Madness. |
| 384 | `_discover_events` | `tasks/sports.py` | Uses Event Registry. Well-structured. |
| 378 | `get_line_movement_analysis` | `routes/events.py` | Line movement feature. |
| 372 | `_recategorize_other_impl` | `tasks/futures.py` | Admin categorization tool. LLM-heavy. |

**Large route files needing eventual split:**
```
 8,684 lines  admin.py      → sub-routers (ops, audit, data management, debug)
 5,042 lines  events.py     → event detail, related futures, odds history, line movement
 3,539 lines  playoffs.py   → grid building per sport, golf-specific builders
 2,866 lines  futures.py    → futures browsing, progression tables
 2,294 lines  golf.py       → landing page, tournament detail, leaderboard
```

**Parallel Safety:** Yellow (one function at a time)

---

### 3. Golf Data Quality
1 remaining bug: Tour misclassification (Hainan = Asian Tour, not PGA Tour) — seasonal, not reproducible.
All other 6 bugs fixed (April 17-19).

### 4. Site Navigation Hierarchy (B1)
`/basketball/nba` hierarchy instead of flat `/playoffs/nba`. Blocked on golf strategy decisions.
**Parallel Safety:** Red (restructures frontend routing)

### 5. Playoff Series Matchup Markets

Polymarket has rich playoff series markets ("Celtics vs Cavaliers"). Need: stage classification in `tournament_stages.py`, grid column, event detail display, trend charts. Timely with NBA/NHL playoffs in progress.

**Files:** `config/league_configs.py`, `utils/tournament_stages.py`, `routes/playoffs.py`, `routes/events.py`
**Parallel Safety:** Yellow

### 6. API Route Contract Tests — Expand Coverage

110 contract tests shipped (April 21). Expand to test with seeded data (not just empty DB):
- Feed: events with probabilities, scoring verification
- Events: detail response shape with full data
- Playoffs: column data, probability sums, monotonicity
- Related futures: market grouping, dedup, gender filtering

**Files:** `tests/integration/` (existing files)
**Parallel Safety:** Green

---

## Tier 3 — Valuable But Can Wait

### Operational Health

| # | Item | What | Files | Safety |
|---|------|------|-------|--------|
| 7 | **Aggregation Quality Monitoring** | Daily task: sample 50 live events, log source count/spread, alert when >20% single-source | `tasks/monitoring.py` (new), `routes/admin.py` | Green |
| 8 | **Source Ingestion Coverage Metrics** | Each poll logs: markets found, matched, classified, rejected + why | `tasks/kalshi.py`, `tasks/polymarket.py`, `tasks/odds_polling.py` | Yellow |
| 9 | **Structured Logging** | JSON logging for Heroku (python-json-logger or structlog) | `app/main.py`, `app/tasks/__init__.py` | Yellow |
| 10 | **Request Observability** | Request ID middleware, duration logging, slow-query detection | `app/main.py`, `app/services/database.py` | Green |
| 11 | **Hardcoded Conference Maps → Data-Driven** | Pull from `Team.standings_data` instead of static dicts in playoffs.py:35-165 | `routes/playoffs.py` | Yellow |

### Product Features

| # | Item | What | Depends on | Safety |
|---|------|------|-----------|--------|
| 12 | **Evolution Chart: Combined Probability** | Multi-source merged trend line on charts | Nothing | Yellow |
| 13 | **Line Movement Explainer v2** | Causal analysis, key moment identification | Nothing | Green |
| 14 | **Freshness-Weighted Blending** | Time-decay for stale prediction market prices | More eval data | Yellow |
| 15 | **DS/Analytics Infrastructure** | Analytical columns, `v_completed_events` view, Brier scores | Migration slot | Red |
| 16 | **Golf Tournament Related Futures** | "Bigger Picture" section on tournament detail | Nothing | Yellow |
| 17 | **Golf Evolution Chart Redesign** | Tournament-aware time ranges, round markers | Nothing | Green |

---

### 18. Non-Sports Category Pages (Economics, Politics, Tech & Science)

**Goal:** Build themed landing pages aggregating Kalshi + Polymarket markets into consumable dashboards — like the weather page.

**Design constraint:** Programmatic market discovery and grouping. No hardcoded market lists.

**Implementation pattern:** `GET /api/categories/{slug}` endpoint + shared `CategoryPage` frontend component + `config/category_pages.py` per-category config.

**Parallel Safety:** Green (new routes, new pages, no conflicts)

#### 18a. Economics Page — **DESIGN READY, HIGHEST PRIORITY**
9 sub-themes (Inflation/CPI, Federal Reserve, Jobs, GDP/Recession, Markets/Indices, Energy, Housing, Trade/Tariffs, Government/Fiscal). Calendar integration opportunity (data release dates).

#### 18b. Politics & Elections Page
Sub-themes: Presidential 2028, Congressional 2026, Gubernatorial, Policy/Legislation, Supreme Court, International. Lifecycle concern: market expiry at election dates.

#### 18c. Tech & Science Page
Sub-themes: AI/LLMs, Space, Big Tech, Social Media, Science/Health. Spiky (viral) rather than steady (monthly reports).

---

## Tier 4 — Someday / Maybe

- Entity pages (`/[sport]/[league]/[team]`) — SEO upside, depends on B1
- Win totals column in championship grid
- Awards/props cards on league pages (MVP, DPOY, ROY)
- TV Mode v2 — Design complete, prototype exists
- "The Market Was Wrong" v2 — AI narrative generation
- Related Futures Phase 5 — Bidirectional
- Frontend tests — Jest config exists, zero test files
- iOS tests — ViewModels with deterministic state logic
- iOS beyond parity — App Store, widgets, push, share extension
- Apple Watch / Apple TV apps
- Weather visualization — prediction market weather maps

---

## Housekeeping

### WrestleMania — **DONE (April 21)**
Archive: `docs/archive/wrestlemania-reference.md`. All runtime code deleted. DB tables preserved.

### Other
- **May 1**: Delete `frontend/_to-delete/` if nothing broke
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches
- Code review reference: `.claude/plans/mutable-cooking-ember.md`
