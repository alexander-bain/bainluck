# Championship Grids Project

## The Problem

Bain Luck's fundamental value proposition is showing championship probabilities clearly. But right now, if a user wants to understand "How likely are the Celtics to win the NBA Championship?", they have to:

1. Find a Celtics game on the feed
2. Click into the event detail
3. Scroll to "Bigger Picture" section
4. See a single championship probability with no context about the journey to get there

We don't answer the most basic questions a fan has: *What are my team's chances at each stage of the playoffs? How has that changed over time? How do different sources see it?*

Reference sites that do this well:
- **MoneyPuck** (`moneypuck.com/predictions.htm`) — NHL playoff grid with round-by-round probabilities, team logos, clean table layout
- **PlayoffStatus** (`playoffstatus.com/nfl/nflpostseasonprob.html`) — NFL grid with make playoffs / win division / conference / Super Bowl columns
- **DataGolf** (`datagolf.com/predictions/pga-tour`) — Golf tournament grid with trend chart at top, per-round columns (Make Cut, Top 20, Top 10, Top 5, Win)
- **ESPN Betting** — March Madness bracket odds with round-by-round progression

## The Goal

Build **championship progression grids** — one per league/tournament — that show every relevant team as a row and every playoff round as a column. Each cell shows the team's probability of reaching that stage, sourced from multiple providers where available. A trend chart at the top shows how the top contenders' odds have moved over time.

This becomes **the** way to browse championship odds on Bain Luck, and the data feeds cleanly into event detail pages, the feed, and eventually the iOS app.

## Success Criteria

1. A user can find any NBA/NHL/NCAA team's championship odds within 2 taps from the homepage
2. Every cell in the grid shows a probability that is mathematically consistent (P(championship) ≤ P(conference finals) ≤ P(second round) ≤ P(make playoffs))
3. Multi-source data is visible (e.g., "22% DK / 24% Poly") without making the grid unreadable
4. The trend chart shows meaningful time windows (7d for leagues, tournament-duration for events)
5. The grid data is reusable — event detail pages show a team's progression row inline
6. Each grid page is discoverable from the homepage, navigation, and search

## Platform Requirements

This must work across **all four surfaces:**
- **Web desktop** — full grid with all columns visible, hover interactions
- **Web mobile** — sticky team column, horizontal scroll, condensed columns, tap interactions
- **iOS iPhone** — native SwiftUI grid in the app, same data, adapted for phone viewport
- **iOS iPad** — native SwiftUI with wider grid layout, sidebar navigation

The backend endpoint (`GET /api/playoffs/{league_slug}`) is shared across all platforms. The web frontend (Next.js) and iOS app (SwiftUI) each implement their own grid rendering against the same API response.

**Design principle:** The API response must be self-describing enough that any client can render the grid without hardcoded layout knowledge. Column definitions, sort order, conference groupings, and source metadata are all in the response — not baked into frontend code.

---

## Leagues & Tournament Structures

### 1. NCAA Basketball (March Madness) — TIME SENSITIVE
**Structure:** 68 teams → First Four → Round of 64 → Round of 32 → Sweet 16 → Elite 8 → Final Four → Championship
**Grid columns:** R64 | R32 | Sweet 16 | Elite 8 | Final Four | Champion
**Notes:** Single-elimination bracket. Region-based (teams can only meet certain opponents in certain rounds). Tournament lasts ~3 weeks. Markets exist for each round on Kalshi/Polymarket. DataGolf-style "current tournament" view with live round results.
**Data sources:** Odds API (outrights), Kalshi (round-by-round markets), Polymarket
**Time relevance:** Mid-March to early April (3 weeks/year). Must ship ASAP for 2026 tournament.

### 2. NBA Playoffs
**Structure:** 16 teams (8 per conference) → Play-In → First Round → Conference Semis → Conference Finals → NBA Finals → Champion
**Grid columns:** Make Playoffs | First Round | Conf Semis | Conf Finals | NBA Finals | Champion
**Notes:** Best-of-7 series at each stage. Eastern/Western conference brackets. Season-long relevance (Oct-Jun). Markets exist for championship, conference, division.
**Data sources:** Odds API (championship, conference, division outrights), Kalshi (various), Polymarket, ESPN (BPI projections)
**Time relevance:** Championship futures matter all season. Playoff round markets appear ~April.

### 3. NHL Playoffs
**Structure:** 16 teams (8 per conference) → First Round → Conference Semis → Conference Finals → Stanley Cup Finals → Champion
**Grid columns:** Make Playoffs | First Round | Conf Semis | Conf Finals | Stanley Cup | Champion
**Notes:** Best-of-7 series. Conference-based bracket. MoneyPuck is the gold standard for this view.
**Data sources:** Odds API (Stanley Cup outrights), Kalshi, Polymarket
**Time relevance:** Similar to NBA — futures all season, round-by-round in playoffs.

### 4. PGA Tour / Golf Majors
**Structure:** Per-tournament, not sequential rounds like playoffs. Each tournament: 156 players → Make Cut → Top 20 → Top 10 → Top 5 → Win
**Grid columns:** Make Cut | Top 20 | Top 10 | Top 5 | Win
**Notes:** NOT sequential elimination — a golfer can finish Top 5 without ever being "in" Top 10 during the tournament. Columns represent *finishing position probabilities*, not round-by-round progression. Weekly tournaments + 4 majors.
**Data sources:** DataGolf (best source, has round-by-round), Odds API, Polymarket, Kalshi
**Time relevance:** Each tournament is 4 days (Thu-Sun). Masters Apr 10-13 is the big one.

### 5. Future Leagues (not in v1, but architecture should support)
- **NFL** (Sep-Feb): Make Playoffs | Wild Card | Divisional | Conference | Super Bowl
- **MLB** (Apr-Oct): Make Playoffs | Wild Card | Division Series | Championship Series | World Series
- **Soccer** (Champions League, World Cup): Group Stage | R16 | QF | SF | Final
- **College Football Playoff**: 12 teams, First Round | QF | SF | Championship

---

## Data Architecture

### The Core Challenge: Market-to-Grid Matching

Each cell in the grid needs to map to one or more futures markets. This is the hardest part of the project. Markets don't label themselves as "NBA Conference Finals" — they say things like:

- Odds API: `"NBA Eastern Conference Winner 2025-26"` (market_tier=2)
- Kalshi: `"Will the Celtics make the NBA Finals?"` (binary yes/no)
- Polymarket: `"NBA Championship Winner"` (single market, tier 1 only)
- Polymarket: `"Will the Celtics win the Eastern Conference?"` (binary)

**Approach: League Config + Market Matching Rules**

Each league gets a config that defines:
```python
LEAGUE_CONFIGS = {
    "nba": {
        "name": "NBA Playoffs",
        "sport_keys": ["basketball_nba"],
        "grid_columns": [
            {"key": "make_playoffs", "label": "Make Playoffs", "order": 1, "sequential": True},
            {"key": "first_round", "label": "First Round", "order": 2, "sequential": True},
            {"key": "conf_semis", "label": "Conf Semis", "order": 3, "sequential": True},
            {"key": "conf_finals", "label": "Conf Finals", "order": 4, "sequential": True},
            {"key": "finals", "label": "NBA Finals", "order": 5, "sequential": True},
            {"key": "champion", "label": "Champion", "order": 6, "sequential": True},
        ],
        "market_matching_rules": [
            {"column": "champion", "patterns": [r"NBA Championship", r"NBA Finals Winner"], "tier": 1},
            {"column": "conf_finals", "patterns": [r"Eastern Conference", r"Western Conference"], "tier": 2},
            {"column": "make_playoffs", "patterns": [r"Make Playoffs", r"Playoff"], "tier": 4},
            # ...
        ],
        "team_sort": "championship_desc",  # Sort teams by championship probability
        "conference_split": True,  # Show East/West separately
    }
}
```

### Probability Consistency Enforcement

For **sequential** columns (where reaching round N requires surviving round N-1):
```
P(Champion) ≤ P(Finals) ≤ P(Conf Finals) ≤ P(Conf Semis) ≤ P(First Round) ≤ P(Make Playoffs)
```

When we have direct market data for multiple rounds, we trust the data but **flag inconsistencies** visually rather than silently adjusting. If Kalshi says 30% championship and Odds API says 25% conference finals, that's a data quality issue worth surfacing.

When we only have championship odds (common case), we can:
1. Show only the column we have data for (honest but sparse)
2. Derive implied probabilities from related markets (e.g., if a team's odds of winning the conference are 40%, and they'd likely be ~60% favorites in each series, work backwards)
3. Show "—" for missing columns with a tooltip explaining why

**Recommendation:** Start with option 1 (show what we have), evolve to option 2 as data improves.

### Multi-Source Cell Values

Each grid cell can have data from multiple sources. The display model:

```typescript
interface GridCell {
  column_key: string;           // "champion", "conf_finals", etc.
  team_id: number;
  merged_probability: number;   // Weighted average across sources
  sources: {
    source: string;             // "odds_api", "kalshi", "polymarket"
    probability: number;
    bookmaker?: string;         // For odds_api: "draftkings", "fanduel", etc.
    last_updated: string;       // ISO timestamp
  }[];
  trend_24h: number;            // Change in merged probability
  trend_7d: number;
}
```

Merging strategy: Use the same aggregation logic as the Oscars page — take median across sources, normalize per-column so probabilities don't exceed 100% in aggregate.

### New Backend Endpoint

```
GET /api/playoffs/{league_slug}
```

Response:
```json
{
  "league": "nba",
  "name": "NBA Playoffs 2025-26",
  "season": "2025-26",
  "columns": [
    {"key": "make_playoffs", "label": "Make Playoffs", "order": 1},
    {"key": "champion", "label": "Champion", "order": 6}
  ],
  "trend_chart": {
    "column": "champion",
    "hours": 168,
    "bucket_seconds": 3600,
    "timeline": [...]  // Reuse probability-timeline format
  },
  "teams": [
    {
      "team_id": 123,
      "name": "Boston Celtics",
      "short_name": "Celtics",
      "logo_url": "...",
      "primary_color": "#007A33",
      "conference": "Eastern",
      "record": "48-20",
      "cells": {
        "champion": {
          "merged_probability": 0.22,
          "sources": [
            {"source": "odds_api", "probability": 0.21, "bookmaker": "draftkings"},
            {"source": "polymarket", "probability": 0.24}
          ],
          "trend_24h": 0.015
        },
        "conf_finals": {
          "merged_probability": 0.45,
          "sources": [...]
        }
      }
    }
  ],
  "movers": [
    {"team_id": 123, "name": "Celtics", "column": "champion", "change_24h": 0.03, "direction": "up"}
  ],
  "last_updated": "2026-03-17T12:00:00Z",
  "sources_available": ["odds_api", "kalshi", "polymarket"]
}
```

### Team Row Reuse on Event Detail Pages

The related-futures endpoint should return a `playoff_progression` object for each team:
```json
{
  "home_team_progression": {
    "league": "nba",
    "cells": {
      "champion": {"merged_probability": 0.22, "trend_24h": 0.015},
      "conf_finals": {"merged_probability": 0.45}
    }
  }
}
```

This is a compact version of the team's row from the full grid, rendered as a mini horizontal bar on the event detail page.

---

## Frontend Design

### Page Structure

Each playoff grid page follows the same template:

```
┌──────────────────────────────────────────────────────┐
│  [← Back]  NBA Playoff Odds  [Pin] [Share]           │
│                                                       │
│  ┌─ Trend Chart ──────────────────────────────────┐  │
│  │  Multi-line chart: Top 5 teams' championship    │  │
│  │  odds over [7d ▾] with zoom controls            │  │
│  │  (Reuse TournamentChart component)              │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
│  ┌─ Biggest Movers ───────────────────────────────┐  │
│  │  ↑ Thunder +3.2%  ↑ Celtics +1.1%  ↓ Cavs -2% │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
│  Eastern Conference                                   │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Team        | Playoffs | R1  | CSF | CF  | Champ │ │
│  │─────────────┼──────────┼─────┼─────┼─────┼───────│ │
│  │ [🟢] BOS   | 99%      | 85% | 62% | 45% | 22%  │ │
│  │ [🔵] CLE   | 98%      | 80% | 55% | 38% | 15%  │ │
│  │ [🟠] NYK   | 95%      | 72% | 48% | 30% | 12%  │ │
│  │ ...                                               │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  Western Conference                                   │
│  ┌──────────────────────────────────────────────────┐ │
│  │ (same grid layout)                                │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  Sources: DraftKings · FanDuel · Polymarket · Kalshi  │
│  Last updated: 2 min ago                              │
└──────────────────────────────────────────────────────┘
```

### Cell Display

Each cell shows the merged probability prominently with small source indicators:
```
┌────────┐
│  22%   │   ← merged probability, bold
│ DK Poly│   ← tiny source abbreviations below
└────────┘
```

On hover/tap, expand to show:
```
┌──────────────────┐
│ Championship: 22%│
│                  │
│ DraftKings  21%  │
│ FanDuel     22%  │
│ Polymarket  24%  │
│ Kalshi      20%  │
│                  │
│ 24h: +1.5%      │
│ 7d:  +3.2%      │
└──────────────────┘
```

### Golf Variation

Golf tournaments use a different column structure (not sequential elimination) and need "current tournament" vs "upcoming tournaments" modes. The existing golf landing page should evolve into this grid format.

### Mobile Responsiveness

The grid must work on mobile. Strategy:
- Freeze team name + logo column on the left
- Horizontally scroll the round columns
- Default to showing only the 3-4 most important columns (e.g., Sweet 16 / Final Four / Champion for March Madness)
- Expandable to show all columns

---

## Implementation Phases

### Phase 0: Project Setup & Data Audit (1 session)
- [ ] Audit current futures markets in production to understand what data actually exists for each league
- [ ] Build league config structure (`backend/app/config/league_configs.py`)
- [ ] Write market-to-column matching rules for NBA and March Madness
- [ ] Verify which markets exist in Kalshi/Polymarket/OddsAPI for each playoff round

### Phase 1: Backend — Playoff Grid Endpoint (1-2 sessions)
- [ ] Create `GET /api/playoffs/{league_slug}` endpoint
- [ ] Implement market-to-column matching using league configs
- [ ] Implement multi-source probability merging (reuse Oscars aggregation logic)
- [ ] Add trend data (reuse probability-timeline bucket logic)
- [ ] Add movers computation (reuse golf movers logic)
- [ ] Include team metadata (logos, colors, records from Team table)
- [ ] Probability consistency checking (flag violations, don't silently fix)
- [ ] Tests: market matching accuracy, probability ordering, source merging

### Phase 2: Frontend — Grid Component (1-2 sessions)
- [ ] Design grid component in v0.dev (see v0 prompt below)
- [ ] Build `PlayoffGrid` React component from v0 output
- [ ] Build `GridCell` component with hover/tap source breakdown
- [ ] Integrate TournamentChart for trend visualization
- [ ] Mobile layout: sticky team column, horizontal scroll, column toggle
- [ ] Route: `/playoffs/[league]` (e.g., `/playoffs/nba`, `/playoffs/ncaa-basketball`)
- [ ] Navigation: add to header nav, filter chips, homepage section

### Phase 3: March Madness Specifics (1 session)
- [ ] Bracket-aware grid (show regions: East, West, South, Midwest)
- [ ] Round-by-round market matching for NCAA tournament
- [ ] "Current round" highlighting (which round is being played now)
- [ ] Results integration (show eliminated teams grayed out)
- [ ] Live tournament mode with auto-refresh

### Phase 4: Event Detail Integration (1 session)
- [ ] Add `playoff_progression` to related-futures endpoint
- [ ] Build `TeamProgressionBar` component for event detail pages
- [ ] Show both teams' progression rows inline on event detail
- [ ] Link from progression bar to full grid page

### Phase 5: iOS App — Native Grid (1-2 sessions)
- [ ] SwiftUI `PlayoffGridView` component (same API, native rendering)
- [ ] `GridCellView` with tap-to-expand source breakdown
- [ ] Horizontal scroll with sticky team column (works on iPhone + iPad)
- [ ] iPad: wider layout, all columns visible by default
- [ ] iPhone: condensed 3-column default, expandable
- [ ] Trend chart integration (port TournamentChart to SwiftUI Charts)
- [ ] Navigation from feed → grid, and from event detail → team row
- [ ] Deep link support (`bainluck://playoffs/nba`)

### Phase 6: Polish & Additional Leagues (1-2 sessions)
- [ ] NHL playoff grid
- [ ] Golf grid (evolve existing golf landing page)
- [ ] Shareable grid snapshots (OG image generation)
- [ ] SEO: meta tags, structured data for Google

### Phase 7: Ongoing Maintenance
- [ ] Add new leagues as playoff seasons approach (NFL in Sep, MLB in Oct)
- [ ] Monitor market-to-column matching accuracy
- [ ] Add new data sources as they become available

---

## v0.dev Prompts

### Prompt 1: Championship Grid Component

Copy this into v0.dev:

```
Design a dark-mode championship playoff progression grid for a sports odds product called "Bain Luck". This is the core visualization — think MoneyPuck.com/predictions.htm meets ESPN bracket odds.

## Tech Stack
- React with TypeScript
- Tailwind CSS
- shadcn/ui components
- Font: Inter for text, JetBrains Mono for numbers

## Color System
Background: #0C0F14, Card: #141820, Border: #242830
Text primary: #F8FAFC, Text secondary: #94A3B8, Text muted: #475569
Live green: #22C55E, Purple accent: #8B5CF6, Amber: #F59E0B

## Page Layout

The page has three sections stacked vertically:

### 1. Hero + Trend Chart
- Title: "NBA Playoff Odds" with a small "2025-26" season badge
- Below: a multi-line chart showing the top 5 teams' championship probability over time
  - Each line uses the team's primary color
  - X-axis: dates. Y-axis: probability 0-40%
  - Interactive: hover shows crosshair with team name + probability
  - Time range selector pills: "7D", "1M", "Season"
- Below chart: "Biggest Movers" row — 3-5 horizontal pills showing "↑ Thunder +3.2%", "↓ Cavaliers -2.1%" etc.

### 2. Conference Grid (Eastern Conference)
A data table with:
- **Left column (sticky):** Team logo (24px circle) + team abbreviation (3 letters) + current record in muted text. Row background has a very subtle gradient from the team's primary color at 5% opacity on the left edge.
- **Data columns:** "Playoffs" | "R1" | "Conf Semis" | "Conf Finals" | "Champion"
- **Cell contents:**
  - Large: the merged probability as a percentage (e.g., "22%") in JetBrains Mono
  - Small: 2-3 tiny colored dots or 2-letter abbreviations below indicating sources (DK=DraftKings, FD=FanDuel, PM=Polymarket, KA=Kalshi)
  - Cell background: subtle heat-map tint — higher probabilities get a faint green tint, lower get nothing
  - If probability > 50%, the number is slightly brighter/bolder
  - 24h change as a tiny +/- badge in the corner (green up, red down), only shown if |change| > 1%
- **Column headers:** Round names, vertically oriented or abbreviated for mobile
- **Sorted by:** Championship probability descending within each conference
- **Hover state:** Cell expands to show per-source breakdown (source name, probability, last updated)

### 3. Western Conference Grid
Same layout as Eastern, for the other conference.

### Footer
"Sources: DraftKings · FanDuel · BetMGM · Polymarket · Kalshi"
"Last updated: 2 minutes ago"

## Mobile Behavior
- Team column (logo + abbreviation) is sticky on the left
- Data columns scroll horizontally
- Default shows: Conf Finals + Champion columns only
- "Show all rounds ›" toggle expands to full grid
- Cells are slightly smaller (40px) with abbreviations only

## Interactive Details
- Tapping a team row should highlight it and could link to a detail page
- Tapping a cell shows a popover with source breakdown
- The grid should feel like a financial data table — dense but readable
- Consider subtle row hover highlight (white at 3% opacity)

## Design Reference
Think: the data density of a Bloomberg terminal, the polish of Linear, the sports branding of ESPN. Dark mode. No gradients except team color tints. Monospace numbers. Clean borders, generous padding in cells.

Generate the full React component with mock data for 15 NBA teams across both conferences.
```

### Prompt 2: March Madness Bracket Grid

```
Design a dark-mode NCAA March Madness bracket odds grid for "Bain Luck". This shows 68 teams' probability of reaching each round of the tournament.

Same tech stack and color system as before (see previous prompt).

## Key Differences from NBA Grid
1. **Four regions** instead of two conferences: East, West, South, Midwest
2. **More columns:** R64 | R32 | Sweet 16 | Elite 8 | Final Four | Champion
3. **Eliminated teams** shown grayed out with strikethrough probability and actual result (e.g., "Lost R32")
4. **Current round highlight** — the column representing the round being played now has a subtle accent border
5. **Bracket lines** (optional) — faint connector lines between rounds showing potential matchups
6. **Seed numbers** shown before team name (e.g., "1 Duke", "16 Wagner")

## Mobile
Default to showing: Sweet 16 | Final Four | Champion only.
R64 and R32 collapsed behind "Show earlier rounds ›" toggle.

Generate with mock data for 16 teams per region (64 total), with 2-3 already eliminated.
```

### Prompt 3: Grid Cell Source Breakdown Popover

```
Design a popover/tooltip that appears when you tap a cell in a championship odds grid. Dark mode. Same color system.

The popover shows:
- Header: "{Team} — {Round}" (e.g., "Celtics — Championship")
- Large merged probability: "22%"
- Divider
- Source breakdown table:
  | DraftKings  | 21% | 2m ago  |
  | FanDuel     | 22% | 5m ago  |
  | Polymarket  | 24% | 1m ago  |
  | Kalshi      | 20% | 15m ago |
- Each source row has a tiny colored dot (unique per source)
- Trend section: "24h: +1.5% · 7d: +3.2%"
- A tiny sparkline (30px wide) showing 7d trend

The popover should feel like a financial data tooltip — informative but not overwhelming. Max width 240px. Appears above/below the cell with a tiny arrow pointer.
```

---

## CLI Workflow Instructions

### Kickoff Prompt

When moving to Claude Code CLI for implementation, paste this to start each session:

```
I'm starting implementation of the Championship Grids project. Read docs/championship-grids-project.md for the full plan.

The project adds playoff/tournament progression grid pages that show every team's probability of reaching each playoff round, with data from multiple sources (Odds API, Kalshi, Polymarket).

This session, I want to focus on Phase [X]. Here's specifically what I need:

[Describe the specific phase you want to work on]

Key files to understand first:
- docs/championship-grids-project.md (full project plan)
- backend/app/models/models.py (FuturesMarket, FuturesOutcome models)
- backend/app/routes/futures.py (existing futures endpoints)
- backend/app/routes/oscars.py (reference for cross-source aggregation)
- backend/app/routes/golf.py (reference for per-sport landing page)
- backend/app/utils/market_grouping.py (canonical key matching)
- frontend/components/TournamentChart.tsx (trend chart component)
- frontend/components/RelatedFutures.tsx (tier system, source display)

Before writing any code, start by querying the production API to audit what futures market data actually exists:
curl "https://api.bainluck.com/api/futures/debug/sources"
curl "https://api.bainluck.com/api/futures/canonical-keys"
curl "https://api.bainluck.com/api/futures/browse?category=basketball&limit=50"

Then tell me what you find before implementing.
```

### Commit, Push & Deploy Protocol

**After completing each logical unit of work** (a new endpoint, a new component, a migration, a batch of tests), proactively:

1. **Commit** with a descriptive message. Don't wait for me to ask.
2. **Push to master** — both Heroku and Vercel auto-deploy from master. If auto-deploy doesn't trigger, manually deploy:
   - Heroku: `git push heroku master` (or `heroku builds:create -a bainluck` if the remote isn't set up)
   - Vercel: deploys automatically on push; if not, `vercel --prod` from the frontend directory
3. **Verify deployment succeeded** before moving to the next step:
   - **Heroku backend:** `heroku releases -a bainluck --num 1` to check latest release status, then `curl -s https://api.bainluck.com/health/ready | python3 -m json.tool` to confirm the API is live and healthy
   - **Vercel frontend:** `curl -s -o /dev/null -w "%{http_code}" https://bainluck.com` to confirm 200, or check `vercel ls --prod` for deployment status
   - **If a migration was included:** `heroku run "cd backend && alembic current" -a bainluck` to confirm the migration applied
4. **Report deployment status to me** — tell me "Backend deployed and healthy" or "Frontend deployed, confirmed 200" or "Migration applied: abc123". If something failed, diagnose it before moving on.

**Commit cadence guidance:**
- New Alembic migration → commit + push immediately (migrations must apply before new code that depends on them)
- New backend endpoint + tests → commit + push, verify API responds
- New frontend page/component → commit + push, verify page loads
- Bug fix → commit + push + verify the fix is live
- Config-only change (league_configs.py) → can batch with the next code change

**Don't batch too much** — smaller, more frequent deploys are easier to debug when something breaks.

### Progress Updates

After each phase or significant milestone, update the Progress Tracker table at the bottom of this document with status, session count, and brief notes about what shipped. This keeps continuity across sessions.

---

## Phase 0 Data Audit Results (March 17, 2026)

### What We Actually Have in Production

**Total futures markets:** 100,475 (Polymarket 66,781 + Kalshi 33,668 + DataGolf 15 + Odds API 11)

#### NBA — GOOD championship data, SPARSE round-by-round
| Grid Column | Data Available? | Sources | Notes |
|-------------|----------------|---------|-------|
| Champion | **YES** — 30 teams | Polymarket ("2026 NBA Champion"), Kalshi (none found for championship outright) | Main grid column. Cross-source available. |
| Conference Winner | **YES** — 30 teams | Polymarket ("NBA Eastern/Western Conference Champions"), Kalshi ("Pro Basketball Eastern/Western Conference #1 Seed" — but these are #1 seed markets, not conference winner) | Need to distinguish "conference champion" (playoff winner) from "#1 seed" (regular season) |
| Make Playoffs | **YES** — 30 teams | Polymarket ("Which teams will make the NBA Playoffs?"), Kalshi ("Play-in tournament" markets) | Kalshi play-in ≠ make playoffs. Need careful mapping. |
| Division Winner | **NO** | — | No division winner markets found. |
| First Round / Conf Semis | **NO** | — | No round-by-round playoff markets exist yet. These typically appear when playoffs start (~mid-April). |
| NBA Best/Worst Record | **YES** | Polymarket | Bonus column — interesting but not playoff progression. |
| NBA Draft #1 Pick | **YES** | Polymarket | Separate page? |
| Statistical Leaders | **YES** | Polymarket (PPG, RPG, APG, BPG, SPG, 3PT) | Awards section, not grid column. |

**NBA Grid Today (3 columns):** Make Playoffs → Conference Champion → NBA Champion
**NBA Grid in April (5+ columns):** Make Playoffs → First Round → Conf Semis → Conf Finals → NBA Finals → Champion

#### NHL — GOOD championship data, some round-by-round
| Grid Column | Data Available? | Sources | Notes |
|-------------|----------------|---------|-------|
| Stanley Cup Champion | **YES** | Polymarket, Kalshi | Cross-source. |
| Conference Finals | **YES** | Kalshi ("Eastern/Western Conference Finals Winner") | Kalshi only — these are actual conference champion markets. |
| Make Playoffs | **YES** | Polymarket ("Which teams will make the NHL Playoffs?"), Kalshi | Cross-source. |
| Division Winner | **YES** | Odds API (canonical key `hockey:NHL:division_winner:2025-26`) | Odds API only. |
| Stanley Cup Finalists | **YES** | Kalshi ("Stanley Cup Finalists" — which pair will play) | Combo market, not per-team. Hard to use in grid. |
| Awards | **YES** | Kalshi + Polymarket (Hart, Norris, Art Ross, Calder, Jack Adams, Selke, Richard) | Awards section. |

**NHL Grid Today (4 columns):** Make Playoffs → Division Winner → Conference Champion → Stanley Cup

#### NCAA Basketball (March Madness) — **CRITICAL GAP**
| Grid Column | Data Available? | Sources | Notes |
|-------------|----------------|---------|-------|
| Champion | **NO outright found** | — | The search for NCAA championship, March Madness, and Final Four returned ZERO futures markets. |
| Final Four | **NO** | — | |
| Sweet 16 / Elite 8 | **NO** | — | |
| Individual games | **YES** — hundreds | Kalshi (moneylines, spreads, totals, player props) | Game-level only, no tournament progression. |

**🚨 March Madness is the #1 time-sensitive item but we have NO tournament-level data.** The Odds API does have NCAA basketball championship outrights — we need to check if the polling is capturing them. Kalshi and Polymarket may have round-by-round markets that aren't being categorized correctly.

**Action needed:** Investigate whether NCAA tournament outrights are being polled. Check Odds API available markets for `basketball_ncaab` sport key. Manually search Kalshi/Polymarket for "NCAA", "March Madness", "Final Four" markets that may exist but aren't being ingested.

#### Golf — **EXCELLENT** (best coverage of any sport)
| Grid Column | Data Available? | Sources | Notes |
|-------------|----------------|---------|-------|
| Winner | **YES** | Kalshi, Polymarket, DataGolf | All three sources per tournament. |
| Top 5 | **YES** | Kalshi, Polymarket, DataGolf | All three sources. |
| Top 10 | **YES** | Kalshi, Polymarket, DataGolf | All three sources. |
| Top 20 | **YES** | Kalshi, Polymarket, DataGolf | All three sources. |
| Make Cut | **YES** | Kalshi, DataGolf | Two sources. |

**Golf grid is the easiest win — all 5 columns have multi-source data today.**

Current tournaments with data: Valspar Championship (Kalshi + Polymarket + DataGolf), Arnold Palmer Invitational (Kalshi), Puerto Rico Open (Kalshi), LIV Golf Hong Kong (Kalshi), THE PLAYERS Championship (Kalshi partial).

### Data Quality Issues Found

1. **Canonical key grouping is catching non-basketball markets.** The `basketball:NBA:conference_winner:2025-26` key returned Colorado Avalanche, Tampa Bay Lightning, and other NHL teams. The key assignment logic is leaking across sports.
2. **Kalshi "play-in tournament" ≠ "make playoffs"** — these are different concepts. Play-in teams haven't made the playoffs yet.
3. **Kalshi "#1 seed" ≠ "conference champion"** — #1 seed is regular season, conference champion is the playoff winner. Currently grouped under the same canonical key.
4. **Some Polymarket probabilities look wrong** — OKC Thunder at 91.1% for both "NBA Champion" AND "NBA Best Record" AND "NBA Make Playoffs" is suspicious. These are likely separate markets being conflated in the API response, not the same number meaning three different things. Need to verify.
5. **Odds API has only 11 futures markets total.** Very few compared to Kalshi/Polymarket. But Odds API includes multi-bookmaker data (DraftKings, FanDuel, etc.) which is valuable for the grid.
6. **NCAA tournament data appears completely missing** — either not being polled or not being categorized as basketball.

### Revised Priority Order

Given the audit findings:

1. **Golf** — Ship first. All data exists across 3 sources. Evolve the existing `/categories/golf` page into the grid format. Quickest win, proves the architecture.
2. **NBA** — Ship second. 3 columns today (playoffs/conference/champion), expandable to 5+ when playoff round markets appear in April.
3. **NHL** — Ship third. 4 columns today. Similar architecture to NBA.
4. **March Madness** — **BLOCKED on data.** Must first investigate why NCAA tournament markets aren't appearing. If we can fix the data pipeline, this becomes urgent. If the markets simply don't exist on our sources, we need to find alternative data (ESPN BPI projections? Manual entry from sportsbook screenshots?).

---

## Known Data Quality Issues & Action Items

### Champions League Contamination
**Problem:** Kalshi has Champions League *qualification* binary markets (e.g., "Will Paris FC qualify for Champions League?", "Will OH Leuven qualify?", "Will Juventus qualify?"). These are being matched to the soccer championship grid because they contain "Champions League" in the market name. Teams like Paris FC, OH Leuven, and Juventus appear alongside actual Champions League contenders (Real Madrid, Bayern Munich, etc.) — they're qualification markets, not tournament progression markets.

**Root cause:** The market-matching regex for the `championship` column pattern matches any market containing "Champions League" without distinguishing "win Champions League" from "qualify for Champions League".

**Fix options:**
1. **Negative pattern on matching rules** — Add `qualify`, `qualification`, `make` as negative patterns that downgrade or exclude a match from the `championship` column
2. **Canonical team list validation** (see below) — Only include teams that are actually in the tournament roster
3. **Market name refinement** — Require "win" or "winner" in championship-tier pattern matches, not just the league name

**Priority:** Medium — affects soccer grids. Not blocking NBA/NHL/golf.

### Canonical Team List Validation
**Problem:** The grid currently uses bottom-up market discovery — any team that appears in a matching futures market gets a row. This means teams from wrong leagues/tournaments can leak in (Champions League contamination above), and name dedup can fail ("Connecticut" vs "UConn Huskies" appearing as separate rows).

**Proposed solution:** Use authoritative rosters as the source of truth for which teams belong in each grid:
- **Pro leagues (NBA, NHL, NFL, MLB):** ESPN `/teams` endpoint provides the canonical list of teams per league. Only teams on this list get grid rows. Market outcomes are fuzzy-matched to the canonical list.
- **College (NCAA):** ESPN teams endpoint for D1 programs, or tournament bracket once available.
- **Golf:** DataGolf field (already implemented — `_build_golf_grid_from_datagolf()` uses DataGolf as source of truth for which golfers appear).
- **Soccer:** ESPN or UEFA/FIFA tournament rosters for team validation.

**Benefits:**
1. Eliminates cross-league contamination (Paris FC won't appear in Champions League grid if they're not in the tournament)
2. Solves name dedup (canonical name from ESPN, all market variants fuzzy-match to it)
3. Provides team metadata (logos, colors, records) without a separate lookup
4. Already proven for golf — the DataGolf source-of-truth pattern works well

**Implementation:** Add a `team_roster_source` field to `LeagueConfig` (e.g., `"espn"`, `"datagolf"`, `"manual"`) and a function that fetches the canonical team list before building the grid. Market outcomes that don't match any canonical team are excluded.

**Priority:** High for soccer grids (Champions League contamination). Medium for other leagues (less prone to contamination but would improve name dedup).

---

## Open Questions

1. ~~**DataGolf integration:** DataGolf has the best golf probability data (round-by-round, make cut, top 10, etc.) but requires a paid API. Worth investigating pricing and data quality vs. what we get from Odds API.~~ **RESOLVED:** DataGolf integrated as source of truth for golf. API key set up, hourly polling active, `_build_golf_grid_from_datagolf()` uses DataGolf field as canonical golfer list.
2. **Derived probabilities:** When we only have championship odds, should we try to derive intermediate round probabilities using a statistical model? (e.g., MoneyPuck derives "make playoffs" from win probability models, not from a market). This is complex but would fill the grid.
3. **Historical grids:** Should we archive/snapshot grids over time so users can see "NBA playoff odds from 2 weeks ago"? The snapshot infrastructure exists but the grid presentation layer doesn't.
4. **NCAA bracket integration:** Should the March Madness grid show actual bracket position / potential matchups, or just treat it as a flat probability table by region?
5. **Win totals column:** For NBA/NHL/NFL, should we include a "projected wins" or "win total O/U" column alongside the playoff round columns? This is common on sites like FiveThirtyEight.

---

## Progress Tracker

| Phase | Status | Sessions | Notes |
|-------|--------|----------|-------|
| Phase 0: Data Audit & Config | ✅ Complete | 1 (Cowork) | Audit done Mar 17. Golf=excellent, NBA=good, NHL=good, NCAA=BLOCKED. See audit results above. |
| Phase 1: Backend Endpoint | ✅ Complete | 2 | `GET /api/playoffs/{league_slug}` shipped with 13 leagues. League configs in `config/league_configs.py`. Golf uses DataGolf as source of truth (`_build_golf_grid_from_datagolf()`). 140 tests. Deployed and verified on production. |
| Phase 2: Frontend Grid (Web) | 🟡 In Progress | — | Need to rewrite `frontend/app/playoffs/[sport]/page.tsx` to use new API, update TypeScript types, expand from 5 to 13 leagues. |
| Phase 3: March Madness | BLOCKED on data | — | NCAA tournament markets missing from DB. Pipeline investigation needed. |
| Phase 4: Event Detail Integration | Not started | — | |
| Phase 5: iOS Native Grid | Not started | — | |
| Phase 6: Polish & More Leagues | Not started | — | Known issues: Champions League contamination (see action items above), canonical team list validation needed for pro/college leagues. |
