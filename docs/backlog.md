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
6 independent team/name normalization implementations → 1 canonical module. Mechanical refactor, no behavior changes. Today's grid health session proved this matters — "postseason" vs "playoffs" broke matching for an entire column because normalization wasn't centralized.
**Files:** `utils/name_normalization.py`, `routes/playoffs.py`, `routes/golf.py`, `routes/oscars.py`, `services/datagolf_api.py`, `tasks/mlb_sync.py`
**Parallel Safety:** Yellow

---

### 4. API Client Base Class
7 API services duplicate identical `__init__`, `close()`, HTTP client management. Extract `BaseAPIClient`.
**Files:** `services/base_api.py` (new), all 7 service files
**Parallel Safety:** Yellow

---

## Tier 2 — Important But Bigger Scope

### 5. Break Up God Functions + Large Route Files

**Problem:** 15 functions over 300 lines (3 over 800). 5 route files over 2,000 lines (`admin.py` alone is 8,684). These mix querying, business logic, data transformation, and response formatting in one scope. Debugging is archaeology; refactoring is risky without route-level tests (see Item 9).

**Prerequisite:** Do Item 9 (API Route Contract Tests) first for the endpoint you're about to refactor. Otherwise you're refactoring blind.

**The full inventory (do one per session, start with highest-line-count):**
| Lines | Function | File | Priority | Why |
|-------|----------|------|----------|-----|
| 897 | `_sync_espn_live_events` | `tasks/espn_sync.py` | High | ESPN will change their undocumented API. When they do, debugging an 897-line function will be brutal. Extract: ESPN response parsing, game state extraction, snapshot creation, win probability extraction — each becomes a testable function with fixture data. |
| 862 | `get_playoff_grid` | `routes/playoffs.py` | High | Most-touched grid code. Does team resolution, market discovery, grid building, probability merging, monotonicity enforcement, and response formatting in one function. Extract to `services/playoff_grid.py` with `resolve_teams()`, `discover_markets()`, `build_grid()`, `merge_probabilities()`, `enforce_monotonicity()`. Route handler should be <50 lines. |
| 783 | `get_related_futures` | `routes/events.py` | High | Serves Priority 4 (related futures). Does market discovery, filtering, grouping, deduplication, and response formatting. The tier-aware loading logic (tiers 1-4 sport-wide, tier 5 per-event) is clever but undocumented — a code comment explaining WHY would prevent someone from "simplifying" it later. Extract to `services/related_futures.py`. |
| 686 | `get_golf` | `routes/golf.py` | Medium | Golf landing page. Mixes DataGolf API calls, tournament matching, leaderboard building, and response formatting. |
| 649 | `_match_prediction_markets` | `tasks/prediction_market_matching.py` | Medium | Event Registry shipped (April 16) and replaces much of the duplicate matching logic. Simplify to: fetch markets → registry lookup → write snapshots. |
| 637 | `_poll_all_odds` | `tasks/odds_polling.py` | Low | Stable, rarely changes. Core odds polling loop. |
| 595 | `operations_dashboard` | `routes/admin.py` | Low | Admin-only dashboard builder. Low user impact. |
| 580 | `get_playoff_grid` | `routes/futures.py` | Medium | Appears to be a duplicate/older version of the playoffs.py grid builder. Investigate whether this can be consolidated. |
| 549 | `_build_golf_tour_grid` | `routes/playoffs.py` | Low | Golf-specific grid builder. |
| 466 | `_score_events` | `routes/feed.py` | **High** | **This is the feed ranking function — it determines what users see first. It's completely untested.** Arguably the highest-leverage function to both test AND extract, since it directly controls the user experience. |
| 406 | `_get_march_madness_data` | `routes/march_madness.py` | Low | Seasonal — only relevant during March Madness. |
| 384 | `_discover_events` | `tasks/sports.py` | Low | Event discovery task. |
| 378 | `get_line_movement_analysis` | `routes/events.py` | Low | Line movement feature. |
| 372 | `_recategorize_other_impl` | `tasks/futures.py` | Low | Admin categorization tool. |

**Large route files (context for the above):**
```
 8,684 lines  admin.py      — Should be split into sub-routers (ops, audit, data management, debug)
 5,042 lines  events.py     — event detail, related futures, odds history, line movement all in one file
 3,539 lines  playoffs.py   — grid building for all sports + golf-specific builders
 2,866 lines  futures.py    — futures browsing, progression tables, duplicate grid builder
 2,294 lines  golf.py       — golf landing page, tournament detail, leaderboard
```

**Extraction pattern (repeat for each function):**
1. Write route-level contract test first (Item 9)
2. Extract business logic into `services/` module with pure functions
3. Route handler becomes a thin orchestrator (<50 lines)
4. Run existing tests + new contract test to verify
5. One function per session — never parallelize refactoring on the same file

**Prompt (example for 5a — ESPN sync):**
> Read `tasks/espn_sync.py`, function `_sync_espn_live_events()` (897 lines, starts at line 137). It does: ESPN API calls, response parsing, game state extraction, event matching, snapshot creation, win probability extraction, and error handling — all in one scope.
>
> Extract into testable functions: `_parse_espn_competition()`, `_extract_game_state()`, `_create_espn_snapshots()`, `_extract_win_probability()`. Each should take parsed data and return structured results. The main sync function becomes an orchestrator calling these helpers.
>
> Add tests with fixture data (use existing `tests/fixtures/` pattern) so that when ESPN changes their API format, we can update the fixture and see exactly what breaks.
>
> INTERFERENCE RULES: Do NOT modify other task files. Do NOT change the Celery task registration.

**Parallel Safety:** Yellow (one function at a time)

---

### 6. Golf Data Quality
1 remaining bug: Tour misclassification (Hainan = Asian Tour, not PGA Tour) — seasonal, not reproducible.
All other 6 bugs fixed (April 17-19).

### 7. Site Navigation Hierarchy (B1)
`/basketball/nba` hierarchy instead of flat `/playoffs/nba`. Blocked on golf strategy decisions.
**Parallel Safety:** Red (restructures frontend routing)

### 8. Playoff Series Matchup Markets

**Opportunity:** Polymarket has rich playoff series matchup markets (e.g., "Celtics vs Cavaliers" series winner). Source: `polymarket.com/sports/nba/props`. These are perfect for two surfaces:

1. **Championship grid**: New column(s) showing current-round series win probability per team. Could be a "Current Round" or "Series" column that dynamically updates as rounds progress.
2. **Event detail pages**: Related Futures section could show the series matchup market alongside individual game odds, giving users the "bigger picture" context for any playoff game.

**Implementation sketch:**
- **Stage classification**: Add a `series` or `current_round` stage to `tournament_stages.py` for basketball/hockey. Patterns: `r"vs\b"`, `r"series\b"`, `r"advance\b"` (careful not to collide with game-level "vs" — filter by market type/source).
- **Grid column**: Add `GridColumn(key="current_round", label="Series", order=1.5)` — between make_playoffs and conference. Only show when fill rate is meaningful (playoff season).
- **Ingestion**: Polymarket polls should already pick these up. Verify they're classified as the right `llm_sport_category`. May need name-pattern matching to route into the grid.
- **Event detail**: Match series markets to events by team names + playoff round. Show "Series: Celtics 72% — Cavaliers 28%" on any Celtics playoff game detail page.
- **Trend data**: These markets move fast during series — trend charts would be very engaging.

**Open questions:**
- Should the grid show current-round only, or all active series?
- How to handle series that span multiple rounds (team advances, new matchup appears)?
- Should series markets appear as a grid column or as a separate "Active Series" section below the grid?

**Files:** `config/league_configs.py`, `utils/tournament_stages.py`, `routes/playoffs.py`, `routes/events.py` (related futures)
**Parallel Safety:** Yellow

**Prompt:**
> Read `routes/playoffs.py` (grid builder) and `config/league_configs.py`. Polymarket has playoff series matchup markets (e.g., "Celtics vs Cavaliers"). These need to:
> 1. Be classified into a new "current_round" stage in `tournament_stages.py`
> 2. Appear in the championship grid as a dynamic column showing series win probability
> 3. Appear in event detail pages as Related Futures for playoff games
>
> Start by checking what series markets exist in the DB: query `futures_markets` for Polymarket markets with "vs" or "series" in the name and `llm_sport_category` in ('basketball', 'hockey'). Then design the classification patterns and grid column.
>
> INTERFERENCE RULES: Do NOT modify event matching, score tracking, or non-playoff routes.

---

### 9. API Route Contract Tests

**Problem:** Out of 17 route files, only 1 has a corresponding test file (`market_moves`). The 3,121 backend tests are concentrated in utils and domain logic — which is good — but the API contract layer (what JSON shape does `/api/playoffs/nba` actually return?) is completely unverified. One refactor of a god function (Item 5) could silently break the frontend. **This is the prerequisite for safely doing Item 5.**

**What to test (in priority order):**

1. **`/api/feed`** — the home page. This is the first thing every user sees.
   - Response has `events` array with `id`, `home_team`, `away_team`, `home_probability`, `away_probability`
   - Probabilities are 0.0-1.0 decimals, never null for live/scheduled events
   - Status values are from the allowed set (`scheduled`, `live`, `completed`, `closed`)
   - `win_probability_sources` is present and is a dict keyed by source name
   - Feed scoring (`_score_events`, 466 lines, completely untested) correctly prioritizes live > soon > later

2. **`/api/events/{id}`** — event detail page.
   - Aggregated probability in response matches `compute_aggregate_probability()` output
   - Source list includes all contributing sources with timestamps
   - Chart data (`win_prob_history`) is chronologically ordered
   - Game state fields (period, clock, score) are present for live events

3. **`/api/playoffs/{league}`** — championship grid.
   - Response has `teams` array with `name`, `cells` dict
   - Each cell has `merged_probability` (0.0-1.0), `sources` array, `trend_24h`
   - Championship column probabilities sum to ~100% (within tolerance)
   - `columns` array matches league config
   - Monotonicity holds: P(earlier round) >= P(later round)

4. **`/api/events/{id}/related-futures`** — related futures sidebar.
   - Markets are grouped by category (championship, conference, player props, etc.)
   - No duplicate markets within a group
   - Tier-aware loading: tiers 1-4 load sport-wide, tier 5 loads per-event
   - Gender filtering: men's events don't show women's futures

**Approach:** Use the existing test infrastructure (`conftest.py` fixtures, async test patterns). Create test events + markets in the test database, hit the endpoint via `httpx.AsyncClient`, assert response shape. Not mocking — test the full route handler.

**Files:** `tests/test_route_feed.py`, `tests/test_route_events.py`, `tests/test_route_playoffs.py`, `tests/test_route_related_futures.py` (all new)
**Parallel Safety:** Green (read-only, no file conflicts — always safe to parallelize)

**Prompt:**
> Write API contract tests for the 4 highest-traffic endpoints. Use `httpx.AsyncClient` with the FastAPI test client. Create test fixtures (events, teams, markets, odds snapshots) in conftest.py. For each endpoint:
> 1. Test the happy path response shape (all expected keys present, correct types)
> 2. Test probability ranges (0.0-1.0, no nulls where required)
> 3. Test edge cases (no data, completed events, single-source events)
>
> Start with `/api/feed` since it's the home page and `_score_events` (466 lines) is completely untested.
>
> Run: `python3 -m pytest tests/test_route_feed.py -v`
>
> INTERFERENCE RULES: Do NOT modify any route, task, or service files. Tests only.

---

## Tier 3 — Valuable But Can Wait

### Operational Health (from April 20 code review)

#### 10. Aggregation Quality Monitoring
**Problem:** Currently no way to know when a source goes dark until users notice bad probabilities. During the March Odds API quota exhaustion, we only knew because someone checked manually.
**Fix:** Daily Celery task that samples 50 live/scheduled events and logs: how many sources contributed per event, spread between sources (max-min), events with only 1 source, events with 0 sources. Push stats to Sentry/ODS or a Redis key for the admin dashboard. Alert (Sentry) when >20% of live events are single-source.
**Files:** `tasks/monitoring.py` (new), `routes/admin.py` (add dashboard widget)
**Serves:** Priority 1 (best aggregated probabilities)
**Parallel Safety:** Green

#### 11. Source Ingestion Coverage Metrics
**Problem:** Each Kalshi/Polymarket/Odds API poll runs silently. When Polymarket's MLB make-postseason market exists but isn't reaching the grid, there's no log to explain why. Today's grid health session (April 19-20) took 2+ hours of manual investigation.
**Fix:** Each poll task logs a coverage summary at the end: total markets found, markets matched to events (with count by sport), markets classified to grid columns, markets rejected and why (with top 5 rejection reasons). Store in Redis for admin dashboard display.
**Files:** `tasks/kalshi.py`, `tasks/polymarket.py`, `tasks/odds_polling.py`, `tasks/prediction_market_matching.py`
**Serves:** Priority 3 (cross-source comparison)
**Parallel Safety:** Yellow (touches task files)

#### 12. Structured Logging
**Problem:** Backend uses plain-text Python logging. In Heroku's log stream with multiple Celery workers, it's nearly impossible to follow a single request or task execution. Debugging requires `heroku logs --tail | grep` and prayer.
**Fix:** Switch to JSON structured logging (python-json-logger or structlog). Include: timestamp, level, logger name, request_id (see Item 13), task_name, sport, event_id. Heroku's Logplex will ingest JSON lines and tools like Papertrail/LogDNA can parse them.
**Files:** `app/main.py` (logging config), `app/tasks/__init__.py` (Celery logging)
**Parallel Safety:** Yellow

#### 13. Request Observability
**Problem:** No request ID middleware, no request duration logging, no slow-query detection. When a user reports "the page was slow," there's no way to correlate to a specific API call or identify which database query was the bottleneck.
**Fix:** Add FastAPI middleware that: (1) generates a UUID request ID, (2) attaches it to the response header `X-Request-ID`, (3) logs request method, path, duration, status code. Optionally: log queries that take >500ms via SQLAlchemy event hooks.
**Files:** `app/main.py` (middleware), `app/services/database.py` (optional query logging)
**Parallel Safety:** Green

#### 14. Hardcoded Conference Maps → Data-Driven
**Problem:** `playoffs.py:35-165` has 4 static Python dicts mapping every team to its conference/division for NBA, NFL, MLB, NHL. When the Utah Jazz became the Utah Mammoth, these needed manual updates. Every expansion, relocation, or rebrand requires a code change.
**Fix:** Pull conference/division from `Team.standings_data` (already populated by StatPal sync). Fall back to the static dicts only when standings data is missing. This makes the system self-healing as teams change.
**Files:** `routes/playoffs.py` (lines 35-165)
**Parallel Safety:** Yellow

### Product Features

#### 15. Evolution Chart: Combined Probability
**Problem:** Chart shows single-source probability over time. Grid already shows merged multi-source probability. The chart should show the merged trend, so users see how the aggregate probability evolved — not just one source's view.
**Fix:** Compute time-series aggregate from `futures_odds_snapshots` across sources, using the same `_merge_probabilities` logic. Return as a new `merged_history` array in the chart data response.
**Files:** `routes/events.py` (history endpoint), `routes/playoffs.py` (trend chart builder)
**Depends on:** Source coverage (#1 shipped)
**Parallel Safety:** Yellow

#### 16. Line Movement Explainer v2
**Problem:** v1 was disabled because it only stated the obvious ("Team X won, odds went up"). Needs: key moment identification, causal analysis (scoring plays → probability shifts), context from game state.
**Files:** `services/llm.py`, `routes/events.py` (line movement endpoint)
**Parallel Safety:** Green

#### 17. Freshness-Weighted Blending
**Problem:** Stale prediction market prices (Kalshi 5h old) weighted equally with fresh model data (DataGolf updated 2 min ago). During live play, this makes the merged probability misleading.
**Design:** Memory file has full analysis (`project_freshness_blending.md`). Key insight: `last_updated` reflects poll time, not last price change — need to track actual price movement.
**Status:** Waiting on more eval data from live play sessions.
**Parallel Safety:** Yellow

#### 18. DS/Analytics Infrastructure
Analytical columns (`ended_at`, `final_home_probability`, `event_results`, `season`). Denormalize `sport_group`. Create `v_completed_events` view. Enables "Who's Right?" Brier score analysis.
**Parallel Safety:** Red (migrations)

#### 19. Golf Tournament Related Futures
"Bigger Picture" section on tournament detail pages. Markets exist on Kalshi/Polymarket (Top 5, Make Cut, H2H, round leaders, nationality props). Must match by tournament key (NOT `ILIKE '%Masters%'` which leaks esports).
**Parallel Safety:** Yellow

#### 20. Golf Evolution Chart Redesign
Multiple problems: "24 Hours" and "Today" time ranges make no sense for golf, round markers needed, tournament-aware time ranges. DataGolf's evolution plot is the gold standard (white background, thin colored lines, clean gridlines — matches our light-mode-only design constraint).
**Parallel Safety:** Green

---

### 21. Non-Sports Category Pages (Economics, Politics, Tech & Science)

**Goal:** Build themed landing pages that aggregate Kalshi + Polymarket markets into consumable, sub-themed dashboards — like we did for the weather page. Each page should feel like a "Bloomberg terminal for normies" for its topic.

**Design constraint:** Every page needs **programmatic market discovery and grouping**, not hardcoded market lists. Markets appear and expire constantly — a page that requires manual curation is a page that rots. The system must:
1. **Detect new markets** as they're ingested from Kalshi/Polymarket polling tasks
2. **Classify into sub-themes** automatically (via LLM category + regex patterns on market names + ticker prefix mapping)
3. **Expire resolved markets** gracefully (show outcome, then archive after N days)
4. **Handle lifecycle changes** — when 2026 election markets resolve, 2028 markets should auto-populate without code changes

**Implementation pattern (reusable across all category pages):**
- Backend: `GET /api/categories/{slug}` endpoint that queries `futures_markets` by `llm_sport_category` + sub-theme classification rules
- Sub-theme classification: regex patterns on market names + Kalshi ticker prefix mapping (e.g., `kxcpi*` → Inflation, `kxfedfunds*` → Fed)
- Frontend: Shared `CategoryPage` component with configurable sub-theme sections, hero stats, trend charts
- Config: `config/category_pages.py` with per-category sub-theme definitions, hero market selection rules, sort/display preferences

**Parallel Safety:** Green (new routes, new frontend pages, no existing file conflicts)

---

#### 21a. Economics Page — **DESIGN READY, HIGHEST PRIORITY**

The strongest candidate: deep markets on both sources, natural sub-themes, evergreen relevance, calendar-driven urgency (monthly data releases), and highly differentiated (nobody visualizes economic prediction markets as a consumer dashboard).

**Sub-themes and known market inventory:**

| Sub-theme | Hero stat | Kalshi markets | Polymarket markets | Ticker patterns |
|-----------|-----------|---------------|-------------------|-----------------|
| **Inflation & CPI** | "72% chance CPI falls below 3%" | Monthly CPI brackets, PCE readings, Argentina/country inflation | Inflation above/below thresholds | `kxcpi*`, `kxpce*`, `kxinflation*` |
| **Federal Reserve** | "64% chance of June rate cut" | Fed funds rate per meeting (Jan-Dec), number of cuts/hikes in 2026 | ECB rate decisions | `kxfedfunds*`, `kxfedcuts*` |
| **Jobs & Employment** | "Unemployment: markets say 4.1%" | Unemployment rate brackets, nonfarm payrolls, jobless claims | Jobs report outcomes | `kxunemployment*`, `kxjobless*`, `kxnonfarm*` |
| **GDP & Recession** | "23% recession probability" | Quarterly GDP brackets, recession Y/N, consecutive negative quarters | Recession timing, GDP growth | `kxgdp*`, `kxrecession*` |
| **Markets & Indices** | "S&P 500 at close today" | Nasdaq-100 daily/weekly price brackets, S&P targets, VIX levels | Daily up/down, weekly range targets | `kxnasdaq*`, `kxsp500*`, `kxvix*` |
| **Energy & Commodities** | "Gas price: 78% stays under $4" | Gas prices (national + California), oil (WTI + Brent), daily/weekly targets | Oil price thresholds | `kxgasprice*`, `kxoil*`, `kxbrent*` |
| **Housing & Mortgages** | "30yr mortgage rate direction" | Mortgage rate brackets, Case-Shiller direction | Mortgage rate thresholds for 2026 | `kxmortgage*`, `kxhousing*` |
| **Trade & Tariffs** | "Will tariffs increase?" | Tariff-related policy markets, trade war outcomes | Tariff policy markets | `kxtariff*`, `kxtrade*` |
| **Government & Fiscal** | "Debt ceiling status" | Government shutdown, debt ceiling, spending bills | Shutdown probability, DOGE savings | `kxshutdown*`, `kxdebt*` |

**Calendar integration opportunity:** A "This Week's Data Releases" section showing which sub-themes have upcoming catalysts (CPI report Tuesday, jobs report Friday, FOMC meeting Wednesday). Markets become more engaging when you know the resolution date.

---

#### 21b. Politics & Elections Page

Deepest market category on both platforms. Risk: every prediction market site does politics. Our differentiation is cross-source probability aggregation + visual clarity.

**Sub-themes:**
| Sub-theme | Kalshi tickers | Polymarket coverage |
|-----------|---------------|-------------------|
| **Presidential 2028** | `kxpres*`, `kxpresnomd*`, `kxpresnomd*` | Nominee odds, approval ratings |
| **Congressional 2026** | `kxhouserace*`, `kxsenaterace*`, `kxhousecontrol*` | Senate/House control, key races |
| **Gubernatorial** | `kxgov*` | State-level races |
| **Policy & Legislation** | `kxbill*`, `kxexecorder*` | Specific bills, executive actions |
| **Supreme Court** | `kxscotus*` | Rulings, retirements |
| **International** | Various | UK, France, Brazil elections |

**Lifecycle concern:** Election markets have a hard expiry (election day). Need automatic transition: 2026 midterm markets → show results → archive → 2028 presidential markets populate naturally. The sub-theme structure (Presidential, Congressional, etc.) is stable across cycles — only the specific markets rotate.

---

#### 21c. Tech & Science Page

Fun, viral-friendly markets. Less structured than economics but more shareable.

**Sub-themes:**
| Sub-theme | Example markets |
|-----------|----------------|
| **AI & LLMs** | GPT-5 release, AI regulation, benchmark milestones, Anthropic/OpenAI valuations |
| **Space** | SpaceX launches, Starship milestones, Artemis, Mars mission timelines |
| **Big Tech** | Earnings beats, antitrust rulings, TikTok ban, product launches |
| **Social Media** | Platform user milestones, regulatory actions, CEO changes |
| **Science & Health** | FDA approvals, fusion milestones, pandemic-related |
| **Crypto Overlap** | Bitcoin/Ethereum prices (from crypto category) that have tech implications |

**Note:** Kalshi has `kxai*`, `kxtiktok*`, `kxtesla*` ticker patterns. Polymarket has rich tech/AI coverage. Markets here tend to be spiky (viral moments) rather than steady (monthly reports), so the page design needs to handle variable density.

---

## Tier 4 — Someday / Maybe

- Entity pages (`/[sport]/[league]/[team]`) — SEO upside, depends on B1
- Win totals column in championship grid
- Awards/props cards on league pages (MVP, DPOY, ROY)
- TV Mode v2 — Design complete, prototype exists
- "The Market Was Wrong" v2 — AI narrative generation
- Related Futures Phase 5 — Bidirectional: futures detail shows relevant events
- Frontend tests — Jest config exists, zero test files. FeedCard, probability formatting, status-dependent UI are prime candidates
- iOS tests — ViewModels with deterministic state logic (debouncing, search) could be tested trivially
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
| Admin Auth Security Fix | Shipped April 20 | `routes/admin.py` — `_check_admin_secret()` now rejects when `ADMIN_SECRET` unset |
| Grid Health: Normalization + Multi-Source | Shipped April 19-20 | Postseason patterns, Kalshi ticker prefixes, championship normalization, division rule ordering |

---

## Code Review Findings (April 20, 2026)

Full writeup: `.claude/plans/mutable-cooking-ember.md`

**What's strong:** Aggregation math, Event Registry architecture, database indexing, quota management, iOS concurrency patterns, frontend data fetching.

**Priority-specific technical guidance:**
1. **Best aggregated probabilities:** Test the aggregation *contract* (route responses), not just the math. Add aggregation quality monitoring (Tier 3).
2. **Odds vs algorithms:** `win_probability_sources` JSONB has no schema validation — a Pydantic model would catch corruption. ESPN sync (897-line function) is the most brittle integration.
3. **Cross-source comparison:** Grid health audit should run on a schedule (not just on-demand). Source ingestion tasks should report coverage metrics (Tier 3).
4. **Related futures:** `get_related_futures` (783 lines) is the bottleneck. Extract to `services/related_futures.py`. Document the tier-aware loading logic.
5. **Team/league odds:** League config matching rules are fragile (proven by today's postseason/playoffs mismatch). Add a normalization step before pattern matching — centralize in Item 3.
6. **Discovery & engagement:** `_score_events` (466 lines, completely untested) is the feed ranking function. Highest-leverage function to test — it controls what users see first.

---

## Housekeeping

- **April 21**: Remove WrestleMania code (throwaway prediction game, event is over)
- **May 1**: Delete `frontend/_to-delete/` and `docs/archive/` if nothing broke
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches (old feature/claude branches from Jan-Mar 2026)
