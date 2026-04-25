# Backlog (SINGLE SOURCE OF TRUTH)

All outstanding work items for Bain Luck. Shipped items live in `docs/completed-features.md`.

---

## Current Priority: Semantic Matching Excellence

The product's magic depends on **perfectly understanding every event, market, and source** — then grouping and matching them so the user sees one unified view. This is the #1 technical priority and the area with the most measurable room for improvement.

**Matching health dashboard:** `GET /api/admin/prediction-markets/link-rate` + admin dashboard at `/admin`

**FIXED (April 24):** Dashboard was showing all-time link rates (including resolved/closed markets in denominator). Now shows open-market-only rates. Numbers should be significantly higher and actually reflect matching work.

**Current state (April 25, 2026 — open markets only):**

Kalshi: **61.9%** (7,991 / 12,917) | Polymarket: **72%** (3,467 / 4,814)

| Sport | Kalshi open | Polymarket open | Target | Status |
|-------|------------|----------------|--------|--------|
| Tennis | 98.6% | 0.2% | >90% K, accept PM | **Kalshi: EXCELLENT** |
| MMA | 86.3% | — | >80% | **Kalshi: TARGET MET** |
| Baseball | 75.1% | 73.4% | >85% | Close on both |
| Esports | 69.4% | 5.1% | ~20% | **Kalshi: WAY above target** |
| Basketball | 58.9% | 93.8% | >85% | PM great, Kalshi needs work |
| Hockey | 59% | 23.8% | >80% | Both need work |
| Soccer | 44.4% | 98.6% | varies | PM excellent, Kalshi limited by minor league coverage |
| Rugby | — | 97.6% | N/A | PM only |
| Cricket | — | 28.2% | N/A | PM only |
| Golf | 0.7% | — | N/A | Not a bug — futures use grid, not event_id |

**Grid Health: 94/100** (NBA 94, NHL 97, MLB 87, Golf 100)

**Target: 100%** for all sports where matching is possible. Any miss on a market that SHOULD match is a bug.

**Audit tooling (April 23, 2026):**
- `scripts/audit_grid_accuracy.py` — Grid structural correctness. **51/51 (100%)** after hill-climb.
- `scripts/audit_event_matching.py` — Four-layer event matching audit (self-check + Manus ground truth modes).
- Plan: `.claude/plans/clever-nibbling-bumblebee.md`

---

## Tier 0 — Semantic Matching Accuracy (ACTIVE HILL-CLIMB)

### Four-Layer Matching Audit System — IN PROGRESS (April 23)

Built to measure and hill-climb matching accuracy to 100%. Same pattern as grid audit: measure → fix biggest bucket → re-measure → repeat.

**The real target**: every market on Kalshi/Polymarket for a game should appear on its bainluck event page. Not just championship/pennant/division — also novel props, broadcast props, announcer markets, "Which European finishes highest?", etc. If it exists, we show it.

**How matching works (two passes):**
- **Tier 1-4 (season markets)**: Load ALL markets for the sport, filter outcomes by team/player name matching. Catches championship, pennant, division, awards, make_playoffs.
- **Tier 5 (game props)**: Load only markets linked to this event via `event_id` FK. Catches spreads, totals, player props, game-specific novelty.
- **Gap**: Markets that are season-long but lack team names in outcomes (e.g., "Which European finishes highest?") fall through tier 1-4 matching. Markets that are game-adjacent but missing `event_id` linkage fall through tier 5.

**Layer 1: Event Existence** — Does every game exist with all sources?
- Status: Self-check working. Scheduled events have 1 source (betting only) — this is EXPECTED (ESPN/MLB/stat_model activate when games start). Live events have 4 sources. Not a real gap.
- NHL: all 3 events have only 1 source (betting) for scheduled games — expected.
- Next: Confirm no real L1 gaps exist by running during live games.

**Layer 2: Market → Event Linking** — Are all game markets linked correctly?
- Status: ✅ **ALL events have Kalshi markets.** MLB 8/8, NBA 3/3, NHL 3/3.
- Previous zero-market event (White Sox @ Diamondbacks) resolved — now has 12 Kalshi markets, 228 props.

**Layer 3: Futures Surfacing** — Do season futures show on event pages?
- Status: ✅ **100% across all 3 sports.** MLB 5/5, NBA 3/3, NHL 3/3.
- Hill-climbed April 23 from "all missing" to 100% via 7 commits:
  1. Audit vocabulary: label-level regex matching instead of wrong display_category names
  2. Make_playoffs regex: `\bmake.+(?:playoffs|postseason)` handles intervening league names
  3. Team name patterns: individual city words ≥4 chars (e.g., "Boston" from "Boston Red Sox")
  4. Stat leader classification: "Doubles Leader" etc. now `season_stat` not `championship`
  5. Tier assignment: name patterns checked BEFORE game_prop category shortcut (Kalshi mislabels season markets as game_prop)
  6. Per-tier market loading: 100 markets per tier prevents tier crowding (was flat 500 cap)
  7. Audit regex: "Playoff Qualifiers" pattern for Kalshi's alternate naming

**Layer 4: Market Completeness** — Are we showing EVERY market, none we shouldn't?
- Status: ✅ **VERIFIED LIVE** (April 24 Celtics game). 15 Kalshi markets, all required types, Polymarket moneyline showing.
- **Key finding**: We ingest EVERYTHING from Kalshi + Polymarket (minus crypto). No ingestion gap. Kalshi creates game markets 2-3 days before games. Discovery is NOT the bottleneck.
- **Root cause (confirmed)**: Kalshi market backfill queried `status=open` but live game markets have `status=active`. This prevented spread/total/F5/moneyline outcomes from being populated during games, even though the FuturesMarket records existed. **Fixed** — backfill now uses `status=None` (no filter).
- **Kalshi L4**: Required types (player props) ✅ present. Bonus types (spread/total/F5/moneyline) need live game verification — the backfill fix should make them appear when Kalshi has liquidity.
- **Polymarket L4**: ✅ Game moneylines for NBA playoffs. Season futures for all sports.
- **VERIFY April 24**: During the first live MLB game, check if spread/total/F5 appear on the event page and if Kalshi shows as a source on the win probability chart.
- **Fixes shipped (April 23, 10 commits):**
  1. `is_game_prop()` detects "Team vs Team Winner?" moneyline format
  2. Game-markets fallback uses Kalshi ticker prefixes, not just `category="game_prop"`
  3. NULL-status markets included for live events
  4. Per-tier season market loading (100/tier) prevents crowding
  5. Kalshi market backfill: removed `status=open` filter (missed `active` markets)
  6. Kalshi polling: 2h (markets posted days early, 4h was fine for discovery — backfill bug was the real issue)
  7. Matching task: every 15 min (was hourly) for faster linking
  8. Polymarket coverage added to L4 audit
  9. L4 audit distinguishes required vs bonus (liquidity-dependent) market types
  10. Bare matchup moneyline detection in audit

**Design needs** (market types now surfacing that may need frontend work):
| Type | Design Status | Notes |
|------|--------------|-------|
| Moneyline | ✅ | Win probability display |
| Spread/Total | ✅ | Game markets section |
| Player props | ✅ | Player props cards |
| F5/First Half | ⚠ Needs design | Currently in "other" section |
| Team totals | ⚠ Needs design | Separate from game totals |
| First Inning Run | ⚠ Needs design | Binary prop, no section |
| Announcer/broadcast | ❌ No design | Entirely new category |

**Hill-climb protocol (per iteration):**
1. Run `--l4-deep --sport {sport}` → identify missing types
2. Trace root cause in code
3. Write fix
4. Re-run audit → confirm score improved
5. If not 100%, go to step 1

**Files:**
- `backend/scripts/audit_event_matching.py` — four-layer audit script (self-check + L4 deep)
- `backend/scripts/audit_grid_accuracy.py` — grid accuracy (SHIPPED, 100%)
- `Manus/prompts/event_matching_ground_truth.md` — ground truth prompt (built, not yet run)
- Plan: `.claude/plans/clever-nibbling-bumblebee.md`

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

### 0f-4. Event Detail Page Quality Issues (April 23 live audit)

Spotted during Yankees vs Red Sox live game (event 14594074):

**~~0f-4a. Player prop monotonicity violation~~ ✅ FIXED (April 23)**
Kalshi "2+", "Aaron Judge: 1+" outcomes weren't detected as "over" thresholds — probabilities were inverted (`1-prob`), causing P(2+ runs) = 90% but P(5+ runs) = 97%. Fixed to recognize `N+` pattern as over outcomes. Affects both game totals and player props. **Needs live game verification April 24.**

**~~0f-4b. Score differential chart empty after 1st inning~~ ✅ FIXED (April 23)**
Root cause: ESPN's scoreboard API only provides ~2 win probability data points per MLB game (sparse `situation.lastPlay.probability` field). The MLB Stats API has ~50 dense data points with scores in `game_state`. Fix: when `espn_history` is sparse (<10 points), supplement with MLB/stat_model score data from `win_prob_history`. Yankees game went from 2 → 81 data points.

**0f-4c. Player props: no pre-game vs current comparison**
Cards show current probabilities but not what they were pre-game or actual results so far. During a live game, "was 22% pre-game, now 45%" would be much more useful context. Need pre-game snapshot + actual stat tracking.
**Files:** Frontend `components/PlayerPropsCardView`, backend game-markets endpoint

**0f-4d. Player award headshots STILL missing**
Roster `player_metadata` lookup was enabled for completed events (April 23 fix), but award outcomes often reference players NOT on either team's roster (e.g., Quentin Grimes for 6MOY). The headshot lookup only checks the two event teams' rosters. Fix needs to either: look up ALL rosters for the sport, or use a separate player image service.
**Files:** `routes/events.py` (player_metadata scope), `RelatedFutures.tsx` (PlayerHeadshot component)

**0f-4e. Slow headshot loading (~60s)**
Player prop cards show initials for ~60 seconds before headshots load. Either the roster data fetch is slow or headshot URLs need preloading.
**Files:** Frontend image loading, backend roster sync timing

### 0f-5. Event Detail Issues from Celtics Playoff Game Audit (April 24)

Spotted on 76ers vs Celtics (event 14595395, scheduled playoff game):

**~~0f-5a. Monotonicity in Projected Combined Scoring~~ ✅ FIXED (April 24)**
Root cause: 1H/2H totals ("First Half Total", "Second Half Total") were classified as `game_total` instead of `half_total`. The pattern check only matched "1st half" not "First Half". Fixed in `_classify_game_market()`. Verified: 11 game_total items, all monotonically decreasing.

**~~0f-5b. Spread section raw dump~~ ✅ FIXED (April 24)**
Now groups by market name (Full Game / First Half / Second Half), sorts by probability within each group, caps at 8 outcomes per group with "+N more" indicator.

**~~0f-5c. Polymarket "Yes" labels~~ ✅ FIXED (April 24)**
"Yes"/"No" outcomes on matchup markets now resolved to team names. "Celtics vs. 76ers — Yes 71%" → "Celtics Win 71%". Regex extracts team from market name.

**~~0f-5d. "since start" label~~ ✅ FIXED (April 24)**
Changed to "since open" for all events (pre-game and post-game).

**~~0f-5e. Award label verbosity~~ ✅ FIXED (April 24)**
`shortAwardLabel()` now strips "NBA Playoffs:", "Eastern/Western Conference" prefixes. "NBA Playoffs: Finals MVP" → "Finals MVP".

### ~~0f-6. iOS/Web Chart Axis Alignment~~ ✅ FIXED (April 24)

Two fixes:
1. **iOS Score Diff chart noise**: X-axis `AxisMarks` had no count limit, creating grid lines at every data point (hundreds). Fixed to `desiredCount: 5`.
2. **Web + iOS chart axis alignment**: Win Probability and Score Differential charts now share a single computed domain (`sharedChartDomain`) from ALL data sources. Both charts fill every minute in the range, ensuring identical x-axes, linear time, and aligned period markers. Previously OddsChart computed its own domain and reported it async — now both use the same parent-computed domain.

### 0f-7. Mac App (April 24)

Consider building a Mac app (Catalyst or SwiftUI for macOS). The iOS app already has most of the views — macOS would give a desktop experience with sidebar navigation.

---

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

### ~~0f-3b. Player Prop Headshots~~ ✅ DONE (April 23)

Roster sync fixed: moved to 10 AM UTC, loaded 3,261 players across MLB/NBA/NHL with headshot URLs. Enrichment gating bug fixed (`player_roster_info` instead of `player_headshots`). Verified: 151/156 props return headshots + team assignments for Padres-Rockies game. Both web and iOS now display headshots.

### 0f-3. Live Box Score Integration for Player Props
Player prop cards should show actual stats from `box_score_data` during live games (e.g., "Jayson Tatum: 18 points so far vs 24.5 O/U"). The `boxScore` prop is wired but the matching logic needs work — player names from Kalshi props don't always match ESPN box score names.
**Files:** `frontend/components/PlayerPropsDashboard.tsx` (matching), `backend/app/routes/events.py` (box score in response)

### ~~0f-X. Kalshi conference markets misclassified as wrong sport~~ ✅ RESOLVED (April 24)

**Status:** RESOLVED. Verified April 24: both KXNHLEAST-26 and KXNHLWEST-26 showing correctly in NHL grid with `llm_sport_category=hockey`. The classification order fix + Kalshi poll cycle resolved it. Hotfix no longer needed.

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

## PREQ Sprint — Performance, Reliability, Efficiency, Quality

Dedicated pass to make everything faster, more reliable, and higher quality. Ordered by impact-to-effort ratio.

### Phase 1: Quick Wins (ship in one session)

#### PREQ-1. Request Timing Middleware
**What:** Add FastAPI middleware that logs slow requests (>500ms) and sets `X-Response-Time` header on every response. Gives us real latency data instead of guessing.
**Files:** `backend/app/main.py`
**Risk:** Middleware runs on every request — adds ~0.1ms overhead per request.
**Mitigation:** Only the logging branch (>500ms) does string formatting. Header assignment is negligible. No DB or I/O in the hot path.
**Parallel Safety:** Green

#### PREQ-2. API Client Timeout
**What:** Add 15s `AbortController` timeout to `apiFetch()` in the frontend. Prevents infinite white-screen hangs when the API is slow or unreachable.
**Files:** `frontend/lib/api.ts` — `apiFetch()`
**Risk:** Aggressive timeout could abort legitimately slow endpoints (admin audit, data quality check).
**Mitigation:** 15s is generous for user-facing endpoints (feed, events, playoffs). Admin endpoints already have their own fetch wrappers. Could add per-call timeout override parameter.
**Parallel Safety:** Green

#### PREQ-3. HTTP Cache-Control Headers
**What:** Add `Cache-Control` response headers so browsers cache stable data:
- `/api/feed` — `max-age=10` (changes frequently)
- `/api/events/{id}` (completed) — `max-age=300` (5 min, data frozen)
- `/api/events/{id}` (live) — `max-age=5`
- `/api/playoffs/{sport}` — `max-age=60`
- `/api/events/{id}/history` — `max-age=30`
**Files:** `backend/app/routes/feed.py`, `events.py`, `playoffs.py`
**Risk:** Stale data shown to users if cache TTL is too long. Live game data could be 5-10s behind.
**Mitigation:** Conservative TTLs (5-10s for live, 60s for grids). Users already see 30s refresh intervals on the frontend (SWR), so 5-10s server cache is invisible. `Vary: Authorization` header ensures authenticated vs anon responses aren't cross-cached. Completed events are truly immutable — 5 min is safe.
**Parallel Safety:** Yellow (touches multiple route files)

#### PREQ-4. Connection Pool Tuning
**What:** Increase SQLAlchemy connection pool from `pool_size=10, max_overflow=15` to `pool_size=20, max_overflow=20`. Under concurrent load (5 users × 8 queries = 40 connections), current pool exhausts and requests queue.
**Files:** `backend/app/services/database.py`
**Risk:** Exceeding Heroku Postgres connection limit causes hard errors (connection refused).
**Mitigation:** Check `heroku pg:info` for plan limit first (Standard-0 = 120 connections). With 20+20=40 max from web dyno, plus 4 realtime workers + 2 background workers (each with their own sync connections), we're well under 120. Monitor with `heroku pg:info | grep Connections` after deploy.
**Parallel Safety:** Green

#### PREQ-5. SWR Refresh Interval Tuning
**What:** Reduce unnecessary polling:
- My Stuff page: 15s → 60s (pins don't change that fast)
- Grouped feed: 60s → 120s (or merge into main feed response)
- Add `dedupingInterval: 5000` globally to prevent duplicate requests when components remount
**Files:** `frontend/app/my-stuff/page.tsx`, `frontend/app/page.tsx`
**Risk:** User sees stale data on My Stuff for up to 60s after pinning something elsewhere.
**Mitigation:** SWR still revalidates on focus and on mount. Manual pin/unpin actions trigger immediate `mutate()` calls already. The 15s interval was burning API quota for no visible benefit.
**Parallel Safety:** Green

### Phase 2: Backend Performance

#### PREQ-6. Feed Endpoint Redis Caching
**What:** Add Redis-backed response cache to `/api/feed` with 10-15s TTL. Key by `(sport_filter, auth_state)`. Uses existing Redis connection from Celery. Most expensive endpoint (6-10 queries, complex scoring) — serves identical results to all anonymous users.
**Files:** `backend/app/routes/feed.py`
**Risk:** (1) Cache serving stale data during rapid odds changes. (2) Redis connection failure blocks feed. (3) Cache key collision between users with different preferences.
**Mitigation:** (1) 10-15s TTL means data is at most 15s stale — same as current SWR interval. (2) Wrap Redis in try/except — on failure, fall through to DB query (graceful degradation). (3) Key includes user ID for authenticated users; anonymous users share cache (acceptable — they all see the same feed).
**Parallel Safety:** Yellow (touches feed.py)

#### PREQ-7. N+1 Query Audit
**What:** Resolve top Sentry N+1 warnings. Search for `await db.execute(select(` inside loops. Replace with `selectinload()` eager loading or batch queries.
**Files:** `routes/feed.py`, `routes/events.py`, `routes/playoffs.py`
**Risk:** Eager loading can fetch too much data if relationships are large (e.g., loading all outcomes for all futures markets).
**Mitigation:** Use `selectinload()` (separate IN query) not `joinedload()` (cartesian product). Profile before/after with PREQ-1 timing middleware. Only fix patterns that Sentry flags as high-frequency (>100 events).
**Parallel Safety:** Yellow (one file at a time)

### Phase 3: Frontend Performance

#### PREQ-8. Dynamic Imports for Heavy Libraries
**What:** Recharts (~200KB) and framer-motion (~100KB) are loaded on every page. Use `next/dynamic` with `{ ssr: false }` for chart components so they're only loaded on pages that use them.
**Files:** Components importing Recharts: `OddsChart.tsx`, `EvolutionChart.tsx`, `FuturesChart.tsx`, `ScoreDifferentialChart.tsx`, `TournamentChart.tsx`
**Risk:** Flash of empty space while chart loads asynchronously. SSR output won't include charts (but we're already client-side only with `"use client"`).
**Mitigation:** Add a loading skeleton (`<div className="h-48 bg-surface-elevated animate-pulse rounded" />`) as the `loading` prop to `dynamic()`. Since these components already use `"use client"`, SSR isn't affected.
**Parallel Safety:** Green

#### PREQ-9. Image Optimization
**What:** Audit `<img>` tags for team logos and replace with Next.js `<Image>` for automatic lazy loading, sizing, and format optimization. Add `loading="lazy"` for below-fold images.
**Files:** `frontend/components/EntityImage.tsx`, `FeedCard.tsx`, any component using `<img src={espnCdn}>`
**Risk:** Next.js Image requires `width`/`height` or `fill` prop — could break layout if sizes aren't specified correctly. ESPN CDN domain needs to be in `next.config` `images.remotePatterns`.
**Mitigation:** Use `fill` with `sizes` prop for dynamic team logos. Check `next.config` already allows `a.espncdn.com` (likely does since logos already load). Test on a single component before bulk migration.
**Parallel Safety:** Green

### Phase 4: Reliability & Quality

#### PREQ-10. Health Endpoint Enhancement
**What:** Enhance `/health` to check DB connectivity, Redis connectivity, and last successful poll timestamp per source. Returns structured health object for monitoring.
**Files:** `backend/app/routes/health.py`
**Risk:** Health check itself could be slow if DB/Redis are unhealthy (timeout waiting for connection).
**Mitigation:** Add 2s timeout on DB `SELECT 1` and Redis `PING`. If either times out, return `degraded` status with the failing component identified. Don't let the health check hang.
**Parallel Safety:** Green

#### PREQ-11. Graceful Source Degradation
**What:** Wrap each source enrichment step in feed/event endpoints with try/except. If ESPN is down, still return betting + prediction market data. If Kalshi is down, still return Polymarket + Odds API.
**Files:** `backend/app/routes/feed.py`, `routes/events.py`
**Risk:** Silently swallowing errors could mask real bugs.
**Mitigation:** Log each source failure at WARNING level with source name + error. Add a `_degraded_sources` field to the API response so the frontend could show "ESPN data unavailable" if needed. Already validated this pattern during March 2026 Odds API outage.
**Parallel Safety:** Yellow

#### PREQ-12. Sentry Noise Cleanup
**What:** Resolve top 3 N+1 warnings by event count (covered by PREQ-7). For remaining low-frequency warnings (WorkerLost/SIGTERM, Redis transient drops), configure Sentry ignore rules so real errors surface faster.
**Files:** `backend/app/main.py` (Sentry config)
**Risk:** Over-filtering could hide real errors.
**Mitigation:** Only ignore specific known-harmless error types: `WorkerLost` (normal recycling), `TimeLimitExceeded` (Polymarket poll — already known), transient Redis `ConnectionError`. Never ignore 500s or unhandled exceptions.
**Parallel Safety:** Green

### Implementation Order

| # | Item | Effort | Impact | Risk Level |
|---|------|--------|--------|------------|
| PREQ-1 | Request timing middleware | 15 min | Unlocks data | Low |
| PREQ-2 | API client timeout | 10 min | Reliability | Low |
| PREQ-3 | Cache-Control headers | 30 min | **High** perf win | Medium |
| PREQ-4 | Connection pool tuning | 5 min | Moderate | Low (check plan limits) |
| PREQ-5 | SWR interval tuning | 15 min | Moderate | Low |
| PREQ-6 | Feed Redis caching | 45 min | **Highest** perf win | Medium |
| PREQ-7 | N+1 query audit | 1-2 hr | Moderate | Medium |
| PREQ-8 | Dynamic imports | 20 min | Bundle size | Low |
| PREQ-9 | Image optimization | 30 min | LCP improvement | Low |
| PREQ-10 | Health endpoint | 30 min | Reliability | Low |
| PREQ-11 | Source degradation | 30 min | Reliability | Medium |
| PREQ-12 | Sentry cleanup | 15 min | Quality | Low |

**Start with PREQ-1 through PREQ-5 (quick wins, ~75 min). Then PREQ-6 (biggest single win). Then remainder.**

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

### 19. "What Are The Odds?" Discovery Page

**Goal:** Surface the most interesting prediction markets across ALL categories in one browsable page. The front door for non-sports content. Extends Bain Luck's "visual probability" brand from sports to everything.

**URL:** `/explore` (or `/odds` — TBD)

**Why now:** We're ingesting 15K+ markets from Kalshi and Polymarket but only surfacing sports + weather + economics. Markets like "Taylor Swift meets Pope Leo" and "Foldable iPhone in 2026" are sitting in the DB invisible to users. These are exactly the kind of questions that make someone stop and think.

**Design concept:**

```
┌─────────────────────────────────────────────────┐
│  What Are The Odds?                             │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │  🔥 Featured: Will Taylor Swift meet      │  │
│  │     Pope Leo XIV before 2027?        23%  │  │
│  │     ████████░░░░░░░░  kalshi              │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ Pop      │ │ Politics│ │ Tech &  │          │
│  │ Culture  │ │         │ │ Science │          │
│  │ 47 mkts  │ │ 312 mkts│ │ 89 mkts │          │
│  │          │ │         │ │         │          │
│  │ Swift/   │ │ Alito   │ │ Foldable│          │
│  │ Pope 23% │ │ retire  │ │ iPhone  │          │
│  │          │ │ 18%     │ │ 12%     │          │
│  │ Oscar    │ │         │ │         │          │
│  │ host 45% │ │ Canada  │ │ GPT-5   │          │
│  │          │ │ rate 67%│ │ 2026 88%│          │
│  └─────────┘ └─────────┘ └─────────┘          │
│                                                 │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ Weather  │ │Economics│ │ Health  │          │
│  │ →/weather│ │→/econ   │ │ 31 mkts │          │
│  └─────────┘ └─────────┘ └─────────┘          │
└─────────────────────────────────────────────────┘
```

**Key design decisions:**
- **Featured market** at top — algorithmic (most decisive probability, or most recently moved) with manual override via admin
- **Category cards** — each shows market count + 2-3 most interesting markets as previews
- Weather and Economics link to their existing dedicated pages
- Categories without dedicated pages show an inline expanded view on click
- Each market card: question text + probability bar + source badge (Kalshi/Polymarket/both)
- Cross-source comparison when both platforms have the same market
- Light mode only, probability-first design (consistent with rest of site)

**"Interestingness" ranking** (for picking preview markets per category):
1. Probability is decisive but not resolved (15-85%, not 50/50 noise)
2. Multiple sources agree (cross-platform signal)
3. Recently moved (price change in last 24h)
4. Has resolution date within 90 days (timely)

**Backend:**
- `GET /api/explore` — returns all open non-sport markets grouped by `llm_sport_category`, sorted by interestingness
- Featured market endpoint (or field in explore response): `GET /api/explore/featured`
- Admin: `POST /api/admin/explore/feature?market_id=X` to pin a featured market
- Uses existing `_NON_SPORT_CATEGORIES` set from `market_label_normalization.py`

**Frontend:**
- New page at `frontend/app/explore/page.tsx`
- `CategoryPreviewCard` component (reusable for each category)
- `MarketProbabilityCard` component (question + bar + source — reusable across site)
- GA4 tracking hooks
- No gambling language — "What are the odds" framing, not "bet on"

**Relationship to Item 18:**
Item 18 builds deep category pages (economics themes, political sub-categories). This page is the **discovery layer on top** — a curated front door that links into those deeper pages. Build this first as a lightweight MVP, then build deep category pages as follow-ups.

**Parallel Safety:** Green (new route, new page, no conflicts)

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

### ~~iOS-15. Bigger Picture Section Redesign~~ ✅ DONE (April 23)

V6 redesign: renamed to "Season Futures". Stat leader markets (Doubles Leader, ERA Leader, etc.) extracted from championship bucket into new "Stat Leaders" section with 2-column grid grouped by stat type. Season Stats renamed to "Season Outlook". Division/conference winner patterns now properly route to championship path. All futures shown — nothing removed.

### ~~iOS-16. Season Stats Categorization~~ ✅ DONE (April 23)

iOS-side reclassification: expanded `isDivisionOrPlayoff` regex to catch "NL East Winner", "AL West Winner", etc. New `isStatLeader` regex catches "Leader" markets miscategorized as championship by backend. Active items filtered (skip <=1% and >=99%).

### ~~iOS-17. Player Headshot Images~~ ✅ DONE (April 23)

Roster sync fixed (moved to 10 AM UTC, 3,261 players loaded). Backend returns `player_headshot` + `player_team` on game-markets endpoint. iOS `PlayerPropsCardView` updated to show AsyncImage headshots with initials fallback, plus uses `playerTeam` from API instead of guessing from name.

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
- **Self-Evolving Website** — closed-loop autonomous improvement cycle:
  - (A) User browsing → events captured (clicks, scrolls, dwell time) → `events.jsonl`
  - (B) Coding sessions → MyClaw indexes sessions, extracts patterns & insights → facts
  - (3) Self-evolve cron (hourly): reads events + facts, decides what to build
  - (4) Claude writes code: React pages, API routes, nav-registry.json, sidebar entries
  - (5) Deploy → new features appear via hot reload
  - `/evolution` page: the website watches itself grow
  - Inspiration: "75 runs, 59 features shipped autonomously, 8→30 pages, zero human commits, ~24 min longest single build"
  - Key principle: "Usage data is the best product spec"

---

## Housekeeping

### WrestleMania — **DONE (April 21)**
Archive: `docs/archive/wrestlemania-reference.md`. All runtime code deleted. DB tables preserved.

### Other
- **May 1**: Delete `frontend/_to-delete/` if nothing broke
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches
- Code review reference: `.claude/plans/mutable-cooking-ember.md`
