# Golf Product Strategy

**Status**: Draft — needs Alex's review before implementation
**Last updated**: April 3, 2026

---

## The Problem

Golf on BainLuck is currently a scattered collection of features with no coherent UX:

- `/categories/golf` — a long list of tournaments across all tours, with inline odds tables and a "Biggest Movers" section. No clear hierarchy, no filtering, no personalization.
- `/playoffs/golf` — a championship grid that only works for the 4 majors. Confusing name ("playoffs" doesn't make sense for golf).
- `/categories/golf/tournaments/[slug]` — a tournament detail page with evolution chart, leaderboard, and bubble watch. The best page we have, but users have to find it.
- Tournament cards on the categories page are inconsistent — some show hero probabilities, others show raw market labels like "HAINAN CLASSIC END OF ROUND 1 LEADER".

**Core question**: What does a casual golf fan want when they come to BainLuck during the Masters?

---

## North Star

**BainLuck is the best place to understand what's likely to happen in golf, right now.**

Not a sportsbook. Not a stats site. Not a leaderboard (ESPN/DataGolf already do that). BainLuck's unique value is:
1. **Aggregated probabilities** across all sources (sportsbooks, Kalshi, Polymarket, DataGolf model)
2. **Evolution over time** — how have odds shifted? (our evolution chart)
3. **Position depth** — not just "who wins" but Top 5, Top 10, Top 20, make cut
4. **Fun props** — will Tiger play? H2H matchups? Nationality winner?

---

## Information Architecture

### Page Hierarchy

```
/categories/golf                    ← GOLF HOME (the hub)
  └─ /categories/golf/tournaments/[slug]  ← TOURNAMENT DETAIL (the deep dive)
```

**Kill `/playoffs/golf`**. Redirect to `/categories/golf`. "Playoffs" doesn't apply to golf. The majors grid was an experiment; the evolution chart on tournament detail pages is a better visualization.

### Golf Home (`/categories/golf`)

This is the **TV Guide for golf**. A user opens it and instantly knows: what's happening now, what's coming up, and what's interesting.

#### Layout (top to bottom):

1. **This Week / Live Tournament Hero** (if any tournament is in progress or starts within 3 days)
   - Full-width card with tournament name, dates, venue, round status
   - Leader + top 4 chasers with win probabilities
   - Tap → tournament detail page
   - If no current tournament: show "Next up: [Tournament Name] — starts [date]"

2. **The Majors** (4 cards, always visible)
   - The Masters, PGA Championship, U.S. Open, The Open
   - Each shows: leader, win%, dates, venue
   - Highlight the one that's next/current
   - These are the anchor — casual fans care about majors

3. **Upcoming Tournaments** (scrollable list, grouped by tour)
   - PGA Tour events only by default (casual fans don't follow Asian Tour)
   - Each card: tournament name, dates, venue, leader + win%
   - Filter/toggle: "PGA Tour" | "All Tours" (default: PGA Tour)
   - Sort: chronological (next event first)

4. **Recently Completed** (collapsed by default)
   - Last 2-3 finished tournaments
   - Show winner + winning margin
   - "View full results" → tournament detail page

#### What to REMOVE from the current categories page:
- ❌ Inline 40-row odds tables (move to tournament detail page)
- ❌ "Biggest Movers (24H)" section (move movers into tournament cards as delta indicators)
- ❌ Raw market labels like "HAINAN CLASSIC END OF ROUND 1 LEADER" (filter to outright winner only)
- ❌ Non-PGA Tour events in the default view (hide behind "All Tours" toggle)
- ❌ "Will Tiger Woods Play" type markets on the landing page

### Tournament Detail (`/categories/golf/tournaments/[slug]`)

This is the **deep dive**. Already the strongest page — keep iterating here.

#### Layout (top to bottom):

1. **Tournament Header** — name, dates, venue, round status, source badges
2. **Evolution Chart** — with position toggle (Top 20/10/5/Win), time range, fullscreen
3. **Bubble Watch** — rounds 1-2 only, cut line tracker
4. **Leaderboard** — full 9-column grid (Pos, Name, Score, Today, Thru, Win, T5, T10, T20)
5. **H2H Matchups** — head-to-head markets (future, needs backend work)
6. **Fun Props** — "Will Tiger play?", nationality winner, etc. (future)
7. **Source Attribution** — footer with data sources

---

## Tournament Cards

Cards are how users discover tournaments. They appear on the Golf Home page and potentially in the main feed.

### Card Variants

**Hero Card** (current/live tournament — max 1 at a time):
```
┌──────────────────────────────────────────┐
│ ⛳ The Masters  ● Round 2               │
│ Augusta National Golf Club               │
│ Apr 9-12, 2026                           │
│                                          │
│  14.2%  Scottie Scheffler  ↑2.1%        │
│         Leader · -8 (Thru 14)            │
│                                          │
│  Rahm 6.8%  McIlroy 6.1%  Schauffele 4% │
│                                          │
│  [View Leaderboard →]                    │
└──────────────────────────────────────────┘
```

**Standard Card** (upcoming or other tournaments):
```
┌──────────────────────────────┐
│ PGA Tour · Apr 16            │
│ Mexico City Open             │
│ Club de Golf                 │
│                              │
│  19.6%  Jon Rahm             │
│  DeChambeau 11.5%  Niemann 4%│
└──────────────────────────────┘
```

**Completed Card** (past tournaments):
```
┌──────────────────────────────┐
│ PGA Tour · Mar 30  ✓         │
│ Valero Texas Open            │
│                              │
│  🏆 Matti Schmid  -14       │
│  Runner-up: Coody -12       │
└──────────────────────────────┘
```

### Card Rules:
- **Only show outright winner/champion markets** — never "End of Round 1 Leader", "Make The Cut", or "Top 20 Finishers" in the card hero probability
- **Label what the probability means**: "14.2% to win" not just "14.2%"
- **Show score + position for live tournaments**: not just the probability
- **24h movement as inline delta** (↑2.1%), not as a separate "Biggest Movers" section
- **Tour badge**: PGA Tour, DP World Tour, LPGA, LIV, etc.
- **Never show "LIVE" badge unless the tournament is actually in progress** (rounds being played right now, not just "market exists")

---

## Tour Classification

### Current Problem
Events from different tours are all labeled "PGA Tour". The Hainan Classic is an Asian Tour / DP World Tour co-sanctioned event, not PGA Tour. Hero Indian Open is DP World Tour.

### Fix
- Use DataGolf's tour classification as source of truth (they provide `tour` field)
- Supported tours: PGA Tour, DP World Tour, LPGA, LIV Golf, Korn Ferry, Champions Tour
- Default view: PGA Tour only
- "All Tours" toggle shows everything
- Each card shows its tour badge

---

## Following & "My Stuff"

### How Golf Subscriptions Work

Golf following is **tour-based**, not team-based (unlike other sports).

**Onboarding flow** (when user first visits golf):
1. "Which tours do you follow?" → PGA Tour (default on), DP World Tour, LPGA, LIV, All
2. "Any favorite golfers?" → search/select from top 50 (optional)
3. Following preferences stored in `user_preferences`

**What following does:**
- Golf cards appear in the main feed based on followed tours
- Favorite golfers get highlighted in leaderboards
- Notifications (future): "Scheffler takes the lead at the Masters"

**"My Stuff" → Golf section:**
- Next tournament for each followed tour
- Favorite golfer standings (if any tournament is live)
- Quick links to evolution charts for tracked tournaments

---

## Props & Side Markets

### Where They Live

Props should NOT clutter the main views. They live:
1. **Tournament detail page** — dedicated section below the leaderboard
2. **"More Markets" expandable section** — collapsed by default

### Prop Categories
- **H2H Matchups** — "Scheffler vs McIlroy" with probability line (approved design: Option B)
- **Player Props** — "Will Tiger Woods play?" yes/no with probability
- **Nationality/Group** — "European winner?" with probability
- **Round-specific** — "Round 1 leader" (only show during/before that round)

### Prop Display Rules
- Never show resolved/obvious props (e.g., "make the cut" at 100%)
- Never show props as if they're win probabilities
- Always label clearly: "H2H: Scheffler vs McIlroy" not just "Scheffler 62%"
- Group by type, not by source

---

## Data Quality Fixes (Immediate)

These bugs need fixing before the strategy can work:

| # | Bug | Fix |
|---|-----|-----|
| 1 | "Augusta National Invitational" with wrong date | Investigate: is this a misclassified Kalshi market? Filter or rename |
| 2 | Hainan Classic / Hero Indian Open labeled PGA Tour | Use DataGolf tour classification; add tour field to tournament model |
| 3 | Masters shows "LIVE" when not in progress | Fix `isTournamentLive()` — check actual round dates, not just market existence |
| 4 | Categories page chart shows "Yes" (Polymarket binary) | Categories page needs same market fallback logic as tournament detail |
| 5 | Tiger Woods 41.3% for The Open | Investigate: stale/inflated odds? Check source data |
| 6 | "Matti Schim 50%" with no context | Label as "50% to win" explicitly |
| 7 | Raw market labels in cards | Filter to outright winner markets only; normalize display names |
| 8 | Completed tournaments showing 100% probabilities | Filter resolved markets or show final results instead |

---

## Implementation Phases

### Phase 1: Clean Up (Pre-Masters, April 3-8)
**Goal**: Make what exists work correctly
- [ ] Fix tour classification (PGA Tour vs other tours)
- [ ] Fix "LIVE" badge logic (only during actual rounds)
- [ ] Fix "Yes" binary market on categories page chart
- [ ] Filter non-winner markets from tournament cards
- [ ] Add "to win" label on probabilities
- [ ] Redirect `/playoffs/golf` → `/categories/golf`

### Phase 2: Golf Home Redesign (Post-Trip, April 11+)
**Goal**: Make `/categories/golf` the hub
- [ ] "This Week" hero card for current/upcoming tournament
- [ ] Majors section (4 cards, always visible)
- [ ] Upcoming tournaments list (PGA Tour default, "All Tours" toggle)
- [ ] Remove inline 40-row odds tables
- [ ] Remove "Biggest Movers" section (integrate deltas into cards)

### Phase 3: Tournament Detail Polish (April 11+)
**Goal**: Make tournament pages world-class during live events
- [ ] Populate Top 5/10/20 columns from Kalshi position markets
- [ ] H2H Matchups section (needs backend: stop filtering " vs " markets)
- [ ] Props section (Will Tiger play?, nationality, etc.)
- [ ] Round markers on evolution chart (R1, R2, Cut, R3, R4)

### Phase 4: Following & Feed (Later)
**Goal**: Golf in the main product loop
- [ ] Tour-based following in onboarding
- [ ] Golf cards in the main feed
- [ ] Favorite golfer highlights in leaderboards
- [ ] "My Stuff" golf section

---

## Success Metrics

How we know golf is working:
1. **Time on golf pages** — do users stay and explore, or bounce?
2. **Tournament detail page visits** — are users drilling in from the hub?
3. **Return visits during Masters** — do people come back across rounds?
4. **Position toggle usage** — are people exploring Top 5/10/20, or just Win?
5. **Evolution chart engagement** — time range switching, player adding/removing, fullscreen

---

## Open Questions

1. Should completed tournaments show final results (winner, margin) or pre-tournament odds? → **Final results** (nobody cares about pre-tournament odds after it's over)
2. Should we show odds for tournaments >30 days out? → **Yes, but de-emphasize** (smaller cards, "early odds" label)
3. LIV Golf — do we want to support it? → **Yes, but low priority** (no DataGolf coverage, limited Kalshi markets)
4. Should evolution charts on the categories page show position toggle? → **No** — keep it simple on the hub, deep dive on the tournament page
5. Ryder Cup — how to handle team format? → **Custom card** (team-based, different from individual tournaments)
