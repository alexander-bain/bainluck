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
| Game prop linking (#1C) | Items 4, 5, 9 (all Green) |
| No good parallel candidate? | Brainstorm B1 design decisions, or write tests (#4, #9) |

---

## Tier 1 — High Leverage, Do Next

### 1. ESPN + Source Coverage — SHIPPED April 16
**Status:** COMPLETE. All acceptance criteria met.

**What shipped:**
- All 6 sources (betting, espn, stat_model, mlb, kalshi, polymarket) now write to `win_probability_sources` via select+update pattern
- Feed response includes `win_probability_sources`
- `espn_win_prob_home` written atomically with `win_probability_sources["espn"]`
- ESPN match rate: 100% for completed events (NBA, NHL, MLB)
- Live events show 3-4 sources (was 1)
- Root cause: ORM attribute assignment silently failed due to session caching; fixed by using SQLAlchemy `update()` statements

---

### 1B. Event Detail Page Quality Issues (discovered April 16, partially fixed)
**Layer:** frontend-components, backend-routes
**Parallel Safety:** Yellow (touches frontend components + backend routes)

**Issues found on Athletics vs Rangers game (screenshot April 16):**

1. **Baseball game state markers say just "1", "2", "3"** — need "Top 1st", "Mid 3rd", "Bot 5th" etc. Currently showing bare inning numbers that overlap and are unreadable. Must clarify half-inning and space markers so they don't collide.

2. **Player props show "points" and "assists" for a baseball game** — these are hockey stat categories leaking into baseball. Vladislav Gavrikov and Mavrik Bourque are hockey players, not baseball. The player props section is pulling from the wrong sport. Likely a sport filter issue in Related Futures.

3. **Player prop cards need headshots** — text-only cards look bad. `PlayerStatCard.tsx` already has `PlayerAvatar` with ESPN headshot support. May just need the `espnPlayerId` or `headshotUrl` to be passed through from the backend.

4. **Playoff Path card broken for Athletics** — only shows "AL Champ: 2%" with no other columns (Make Playoffs, Division, Championship). Alex provided full Kalshi/Polymarket market links for all MLB progression levels. The `league_configs.py` MLB config may be missing matching rules for these markets.

5. **Title Odds card shows Rangers at 52%** — impossibly high for mid-season. And it duplicates info that should be in the Playoff Path card. Title Odds card should be removed (we decided this before) or at minimum should agree with the Playoff Path championship column.

6. **Awards & All-Team card** — only shows "Corey Seager" with 5%. Should show many more players. Card title "Awards & All-Team" is awkward — rename to something like "Player Awards" or "Season Awards". Need to populate from the full list of MLB award markets (MVP, Cy Young, ROY, etc. — Alex provided Kalshi/Polymarket links).

7. **"More Baseball" text at bottom** — shows as plain text with no link or card. Should either link to the MLB league page or be removed.

**MLB Market Links (from Alex, for Playoff Path + Awards):**
- Make playoffs: Kalshi `kxmlbplayoffs`, PM `mlb-team-to-make-postseason`
- Divisions: Kalshi `kxmlbaleast/alcent/alwest/nleast/nlcent/nlwest`, PM equivalents
- League champions: Kalshi `kxmlbal/kxmlbnl`, PM equivalents
- World Series: Kalshi `kxmlb`, PM `mlb-world-series-champion-2026`
- Win totals: Kalshi category, PM `mlb-2026-regular-season-win-totals`
- Awards: PM has 16+ player award markets (MVP, Cy Young, ROY, Manager, etc.)
- League leaders: Kalshi category
- Best/worst record: Kalshi `kxmlbbestrecord/worstrecord`

---

### 1C. Revive Related Futures Cards: Fix Game Prop → Event Linking
**Layer:** backend-tasks, backend-routes
**Touches:** `tasks/prediction_market_matching.py`, `routes/events.py` (get_related_futures), `utils/prediction_market_matching.py`
**Depends on:** Nothing (Event Registry is shipped)
**Conflicts with:** Any work on prediction_market_matching.py or events.py related futures section
**Parallel Safety:** Yellow

**Problem:** We designed and built 19 Related Futures card components (frontend + iOS). The code is complete and correct. But users only see ~5 card types (championship, conference, awards, playoff path). The other cards — **PlayerStatCard with probability gauges, GameMarketsGrid, WinTotalsGauge, MatchupGrid** — never appear because the data they need isn't linked.

**Root cause:** There are **1,858 Kalshi game_prop markets** in the database (873 basketball, 720 soccer, 154 hockey, 80 baseball) including player points, assists, rebounds, goals, total points, etc. But they have `event_id=NULL` and `sport=None`. The `get_related_futures()` query in `routes/events.py` (line 2783) filters game props by `FuturesMarket.event_id == event_id` — if `event_id` is NULL, they never appear.

**The matching system exists but isn't linking these markets.** `tasks/prediction_market_matching.py` has a full pipeline:
1. Scans Kalshi markets where `event_id IS NULL` and ticker matches `_KALSHI_GAME_TICKER_PREFIXES`
2. Extracts team names via `extract_matchup_with_ticker_fallback()`
3. Matches to events via `_find_matching_event()` (time window + team name scoring)
4. Sets `market.event_id = matched_event["event_id"]`

But 1,858 markets remain unlinked. Possible failure points:
- **Ticker prefix not in `_KALSHI_GAME_TICKER_PREFIXES`** — the market ticker may not match any known prefix, so it's never scanned
- **`extract_matchup_with_ticker_fallback()` fails** — can't parse team names from market name like "WSH Capitals at NJ Devils: Assists"
- **`_find_matching_event()` fails** — time window too narrow, or team name matching too strict
- **`sport=None`** — market has no sport classification, making sport-based matching harder
- **Market tier classification** — the market might not be classified as tier 5 (game_prop), so even if linked, `get_related_futures()` won't load it in the game props pass

**Verified example:** Market id=8633585 "WSH Capitals at NJ Devils: Assists" (Kalshi):
- `sport=None`, `event_id=NULL`, `source=kalshi`
- 25 outcomes (Jakob Chychrun: 1+, Jesper Bratt: 1+, etc.)
- `commence_time=2026-04-16T23:30:00+00:00` (this is the RESOLUTION date, not the game date)
- The actual game "Capitals at Devils" exists in our events table
- Matching should work but doesn't — likely ticker prefix or date extraction issue

**Cards this unblocks (all already implemented, just need data):**

| Card | Component | What it shows | File |
|------|-----------|--------------|------|
| **PlayerStatCard** | `StatPropsSection` | Pre-game: probability gauge. Live: progress bar toward line. Completed: hit/miss badge. Player headshots. | `frontend/components/RelatedFutures.tsx` L820-1099 |
| **GameMarketsGrid** | `GameMarketsGrid` | 2-column grid of upcoming game matchups with probabilities | `frontend/components/RelatedFutures.tsx` L562-719 |
| **GameMarketsPair** | `GameMarketsPair` | Paired upcoming games with moneyline probabilities | `frontend/components/RelatedFutures.tsx` L2158-2185 |

**Also worth verifying (may need small data format fixes):**

| Card | Component | Issue | File |
|------|-----------|-------|------|
| **WinTotalsGauge** | `WinTotalsPair` | Semi-circular gauge for season win totals. Data exists (`display_category=season_stat`) but gauge needs structured over/under threshold data — verify format matches | `frontend/components/RelatedFutures.tsx` L1520-1660 |
| **MatchupGrid** | `MatchupGrid` | Conference/Finals matchup probability grid. Playoff path markets exist but may need specific formatting for the grid | `frontend/components/RelatedFutures.tsx` L1834-1978 |

**Investigation steps (do first, before coding):**
1. Check `_KALSHI_GAME_TICKER_PREFIXES` — are the tickers for these 1,858 markets included?
   ```python
   # Find what tickers these unlinked markets actually have
   SELECT DISTINCT LEFT(external_id, 10), COUNT(*)
   FROM futures_markets
   WHERE source = 'kalshi' AND event_id IS NULL AND market_tier = 5
   GROUP BY 1 ORDER BY 2 DESC;
   ```
2. Check the matching task logs — look for `_match_prediction_markets` stats: what does `no_matchup_extracted` count show? What are the `sample_game_level_no_event` examples?
3. Check if the Kalshi `commence_time` issue is the blocker — Kalshi sets `commence_time` to the market RESOLUTION date, not the game date. `extract_game_date_from_ticker()` exists to handle this but may not cover all ticker formats.
4. Run a manual matching test: take the "WSH Capitals at NJ Devils: Assists" market and trace through the matching pipeline step by step.

**Acceptance criteria:**
- >80% of Kalshi game_prop markets have `event_id` set (currently 0%)
- Event detail pages for NBA/NHL/MLB games show the PlayerStatCard section with player props
- Live games show progress bars with box score data flowing into stat props
- Completed games show hit/miss badges on player props
- GameMarketsGrid appears in the "Game Markets" section of Related Futures
- WinTotalsGauge renders when win total markets exist for the teams

**Prompt:**
> The Related Futures section has 19 card components but only 5 show up. The biggest unlock is fixing game_prop → event linking so PlayerStatCard, GameMarketsGrid, and GameMarketsPair start receiving data.
>
> **Phase 1: Diagnose why 1,858 Kalshi game_prop markets have event_id=NULL**
>
> 1. Read `utils/sport_keys.py` → `KALSHI_GAME_TICKER_PREFIXES`. Check if the tickers for unlinked markets are covered.
> 2. Read `tasks/prediction_market_matching.py` → `_match_prediction_markets()`. Trace the linking pipeline. Find where unlinked game_prop markets fall out.
> 3. Hit the admin API to see matching task stats: `curl "https://api.bainluck.com/api/admin/dashboard?secret=$ADMIN_SECRET"` — look for prediction market matching metrics.
> 4. Pick 3 specific unlinked markets and manually trace them through `extract_matchup_with_ticker_fallback()` and `_find_matching_event()`. Find exactly why matching fails.
>
> **Phase 2: Fix the linking gaps**
>
> Based on diagnosis, the fix is likely one or more of:
> - Add missing ticker prefixes to `KALSHI_GAME_TICKER_PREFIXES` in `utils/sport_keys.py`
> - Fix `extract_matchup_with_ticker_fallback()` to handle the "Team A at Team B: Stat Type" format
> - Fix `extract_game_date_from_ticker()` for ticker formats that aren't covered
> - Widen time window in `_find_matching_event()` if games aren't found
>
> **Phase 3: Verify cards appear**
>
> After fixing linking, check that Related Futures now returns game_prop data:
> ```bash
> curl "https://api.bainluck.com/api/events/{nba_event_id}/related-futures" | python3 -c "
> import sys,json; d=json.load(sys.stdin)
> all_items = d.get('home_team_futures',[]) + d.get('away_team_futures',[])
> game_props = [i for i in all_items if i.get('display_category') == 'game_prop']
> print(f'Game props: {len(game_props)}')"
> ```
>
> **Phase 4: Verify WinTotalsGauge and MatchupGrid data format**
>
> Check if the season_stat markets have the right structure for the WinTotalsGauge component. The gauge needs over/under threshold data with probabilities. Read the frontend component to understand what data shape it expects, then check if the backend response matches.
>
> Run tests: `python3 -m pytest tests/ -v -k "prediction_market or related"`
>
> INTERFERENCE RULES: Do NOT modify `services/event_registry.py`. Do NOT modify `tasks/config.py` or `tasks/odds_polling.py` (quota optimization was just deployed).

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

### 5. iOS Search & Futures Parity — **SHIPPED April 16** (not build-verified)
**Layer:** ios
**Touches:** `ios/Bain Luck/Views/SearchView.swift`, `ios/Bain Luck/Models/`, `ios/Bain Luck/Services/APIClient.swift`, potentially new Views
**Depends on:** Nothing
**Conflicts with:** Nothing (iOS is fully isolated)
**Parallel Safety:** Green — can ALWAYS run in parallel

**Status:** Commit `7620535`. Search filters + recent searches + FuturesListView shipped. NOT build-verified (SPM sandbox issue). Dynamic league list skipped (no backend endpoint). See `memory/project_ios_parity_april16.md` for full change log.

**Acceptance criteria:**
- ~~Search: sport/status filter chips below search bar (match web patterns)~~ DONE
- ~~Search: recent searches stored in UserDefaults, shown when search field is empty~~ DONE
- ~~Futures: browsable futures section accessible from main navigation~~ DONE (iPad sidebar)
- League list: fetched from API, not hardcoded — SKIPPED (no backend endpoint)

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
