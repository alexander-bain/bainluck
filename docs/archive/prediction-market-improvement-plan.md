# Prediction Market & Related Futures Improvement Plan

**Date:** 2026-03-30
**Status:** Draft
**Trigger:** Feedback from Celtics-Hornets game (event 12080345)

---

## Problem Statement

The related futures section on event detail pages is overwhelming and poorly organized. A single NBA game (Celtics-Hornets) returns **176 raw futures items** displayed as a flat list. The goal is NOT to show less — it's to **group, match, and visualize** all 176 items so skillfully that it feels like ~15 smart cards, each expandable to full detail.

Key issues:

1. **No cross-source merging** — "NBA Champion" appears 3x (Odds API + Polymarket + Kalshi) as separate rows instead of one merged row with source breakdown
2. **No grouping** — 10+ NBA Finals Matchup rows shown individually instead of as one expandable card
3. **Flat visual hierarchy** — a 0.05% longshot competes visually with a 36% Conference Champion probability
4. **Missing game-level context** — opening odds blank, no scoring trend, "Since Start" not clickable
5. **Existing infrastructure underutilized** — championship grid already solves cross-source matching

### Design Philosophy

**Every data point stays accessible.** The hierarchy is:
1. **Top level**: ~15 grouped cards with summary info (Playoff Path, Finals Matchups, Awards, Trades, etc.)
2. **Expanded level**: Full detail within each card — every source, every outcome, every threshold
3. **Cross-source merge**: Show aggregated probability prominently, tap to see per-source breakdown

Nothing is hidden or deleted — it's organized with clear visual hierarchy so the most meaningful items are prominent and the deep detail is one tap away.

---

## Part A: Event Detail Page Fixes (Quick Wins)

### A1. Opening Odds Fallback (Hero Card Shows "—%–—%")
**Problem:** When Odds API quota runs out, `opening_home_probability` is null, hero shows blanks.
**Root cause:** `page.tsx` lines 601-614 only falls back to current betting odds, not alternative sources.
**Fix:** Fallback cascade: Odds API opening → first win_prob_snapshot → ESPN pre-game → Kalshi/Polymarket pre-game
**Files:** `frontend/app/events/[id]/page.tsx` (lines 600-652), `backend/app/routes/events.py`
**Effort:** Small

### A2. "Since Start" Toggle Not Clickable on Completed Games
**Problem:** The time range pill is visually present but not interactive for completed games.
**Fix:** Enable click handler regardless of game status.
**Files:** `frontend/components/OddsChart.tsx`
**Effort:** Trivial

### A3. Chart Start Time Before Game Start
**Problem:** Chart starts at 1:05 PM but game started at 3 PM — pre-game polling data shown.
**Fix:** Default to "Since Start" view for completed games, or trim pre-game noise.
**Files:** `frontend/components/OddsChart.tsx`
**Effort:** Small

### A4. Missing Game State Indicators in Chart
**Problem:** No quarter markers, no scoring play dots visible on the probability chart.
**Fix:** Verify scoring play data is being passed to OddsChart; check if ESPN snapshots include period boundaries.
**Files:** `frontend/components/OddsChart.tsx`, `backend/app/routes/events.py` (history endpoint)
**Effort:** Medium

### A5. Scoring Trend Chart Missing
**Problem:** No score differential visualization. ScoreDifferentialChart exists but may not be receiving data.
**Fix:** Verify StatPal score snapshots are being captured during games. Consider adding Kalshi spread data.
**Files:** `frontend/components/ScoreDifferentialChart.tsx`, `backend/app/routes/events.py`
**Effort:** Medium

---

## Part B: Related Futures — Cross-Source Dedup

### Current State
- `merge_group` field exists on outcomes (e.g., `nba_champion`, `make_playoffs`, `win_total`)
- Championship grid (`/api/playoffs/nba`) already does cross-source matching via `merge_group`
- Related futures endpoint does NOT use `merge_group` for dedup — returns raw items

### B1. Server-Side Cross-Source Merging
**Problem:** 14+ concepts appear as separate Kalshi vs Polymarket vs Odds API rows.
**Solution:** In `routes/events.py` related-futures endpoint, group outcomes by `(merge_group, outcome_name_normalized)`, then:
- Pick best probability (weighted by source reliability or averaged)
- Show source count badge ("3 sources")
- Expose individual source breakdown on click/expand

**Example merge:**
| Before (3 rows) | After (1 row) |
|------------------|---------------|
| Polymarket: NBA Champion = 11.35% | NBA Champion = 13.5% |
| Odds API: NBA Champion = 13.53% | (3 sources: Odds API, Kalshi, Polymarket) |
| Kalshi: NBA Champion = 13.5% | |

**Files:** `backend/app/routes/events.py` (related-futures endpoint)
**Effort:** Medium

### B2. Matching Quality Metric
**Problem:** No way to measure how well we're pairing obvious cross-source duplicates.
**Solution:** Add an admin endpoint that:
1. Finds all outcomes within same `merge_group` + similar outcome name across sources
2. Counts paired vs unpaired
3. Reports pairing % by sport and merge_group
4. Add to admin dashboard

**Files:** `backend/app/routes/admin.py`, `frontend/app/admin/page.tsx`
**Effort:** Medium

---

## Part C: Related Futures — Smart Grouping

### Current State
- `display_category` field exists (playoff_path, conference, award, season_stat, trade, novelty)
- `merge_group` exists (nba_champion, make_playoffs, win_total, 3pm_leader, etc.)
- Frontend `RelatedFutures.tsx` has tier classification but renders items individually

### C1. Playoff Progression Card
**Problem:** "Make Playoffs", "Eastern Conference Champion", "NBA Champion" shown as 3+ separate items.
**Solution:** Detect sequential playoff stages for the same team and render as a single progression card:

```
Celtics Playoff Path
  Make Playoffs     100%  ████████████████████
  Eastern Conf       36%  ████████
  NBA Champion       13%  ███
```

This is exactly what the championship grid already computes. Reuse `league_configs.py` column definitions.

**Files:** `backend/app/routes/events.py`, `frontend/components/RelatedFutures.tsx`
**Effort:** Medium-Large

### C2. Matchup Markets Grid
**Problem:** 10+ "NBA Finals Matchup" rows shown individually. Labels don't show which matchup.
**Solution:** Group all outcomes from same market into a single expandable card:

```
NBA Finals Matchup (involving Celtics)
  Houston vs Boston       20%
  Oklahoma City vs Boston 17.5%
  San Antonio vs Boston   15.5%
  Denver vs Boston        12%
  ... +6 more
```

**Key fix needed:** Outcome names are already there (`outcome_name` = "Houston vs Boston") but the frontend card doesn't display them prominently.

**Files:** `frontend/components/RelatedFutures.tsx` (GameMarketsGrid component, lines 625-700)
**Effort:** Medium

### C3. Win Total Consolidation
**Problem:** 8+ rows showing "Charlotte Win Total: 5+ wins" through "45+ wins" (most at 0.995).
**Solution:** Group all thresholds into one card, show the "interesting" threshold (the one nearest 50%):

```
Charlotte Win Total
  45+ wins: 22.5%  (this is the interesting line)
  Current: 27 wins with 8 games left
```

Filter out thresholds that are effectively resolved (>0.99 or <0.01).

**Files:** `backend/app/routes/events.py`, `frontend/components/RelatedFutures.tsx`
**Effort:** Medium

### C4. Trade Watch Consolidation
**Problem:** 7+ individual trade destination markets shown separately, unclear how to read.
**Solution:** Group all "X Trade Destination = [Team]" into one card per team:

```
Trade Watch (to Celtics)
  Josh Giddey       12%
  Julius Randle      12%
  Ja Morant          11%
  Draymond Green     11%
  James Harden        7%
```

Add clarity: "Probability of being traded TO the Celtics"

**Files:** `frontend/components/RelatedFutures.tsx`
**Effort:** Small-Medium

### C5. Award & Statistical Leader Consolidation
**Problem:** MVP, MIP, ROY, 6MOY, Clutch Player, All-NBA, All-Defensive, plus PPG/APG/RPG/3PM/SPG/BPG leaders — all shown as individual rows.
**Solution:** Group into two cards:
1. **Awards** — one card showing team players' chances across all awards
2. **Statistical Leaders** — one card showing team players' chances at league leader categories

**Files:** `frontend/components/RelatedFutures.tsx`
**Effort:** Medium

### C6. Visual Hierarchy & Sort Order
**Problem:** A 0.05% longshot competes visually with a 36% Conference Champion. Flat list has no hierarchy.
**Solution:** Sort and style by relevance within each group:
- Within groups, sort by probability (most interesting first)
- Items near 50% (high uncertainty) get visual prominence
- Items at extremes (>0.99, <0.01) render in muted/compact style but remain visible
- Resolved items (prob = 1.0 or 0.0) show with a "locked" badge
- Every item stays accessible — nothing is deleted, just organized

**Files:** `frontend/components/RelatedFutures.tsx`, `backend/app/routes/events.py`
**Effort:** Small-Medium

---

## Part D: Fully Leveraging Prediction Markets

### Current Ingestion
- **Kalshi:** Fetches ALL open events (categories=None). 40+ ticker prefixes mapped.
  - Game-level markets detected via ticker prefix (KXNBAGAME, KXNFLGAME, etc.)
  - Futures/awards/props/novelty all ingested as FuturesMarket records
  - Only crypto is filtered out
- **Polymarket:** Fetches via Gamma API with sports tag filtering
  - NegRisk multi-outcome market support
  - Price history backfill via CLOB API
- **Both:** All binary outcomes stored with probabilities

### D1. Audit: What Kalshi Basketball Categories Exist

Based on the Celtics-Hornets data, Kalshi has these NBA market types:
| Category | Example | Currently Grouped? |
|----------|---------|-------------------|
| Championship | NBA Champion | Yes (merge_group) |
| Conference Champion | Eastern Conference Champion | Yes |
| Division Winner | Southeast Division Winner | Yes |
| Make Playoffs | NBA Playoff Qualifiers | Yes |
| Play-In | Eastern Conference Play-In | Yes |
| #1 Seed | Eastern Conference #1 Seed | Yes |
| Finals Matchup | NBA Finals Matchup | Partially (merge_group=None!) |
| Conference Finals Matchup | Eastern Conference Finals Matchup | Partially (merge_group exists) |
| Conference Finals MVP | Eastern Conf Finals MVP | Yes |
| Win Total | Boston Win Total: 55+ wins | Yes |
| Awards | MVP, MIP, ROY, 6MOY, DPOY, Clutch Player, Finals MVP | Yes |
| All-NBA/Defense | All-NBA 1st/2nd/3rd, All-Defensive 1st/2nd | Yes |
| Statistical Leaders | PPG, APG, RPG, 3PM, SPG, BPG Leader | Yes |
| Best/Worst Record | Best Record, Worst Record | Yes |
| Trade Destination | Zion Williamson Trade Destination | No (merge_group=None) |
| Novelty | NBA 2K Cover, Kon Knueppel 207th three pointer | No |
| Game Markets | Spread, Total, Moneyline | Via prediction_market_matching |

**Key finding:** NBA Finals Matchup has `merge_group=None` — this is why 10+ matchup rows aren't being grouped. Same for Trade Destinations.

### D2. Missing merge_group Assignments
**Action:** Fix `merge_group` assignment in `tasks/kalshi.py` for:
- Finals Matchup → `merge_group = "nba_finals_matchup"`
- Trade Destinations → `merge_group = "trade_{player_name_normalized}"`
- Novelty items → `merge_group = "novelty_{topic}"`

### D3. Game-Level Props from Prediction Markets
**Opportunity:** Kalshi has game-level props (spreads, 1st half winner, player props) that could enrich the event detail page beyond just moneyline.

Currently, `prediction_market_matching.py` only extracts moneyline (home/away win probability). We could also surface:
- **Spread markets** → "Kalshi thinks Celtics -6.5"
- **Total markets** → "Over/Under 221.5"
- **1st half winner** → separate probability
- **Player props** → "Jaylen Brown 30+ points: 15%"

This would require a new section on the event detail page: "Prediction Market Props"

### D4. Cross-Sport Audit (Future Work)
Repeat the analysis above for:
- **NFL** — game props, Super Bowl futures, MVP, draft
- **MLB** — game props, World Series, Cy Young, HR leader
- **NHL** — game props, Stanley Cup, Hart Trophy
- **Soccer** — match props, Champions League, Golden Boot
- **Golf** — tournament winner, matchup markets (DataGolf already handles this well)

---

## Implementation Priority

| Phase | Items | Impact | Effort |
|-------|-------|--------|--------|
| **1: Quick Wins** | A1, A2, A3, C6 | Fix embarrassing UX gaps | 1-2 sessions |
| **2: Core Grouping** | B1, C1, C2, D2 | Transform related futures from noise to signal | 2-3 sessions |
| **3: Rich Grouping** | C3, C4, C5, A4, A5 | Polish the grouped cards | 2-3 sessions |
| **4: Measurement** | B2 | Track matching quality over time | 1 session |
| **5: Game Props** | D3 | New category of content | 2-3 sessions |
| **6: Cross-Sport** | D4 | Extend to all sports | Ongoing |

---

## Design Principles

1. **176 items → 15 groups → expand to see all 176** — Nothing is deleted. Smart grouping + visual hierarchy makes it feel organized, not overwhelming.
2. **Cross-source = credibility** — "3 sources agree: 13.5%" is more compelling than showing 3 separate rows. Show merged probability prominently, per-source breakdown on expand.
3. **Reuse championship grid logic** — Don't reinvent matching. The grid already solves cross-source dedup.
4. **Playoff progression is the hero** — The path from "Make Playoffs" to "Win Championship" is the most compelling visualization for any team sport.
5. **Visual hierarchy, not filtering** — Extreme probabilities (>0.99, <0.01) render compact/muted but remain accessible. Sort by "interestingness" (proximity to 50%, recent movement).
6. **Labels matter** — "Zion Williamson Trade Destination = 10%" needs to clearly say "10% chance he's traded TO the Celtics"
