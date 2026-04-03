# BainLuck Travel Guide — Italy + Masters Week

**April 3-10, 2026** | Phone + iPad only | All deploys work from GitHub web UI

---

## Quick Links (tap-friendly)

| What | Link |
|------|------|
| Golf home | [bainluck.com/categories/golf](https://bainluck.com/categories/golf) |
| Masters detail | [bainluck.com/categories/golf/tournaments/masters](https://bainluck.com/categories/golf/tournaments/masters) |
| Golf grid | [bainluck.com/playoffs/golf](https://bainluck.com/playoffs/golf) |
| Eval page | [bainluck.com/admin/eval](https://bainluck.com/admin/eval) |
| Admin dashboard | [bainluck.com/admin](https://bainluck.com/admin) |
| Health check | [api.bainluck.com/health](https://api.bainluck.com/health) |
| GitHub repo | [github.com/alexander-bain/bainluck](https://github.com/alexander-bain/bainluck) |
| Claude.ai | [claude.ai](https://claude.ai) |

---

## Masters Schedule

| Date | What | What to check on BainLuck |
|------|------|--------------------------|
| Apr 7-8 (Mon-Tue) | Practice rounds | Pre-tournament odds, evolution chart building |
| **Apr 9 (Thu)** | **Round 1** | Masters as current event, live DataGolf probs, leaderboard |
| **Apr 10 (Fri)** | **Round 2 + Cut** | Cut line drama, bubble watch, eliminated players |
| Apr 11 (Sat) | Round 3 | Big movers, odds shifts |
| Apr 12 (Sun) | Final Round | Live win probability, champion crowned |

---

## Daily Routine

### Morning (15 min, with coffee)
1. Open [bainluck.com/categories/golf](https://bainluck.com/categories/golf) — check overnight updates
2. If Masters is live: check leaderboard, movers, evolution chart
3. Note any issues in Apple Notes or a Google Doc

### During Masters rounds (passive, while watching)
1. Keep BainLuck open alongside TV/streaming
2. Compare what you see vs broadcast commentary
3. Note when probabilities feel right, wrong, or delayed
4. Do a few eval page reviews during breaks: [bainluck.com/admin/eval](https://bainluck.com/admin/eval) → Golf tab

### Evening (optional, 20 min)
1. Browse [kalshi.com](https://kalshi.com) and [polymarket.com](https://polymarket.com) for interesting markets
2. If inspired: use [claude.ai](https://claude.ai) to draft a change → commit via GitHub web

---

## What to Watch For (QA Checklist)

During each Masters round, check these:

- [ ] Does golf page show Masters as current event with "LIVE" badge?
- [ ] Are golfer probabilities reasonable? (Scheffler ~15-20%, Rory ~8-10%)
- [ ] Do odds update live during play? (DataGolf polls every 5 min)
- [ ] Does evolution chart show sensible movements? Does position toggle (Top 20/10/5/Win) work?
- [ ] Does leaderboard update with Score/Today/Thru during live play?
- [ ] Does Bubble Watch appear during Rounds 1-2?
- [ ] Does the championship grid update? [bainluck.com/playoffs/golf](https://bainluck.com/playoffs/golf)
- [ ] Mobile layout: anything cut off, overlapping, or hard to tap?
- [ ] If odds seem stale (same numbers >30 min during active play), note it
- [ ] If probabilities don't sum to ~100%, note it
- [ ] If eliminated/cut players still show high odds, note it

---

## To-Do List

### Before Masters (April 3-8) — Can do from iPad via Claude.ai

| # | Task | Next action | Can do from iPad? |
|---|------|-------------|-------------------|
| 1 | Fix tour classification (Hainan = Asian Tour, not PGA Tour) | Claude.ai: edit `golf.py` to use DataGolf `tour` field | Yes |
| 2 | Fix false "LIVE" badges | Claude.ai: fix `isTournamentLive()` to check round dates | Yes |
| 3 | Fix "Yes" binary market on categories page chart | Claude.ai: apply same market fallback as tournament detail | Yes |
| 4 | Filter non-winner markets from tournament cards | Already done (prop market filter shipped Apr 3) | Done |
| 5 | Add "to win" label on probabilities | Claude.ai: small copy change in `TournamentCard.tsx` | Yes |
| 6 | Verify DataGolf live polling activates for Masters | Check [admin dashboard](https://bainluck.com/admin) on Apr 9 — look for DataGolf task activity | Check only |
| 7 | Mobile smoke test (phone Safari) | Open all golf pages on phone, note layout issues | Yes (manual) |
| 8 | Review golf product strategy | Read the "Strategy Decisions" section below, approve/edit | Yes (this doc) |

### After Trip (April 11+)

| # | Task | Notes |
|---|------|-------|
| 9 | Golf home redesign | Hero card, majors section, tour filtering, kill inline tables |
| 10 | H2H matchups on tournament detail | Option B compact rows + probability line |
| 11 | Redirect `/playoffs/golf` → `/categories/golf` | Kill the "playoffs" framing for golf |
| 12 | Tour-based following + onboarding | "Which tours do you follow?" |
| 13 | Freshness-weighted source blending | Stale Kalshi prices diluting fresh DataGolf — see design notes below |

---

## Open Investigations

### Tiger Woods 41.3% for The Open
**What**: Tiger shows as favorite for The Open Championship at 41.3%, which is absurd.
**Likely cause**: Stale or inflated odds from a single sportsbook in the Odds API. Not a code bug.
**Next action**: Will self-correct when DataGolf publishes the field closer to tournament. Monitor, don't fix in code. (We do NOT manually adjust odds — core product principle.)

### Freshness-Weighted Source Blending
**What**: During live play, stale prediction market prices (Kalshi 5h old) get equal weight with fresh model data (DataGolf updated minutes ago). Merged probability becomes less accurate than the fresh source alone.
**Key complications**:
- `last_updated` reflects poll time, not last price change — need to detect actual movement
- Staleness is context-dependent (2h stale during live round vs 12h pre-tournament)
- If decay drops a source to near-zero, cells become single-source
- Applies to all grids, not just golf
**Next action**: Gather eval data during Masters, then design solution. Don't implement yet.

### "Augusta National Invitational" Ghost Tournament
**What**: A tournament with wrong date appearing on the golf page.
**Next action**: Investigate — is this a misclassified Kalshi market? Check data after Masters.

---

## Strategy Decisions (Need Your Approval)

These are from the golf product strategy doc. Mark Y/N or add notes:

### 1. Kill `/playoffs/golf`?
**Proposal**: Redirect to `/categories/golf`. "Playoffs" doesn't make sense for golf.
**Status**: Pending your call.

### 2. Default to PGA Tour only?
**Proposal**: Golf home shows PGA Tour events by default. "All Tours" toggle for DP World, LIV, LPGA, etc.
**Status**: Pending your call.

### 3. Golf home hierarchy?
**Proposal** (top to bottom):
1. This Week / Live Tournament hero card
2. The Majors (4 cards, always visible)
3. Upcoming Tournaments (chronological)
4. Recently Completed (collapsed)

**Status**: Pending your call.

### 4. Props on cards vs detail page only?
**Current**: Prop markets (captain picks, participation) show on tournament cards (shipped Apr 3).
**Question**: Keep props on cards, or move them to detail page only?
**Status**: Pending your call.

### 5. Completed tournaments: show final results or pre-tournament odds?
**Proposal**: Final results (winner, margin). Nobody cares about pre-tournament odds after it's over.
**Status**: Pending your call.

---

## How to Make Changes From iPad

1. Open [claude.ai](https://claude.ai)
2. Describe what you want changed (paste file contents from GitHub if needed)
3. Get Claude to generate the edited file
4. Go to [github.com/alexander-bain/bainluck](https://github.com/alexander-bain/bainluck)
5. Navigate to the file, click edit (pencil icon), paste the new contents
6. Commit directly to `master`
7. **Frontend**: Vercel deploys in ~60 seconds
8. **Backend**: Heroku deploys in ~15 seconds (both auto-deploy from master, confirmed working)

---

## If Something Breaks

| Problem | What to do |
|---------|-----------|
| Site down | Check [api.bainluck.com/health](https://api.bainluck.com/health). If down, restart via Heroku dashboard on phone |
| Odds stale | Check [admin dashboard](https://bainluck.com/admin) for quota/worker status. Quota guard auto-protects. |
| DataGolf not updating | May be a Redis gate issue. Note for post-trip fix. |
| Something else | Note it. Fix when you're back with full CLI. |
