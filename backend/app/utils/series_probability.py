"""Series win probability computation.

Computes the probability of a team winning a best-of-N series given:
- Their probability of winning each remaining game
- Current series score (games won by each side)

Uses the negative binomial distribution: the probability that one side
reaches the required number of wins before the other.
"""

from math import comb
from typing import Optional


def compute_series_win_prob(
    team_win_prob_this_game: float,
    team_games_won: int,
    opponent_games_won: int,
    games_to_win: int = 4,
) -> float:
    """Compute probability of winning a best-of-N series.

    Uses the negative binomial distribution: given P(win each remaining game),
    what's P(reaching `games_to_win` before opponent does)?

    The team must win exactly `team_needs` of the remaining games,
    and the final game must be a win (clinch game). This is equivalent to:
    P = sum over k from (team_needs-1) to (total_remaining-1) of
        C(k, team_needs-1) * p^team_needs * (1-p)^(k - team_needs + 1)

    Args:
        team_win_prob_this_game: Probability of winning each remaining game (0-1)
        team_games_won: Games won by the team so far
        opponent_games_won: Games won by the opponent so far
        games_to_win: Number of wins needed to win the series (4 for best-of-7)

    Returns:
        Probability of winning the series (0-1)

    Raises:
        ValueError: If inputs are invalid
    """
    if not 0.0 <= team_win_prob_this_game <= 1.0:
        raise ValueError(
            f"team_win_prob_this_game must be between 0 and 1, got {team_win_prob_this_game}"
        )
    if team_games_won < 0 or opponent_games_won < 0:
        raise ValueError("Games won cannot be negative")
    if games_to_win < 1:
        raise ValueError("games_to_win must be at least 1")

    team_needs = games_to_win - team_games_won
    opp_needs = games_to_win - opponent_games_won

    # Already won
    if team_needs <= 0:
        return 1.0
    # Already lost
    if opp_needs <= 0:
        return 0.0

    p = team_win_prob_this_game
    # Maximum remaining games: team_needs + opp_needs - 1
    # (one side will clinch before all are played)
    total_remaining = team_needs + opp_needs - 1

    # Sum over all scenarios where the team wins exactly `team_needs` games
    # The last game played must be a win (clinch), so we choose
    # (team_needs - 1) wins from the first (k) games, then win game k+1.
    prob = 0.0
    for games_before_clinch in range(team_needs - 1, total_remaining):
        # Team wins (team_needs - 1) of the first `games_before_clinch` games
        # then wins the clinch game
        losses = games_before_clinch - (team_needs - 1)
        prob += (
            comb(games_before_clinch, team_needs - 1)
            * (p ** team_needs)
            * ((1 - p) ** losses)
        )

    return prob


def series_state_label(
    team_games_won: int,
    opponent_games_won: int,
    games_to_win: int = 4,
    team_name: Optional[str] = None,
) -> str:
    """Generate a human-readable series state label.

    Examples:
        "Series tied 2-2"
        "Lakers lead 3-1"
        "Team leads 3-2"
        "Lakers win series 4-2"

    Args:
        team_games_won: Games won by the team
        opponent_games_won: Games won by the opponent
        games_to_win: Number of wins needed to clinch
        team_name: Optional team name (defaults to "Team")

    Returns:
        Human-readable series state string
    """
    name = team_name or "Team"

    if team_games_won >= games_to_win:
        return f"{name} win series {team_games_won}-{opponent_games_won}"
    if opponent_games_won >= games_to_win:
        return f"{name} lose series {team_games_won}-{opponent_games_won}"
    if team_games_won == opponent_games_won:
        return f"Series tied {team_games_won}-{opponent_games_won}"
    if team_games_won > opponent_games_won:
        return f"{name} lead {team_games_won}-{opponent_games_won}"
    return f"{name} trail {team_games_won}-{opponent_games_won}"
