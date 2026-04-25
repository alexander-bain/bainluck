# Design Brief: Event Detail Page — Below-the-Fold Redesign

## Context

The event detail page's below-the-fold sections (Total Points, Player Props, Bigger Picture, Trade Watch) are broken and embarrassing. This brief describes the current problems, the available data, and the vision for each section — giving Claude Design enough detail to produce mockups.

**Core product principle**: We aggregate probabilities from multiple sources (sportsbooks, Kalshi, Polymarket, ESPN, our own models) and show them as clean visual probabilities. NEVER American odds. When Kalshi and Polymarket both have odds on the same thing, we group and dedup — that cross-source aggregation is the magic. Subtly surface it (e.g., "2 sources" badge).

**Design constraint**: Light mode only. White backgrounds, clean gridlines. Reference: DataGolf's evolution plot for chart style.

---

## Section 1: Total Points Spectrum

### Current State (BROKEN)
- 172 Kalshi thresholds crammed into a single horizontal bar
- X-axis labels all overlap and are completely unreadable
- Green/red/yellow blocks with no context
- No connection to the game score or what the thresholds mean

### Available Data
For each threshold (e.g., "Over 212.5 points"):
- `threshold`: number (e.g., 212.5)
- `over_probability`: float (e.g., 0.65)
- `source`: "kalshi" or "polymarket"
- `movement`: change from opening

Also available:
- Current game total (home_score + away_score)
- Projected total from spreads (over/under consensus)
- Pace data: `projected_total`, `total_scored`, `fraction_elapsed`, `time_remaining_display`

### Vision
A clean visualization that answers: **"What's the expected final total, and how confident is the market?"**

**Core display:**
- A bell curve / distribution showing the probability density across total thresholds
- Clear x-axis with major gridlines every 5 points (e.g., 200, 205, 210, 215, 220)
- A vertical marker showing the current sportsbook O/U line
- A second marker showing the pace-projected total (if game is live)
- A third marker showing actual total scored so far (if live)
- Shaded region showing the "most likely range" (e.g., 70% confidence interval)

**Live game enhancement:**
- "Pace" indicator: "On pace for 224 points (212.5 O/U)" with a visual showing whether the game is tracking over or under

**Completed game:**
- Show final total vs. opening O/U — "Finished at 219 (opened 212.5 O/U)"

**Key**: Don't try to show 172 individual thresholds. Aggregate them into a smooth distribution. The raw data is per-threshold binary markets — we turn them into a probability distribution.

### Data Tiers
| Tier | Data Available | Display |
|------|---------------|---------|
| Rich (NBA, MLB) | 40-200 thresholds + pace | Full distribution + pace overlay |
| Medium (NHL, soccer) | 10-40 thresholds | Simplified distribution |
| Minimal (college) | 0-5 thresholds | Just show O/U line + over prob |
| None | No total markets | Hide section entirely |

---

## Section 2: Player Props

### Current State (BROKEN)
- Massive grid of cards with random, unlabeled numbers
- Players from WRONG SPORTS showing up (NBA three-pointers on MLB games due to city-name matching)
- No headshot images for most players
- "98% chance" everywhere (boring props not filtered — FIXED in this session but design still broken)
- No connection between pre-game expectation, live drift, and actuals
- No stat type labels ("Points", "Rebounds", "Assists" etc.)

### Cross-Sport Contamination (must fix in backend first)
The game markets endpoint matches by team city name without sport filtering. A "Cleveland Guardians vs Houston Astros" MLB game pulls in:
- "Atlanta at Cleveland: Three Pointers" (NBA)
- "Memphis at Houston: Double Doubles" (NBA)
- "San Diego FC at Houston: Both Teams to Score" (MLS)

**Backend fix needed**: Filter game markets by `sport_id` or `llm_sport_category` matching the event's sport.

### Available Data (per player prop)
- `market_name`: "Houston vs Cleveland: Hits" or "LeBron James: Points"
- `outcome_name`: "Steven Kwan: 1+" or "Over 24.5"
- `threshold`: number (e.g., 24.5)
- `over_probability`: float
- `source`: "kalshi" or "polymarket"  
- `movement`: change from opening probability
- `player_headshot`: URL (when available)

Also available from box scores (live games):
- `box_score_data`: actual stats per player (points, rebounds, assists, hits, etc.)

### Vision: The Player Stat Dashboard

**The magic experience Alex described:**
> "If Jayson Tatum starts with a 20-point O/U, gets hot with 10 in Q1, it's neat to see he's halfway to the original O/U and the live O/U is now 35."

**Per-player card layout:**
```
┌─────────────────────────────────────────┐
│ [headshot]  Jayson Tatum        BOS     │
│                                         │
│  Points        Rebounds      Assists    │
│  ╔══════╗     ╔══════╗     ╔══════╗    │
│  ║  18  ║     ║   4  ║     ║   3  ║    │
│  ╚══════╝     ╚══════╝     ╚══════╝    │
│  O/U: 24.5    O/U: 6.5    O/U: 4.5    │
│  Live: 32.5   Live: 8.5   Live: 5.5   │
│  ──────────   ──────────   ──────────  │
│  [progress]   [progress]   [progress]  │
│                                 2 src  │
└─────────────────────────────────────────┘
```

**Key elements per stat:**
1. **Actual** (big number, bold): current stat line from box scores
2. **Opening O/U** (small, muted): pre-game threshold
3. **Live O/U** (if different from opening): current market threshold
4. **Progress bar**: visual showing actual vs. opening O/U
5. **Source count badge**: "2 src" when both Kalshi and Polymarket have it

**Three states:**

**Pre-game:**
- Show opening O/U thresholds per stat type
- Show the over probability for each
- Group by player, sorted by "most interesting" (biggest props first)

**Live:**
- Show actual stats vs. opening O/U
- Progress bar fills as player accumulates stats
- Highlight when a player is "ahead of pace" or "behind pace"
- Live O/U shifts shown as annotation ("O/U moved from 24.5 → 32.5")

**Completed:**
- Show final stats vs. pre-game O/U
- Clear hit/miss indicator: "Over" or "Under" badge per stat
- Sort by biggest surprise (most unexpected result first)

### Grouping & Dedup
- Group all props for the same player into one card
- Within a player card, group by stat type (Points, Rebounds, Assists, etc.)
- When Kalshi AND Polymarket both have "Jayson Tatum: Points Over 24.5", show averaged probability with "2 sources" badge
- When thresholds differ (Kalshi: 24.5, Polymarket: 25.5), show the averaged threshold or both

### Sport-Specific Stat Types

| Sport | Primary Stats | Secondary Stats |
|-------|--------------|-----------------|
| NBA | Points, Rebounds, Assists | Three Pointers, Steals, Blocks, Double-Doubles |
| NFL | Passing Yards, Rushing Yards, TDs | Receptions, Receiving Yards, Interceptions |
| MLB | Hits, Home Runs, RBIs | Strikeouts (pitcher), Stolen Bases, Total Bases |
| NHL | Goals, Assists, Shots | Saves (goalie), Power Play Points |
| Soccer | Goals, Assists, Shots | Cards, Corners |

### Data Tiers
| Tier | Data Available | Display |
|------|---------------|---------|
| Rich (NBA, NFL playoffs) | 50-200+ props per player, box scores | Full player dashboard cards |
| Medium (MLB, NHL regular) | 10-50 props | Condensed player cards |
| Minimal (college, soccer) | 0-5 props | Small inline list or hide |
| None | No props | Hide section entirely |

---

## Section 3: Bigger Picture (Related Futures)

### Current State (MEH)
- Playoff Path cards are okay but have wasted white space
- Team record is shown redundantly (in Playoff Path AND in Season Stats)
- No visual probability bars — just text percentages
- Missing team-level props: win totals, awards (MVP, DPOY)
- No series matchup odds during playoffs
- Trade Watch is conceptually fun but shows same player traded to both teams

### Available Data

**Championship progression (per team):**
- Make Playoffs: probability + change
- Win Conference: probability + change
- Win Championship: probability + change
- Sources: Kalshi, Polymarket, Odds API (up to 3 independent sources)

**Additional season-level markets we SHOULD show but don't:**
- Win Total O/U (e.g., "Lakers Over 45.5 Wins: 62%")
- Division Winner
- MVP / DPOY / ROY / 6MOY (player awards for players on these teams)
- Playoff series winner (during playoffs: "Celtics vs Cavaliers: 72%")
- Coach of the Year
- Season win total exact

**Team context (from ESPN):**
- Current record (e.g., 56-26)
- Conference/division standing (#1 Eastern Conference)
- Streak (W5, L2)
- Home/away record

### Vision: The Season Context Dashboard

**Replace the current scattered layout with a unified two-column team comparison:**

```
┌──────────────────────┬──────────────────────┐
│   🏀 76ers  (45-37)  │   🏀 Celtics (56-26) │
│   #4 Eastern Conf    │   #1 Eastern Conf    │
│                      │                      │
│   Championship Path  │   Championship Path  │
│   ━━━━━━━━━━━━━━━━━ │   ━━━━━━━━━━━━━━━━━ │
│   Playoffs  ✓ done   │   Playoffs  ✓ done   │
│   Conference  3% ▪   │   Conference 41% ████│
│   Champion    1% ▪   │   Champion  13% ██   │
│   ─────────────────  │   ─────────────────  │
│   Win Total: O52.5   │   Win Total: O62.5   │
│   48% (2 src)        │   71% (3 src)        │
│                      │                      │
│   Player Awards      │   Player Awards      │
│   MVP: Embiid 2%     │   MVP: Tatum 12%     │
│   DPOY: — none       │   DPOY: Brown 8%     │
└──────────────────────┴──────────────────────┘
```

**Key design principles:**
1. **Visual bars** for championship path (not just text percentages)
2. **One card per team**, side-by-side — eliminates the redundant "Season Stats" section
3. **Source count badges** everywhere Kalshi + Polymarket + Odds API agree
4. **Progressive disclosure**: Show champion path + win total by default. Expand for awards, division, series.

**Playoff series (when applicable):**
If teams are in a playoff series, show a prominent series matchup card above the team columns:
```
┌─────────────────────────────────────────────┐
│  PLAYOFF SERIES: Celtics vs Cavaliers       │
│  Celtics lead 3-1                           │
│  ████████████████████░░░  Celtics 92%       │
│  ███░░░░░░░░░░░░░░░░░░░  Cavaliers 8%      │
│  Kalshi + Polymarket                        │
└─────────────────────────────────────────────┘
```

**Trade Watch (rethink):**
The current implementation shows "Ja Morant traded to BOTH teams" simultaneously, which is illogical. Either:
- (a) Show only the team with higher probability
- (b) Remove entirely until we have better data
- (c) Reframe as "Transfer Rumors" with a disclaimer about prediction market speculation

### Data Tiers
| Tier | Data Available | Display |
|------|---------------|---------|
| Rich (NBA/NFL/NHL playoffs) | Championship path + series + win totals + awards | Full two-column dashboard |
| Medium (regular season MLB/NBA) | Championship path + win totals | Standard two-column, collapsed awards |
| Minimal (college, MLS) | Make playoffs only, maybe conference | Compact single row per team |
| None | No futures for these teams | Hide section entirely |

---

## Section 4: Special Events (Super Bowl, Masters, World Series)

### Challenge
When a marquee event happens, there are TONS of additional markets available (e.g., Super Bowl: first TD scorer, halftime score, MVP, coin toss, anthem length, Gatorade color). We need to surface these automatically without building bespoke pages.

### Solution: Market Category Discovery
The system should auto-discover market categories from the available data:

1. **Scan all markets linked to the event** (via `event_id`)
2. **Classify by market type**: moneyline, total, spread, player prop, game prop, novelty
3. **Group by category**: "Player Performance", "Game Events", "Fun Props"
4. **Sort by engagement potential**: number of outcomes, volume, uniqueness

**For a Super Bowl, this might auto-generate:**
- Player Performance (30 player prop cards)
- Game Props (first score method, halftime lead, OT?)
- Novelty Props (coin toss, anthem, Gatorade color)
- MVP (probability distribution across candidates)

**For a golf major, this might auto-generate:**
- Winner odds (top 20 golfers)
- Top 5 / Top 10 / Top 20 / Make Cut (expandable per golfer)
- Head-to-head matchups
- Nationality props

**Key**: The frontend component should accept ANY list of categorized markets and render them appropriately. No sport-specific hardcoding in the frontend.

---

## Cross-Cutting Design Requirements

### 1. Cross-Source Magic
Every time we show a probability that combines Kalshi + Polymarket + sportsbook data, subtly indicate it:
- Small badge: "3 sources" or "K+P" 
- Tooltip on hover showing per-source breakdown
- This is our competitive advantage — make it visible but not noisy

### 2. Graceful Degradation
Design must work across data density tiers:
- **NBA playoff game**: 6,000+ props, rich futures, series matchups — full dashboard
- **Regular season MLB**: 200 props, basic futures — standard layout
- **College lacrosse**: 0 props, no futures — just the win probability chart + schedule context
- **Never show an empty section** — if no data, hide the section entirely

### 3. Responsive
- Mobile (375px): Stack everything vertically, cards become full-width
- Tablet: Two-column where appropriate
- Desktop: Two-column with room for detail panels

### 4. Live vs. Pre-Game vs. Completed States
Every section has three states. Design all three:
- **Pre-game**: Expectations, opening lines, probability distributions
- **Live**: Expectations vs. reality, pace tracking, drift from opening
- **Completed**: Final results vs. expectations, biggest surprises

---

## Reference: Market Inventory Per Sport

### NBA Regular Season Game
| Category | Kalshi Markets | Polymarket Markets | Odds API |
|----------|---------------|-------------------|----------|
| Player Points | ~30 per game | ~20 per game | ~40 |
| Player Rebounds | ~25 | ~15 | ~30 |
| Player Assists | ~20 | ~10 | ~25 |
| Player 3PT | ~15 | ~10 | ~20 |
| Player Double-Doubles | ~8 | ~5 | ~10 |
| Game Total | ~50 thresholds | ~20 | ~15 |
| Team Total | ~20 per team | — | ~10 |
| Spreads | ~30 | ~10 | ~15 |
| First Half | ~15 | — | ~10 |
| Quarter-by-Quarter | ~10 | — | — |
| **Championship (season)** | 30 teams | 30 teams | 30 teams |
| **Conference (season)** | 30 teams | 30 teams | — |
| **Win Total (season)** | 30 teams | — | 30 teams |
| **MVP / Awards (season)** | ~20 players | ~15 players | ~10 |
| **Playoff Series** | per matchup | per matchup | — |

### MLB Regular Season Game
| Category | Kalshi | Polymarket | Odds API |
|----------|--------|-----------|----------|
| Player Hits | ~15 | — | ~20 |
| Player Home Runs | ~10 | — | ~15 |
| Player H+R+RBI | ~20 | — | — |
| Pitcher Strikeouts | ~5 | — | ~10 |
| Game Total | ~20 | ~5 | ~10 |
| First 5 Innings | ~3 | — | ~5 |
| **Championship** | 30 teams | 30 teams | 30 teams |
| **Pennant** | 30 teams | 30 teams | — |
| **Division** | 30 teams | — | 30 teams |

### NHL Playoff Game
| Category | Kalshi | Polymarket | Odds API |
|----------|--------|-----------|----------|
| Player Goals | ~10 | — | ~15 |
| Player Assists | ~5 | — | ~10 |
| Player Shots | ~5 | — | ~10 |
| Game Total | ~15 | ~5 | ~10 |
| **Stanley Cup** | 16 teams | 16 teams | 32 teams |
| **Conference** | 16 teams | 16 teams | — |
| **Playoff Series** | per matchup | per matchup | — |

### College Basketball / Low-Tier
| Category | Kalshi | Polymarket | Odds API |
|----------|--------|-----------|----------|
| Moneyline only | maybe 1 | — | 1 |
| Game Total | maybe 1 | — | 1 |
| Spread | maybe 1 | — | 1 |
| **Championship** | maybe | — | yes |

---

## Deliverables Requested

1. **Total Points Spectrum redesign** — Distribution visualization replacing the unreadable bar
2. **Player Props redesign** — Player stat dashboard cards with opening/live/actual comparison
3. **Bigger Picture redesign** — Two-column team comparison with visual probability bars
4. **Adaptive layout** — How the page looks for rich (NBA playoff), medium (MLB regular), and minimal (college) data tiers
5. **Special event handling** — How auto-categorized markets render for Super Bowl / Masters type events

All mockups should use real team names, realistic probabilities, and show the three states (pre-game, live, completed).
