# BainLuck TODO

Living checklist. Edit from GitHub web UI, Claude.ai, or Claude Code.
Items added during Italy trip (Apr 3-10) will be picked up in the next Claude Code session.

---

## Pre-Flight (April 2-3)
- [x] Fix quota chart stuck on March → UTC-based dynamic month switching
- [x] Grid health scores visible on admin dashboard
- [x] Eval page link from admin dashboard
- [x] MLB grid: missing Make Playoffs, Division, AL/NL Champion columns
- [x] MLB make_playoffs: 21/30 → 30/30 teams (noise filter + merge fix)
- [x] Capture Masters prototype design feedback
- [x] Verify Heroku auto-deploy works (confirmed working!)
- [x] Fix grid page 20s blank screen (added loading.tsx skeleton)
- [x] Fix invisible chart axes (white-on-white in light mode)
- [x] Fix evolution chart: "Champion" regex match, fallback on <3 outcomes
- [x] Fix sidebar player names invisible (min-w-0 + flex-shrink-0)
- [x] Leaderboard: unified 9-column grid (Score/Today/Thru/Win/Top5/Top10/Top20 always visible)
- [x] Darken header text (gray-400 → gray-500) for readability
- [x] Add position toggle (Top 20 / Top 10 / Top 5 / Win) to evolution chart
- [ ] Smoke-test golf page + golf grid on mobile (phone Safari)
- [ ] Build matching eval admin page (`/admin/matching-eval`) — mobile-friendly

## Golf Cleanup — Phase 1 (Pre-Masters, April 3-8)
**Strategy doc**: `docs/golf-product-strategy.md` — review before building more features

### Data Quality (bugs from smoke test)
- [ ] Fix "Augusta National Invitational" with Aug 29 date — investigate and remove/fix
- [ ] Fix tour classification: Hainan Classic / Hero Indian Open mislabeled as PGA Tour
- [ ] Fix Masters "LIVE" badge showing before tournament starts (April 9-12)
- [ ] Fix categories page chart showing "Yes" (Polymarket binary, not Kalshi player market)
- [ ] Investigate Tiger Woods 41.3% for The Open (inflated?)
- [ ] Add "to win" label on all golf card probabilities ("50% to win" not just "50%")
- [ ] Filter non-winner markets from tournament cards (no "End of Round 1 Leader" etc.)
- [ ] Filter resolved/100% markets from completed tournaments

### UX Fixes
- [ ] Add "show more" to categories page golfer list (currently capped at 40)
- [ ] Fix fullscreen chart blank space (chart height vs container)
- [ ] Categories page evolution chart: use Kalshi player market, not Polymarket binary

## Masters Week (April 9-12)
- [ ] Filter Masters odds to only show invitees (https://www.masters.com/en_US/players/invitees_2026/index.html)
- [ ] Verify live DataGolf polling activates for Masters
- [x] Leaderboard view (approved — use for all tournaments) ✓ Deployed
- [x] Bubble Watch / Cut Line section (approved — worth trying) ✓ Deployed
- [ ] H2H Matchups — Option B (compact) + probability line + round/hole info (needs backend: stop filtering `" vs "` markets in golf.py ~L608)
- [ ] Hole-by-hole probability view (approved — NO Amen Corner callout, needs per-hole data)
- [x] Evolution chart redesign — DataGolf-style interactive highlight with position toggle ✓ Deployed
- [ ] Populate Top 5/10/20 leaderboard columns from Kalshi position markets (pre-tournament)

## Golf Home Redesign — Phase 2 (Post-Trip, April 11+)
See `docs/golf-product-strategy.md` for full spec
- [ ] "This Week" hero card for current/upcoming tournament
- [ ] Majors section (4 cards, always visible)
- [ ] Upcoming tournaments list (PGA Tour default, "All Tours" toggle)
- [ ] Remove inline 40-row odds tables from categories page
- [ ] Remove "Biggest Movers" section (integrate deltas into cards)
- [ ] Redirect `/playoffs/golf` → `/categories/golf`

## Chart Redesign (All Championship Grids)
**Decision: Interactive Highlight (DataGolf-style), Variant A — sidebar dropdown**
Prototype: `docs/designs/evolution-chart-final.html`
- [x] Evaluate 5 chart options (A-E) — Option B: Interactive Highlight chosen
- [x] Evaluate 4 sub-variants of Option B — Variant A (DataGolf sidebar dropdown) chosen
- [x] Final prototype with light mode, round/season markers, fullscreen expand
- [x] Implement evolution chart component in React (`EvolutionChart.tsx` + `EvolutionView.tsx` + `EvolutionLeaderboard.tsx`)
- [x] Sidebar player list with color dots, probabilities, add/remove
- [x] Time range toggle (Full Event / 7 Days / 24 Hours / Today)
- [x] Position toggle (Top 20 / Top 10 / Top 5 / Win) — switches between Kalshi markets
- [x] Fullscreen/expand mode with ESC to exit
- [ ] Add 7D trend + sparkline columns to championship grid table (championship odds column only)
- [ ] Add collision detection for overlapping season markers
- [ ] Golf round markers: R1, R2, Cut, R3, R4
- [ ] MLB season markers: Opening Day, All-Star Break, Trade Deadline
- [ ] NBA season markers: All-Star Break, Trade Deadline, Play-In, Playoffs
- [ ] Default to R1 start when tournament is live (DataGolf behavior)

## Data Quality
- [ ] Golf tournament detail missing dates/venue (`/api/golf/tournaments/{slug}`)
- [ ] ADMIN_SECRET not set on Heroku (admin endpoints currently unprotected — only ADMIN_TOKEN exists)
- [ ] Add audit check for noise filter correctness (quality ratchet)

## DS Veteran Analysis (from `docs/ds-veteran-analysis.md`)
Infrastructure improvements to unlock analytics. Start here:
- [ ] **Priority 1A**: Add `ended_at` column on events
- [ ] **Priority 1B**: Add `final_home_probability` / `final_away_probability` on events
- [ ] **Priority 1C**: Add `event_results` summary (winner, final_margin, is_upset, total_points)
- [ ] **Priority 1D**: Add `season` column on events
- [ ] **Priority 1E**: Denormalize `sport_group` on events
- [ ] **Priority 2F**: Normalize `ei_metadata` from Text to proper columns
- [ ] **Priority 2G**: Standardize all timestamps to TIMESTAMPTZ
- [ ] **Priority 3I**: Per-bookmaker summary before snapshot collapsing
- [ ] **Priority 4K**: Create `v_completed_events` analytical view
- [ ] **First analysis**: "Who's Right?" Brier score source accuracy (data already exists)

## Golf Navigation & Discoverability
- [ ] Fix LeagueChips: Golf chip → `/categories/golf` (not `/playoffs/golf`)
- [ ] Redirect `/playoffs/golf` → `/categories/golf`
- [ ] Golf tournament event cards (show on Feed + category pages) — prototype: `docs/designs/golf-tournament-cards.html`
- [ ] "Live Tournament" card on main feed when tournament is active
- [ ] Ultra-low-data Masters leaderboard page — plain HTML table: rank, name, score, thru, win%, rank change today, probability change today. Instant load, works on any connection.
- [ ] Make `/categories` page live with real category pages showing live + upcoming event cards
- [ ] "My Stuff" league subscriptions — let users pick which leagues appear in their feed
- [ ] Consolidate `/categories/golf` and `/playoffs/golf` → redirect to `/categories/golf`

## Backlog
- [ ] Non-sports category display (politics, entertainment tabs)
- [ ] TV Mode v2 (prototype exists at `docs/tv-mode-prototype.jsx`)
- [ ] "The Market Was Wrong" v2 — AI narrative + personalization
- [ ] "Your Team's Season at a Glance" dashboard
- [ ] Sport-specific EI normalization (different ceilings per sport)
- [ ] Hockey win probability model research
- [ ] Analytics events table (user behavior tracking — prerequisite for ALL product analysis)
- [ ] Matching eval admin page (`/admin/matching-eval`)

## Housekeeping
- [ ] **May 1, 2026**: Delete `frontend/_to-delete/` folder if nothing has broken (dead components, stale pages, one-time scripts moved there April 3)
- [ ] **May 1, 2026**: Delete `docs/archive/` if nothing has been referenced (stale plans, prompts, superseded designs moved there April 3)

## Ideas / Notes from Trip
<!-- Add items here as they come up while traveling -->
<!-- Format: - [ ] description (date noted) -->

