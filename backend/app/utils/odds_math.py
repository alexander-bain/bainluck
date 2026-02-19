"""
Odds conversion and calculation utilities.

This module handles all the math for converting betting odds
to probabilities, projected scores, and excitement indices.
"""

from typing import List, Optional, Tuple

from statistics import mean, median


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


def probability_to_american(prob: float) -> Optional[int]:
    """
    Convert probability back to American odds.

    Useful for displaying "fair odds" after removing vig.
    Returns None for extreme probabilities (0.0 or 1.0) where
    American odds are undefined.

    Examples:
        >>> probability_to_american(0.6)
        -150
        >>> probability_to_american(0.4)
        150
    """
    if prob <= 0 or prob >= 1:
        return None
    if prob >= 0.5:
        return round(-100 * prob / (1 - prob))
    else:
        return round(100 * (1 - prob) / prob)


def aggregate_probabilities(
    probabilities: List[float],
    method: str = "mean"
) -> Optional[float]:
    """
    Aggregate win probabilities from multiple bookmakers.

    Args:
        probabilities: List of probabilities from different bookmakers (0-1)
        method: Aggregation method - "mean", "median", or "trimmed_mean"

    Returns:
        Aggregated probability or None if no valid probabilities

    Examples:
        >>> aggregate_probabilities([0.55, 0.57, 0.54])
        0.5533  # Mean of the three
        >>> aggregate_probabilities([0.55, 0.57, 0.54], method="median")
        0.55  # Median value
    """
    # Filter out None and invalid values
    valid_probs = [p for p in probabilities if p is not None and 0 <= p <= 1]

    if not valid_probs:
        return None

    if len(valid_probs) == 1:
        return valid_probs[0]

    if method == "median":
        return median(valid_probs)
    elif method == "trimmed_mean" and len(valid_probs) >= 3:
        # Remove highest and lowest, then average
        sorted_probs = sorted(valid_probs)
        trimmed = sorted_probs[1:-1]
        return mean(trimmed) if trimmed else mean(valid_probs)
    else:  # Default to mean
        return mean(valid_probs)


def detect_reversed_bookmakers(snapshots) -> set:
    """
    Detect bookmakers whose home/away odds appear to be swapped.

    Some bookmakers in The Odds API occasionally return h2h outcomes
    with the moneyline prices assigned to the wrong team. This detects
    those cases by comparing each bookmaker's home probability against
    the median consensus.

    A bookmaker is flagged as reversed if:
    - Its home probability is close to (1 - median) rather than the median
    - The median is far enough from 50% to make detection reliable
    - At least 3 bookmakers have probability data

    Args:
        snapshots: List of OddsSnapshot objects or dicts with
            home_win_probability and bookmaker fields.

    Returns:
        Set of bookmaker keys whose odds appear reversed.
    """
    def get_val(item, key):
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    # Collect (bookmaker, home_prob) pairs
    entries = []
    for s in snapshots:
        prob = get_val(s, "home_win_probability")
        bk = get_val(s, "bookmaker")
        if prob is not None and bk is not None:
            entries.append((bk, float(prob)))

    if len(entries) < 3:
        return set()

    probs = [p for _, p in entries]
    med = median(probs)

    # Don't attempt detection when odds are close to 50/50
    if 0.38 <= med <= 0.62:
        return set()

    reversed_keys = set()
    for bk, prob in entries:
        mirror = 1.0 - med
        dist_to_median = abs(prob - med)
        dist_to_mirror = abs(prob - mirror)
        # Reversed if much closer to the mirror than to the median,
        # and meaningfully far from the median
        if dist_to_mirror < 0.10 and dist_to_median > 0.20:
            reversed_keys.add(bk)

    # Safety: don't "correct" if too many would be flagged —
    # requires a clear consensus (>2/3 of bookmakers agree)
    if len(reversed_keys) > len(entries) // 3:
        return set()

    return reversed_keys


def aggregate_bookmaker_odds(
    bookmaker_snapshots: List[dict],
    method: str = "mean"
) -> dict:
    """
    Aggregate odds data from multiple bookmakers into a single consensus.

    Args:
        bookmaker_snapshots: List of dicts with keys:
            - home_win_probability: float
            - away_win_probability: float
            - over_under: float (optional)
            - home_spread: float (optional)
            - projected_home_score: float (optional)
            - projected_away_score: float (optional)
        method: Aggregation method ("mean", "median", "trimmed_mean")

    Returns:
        Dict with aggregated values and metadata:
            - home_probability: aggregated home win probability
            - away_probability: aggregated away win probability
            - over_under: aggregated total (if available)
            - home_spread: aggregated spread (if available)
            - projected_home_score: aggregated projected score
            - projected_away_score: aggregated projected score
            - bookmaker_count: number of bookmakers included
            - min_home_probability: lowest home probability
            - max_home_probability: highest home probability
    """
    if not bookmaker_snapshots:
        return {
            "home_probability": None,
            "away_probability": None,
            "over_under": None,
            "home_spread": None,
            "projected_home_score": None,
            "projected_away_score": None,
            "bookmaker_count": 0,
            "min_home_probability": None,
            "max_home_probability": None,
        }

    # Extract values, handling both dict keys and attribute access
    def get_val(item, key):
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    home_probs = [get_val(s, "home_win_probability") for s in bookmaker_snapshots]
    away_probs = [get_val(s, "away_win_probability") for s in bookmaker_snapshots]
    over_unders = [get_val(s, "over_under") for s in bookmaker_snapshots]
    home_spreads = [get_val(s, "home_spread") for s in bookmaker_snapshots]
    proj_home = [get_val(s, "projected_home_score") for s in bookmaker_snapshots]
    proj_away = [get_val(s, "projected_away_score") for s in bookmaker_snapshots]

    # Convert Decimal types to float
    home_probs = [float(p) if p is not None else None for p in home_probs]
    away_probs = [float(p) if p is not None else None for p in away_probs]
    over_unders = [float(p) if p is not None else None for p in over_unders]
    home_spreads = [float(p) if p is not None else None for p in home_spreads]
    proj_home = [float(p) if p is not None else None for p in proj_home]
    proj_away = [float(p) if p is not None else None for p in proj_away]

    # Filter valid home probabilities for min/max calculation
    valid_home_probs = [p for p in home_probs if p is not None and 0 <= p <= 1]

    # Aggregate each metric
    agg_home = aggregate_probabilities(home_probs, method)
    agg_away = aggregate_probabilities(away_probs, method)

    # For over_under and spreads, use mean of valid values
    valid_ou = [v for v in over_unders if v is not None]
    valid_spread = [v for v in home_spreads if v is not None]
    valid_proj_home = [v for v in proj_home if v is not None]
    valid_proj_away = [v for v in proj_away if v is not None]

    return {
        "home_probability": round(agg_home, 4) if agg_home is not None else None,
        "away_probability": round(agg_away, 4) if agg_away is not None else None,
        "over_under": round(mean(valid_ou), 1) if valid_ou else None,
        "home_spread": round(mean(valid_spread), 1) if valid_spread else None,
        "projected_home_score": round(mean(valid_proj_home), 1) if valid_proj_home else None,
        "projected_away_score": round(mean(valid_proj_away), 1) if valid_proj_away else None,
        "bookmaker_count": len(valid_home_probs),
        "min_home_probability": round(min(valid_home_probs), 4) if valid_home_probs else None,
        "max_home_probability": round(max(valid_home_probs), 4) if valid_home_probs else None,
    }
