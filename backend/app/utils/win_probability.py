"""
Statistical win probability model.

Based on the methodology from Pro-Football-Reference / nflfastR:
  - Final margin of victory is modeled as a normal distribution
  - Mean = pregame spread scaled by remaining time + current score differential
  - Std dev = base std dev × sqrt(fraction of game remaining)
  - Win probability = P(margin > 0) using the normal CDF

This gives an independent probability estimate from game state alone,
complementing market-implied odds and ESPN's proprietary model.

Sport-specific parameters:
  - NFL/NCAAF: base_std = 13.45 (from Hal Stern's research, 1978-2012 NFL data)
  - NBA/NCAAB: base_std = 12.0 (estimated from final margin distributions)
  - NHL: base_std = 2.5 (low-scoring sport, tighter margins)
  - MLB: Not well-suited to this model (inning-based, not clock-based)
"""

import math
from typing import Optional

from app.utils.sport_keys import (
    ODDS_API_TO_WIN_PROB_KEY as _SPORT_KEY_ALIASES,  # noqa: F401 — re-exported for tests
    normalize_to_win_prob_key as _normalize_sport_key,  # noqa: F401 — re-exported for tests
)


# Standard normal CDF using math.erfc (no scipy needed)
def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * math.erfc(-x / math.sqrt(2))


# Sport-specific parameters
SPORT_PARAMS = {
    # (base_std_dev, total_game_seconds)
    "football_nfl": (13.45, 3600),      # 60 minutes
    "football_ncaaf": (13.45, 3600),     # 60 minutes
    "basketball_nba": (12.0, 2880),      # 48 minutes
    "basketball_ncaab": (12.0, 2400),    # 40 minutes
    "basketball_wncaab": (12.0, 2880),   # 40 minutes (4x10 quarters)
    "hockey_nhl": (2.5, 3600),           # 60 minutes
}


def parse_game_clock(clock_str: str | None, period: str | None, sport_key: str) -> float | None:
    """
    Parse game clock and period into total seconds remaining.

    Returns None if the game state can't be parsed.
    """
    if not clock_str or not period:
        return None

    sport_key = _normalize_sport_key(sport_key)
    params = SPORT_PARAMS.get(sport_key)
    if not params:
        return None

    _, total_seconds = params

    # Parse clock string "MM:SS" or "M:SS"
    try:
        parts = clock_str.strip().split(":")
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            clock_seconds = minutes * 60 + seconds
        else:
            return None
    except (ValueError, IndexError):
        return None

    # Parse period to determine how many periods are left
    period_lower = period.lower().strip()

    # Extract numeric period from various formats: "1", "Q1", "q2", etc.
    period_num = None
    if period_lower.isdigit():
        period_num = int(period_lower)
    elif len(period_lower) == 2 and period_lower[0] in ("q", "p") and period_lower[1].isdigit():
        period_num = int(period_lower[1])

    def _match_period(n: int, ordinal: str) -> bool:
        """Check if period matches a given period number or ordinal string."""
        return period_num == n or ordinal in period_lower

    if sport_key.startswith("football_"):
        # NFL/NCAAF: Q1-Q4, each 15 minutes (900s)
        period_seconds = 900
        if _match_period(1, "1st"):
            periods_remaining_after = 3
        elif _match_period(2, "2nd"):
            periods_remaining_after = 2
        elif _match_period(3, "3rd"):
            periods_remaining_after = 1
        elif _match_period(4, "4th"):
            periods_remaining_after = 0
        elif "ot" in period_lower or "overtime" in period_lower or (period_num is not None and period_num >= 5):
            # OT: treat as ~2.5 min remaining, low variance
            return 150
        elif "half" in period_lower:
            # Halftime: start of Q3
            return 1800
        else:
            return None
        return periods_remaining_after * period_seconds + clock_seconds

    elif sport_key.startswith("basketball_"):
        if sport_key == "basketball_ncaab":
            # NCAA men's: 2 halves of 20 minutes each
            if _match_period(1, "1st"):
                return 1200 + clock_seconds  # 20 min of 2nd half + current clock
            elif _match_period(2, "2nd"):
                return clock_seconds
            elif "ot" in period_lower or "overtime" in period_lower or (period_num is not None and period_num >= 3):
                return clock_seconds  # OT is just current clock
            elif "half" in period_lower:
                return 1200
            else:
                return None
        else:
            # NBA / WNCAAB: 4 quarters of 12 minutes (720s each)
            period_seconds = 720
            if _match_period(1, "1st"):
                periods_remaining_after = 3
            elif _match_period(2, "2nd"):
                periods_remaining_after = 2
            elif _match_period(3, "3rd"):
                periods_remaining_after = 1
            elif _match_period(4, "4th"):
                periods_remaining_after = 0
            elif "ot" in period_lower or "overtime" in period_lower or (period_num is not None and period_num >= 5):
                return clock_seconds
            elif "half" in period_lower:
                return 1440
            else:
                return None
            return periods_remaining_after * period_seconds + clock_seconds

    elif sport_key.startswith("hockey_"):
        # NHL: 3 periods of 20 minutes (1200s each)
        period_seconds = 1200
        if _match_period(1, "1st"):
            periods_remaining_after = 2
        elif _match_period(2, "2nd"):
            periods_remaining_after = 1
        elif _match_period(3, "3rd"):
            periods_remaining_after = 0
        elif "ot" in period_lower or "overtime" in period_lower or (period_num is not None and period_num >= 4):
            return clock_seconds
        elif "intermission" in period_lower:
            if "1st" in period_lower:
                return 2400
            elif "2nd" in period_lower:
                return 1200
            else:
                return 1200
        else:
            return None
        return periods_remaining_after * period_seconds + clock_seconds

    return None


def estimate_seconds_remaining_from_wall_clock(
    commence_time: "datetime | None",
    sport_key: str,
    now: "datetime | None" = None,
) -> float | None:
    """
    Estimate seconds remaining from wall-clock elapsed time.

    This is a fallback for when ESPN sync doesn't provide game clock/period
    (e.g., college teams that fail name matching). Uses average real-time
    game durations which are longer than clock time due to stoppages.

    Returns None if game hasn't started, sport isn't supported, or
    the estimated time remaining is negative (game likely over).
    """
    if not commence_time:
        return None

    sport_key = _normalize_sport_key(sport_key)
    params = SPORT_PARAMS.get(sport_key)
    if not params:
        return None

    _, total_game_seconds = params

    # Average real-time duration of games (including stoppages, halftime, etc.)
    # These are deliberately conservative (longer) to avoid prematurely
    # declaring games over — it's better to slightly overestimate remaining time.
    _WALL_CLOCK_DURATIONS = {
        "football_nfl": 11700,      # ~3h 15m (NFL average ~3h 12m)
        "football_ncaaf": 12600,    # ~3h 30m (college games run longer)
        "basketball_nba": 9000,     # ~2h 30m (NBA average ~2h 15m)
        "basketball_ncaab": 8100,   # ~2h 15m
        "basketball_wncaab": 8100,  # ~2h 15m
        "hockey_nhl": 9000,         # ~2h 30m (NHL average ~2h 20m)
    }

    wall_duration = _WALL_CLOCK_DURATIONS.get(sport_key)
    if not wall_duration:
        return None

    if now is None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

    elapsed_wall = (now - commence_time).total_seconds()
    if elapsed_wall < 0:
        return None  # Game hasn't started yet

    # Map wall-clock progress to game-clock progress
    # wall_fraction is how far through the real-time duration we are
    wall_fraction = min(elapsed_wall / wall_duration, 1.0)

    # Convert to game seconds remaining
    game_seconds_remaining = total_game_seconds * (1.0 - wall_fraction)

    # Don't return negative or essentially-zero values
    if game_seconds_remaining < 1.0:
        return None

    return game_seconds_remaining


def compute_statistical_win_prob(
    home_score: int,
    away_score: int,
    clock: str | None,
    period: str | None,
    sport_key: str,
    pregame_spread: float | None = None,
    commence_time: "datetime | None" = None,
) -> float | None:
    """
    Compute home team win probability from current game state.

    Args:
        home_score: Current home team score
        away_score: Current away team score
        clock: Game clock string (e.g., "4:32")
        period: Period string (e.g., "Q4", "2nd Half")
        sport_key: Sport key (e.g., "football_nfl")
        pregame_spread: Pregame Vegas spread (negative = home favored).
                       If None, assumes 0 (pick'em).
        commence_time: Game start time (UTC). Used as fallback when
                      clock/period aren't available — estimates remaining
                      time from wall-clock elapsed time.

    Returns:
        Home win probability (0.0-1.0) or None if game state can't be parsed.
    """
    sport_key = _normalize_sport_key(sport_key)
    params = SPORT_PARAMS.get(sport_key)
    if not params:
        return None

    base_std, total_seconds = params

    seconds_remaining = parse_game_clock(clock, period, sport_key)
    if seconds_remaining is None and commence_time is not None:
        # Fallback: estimate from wall-clock elapsed time
        seconds_remaining = estimate_seconds_remaining_from_wall_clock(
            commence_time, sport_key
        )
    if seconds_remaining is None:
        return None

    # Fraction of game remaining (0 = game over, 1 = just started)
    fraction_remaining = max(seconds_remaining / total_seconds, 0.001)

    # Current score differential (positive = home leading)
    score_diff = home_score - away_score

    # Pregame spread: negative means home is favored by that many points
    # Scale the spread by remaining fraction (as the game progresses,
    # the pregame expectation matters less)
    spread = pregame_spread if pregame_spread is not None else 0.0

    # Expected final margin for home team:
    # = current_lead + (expected_remaining_margin_from_spread)
    # The remaining expected margin is the spread scaled by remaining time
    expected_remaining = -spread * fraction_remaining  # negative spread = home favored = positive expected margin
    expected_final_margin = score_diff + expected_remaining

    # Standard deviation scales with sqrt of remaining fraction
    std_dev = base_std * math.sqrt(fraction_remaining)

    # Edge case: if game is essentially over, use deterministic result
    if std_dev < 0.01:
        if score_diff > 0:
            return 1.0
        elif score_diff < 0:
            return 0.0
        else:
            return 0.5

    # P(home wins) = P(final_margin > 0) = Φ(expected_final_margin / std_dev)
    win_prob = _norm_cdf(expected_final_margin / std_dev)

    # Clamp to reasonable range
    return max(0.001, min(0.999, win_prob))
