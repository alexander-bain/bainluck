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

### 0f-2. Futures Detail Page Data Quality
Polymarket `futures/132810` (2026 AL Cy Young Winner) shows "player AO", "player AH" etc. at 100% with 3400% y-axis. Outcome names are abbreviations instead of real names, probabilities are broken. Likely a Polymarket data parsing issue.
**Files:** `tasks/polymarket.py` (outcome name parsing), `routes/futures.py` (display)

### 0f-3a. Player Props: Team Filter Bug (SOX/YAN pills) — CODE FIX READY, NEEDS DEPLOY

**Problem:** Clicking SOX or YAN team filter pills in the Player Props section causes ALL cards to disappear.

**Root cause:** `PlayerPropsDashboard.tsx` `detectTeam()` parses the Kalshi market name prefix (e.g., "New York Y vs Boston") to determine which team a player is on. But BOTH team names appear in every market name. The position-based tiebreaker (`homeIdx < awayIdx`) always assigns ALL players to whichever team name appears first in the market string. For "New York Y vs Boston" → all players get `team="away"`. Clicking SOX (home filter) → zero matches → all cards disappear.

**Fix (committed locally, not yet deployed):**
1. **Backend** (`routes/events.py`): Headshot enrichment (step 10) now also determines team membership from roster data. Returns `player_team: "home" | "away"` per prop based on which team's roster contains the player. Works independently of headshot availability.
2. **Frontend** (`PlayerPropsDashboard.tsx`, `PlayerPropsGrid.tsx`): Uses `player_team` from API when available, falls back to the (imperfect) market-name detection only when API doesn't provide team info.
3. **Frontend type** (`lib/api.ts`): Added `player_team?: "home" | "away"` to `GameMarketsResponse.player_props`.

**Tests:** 39 existing game-markets tests pass. No new TS errors introduced.
**Files:** `backend/app/routes/events.py` (headshot enrichment rewrite), `frontend/components/PlayerPropsDashboard.tsx:363`, `frontend/components/PlayerPropsGrid.tsx:91-100`, `frontend/lib/api.ts:574`
**Parallel Safety:** Yellow (touches events.py + 2 frontend components)

### 0f-3b. Player Prop Headshots Missing — ROSTER DATA EXISTS, ENRICHMENT NEEDS DEBUGGING

**Problem:** All 97 player prop cards show initials instead of player headshot images. `player_headshot` is `MISSING` for every prop in the API response.

**Investigation findings (April 22):**
- MLB roster data EXISTS in DB: Red Sox 28 players, Yankees 28 players (confirmed via admin debug endpoint)
- MLB Stats API works perfectly: returns 26 active roster players per team with headshot URLs (`img.mlbstatic.com/mlb-photos/...`)
- The roster sync task (`sync_rosters`) runs daily at 7 AM UTC
- The headshot enrichment code (`events.py:2636-2698`) queries `Team.roster_players WHERE Team.name IN (home_team_name, away_team_name)` — names match ("Boston Red Sox" in both event and team)

**Suspected root cause:** Roster entries may be plain strings (just player names) instead of dicts with `{"name": "...", "headshot": "..."}`. This would happen if:
- Rosters were synced before the headshot URL generation was added to `MLBAPIService.get_team_roster()` 
- The MLB roster sync branch failed silently and only the ESPN/StatPal branch ran (which stores fewer fields)
- Or there's a JSON serialization mismatch between what's stored and what's queried

**Fix:** 
1. Trigger a fresh MLB roster sync: `POST /api/admin/rosters/sync?sport_key=baseball_mlb` (via admin dashboard or Heroku one-off dyno)
2. Verify roster entries have headshot keys: `SELECT name, roster_players->0 FROM teams WHERE name = 'Boston Red Sox'`
3. If entries are plain strings, the sync code at `roster_sync.py:279-288` should replace them with dicts on next run

**Previous code also had a gating bug (FIXED in local code):** The enrichment only ran matching logic when `player_headshots` dict was non-empty (required at least one headshot URL). New code uses `player_roster_info` which populates for ANY named roster player regardless of headshot availability. This ensures team assignment works even without headshots.

**Files:** `backend/app/tasks/roster_sync.py` (MLB sync), `backend/app/services/mlb_api.py:254-289` (headshot URL generation), `backend/app/routes/events.py:2635-2698` (enrichment)
**Parallel Safety:** Green (backend only, no frontend changes needed)
**Also see:** iOS-17 (same underlying issue)

### 0f-3. Live Box Score Integration for Player Props
Player prop cards should show actual stats from `box_score_data` during live games (e.g., "Jayson Tatum: 18 points so far vs 24.5 O/U"). The `boxScore` prop is wired but the matching logic needs work — player names from Kalshi props don't always match ESPN box score names.
**Files:** `frontend/components/PlayerPropsDashboard.tsx` (matching), `backend/app/routes/events.py` (box score in response)

### 0f-X. CRITICAL: Kalshi conference markets misclassified as wrong sport

**Status:** Partially fixed, needs debugging. Direct DB fix applied April 22 as hotfix.

**The Problem:**
Kalshi's NHL Eastern/Western Conference markets (`KXNHLEAST-26`, `KXNHLWEST-26`) were classified as `llm_sport_category='basketball'` instead of `'hockey'`. This made them invisible to the NHL championship grid. The NHL grid showed 0.1% for Bruins conference odds when Kalshi has them at 6%.

**Root Cause Chain (3 bugs stacked):**
1. **`status=None` filter** (FIXED in commit `d8872ed`): Kalshi neg-risk events have `status=None` on the API, not `"open"`. Our `_fetch_all_events_unfiltered()` filtered on `status="open"`, silently skipping these events. Fixed by passing `status=None` explicitly.

2. **Default parameter override** (FIXED in commit `038e185`): `get_events()` has `status="open"` as default parameter. Even after removing the explicit `status="open"` in `_fetch_all_events_unfiltered`, the default was still applied. Fixed by passing `status=None` explicitly.

3. **Pagination gap** (FIXED in commit `17b2341`): Without the status filter, the API returns ALL Kalshi events (7,400+). KXNHLEAST might not appear within the 50-page limit. Added supplementary fetch for known sports series tickers (`KXNBA`, `KXNHL`, `KXMLB`, `KXNFL` + conference variants).

4. **Sport misclassification** (FIXED in commit `9786298`): `_categorize_kalshi_market()` checked name-based rules BEFORE ticker-based classification. "Eastern Conference Finals Winner?" matched a basketball rule first. KXNHLEAST ticker is unambiguously hockey, but the ticker check was step 3 instead of step 1. Fixed by moving ticker check to step 1.

5. **Upsert not updating llm_sport_category** (DEBUGGING — not yet confirmed fixed): Even after fix #4, the poll doesn't seem to update the stored `llm_sport_category` from `basketball` to `hockey`. The `on_conflict_do_update` at line 432 should update it when `sport_category != "other"`. Possible causes:
   - The Celery worker may not be picking up the queued `poll_kalshi_markets` task (observed: task queued but never executed, worker was busy with `discover_events`, `sync_mm_bracket`, `sync_statpal_schedules`)
   - The worker may have stale code despite restart (Celery preforking can cache imports)
   - The `heroku run` one-off dyno successfully fetched 7,463 events including KXNHLEAST-26 with markets, but no evidence the poll task ran to completion on the scheduled worker

**Hotfix Applied:**
Direct SQL: `UPDATE futures_markets SET llm_sport_category = 'hockey' WHERE external_id IN ('KXNHLEAST-26', 'KXNHLWEST-26')` — fixes the grid immediately.

**What Still Needs Debugging:**
1. Run `heroku logs -a bainluck --ps worker-background -n 500 | grep -i "kalshi"` after the next scheduled Kalshi poll (runs at :45 past every 4th hour) to confirm the task actually executes
2. Verify the classification fix works by checking `llm_sport_category` after the poll: `heroku pg:psql -a bainluck -c "SELECT external_id, llm_sport_category FROM futures_markets WHERE external_id LIKE 'KXNHL%' AND source='kalshi';"`
3. If still `basketball`, add explicit logging to `_categorize_kalshi_market()` for KXNHL tickers to trace the classification path
4. Check if there are OTHER misclassified conference markets across sports: `heroku pg:psql -a bainluck -c "SELECT external_id, name, llm_sport_category FROM futures_markets WHERE source='kalshi' AND (name LIKE '%Conference%' OR name LIKE '%Eastern%' OR name LIKE '%Western%') AND external_id NOT LIKE 'KXNBA%';"`

**Also discovered:** `sync_mm_bracket` task is still running (March Madness ended weeks ago) — wastes worker capacity. Disable it.

**Files:**
- `backend/app/services/kalshi_api.py` — `_fetch_all_events_unfiltered()` (status filter + supplementary fetch)
- `backend/app/tasks/kalshi.py` — `_categorize_kalshi_market()` (classification order), `poll_kalshi_markets` (upsert logic)
- `backend/app/config/league_configs.py` — NHL_CONFIG conference matching rules
- `backend/app/tasks/__init__.py` — Celery beat schedule (disable `sync_mm_bracket`)

**Key commands for debugging:**
```bash
# Check classification
heroku pg:psql -a bainluck -c "SELECT external_id, name, llm_sport_category FROM futures_markets WHERE source='kalshi' AND external_id LIKE 'KXNHL%';"

# Trigger poll
heroku ps:restart worker-background -a bainluck && sleep 30 && curl -X POST "https://api.bainluck.com/api/admin/kalshi/poll?secret=cleanup-soccer-2024"

# Check worker logs
heroku logs -a bainluck --ps worker-background -n 300 | grep -i "kalshi\|Fetched.*unique\|supplement"

# Verify grid
curl -s "https://api.bainluck.com/api/playoffs/nhl?debug=true" | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'  {m.get(\"source\"):12s} {m.get(\"external_id\")[:25]}') for m in d.get('_debug_column_markets',{}).get('conference',[])]"
```

### 0f-4. Sport Hierarchy Page Data Quality (Manus audit April 22)

Two issues reported by Manus league page audit. May be transient data issues — verify before investing time:
1. **EPL page shows Egyptian Premier League teams** — cross-league contamination in grid or event data. Grid API currently shows correct 20 English teams. May have been stale data at audit time.
2. **Tennis category page shows Golf content** — `/categories/tennis` or `/sport/tennis/atp` displaying golf tournaments. Tennis feed API returns correct data. May be a rendering path issue where golf-specific code runs for non-golf sports.

**Verify:** Visit `/sport/soccer/epl` and `/sport/tennis/atp` in browser. If issues persist, trace the data loading path.
**Files:** `frontend/app/sport/[sport]/[league]/page.tsx`, `frontend/app/categories/[slug]/page.tsx`

---

### 0f-3d. Event Detail Market Completeness — 5 ISSUES (April 22 audit)

**Context:** Audited event 14523747 (Red Sox vs Yankees, April 22) to check if we're showing ALL available markets. Found 21 linked markets (all Kalshi), but several data quality issues.

#### Issue 1: NBA markets incorrectly linked to MLB event
Two NBA markets (`KXNBA2D-26APR09BOSNYK`, `KXNBA1HSPREAD-26APR09BOSNYK`) are linked to this MLB event via `event_id`. Root cause: "Boston" + "New York" city name collision — Celtics/Knicks game matched Red Sox/Yankees event. The game-markets endpoint filters these out via `llm_sport_category` so they don't display, but they waste the `event_id` FK slot.

**Fix:** Add sport validation in prediction market matching — if market ticker starts with `KXNBA`, don't link to a `baseball_mlb` event. Check `sport_id` consistency between market and event before linking.
**Files:** `tasks/prediction_market_matching.py` (Pass 2 general scan)

#### Issue 2: Zero Polymarket game-specific markets linked
~20 Polymarket markets exist mentioning Red Sox/Yankees (NRFI, win markets), but ALL have `sport_id=None` and `llm_sport_category=None`. They're never considered for linking because the matching task requires sport identification.

**Fix:** Improve Polymarket sport classification. These markets have team names in their titles ("New York Yankees vs. Boston Red Sox") — the matching task should detect the sport from team names even without explicit sport metadata.
**Files:** `tasks/polymarket.py` (sport classification), `tasks/prediction_market_matching.py`

#### Issue 3: Tomorrow's game markets linked to today's event
6 Kalshi markets with APR23 tickers (tomorrow's game) are linked to today's event. The matching task linked them based on team name + time window without distinguishing the game date embedded in the ticker.

**Fix:** Extract game date from Kalshi ticker (e.g., `KXMLBHIT-26APR23NYYBOS` → April 23) and compare to event `commence_time` date. Reject if dates differ by >1 day.
**Files:** `tasks/prediction_market_matching.py`, `utils/prediction_market_matching.py` (`extract_game_date_from_ticker`)

#### Issue 4: Series Winner market unlinked (ticker parsing bug)
Market `KXMLBSERIES-26APR21NYYBOS` ("Yankees vs Red Sox: Series Winner") exists but isn't linked. The ticker team extraction returned `["Yankees", "Celtics"]` instead of `["Yankees", "Red Sox"]` — a parsing bug.

**Fix:** Debug ticker team extraction for `KXMLBSERIES` prefix. The Celtics/Red Sox confusion suggests the city-to-team mapping defaults to the wrong sport.
**Files:** `utils/prediction_market_matching.py` (ticker team extraction)

#### Issue 5: Game props have market_tier=1 (should be tier 5) — CODE ORDERING BUG
85/136 outcomes in related-futures are game props with `market_tier=1`. Root cause is a code ordering bug in `kalshi.py`:
1. Line 287: `_kalshi_category_to_internal()` returns `"championship"` for all sports categories
2. Line 336-338: `compute_market_tier()` sees `category=="championship"` → returns tier 1
3. Line 364-366: `is_game_prop()` correctly updates `category = "game_prop"` — but AFTER tier was already computed

**Impact:** Game props leak into the season-long query (Pass 1 of related-futures, which loads tiers 1-4) instead of being restricted to Pass 2 (game-prop query, `event_id == event_id`). This means game props from OTHER games could appear on the wrong event page.

**Fix:** Move `is_game_prop()` check and `category = "game_prop"` assignment to BEFORE `compute_market_tier()`, OR add game prop detection inside `compute_market_tier()`. Then backfill existing market_tier values.
**Files:** `tasks/kalshi.py:336-366`, `utils/market_label_normalization.py:737-792` (`compute_market_tier`)
**Parallel Safety:** Yellow (affects market ingestion + grid/futures display)

---

### 0f. Event Detail Below-the-Fold Redesign (from Claude Design prototype)

Design prototype: `handoffs/Event Detail Below-the-Fold.html`
Brief: `docs/design-brief-event-detail-v2.md`

Steps 1-5 shipped April 22. Remaining:
6. **TradeWatch rethink** — one-sided, highest-prob destination only (partially done — disclaimer added, layout fix needed)

**Parallel Safety:** Yellow (frontend only, no backend changes)

---

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

## iOS App — Web Parity & Polish (April 22, 2026)

Major iOS overhaul April 22 evening (~30 commits). Core event detail now has: hero with team logos/scores, multi-source win prob chart with period markers, score diff chart with period markers, ChampionshipPathView (from team-progression), PlayerPropsCardView (from game-markets), awards, season stats, trade watch, clean error messages.

### ~~iOS-1. Period Markers~~ — SHIPPED
### ~~iOS-2. Feed Card Polish~~ — SHIPPED
### ~~iOS-3. Chart Clipping~~ — SHIPPED
### ~~iOS-cleanup~~ — SHIPPED: removed LineMovement, divergence badge, tags, baseball clock, refresh countdown

### ~~iOS-7/8/9/10~~ — SHIPPED (April 22)
Period markers on score diff chart, championship card filter fix, ChampionshipPathView from team-progression endpoint, PlayerPropsCardView from game-markets endpoint.

### iOS-11. Sections Disappear on Auto-Refresh — CRITICAL BUG

**Problem:** Player Props, Championship Path, and other sections vanish after ~30 seconds. The auto-refresh re-runs `load()` which overwrites existing data with `nil` when a fetch fails transiently.

**Fix:** Only update `@Published` properties when the new value is non-nil. Already coded (April 22 evening), needs push.
**Files:** `EventDetailView.swift`

### iOS-12. Score Diff Actual Line Cuts Off Mid-Game — BACKEND BUG

**Problem:** The teal "Actual Score Diff" line stops partway through the game (e.g., 5th inning).

**Root cause found (April 22):** ALL 7 ESPN history points have `homeScore=None, awayScore=None`. The ESPN sync writes period/clock data to ESPNSnapshot but scores are null. The score diff chart only gets 3 ScoreSnapshot data points from the Odds API (5-minute polling). This is a BACKEND issue — the ESPN API response parsing may not be extracting scores, or ESPN isn't providing them for this event type.

**Fix:** Debug the ESPN sync score extraction: `ee.home_score` is None when writing ESPNSnapshot. Check what the ESPN API returns and how it's parsed. The `_sync_espn_live_events` function at line 493 sets `event.home_score = ee.home_score` — this path works for Event updates but the snapshot write at line 541 may be running before scores are available.
**Files:** `backend/app/tasks/espn_sync.py` (ESPN API response parsing), `backend/app/services/espn_api.py`

### iOS-13. Score Diff X-Axis Doesn't Match Win Prob

**Problem:** Win prob chart shows 4:11-6:11 PM, score diff shows 4:00-6:00 PM. Both use `commenceTime` → `completedAt+2min` for domain, but the tick labels differ because Swift Charts auto-picks different nice-number intervals for different data densities.

**Fix:** Both charts need identical x-axis domain. Options: (a) pass OddsChart domain down to ScoreDiffChart via state binding, or (b) use the raw `commenceTime` and `completedAt` strings parsed identically. Current code may have different Date precision (OddsChart may round/filter start differently).
**Files:** `ScoreDifferentialChartView.swift`, `OddsChartView.swift`, `EventDetailView.swift`

### iOS-14. Player Prop Threshold Monotonicity

**Problem:** Goldschmidt shows 3+ Hits at 6% but 2+ Hits at 72%. Probabilities should be monotonically decreasing (P(3+) ≤ P(2+)). Root cause: likely mixing HITS and HITS+RUNS+RBIS stat types under the same player's card.

**Fix:** In `PlayerPropsCardView`, group rungs strictly by `marketName` (not just player name). The stat type label (HITS vs HITS+RUNS+RBIS) must scope each ladder independently.
**Files:** `PlayerPropsCardView.swift`

### iOS-15. Bigger Picture Section Needs Redesign

**Problem:** The compact 2-column grid duplicates Player Props (same game prop data from related-futures). Shows last names + thresholds with no context. Users can't tell what markets these are.

**Current state:** `GamePropsView` renders game_prop futures from related-futures endpoint. `PlayerPropsCardView` renders from game-markets endpoint. Both show the same underlying data in different formats.

**Fix options:**
- Remove `GamePropsView` from Bigger Picture since `PlayerPropsCardView` covers game props better
- Rename "Bigger Picture" to something that reflects what remains (awards, season stats, trades, novelty)
- Or redesign to show only the non-game-prop futures (championship path already has its own section)

**Principle (from Alex):** NEVER remove data to simplify. Show ALL futures beautifully grouped. The web's below-the-fold is the reference.
**Files:** `RelatedFuturesView.swift`, `GamePropsView.swift`

### iOS-16. Season Stats Categorization Issues

**Problem:** "NL East Winner 18%" shows in Season Stats but belongs in Championship Path. "Longest Losing Streak 69%" is confusing without context.

**Root cause:** Backend `display_category` assignments are imperfect. "NL East Winner" is categorized as `season_stat` but should be `playoff_path` or `conference`. This is a backend data quality issue.

**Fix:** Either fix categorization in `backend/app/routes/events.py` (related-futures response builder), or add iOS-side reclassification rules.
**Files:** Backend: `routes/events.py` related-futures builder. iOS: `RelatedFuturesView.swift`

### iOS-17. Player Headshot Images — SEE 0f-3b

**Problem:** Player prop cards show initials avatars on both web and iOS. Backend headshot enrichment code exists but returns 0 headshots.

**Root cause:** See `0f-3b` above — roster data exists, enrichment code looks correct, but headshot URLs may not be in the stored JSONB entries. Fix is backend-only: trigger roster re-sync, then both web and iOS get headshots automatically.

**Files:** Backend: `routes/events.py` (game-markets endpoint enrichment). iOS: `PlayerPropsCardView.swift` (already handles headshot URLs)

### iOS-4. Dead/Stale Views Cleanup

**Problem:** Several views reference features that are seasonal, deprecated, or no longer maintained:
- `MastersLiveView.swift` — built for Masters tournament (April 9-12), now stale
- `EIRankingsView.swift` — may show outdated data
- `TournamentChartView.swift` / `TournamentCardView.swift` — golf-specific, may be stale

**Fix:** Audit each for staleness. Remove or hide views that show incorrect data. MastersLiveView should be generalized to "current tournament" or removed.

**Files:** `ios/Bain Luck/Bain Luck/Views/MastersLiveView.swift`, `ios/Bain Luck/Bain Luck/Views/EIRankingsView.swift`
**Parallel Safety:** Green

### iOS-5. Missing Pages (Weather, Economics, Categories Browser)

**Problem:** Web has Weather (`/weather`), Economics (`/economics`), and a category browser on the search page. iOS has none of these.

**Fix:** Add native views for each. Weather and Economics could start as simple list views showing market cards grouped by sub-theme, matching the web's structure. Categories browser could be integrated into the Search tab.

**Files:** New views + updates to `MainTabView.swift`, `Route.swift`
**Parallel Safety:** Green

### iOS-6. Feed `limit=200` Override

**Problem:** `FeedView.swift` was passing `limit: 200` explicitly, overriding the default `50` we set in `APIClient`. Fixed April 22 but not yet deployed in a build-verified commit.

**Files:** `ios/Bain Luck/Bain Luck/Views/FeedView.swift` — already fixed, needs build verification.
**Parallel Safety:** Green

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
