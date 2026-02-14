# Test Coverage Analysis

**Date:** February 2026
**Total tests:** 693 backend + 107 frontend = 800 total

---

## Current Coverage Summary

### Backend (693 tests across 15 test files)

| Test File | Module Under Test | Tests | Coverage Level |
|-----------|-------------------|-------|----------------|
| `test_futures_categorization.py` | `utils/futures_categorization.py` | 116 | Excellent — all 22 categories, LLM fallback |
| `test_team_linking.py` | `utils/team_linking.py` | 97 | Excellent — tier classification, name matching, relevance scoring |
| `test_highlights.py` | `utils/highlights.py` | 88 | Excellent — all statuses, labels, exact score regression pins |
| `test_pulse.py` | `utils/pulse.py` | 85 | Excellent — algorithm, normalization constants, aggregation |
| `test_llm.py` | `services/llm.py` | 60 | Excellent — all classify functions, mocked OpenAI |
| `test_win_probability.py` | `utils/win_probability.py` | 51 | Excellent — stat model, sport key aliases, database key mapping, all 6 sports |
| `test_odds_math.py` | `utils/odds_math.py` | 35 | Excellent — core conversions, reversed bookmaker detection |
| `test_odds_math_extended.py` | `utils/odds_math.py` | 35 | Excellent — project_scores, calculate_gei, format_probability, round-trips |
| `test_odds_polling_helpers.py` | `tasks/odds_polling.py` | 27 | Good — get_max_duration_for_sport prefix matching, _snapshots_are_equal dedup |
| `test_win_prob_sources.py` | `config/win_prob_sources.py` | 24 | Good — structural validation, required fields, hex colors, source types |
| `test_tasks_wiring.py` | `tasks/` (wiring only) | 19 | Good — beat schedule, imports, re-exports |
| `test_espn_api_parsing.py` | `services/espn_api.py` | 20 | Good — _parse_color, SPORT_LEAGUE_MAP completeness, _get_espn_path |
| `test_stale_bookmaker_filter.py` | `utils/odds_filtering.py` | 14 | Good — stale bookmaker filter, all statuses |
| `test_snapshot_collapse.py` | `tasks/retention.py` | 13 | Good — collapse algorithm, edge cases |
| `test_redis_state.py` | `tasks/redis_state.py` | 9 | Good — compute_odds_hash determinism, ordering, edge cases |
| | **routes/** | **0** | **None** |
| | **dependencies/** | **0** | **None** |

### Frontend (107 tests across 2 test files)

| Test File | Module Under Test | Tests | Coverage Level |
|-----------|-------------------|-------|----------------|
| `sportCategories.test.ts` | `lib/sportCategories.ts` | 85 | Excellent — categorization, tiers, excitement scoring |
| `pinnedStorage.test.ts` | `hooks/usePinnedEvents.ts` + `usePinnedFutures.ts` | 22 | Good — localStorage operations, pin limits, storage independence |
| | **components/** (21 files) | **0** | **None** |
| | **app/** pages (12 files) | **0** | **None** |
| | **hooks/** (7 of 9 untested) | **0** | **None** |
| | **lib/api.ts** | **0** | **None** |

---

## Strengths

1. **Core algorithms are thoroughly tested.** Pulse, Highlights, odds math, and futures categorization have 390+ tests with exact score regression pins that prevent accidental changes to weights or normalization constants.

2. **Pure function testing strategy works well.** 85% of backend tests cover `utils/` — functions with no I/O dependencies that are easy to test and have historically caused the most rework.

3. **Task wiring is verified.** The 19 tests in `test_tasks_wiring.py` catch broken imports and beat schedule misconfigurations — a class of bugs that only surfaces in production.

4. **Good fixture design.** `conftest.py` provides `make_snapshots` and `make_multi_bookmaker_snapshots` factories that make writing new Pulse/odds tests fast.

---

## Recommended Improvements (Priority Order)

### 1. Backend: Extractable pure functions in `tasks/odds_polling.py`

**Why:** This is the most critical background task. Several functions inside it are pure or near-pure and testable without a database, but have zero tests.

**Specific functions to test:**

- **`get_max_duration_for_sport(sport_key)`** — Pure function. Maps sport keys to max durations. Untested prefix matching logic could silently break staleness detection for entire sports.

- **`_snapshots_are_equal(existing, new_values)`** — Pure comparison function. Determines whether to create a new snapshot or bump `reading_count`. A bug here means either duplicate data (wasting storage / causing OOM) or lost data.

- **`_maybe_set_opening_odds(event, home_prob, away_prob, status)`** — Stateful but logic is testable: should freeze opening odds once game starts. A regression here corrupts the "Opened X/Y" display on every completed game.

- **`_create_or_update_win_prob_snapshot`** — Shared utility (imported by `espn_sync.py`). Write-time dedup logic should be tested: same value = bump count, different value = new row.

**Estimated effort:** ~25-30 tests. High value-to-effort ratio since these are all extractable to pure functions or testable with lightweight mocks.

### 2. Backend: ESPN API client parsing (`services/espn_api.py`)

**Why:** ESPN's undocumented API returns inconsistent response shapes (e.g., `"logo"` string on scoreboard vs `"logos"` array on teams endpoint). The parsing code in `_parse_team`, `_parse_event`, `_parse_venue` handles these differences, but a format change from ESPN would silently break team enrichment.

**Specific functions to test:**

- **`_parse_team(team_data)`** — Handles two different logo formats, optional fields, color parsing. Test with both scoreboard-format and teams-format JSON.

- **`_parse_color(color)`** — Adds `#` prefix. Simple but currently untested.

- **`_parse_event(event_data)`** — Parses status, clock, period, win probability. The win probability extraction path (`predictor.homeTeam[0].gameProjection`) is deeply nested and brittle.

- **`_get_espn_path(sport_key)`** — Pure lookup. Verify all 17 sport mappings.

- **Team name normalization** — Unicode/accent handling for college team matching. Currently tested indirectly via win_probability tests but ESPN-specific normalization deserves its own tests.

**Estimated effort:** ~20-25 tests using static JSON fixtures (no network calls). Prevents silent breakage from ESPN API format changes.

### 3. Frontend: `lib/api.ts` — API client

**Why:** Every data flow in the frontend goes through `apiFetch`. It handles auth token injection, error parsing, and response typing. Zero tests.

**What to test:**

- Auth token is attached when `_getAuthToken` is set
- Auth header is omitted for anonymous users
- HTTP errors are parsed and thrown with correct message
- JSON parse failure in error response falls back to "Unknown error"

**Estimated effort:** ~10-12 tests with a mocked `fetch`.

### 4. Backend: Route-level contract tests for `routes/events.py`

**Why:** The events API is the most complex route file (~800+ lines) with query parameter parsing, pagination, search logic, and the related-futures endpoint. No tests exist for any route.

**What to test (without a real database):**

- **`_escape_like(pattern)`** — Pure function. Escapes `%`, `_`, `\` for ILIKE queries.
- **`_team_name_patterns(team)`** — Builds ILIKE patterns from team names. Already partially tested in `test_team_linking.py` but the route-local version should be verified too.
- **Response shape validation** — Mock the DB session and verify that endpoints return the expected JSON structure. Catches field renames or missing keys before deployment.

**Estimated effort:** Start with ~10 tests for the pure helper functions. Full route integration tests would need an async test DB setup (higher effort).

### 5. Backend: `tasks/redis_state.py` — Adaptive polling logic

**Why:** Controls poll intervals for every sport. Functions like `should_poll_now`, `compute_odds_hash`, and `update_poll_state` determine when the system fetches new data. A bug here means either missed live game updates or wasted API quota.

**What to test:**

- **`compute_odds_hash(odds_data)`** — Pure function. Verify deterministic hashing, handling of None values, and that different odds produce different hashes.
- **`should_poll_now(sport_key, interval)`** — Testable with a mocked Redis client. Verify interval enforcement and edge cases (first poll, expired interval).

**Estimated effort:** ~10-15 tests.

### 6. Frontend: `hooks/useAuth.ts` — Authentication state

**Why:** Auth is a new feature (Phase 1 shipped). The hook manages Firebase ID tokens, backend registration, and sign-in/sign-out flows. The Safari fallback path (`signInWithCustomToken`) is particularly fragile. Zero tests.

**What to test:**

- Token refresh on expiry
- Backend registration call on first sign-in
- Sign-out clears auth state
- Error handling for network failures during sign-in

**Estimated effort:** ~10-15 tests. Requires mocking Firebase SDK and fetch.

### 7. Backend: `config/win_prob_sources.py` — Source registry validation

**Why:** Small file but adding a new win probability source requires correct keys, colors, and methodology. A structural test prevents deploying a misconfigured source.

**What to test:**

- All source entries have required fields (display_name, color, dash_pattern, methodology)
- No duplicate source keys
- Color values are valid hex codes
- Source keys match what the snapshot writer uses

**Estimated effort:** ~5 tests. Very low effort, prevents configuration mistakes.

### 8. Frontend: Component rendering tests

**Why:** 21 components with zero tests. While full component testing has high overhead, a few targeted tests for the most logic-heavy components would catch regressions.

**Priority components:**

- **`EventCard.tsx`** — Renders different layouts for scheduled/live/completed statuses. Test that correct probability source (current vs opening odds) is shown per status.
- **`PulseBadge.tsx`** — Tooltip content, status-to-color mapping, score thresholds.
- **`ProbabilityBar.tsx`** — Width calculation, team color application, edge cases (0%, 100%, 50/50).

**Estimated effort:** Requires adding React Testing Library to devDependencies. ~15-20 tests for the three priority components.

---

## What NOT to Prioritize

- **Full route integration tests** — Requires async DB fixtures (SQLite or test Postgres). High setup cost, moderate value since the app auto-deploys and is verified on production.
- **E2E tests (Playwright/Cypress)** — The development workflow is GitHub-based with no local dev environment. E2E infrastructure would add significant complexity.
- **Analytics hooks** (`useAnalytics`, `useEngagementTime`, `useScrollDepth`) — Low risk. These fire GA4 events; bugs in tracking are non-critical and detectable via GA4 dashboard.
- **Admin routes** — Debug/admin endpoints are low-traffic and manually verified.

---

## Quick Wins — ✅ Completed

All 6 quick wins were implemented, adding 80 tests across 4 new test files:

1. ✅ **`get_max_duration_for_sport`** — 15 tests in `test_odds_polling_helpers.py` (all prefixes, default fallback, edge cases)
2. ✅ **`_snapshots_are_equal`** — 12 tests in `test_odds_polling_helpers.py` (equal/different per field, None handling, int/float coercion)
3. ✅ **`_parse_color`** — 6 tests in `test_espn_api_parsing.py` (None, empty, with/without #, lowercase)
4. ✅ **`_get_espn_path` + SPORT_LEAGUE_MAP** — 14 tests in `test_espn_api_parsing.py` (10 specific mappings, unknown key, structural validation)
5. ✅ **`compute_odds_hash`** — 9 tests in `test_redis_state.py` (determinism, different inputs, ordering independence, edge cases)
6. ✅ **`win_prob_sources.py` validation** — 24 tests in `test_win_prob_sources.py` (required fields, hex colors, source types, helper functions)

---

## Summary

The codebase has strong coverage for pure algorithms (~80% of backend tests) but zero coverage for:
- API routes (7 files)
- Frontend components (21 files)
- Frontend hooks (7 of 9 untested)

The highest-leverage improvements are extracting and testing the pure functions hiding inside `tasks/odds_polling.py` and `services/espn_api.py` — these are in the critical data path, have caused production issues, and can be tested without database or network dependencies.
