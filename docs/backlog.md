# Backlog (SINGLE SOURCE OF TRUTH)

All outstanding work items for Bain Luck. This is the canonical list — no other doc should duplicate it.

**How to use this doc:**
- When items ship, move them to `docs/completed-features.md` with a date and brief description
- When new work is discovered (bugs, ideas, follow-ups), add it here in the right section
- When priorities change, reorder within sections
- Mark items with **SHIPPED** and date when done, then move to completed-features on next cleanup pass

**Item format:**
Each item includes metadata for parallel work planning. `Layer` identifies what part of the codebase it touches. `Touches` lists specific files. `Parallel Safety` indicates whether it's safe to run alongside other work. `Prompt` is a ready-to-paste prompt for starting the item in a Claude Code session.

**Related docs:**
- `docs/completed-features.md` — shipped features log
- `docs/PRD.md` — product vision, ideas under exploration, open questions
- `docs/golf-product-strategy.md` — golf-specific product strategy
- `.claude/plans/mighty-churning-blum.md` — strategic codebase health plan (code review, testing, iOS parity audit)

---

## Quick Reference: What Can Run In Parallel

| If you're working on... | Safe parallel candidates |
|------------------------|------------------------|
| ESPN source coverage (#1) | Items 4, 5, 9 (all Green) |
| Name normalization (#2) | Items 4, 5, 9 (all Green) |
| API base class (#3) | Items 4, 5, 9 (all Green) |
| API contract tests (#4) | Items 2, 3, 5, 7, 9 (anything except same route files) |
| iOS parity (#5) | ANYTHING — always safe |
| God function refactoring (#6) | Items 4, 5, 9 (all Green) |
| Golf data quality (#7) | Items 4, 5, 9 (all Green) |
| No good parallel candidate? | Brainstorm B1 design decisions, or write tests (#4, #9) |

---

## Tier 1 — High Leverage, Do Next

### 1. ESPN + Source Coverage Crisis Investigation
**Layer:** backend-tasks, backend-services
**Touches:** `tasks/espn_sync.py`, `tasks/odds_polling.py`, `services/espn_api.py`, `services/event_registry.py`, `routes/events.py` (read-only)
**Depends on:** Event Registry wiring — **SHIPPED April 16**
**Conflicts with:** Any work on espn_sync.py or odds_polling.py
**Parallel Safety:** Yellow (Event Registry is done, but touches core task files)

**Problem:** ESPN win probability is barely writing — 1 snapshot per sync cycle out of 34 events. 67 ESPN events were "unmatched." Most NBA events showed only StatPal as a source. No events had Kalshi/Polymarket in `win_probability_sources`. The core product promise (multi-source probability) was broken for most events. Event Registry shipping may have fixed some of this — needs verification.

**Acceptance criteria:**
- ESPN match rate >90%
- Win probability snapshots created for all matched ESPN live events
- Betting odds from Odds API appear in `win_probability_sources`
- Feed response includes `win_probability_sources` array
- Kalshi/Polymarket prices flow into `win_probability_sources` for matched events

**Prompt:**
> We have a source coverage crisis. The core product shows aggregated multi-source probabilities, but most events only have 1 source. The Event Registry was just shipped (all 5 phases) which should help with matching — but we need to verify and fix remaining gaps.
>
> 1. Read `tasks/espn_sync.py` — it now uses Event Registry. Check: are ESPN events being matched at a high rate? Look at the audit logs from recent runs if available. Check if win_prob_snapshots are being created for matched events.
> 2. Read `tasks/odds_polling.py` — are betting odds being written to `win_probability_sources` on the event? Or only to `odds_snapshots`? The aggregate probability system needs data in `win_probability_sources`.
> 3. Read `routes/events.py` and `routes/feed.py` — is `win_probability_sources` included in the feed API response? Check serialization.
> 4. Read `tasks/prediction_market_matching.py` — are Kalshi/Polymarket prices flowing into `win_probability_sources`?
> 5. Hit the production API to verify: `curl "https://api.bainluck.com/api/events?sport=basketball_nba" | python3 -m json.tool | head -50` — check if events have multiple sources.
>
> For each issue found, fix it. Run tests after each fix.
>
> INTERFERENCE RULES: Do NOT modify `services/event_registry.py` — it was just shipped and is stable.

---

### 2. Name Normalization Consolidation
**Layer:** backend-utils, backend-routes, backend-tasks, backend-services
**Touches:** `utils/name_normalization.py` (primary), `routes/playoffs.py`, `routes/golf.py`, `routes/oscars.py`, `services/datagolf_api.py`, `tasks/mlb_sync.py`
**Depends on:** Nothing
**Conflicts with:** Any work touching playoffs.py, golf.py, or oscars.py routes
**Parallel Safety:** Yellow (touches multiple files but changes are mechanical)

**Problem:** 6 independent team/name normalization implementations scattered across the codebase. Each handles diacritics, casing, and suffix stripping slightly differently. Bug fixes in one don't propagate to others.

**Current implementations:**
- `utils/name_normalization.py:normalize_name()` — canonical, 22 lines
- `routes/playoffs.py:_normalize_team_name()` — local duplicate with `_strip_diacritics()`, 12 lines
- `routes/golf.py:_normalize_golfer_name()` — golfer-specific (Last, First format), 25 lines
- `routes/oscars.py:_normalize_nominee_name()` — nominee-specific, 15 lines
- `services/datagolf_api.py:strip_diacritics()` — standalone diacritic function
- `tasks/mlb_sync.py:_normalize_team()` — trivial lowercase-only, 8 lines

**Acceptance criteria:**
- All normalization goes through `utils/name_normalization.py`
- Sport-specific variants (golf, oscars) are exported functions from the same module
- Zero duplicate `_strip_diacritics()` or `unicodedata.normalize("NFD", ...)` outside the canonical module
- All existing tests pass
- Add tests for each variant function

**Prompt:**
> Consolidate all team/name normalization into `utils/name_normalization.py`. There are 6 independent implementations:
>
> 1. Read each implementation listed above. Understand what each does differently.
> 2. Extend `utils/name_normalization.py` to cover all cases:
>    - `normalize_name()` — general purpose (already exists)
>    - `normalize_golfer_name()` — handles "Last, First" format + DataGolf quirks
>    - `normalize_nominee_name()` — Oscars nominee cleaning
>    - `normalize_category()` — Oscars category extraction
>    - Ensure `strip_diacritics()` is a public function others can import
> 3. Update all callers to import from the canonical module. Delete the local implementations.
> 4. Add tests in `tests/test_name_normalization.py` for each new variant.
> 5. Run `python3 -m pytest tests/ -v` to verify nothing breaks.
>
> INTERFERENCE RULES: Do NOT modify `services/event_registry.py` or `tasks/prediction_market_matching.py`.

---

### 3. API Client Base Class
**Layer:** backend-services
**Touches:** `services/odds_api.py`, `services/kalshi_api.py`, `services/polymarket_api.py`, `services/statpal_api.py`, `services/espn_api.py`, `services/datagolf_api.py`, `services/mlb_api.py`, NEW: `services/base_api.py`
**Depends on:** Nothing
**Conflicts with:** Any work modifying a specific API service file
**Parallel Safety:** Yellow (touches many files but changes are structural, not behavioral)

**Problem:** All 7 API services duplicate identical `__init__`, `close()`, and HTTP client management. No shared retry/timeout logic. When we add a new service, we copy-paste the same boilerplate.

**Acceptance criteria:**
- New `services/base_api.py` with `BaseAPIClient` class
- All 7 services inherit from it
- Shared: `__init__` (api_key from env), `close()`, `_get()` with timeout, `_post()` if needed
- Configurable per-service: base_url, default timeout, custom headers
- All existing tests pass
- Net reduction of ~100-140 lines of duplicated code

**Prompt:**
> Extract a base API client class from our 7 duplicate service implementations.
>
> 1. Read all 7 API services: `services/odds_api.py`, `kalshi_api.py`, `polymarket_api.py`, `statpal_api.py`, `espn_api.py`, `datagolf_api.py`, `mlb_api.py`
> 2. Identify the common patterns: `__init__` with env var API key, `httpx.AsyncClient` creation, `close()` method, `_get()` helper
> 3. Create `services/base_api.py` with a `BaseAPIClient` that handles all shared logic
> 4. Refactor each service to inherit from `BaseAPIClient`. Keep all service-specific methods unchanged.
> 5. Run `python3 -m pytest tests/ -v` to verify nothing breaks.
>
> Don't over-abstract. The base class should handle boilerplate, not business logic. Each service keeps its own methods.
>
> INTERFERENCE RULES: If another thread is actively modifying a specific service file (e.g., `espn_api.py`), skip that service and note it for later.

---

### 4. API Contract Tests
**Layer:** backend-tests
**Touches:** NEW files in `tests/` only — `tests/test_route_events.py`, `tests/test_route_playoffs.py`, `tests/test_route_golf.py`, `tests/test_route_feed.py`, `tests/test_route_futures.py`
**Depends on:** Nothing
**Conflicts with:** Nothing (only creates new test files)
**Parallel Safety:** Green

**Problem:** 1 out of 14 route modules has tests. API response shape changes go undetected until the frontend breaks.

**Acceptance criteria:**
- Tests for 5 core endpoints verifying response structure (not exact values)
- Uses FastAPI TestClient with mocked DB session
- Tests assert on: required fields present, correct types, correct nesting
- Tests cover: success case, empty results, error cases (404, invalid params)

**Prompt:**
> Add API contract tests for our 5 most important endpoints. These tests verify response SHAPE, not exact data.
>
> Endpoints to test:
> 1. `GET /api/events` (feed) — `routes/feed.py`
> 2. `GET /api/events/{id}` (event detail) — `routes/events.py`
> 3. `GET /api/events/{id}/related-futures` — `routes/events.py`
> 4. `GET /api/playoffs/{league_slug}` — `routes/playoffs.py`
> 5. `GET /api/golf/tournaments/{slug}` — `routes/golf.py`
>
> For each endpoint:
> 1. Read the route handler to understand the response shape
> 2. Create a test file using FastAPI's TestClient
> 3. Mock the database session to return minimal fixture data
> 4. Assert on: required keys present, correct types, nested structure matches frontend expectations
> 5. Add error cases: 404 for missing resources, validation errors for bad params
>
> Reference `tests/conftest.py` for existing fixture patterns. Reference `frontend/lib/types.ts` for the response shapes the frontend expects.
>
> INTERFERENCE RULES: Only create NEW files in tests/. Do NOT modify any existing code.

---

### 5. iOS Search & Futures Parity
**Layer:** ios
**Touches:** `ios/Bain Luck/Views/SearchView.swift`, `ios/Bain Luck/Models/`, `ios/Bain Luck/Services/APIClient.swift`, potentially new Views
**Depends on:** Nothing
**Conflicts with:** Nothing (iOS is fully isolated)
**Parallel Safety:** Green — can ALWAYS run in parallel

**Problem:** iOS search has no filter UI (sport, status, league). No dedicated futures browsing. League list is hardcoded. These gaps make the app feel incomplete for new TestFlight users.

**Acceptance criteria:**
- Search: sport/status filter chips below search bar (match web patterns)
- Search: recent searches stored in UserDefaults, shown when search field is empty
- Futures: browsable futures section accessible from main navigation
- League list: fetched from API, not hardcoded

**Prompt:**
> Close the iOS feature gaps for TestFlight readiness. The iOS app is at `ios/Bain Luck/`. Key patterns:
> - Models: `nonisolated struct X: Decodable, Sendable` (NOT Codable, NOT without nonisolated)
> - ViewModels: `final class XViewModel: ObservableObject` — NO @MainActor on class, only on async methods
> - API: `Services/APIClient.swift` with snake_case JSON decoding
>
> Tasks:
> 1. **Search filters**: Read `Views/SearchView.swift`. Add filter chips for sport and status below the search bar. Look at how `SportFilterChips` works in `Views/Feed/FeedView.swift` for the pattern. Store recent searches in UserDefaults (max 10).
> 2. **Futures browsing**: Create a `FuturesListView` that fetches and displays futures markets. Add it as a section or tab accessible from main navigation. Reference the web's `frontend/app/futures/page.tsx` for what to show.
> 3. **Dynamic league list**: Read `Views/LeaguesView.swift`. Replace the hardcoded league array with an API fetch. Check if there's an existing endpoint (look at `routes/sports.py`).
>
> After each change, verify the project builds: `cd "ios/Bain Luck" && xcodebuild -scheme "Bain Luck" -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -20`
>
> INTERFERENCE RULES: None — iOS is fully isolated from backend and frontend.

---

## Tier 2 — Important But Bigger Scope

### 6. Break Up God Functions
**Layer:** backend-routes, backend-tasks
**Touches:** Varies per sub-task (one function per session)
**Depends on:** Nothing (Event Registry is shipped)
**Conflicts with:** Any work on the same route/task file
**Parallel Safety:** Yellow (one function at a time, check conflicts)

**Problem:** 5 functions over 400 lines. Hard to understand, test, and modify without bugs.

**Sub-tasks (do one per session):**

**6a. `get_playoff_grid()` (847 lines in `routes/playoffs.py`)**

**Prompt:**
> Read `routes/playoffs.py`, function `get_playoff_grid()`. It's 847 lines doing: team resolution, market discovery, grid building, probability merging, monotonicity enforcement, and response formatting. Extract into: `services/playoff_grid.py` with functions like `resolve_teams()`, `discover_markets()`, `build_grid()`, `merge_probabilities()`, `enforce_monotonicity()`. The route handler should be <50 lines calling these service functions. Add tests for each extracted function. Run existing tests to verify: `python3 -m pytest tests/test_playoff_grid.py -v`
>
> INTERFERENCE RULES: Do NOT modify other route files.

**6b. `get_related_futures()` (771 lines in `routes/events.py`)**

**Prompt:**
> Read `routes/events.py`, function `get_related_futures()`. Extract market filtering, grouping, and formatting into `services/related_futures.py`. The route handler should orchestrate calls to service functions. Keep the tier-aware loading logic. Run tests after.
>
> INTERFERENCE RULES: Do NOT modify other route files or task files.

**6c. `_sync_espn_live_events()` (804 lines in `tasks/espn_sync.py`)**

**Prompt:**
> Read `tasks/espn_sync.py`, function `_sync_espn_live_events()`. Extract into: ESPN event matching, game state parsing, snapshot creation, win probability extraction. Each becomes a testable function. The main sync function becomes an orchestrator.
>
> INTERFERENCE RULES: Do NOT modify other task files.

**6d. `_match_prediction_markets()` (622 lines in `tasks/prediction_market_matching.py`)**

**Prompt:**
> Read `tasks/prediction_market_matching.py`. Event Registry is now shipped. Delete duplicate matching logic that's been replaced by the registry. Simplify to: fetch markets → registry lookup → write snapshots. Run tests: `python3 -m pytest tests/test_prediction_market_matching.py -v`
>
> INTERFERENCE RULES: Do NOT modify `services/event_registry.py`.

---

### 7. Golf Data Quality Pass
**Layer:** backend-routes, backend-tasks
**Touches:** `routes/golf.py`, `tasks/datagolf.py`, `utils/futures_categorization.py`
**Depends on:** Nothing
**Conflicts with:** Any work on golf.py
**Parallel Safety:** Yellow

**Known bugs (7, each small and independent):**
1. Tour misclassification (Hainan = Asian Tour, not PGA Tour)
2. "Augusta National Invitational" ghost tournament
3. Categories page chart showing "Yes" (Polymarket binary label)
4. "To win" label on card probabilities
5. H2H matchups filtered out on tournament detail (~L608 in golf.py)
6. Make Cut column missing on tournament detail
7. ATP Monte-Carlo "Masters" markets leaking into golf

**Prompt:**
> Fix 7 golf data quality bugs. Read `routes/golf.py`, `tasks/datagolf.py`, and `utils/futures_categorization.py`.
>
> Bugs to fix (in order — each is small and independent):
> 1. **Tour misclassification**: Hainan Open classified as PGA Tour. DataGolf provides a `tour` field — use it to set correct tour. Check `tasks/datagolf.py` for where tour is set.
> 2. **Ghost tournament**: "Augusta National Invitational" appears as a tournament. Find where it's created and add a filter/blocklist.
> 3. **"Yes" label**: Polymarket binary markets show "Yes" instead of golfer name on categories page chart. Trace from `routes/golf.py` response → frontend rendering.
> 4. **"To win" label**: Card probabilities show "To win" text. Find the label source and remove/replace.
> 5. **H2H matchups filtered**: Tournament detail page filters out " vs " markets around line 608 of `golf.py`. Remove this filter — H2H matchups should appear.
> 6. **Make Cut column**: Tournament detail grid is missing a "Make Cut" column. Check if make-cut markets exist in the data, add column if so.
> 7. **Monte-Carlo leak**: ATP Monte-Carlo Masters tennis markets appear in golf data. Add sport/category gate in `utils/futures_categorization.py`.
>
> After each fix, run: `python3 -m pytest tests/ -k golf -v`
>
> INTERFERENCE RULES: Do NOT modify files outside golf-related code.

---

### 8. Site Navigation Hierarchy (B1)
**Layer:** frontend, backend-routes
**Touches:** `frontend/app/` (new route structure), `frontend/components/Navigation/`, `backend/app/routes/sports.py`
**Depends on:** Golf strategy decisions (default PGA Tour? hero layout?)
**Conflicts with:** Any frontend page work
**Parallel Safety:** Red (restructures frontend routing)

**Problem:** Current URL structure is flat (`/playoffs/nba`, `/categories/golf`). Need hierarchy: `/basketball/nba`, `/golf/pga-tour`. Team sports get grid+games+futures tabs. Individual sports get tour hub → tournament detail.

**Status:** NOT STARTED. Blocked on golf strategy decisions.

**Open design decisions:**
- Default to PGA Tour only? (Recommendation: yes, "All Tours" toggle)
- Golf home hierarchy? (Recommendation: hero -> majors -> upcoming -> completed)
- Don't kill `/playoffs/golf` yet — wait until golf pages are really humming

**Prompt:**
> [NOT READY — needs design decisions first]

---

### 9. External API Fixture Tests
**Layer:** backend-tests
**Touches:** NEW files only — `tests/fixtures/` (JSON files), `tests/test_service_*.py`
**Depends on:** Nothing
**Conflicts with:** Nothing (only creates new files)
**Parallel Safety:** Green

**Problem:** If Kalshi, Polymarket, ESPN, or DataGolf change their API response format, we won't know until production breaks.

**Prompt:**
> Create fixture-based tests for our external API service parsing.
>
> For each service (Kalshi, Polymarket, ESPN, DataGolf, Odds API):
> 1. Read the service file in `services/` to understand what fields we extract
> 2. Create a realistic JSON fixture file in `tests/fixtures/` representing a real API response
> 3. Write tests that feed the fixture through our parsing functions and verify we extract the right fields
> 4. Include edge cases: empty responses, missing fields, unexpected types
>
> Focus on PARSING correctness, not HTTP behavior. Mock the HTTP layer, test the data extraction.
>
> Services to cover:
> - `services/kalshi_api.py` — market listings, event data
> - `services/polymarket_api.py` — market/token data
> - `services/espn_api.py` — scoreboard, game state, win probability
> - `services/datagolf_api.py` — leaderboard, predictions, field data
> - `services/odds_api.py` — odds response format
>
> INTERFERENCE RULES: Only create NEW files. Do NOT modify any existing code.

---

## Tier 3 — Valuable But Can Wait

### 10. Evolution Chart: Combined Probability
**Layer:** backend-routes, frontend | **Parallel Safety:** Yellow
**Depends on:** Source coverage crisis fixed (#1)
Chart shows single-source data. Grid shows merged probability. Chart should show merged trend over time. Requires time-series aggregate computation.
**Status:** DEFERRED — fix source coverage first so there's multi-source data to merge.

### 11. Line Movement Explainer v2
**Layer:** backend-services, frontend | **Parallel Safety:** Green
Currently disabled. Only stated the obvious ("Team X won, odds went up"). Needs: key moment identification, causal analysis, context from scoring plays. Not blocking anything.

### 12. Freshness-Weighted Blending
**Layer:** backend-utils | **Parallel Safety:** Yellow
Stale prediction market prices weighted equally with fresh model data. Need time-decay weighting. Design notes in memory. Waiting on more eval data.

### 13. DS/Analytics Infrastructure
**Layer:** backend-models, migrations | **Parallel Safety:** Red (migrations)
Add analytical columns (`ended_at`, `final_home_probability`, `event_results`, `season`). Denormalize `sport_group`. Create `v_completed_events` view. Enables "Who's Right?" Brier score analysis. Low urgency.

### 14. Related Futures for Golf Tournaments
**Layer:** backend-routes | **Parallel Safety:** Yellow
Tournament detail pages have no "Bigger Picture" section. Markets exist on Kalshi/Polymarket (Top 5, Make Cut, H2H, round leaders, nationality props). Need "Related Futures for Tournament" endpoint. Must match by tournament key (NOT `ILIKE '%Masters%'` which leaks esports). Exclude markets already in grid columns.

### 15. Golf Evolution Chart Redesign
**Layer:** frontend | **Parallel Safety:** Green
Multiple problems: "24 Hours" and "Today" time ranges make no sense for golf, round markers needed, tournament-aware time ranges. DataGolf's evolution plot is the gold standard.

---

## Tier 4 — Someday / Maybe

- **Entity pages** (`/[sport]/[league]/[team]`) — Depends on B1. SEO upside.
- **Win totals column** in championship grid
- **Awards/props cards** on league pages (MVP, DPOY, ROY)
- **TV Mode v2** — Design complete, prototype at `docs/tv-mode-prototype.jsx`
- **"The Market Was Wrong" v2** — AI narrative generation
- **MoneyPuck for NHL** — Infrastructure ready (stub configured)
- **Related Futures Phase 5** — Bidirectional: futures detail shows relevant events
- **Non-Sports Categories** — Audit politics, entertainment, crypto, weather markets
- **iOS beyond parity** — App Store submission, widgets, background refresh, share extension, push notifications
- **Apple Watch app** — Glanceable live probabilities
- **Apple TV app** — Natural fit for TV Mode
- **Weather visualization** — Prediction market weather maps
- **"What Are the Odds?" game** — Probability guessing game

---

## Architecture Initiatives (Reference)

### B1: Site Navigation Hierarchy — NOT STARTED (see Item 8 above)

### B2: League Context Service — SHIPPED April 14-15
`LeagueContextService` in `services/league_context.py`. Redis-cached (5-min TTL), dynamic columns from `league_configs.py`. Powers Playoff Path card + team-progression endpoint.

**Remaining follow-ups:** Extract `market_discovery.py` + `team_resolution.py` from `playoffs.py` (cleanup, not blocking). Orphaned event detection.

### B3: Eval Page v2 — NOT STARTED (Tier 3)
Group by market. Three card types: market-column assignment, source disagreement, interesting futures.

### B4: Trade Volume — SHIPPED April 14-15
All 3 phases complete. Internal signal only — NEVER user-facing.

### Event Registry — SHIPPED April 16
All 5 phases. Unified event matching via `find_or_create_event()`. Removed ~430 lines of scattered dedup spaghetti.

---

## Housekeeping

- **May 1, 2026**: Delete `frontend/_to-delete/` if nothing broke
- **May 1, 2026**: Delete `docs/archive/` if nothing referenced
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches (old feature/claude branches from Jan-Mar 2026)
