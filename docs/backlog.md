# Backlog (SINGLE SOURCE OF TRUTH)

All outstanding work items for Bain Luck. This is the canonical list — no other doc should duplicate it.

**How to use this doc:**
- When items ship, move them to `docs/completed-features.md` with a date and brief description
- When new work is discovered (bugs, ideas, follow-ups), add it here in the right section
- When priorities change, reorder within sections
- Mark items with **SHIPPED** and date when done, then move to completed-features on next cleanup pass
- Items from `docs/PRD.md` "Ideas Under Exploration" are longer-horizon; this doc is the active working list

**Related docs:**
- `docs/completed-features.md` — shipped features log
- `docs/PRD.md` — product vision, ideas under exploration, open questions
- `docs/trip-recap-and-next-steps.md` — historical reference (April 2026 trip)
- `docs/golf-product-strategy.md` — golf-specific product strategy

---

## Priority Tiers (last reviewed April 15, 2026)

### Tier 1 — High leverage, do next
1. **Market tier tagging** — Unblocks multiple downstream features. Pure backend, well-scoped.
2. **Roster-based team_id tagging** — Plan already written. Reduces LLM cost, improves personalization.
3. **iOS feature parity audit** — Produce the gap list vs web so we know the scope. Only user right now is Alex, but goal is to get others on TestFlight soon.

### Tier 2 — Important but bigger scope
4. **B1: Site navigation hierarchy** — URL restructure. Needs golf strategy decisions first, then big frontend+backend effort.
5. **Entity pages** (`/[sport]/[league]/[team]`) — Depends on B1 for URL structure. SEO upside.
6. **Golf data quality pass** — 7 open bugs. Individually small, collectively meaningful.
7. **Live tournament polling** — High impact during tournaments but episodic.

### Tier 3 — Valuable but can wait
8. **Evolution chart: combined probability** — Data pipeline question, needs design thinking.
9. **Line Movement Explainer v2** — Disabled, not hurting anything. Needs a rethink.
10. **DS/Analytics infrastructure** — Enables future analysis but no user-facing impact. "Who's Right?" Brier score analysis is a "when I get to it" item.
11. **B3: Eval page v2** — Nice-to-have admin tool improvement.
12. **Freshness-weighted blending** — Waiting on more eval data.

### Tier 4 — Someday / Maybe
13. Everything in the Someday / Maybe and Ideas Under Exploration sections below.

---

## Architecture Initiatives

### B1: Site Navigation Hierarchy — NOT STARTED
Move from `/playoffs/[sport]` to `/[sport]/[league]` hierarchy. Team sports get grid+games+futures tabs. Individual sports (golf, tennis) get tour hub -> tournament detail. Sport hub pages list sub-leagues.

**Key decisions still needed:**
- Default to PGA Tour only? (Recommendation: yes, "All Tours" toggle)
- Golf home hierarchy? (Recommendation: hero -> majors -> upcoming -> completed)
- **Don't kill `/playoffs/golf` yet** — wait until golf pages are really humming, then clean up. Keep checking in on this.

### B2: League Context Service — SHIPPED April 14-15
`LeagueContextService` in `services/league_context.py`. Redis-cached (5-min TTL), dynamic columns from `league_configs.py`. Powers Playoff Path card in Related Futures + team-progression endpoint. `SPORT_GROUPS` + `get_league_for_sport_key()` added to `league_configs.py`.

**Remaining B2 follow-ups:**
- Extract `market_discovery.py` + `team_resolution.py` from `playoffs.py` (cleanup, not blocking)
- Orphaned event detection

### B3: Eval Page v2 — NOT STARTED (Tier 3)
Group by market (not per-team). Three card types: market-column assignment, source disagreement, interesting futures. Decisions flow downstream to grid builder + feed ranking. Gamification phase 2 (points, levels, leaderboard).

### B4: Trade Volume — SHIPPED April 14-15
All 3 phases: storage (5 columns on `FuturesMarket`), feed ranking (volume scoring in `futures_highlights.py`), grid confidence (volume-weighted merging in `_merge_probabilities()`, enhanced Kalshi noise detection). Internal signal only — NEVER user-facing (see `memory/feedback_no_gambling_display.md`).

---

## Tier 1: HIGH-PRIORITY Follow-ups

### Related Futures Performance + Completed Event Props
Related Futures was timing out (fixed April 15 — tier-aware loading + recency filter). Current workaround: completed events skip roster player ILIKE patterns for speed. **This is a product sacrifice** — we WANT to show player props for completed games ("market expected 2.5 hits, Judge went 3-for-4"). Need to make the query fast enough to include player props for completed events. Options: pre-compute team→outcome links via `team_id` backfill (see roster-based tagging below), use GIN index on outcome names, or denormalize player props onto events.

Also: design slick "expected vs actual" cards for completed game props — this is a compelling content type that differentiates BainLuck.

### Roster-Based team_id Tagging for Player Awards
Detailed plan at `.claude/plans/prancy-seeking-ritchie.md`. Add roster matching step to `team_linking` backfill — match player names against `Team.roster_players` before expensive LLM fallback. Reduces OpenAI cost, improves My Stuff and Related Futures for player awards (MVP, ROY, DPOY).

### iOS Feature Parity Audit
iOS app is behind web. Only user is Alex right now, but goal is to get others on TestFlight soon. First step: produce a gap list comparing web pages/features vs iOS views. Then prioritize which gaps to close before wider TestFlight distribution.

---

## Tier 2: Golf

### Data Quality (still open)
- Tour misclassification (Hainan = Asian Tour, not PGA Tour). DataGolf provides correct `tour` field.
- "Augusta National Invitational" ghost tournament
- Categories page chart showing "Yes" (Polymarket binary, not Kalshi player market)
- "To win" label on card probabilities
- H2H matchups on tournament detail (stop filtering `" vs "` markets in `golf.py` ~L608)
- Make Cut column on tournament detail page
- ATP Monte-Carlo "Masters" markets leaking into golf data

### Features
- **Golf round markers on charts** — R1/R2/R3/R4 start times as vertical markers. Minimum: midnight each tournament day. Ideal: actual start-of-play.
- **Golf LIVE badge fix** — Date-based validation added April 14, but still false-positive edge cases for completed tournaments.
- **Live tournament Kalshi/Polymarket polling** — Futures polls run every 4h (Kalshi) / 1h (Polymarket), way too slow for live golf tournaments. Need a "live tournament" polling mode: detect active tournament via DataGolf leaderboard, poll its Kalshi/Polymarket markets every 5-10 min during play. Same pattern could apply to any high-interest futures (NBA playoffs, Super Bowl week).
- **Golf home redesign** — Hero card, majors section, tour filtering
- **Mobile smoke test** — Phone Safari QA still pending

### Strategy Decisions (need Alex's call)
- Default to PGA Tour only? (Recommendation: yes, "All Tours" toggle)
- Golf home hierarchy? (Recommendation: hero -> majors -> upcoming -> completed)
- Props on cards vs detail page only?
- Completed tournaments: final results vs pre-tournament odds?

---

## Tier 2: Entity Pages & Navigation

### Entity Pages: `/[sport]/[league]/[team]`
e.g., `/basketball/nba/celtics` aggregates all content for a team: games, futures, related markets, championship timeline. Good for SEO + My Stuff integration. Team names in championship grid should link here. Depends on B1 for URL structure.

### Sport/League Pages
- Win totals column in championship grid
- Awards/props cards on league pages (MVP, DPOY, ROY) — blocked on market tier tagging
- Season state indicators on evolution chart (Trade Deadline, All-Star Break, etc.)
- Team landing pages (clickable from grid team names) — see Entity Pages above
- SEO: sitemap, structured data for `/sport/*` routes

---

## Tier 3: Can Wait

### Evolution Chart: Combined Probability Trend
Chart currently shows single-source data; grid shows merged/grouped. Chart should show merged probability trend. Requires time-series computation of aggregate — data pipeline question.

### Data Quality / Blending
- **Freshness-weighted source blending** — Stale prediction market prices weighted equally with fresh model data. Need time-decay weighting. Design notes in `.claude/projects/-Users-bain-bainluck/memory/project_freshness_blending.md`. Decision: gather more eval data before implementing.
- Sport-specific EI normalization (different ceilings per sport) — PRD item #28
- "Connecticut" vs "UConn Huskies" don't merge (different naming, DB lookup miss)

### DS/Analytics Infrastructure
- Add `ended_at`, `final_home_probability`, `event_results`, `season` columns to events
- Denormalize `sport_group` on events
- Normalize `ei_metadata` from Text to proper columns
- Create `v_completed_events` analytical view
- First analysis: "Who's Right?" Brier score source accuracy

### Features
- **Line Movement Explainer v2** — Current version disabled (April 15). Only stated the obvious ("Team X won, odds went up"). Needs: key moment identification, causal analysis, context from scoring plays. Revamp before re-enabling.
- **TV Mode v2** — Design complete, interactive prototype at `docs/tv-mode-prototype.jsx`. Plan at `docs/tv-mode-plan.md`. Fullscreen second-screen experience at `/tv`.
- **"The Market Was Wrong" v2** — AI narrative generation + personalization.
- **Additional Win Prob Sources** — MoneyPuck for NHL. Infrastructure ready (stub configured).
- **Related Futures Phase 5** — Bidirectional linking: futures detail pages show relevant events.
- **Non-Sports Categories** — Audit existing markets (politics, entertainment, crypto, weather). Politics timelines.
- **iOS App Next Steps** (beyond parity) — App Store submission, widgets, background refresh, share extension.

---

## Ideas Under Exploration (from PRD)

These need design questions answered before planning. See `docs/PRD.md` for full details.

- **Bespoke category landing pages** — Basketball, football, soccer, politics, entertainment (golf shipped)
- **Golf live scores integration** — StatPal live scores overlaid on odds data during tournaments
- **"What Are the Odds?" game** — Probability guessing game as retention/viral driver
- **Insight Arena** — Admin LLM training via A/B preference selection on generated insights
- **Probability Comparisons** ("Comparable Odds") — PRD Phase 16
- **Event Similarity Scores** — PRD Phase 17
- **Team Insights** (LLM-Powered Personalized Feed) — PRD Phase 19

---

## Someday / Maybe

Ideas worth capturing but no timeline or commitment yet.

- **Apple Watch app** — Mock up what a BainLuck watchOS experience could look like. Glanceable live probabilities, complication for favorite team odds, haptic alerts on big swings.
- **Apple TV app** — Mock up a tvOS experience. Natural fit for TV Mode concept — full-screen probability dashboard during live games.
- **Weather visualization** — Kalshi/Polymarket have tons of fragmented weather markets (city temps, rainfall, snowfall, hurricane paths, etc.). Individually they're boring. The BainLuck magic appears when we group and visualize TONS of markets at once in a way that's easily understood — imagine a weather map colored by probability, or a city-by-city temperature forecast dashboard built entirely from prediction market data. Low priority but high ceiling.
- **Non-sports market audit** — Systematic review of all non-sports markets currently flowing through (politics, entertainment, crypto, weather, etc.) to identify which categories have enough market density to build compelling grouped visualizations.

---

## Housekeeping

- **May 1, 2026**: Delete `frontend/_to-delete/` if nothing broke
- **May 1, 2026**: Delete `docs/archive/` if nothing referenced
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches (old feature/claude branches from Jan-Mar 2026)
