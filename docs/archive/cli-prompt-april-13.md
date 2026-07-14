# CLI Prompt — Post-Trip Cleanup & Planning (April 13, 2026)

## How to use

1. Open Claude Code CLI in the `bainluck/` directory
2. Make sure you've run `git pull origin master` first
3. Type `/plan` to enter plan mode
4. Paste the prompt below

---

## The Prompt

```
I just got back from a week traveling and need to do two things in this session:

**Part A: Execute quick cleanups** (things you can just do)
**Part B: Draft architectural plans** (things I need to think through before building)

Start with Part B (planning) since we're in plan mode. I'll switch you out of plan mode for Part A after I've reviewed your proposals.

---

## PART B: PLANS NEEDED (do these first, in plan mode)

### B1: Site Navigation Architecture

The site currently has three different page types serving overlapping purposes:
- `/playoffs/[sport]` — Championship grid with multi-column progression tables (874 lines, most feature-rich)
- `/categories/[slug]` — Mixed events + futures feed by sport/topic (232 lines, simpler)
- `/sports/[key]` — Simple upcoming events list (122 lines, barely used, not linked from main nav)

The homepage LeagueChips link to `/playoffs/{sport}`. The footer links to `/playoffs`. The `/categories` and `/sports` pages are effectively undiscoverable unless you type the URL directly.

**The problem:** "Playoffs" is a bad name (golf doesn't have playoffs, soccer doesn't have playoffs in the American sense). Redirecting `/playoffs` to `/categories` doesn't work because the pages show fundamentally different data — the championship grid is the most valuable thing we've built, and `/categories` doesn't show it. And `/sports` is the best URL but currently the weakest page.

**What I want:** `/sport/[key]` (or `/sports/[key]`) should be THE canonical league page. It should combine the best of all three current pages: the championship grid data, the event feed, the futures markets. One page per sport that has everything.

**Constraints:**
- The championship grid code in `/playoffs/[sport]/page.tsx` is 874 lines of battle-tested logic. Don't throw it away — extract and reuse.
- `/categories/[slug]` also handles non-sports categories (politics, entertainment, etc.) which don't have grids. Those still need a home.
- `league_configs.py` currently only powers the `/playoffs` route. Its market matching rules, column definitions, and team groupings should be reusable on the unified sport page AND on event detail pages (Related Futures / "Bigger Picture").
- The LeagueChips on the homepage need to point somewhere good.
- Mobile matters — the championship grid table is wide. The unified page needs to work on phones.

**Please propose:**
1. The URL structure and page hierarchy
2. What each page renders (wireframe-level description)
3. How to migrate without breaking existing pages (redirects from /playoffs/, /categories/)
4. How league_configs.py data can power multiple surfaces (sport page, event detail related futures, feed cards)
5. What happens to non-sports categories

### B2: Shared Infrastructure — League Context Everywhere

Events often appear "orphaned" on detail pages — missing game state, no period/clock indicators, no related futures, no "Bigger Picture" context. This happens because:
- ESPN enrichment fails (event.espn_id is NULL, so no period/clock/score updates)
- Team identity resolution fails (event.home_team_id or away_team_id is NULL, so related futures can't match by team)
- The related-futures endpoint uses name-based matching against FuturesOutcome.name, which is fragile

Meanwhile, the championship grid has high-quality market matching rules defined in `league_configs.py` (MarketMatchingRule with name_patterns, canonical_prefix, tier), but this knowledge is locked inside the playoffs route and not used anywhere else.

**What I want:** A shared "league context" layer that:
- Knows the schedule for each league (what games are happening when)
- Knows where each team stands in the playoff picture (from the grid data)
- Can enrich any event detail page with: "This team is 65% to make playoffs, 12% to win the championship"
- Uses the same matching rules that power the grids to find related futures on event pages
- Identifies orphaned events (no ESPN match, no team IDs) and flags them for investigation

**Please propose:**
1. What "league context" looks like as a data model or service
2. How to extract the matching logic from league_configs.py + playoffs.py into a reusable service
3. How event detail pages would consume this (API shape, frontend integration)
4. How to detect and report orphaned events systematically
5. Whether this should be computed at query time, cached in Redis, or denormalized into the events table

### B3: Eval Page v2

The current eval page (`/admin/eval`) has issues:
- **Repetition**: You can get functionally the same question 30 times in a row because dedup is by exact `{league}:{team}:{column}` key, but many cards are asking the same conceptual question (e.g., "is this Kalshi market about the NBA championship?" appearing for every team)
- **Missing context**: When asked "should these be merged?", there's often not enough info to decide. Need to see: the actual market names from each source, what other markets exist for this team, and maybe a link to the source
- **Unclear actions**: The difference between 🚫 ("never show") and "skip" is ambiguous. When should I use which?
- **No feedback loop**: Eval decisions are stored in `matching_overrides` table but only used for dedup (preventing re-display). They're NOT used to improve matching, ranking, or display logic. The ROI of answering questions is unclear.
- **No prioritization**: Cards are sorted by disagreement spread, which is reasonable, but doesn't account for impact (a 30pp disagreement on the Lakers matters more than on a random esports team)

**What I want:** An eval page that:
- Asks me the HIGHEST-VALUE questions first (by league tier × disagreement × volume)
- Groups related questions (all NBA championship matches together, not interleaved with random sports)
- Shows enough context that I can always make a confident decision
- Clearly explains what each action does and how my answer will be used
- Actually USES my answers downstream (improve matching confidence, surface/hide markets, adjust grid display)
- Has a progress indicator ("you've reviewed 45 of 120 pending items, 23 corrections applied")

**Please propose:**
1. How to restructure the question selection and ordering
2. What context each card needs to show
3. How eval decisions should flow back into the matching/ranking system
4. A clear action vocabulary (what does each button do?)
5. How to measure ROI of eval time

### B4: Trade Volume Integration

We currently fetch `volume`, `volume_24h`, and `open_interest` from Kalshi, and `volume`, `volume_24h`, `liquidity` from Polymarket — but we don't store any of it. It's parsed in the API service models and then discarded.

**What I want to understand:**
- Should volume be stored? If so, where — on FuturesMarket? FuturesOutcome? A new snapshot table?
- How could volume improve matching confidence? (High-volume markets are more likely to be "real" and less likely to be noise)
- How could volume improve feed ranking? (High-volume = more public interest = more interesting to show)
- How could volume improve the championship grid? (Low-volume markets might explain some of the noise we filter with the 0.45-0.65 Kalshi filter)
- Should we show volume to users? ("$2.3M traded" as a signal of market confidence)
- What's the simplest useful first step?

**Please propose:**
1. Storage schema
2. Which downstream systems benefit and how
3. Implementation priority (what to do first)

---

## PART A: QUICK CLEANUPS (do these after plan review)

Once I've reviewed your Part B proposals and we switch out of plan mode, execute these:

### A1: Quota Optimization (re-implement)
During the trip, we designed but didn't deploy API quota savings. Implement in `backend/app/tasks/odds_polling.py` and `backend/app/tasks/__init__.py`:

1. **Tier-aware API params in `_poll_odds_for_sport()`:**
   - Live games: full params (h2h,spreads,totals × us,us2) — no change
   - "Soon" games (0-2h pre-game): full markets, single region (h2h,spreads,totals × us only)
   - "Later" games (2-6h pre-game): minimal params (h2h × us only)

2. **Per-sport adaptive slowdown:**
   - Track unchanged-odds hash counter in Redis per sport key (`bainluck:unchanged_count:{sport_key}`)
   - After 3+ consecutive unchanged polls: stretch to 5min interval
   - After 6+ consecutive unchanged: stretch to 10min interval
   - Only for non-live tiers; live games always poll at full speed
   - Reset counter instantly when odds hash changes

3. **Futures polling frequency:**
   - Change `poll_futures` beat schedule from `crontab(minute=30)` (hourly) to `crontab(minute=30, hour="*/2")` (every 2 hours)

Run the test suite after to make sure nothing breaks.

### A2: Update CLAUDE.md
After completing A1, update the relevant sections of CLAUDE.md to reflect:
- The quota optimization changes
- The dual worker infrastructure (already deployed but CLAUDE.md may not reflect it)
- Archive the travel-related docs (travel-guide.md and italy-trip-masters-plan.md now point to trip-recap-and-next-steps.md)
- Add any new gotchas discovered

### A3: Golf data quality check
The Masters just finished (April 9-12). Query the production API to check:
- Did DataGolf live polling work during the Masters? (`curl "https://api.bainluck.com/api/golf/tournaments/masters"`)
- Is the Masters showing as completed with a winner?
- Does the evolution chart have data from all 4 rounds?
- Are there stale "LIVE" badges on any golf tournaments?

Report findings but don't fix anything yet — just document what you find.
```

---

## Notes for Alex

- After pasting this in plan mode, Claude will produce proposals for B1-B4 without touching any code
- Review the proposals, push back on anything that feels wrong, then say "OK, now do Part A" (or `/exitplan` to leave plan mode)
- The B1 navigation proposal is the most important one — make sure it accounts for the fact that `/playoffs` grid code is your most valuable frontend asset and shouldn't be rewritten from scratch
- For B3 (eval), the key insight Claude needs to internalize: eval decisions currently go into `matching_overrides` but are ONLY used for dedup. They need to actually influence matching confidence scores, grid display, and feed ranking.
- For B4 (volume), the lowest-hanging fruit is probably just adding `volume` and `volume_24h` columns to `FuturesMarket` and storing them during the existing polling tasks — zero new API calls needed
