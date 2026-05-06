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
- **Key finding (updated April 29)**: We ingest everything from Kalshi + Polymarket (minus crypto, confirmed 0 in DB). Polymarket game events now decomposed into per-sub-market rows — player props, spreads, O/U all surfacing alongside Kalshi. 29,785 sub-markets created across all sports. Crypto cleanup complete (26 stale markets deleted).
- **Root cause (confirmed)**: Kalshi market backfill queried `status=open` but live game markets have `status=active`. This prevented spread/total/F5/moneyline outcomes from being populated during games, even though the FuturesMarket records existed. **Fixed** — backfill now uses `status=None` (no filter).
- **Kalshi L4**: Required types (player props) ✅ present. Bonus types (spread/total/F5/moneyline) need live game verification — the backfill fix should make them appear when Kalshi has liquidity.
- **Polymarket L4**: ✅ **FIXED (April 29)** — Game moneylines, spreads, O/U, AND player props now surfacing. Root cause: Polymarket game events (40 sub-markets) were stored as 1 FuturesMarket with all sub-markets flattened into outcomes. Decomposition fix creates per-sub-market FuturesMarket rows. Matching task propagates event_id to sub-markets on link. Verified: HOU vs BAL shows 42 Polymarket items (spreads, O/U, player props) alongside 101 Kalshi. Backfill script: `scripts/backfill_polymarket_submarkets.py`.
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
| F5/First Half | ✅ Removed | Period markets removed; market maps replace them |
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

## Tier 0.5 — Feed & Navigation Quality (April 25 Review)

### 0n. Navigation Redesign — NEEDS DESIGN BRIEF

**Proposed structure:** Feed | Categories | My Stuff + Search bar (all platforms)

**Categories** (dropdown on hover/click + full `/categories` page):
- **Sport** — subcategories for each sport/league (NBA, NFL, MLB, NHL, Golf, Soccer, etc.)
- **Weather** — existing `/weather` page
- **Economics** — existing `/economics` page
- **Entertainment** — placeholder filtered feed view
- **Politics** — placeholder filtered feed view

**Current state (inconsistent):**
- Desktop web: Feed | Search | Weather | Economics | My Stuff
- Mobile web: Feed | Search | My Stuff (no Weather, Economics, Leagues)
- iOS: Feed | Leagues | Search | My Stuff
- Mac: Same as iOS with sidebar

**Requirements:**
- Consistent across web desktop, web mobile, iOS, Mac
- Dropdown + full page for Categories (confirmed April 25)
- Sport subcategories show leagues within each sport
- Needs a proper design brief before implementation (memory: "Nav needs design")

**Files:** `frontend/components/DesktopNav.tsx`, `frontend/components/BottomNav.tsx`, `ios/Bain Luck/Bain Luck/Views/MainTabView.swift`, new `/categories` routing
**Parallel Safety:** Red (touches navigation on all platforms)

### 0s. League Pages: Surface ALL Sport Markets (Series, Awards, Playoff Props, Season Stats) — Phase 1 SHIPPED

**Problem:** The league page (`/sport/basketball/nba`) is a single-purpose page — it shows the championship grid and nothing else. Meanwhile we're ingesting thousands of markets from Kalshi and Polymarket that are clearly sport-specific (NBA series winners, MVP, DPOY, playoff win totals, sweeps, Game 7 counts, player return dates) and NOT showing them anywhere at the league level. Users have to stumble onto these via individual event detail pages or the generic futures browser.

Kalshi's own NBA page organizes into 5 tabs: **Games, Series, Futures, Playoff Props, Awards**. We have the data for all 5 — we just don't surface it.

**What we have in the DB (examples for NBA, April 2026):**

| Market Type | Example | DB Classification | Currently Shown On League Page? |
|-------------|---------|-------------------|-------------------------------|
| Championship | "NBA Championship Winner" | tier 1, `playoff_path` | ✅ Grid |
| Conference | "Eastern/Western Conference Winner" | tier 2, `conference` | ✅ Grid |
| Division | "Atlantic Division Winner" | tier 4, `division` | ✅ Grid |
| Make Playoffs | "Team to Make Playoffs" | tier 4, `playoff_path` | ✅ Grid |
| **Series Winner** | "Celtics vs Cavaliers: Series Winner" | tier 5 or `game_prop` | ❌ **Not shown** (see also 0f-3d Issue 4) |
| **MVP** | "NBA MVP Winner" | tier 3, `award` | ❌ **Not shown** |
| **DPOY/6MOY/MIP/ROY** | "Defensive Player of the Year" | tier 3, `award` | ❌ **Not shown** |
| **Finals MVP** | "Finals MVP Winner" | tier 3, `award` | ❌ **Not shown** |
| **Conference Finals MVP** | "Eastern/Western Conference Finals MVP" | tier 3, `award` | ❌ **Not shown** |
| **All-Pro/All-NBA** | "All-Pro Basketball 3rd Team Selections" | tier 3, `award` | ❌ **Not shown** |
| **Playoff Win Totals** | "Playoff Win Total: Boston 12+" | tier 4-5, `season_stat` | ❌ **Not shown** |
| **Series Sweeps** | "Number of Series Sweeps in 1st Round" | tier 5, `novelty`/`prop` | ❌ **Not shown** |
| **Game 7 Count** | "Number of Series that go to a Game 7" | tier 5, `novelty`/`prop` | ❌ **Not shown** |
| **Player Return** | "Luka Doncic: Next Game Played Before May 7" | tier 5, `prop` | ❌ **Not shown** |
| **Stat Leaders** | "PPG Leader", "RPG Leader" | tier 3-4, `season_stat` | ❌ **Not shown** |
| **Win Totals** | "Regular Season Win Total: OKC 65.5" | tier 4, `season_stat` | ❌ **Not shown** |

**Design direction:**

The league page should become a **one-stop destination** for everything happening in that sport, organized into clear sections. Inspired by Kalshi's tab structure but translated into Bain Luck's probability-first visual language (NO American odds, NO gambling terminology, probability bars everywhere).

**Proposed league page layout:**

```
┌─────────────────────────────────────────────────────┐
│  NBA  [Games] [Futures] [Awards] [Props]            │
│                                                      │
│  ── Today's Games (from 0p — ✅ SHIPPED) ─────────  │
│  [Live event cards — same as feed, filtered by sport]│
│                                                      │
│  ── Championship Race ────────────────────────────  │
│  [Existing championship grid — Make PO → Champ]     │
│  [Evolution chart below]                             │
│                                                      │
│  ── Playoff Series ───────────────────────────────  │
│  ┌──────────────────┐ ┌──────────────────┐          │
│  │ MIN vs DEN (6)   │ │ HOU vs LAL (5)   │          │
│  │ MIN 62% ████████░│ │ HOU 78% █████████│          │
│  │ DEN 38% █████░░░░│ │ LAL 22% ███░░░░░░│          │
│  │ Game 5: Apr 27   │ │ Game 6: Apr 28   │          │
│  └──────────────────┘ └──────────────────┘          │
│  ┌──────────────────┐ ┌──────────────────┐          │
│  │ NYK vs ATL (2-2) │ │ BOS vs PHI (3-1) │          │
│  │ ...              │ │ ...              │          │
│  └──────────────────┘ └──────────────────┘          │
│                                                      │
│  ── Awards ───────────────────────────────────────  │
│  MVP                    Finals MVP                   │
│  ┌────────────────┐    ┌────────────────┐           │
│  │ 🏀 SGA    89%  │    │ 🏀 SGA    35%  │           │
│  │ 🏀 Jokic   8%  │    │ 🏀 Wemby  28%  │           │
│  │ 🏀 Giannis 2%  │    │ 🏀 Jokic  15%  │           │
│  └────────────────┘    └────────────────┘           │
│  DPOY        6MOY        MIP        ROY             │
│  [compact cards with top 2-3 candidates each]       │
│                                                      │
│  ── Playoff Props ────────────────────────────────  │
│  Series Sweeps (1st Rd)     Game 7 Count            │
│  At least 1: 91%            3+ series: 23%          │
│  At least 2: 32%            4+ series: 5%           │
│                                                      │
│  Playoff Win Totals                                  │
│  BOS 12+: 55%  |  SAS 10+: 62%  |  OKC 14+: 28%   │
│                                                      │
│  Player Watch                                        │
│  Luka Doncic back before May 7: 55%                 │
│  Luka Doncic back before Jun 20: 83%                │
│                                                      │
│  ── Season Stats ─────────────────────────────────  │
│  [Win totals, stat leaders — if season is ongoing]   │
└─────────────────────────────────────────────────────┘
```

**Implementation plan:**

#### ~~Phase 2: Frontend — Sectioned league page~~ ✅ SHIPPED (May 6)
4 new components: SeriesCard (playoff matchups), AwardCard (leader highlight + contenders), PropGroupCard (threshold/ranked outcomes), LeagueMarketSection (routing + grid layout). Wired into league page below championship grid.

#### Phase 3: Cross-sport generalization
Same pattern for NHL (series, Conn Smythe, playoff props), MLB (pennant races, awards, World Series props), NFL (division winners, MVP, draft props). Each sport gets the same sectioned layout, populated by the same league-scoped endpoint.

#### Phase 4: iOS parity
Port the new sections to `LeagueView.swift`. Reuse existing card components where possible.

**Scope for first iteration:** NBA only, single scrollable page (not tabs). Awards + Series + a couple playoff props. ~1 day backend, ~1 day frontend.

**What this does NOT include:**
- Deep-dive pages for individual awards (click MVP → see all 30 candidates). That's the existing `/futures/{id}` page.
- Historical trend charts per market (existing evolution chart covers championship; extending to awards is a separate item).
- Live game scores integration (that's item 0p, do it in parallel).

**Why this matters:** The league page is the most natural destination for a fan checking "what's happening in the NBA right now." Right now it answers only one question (who wins the championship). With this change, it answers a dozen: who's MVP, which series are competitive, will there be sweeps, when is Luka back, etc. It transforms the page from a reference table into a living dashboard.

**Parallel Safety:** Yellow (backend new endpoint is Green; frontend touches existing league page)

### 0q. Feed "Top Markets" Stale Data (BUG — user-facing)

### 0r. Golf Data Quality Issues (April 25)

---

## Tier 1 — High Leverage, Do Next

---

### 0e-3. GA4 Console Configuration — TODO (Phase 4)

Not code — configuration in the GA4 property (analytics.google.com):
1. **Custom definitions**: Register `sport`, `league`, `event_id`, `event_status`, `source_section`, `position_index`, `is_live`, `is_close_game` as custom dimensions
2. **Key events (conversions)**: Mark `sign_up`, `onboarding_complete`, `event_detail_view` as key events
3. **Audiences**: Create "Sports Enthusiasts" (3+ event_detail_view / 7d), "NBA Fans" (sport=basketball_nba 5+), "Power Users" (5+ sessions / 7d)
4. **Funnels** (Explore): Acquisition (first_visit → page_view → event_card_click → event_detail_view), Onboarding (start → steps → complete), Retention (return_visit by days_since_last)
5. **Dashboards**: DAU by platform, top sports by engagement time, feed CTR, onboarding completion rate

**Parallel Safety:** Green (no code changes)

### 0f-2. Futures Detail Page Data Quality — IN PROGRESS (April 25)
Polymarket Cy Young (futures/132810) showed "player AA" garbage names. Root cause: (1) orphan outcomes with NULL external_id from old polling code, (2) Polymarket poll capped at 10K events but 10,542 exist — Cy Young market fell outside pagination. 
**Fixes deployed:** orphan cleanup + pagination increased to 13K + one-off fix script. Awaiting next poll to verify.
**Cross-game contamination FIXED:** ±18h time window on BOTH linked and fallback queries. NBA went from 38 violations → 0.
**Files:** `tasks/polymarket.py`, `routes/events.py`, `scripts/fix_polymarket_cy_young.py`

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

---

### 0f-13. Event Detail April 29 Review — 9 OPEN ISSUES

Reviewed BOS-PHI completed game (event 14617909). Screenshots in `/Users/bain/Desktop/Screenshot 2026-04-29 at 4.20*.png`. Issues affect BOTH web and native unless noted.

#### 0f-13c-native. 2nd Half Margin/Total Maps Not Showing (NATIVE ONLY — remaining)

**Problem:** Only 1st half maps show. 2nd half maps don't appear on either platform. The web fix (checking `market_name` for half grouping) either hasn't deployed or the underlying 2H market data still isn't in our DB.

**Investigation needed:**
1. Check if the Kalshi poll has run since adding 2H tickers to supplementary fetch (April 28)
2. Check if 2H spread/total markets exist in `futures_markets` with `event_id` set for this event
3. If they exist, check if `_classify_game_market()` returns `half_spread`/`half_total` for them
4. If classified correctly, check if the frontend grouping logic picks them up

**Files:** `backend/app/services/kalshi_api.py` (supplementary fetch), `backend/app/routes/events.py` (`_classify_game_market`), `frontend/components/MarketMapSection.tsx` (grouping), `ios/.../Components/MarketMapSection` (if exists)

#### 0f-13h. Player Award Headshots Missing on WEB

**Problem:** Native shows player headshots (from roster data) next to award names in the Season Futures / Awards section. Web shows only colored initials circles.

**Fix:** The web "Bigger Picture" section's award display needs to use the `PlayerHeadshot` component (already exists for player props). Check if the award data from the `team-progression` endpoint includes player image URLs. If not, the backend needs to enrich award outcomes with headshot URLs from roster data.

**Files:** `frontend/app/events/[id]/page.tsx` (Bigger Picture section), `backend/app/routes/events.py` (team-progression endpoint)

---

### Bug Report #1 — Event Detail Page (PHI 109 - BOS 100, May 4)

From rage shake. Three separate issues on a completed NBA playoff game event detail page.

#### BR1-2. Source attribution looks duplicated — NEEDS DESIGN

**Problem:** The source list (sportsbooks contributing to the aggregate) appears to show twice — once as a static list and once inside a collapsible dropdown. The dropdown is valuable because it shows we're aggregating across many sportsbooks, but in practice users see the sources listed twice since they don't click the dropdown. Needs a design fix, not just a code change.

**Design question:** How should source attribution work? Options:
- Show just the count ("Aggregated from 12 sportsbooks") with dropdown for details
- Show the dropdown only, collapsed by default
- Inline chips for the top 3 sources + "+9 more" expander

**Files:** `ios/.../Views/EventDetailView.swift` (`sourcesToggle` ~line 824), `frontend/app/events/[id]/page.tsx`
**Parallel Safety:** Yellow (design brief needed)

#### ~~BR1-3. Kalshi/Polymarket probabilities for NBA playoff game~~ ✅ INVESTIGATED (May 6)

Event 14617909 now has Kalshi (230 markets) and Polymarket (10 markets) linked. Kalshi shows in win_probability_sources. Root cause was the cross-sport/cross-day matching bugs fixed in this session (0f-3d Issues 1/3). Polymarket prob history missing for this past game because markets were linked post-completion — expected for historical games. Future games will have live snapshots.

---

### Manus Sweep May 4 — 7 Issues Found (Health Score: 58/100)

9 modules run, all completed. MLB and NBA live pages are excellent. Grids score 85-92. Source accuracy within 3pp of Kalshi/Polymarket across all spot checks.

#### MS-May4-4. EPL League Page Data Contamination

**Problem:** EPL page shows contaminated data from non-EPL sources. Need to investigate what's leaking in.
**Files:** Backend league page endpoint, sport key classification
**Parallel Safety:** Yellow

#### MS-May4-6. NBA 1H Total — 7 Thresholds vs Kalshi's 9 (23% gap at Over 98.5)

**Problem:** Missing 2 threshold values from Kalshi. Could be outcome ingestion issue or dedup filtering too aggressively.
**Files:** Backend outcome ingestion, `backend/app/routes/events.py` (game-markets threshold logic)
**Parallel Safety:** Yellow

---

### Manus Site Sweep Findings (April 25) — NEW

Full report: `Manus/audit_results/site_sweep_april25.md`

#### ~~MS-8. Kalshi 1.0% minimum tick~~ ✅ SHIPPED (May 6)

Backend adds `is_minimum_tick` flag on grid cells at exactly 0.01 from Kalshi-only source. Frontend `fmt()` shows "<1" for any probability ≤ 0.01.

### 0f-9. Mac App — SHIPPED + Polish (April 24-25)

**SHIPPED:** Native macOS target compiles and runs. SwiftUI multiplatform — same codebase as iOS with `#if os` conditionals. 30 files modified. Sidebar nav, adaptive grid, keyboard shortcuts (Cmd+1-4), light mode, Mac icon.

**Remaining macOS polish items:**

| # | Feature | Effort | Status |
|---|---------|--------|--------|
| MAC-1 | **Live-updating title bar** | 1-2h | Open |
| ~~MAC-2~~ | ~~Multi-window support~~ | — | ✅ Already done (context menu + WindowGroup) |
| MAC-3 | **Keyboard navigation** | 2-3h | Skipped (>1.5h, complex focus management) |
| ~~MAC-4~~ | ~~Toolbar refresh button~~ | — | ✅ SHIPPED May 6 |
| MAC-5 | **Menu bar extra (scores)** | 3-4h | Open |
| MAC-6 | **Push notifications** | 2-3h | Open |
| ~~MAC-7~~ | ~~Hover states~~ | — | ✅ SHIPPED May 6 |
| MAC-8 | **Right-click context menus** | 1h | Open |
| MAC-9 | **Share button + universal links** | 2-3h | Open |
| MAC-12 | **macOS widgets** | 3-4h | Open |

**Files:** `ios/Bain Luck/Bain Luck/` (various Views, Bain_LuckApp.swift)
**Parallel Safety:** Green (iOS-only changes)

---

### 0f-3. Live Box Score Integration for Player Props
Player prop cards should show actual stats from `box_score_data` during live games (e.g., "Jayson Tatum: 18 points so far vs 24.5 O/U"). The `boxScore` prop is wired but the matching logic needs work — player names from Kalshi props don't always match ESPN box score names.
**Files:** `frontend/components/PlayerPropsDashboard.tsx` (matching), `backend/app/routes/events.py` (box score in response)

### 0f-4. Sport Hierarchy Page Data Quality (Manus audit April 22)

Two issues reported by Manus league page audit. May be transient data issues — verify before investing time:
1. **EPL page shows Egyptian Premier League teams** — cross-league contamination in grid or event data. Grid API currently shows correct 20 English teams. May have been stale data at audit time.
2. **Tennis category page shows Golf content** — `/categories/tennis` or `/sport/tennis/atp` displaying golf tournaments. Tennis feed API returns correct data. May be a rendering path issue where golf-specific code runs for non-golf sports.

**Verify:** Visit `/sport/soccer/epl` and `/sport/tennis/atp` in browser. If issues persist, trace the data loading path.
**Files:** `frontend/app/sport/[sport]/[league]/page.tsx`, `frontend/app/categories/[slug]/page.tsx`

---

### 0f-3d. Event Detail Market Completeness — 5 ISSUES (April 22 audit)

**Context:** Audited event 14523747 (Red Sox vs Yankees). Issues 1, 2, 3, 5 all resolved. Only Issue 4 remains.

#### Issue 4: Series markets not surfaced on event detail pages
Kalshi has rich series-level markets (Series Winner, Series Exact Score, Series Game Spread, Series Total Games) that should show on every game's event detail page during a playoff series. Example: Bruins vs Sabres NHL playoff game (April 28) — Kalshi has "BUF wins 4-1 62%", series spread -2.5, series total games — none of this appears on bainluck.com for any game in that series.

**Two sub-problems:**
1. **Linking:** Series markets (e.g., `KXMLBSERIES-26APR21NYYBOS`) may not be linked to individual game events via `event_id`. The ticker team extraction had a parsing bug ("Yankees" → "Celtics" via city-to-team mapping defaulting to wrong sport). Also, Kalshi series tickers (`KXNHLSERIES`, `KXNBASERIES`) need to be in `KALSHI_TICKER_TO_SPORT_KEY`.
2. **Display:** Even if linked, series markets need a dedicated "Series" section on the event detail page — separate from player props and game-level markets. Should show series winner probability, exact score outcomes, and series spread/total as grouped cards.

**Fix:** 
- Debug ticker team extraction for series prefixes (`KXMLBSERIES`, `KXNHLSERIES`, `KXNBASERIES`)
- Add series market detection to `is_game_prop()` or create `is_series_prop()`
- Link series markets to ALL games in the series (not just one game)
- Add "Series Context" section to event detail page between Bigger Picture and Related Futures
**Files:** `utils/prediction_market_matching.py` (ticker extraction), `tasks/prediction_market_matching.py` (linking), `frontend/app/events/[id]/page.tsx` (display)

---

### 0f. Event Detail Below-the-Fold Redesign

Steps 1-5 shipped April 22. Remaining:
6. **TradeWatch rethink** — one-sided, highest-prob destination only (partially done — disclaimer added, layout fix needed)
**Parallel Safety:** Yellow (frontend only)

---

### 0t. Chart Timing Quality — 3 Issues (April 22, 2026)

Discovered via `scripts/audit_event_timing.py` — 45 completed events audited across 17 sport/league combos.
Full audit baseline: `scripts/audit_results/timing_latest.json`. Manus visual prompt: `Manus/prompts/chart_timing_audit.md`.

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

---

### 1. Improve Game Prop Link Rate (1C continuation)

**Goal:** Push basketball, baseball, hockey to >85% open link rate.

**What's already shipped (April 19-20):**
- Ticker-derived team names, ILIKE pattern expansion, city abbreviation map (65 entries)
- `sport_id` propagation, `llm_sport_category` correction from ticker
- Matching frequency 4h → 1h, limit 200 → 500
- Link rate dashboard + API endpoint
- 324 prediction market matching tests

**Current open rates (April 25):** Basketball 58.9% K / 93.8% PM | Hockey 59% K / 23.8% PM | Baseball 75.1% K / 73.4% PM

**Remaining sub-items (in priority order):**

#### ~~1a. Time Window Expansion (48h → 7d for Kalshi)~~ ✅ ALREADY SHIPPED
Commit `eb32ace`. Kalshi uses 7-day window in broad fallback, 48h when ticker game date is available.

#### 1b-monitor. Hockey Kalshi Link Rate — MONITOR (April 28)
**Context:** Health check (April 27) found Hockey Kalshi at 59%, Polymarket at 23.8% — both well below 80% target. The ticker-based fallback (1b) shipped April 27; check if it moved the needle. Also investigate whether 1d (non-NHL leagues in denominator) is inflating the gap.
**Action:** Re-check `/api/admin/prediction-markets/link-rate` hockey rates. If 1b didn't help, prioritize 1c (sport key validation) and 1d (denominator filtering) next.

#### 1c. Sport Key Extraction Validation
**Root cause:** When sport key extraction fails from a Kalshi market, the code falls back to generic time-based matching with NO sport filtering. This can cause cross-sport mismatches (basketball market matching a hockey event).
**Fix:** Always extract sport key from ticker in Pass 1. Add sport filtering to the generic fallback in `_find_event_by_sport_and_time()`. Add stats counter `sport_key_extraction_failed`.
**Expected impact:** +3-5% link rate, eliminates cross-sport mismatches.
**Files:** `tasks/prediction_market_matching.py:235-349` (Pass 1), `tasks/prediction_market_matching.py:1007` (_find_event_by_sport_and_time)
**Effort:** 1-2 hours
**Parallel Safety:** Yellow

#### 1d. Non-NHL Hockey Markets (KHL/AHL/DEL)
**Root cause:** Kalshi has markets for KHL, AHL, DEL leagues. Our event DB only covers NHL. These markets fail silently — they're counted in the denominator but can never link.
**Fix:** Either (a) filter them from the link rate denominator, or (b) add these leagues to event ingestion. Short-term: add explicit tracking counter `non_nhl_hockey_market_skipped`.
**Expected impact:** Adjusts denominator, hockey rate would jump 5-10% if filtered.
**Files:** `utils/sport_keys.py` (KALSHI_TICKER_TO_SPORT_KEY), `tasks/prediction_market_matching.py`
**Effort:** 1 hour to filter, 1-2 days to ingest
**Parallel Safety:** Green

#### ~~1e. MMA~~ ✅ TARGET MET (86.3% Kalshi)

#### 1f. Kalshi team aliases for championship grids (R3)
**Fix:** Admin endpoint to extract all 30 Kalshi outcome names per sport, add as `Team.alternate_names`.

---

## Active Sentry Issues (April 28, 2026)

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

### SEARCH. Search Overhaul — IN PROGRESS (May 1, 2026)

**Problem:** Search is broken and embarrassing. Typeahead shows raw HTML entities (`&#x1f4c8;`), futures results are duplicated/truncated, ranking is noisy, non-sports markets (weather, economics, politics) are completely unsearchable, and there's no fuzzy matching or typo tolerance.

**Screenshot:** Searching "celtics" returns Boston Celtics (good), 1 game (good), then 3 near-identical "Celtics vs 76ers" futures with raw HTML entity codes and truncated names. The futures results are indistinguishable and take up all the dropdown space.

**Current architecture:** 3 backend endpoints in `routes/events.py` (typeahead, full search, suggestions). Frontend in `components/SearchBar.tsx` + `app/search/page.tsx`. All matching is `ILIKE '%query%'` — no trigram, no full-text search, no fuzzy matching. No indexes on searched columns.

**Files:** `backend/app/routes/events.py` (lines 577-1219), `frontend/components/SearchBar.tsx`, `frontend/app/search/page.tsx`, `frontend/lib/api.ts`

#### TEAM PAGES ✅ SHIPPED (May 1)

Canonical team pages at `/sport/[sport]/[league]/team/[slug]` (e.g., `/sport/basketball/nba/team/boston-celtics`). Follows the existing `/sport/[sport]/[league]` URL hierarchy — truncating to `/sport/basketball/nba` still lands on the league page.

**Backend**: `GET /api/teams/{identifier}` returns team info + upcoming/recent games + futures + championship path. Slug column on Team model with backfill migration. team_id/slug/sport_key in typeahead and _format_team_data.

**Frontend**: Hero (logo, colors, record, standings), championship path cards (Championship/Conference/Division %), game cards (upcoming + recent with W/L scores), season futures list. Breadcrumbs: Home / NBA / Celtics. SEO metadata with league name.

**Search integration**: Typeahead team results link to `/sport/.../team/slug`. `buildTeamUrl()` constructs the full hierarchical path from `sport_key`. Typeahead enriched (May 2): event suggestions include `sport_key`, `home_logo`, `away_logo`; futures include `sport_key`; all types have consistent field naming for iOS parity.

**~~Phase B~~ ✅ SHIPPED (May 2)**: TeamNameLink component cross-links team names in EventCard, FeedCard, event detail hero, ChampionshipGrid, TournamentProgressionTable, and team page GameCard. Shared `teamUrls.ts` utility with `slugify()` + `buildTeamPageUrl()`. SearchBar refactored to use shared utility. JSON-LD SportsTeam structured data + dynamic document titles on team pages.

**Files**: `routes/teams.py`, `utils/slugify.py`, `app/sport/[sport]/[league]/team/[team]/page.tsx`, `components/TeamNameLink.tsx`, `lib/teamUrls.ts`, migration `f1a2b3c4d5e6`.

---

#### ~~Phase 4: Fuzzy & Full-Text Search~~ PARTIALLY SHIPPED (May 2)

- [x] **P4a. `pg_trgm` extension** — Enabled via Alembic migration `a7b8c9d0e1f2`.
- [x] **P4b. GIN trigram indexes** — On `teams.name`, `events.home_team_name`, `events.away_team_name`, `futures_markets.name`.
- [ ] **P4c. Weighted `ts_vector` full-text search** — Team names weight A, market names weight B, outcome names weight C.
- [x] **P4d. Did-you-mean suggestions** — Typeahead + full search fall back to trigram similarity (threshold 0.25) when ILIKE finds no results. Frontend shows "Showing results for X" banner.

#### ~~Phase 5: Search UX Polish~~ PARTIALLY SHIPPED (May 2)

- [x] **P5a. Recent searches** — Last 5 in localStorage, shown on focus before typing with clock icons.
- [ ] **P5b. Trending/popular searches** — Track queries server-side, surface top 5 as zero-state chips.
- [x] **P5c. Search results page redesign** — Three sections: Teams (compact cards with logo/record/league), Games (EventCard grid), Futures & Markets (FuturesCard grid). Backend returns matched teams. Summary line with per-entity counts.
- [x] **P5d. Mobile search** — Full-screen overlay with auto-focus, recent searches, typeahead, Cancel button.
- [x] **P5e. Keyboard shortcut** — `Cmd+K` / `Ctrl+K` focuses desktop search bar. Keyboard hint badge shown.

#### Phase N: Native Search Parity (iOS/macOS)

iOS search (`SearchView.swift`) has typeahead, sport filters, recent searches, quick chips — but is missing:

- [x] **~~SN-1. Team results section** — Web shows teams with logos, records, sport labels. iOS has no team results at all. **P0**
- [x] **~~SN-2. Team page navigation** — Web links to `/sport/.../team/slug`. iOS has no team pages. Requires new `TeamDetailView.swift`. **P0**
- [x] **~~SN-3. Enriched typeahead model** — iOS `TypeaheadSuggestion` model is missing `team_id`, `team_slug`, `sport_key`, `status`, `commence_time`, `logo_url`, `market_type_label`. Update model + render logos, live indicators, type differentiation in suggestions. **P1**
- [x] **~~SN-4. "Did you mean" fuzzy correction** — Web shows correction banner when trigram fallback is used. iOS doesn't display `did_you_mean` from API response. **P1**
- [x] **~~SN-5. Cmd+K shortcut on macOS~~ ✅ SHIPPED May 6** — Added to Navigate menu.

**Files:** `ios/.../SearchView.swift`, `ios/.../Models/SearchModels.swift`, new `ios/.../Views/TeamDetailView.swift`

---

#### Phase 6: Semantic Search (2-3 weeks, aspirational)

- [ ] **P6a. Embedding-based search** — OpenAI embeddings (already have API key) for queries like "Will the Celtics repeat?" matching championship markets.
- [ ] **P6b. pgvector extension** — Store embeddings in Postgres, nearest-neighbor search.
- [ ] **P6c. Query intent classification** — Is the user looking for a team, game, market category, or asking a question? Route to different strategies.
- [ ] **P6d. Personalized ranking** — Boost results from leagues/teams the user has viewed or predicted on (have `user_predictions` data).

**Priority order:** Phases 1-2 are "stop embarrassing ourselves" (2-3 days). Phase 3 makes it useful. Phase 4 makes it forgiving. Phases 5-6 make it delightful.

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

Dedicated pass to make everything faster, more reliable, and higher quality.

**Status: ALL 12 items SHIPPED.**

| # | Item | Status |
|---|------|--------|
| ~~PREQ-1~~ | ~~Request timing middleware~~ | ✅ Shipped Apr 24 |
| ~~PREQ-2~~ | ~~API client timeout (15s AbortController)~~ | ✅ Shipped Apr 25 |
| ~~PREQ-3~~ | ~~Cache-Control headers~~ | ✅ Shipped Apr 25 |
| ~~PREQ-4~~ | ~~Connection pool 10→20~~ | ✅ Shipped Apr 25 |
| ~~PREQ-5~~ | ~~SWR interval tuning (My Stuff 15s→60s, grouped 60s→120s)~~ | ✅ Shipped Apr 25 |
| ~~PREQ-6~~ | ~~Redis feed caching (15s TTL, anon only)~~ | ✅ Shipped Apr 25 |
| ~~PREQ-7~~ | ~~N+1 query audit~~ | ✅ Shipped Apr 28 |
| ~~PREQ-8~~ | ~~Dynamic imports~~ | ✅ Already done |
| ~~PREQ-9~~ | ~~Image optimization~~ | ✅ Already optimized |
| ~~PREQ-10~~ | ~~Health endpoint (Redis + poll timestamps)~~ | ✅ Shipped Apr 25 |
| ~~PREQ-11~~ | ~~Source degradation (try/except in feed)~~ | ✅ Shipped Apr 25 |
| ~~PREQ-12~~ | ~~Sentry noise cleanup (before_send filter)~~ | ✅ Shipped Apr 25 |

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

#### ~~18a. Economics Page~~ ✅ SHIPPED
Live at `/economics` with 1,641 markets across 9 sub-themes. Backend: `routes/economics.py`. Frontend: `app/economics/page.tsx`. Fed heatmap, CPI releases, GDP quarters, typed API client.

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

### 20. Market Interestingness Scoring (powers Item 19)

**Goal:** Build an algorithmic interestingness scorer calibrated against Kalshi/Polymarket marketing emails as ground truth. Those emails are hand-curated by their marketing teams — a free labeled dataset of "what humans find interesting."

**Why feature-based, not ML:** Small dataset (~5-15 markets per email, a few emails/week), interpretable weights, debuggable, Alex can tune intuitively, no training infrastructure.

**Phase 1 — Ground Truth Collection:**
- Start: copy/paste email text into Claude session, extract market names
- Graduate to: Google Apps Script + Google Sheet (Gmail filter → daily auto-extract → structured sheet)
- Sheet columns: `[date, source, market_name, market_url, extracted_question]`
- Goal: 50-100 labeled "interesting" markets before calibration

**Phase 2 — Scoring Formula:**
```python
interestingness = (
    w1 * decisiveness(prob)          # prefer 15-85% range, not 50% or 99%
    + w2 * has_multi_source           # both Kalshi AND Polymarket
    + w3 * recency(created_at)        # new markets are more newsworthy
    + w4 * movement(price_change_24h) # movement = something happened
    + w5 * resolution_proximity(date) # 7-90 days out is the sweet spot
    + w6 * category_novelty(category) # "Swift meets Pope" >> "GDP Q2"
    + w7 * volume(open_interest)      # liquidity = people care
    + w8 * llm_question_quality(name) # GPT-4o-mini: "would a casual person find this interesting?"
)
```

**Phase 3 — Calibration (hill-climb):**
1. Score ALL markets in DB
2. Check: what percentile do email markets land at? Goal: top 5%
3. Identify failure modes (email markets that score low = missing feature; non-email markets that score high = false positive)
4. Adjust weights, re-score, repeat
5. **Metrics:** Precision@20, Recall@50, NDCG

**Phase 4 — Product Integration:**
- `/explore` page sort (Item 19)
- Feed futures card ranking
- "Trending" section (biggest interestingness increase in 24h)
- Push notifications (macOS/iOS) for high-scoring new markets
- Featured market hero on `/explore`

**Files:** `utils/market_interestingness.py` (new), `scripts/calibrate_interestingness.py` (new), ground truth in Google Sheet
**Parallel Safety:** Green (new utility, no existing code modified)

---

## iOS App — Web Parity & Polish (April 22, 2026)

Major iOS overhaul April 22 evening (~30 commits). Core event detail now has: hero with team logos/scores, multi-source win prob chart with period markers, score diff chart with period markers, ChampionshipPathView (from team-progression), PlayerPropsCardView (from game-markets), awards, season stats, trade watch, clean error messages.

### ~~iOS-12. Score Diff Actual Line Cuts Off Mid-Game~~ ✅ SHIPPED (May 6)

**Problem:** The teal "Actual Score Diff" line stops partway through the game (e.g., 5th inning).

**Root cause found (April 22):** ALL 7 ESPN history points have `homeScore=None, awayScore=None`. The ESPN sync writes period/clock data to ESPNSnapshot but scores are null. The score diff chart only gets 3 ScoreSnapshot data points from the Odds API (5-minute polling). This is a BACKEND issue — the ESPN API response parsing may not be extracting scores, or ESPN isn't providing them for this event type.

**Fix:** Debug the ESPN sync score extraction: `ee.home_score` is None when writing ESPNSnapshot. Check what the ESPN API returns and how it's parsed. The `_sync_espn_live_events` function at line 493 sets `event.home_score = ee.home_score` — this path works for Event updates but the snapshot write at line 541 may be running before scores are available.
**Files:** `backend/app/tasks/espn_sync.py` (ESPN API response parsing), `backend/app/services/espn_api.py`

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

### iOS Game Detail Triage (April 26)

Findings from iOS event detail page review (BOS @ BAL, Apr 25, final 17–1).

#### ~~iOS-GD3. Win prob chart clipped at game end~~ ✅ SHIPPED (May 6)
**Problem:** For BOS @ BAL (final 17–1), the aggregate win probability drifts toward ~50% after the game ends, even though real sources resolved to ~100%. Likely a wrong Kalshi/Polymarket market linked to the event, and/or upstream market resolution status isn't propagating.
**Approach:** Investigate via: `SELECT id, source, source_market_id, name, status, last_price FROM prediction_markets WHERE event_id = <id>`. Fix root cause in match logic (`app/utils/prediction_market_matching.py`) and/or status propagation (`app/tasks/prediction_market_matching.py`, `poll_live_prediction_markets`). Add audit: for every completed event, every linked market should be resolved upstream and our latest snapshot should match the realized outcome within tolerance. New check in `scripts/audit_matching_quality.py` or `audit_post_final_consistency.py`.
**Files:** `backend/app/utils/prediction_market_matching.py`, `backend/app/tasks/prediction_market_matching.py`, `backend/app/tasks/live_prediction_markets.py`
**Parallel Safety:** Yellow (backend matching logic)

#### iOS-GD12. Trevor Story missing headshot
**Problem:** Trevor Story's award row shows an initials chip instead of a headshot.
**Approach:** Verify whether the headshot URL is missing in the API payload or just not loading on iOS. Add a generic player silhouette as fallback so rows look uniform even when headshots are unavailable.
**Files:** `ios/.../Components/RelatedFuturesView.swift`, backend roster data
**Parallel Safety:** Green

#### iOS-GD — NOT YET APPROVED (ask before adding)
- Score Differential chart inning labels cramped; "Projected Spread" occluded by "Actual Score Diff."
- Player Props 2-col grid leaves orphan card on odd counts
- Game Info footer duplicates broadcaster + time already in hero
- Bookmark icon floats outside standard nav cluster

---

## Tier 2.5 — Discover Feed Enhancement (April 29)

### DN. Native Discover Parity (iOS/macOS) — May 2, 2026 audit

iOS Discover (`DiscoverView.swift`) has category chips, event/futures cards, guess cards with Higher/Lower — but has critical gaps:

**P0 — Correctness bugs:**
- [x] **~~DN-1. Prediction POST broken** — `NativeGuessCard` uses raw `URLSession` with no `x-session-id` header and no user auth token. iOS predictions are NOT being tracked at all. **CRITICAL BUG.** Fix: use the app's existing `APIClient` with auth headers.
- [x] **~~DN-2. Prediction stats page** — Web has `/discover/stats` with accuracy, streaks, badges, trend chart, by-category breakdown. iOS has nothing. New `PredictionStatsView.swift` needed.
- [x] **~~DN-3. Prediction streaks** — Web shows current streak + best streak after each guess. iOS `NativeGuessCard` doesn't fetch or display stats after submission.
- [x] **~~DN-4. "Next question" navigation** — Web auto-scrolls to next guess card after answering. iOS stays on the answered card with no forward momentum.
- [x] **~~DN-5. Daily Challenge** — Web has 5/day goal with progress ring on a dedicated challenge card. iOS has no daily challenge concept.

**P1 — Engagement gaps:**
- [x] **~~DN-6. Events as guessable** — Web (as of May 2) makes events guessable ("Lakers to win — higher or lower than X%?"). iOS only makes futures guessable.
- [x] **~~DN-7. Guess density** — Web now shows guess slot every 5th card (was every 2nd, changed May 5 to reduce feed noise). iOS also every 5th. Aligned.
- [x] **~~DN-8. Dismiss persistence** — Same as D-10a. iOS uses `@State` — dismissed items reset on tab switch.

**P2 — Nice to have:**
- [ ] **DN-9. Swipe to dismiss** — Web has swipe left/right with like/dismiss overlays.
- [ ] **DN-10. Onboarding flow** — "Build Your Feed" modal with category selection.
- [ ] **DN-11. Grouped market cards** — Markets grouped by name prefix (e.g., "Valero Texas Open: ...").

**Files:** `ios/.../Views/DiscoverView.swift` (careful — active native thread may be touching this), new `ios/.../Views/PredictionStatsView.swift`, `ios/.../Models/DiscoverModels.swift`

---

### D-11. Hook Description Coverage — ACTIVE (May 5)
Only **6% of feed markets** have LLM-generated context snippets (`hook_description`). Enrichment task now prioritizes missing hooks over stale regenerations, runs 12x daily at 200/batch (was 8x at 100). Goal: >80% of feed-visible markets have hooks within 48h. Monitor via: `curl api.bainluck.com/api/feed?limit=200 | python3 -c "..."` (count hook_description non-null).
**Files:** `backend/app/tasks/enrich_markets.py`, `backend/app/tasks/__init__.py`

### D-4a. Full Click/View Tracking (REMAINING)
`user_interactions` table logging event/futures detail views. Backend middleware for zero-frontend-work implicit tracking. View-weighted sport affinities.
**Files:** New migration, `backend/app/main.py`, `backend/app/utils/personalization.py`

### D-10a. Dismiss Persistence (Discover)
Dismiss actions on Discover cards are currently `@State`/`useState` — they reset on tab switch or page reload. Persist dismissed IDs server-side (extend `user_seen_markets` with a `dismissed` boolean, or separate `user_dismissed_markets` table). Both web and native should check dismissed state on load.
**Files:** `backend/app/routes/predictions.py`, `frontend/app/discover/page.tsx`, `ios/.../Views/DiscoverView.swift`

### D-10b. Like/Dismiss → Feed Ranking
Feed thumbs up/down and Discover dismiss signals should feed back into futures scoring. New `user_market_feedback` table with `(user_id, market_id, signal, category)`. `_score_futures()` in `feed.py` applies a personalization multiplier based on category-level feedback (liked categories boosted, dismissed categories suppressed). Same pattern as the existing `compute_futures_multiplier()` for sport affinities.
**Files:** New migration, `backend/app/routes/feed.py` (`_score_futures`), `backend/app/utils/personalization.py`

---

### D-6. Push Notifications for Market Moves

Alert users when markets they've pinned or categories they follow have significant movement (>10% in 1h). Firebase Cloud Messaging (already have Firebase Auth). New `notification_preferences` table. Celery task checks for moves and fires FCM push.

### D-7. Live Game Companion Mode

Compact full-screen mode for second-screen game watching. Giant win probability number, real-time play-by-play, probability sparkline, key moment alerts. Auto-refresh every 10s. Keep-alive screen on mobile. Reuses existing OddsChartView data + ESPN polling.

### D-8. Daily Digest Email

Morning email: yesterday's biggest movers, today's top markets, resolved predictions. Celery task at 7am user-local-time. Jinja2 HTML template. SendGrid delivery. Uses existing feed scoring to pick content.

### D-9. Friend Predictions & Challenges

"Challenge a friend: Who wins the NBA Finals?" Both pick, odds are locked, winner gets bragging rights. Shareable URL, no account required for friend. `prediction_challenges` table. Emoji reactions on resolution.

---

### Open Event Detail Parity Items (from April 29 Sweep #3)

Items 2, 4, 5, 6, 8 from the approved plan remain:

- **Web x-axis alignment**: Win Prob and Score Diff charts need identical tick positions. Generate explicit ticks from shared domain with dynamic intervals (hourly for long games, 30-min for short).
- **1st half margin mismatch**: Web shows BOS +6.5, native shows BOS +1.0. Use spread threshold directly from period market with probability closest to 50%.
- **Half map FINAL values**: Derive half scores from ESPN history halftime data point.
- **2nd half maps missing**: Check if API returns 2H period markets; render if present.
- **Double/triple doubles → player props**: Sport-generic: scan `other` markets for player-named outcomes, inject into player prop cards.

---

## Tier 4 — Someday / Maybe

### 21. Rage Shake — In-App Bug Reporting (iOS + Web)

**Goal:** Let anyone using Bain Luck shake their phone (or trigger a gesture on web) to instantly report a bug with full context — screenshot, current page, device info, app state — without leaving the app.

**Why:** Alex and friends are the primary testers. Right now, reporting a bug means texting/screenshotting/describing manually. Rage shake makes it one gesture → structured report → lands in a queue for the next coding session.

**iOS Implementation:**
- SwiftUI has no built-in shake gesture, but UIKit's `motionEnded(.motionShake, ...)` works via a thin UIWindow subclass or `UIViewControllerRepresentable` wrapper.
- On shake: capture screenshot (`UIGraphicsImageRenderer` from the current window), collect context (current route/view, `EventDetailViewModel` state, API errors in last 60s, app version, device model, iOS version).
- Present a modal: screenshot preview + text field ("What went wrong?") + severity picker (broken / ugly / idea) + submit button.
- **Where reports go:** Options ranked by simplicity:
  1. **GitHub Issues** — `POST /repos/alexander-bain/bainluck/issues` via GitHub API. Auto-labeled `bug/rageshake`. Screenshot uploaded as issue attachment. Zero new infrastructure.
  2. **Google Sheet** — append row via Google Sheets API. Lower friction but less structured.
  3. **Backend endpoint** — `POST /api/feedback` stores in DB. Most work, most control.
- Recommendation: Start with GitHub Issues. It's where the backlog lives, screenshots render inline, and it's free.

**macOS Implementation:**
- No shake gesture on Mac. Use keyboard shortcut: `Cmd+Shift+F` ("Feedback") or a menu bar item.
- Same modal, same data capture.

**Web Implementation:**
- **Device shake API** (`DeviceMotionEvent`) works on mobile browsers but requires HTTPS + user permission. Unreliable.
- Better: **floating feedback button** (small `?` or flag icon, bottom-right corner). Click → same modal as iOS.
- Alternative: **keyboard shortcut** (`Ctrl+Shift+F` / `Cmd+Shift+F`) for desktop web.
- Screenshot capture: `html2canvas` library or `dom-to-image` for client-side screenshot. Or just capture the current URL + viewport dimensions and let the developer reproduce.
- Same destination (GitHub Issues or backend endpoint).

**Data captured per report:**
```
{
  "screenshot": "<base64 or URL>",
  "page": "/sport/basketball/nba",
  "event_id": 14595395,           // if on event detail
  "description": "user typed text",
  "severity": "broken|ugly|idea",
  "platform": "ios|macos|web",
  "app_version": "1.2.3",
  "device": "iPhone 15 Pro / Chrome 120 / macOS 15.1",
  "timestamp": "2026-04-28T10:30:00Z",
  "recent_errors": ["API timeout on /api/feed", ...]
}
```

**Files:** New `ios/.../Utils/RageShake.swift`, new `frontend/components/FeedbackButton.tsx`, optionally new `backend/app/routes/feedback.py`
**Parallel Safety:** Green (all new files)
**Effort:** iOS: 2-3h. Web: 2-3h. Backend (if not GitHub): 1h.

### 22. Interestingness-Powered Discovery Feed (LLM Blurbs + Images)

**Goal:** Use the interestingness scorer (Item 20) across the ENTIRE `futures_markets` table — not just the `/explore` page — and generate an engaging, social-media-style feed where each card has: a compelling image, a one-line LLM-written blurb, and the probability bar. Think "Instagram for prediction markets."

**Why:** The current feed is sports-game-centric. Futures markets like "Foldable iPhone in 2026 — 12%" or "3+ NBA Series Sweeps — 32%" are inherently interesting but we present them as sterile data tables. An image + blurb transforms them into content people actually want to scroll through and share.

**What a card looks like:**

```
┌─────────────────────────────────────────┐
│  [Image: iPhone folding concept art]    │
│                                         │
│  Will Apple release a foldable iPhone   │
│  before 2027?                           │
│                                         │
│  "Samsung's had 5 generations of folds  │
│   while Apple watches from the          │
│   sidelines. The market says they're    │
│   still not ready."                     │
│                                         │
│  12% ████░░░░░░░░░░░░░░  Kalshi        │
│  14% ████░░░░░░░░░░░░░░  Polymarket    │
│                                         │
│  Resolves: Dec 31, 2026                 │
└─────────────────────────────────────────┘
```

**Implementation plan:**

#### Phase 1: Score everything
Run `compute_interestingness()` (Item 20) across all open `futures_markets` rows. Store the score as a column (`interestingness_score FLOAT`) on the model. Re-score hourly via Celery task. This gives us a ranked list of the ~500 most interesting markets across all categories.

#### Phase 2: LLM blurb generation
For the top N markets (start with top 100), generate a 1-2 sentence blurb via GPT-4o-mini:

```
Prompt: "Write a 1-2 sentence hook for this prediction market.
Be conversational, slightly opinionated, give context a casual
reader needs. No gambling language. No hedging.
Market: {name}, Current probability: {prob}%, Source: {source}"
```

Store as `llm_blurb TEXT` on the model. Regenerate weekly or on significant probability movement (>10pp). Cost: ~100 markets × $0.01 = $1/week.

#### Phase 3: Image generation/selection
Three tiers of image sourcing (cheapest to richest):
1. **Stock/icon mapping** — Map `llm_sport_category` to a curated set of Unsplash/Pexels images. "Tech" → circuit board, "Politics" → Capitol dome, "Weather" → storm clouds. Free, instant.
2. **Entity image lookup** — For markets mentioning known entities (teams, players, companies), pull logos/headshots we already have (ESPN CDN for sports, company logos via Clearbit). Free, already in DB for sports.
3. **AI-generated** — For truly novel markets ("Taylor Swift meets Pope"), generate via DALL-E or Midjourney. $0.04/image. Only for top 20 featured markets.

Start with tier 1+2 only. Tier 3 is a stretch goal.

#### Phase 4: Feed integration
New feed mode: "Discover" tab alongside the existing sports feed. Or interleave discovery cards into the main feed (every 5th card is a non-sport market from the interestingness ranking).

**Relationship to existing items:**
- **Item 19** ("What Are The Odds?" page) — This feed IS the content engine behind that page. Item 19 is the container; this item is the content.
- **Item 20** (Interestingness Scoring) — This item depends on Item 20 for the ranking. Build 20 first.
- **Item 0s** (League page markets) — Sports markets use the same interestingness score for ordering within league page sections.

**Files:** `backend/app/utils/market_interestingness.py` (from Item 20), new `backend/app/tasks/blurb_generation.py`, new migration for `interestingness_score` + `llm_blurb` columns, `frontend/components/DiscoveryCard.tsx` (new)
**Parallel Safety:** Green (new files, new columns, no conflicts)
**Effort:** Phase 1: 2h (scoring + column + task). Phase 2: 3h (LLM integration + caching). Phase 3: 2h (image mapping). Phase 4: 4h (feed UI).

- Entity pages (`/[sport]/[league]/[team]`) — SEO upside, depends on B1
- Win totals column in championship grid
- ~~Awards/props cards on league pages~~ → Promoted to Tier 1 as item 0s
- TV Mode v2 — Design complete, prototype exists
- "The Market Was Wrong" v2 — AI narrative generation
- Related Futures Phase 5 — Bidirectional
- Frontend tests — Jest config exists, zero test files
- iOS tests — ViewModels with deterministic state logic
- iOS/Mac beyond parity — App Store, widgets, push, share extension

### Platform Parity Checklist (April 25, 2026)

**Core features at parity:** Feed, Event Detail, Search, My Stuff, Championship Grids, Futures Detail, Golf, Preferences, Onboarding

**Event detail sub-features at parity:** Win Prob Chart, Score Diff Chart, Player Props, Divergence Badge, Championship Path, Related Futures, Game Play Card, Auto-refresh, Pin/Bookmark

**iOS/Mac gaps (web has, native doesn't):**

| Priority | Feature | Web Component | Effort |
|----------|---------|--------------|--------|
| Medium | Game Segments (quarter/half breakdown) | `GameSegments.tsx` | Small |
| Medium | Total Points Spectrum (spread+total viz) | `TotalPointsSpectrum.tsx` | Medium |
| Medium | Series Probability (playoff series outcomes) | `SeriesProbability.tsx` | Small |
| Low | Evolution Chart (championship race over time) | `EvolutionChart.tsx` | Medium |
| Low | Line Movement Explainer | `LineMovementExplainer.tsx` | Small |
| Low | Weather page | 16 components | Large |
| Low | Economics page | `/economics` | Medium |
| Low | Explore / faceted browser | `/explore` | Medium |
| N/A | Admin pages (4) | Intentionally web-only | — |
| N/A | Seasonal (Oscars, March Madness) | Web-only | — |

**Web gap (iOS has, web doesn't):** EI Rankings standalone page (iOS has `EIRankingsView.swift` with sport filters)
- Apple Watch / Apple TV apps
- Weather visualization — prediction market weather maps

### 23. Prediction Market Game / Social Picks

**The idea:** Turn the probability content into something people play, not just read. The sheer variety of markets — "OPEC Crude Oil production above __ in May?", "Ferrari Shipments above __ in Q1?", "Airbnb Nights and Seats Booked above ___?", "What Trump-named things will Trump mention in May?", "Which European finishes highest?", "Number of Series Sweeps", "Luka Doncic back before May 7?" — is inherently compelling as a prediction game.

**Possible formats (not mutually exclusive):**

| Format | Description | Vibe |
|--------|------------|------|
| **Feed-as-game** | The main feed IS the game — each card has a "Higher/Lower" button. Track prediction accuracy over time. Leaderboard. | Lowest friction, existing UI |
| **Daily picks** | "5 markets to call today" — curated by interestingness score. Binary over/under on each. Results resolve automatically. | Wordle-style daily ritual |
| **Head-to-head** | Challenge a friend: both pick 5 markets, see who's more calibrated. Share link. | Social + competitive |
| **Ambient screensaver** | Slowly cycling probability cards on Apple TV / Mac screensaver / web idle. "Did you know OPEC production is 83% likely to exceed 28M barrels in May?" Random fascinating facts from our market data. | Discovery + delight |
| **Portfolio mode** | Pick a portfolio of outcomes at current prices. Track "returns" as probabilities shift. No real money. | Fantasy-sports energy |

**Why this could work:** We already have the hardest part — 111K+ markets with live probabilities across sports, economics, politics, weather, entertainment, tech. The content is fascinating. We just need a game layer on top.

**Depends on:** Item 22 (interestingness scoring), authentication (already shipped), user preferences (already shipped).

**Key design question:** Is the game separate from the feed, or IS the feed? Starting with "Higher/Lower" buttons on feed cards is zero new infrastructure.

**Files:** TBD — could be as simple as adding a button to FeedCard + a new `user_predictions` table, or as complex as a standalone game mode.
**Parallel Safety:** Green (new feature, new files)
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

### Other Housekeeping
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches

### 0f-9. Kalshi Win Probability Mismatched Market — DATA BUG (April 28)

**Problem:** DET @ ORL (event 14598003) shows Kalshi at ORL 93.5% while betting/ESPN/stat_model show ~37%. A ~55pp discrepancy. Visible as wild green dashed line on win probability chart.

**Root cause (suspected):** A spread or prop market is being matched as this game's moneyline. Different from 0f-7 (oscillation) — this is a wrong market entirely feeding the probability.

**Fix:** Trace which Kalshi market_id is writing to `win_probability_sources["kalshi"]` for this event. Verify it's the correct moneyline market, not a spread/prop. May need tighter market-type filtering in the live polling task.

**Files:** `backend/app/tasks/live_prediction_markets.py`, `backend/app/tasks/prediction_market_matching.py`
**Parallel Safety:** Yellow

### 0f-10b. Cross-Source Player Prop Merging

**Problem:** Now that both Kalshi and Polymarket player props surface on the same event, duplicate thresholds appear when both sources have the same player+stat. Currently the frontend deduplicates by keeping the higher probability — but the right approach is to merge across sources with weighted averaging, same as `compute_aggregate_probability()` does for win probability.

**Fix:** In `PlayerPropsDashboard.tsx`, when the same player+stat+threshold appears from multiple sources, compute a weighted average (Kalshi weight 0.8, Polymarket weight 0.8) instead of just keeping the higher value. Show source count badge.

**Files:** `frontend/components/PlayerPropsDashboard.tsx`
**Parallel Safety:** Green

### 0f-11. Win Probability and Score Differential Charts Have Different X-Axes (April 28)

**Problem:** The Win Probability chart and Score Differential chart show the same game but their x-axes don't align — different time labels, different spacing. This is visually confusing when they're stacked vertically, since the user expects Q1/Q2/HT/Q3/Q4 markers and time labels to line up between the two charts.

**Root cause:** Both charts share `sharedChartDomain` for the time range, but Recharts renders tick labels independently based on each chart's data density. The Score Differential chart has different data points than the Win Probability chart, so the auto-generated tick positions differ.

**Fix:** Force both charts to use identical x-axis tick positions. Compute a shared set of tick timestamps (e.g., every 15 or 30 minutes) in the parent, pass as explicit `ticks` prop to both charts' XAxis components.

**Files:** `frontend/app/events/[id]/page.tsx` (shared domain), `frontend/components/OddsChart.tsx`, `frontend/components/ScoreDifferentialChart.tsx`
**Parallel Safety:** Green

### 0f-12. Kalshi Half-Period Spread/Total Prices Are Non-Monotonic — DATA QUALITY (April 28)

**Problem:** Half-period spread and total market probabilities from Kalshi are frequently non-monotonic (e.g., ORL +11.5 at 24%, ORL +14.5 at 4%, ORL +17.5 at 17%). This makes the distribution visualization misleading and the data untrustworthy.

**Root cause:** Kalshi half-period markets are thinly traded. Each threshold's `yes_bid` reflects the last trade or last resting order, which may be from different points in the game. Unlike full-game moneylines (which trade actively), half spreads at +11.5 vs +17.5 may not have traded since different quarters.

**Impact:** Market Map cards for half margins/totals show nonsensical distributions. The density rail has random hot spots instead of a coherent bell curve.

**Fix options:**
1. **Client-side:** Enforce monotonicity by dropping non-monotonic points (already done for half totals). For spreads, enforce that P(team wins by X) ≥ P(team wins by X+Y) for each team separately.
2. **Backend:** Track `last_trade_time` per market and exclude markets that haven't traded in >30 min from the game-markets response. More correct but harder.
3. **Both:** Client-side cleanup as a stopgap, backend fix for real solution.

**Files:** `frontend/components/MarketMapSection.tsx` (client enforcement), `backend/app/routes/events.py` (backend filtering)
**Parallel Safety:** Yellow (touches same half-period data as market maps)
