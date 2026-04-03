# Prompt B: Win Probability Chart — Make It Flawless

## Context

You are working on Bain Luck, a sports odds visualization app. Read `CLAUDE.md` for full context.

The win probability chart is the most important visual on the site. It appears on:
1. **Event detail pages** (`/events/[id]`) — two-team game chart (OddsChart.tsx)
2. **Futures detail pages** (`/futures/[id]`) — multi-outcome tournament chart (TournamentChart.tsx)

Both chart types are functional but need polish to feel "flawless." This prompt addresses specific visual and UX issues.

## Step 1: OddsChart.tsx — Two-Team Game Chart Polish

Read `frontend/components/OddsChart.tsx` carefully.

### 1a. Team-colored area fill under the probability line

Currently the chart shows lines but no fill. Add a subtle gradient fill between the line and 50%:

The home team line should have a transparent gradient fill from the line down to 50% (using the home team's primary color at ~10% opacity). The away team line should have the same from 50% up. This creates a visual "territory" effect — you can see at a glance which team is winning.

Implementation approach:
- Create an SVG `<linearGradient>` with the team color at 10% opacity at the top, fading to 0% at 50%
- Add an `<area>` path below the home probability line, bounded at y=50%
- The area should only fill the space between the line and 50% (not below 50%)

### 1b. Current probability callout

At the rightmost point of the chart (current time), add a prominent callout:
- A dot (8px circle) at the current probability
- A small label next to it showing the current probability percentage
- Use the team's primary color for the dot
- Only show for live games (not completed)

### 1c. "Lead changed" markers

The EI metadata includes `lead_changes` count. When the probability crosses 50%, that's a lead change. Mark these on the chart:
- Small diamond shape (◆) at the 50% line where crossings occur
- Subtle, don't overwhelm — use `text-muted` color at 60% opacity
- Tooltip on hover: "Lead change"

### 1d. Tooltip improvements

The current tooltip should show:
- Time (already there)
- Home team probability with team color dot
- Away team probability with team color dot
- If multiple sources visible: show each source's value
- Score at that moment (if available from score_snapshots)

Format probabilities as whole percentages: "65%" not "0.6534"

### 1e. Chart empty state

When there's no chart data (pre-game, or very new event), show a meaningful empty state instead of nothing:
```tsx
<div className="flex flex-col items-center justify-center h-48 text-text-muted">
  <svg className="w-12 h-12 mb-3 opacity-30" /* simple chart icon */ />
  <p className="text-sm">Probability chart will appear when the game starts</p>
  <p className="text-xs mt-1 text-text-muted/60">Data updates every 30 seconds during live games</p>
</div>
```

## Step 2: TournamentChart.tsx — Multi-Outcome Chart Polish

Read `frontend/components/TournamentChart.tsx` carefully. This renders on futures detail pages for markets with many outcomes (golf tournaments, championship races, award predictions).

### 2a. Leader emphasis

The current leader's line should be visually distinct:
- **Thicker stroke** (already 2.5px — confirm this is working)
- **Bolder color** — increase opacity to 100% while non-leaders stay at 70%
- **Name label at the right edge** of the chart next to their line (small, same color as the line)

### 2b. Interactive hover with crosshair

When hovering over the chart:
- Vertical line at the cursor position (dashed, subtle)
- Tooltip showing ALL visible outcomes' probabilities at that timestamp
- Outcomes sorted by probability (highest first) in the tooltip
- Each outcome has its color dot next to the name
- "Field" shown at the bottom in gray

Verify this crosshair behavior is working correctly. If it exists but is buggy, fix it.

### 2c. Outcome toggle interaction

The Top 5 / Top 10 / All toggle should animate transitions:
- When switching from Top 5 to Top 10, the existing 5 lines should stay, and 5 new lines should fade in
- When switching from Top 10 to Top 5, the removed lines should fade out
- The "Field" area should smoothly resize

### 2d. Link from category pages

The golf category page (`/categories/golf`) and other category pages should link to the TournamentChart. On the futures card in category pages, if the market has >10 outcomes, show a small "View chart →" link that goes to `/futures/[id]#chart`.

To make the anchor work, add `id="chart"` to the chart section container in the futures detail page.

## Step 3: Series Probability Display

Read `backend/app/utils/series_probability.py`. The math is implemented. Now surface it.

### 3a. Create a SeriesProbability component

Create `frontend/components/SeriesProbability.tsx`:

```tsx
interface SeriesProbabilityProps {
  teamName: string;
  opponentName: string;
  teamGamesWon: number;
  opponentGamesWon: number;
  gamesToWin: number;         // 4 for best-of-7
  currentGameWinProb: number; // e.g., 0.62
  teamColor?: string;
  opponentColor?: string;
}
```

This component should:
- Call the backend series probability endpoint (or compute client-side — the math is simple enough for JS)
- Show: "Series: [Team] leads 3-1" as a header
- Show: "P(win series) = 87%" in a prominent number
- Show a mini table of scenarios:
  - "Win tonight → 100% (clinch)"
  - "Lose tonight → 73% (up 3-2)"
- Use team colors for the probability display

For client-side computation (preferred — avoids an API call):

```tsx
function computeSeriesWinProb(
  gameWinProb: number,
  teamWins: number,
  oppWins: number,
  gamesToWin: number = 4
): number {
  const teamNeeds = gamesToWin - teamWins;
  const oppNeeds = gamesToWin - oppWins;

  if (teamNeeds <= 0) return 1.0;
  if (oppNeeds <= 0) return 0.0;

  const totalRemaining = teamNeeds + oppNeeds - 1;
  let prob = 0;

  for (let totalGames = teamNeeds; totalGames <= totalRemaining; totalGames++) {
    const losses = totalGames - teamNeeds;
    // C(totalGames-1, teamNeeds-1) * p^teamNeeds * (1-p)^losses
    const coeff = comb(totalGames - 1, teamNeeds - 1);
    prob += coeff * Math.pow(gameWinProb, teamNeeds) * Math.pow(1 - gameWinProb, losses);
  }

  return prob;
}

function comb(n: number, k: number): number {
  if (k > n) return 0;
  if (k === 0 || k === n) return 1;
  let result = 1;
  for (let i = 0; i < k; i++) {
    result = result * (n - i) / (i + 1);
  }
  return result;
}
```

### 3b. Show SeriesProbability on event detail pages

Read `frontend/app/events/[id]/page.tsx`.

During NBA Playoffs, NHL Playoffs, World Series, and other best-of-N series, the event detail page should show the SeriesProbability component. Detection:
- The event's `llm_importance` is "playoff" or "championship"
- The sport is basketball_nba, icehockey_nhl, or baseball_mlb
- A related futures market exists with "series" or the two team names

For now, this can be a manual/semi-automatic feature. Add the component to the event detail page layout, positioned between the chart and the related futures section. If the series data isn't available (regular season, or can't determine series state), simply don't render it.

The series state (games won by each team) would need to come from an API. For now, create the component and have it accept props. The wiring to detect series state automatically can come later. Show it with placeholder data if the event is a playoff game so we can verify the visual works.

### 3c. Win probability source legend improvements

On the event detail page, the chart legend shows source labels (Betting Odds, ESPN, Kalshi, etc.). Improve:
- Each label should have a colored line swatch (not just a dot) matching the chart line style (solid, dashed, etc.)
- Add a subtle "(model)" or "(market)" tag after each source name to help users understand the difference
- The legend should be horizontally scrollable on mobile if there are 4+ sources

## Verification

After all changes:
1. `cd frontend && npx next build` — zero errors
2. Open any live game event detail — chart should have team-colored area fills and current probability callout
3. Open a multi-outcome futures page (golf tournament or championship race) — TournamentChart should have leader labels and smooth toggle transitions
4. Open a playoff game (NBA/NHL) — SeriesProbability component should render (even with placeholder data)
5. Check mobile — charts should be touch-friendly, tooltips should work

**Do NOT commit. Leave changes unstaged for review.**
