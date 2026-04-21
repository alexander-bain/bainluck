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

## Active Sentry Issues (April 21, 2026)

**Fixed this session (April 19-21):**
| ID | Events | Fix | Commit |
|----|--------|-----|--------|
| BAINLUCK-JK (DBAPIError) | 23 | Pool limits added to task engine (`base.py`): pool_size=3, max_overflow=5, pool_recycle=1800 | `283fec8` |
| BAINLUCK-JG (AttributeError: sport_key) | 2,038 | `Event.sport_key` → `Sport.key` join in odds_polling.py score-fetch optimization | `8191ad5` |
| BAINLUCK-JH (UnboundLocalError: _sql_update) | 1,298 | Moved `from sqlalchemy import update as _sql_update` from function-level to top-level import in espn_sync.py (Python 3.12 scoping issue) | `453ce7f` |
| BAINLUCK-JT (AttributeError: espn_event_id) | 27 | `Event.espn_event_id` → `Event.espn_id` in odds_polling.py (same score-fetch block as JG) | `7b73d01` |
| TooManyConnections (WM polling) | — | WrestleMania code removed entirely (-3,686 lines) | `283fec8` |
| Admin auth bypass | — | `_check_admin_secret()` now returns False when `ADMIN_SECRET` unset (was True) | `90a8f8b` |

**Remaining (monitor / low priority):**
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

## Shipped (April 19-21, 2026) — This Session

### Infrastructure & Code Health
| What | Details |
|------|---------|
| **WrestleMania removal** | -3,686 lines. Task, routes, models, scoring, Polymarket service, frontend page + 11 components all deleted. Patterns archived to `docs/archive/wrestlemania-reference.md`. DB tables + Alembic migration preserved. |
| **WrestleMania win probability fix** | Was using stale seed probabilities instead of latest odds snapshots. Daphne showed 100% when she was ~77.5%. Fixed + capped rounding at 99.9%. |
| **Task pool exhaustion fix** | `base.py` task engines had no pool limits (default 15 per worker × 6 workers = 90 connections vs 120 limit). Added pool_size=3, max_overflow=5, pool_recycle=1800. |
| **Admin auth security fix** | `_check_admin_secret()` returned True when ADMIN_SECRET unset. Now returns False. |
| **5 Sentry error fixes** | JK (DBAPIError/pool), JG (Event.sport_key), JH (_sql_update scoping), JT (Event.espn_event_id), TooManyConnections (WM removed). Total: 3,386+ error events eliminated. |
| **Observability tool access** | Heroku CLI, Sentry API, GitHub CLI installed and authenticated. Session health check added to CLAUDE.md. |
| **API route contract tests** | 110 tests across 6 route files (feed, events, playoffs, futures, golf, health). Found and fixed search endpoint count bug. |
| **Name normalization consolidation** | 11 functions → 1 canonical module. strip_diacritics(), normalize_team_name(), match_key(), clean_slug(). 10 files updated. Net -20 lines. |
| **API client base class** | BaseAPIClient in services/base_api.py. Applied to 5 services. |
| **Player prop headshots** | MLB roster sync stores rich dicts with headshot URLs (was plain strings). All 4 major sports now have headshots. |
| **God function refactoring (5 functions)** | _score_events → utils/feed_scoring.py (15 tests), _sync_espn_live_events → 5 module-level helpers (16 tests), get_playoff_grid → utils/playoff_grid.py (25 tests), get_related_futures → utils/related_futures.py (11 tests), _poll_all_odds → utils/polling_config.py (15 tests). Total: 82 new tests, 4 new utility modules. |
| **Bare except / console.log cleanup** | pulse.py: `except:` → `except Exception:`. onboarding/page.tsx: removed console.log. |

### Grid Health
| What | Details |
|------|---------|
| **Championship normalization** | NHL Stanley Cup probabilities normalized from 53.2% → 100% (long-tail teams all floor at 0.1%). |
| **Postseason patterns** | Added "postseason" to all sport stage classifiers + league config matching rules. MLB make_playoffs: Kalshi-only → Kalshi + Polymarket. |
| **Kalshi ticker prefixes** | Added KXNBA/KXNHL/KXMLB external_id_prefixes to league configs. NBA conference: Polymarket-only → Polymarket + Kalshi. |
| **Stanley Cup qualifier pre-check** | "Stanley Cup® Playoff Qualifiers" was matching championship before make_playoffs. Added qualifier/berth keyword pre-check. |
| **MLB division rule ordering** | "NL East Champion" was matching pennant (overly broad `MLB.*(AL|NL)` pattern). Moved division rule above pennant + removed catch-all. |

### Backlog & Process
| What | Details |
|------|---------|
| **Comprehensive code review** | Full writeup at `.claude/plans/mutable-cooking-ember.md`. 7 strengths, 1 critical fix (admin auth), 5 serious issues, 5 moderate issues, 6 priority-specific recommendations. |
| **Backlog integration** | Code review findings folded into backlog (not separate docs). Items numbered, tiered, with prompts and parallel safety tags. |
| **Sentry triage** | All unresolved issues categorized with root cause, severity, disposition. |
| **Triage process** | Added to backlog: weekly cadence, 3-bucket heuristic, CI branch protection recommendation. |
| **Playoff series markets** | Added to Tier 2 backlog with implementation sketch. |

### Stats
| Metric | Start of session | End of session | Delta |
|--------|-----------------|----------------|-------|
| Backend tests | 3,121 | 3,308 | **+187** |
| Integration tests | 33 | 110 | **+77** |
| Utility modules | 24 | 28 | **+4** (feed_scoring, playoff_grid, related_futures, polling_config) |
| Route files with tests | 1/17 | 6/17 | **+5** |
| God functions with extracted logic | 0/15 | 5/15 | **+5** |
| Lines deleted (WM) | — | — | **-3,686** |
| Sentry errors eliminated | — | — | **~3,386 events** |

---

## Code Review Findings (April 20, 2026)

Full writeup: `.claude/plans/mutable-cooking-ember.md`

**What's strong:** Aggregation math, Event Registry architecture, database indexing, quota management, iOS concurrency patterns, frontend data fetching.

**Priority-specific technical guidance:**
1. **Best aggregated probabilities:** Test the aggregation *contract* (route responses), not just the math. Add aggregation quality monitoring (Tier 3).
2. **Odds vs algorithms:** `win_probability_sources` JSONB has no schema validation. ESPN sync (897-line function) is the most brittle integration — helpers now extracted.
3. **Cross-source comparison:** Grid health audit should run on a schedule. Source ingestion tasks should report coverage metrics (Tier 3).
4. **Related futures:** `get_related_futures` dedup logic now extracted + tested. Tier-aware loading still undocumented.
5. **Team/league odds:** League config matching rules proven fragile by postseason/playoffs mismatch. Name normalization now centralized (Item 3 shipped).
6. **Discovery & engagement:** `_score_events` scoring now extracted + tested (15 tests on feed ranking). `TAG_BOOSTS` externalized as testable constant.

---

## Housekeeping

### WrestleMania — **DONE (April 21)**
Archive: `docs/archive/wrestlemania-reference.md`. All runtime code deleted. DB tables preserved.

### Other
- **May 1**: Delete `frontend/_to-delete/` if nothing broke
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches
