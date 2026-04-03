# Prompt 3: Win Probability Chart Improvements

**Terminal:** 3 (run AFTER Prompt 1 completes)
**Estimated time:** 4-6 hours
**Risk level:** Medium (new endpoints + new components)
**Depends on:** Prompt 1 (fangraphs → mlb rename must be done first)

---

## Copy this entire prompt into Claude Code CLI:

```
I need you to improve the Win Probability chart system for three use cases: standard games, multi-participant tournaments, and elimination series. Read docs/architecture-improvement-plan.md first for full context.

## Step 1: Fix stat model for college games

The statistical win probability model (compute_statistical_win_prob in backend/app/utils/win_probability.py) currently only runs when ESPN sync provides game_clock and period data. College teams frequently fail ESPN name matching, so the stat model never fires for college games.

Read these files to understand the current flow:
- backend/app/tasks/odds_polling.py (where stat model is called during odds polling)
- backend/app/tasks/espn_sync.py (where stat model is called during ESPN sync)
- backend/app/utils/win_probability.py (the model itself, including estimate_seconds_remaining_from_wall_clock)

The fix: In odds_polling.py, where the stat model is called, ensure that if game_clock is unavailable but the event is live (status in ['live', 'in_progress']), we fall back to estimate_seconds_remaining_from_wall_clock(). This function already exists in win_probability.py.

Check if this fallback is already wired. If it is, verify it works by reading the tests. If it's NOT wired, add it.

Run tests: cd backend && python -m pytest tests/test_win_probability.py -v

## Step 2: Build tournament probability timeline endpoint

Create a new endpoint that returns per-contestant probability over time for multi-outcome futures markets (e.g., golf tournaments).

Data already exists: FuturesOddsSnapshot stores per-bookmaker per-outcome probability history. We just need to aggregate it.

Add to backend/app/routes/futures.py:

GET /api/futures/{market_id}/probability-timeline
  - Query FuturesOddsSnapshot rows for this market's outcomes
  - Aggregate by 1-hour time buckets (for pre-event) or 15-min buckets (for active)
  - Within each bucket, take the median probability across bookmakers for each outcome
  - Return top N outcomes by current probability (default N=10, param ?top=N)
  - Include a "Field" entry that sums all other outcomes' probabilities

Response format:
{
  "market_id": 12345,
  "market_name": "2026 Masters",
  "total_outcomes": 45,
  "showing": 10,
  "timeline": [
    {
      "timestamp": "2026-04-10T12:00:00Z",
      "outcomes": [
        {"name": "Scottie Scheffler", "probability": 0.15, "team_id": null},
        {"name": "Rory McIlroy", "probability": 0.08, "team_id": null},
        ...
        {"name": "Field", "probability": 0.32, "team_id": null}
      ]
    },
    ...
  ]
}

Write tests for this endpoint in backend/tests/test_futures_timeline.py (at least 10 tests):
- Market with no snapshots → empty timeline
- Market with 1 outcome → works
- Market with 50 outcomes → "Field" aggregation correct
- Probabilities sum to ~1.0 in each bucket
- Time bucketing works correctly
- ?top=5 parameter limits outcomes

Run tests: cd backend && python -m pytest tests/test_futures_timeline.py -v

## Step 3: Build TournamentChart frontend component

Create frontend/components/TournamentChart.tsx — a multi-line chart showing contestant probability over time.

Use Recharts (already available). The component should:
- Accept data from the /probability-timeline endpoint
- Render one line per contestant, colored by relative position (1st place = most vivid)
- Use a consistent color palette (10 distinct colors from our design tokens)
- Show tooltip on hover with all contestant probabilities at that timestamp
- Support toggle: "Top 5" / "Top 10" / "All"
- Responsive: full width on mobile, constrained on desktop
- Show "Field" as a dashed gray area at the bottom
- Y-axis: 0% to max probability + 5% padding
- X-axis: time, with labels for significant moments (e.g., "Round 1", "Round 2" for golf)

Import the animations from frontend/lib/animations.ts for the initial fade-in.

For now, this component doesn't need to be wired into any page — just create it as a standalone component that can be imported later. Include a brief usage example in a comment at the top.

Build the frontend: cd frontend && npm run build

## Step 4: Create series probability utility

Create backend/app/utils/series_probability.py:

```python
"""Compute probability of winning a best-of-N series.

Given the probability of winning the current/next game,
and the current series state (games won by each team),
compute the probability each team wins the series.

Uses the negative binomial distribution approach:
Team needs K more wins, opponent needs J more wins.
They play min(K+J-1) more games. Team wins series if
they accumulate K wins before opponent accumulates J wins.
"""
from math import comb

def compute_series_win_prob(
    team_game_win_prob: float,
    team_wins: int,
    opponent_wins: int,
    games_to_win: int = 4,
) -> float:
    """
    Args:
        team_game_win_prob: P(team wins the next game), 0.0-1.0
        team_wins: Games team has won so far (0 to games_to_win-1)
        opponent_wins: Games opponent has won so far
        games_to_win: Games needed to win series (4 for best-of-7, 3 for best-of-5)

    Returns:
        Probability team wins the entire series (0.0-1.0)
    """
    team_needs = games_to_win - team_wins
    opp_needs = games_to_win - opponent_wins

    if team_needs <= 0:
        return 1.0
    if opp_needs <= 0:
        return 0.0
    if not (0.0 <= team_game_win_prob <= 1.0):
        return 0.5  # fallback for invalid input

    p = team_game_win_prob
    q = 1.0 - p

    # Total remaining games possible
    remaining = team_needs + opp_needs - 1

    # Sum probability of team winning exactly k games out of remaining,
    # where k >= team_needs. The series ends when either team hits their target,
    # so we use the "negative binomial" formulation:
    # P(series win) = sum over i in [team_needs..remaining] of
    #   C(i-1, team_needs-1) * p^team_needs * q^(i-team_needs)
    # Wait — more precisely, the last game must be a win:
    prob = 0.0
    for total_games in range(team_needs, remaining + 1):
        # Team wins `team_needs` games total in `total_games` games
        # Last game must be a win (clinch), so choose team_needs-1 wins
        # from the first total_games-1 games
        losses = total_games - team_needs
        prob += comb(total_games - 1, team_needs - 1) * (p ** team_needs) * (q ** losses)

    return min(1.0, max(0.0, prob))


def series_state_label(
    team_name: str,
    opponent_name: str,
    team_wins: int,
    opponent_wins: int,
    games_to_win: int = 4,
) -> str:
    """Human-readable series state.

    Examples:
        "Celtics lead 3-2"
        "Series tied 2-2"
        "Warriors trail 1-3"
        "Celtics win series 4-2"
    """
    if team_wins >= games_to_win:
        return f"{team_name} win series {team_wins}-{opponent_wins}"
    if opponent_wins >= games_to_win:
        return f"{opponent_name} win series {opponent_wins}-{team_wins}"
    if team_wins > opponent_wins:
        return f"{team_name} lead {team_wins}-{opponent_wins}"
    if opponent_wins > team_wins:
        return f"{team_name} trail {team_wins}-{opponent_wins}"
    return f"Series tied {team_wins}-{opponent_wins}"
```

Write comprehensive tests in backend/tests/test_series_probability.py (at least 20 tests):
- Series tied 0-0, 50% game win prob → ~50% series win prob
- Series tied 0-0, 60% game win prob → >60% series win prob (amplification)
- Up 3-0 → very high probability regardless of game win prob
- Down 0-3 → very low probability
- 3-2 lead, 50% per game → ~75% series win
- Clinched (4-x) → 1.0
- Lost (x-4) → 0.0
- Edge cases: 0% game win prob, 100% game win prob
- Best-of-5 series (games_to_win=3)
- Best-of-3 series (games_to_win=2)
- Best-of-1 (games_to_win=1) → just the game probability
- Label function tests for all states

Run tests: cd backend && python -m pytest tests/test_series_probability.py -v

## Step 5: Remove MoneyPuck stub from source registry

In backend/app/config/win_prob_sources.py, either:
a) Delete the "moneypuck" entry entirely, OR
b) Add a comment: # STUB — no integration built yet. Do not display in frontend.

And ensure the frontend doesn't try to render a MoneyPuck line with no data.

Grep for "moneypuck" across the entire codebase:
  grep -r "moneypuck" backend/ frontend/ --include="*.py" --include="*.ts" --include="*.tsx" --include="*.swift"

Remove or comment out any references. If the iOS app references it, leave a TODO comment rather than changing Swift files from here.

## Final verification

Run all backend tests: cd backend && python -m pytest tests/ -v
Run frontend build: cd frontend && npm run build

Report results.
Do NOT commit — I will review and commit manually.
```
