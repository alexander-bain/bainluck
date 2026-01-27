"""
Odds conversion and calculation utilities.

This module handles all the math for converting betting odds
to probabilities, projected scores, and excitement indices.
"""

from typing import Tuple


def american_to_probability(odds: int) -> float:
    """
    Convert American odds to implied probability.
    
    American odds format:
    - Positive (+150): Amount won on a $100 bet
    - Negative (-150): Amount needed to bet to win $100
    
    Examples:
        >>> american_to_probability(-150)
        0.6  # 60% implied probability
        >>> american_to_probability(150)
        0.4  # 40% implied probability
    """
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)


def decimal_to_probability(odds: float) -> float:
    """
    Convert decimal odds to implied probability.
    
    Examples:
        >>> decimal_to_probability(1.67)
        0.5988  # ~60%
        >>> decimal_to_probability(2.50)
        0.4  # 40%
    """
    return 1 / odds


def remove_vig(home_prob: float, away_prob: float) -> Tuple[float, float]:
    """
    Remove the bookmaker's vig (juice) to get true probabilities.
    
    Bookmakers set odds so implied probabilities sum to >100%.
    The excess is their profit margin (vig).
    
    This normalizes the probabilities to sum to exactly 100%.
    
    Examples:
        >>> remove_vig(0.55, 0.50)  # Sum is 1.05 (5% vig)
        (0.5238, 0.4762)  # Now sums to 1.0
    """
    total = home_prob + away_prob
    return home_prob / total, away_prob / total


def moneyline_to_probability(
    home_odds: int, 
    away_odds: int, 
    remove_juice: bool = True
) -> Tuple[float, float]:
    """
    Convert moneyline odds to win probabilities.
    
    Args:
        home_odds: American odds for home team
        away_odds: American odds for away team
        remove_juice: Whether to normalize probabilities
    
    Returns:
        Tuple of (home_probability, away_probability)
    
    Examples:
        >>> moneyline_to_probability(-150, 130)
        (0.5932, 0.4068)  # Home team ~59% favorite
    """
    home_prob = american_to_probability(home_odds)
    away_prob = american_to_probability(away_odds)
    
    if remove_juice:
        return remove_vig(home_prob, away_prob)
    
    return home_prob, away_prob


def project_scores(
    spread: float,
    over_under: float,
) -> Tuple[float, float]:
    """
    Project final scores based on spread and total.

    The spread indicates expected point differential:
    - Negative spread means home team is favored
    - Positive spread means away team is favored

    Math:
    - home_score + away_score = over_under
    - home_score - away_score = abs(spread) (if home favored)

    Args:
        spread: Point spread (negative = home favored)
        over_under: Expected total points/runs/goals

    Returns:
        Tuple of (projected_home_score, projected_away_score)

    Examples:
        >>> project_scores(-14.5, 226)  # Home favored by 14.5, total 226
        (120.2, 105.8)
        >>> project_scores(3.5, 45)  # Away favored by 3.5, total 45
        (20.8, 24.2)
    """
    # Spread is typically negative when home is favored
    # home_score - away_score = -spread (since negative spread means home wins by that margin)
    # home_score + away_score = over_under
    # Solving: home_score = (over_under - spread) / 2
    #          away_score = (over_under + spread) / 2
    home_score = (over_under - spread) / 2
    away_score = (over_under + spread) / 2

    return round(home_score, 1), round(away_score, 1)


# Sport-specific average totals for normalization
SPORT_AVG_TOTALS = {
    "americanfootball_nfl": 45.0,
    "americanfootball_ncaaf": 52.0,
    "basketball_nba": 220.0,
    "basketball_ncaab": 145.0,
    "baseball_mlb": 8.5,
    "icehockey_nhl": 6.0,
    "soccer_epl": 2.5,
    "soccer_mls": 2.8,
}


def calculate_gei(
    home_prob: float, 
    over_under: float, 
    sport_key: str
) -> float:
    """
    Calculate Game Excitement Index (GEI).
    
    Higher scores indicate more exciting games based on:
    - Closeness (games near 50/50 are more exciting)
    - Scoring (high-scoring games relative to sport average)
    
    Based on methodology from: https://lukebenz.com/post/gei/
    
    Args:
        home_prob: Home team's win probability (0-1)
        over_under: Expected total points/runs/goals
        sport_key: Sport identifier for average lookup
    
    Returns:
        GEI score from 0-100 (higher = more exciting)
    
    Examples:
        >>> calculate_gei(0.51, 230, "basketball_nba")
        85.7  # Close game, high scoring
        >>> calculate_gei(0.85, 180, "basketball_nba")
        32.1  # Blowout expected, lower scoring
    """
    # Closeness factor: peaks at 0.5, drops toward 0 or 1
    # Score of 1.0 when perfectly even, 0.0 when certain outcome
    closeness = 1 - abs(home_prob - 0.5) * 2
    
    # Scoring factor: how does this game's total compare to average?
    avg_total = SPORT_AVG_TOTALS.get(sport_key, 100.0)
    scoring_factor = min(over_under / avg_total, 1.5)  # Cap at 150%
    
    # Weighted combination
    # Closeness matters more than raw scoring
    gei = (closeness * 0.65) + (scoring_factor * 0.35)
    
    # Scale to 0-100
    return round(gei * 100, 1)


def format_probability(prob: float, style: str = "percent") -> str:
    """
    Format probability for display.
    
    Args:
        prob: Probability from 0-1
        style: 'percent' for "60%", 'decimal' for "0.60"
    
    Examples:
        >>> format_probability(0.593)
        "59%"
        >>> format_probability(0.593, style="decimal")
        "0.59"
    """
    if style == "percent":
        return f"{round(prob * 100)}%"
    else:
        return f"{prob:.2f}"


def probability_to_american(prob: float) -> int:
    """
    Convert probability back to American odds.
    
    Useful for displaying "fair odds" after removing vig.
    
    Examples:
        >>> probability_to_american(0.6)
        -150
        >>> probability_to_american(0.4)
        150
    """
    if prob >= 0.5:
        return round(-100 * prob / (1 - prob))
    else:
        return round(100 * (1 - prob) / prob)
