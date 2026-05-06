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

### ~~0p. Sport/League Pages: Add Live Events~~ ✅ SHIPPED (April 28)

Moved to `docs/completed-features.md`.

### ~~0q. Feed Ranking: Penalize "Empty" Events~~ ✅ SHIPPED (April 28)

Added `compute_content_richness_penalty()` to `feed_scoring.py`. Three signals, live events only:
- **Flat line** (-10): EI is 0 after 25%+ of game elapsed
- **Scoreless stalemate** (-8): 0-0 past halftime (exempt soccer/hockey)
- **Thin data** (-5/-8): only 1 or 0 sources in `win_probability_sources`
- **Rich data** (+3): 4+ sources = small bonus
Combined penalty capped at -20. 19 new tests. Applies to web + iOS/Mac (backend feed API).

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

#### ~~Phase 1: Backend — League-scoped futures endpoint~~ ✅ SHIPPED (April 28)
`GET /api/leagues/{sport_key}` returns all open markets for a league, grouped by section (series, awards, playoff_props, season_stats, novelty). Frontend `LeagueMarketCard` component renders 3-column grid with probability bars for series. Cross-source dedup via canonical_market_key. Created `routes/league_futures.py`.

```python
{
  "series": [...],      # Series winner markets (current playoff matchups)
  "awards": [...],      # MVP, DPOY, 6MOY, MIP, ROY, Finals MVP, etc.
  "playoff_props": [...], # Sweeps, Game 7 count, playoff win totals
  "season_stats": [...],  # Win totals, stat leaders (if season ongoing)
  "novelty": [...],     # Player returns, records, streaks
}
```

Each group: markets sorted by interestingness (decisive probability + recent movement). Top 3 outcomes per market. Cross-source dedup via `canonical_market_key`.

**Key challenge:** Filtering by league, not just sport. `llm_sport_category='basketball'` includes WNBA, NCAAB, international leagues. Need to filter using ticker prefixes (`KXNBA` for Kalshi) and/or `canonical_market_key` patterns for Polymarket.

**Files:** New file `backend/app/routes/league_futures.py`, or add to `routes/futures.py`
**Depends on:** Existing `market_label_normalization.py` classification system

#### Phase 2: Frontend — Tabbed/sectioned league page
Add sections below the championship grid. Could be tabs (Games / Futures / Awards / Props) or a single scrollable page with sections (simpler, more discoverable).

Reusable components needed:
- `SeriesCard` — matchup with series score dots, probabilities, next game date
- `AwardCard` — award name, top 3 candidates with headshots + probability bars
- `PropGroupCard` — group of threshold outcomes (sweeps, Game 7s, win totals)
- `PlayerWatchCard` — player name, event description, probability bar, date

**Files:** `frontend/app/sport/[sport]/[league]/page.tsx`, new components in `frontend/components/`
**Parallel Safety:** Yellow (touches league page + new components)

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

**~~0q-1. "Pro Basketball Best Regular Season Record"~~ ✅ SHIPPED (May 2)**
Three staleness heuristics in `_score_futures()`: (1) all outcomes settled (<5% or >95%), (2) leader ≥97% with boring journey, (3) no updates for 7+ days with zero movement.

**~~0q-2. Stale Masters golf market~~ ✅ SHIPPED (May 2)**
Same fix — caught by the 7-day staleness + zero movement heuristic.

**~~0q-3. No probability bars on Top Markets futures~~ ✅ SHIPPED (May 2)**
Added fill bars to `FuturesFeedCard` top outcomes (leader in brand color, others muted). Matches existing `DiscoverCard` pattern.

**~~0q-4. Truncated futures names~~ ✅ SHIPPED (May 2)**
Replaced `truncate` with `line-clamp-2` across `FeedCard`, `DiscoverCard` (compact row + hero leader), and `CombinedFeedCard`. Long names now wrap to 2 lines.

### 0r. Golf Data Quality Issues (April 25)

**~~0r-1. Tiger Woods British Open odds~~ ✅ SHIPPED (May 2)**
Expanded `_NON_WINNER_MARKET_RE` to catch "compete at", "will X compete", "tee up", "in the field". Added binary market detector: per-golfer Yes/No markets (<=2 outcomes) now skipped from winner aggregation.

**~~0r-2. Dead category links in golf~~ ✅ SHIPPED (April 28)**
TournamentCard default href changed from `/categories/golf/tournaments/` to `/sport/golf/{tour}/{slug}`. Tour slug mapping handles dp_world→dpworld, korn_ferry→kft.

---

## Tier 1 — High Leverage, Do Next

### 0. Mystery Shopper Critical Fixes — ALL SHIPPED (April 22)

M1+M3: Golf 100%/0% + LIVE badges, M2: Mobile spinner, M4: Boring props filter,
M11/M12: Period markets + spreads on event detail, Cross-sport prop contamination,
Economics >100% distributions, Weather stale featured market.
Full report: `Manus/mystery_shopper.md`.

---

### ~~0e. Wire Manus audit results into /health skill~~ ✅ ALREADY DONE
Section H of `/health` (`.claude/commands/health.md`) already reads `Manus/audit_results/latest/manifest.json`, scans `*.md` reports for findings, flags staleness >7 days, and suggests running the suite. Verified working April 29.

### ~~0e-2. GA4 Analytics Overhaul Phases 1-3~~ ✅ SHIPPED (April 29)

Phase 1: Wired 16 dead-code events, fixed consent bug (none→denied), fixed FeedCard/SearchBar tagging, added iOS platform/login_status user properties, wired onboarding + futures tracking on iOS.
Phase 2: Added onboarding_start/skip, search_result_click, return_visit (web + iOS), app_version + days_since_install user properties (iOS).
Phase 3: Added navigation_click on BottomNav + DesktopNav, type definitions for grid_cell_click, player_prop_click, market_map_interact, share, feed_refresh.

### 0e-3. GA4 Console Configuration — TODO (Phase 4)

Not code — configuration in the GA4 property (analytics.google.com):
1. **Custom definitions**: Register `sport`, `league`, `event_id`, `event_status`, `source_section`, `position_index`, `is_live`, `is_close_game` as custom dimensions
2. **Key events (conversions)**: Mark `sign_up`, `onboarding_complete`, `event_detail_view` as key events
3. **Audiences**: Create "Sports Enthusiasts" (3+ event_detail_view / 7d), "NBA Fans" (sport=basketball_nba 5+), "Power Users" (5+ sessions / 7d)
4. **Funnels** (Explore): Acquisition (first_visit → page_view → event_card_click → event_detail_view), Onboarding (start → steps → complete), Retention (return_visit by days_since_last)
5. **Dashboards**: DAU by platform, top sports by engagement time, feed CTR, onboarding completion rate

**Parallel Safety:** Green (no code changes)

### 0f. Polymarket CLOB V2 migration — MONITOR (April 28, 2026)
Manus flagged CLOB V2 migration. Investigated April 22: both Gamma and CLOB APIs still working with current field names. We use NO SDK — all raw httpx. CLOB is only used for price history backfill (not critical path). Real risk is if **Gamma API** (`gamma-api.polymarket.com`) changes field names or pagination. Monitor around April 28.
**Action:** Re-test both endpoints on April 27. If Gamma breaks, update field mappings in `services/polymarket_api.py`.
**Files:** `services/polymarket_api.py`, `tasks/polymarket.py`

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

### ~~0f-7. Kalshi Win Probability Spikes~~ ✅ SHIPPED (April 29)

**Phase 1 (April 29):** Deduplicate markets by `(event_id, source)` before writing snapshots.
**Phase 2 (April 29):** Fixed ticker team extraction for per-team binary markets (e.g., `KXNBAGAME-26APR28BOSPHI-BOS`). The outcome suffix `-BOS` was polluting `extract_teams_from_ticker()`, causing `teams_str` to be `"bosphi-bos"` instead of `"bosphi"`. Now strips the suffix before parsing. This was the root cause of the Kalshi line showing inverted probabilities.

### ~~0f-12. Event Detail Batch Fix~~ ✅ SHIPPED (April 29)

6 fixes in one batch:
1. **Hero bubbles removed** — EI badge, sportsbook spread warning, prediction market divergence bubbles all removed (150 lines of dead code cleaned up)
2. **Player props default to Points only** — fixed `.includes("point")` substring match (caught "Three Pointers") → exact match `^points?$`. Per-card "+N more stats" expansion link replaces global toggle
3. **2nd half market grouping** — frontend now checks `market_name` (not just `outcome_name`) for half indicators. Kalshi puts "First Half"/"Second Half" in market_name only
4. **1st half final markers** — expanded halftime detection regex to also match "End of 2nd Quarter". Searches from end of ESPN history array for latest entry
5. **X-axis label alignment** — YAxis width 42→44 to match OddsChart, plus pruning ScoreDiffChart data points outside shared domain
6. **iOS league page** — synced LeagueGridModels with current API fields (marketId, region, marketName, championshipMarketId)

### ~~0f-8. Win Probability Chart Mobile Readability~~ ✅ SHIPPED (April 28)

Y-axis bumped 12→13px with darker fill (#4B5563), width 42→44. X-axis bumped 11→12px.

### ~~0f-10. Half-Game Maps Missing Actual Markers~~ ✅ SHIPPED (April 28)

1st half margin and total maps had no "Actual" tile or bubble during live games — only showed Projection/Pre-game. Fixed: during the 1st half, actual = current game scores (they're the same). During the 2nd half, uses halftime scores from ESPN history to split actuals between halves. Marker order now matches full-game maps (Actual first).

### ~~0f-11. Kalshi 2H Spread/Total Markets Not Ingested~~ ✅ SHIPPED (April 28)

Kalshi has 2nd half spread, 2nd half total, series winner, and other game-level markets that weren't appearing on event detail pages. Root cause: these are neg-risk events (`status=None`) falling outside the 50-page unfiltered pagination window. Added 25 game-level series tickers (NBA/NHL/MLB/NFL) to the supplementary fetch list. Increased per-ticker limit from 10→50. Markets will appear after next Kalshi poll cycle.

---

### 0f-13. Event Detail April 29 Review — 9 OPEN ISSUES

Reviewed BOS-PHI completed game (event 14617909). Screenshots in `/Users/bain/Desktop/Screenshot 2026-04-29 at 4.20*.png`. Issues affect BOTH web and native unless noted.

#### ~~0f-13a. Win Probability Chart Extends Past Game End (WEB ONLY)~~ ✅ SHIPPED (May 2)

`sharedChartDomain` now computes end time from game-end sources only (ESPN, stat_model, mlb, fangraphs) instead of all sources. Removed sportsbook odds from `smartEndTime` candidates. 2-min buffer instead of 5.

#### ~~0f-13b. X-Axis Labels Not Identical Between Charts (WEB ONLY)~~ ✅ SHIPPED (May 2)

Fixed by computing explicit shared tick labels in the parent component and passing them to both charts via `sharedTicks` prop, replacing Recharts' `preserveStartEnd` which picked different indices on different-length arrays.

#### ~~0f-13c. 2nd Half Margin/Total Maps Not Showing (WEB)~~ ✅ SHIPPED (May 2)

Root cause: `halfMarginMaps` was reading from `gameMarkets.spreads` (full-game only) instead of `gameMarkets.period_markets` (where the backend puts `half_spread` markets). Fixed to read from `period_markets` with `market_type === "half_spread"` filter. Both 1H and 2H margin maps now render.

#### 0f-13c-native. 2nd Half Margin/Total Maps Not Showing (NATIVE ONLY — remaining)

**Problem:** Only 1st half maps show. 2nd half maps don't appear on either platform. The web fix (checking `market_name` for half grouping) either hasn't deployed or the underlying 2H market data still isn't in our DB.

**Investigation needed:**
1. Check if the Kalshi poll has run since adding 2H tickers to supplementary fetch (April 28)
2. Check if 2H spread/total markets exist in `futures_markets` with `event_id` set for this event
3. If they exist, check if `_classify_game_market()` returns `half_spread`/`half_total` for them
4. If classified correctly, check if the frontend grouping logic picks them up

**Files:** `backend/app/services/kalshi_api.py` (supplementary fetch), `backend/app/routes/events.py` (`_classify_game_market`), `frontend/components/MarketMapSection.tsx` (grouping), `ios/.../Components/MarketMapSection` (if exists)

#### ~~0f-13d. Double Doubles in Additional Markets, Not Player Props~~ ✅ SHIPPED (May 2)

Root cause: `_PLAYER_PROP_RE` had `double.?double\b` — the `\b` word boundary rejected the plural "Doubles". Fixed both `_PLAYER_PROP_RE` and `_is_team_stat_market` to accept `doubles?`. Team-level "Double Doubles" → `team_total`, player-level "Tatum Double Doubles" → `player_prop`.

#### ~~0f-13e. Hero Bubbles + EI Badge Still Showing on NATIVE~~ ✅ SHIPPED (May 2)

Removed EI badge, sportsbook spread warning, prediction market divergence bubbles, and stakes capsule from iOS hero. Also removed dead `divergenceBadge` method. -135 lines.

#### ~~0f-13f. Standings Context Still Showing on NATIVE~~ ✅ SHIPPED (May 2)

Removed `standingsSection` call and method from iOS `EventDetailView.swift`. Redundant with Championship Path card.

#### 0f-13g. Player Prop Cards Not Fixed on NATIVE

**Problem:** Web player props now default to Points only with per-card "+N more stats" expansion. Native still shows both Points AND Three Pointers side by side for every player, with no way to collapse.

**Fix:** Port the web fix to iOS: default to Points stat only, add per-card expansion for other stats.

**Files:** `ios/.../Components/PlayerPropsCardView.swift` (or equivalent)

#### 0f-13h. Player Award Headshots Missing on WEB

**Problem:** Native shows player headshots (from roster data) next to award names in the Season Futures / Awards section. Web shows only colored initials circles.

**Fix:** The web "Bigger Picture" section's award display needs to use the `PlayerHeadshot` component (already exists for player props). Check if the award data from the `team-progression` endpoint includes player image URLs. If not, the backend needs to enrich award outcomes with headshot URLs from roster data.

**Files:** `frontend/app/events/[id]/page.tsx` (Bigger Picture section), `backend/app/routes/events.py` (team-progression endpoint)

#### ~~0f-13i. Polymarket Not Showing in Any Game Markets Section~~ ✅ SHIPPED (May 2)

**Root cause:** Polymarket creates series-level events (e.g., "Celtics vs. 76ers" covers all playoff games). Sub-market names like "O/U 196.5" don't include team names. The matching task linked parents to old completed events instead of current games, and the fallback name-matching query couldn't find sub-markets without team names.

**Fix (3 commits):**
1. Game-markets endpoint: find Polymarket parents by team name, then pull all sub-markets via `group_id` — bypasses `event_id` linking entirely
2. Matching scoring: +8 bonus for Odds API events to prevent matching to wrong game
3. Phase 1.5: prioritize open markets linked to completed events for re-linking

**Remaining polish:** De-duplicate Polymarket spreads that appear multiple times (series has overlapping game markets). Game-specific sub-market routing (Game 1 vs Game 5 within a series).

---

### Bug Report #3 — Runs Map Missing Zero Label (HOU 3 - BOS 1, May 5)

#### ~~BR3-1. Market map axes must always label zero~~ ✅ SHIPPED (May 6)

Fixed: MarketMap now renders a positioned "0" label at the actual zero position when it's offset from the visual center (where "Tie" sits). Margin maps already label zero as "Tie" at center. Commit `1e2a598`.

---

### Bug Report #4 — Player Props Layout (HOU 3 - BOS 1, May 5)

#### BR4-1. Wasted space in Player Props header (iOS)

**Problem:** Large empty grey area to the right of the Player Props header. The "KALSHI" badge + "All stats" link + team filter tabs ("All", "Sox", "Astros") don't fill the available width, leaving a visible gap on the right side.

**Fix:** Either make the filter tabs fill the width, or tighten the header layout so the gap isn't visible.

**Files:** `ios/.../Components/PlayerPropsCardView.swift` or equivalent player props header
**Parallel Safety:** Green

---

### Bug Report #5 — Baseball Period Markets Misclassified (HOU 3 - BOS 1, May 5)

#### BR5-1. "First 5 Innings" should get market map treatment, not "Other Markets"

**Problem:** "Houston vs Boston: First 5 Innings" appears under "Additional Markets → Other Markets" as a raw outcome list. This is the baseball equivalent of a 1st half market — it should be classified as `half_total` or `half_spread` and rendered as a market map (like 1st half spread/total maps in basketball and football).

**Fix:** Update `_classify_game_market()` in `backend/app/routes/events.py` to recognize "First 5 Innings" / "F5" as a half-game market. Add regex pattern for baseball-specific period names.

**Files:** `backend/app/routes/events.py` (`_classify_game_market`, `_is_half_market` or similar)
**Parallel Safety:** Yellow

#### BR5-2. "First Inning Run" should not be in "Other Markets"

**Problem:** "Houston vs Boston: First Inning Run" (Yes 50%) is in "Other Markets" but is a well-known baseball prop. Could be shown as a binary prop card or integrated into the game markets section with better UI.

**Fix:** Classify as `game_prop` or `period_market` rather than `other`. Consider a dedicated binary prop display.

**Files:** `backend/app/routes/events.py` (`_classify_game_market`)
**Parallel Safety:** Yellow

---

### Bug Report #1 — Event Detail Page (PHI 109 - BOS 100, May 4)

From rage shake. Three separate issues on a completed NBA playoff game event detail page.

#### ~~BR1-1. Pre-game odds shown twice in hero~~ ✅ SHIPPED (May 5)

**Problem:** The completed-game hero shows opening odds as the giant probability numbers (41% / 59%) AND repeats them as an "Opened 41% – 59%" caption below. Redundant — same numbers displayed twice.

**Fix:** Change the caption to "Pre-Game Odds" label (since the big numbers already ARE the opening odds), or remove the caption entirely.

**Files:** `ios/.../Views/EventDetailView.swift` (hero section, `isFinished` branch ~line 468-488), `frontend/app/events/[id]/page.tsx` (equivalent web hero)
**Parallel Safety:** Green

#### BR1-2. Source attribution looks duplicated — NEEDS DESIGN

**Problem:** The source list (sportsbooks contributing to the aggregate) appears to show twice — once as a static list and once inside a collapsible dropdown. The dropdown is valuable because it shows we're aggregating across many sportsbooks, but in practice users see the sources listed twice since they don't click the dropdown. Needs a design fix, not just a code change.

**Design question:** How should source attribution work? Options:
- Show just the count ("Aggregated from 12 sportsbooks") with dropdown for details
- Show the dropdown only, collapsed by default
- Inline chips for the top 3 sources + "+9 more" expander

**Files:** `ios/.../Views/EventDetailView.swift` (`sourcesToggle` ~line 824), `frontend/app/events/[id]/page.tsx`
**Parallel Safety:** Yellow (design brief needed)

#### BR1-3. Kalshi/Polymarket probabilities missing for NBA playoff game

**Problem:** Kalshi and Polymarket had markets for this NBA playoff game, but their probabilities didn't show on the event detail page — neither during the game nor after. This is a linking issue, not a completed-event filtering issue.

**Investigation:** Check if the prediction market matching task linked Kalshi/Polymarket game markets to this event (via `event_id` FK on `futures_markets`). If not, the matching task may be failing for NBA playoff games specifically. Check `futures_markets` for Kalshi NBA playoff tickers and whether they have `event_id` set.

**Files:** `backend/app/tasks/prediction_market_matching.py`, `backend/app/routes/events.py` (game-markets endpoint)
**Parallel Safety:** Yellow

---

### Manus Sweep May 4 — 7 Issues Found (Health Score: 58/100)

9 modules run, all completed. MLB and NBA live pages are excellent. Grids score 85-92. Source accuracy within 3pp of Kalshi/Polymarket across all spot checks.

#### ~~MS-May4-1. MLB Monotonicity Violation — Runs Map~~ ✅ SHIPPED (May 5)

**Event:** Mets vs Rockies (`/events/14624780`)
**Problem:** Full game runs map jumps from 41% (Over 6.5) to 75% (Over 7.5). Indicates two datasets merged incorrectly — likely Polymarket sub-markets (from new group_id lookup) merging with Kalshi spreads and bypassing per-source monotonicity enforcement.
**Fix:** `MarketMapSection.tsx` monotonicity enforcement needs to run AFTER cross-source merge, not per-source. Or dedup by threshold before enforcing.
**Files:** `frontend/components/MarketMapSection.tsx`, `backend/app/routes/events.py` (game-markets dedup)
**Parallel Safety:** Yellow

#### ~~MS-May4-2. Chart extends 50-60 min past game end for Soccer~~ ✅ SHIPPED (May 5)

**Timing Health Score:** 39/100
**Problem:** EPL/La Liga/UCL charts extend 50-60 min past actual game end with stale bookmaker data. NBA 20-30 min. NHL/MLB are clean (within 5 min).
**Root cause:** May 2 fix clips at last ESPN data point — but soccer events have no ESPN data. Fallback to `completed_at` or last non-sportsbook data source needs to fire for non-US sports.
**Files:** `frontend/app/events/[id]/page.tsx` (`sharedChartDomain`, lines ~382-440)
**Parallel Safety:** Yellow

#### ~~MS-May4-3. Tennis Futures — Infinite Loading Spinner~~ ✅ SHIPPED (May 6)

Fixed: Skip SWR fetch for invalid/NaN market IDs, show back navigation during loading/error states, improved error messages. Commit `79d721f`.

#### MS-May4-4. EPL League Page Data Contamination

**Problem:** EPL page shows contaminated data from non-EPL sources. Need to investigate what's leaking in.
**Files:** Backend league page endpoint, sport key classification
**Parallel Safety:** Yellow

#### ~~MS-May4-5. NBA/NHL Grids Missing Make Playoffs + Win Division~~ ✅ SHIPPED (May 5)

**Problem:** Only Conference + Championship columns shown. MLB correctly shows all 4. Grid endpoint may filter out resolved playoff-stage markets during active playoffs.
**Files:** `backend/app/routes/futures.py` or `playoffs.py` (grid endpoint)
**Parallel Safety:** Yellow

#### MS-May4-6. NBA 1H Total — 7 Thresholds vs Kalshi's 9 (23% gap at Over 98.5)

**Problem:** Missing 2 threshold values from Kalshi. Could be outcome ingestion issue or dedup filtering too aggressively.
**Files:** Backend outcome ingestion, `backend/app/routes/events.py` (game-markets threshold logic)
**Parallel Safety:** Yellow

#### MS-May4-7. NBA Duplicated Player Awards in Futures Section

**Problem:** Awards appearing multiple times on event detail page. Likely a dedup issue in related-futures endpoint.
**Files:** `backend/app/routes/events.py` (related-futures), `frontend/app/events/[id]/page.tsx`
**Parallel Safety:** Yellow

---

### Manus Site Sweep Findings (April 25) — NEW

Full report: `Manus/audit_results/site_sweep_april25.md`

#### ~~MS-1. Small text audit — 388 elements <11px across site~~ ✅ SHIPPED (April 28)
Bumped text-[9px]→10px and text-[10px]→11px across FeedCard, ChampionshipGrid, OddsChart, event detail page. Trend indicators 7→9px.

#### ~~MS-2. Cookie consent banner overlaps bottom nav~~ ✅ SHIPPED (April 27)
Banner uses `bottom-16` on mobile to sit above the tab bar.

#### ~~MS-3. Missing team logos on event detail (pink/grey placeholders)~~ ✅ SHIPPED (April 28)
ESPN CDN fallback when team_data.logo_large missing + onError handler shows initials if image fails.

#### MS-4. Game props missing team names
**Problem:** Game props section shows "Team 199.5 84%" instead of "Hawks 199.5 84%". Team name not being passed through.
**Fix:** Check game-markets API response — `team_name` may be null for some market types. File: `frontend/components/PlayerPropsDashboard.tsx`, `backend/app/routes/events.py` (game-markets endpoint).
**Parallel Safety:** Yellow

#### ~~MS-5. NYC rainfall listed 8 times~~ ✅ SHIPPED (April 27)
Monthly rain deduplicates by city name, keeps latest resolution date.

#### ~~MS-6. Tornado months non-chronological~~ ✅ SHIPPED (April 27)
Tornado markets sorted by resolution date (chronological).

#### ~~MS-7. Championship grid: no horizontal scroll indicator on mobile~~ ✅ SHIPPED (April 28)
Changed overflow-hidden → overflow-x-auto with right-edge gradient fade on mobile.

#### MS-8. Kalshi 1.0% minimum tick misleading in grids
**Problem:** Many teams show exactly "1.0%" for Conference/Champion odds. This is Kalshi's minimum tick, not a real 1% probability — it's misleading when aggregated.
**Fix:** Filter or annotate Kalshi values at the minimum tick (0.01). Either: (a) exclude from aggregation when it's the only source at 1%, or (b) show "< 1%" instead of "1.0%". This is similar to the existing Kalshi noise filter (0.45-0.65 range).
**Files:** `backend/app/routes/playoffs.py` (grid cell assembly), `backend/app/utils/playoff_grid.py`
**Parallel Safety:** Yellow

### 0f-9. Mac App — SHIPPED + Polish (April 24-25)

**SHIPPED:** Native macOS target compiles and runs. SwiftUI multiplatform — same codebase as iOS with `#if os` conditionals. 30 files modified. Sidebar nav, adaptive grid, keyboard shortcuts (Cmd+1-4), light mode, Mac icon.

**Remaining macOS polish items:**

| # | Feature | Effort | Notes |
|---|---------|--------|-------|
| MAC-1 | **Live-updating title bar** | 1-2h | Show score in window title (e.g., "BOS 87 - PHI 82 • Q4 2:31") when on event detail. Visible even when app is backgrounded. |
| MAC-2 | **Multi-window support** | 2-3h | Cmd+click event → opens in own window. Watch multiple games. THE killer desktop feature. Uses SwiftUI `openWindow(value:)`. |
| MAC-3 | **Keyboard navigation** | 2-3h | Arrow keys between feed cards, Enter to open, Escape to go back. `.focusable()` + `onKeyPress`. |
| MAC-4 | **Toolbar refresh button** | 30min | Add refresh button + countdown ring to toolbar on event detail. |
| MAC-5 | **Menu bar extra (scores)** | 3-4h | Clover icon in macOS menu bar → dropdown with live scores. `MenuBarExtra` API. |
| MAC-6 | **Push notifications** | 2-3h | Game start, momentum shifts, upsets. macOS notification center. |
| MAC-7 | **Hover states** | 1-2h | Feed cards highlight on mouse hover. `.onHover` modifier. |
| MAC-8 | **Right-click context menus** | 1h | Pin, copy probability, open in new window. Some already via `.contextMenu`. |
| MAC-9 | **Share button + universal links** | 2-3h | Share button on event detail (top-right). Shares `https://bainluck.com/events/{id}`. Falls back to web for non-app users. Also consider drag-and-drop of cards to create shareable links. |
| MAC-12 | **macOS widgets** | 3-4h | Desktop widgets showing live scores/probabilities. `WidgetKit`. |

**Files:** `ios/Bain Luck/Bain Luck/` (various Views, Bain_LuckApp.swift)
**Parallel Safety:** Green (iOS-only changes)

---

### ~~0f-3a. Player Props: Team Filter Bug (SOX/YAN pills)~~ ✅ DEPLOYED (April 24)

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
heroku ps:restart worker-background -a bainluck && sleep 30 && curl -X POST "https://api.bainluck.com/api/admin/kalshi/poll?secret=$ADMIN_TOKEN"

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

#### ~~Issue 1: NBA markets incorrectly linked to MLB event~~ ✅ SHIPPED (May 6)

Fixed: Ticker-derived sport prefix now hard-rejects cross-sport matches in `_score_candidates()`. KXNBA tickers can no longer link to baseball_mlb events. Commit `6dbf84f`.

#### Issue 2: Zero Polymarket game-specific markets linked
~20 Polymarket markets exist mentioning Red Sox/Yankees (NRFI, win markets), but ALL have `sport_id=None` and `llm_sport_category=None`. They're never considered for linking because the matching task requires sport identification.

**Fix:** Improve Polymarket sport classification. These markets have team names in their titles ("New York Yankees vs. Boston Red Sox") — the matching task should detect the sport from team names even without explicit sport metadata.
**Files:** `tasks/polymarket.py` (sport classification), `tasks/prediction_market_matching.py`

#### Issue 3: Tomorrow's game markets linked to today's event
6 Kalshi markets with APR23 tickers (tomorrow's game) are linked to today's event. The matching task linked them based on team name + time window without distinguishing the game date embedded in the ticker.

**Fix:** Extract game date from Kalshi ticker (e.g., `KXMLBHIT-26APR23NYYBOS` → April 23) and compare to event `commence_time` date. Reject if dates differ by >1 day.
**Files:** `tasks/prediction_market_matching.py`, `utils/prediction_market_matching.py` (`extract_game_date_from_ticker`)

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

#### 0t-bonus. Soccer EFL/League 2: 53-Minute Late Start — NOT A BUG

**Investigation (May 6):** Traced the full commence_time chain — Odds API → `fromisoformat(Z→+00:00)` → Event Registry → DB. All UTC throughout, no BST/UTC confusion anywhere. The 53-minute gap is not a timezone issue (BST would be exactly 60min). Most likely cause: late odds publication for lower-tier English football — event is created at discovery time but odds don't flow until bookmakers post lines near kickoff. Tier 3/4 sports also poll less frequently. No code fix needed.

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

#### ~~1b. Ticker-Based Team Name Fallback~~ ✅ SHIPPED (April 27)
Added `external_id` param to `match_teams_to_event()`. When fuzzy name matching fails, falls back to `extract_teams_from_ticker()` which uses reliable 3-letter Kalshi ticker codes. 2 new tests.

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

### ~~PREQ-7. N+1 Query Audit~~ ✅ SHIPPED (April 28)

Fixed all 5 top Sentry N+1 issues (4,350+ events total). Root cause was Celery tasks, not API routes (routes already had correct `selectinload()`). Three batch-loading fixes: ESPN team cache, PM outcome batch-load, odds snapshot cache. Monitor Sentry over 24h to confirm drop to zero.

**Monitor / low priority:**
| ID | Events | Status |
|----|--------|--------|
| N+1 Query warnings (GA, H0, G7, K8, KE) | 4,350+ | **PREQ-7 shipped April 28. ESPN sync N+1 fixes May 2 (win_probability_sources re-read × 3 + identity registration × 2). Monitoring.** |
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

### SEARCH. Search Overhaul — IN PROGRESS (May 1, 2026)

**Problem:** Search is broken and embarrassing. Typeahead shows raw HTML entities (`&#x1f4c8;`), futures results are duplicated/truncated, ranking is noisy, non-sports markets (weather, economics, politics) are completely unsearchable, and there's no fuzzy matching or typo tolerance.

**Screenshot:** Searching "celtics" returns Boston Celtics (good), 1 game (good), then 3 near-identical "Celtics vs 76ers" futures with raw HTML entity codes and truncated names. The futures results are indistinguishable and take up all the dropdown space.

**Current architecture:** 3 backend endpoints in `routes/events.py` (typeahead, full search, suggestions). Frontend in `components/SearchBar.tsx` + `app/search/page.tsx`. All matching is `ILIKE '%query%'` — no trigram, no full-text search, no fuzzy matching. No indexes on searched columns.

**Files:** `backend/app/routes/events.py` (lines 577-1219), `frontend/components/SearchBar.tsx`, `frontend/app/search/page.tsx`, `frontend/lib/api.ts`

#### ~~Phase 1: Fix What's Broken (1-2 days)~~ ✅ SHIPPED (May 1)

- [x] **P1a. HTML entity rendering** — Fixed: Unicode escapes in `<span>` elements instead of JS string HTML entities.
- [x] **P1b. Deduplicate futures in typeahead** — Fixed: group_id dedup in both typeahead and full search. Fetches 15/20 candidates, deduplicates, returns top 3/10.
- [x] **P1c. Better display names** — Fixed: `market_type_label` on all futures (Championship/Conference/Award/Division/Prop). Ranking by tier + volume instead of updated_at.
- [x] **P1d. Widen dropdown** — Fixed: `min-w-[480px]` on sm+ breakpoints. Commit `dee1b74`.

#### ~~Phase 2: Better Matching (1 week)~~ ✅ SHIPPED (May 1)

- [x] **P2a. Search team `alternate_names`** — JSONB `alternate_names` now searched via `cast(Team.alternate_names, String).ilike()`.
- [x] **P2b. Search player names** — Typeahead now searches `FuturesOutcome.name` via `.any()` subquery. "Tatum" finds player prop markets.
- [x] **P2c. Search Discover/non-sports markets** — Non-sports markets (sport_id IS NULL) searched as fallback in typeahead. Category label from `llm_sport_category`.
- [x] **P2d. Multi-word futures matching** — AND across terms in market name, same as events. "celtics championship" works.

**Also shipped:**
- Cross-source dedup via normalized name (sorted team names, stripped prefixes)
- Tier 5 patterns for game-level markets (first half, series, O/U, next team, win by)
- Removed blind trust of `category="championship"` (Polymarket labels everything as championship)
- 8 new tests for tier 5 classification
- Wider dropdown (min-w-[360px])

#### ~~Phase 3: Smarter Ranking (1 week)~~ ✅ SHIPPED (May 1)

- [x] **P3a. Relevance scoring** — Futures ranked by tier ASC + volume DESC. Events ranked by live-first + commence_time ASC. Tier fix (Phase 2) ensures championship > prop.
- [x] **P3b. Category-aware grouping** — Search results page shows "Games (N)" and "Futures & Markets (N)" as grouped sections with clear counts.
- [x] **P3c. Smart typeahead slot allocation** — Collect into pools, then assemble: 1 team + 2 events + 2 futures baseline, fill remaining 2 slots from extras. No more 5 futures crowding out games.

**Also shipped:**
- Backfill script (`scripts/backfill_market_tiers.py`) to recompute tier for existing Polymarket markets
- Cleaner search results header

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
- [ ] **SN-5. Cmd+K shortcut on macOS** — Web has `Cmd+K` global focus. Missing on macOS build. **P2**

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

**Status (April 25-26): 11 of 12 items SHIPPED.**

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

### ~~PREQ-7. N+1 Query Audit~~ ✅ SHIPPED (April 28)
Batch-loading fixes in 3 Celery tasks: `espn_sync.py`, `prediction_market_matching.py`, `odds_polling.py`. PREQ sprint now 12/12 complete.

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

### iOS-18. Prevent Screen Sleep While App Is Foreground

**Problem:** The phone auto-locks / screen dims while using the app. When you're watching a game and glancing at live probabilities, the phone shouldn't go to sleep.

**Fix:** Set `UIApplication.shared.isIdleTimerDisabled = true` when the app is in the foreground, and re-enable it when backgrounded. In SwiftUI, apply this in the root `App` struct using `.onChange(of: scenePhase)`:

```swift
@Environment(\.scenePhase) var scenePhase

.onChange(of: scenePhase) { newPhase in
    UIApplication.shared.isIdleTimerDisabled = (newPhase == .active)
}
```

This keeps the screen on while the app is visible and restores normal sleep behavior when the user switches away.

**Files:** `ios/Bain Luck/Bain Luck/Bain_LuckApp.swift`
**Parallel Safety:** Green (one line, no conflicts)
**Effort:** 5 minutes

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

#### iOS-GD1. Mystery "8" icon between teams in hero
**Problem:** Unlabeled value (likely EI badge) appears between team logos in the hero section. No context for what it means.
**Approach:** Confirm what the value represents in `EIBadgeView`. Label it clearly, or hide it for completed games since EI is a pre-game/live concept — showing it post-final is meaningless.
**Files:** `ios/.../Components/EIBadgeView.swift`, `EventDetailView.swift` (hero section)
**Parallel Safety:** Green

#### ~~iOS-GD2. Records visually merge with score~~ ✅ SHIPPED (May 5)
**Problem:** Team records ("10-17" / "13-14") sit directly under scores ("17 / 1") with similar font weight and color, making them hard to distinguish at a glance.
**Approach:** Reduce font size/weight on records, switch to `text-muted` color, and/or prefix with "Record:" to differentiate from the score.
**Files:** `ios/.../Views/EventDetailView.swift` (hero section)
**Parallel Safety:** Green

#### iOS-GD3. Win prob chart drifts toward 50% post-final — PRIORITY
**Problem:** For BOS @ BAL (final 17–1), the aggregate win probability drifts toward ~50% after the game ends, even though real sources resolved to ~100%. Likely a wrong Kalshi/Polymarket market linked to the event, and/or upstream market resolution status isn't propagating.
**Approach:** Investigate via: `SELECT id, source, source_market_id, name, status, last_price FROM prediction_markets WHERE event_id = <id>`. Fix root cause in match logic (`app/utils/prediction_market_matching.py`) and/or status propagation (`app/tasks/prediction_market_matching.py`, `poll_live_prediction_markets`). Add audit: for every completed event, every linked market should be resolved upstream and our latest snapshot should match the realized outcome within tolerance. New check in `scripts/audit_matching_quality.py` or `audit_post_final_consistency.py`.
**Files:** `backend/app/utils/prediction_market_matching.py`, `backend/app/tasks/prediction_market_matching.py`, `backend/app/tasks/live_prediction_markets.py`
**Parallel Safety:** Yellow (backend matching logic)

#### ~~iOS-GD4. Two "Bain Luck" series in chart legend~~ ✅ SHIPPED (May 5)
**Problem:** Chart legend shows both "Bain Luck" (aggregate) and "Bain Luck Model" — confusing which is which.
**Approach:** Rename aggregate series to "Bain Luck Agg". For "Bain Luck Model", look up what the model is actually based on (start in `app/config/win_prob_sources.py`, follow the source key, then check `app/services/`/`app/utils/` for implementation) and rename to reflect the basis. Update source label in `win_prob_sources.py` and legend strings in `OddsChartView`.
**Files:** `backend/app/config/win_prob_sources.py`, `ios/.../Components/OddsChartView.swift`
**Parallel Safety:** Yellow (touches backend config + iOS)

#### iOS-GD5. Game-state indicators cluttered on chart
**Problem:** Inning numbers above the chart frame are cramped and hard to read.
**Approach:** KEEP x-axis time-based (do NOT make innings/periods the primary tick units — breaks for sports with few phases). Drop the cramped strip of inning numbers above the chart frame. Replace with light vertical gridlines at inning-boundary timestamps and small floating chips ("1"…"9") tied to each gridline near the top of the plot area. Degrade gracefully to "1H/2H" for soccer/basketball halves. Time labels at the bottom remain the only x-axis ticks.
**Files:** `ios/.../Components/OddsChartView.swift`
**Parallel Safety:** Green

#### ~~iOS-GD6. Sources row renamed~~ ✅ SHIPPED (May 5)
**Problem:** Non-functional UI row in the chart section. No interaction, wastes vertical space.
**Approach:** Remove the row from `OddsChartView`.
**Files:** `ios/.../Components/OddsChartView.swift`
**Parallel Safety:** Green

#### ~~iOS-GD7. First x-axis tick rounds up past game start~~ ✅ SHIPPED (May 5)
**Problem:** First x-axis tick is 10:00 AM despite a 9:05 AM game start, creating a misleading gap.
**Approach:** Adjust tick generator so the first label aligns with game start (or a half-hour-aligned tick that includes the start) instead of rounding up to the next whole hour. Likely a one-line axis configuration change.
**Files:** `ios/.../Components/OddsChartView.swift`
**Parallel Safety:** Green

#### iOS-GD8. Player props show initials instead of headshots
**Problem:** Player prop cards use colored-initial chips instead of headshots, even when headshot URLs are available.
**Approach:** Replace colored-initial chips in `PlayerPropsCardView` with the headshot pattern Awards uses in `RelatedFuturesView`. Initials are the fallback when no headshot URL is available. Reuse the existing image-loading helper.
**Files:** `ios/.../Components/PlayerPropsCardView.swift`, `ios/.../Components/RelatedFuturesView.swift` (reference)
**Parallel Safety:** Green

#### iOS-GD9. Championship Path shows wrong league rows
**Problem:** "AL / NL Champ" row appears for AL-only matchups (e.g., two AL teams). Should show only the relevant pennant.
**Approach:** Make the row league-aware in `ChampionshipPathView`: when both teams share a league/conference, show only that pennant ("AL Pennant"); otherwise keep "AL / NL Champ" for cross-league matchups. Apply same logic for NBA/NHL/NFL conference finals. League is already on the team record.
**Files:** `ios/.../Components/ChampionshipPathView.swift`
**Parallel Safety:** Green

#### ~~iOS-GD10. Prose summary removed~~ ✅ SHIPPED (May 5)
**Problem:** Related futures section shows a text summary blob instead of the card-based design the web app uses.
**Approach:** Port the web card design. Find components under `frontend/components/RelatedFutures*`, enumerate the props they consume, verify the iOS related-futures payload provides the same fields (extend if not), then build SwiftUI equivalents in `RelatedFuturesView.swift` to replace the `summary` text block.
**Files:** `ios/.../Components/RelatedFuturesView.swift`, `frontend/components/RelatedFutures.tsx` (reference)
**Parallel Safety:** Green

#### ~~iOS-GD11. Awards section: probability bars added~~ ✅ SHIPPED (May 5)
**Problem:** Award outcomes show percentages but no visual bars, unlike the web version.
**Approach:** Port the web award card design to SwiftUI. Bar primitive already exists (`ProbabilityBar.swift`). Match the web row layout: headshot, player name, award label, probability bar, percent.
**Files:** `ios/.../Components/RelatedFuturesView.swift` (awards section), `ios/.../Components/ProbabilityBar.swift`
**Parallel Safety:** Green

#### iOS-GD12. Trevor Story missing headshot
**Problem:** Trevor Story's award row shows an initials chip instead of a headshot.
**Approach:** Verify whether the headshot URL is missing in the API payload or just not loading on iOS. Add a generic player silhouette as fallback so rows look uniform even when headshots are unavailable.
**Files:** `ios/.../Components/RelatedFuturesView.swift`, backend roster data
**Parallel Safety:** Green

#### ~~iOS-GD13. Season Stats dedup~~ ✅ SHIPPED (May 5)
**Problem:** "Make Playoffs" (Championship Path: BOS 32%, BAL 50%) and "Team to make postseason" (Season Stats: BOS 31%, BAL 51%) are the same concept matched as two separate markets with slightly different numbers.
**Approach:** Treat as a futures-side matching problem first: identify the two `futures_markets` rows feeding each section, unify them at the futures matcher, then drop the postseason row from Season Stats (Championship Path is canonical). Repeat for "AL East Winner" — likely folds into a Division row. After consolidation, reassess whether Season Stats earns its place at all. Add an audit check for futures markets that should have unified but didn't.
**Files:** `backend/app/routes/events.py` (related-futures logic), `backend/app/utils/related_futures.py` (dedup), `ios/.../Components/RelatedFuturesView.swift`
**Parallel Safety:** Yellow (backend dedup logic)

#### ~~iOS-GD14. Game Info absolute dates~~ ✅ SHIPPED (May 5)
**Problem:** Footer shows "Today 9:05 AM" for a FINAL game. Should be state-aware.
**Approach:** Make the label driven by `event.status`:
- Scheduled → "Today 9:05 AM" / "Tomorrow 7:00 PM"
- Live → "Started 9:05 AM"
- Final → "Final · Apr 25, 9:05 AM"
**Files:** `ios/.../Views/EventDetailView.swift` (espnSection / game info footer)
**Parallel Safety:** Green

#### ~~iOS/macOS Event Detail Parity Sweep~~ ✅ SHIPPED (April 28)
Full parity achieved. See `docs/completed-features.md`. Added: tag chips, trend indicator, projected score, divergence warnings, stakes context, bookmaker table, market maps, special event markets, series probability, league page link, related-by-tag. Removed from web: Game Segments, Period Markets, Blowout Warning.

#### iOS-GD — NOT YET APPROVED (ask before adding)
- Score Differential chart inning labels cramped; "Projected Spread" occluded by "Actual Score Diff."
- Player Props 2-col grid leaves orphan card on odd counts
- Game Info footer duplicates broadcaster + time already in hero
- Bookmark icon floats outside standard nav cluster

---

## Tier 2.5 — Discover Feed Enhancement (April 29)

### ~~D-1. Market Card Images~~ ✅ SHIPPED (April 30)
Pexels API integration. `image_url` column on FuturesMarket. Enrichment task runs 2x daily.

### ~~D-2. LLM Hook Descriptions~~ ✅ SHIPPED (April 30)
GPT-4o-mini generates 1-sentence hooks. `hook_description` column. Enrichment task runs 2x daily.

### ~~D-3. Content Ranking~~ PARTIALLY SHIPPED (April 30)
Staleness filtering, category interleaving, non-sports quota implemented in Discover page. Volume-weighted scoring deferred.

### ~~D-4. Behavioral Engagement Tracking~~ PARTIALLY SHIPPED (April 30)
`user_predictions` table tracks Higher/Lower guesses. Full click/view tracking deferred.

### ~~D-5. Native Discover Feed~~ ✅ SHIPPED (April 30)
DiscoverView.swift with category chips, event/futures/guess cards, API wiring.

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
- [x] **~~DN-7. Guess density** — Web shows guess slot every 2nd card. iOS shows every 5th. Lower engagement surface.
- [x] **~~DN-8. Dismiss persistence** — Same as D-10a. iOS uses `@State` — dismissed items reset on tab switch.

**P2 — Nice to have:**
- [ ] **DN-9. Swipe to dismiss** — Web has swipe left/right with like/dismiss overlays.
- [ ] **DN-10. Onboarding flow** — "Build Your Feed" modal with category selection.
- [ ] **DN-11. Grouped market cards** — Markets grouped by name prefix (e.g., "Valero Texas Open: ...").

**Files:** `ios/.../Views/DiscoverView.swift` (careful — active native thread may be touching this), new `ios/.../Views/PredictionStatsView.swift`, `ios/.../Models/DiscoverModels.swift`

---

### ~~D-3a. Volume-Weighted Feed Scoring~~ ✅ SHIPPED (May 6)
Added `volume_24h` + `volume_7d_avg` to `compute_base_score`, volume velocity scoring (3x avg = spike +12, 1.5x = uptick +5), surprise factor (`abs(current - opening)` >= 20% = +15, >= 10% = +8) to both event and futures scoring. Commit `b47f8a0`.

### D-4a. Full Click/View Tracking (REMAINING)
`user_interactions` table logging event/futures detail views. Backend middleware for zero-frontend-work implicit tracking. View-weighted sport affinities.
**Files:** New migration, `backend/app/main.py`, `backend/app/utils/personalization.py`

### D-10a. Dismiss Persistence (Discover)
Dismiss actions on Discover cards are currently `@State`/`useState` — they reset on tab switch or page reload. Persist dismissed IDs server-side (extend `user_seen_markets` with a `dismissed` boolean, or separate `user_dismissed_markets` table). Both web and native should check dismissed state on load.
**Files:** `backend/app/routes/predictions.py`, `frontend/app/discover/page.tsx`, `ios/.../Views/DiscoverView.swift`

### D-10b. Like/Dismiss → Feed Ranking
Feed thumbs up/down and Discover dismiss signals should feed back into futures scoring. New `user_market_feedback` table with `(user_id, market_id, signal, category)`. `_score_futures()` in `feed.py` applies a personalization multiplier based on category-level feedback (liked categories boosted, dismissed categories suppressed). Same pattern as the existing `compute_futures_multiplier()` for sport affinities.
**Files:** New migration, `backend/app/routes/feed.py` (`_score_futures`), `backend/app/utils/personalization.py`

### ~~D-10. Resolution Notifications Backend~~ ✅ SHIPPED (May 6)
Backend endpoint `/api/predictions/resolutions` already existed. Added `fetchResolutions` API client, wired SWR call into Discover page, renders up to 3 ResolutionCards at top of feed. Commit `94cdf52`.

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

### WrestleMania — **DONE (April 21)**
Archive: `docs/archive/wrestlemania-reference.md`. All runtime code deleted. DB tables preserved.

### Other
- **May 1**: Delete `frontend/_to-delete/` if nothing broke
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches
- Code review reference: `.claude/plans/mutable-cooking-ember.md`

### 0f-9. Kalshi Win Probability Mismatched Market — DATA BUG (April 28)

**Problem:** DET @ ORL (event 14598003) shows Kalshi at ORL 93.5% while betting/ESPN/stat_model show ~37%. A ~55pp discrepancy. Visible as wild green dashed line on win probability chart.

**Root cause (suspected):** A spread or prop market is being matched as this game's moneyline. Different from 0f-7 (oscillation) — this is a wrong market entirely feeding the probability.

**Fix:** Trace which Kalshi market_id is writing to `win_probability_sources["kalshi"]` for this event. Verify it's the correct moneyline market, not a spread/prop. May need tighter market-type filtering in the live polling task.

**Files:** `backend/app/tasks/live_prediction_markets.py`, `backend/app/tasks/prediction_market_matching.py`
**Parallel Safety:** Yellow

### ~~0f-10. Player Props All Showing "0 so far" and "—" Probabilities~~ ✅ FIXED (April 29)

**Root cause (confirmed):** Two stacked bugs: (1) `espn_id` was not persisting due to ORM/Core SQL mixing (gotcha #46), so `box_score_data` never populated. (2) When `box_score_data` is null, the frontend's "done" mode assumed `actual=0` for all stats, showing "0 so far" and "—" everywhere. **Fixes:** espn_id now written via Core SQL update. Frontend falls back to "pre" mode (shows probabilities) when box score is unavailable. Threshold dedup added for same-source duplicates.

### 0f-10b. Cross-Source Player Prop Merging (follow-up)

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

### ~~0f-13. Score Differential y-axis labels should match Win Probability style~~ ✅ SHIPPED (April 28)
Replaced horizontal "leading" labels with vertical rotated team abbreviation + logo matching OddsChart. Chart height h-40→h-48.

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
