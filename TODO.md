# BainLuck TODO

Living checklist. Edit from GitHub web UI, Claude.ai, or Claude Code.
Items added during Italy trip (Apr 3-10) will be picked up in the next Claude Code session.

---

## Pre-Flight (April 2)
- [x] Fix quota chart stuck on March → UTC-based dynamic month switching
- [x] Grid health scores visible on admin dashboard
- [x] Eval page link from admin dashboard
- [x] MLB grid: missing Make Playoffs, Division, AL/NL Champion columns
- [x] MLB make_playoffs: 21/30 → 30/30 teams (noise filter + merge fix)
- [x] Capture Masters prototype design feedback
- [x] Verify Heroku auto-deploy works (confirmed working!)
- [x] Fix grid page 20s blank screen (added loading.tsx skeleton)
- [x] Fix invisible chart axes (white-on-white in light mode)
- [ ] Smoke-test golf page + golf grid on mobile (phone Safari)
- [ ] Review Masters tournament detail page (`/categories/golf/tournaments/the-masters`)
- [ ] Build matching eval admin page (`/admin/matching-eval`) — mobile-friendly

## Masters Week (April 9-12)
- [ ] Filter Masters odds to only show invitees (https://www.masters.com/en_US/players/invitees_2026/index.html)
- [ ] Verify live DataGolf polling activates for Masters
- [ ] Leaderboard view (approved — use for all tournaments)
- [ ] Bubble Watch / Cut Line section (approved — worth trying)
- [ ] H2H Matchups — Option B (compact) + probability line + round/hole info
- [ ] Hole-by-hole probability view (approved — NO Amen Corner callout)
- [ ] Trend chart redesign (current version is terrible — needs design decision, see chart options below)

## Chart Redesign (All Championship Grids)
Current chart is a weakness. Needs to become a strength. Options to evaluate:
- [ ] **Option A: Bump/Rank Chart** — Y-axis = rank (1st at top), not raw probability. Lines cross when teams swap. Much more readable than bunched-up probability spaghetti. Best for "who's moving up/down"
- [ ] **Option B: Interactive Highlight** — All lines shown muted. Tap/hover a team to spotlight just that line. Default: top 3 highlighted. Legend = toggle buttons. Best for desktop exploration
- [ ] **Option C: Sparklines in Grid** — Kill the standalone chart. Put a tiny 50px sparkline next to each team's probability in the grid table itself. Clean, mobile-friendly, no separate chart needed
- [ ] **Option D: Small Multiples** — Top 6 teams each get their own mini area chart in a 2x3 grid. Clean and readable but uses vertical space
- [ ] **Option E: Horizontal Bars + Sparklines** — Current snapshot as horizontal bar chart (biggest at top) with a 7-day sparkline next to each bar. Clearest on mobile

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

## Golf Page Consolidation
- [ ] Consolidate `/categories/golf` and `/playoffs/golf` — they serve overlapping purposes. `/categories/golf` is the richer experience; `/playoffs/golf` should redirect there. Keep golf in the grid nav tabs but link to `/categories/golf`

## Backlog
- [ ] Non-sports category display (politics, entertainment tabs)
- [ ] TV Mode v2 (prototype exists at `docs/tv-mode-prototype.jsx`)
- [ ] "The Market Was Wrong" v2 — AI narrative + personalization
- [ ] "Your Team's Season at a Glance" dashboard
- [ ] Sport-specific EI normalization (different ceilings per sport)
- [ ] Hockey win probability model research
- [ ] Analytics events table (user behavior tracking — prerequisite for ALL product analysis)
- [ ] Matching eval admin page (`/admin/matching-eval`)

## Ideas / Notes from Trip
<!-- Add items here as they come up while traveling -->
<!-- Format: - [ ] description (date noted) -->

