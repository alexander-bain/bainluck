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
- [ ] Smoke-test golf page + golf grid on mobile (phone Safari)
- [ ] Review Masters tournament detail page (`/categories/golf/tournaments/the-masters`)
- [ ] Build matching eval admin page (`/admin/matching-eval`) — mobile-friendly

## Masters Week (April 9-12)
- [ ] Verify live DataGolf polling activates for Masters
- [ ] Leaderboard view (approved — use for all tournaments)
- [ ] Bubble Watch / Cut Line section (approved — worth trying)
- [ ] H2H Matchups — Option B (compact) + probability line + round/hole info
- [ ] Hole-by-hole probability view (approved — NO Amen Corner callout)
- [ ] Trend chart redesign (current version is terrible — needs mocks first)

## Data Quality
- [ ] Golf tournament detail missing dates/venue (`/api/golf/tournaments/{slug}`)
- [ ] ADMIN_SECRET not set on Heroku (admin endpoints currently unprotected — only ADMIN_TOKEN exists)
- [ ] Kalshi noise filter: update MEMORY.md now that plausibility check is implemented
- [ ] Add audit check for noise filter correctness (quality ratchet)

## Backlog
- [ ] Non-sports category display (politics, entertainment tabs)
- [ ] TV Mode v2 (prototype exists at `docs/tv-mode-prototype.jsx`)
- [ ] "The Market Was Wrong" v2 — AI narrative + personalization
- [ ] "Your Team's Season at a Glance" dashboard
- [ ] Sport-specific EI normalization (different ceilings per sport)
- [ ] Hockey win probability model research

## Ideas / Notes from Trip
<!-- Add items here as they come up while traveling -->
<!-- Format: - [ ] description (date noted) -->

