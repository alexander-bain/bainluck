"""
Statistical win probability model.

Clock sports (NFL, NBA, NHL):
  Based on the methodology from Pro-Football-Reference / nflfastR:
  - Final margin modeled as normal distribution
  - Mean = pregame spread scaled by remaining time + current score differential
  - Std dev = base std dev × sqrt(fraction of game remaining)
  - Win probability = P(margin > 0) using the normal CDF

Baseball (MLB and all baseball):
  Based on Poisson run-scoring distributions (Tom Tango / "The Book"):
  - Remaining runs for each team modeled as Poisson(λ)
  - λ = runs_per_half_inning × half_innings_remaining_for_team
  - Normal approximation: final margin ~ N(score_diff + λ_home - λ_away, λ_home + λ_away)
  - Accounts for home field advantage and walk-off rule
  - Works for MLB, NCAA baseball, WBC, etc.

Sport-specific parameters:
  - NFL/NCAAF: base_std = 13.45 (from Hal Stern's research, 1978-2012 NFL data)
  - NBA/NCAAB: base_std = 12.0 (estimated from final margin distributions)
  - NHL: base_std = 2.5 (low-scoring sport, tighter margins)
  - MLB: Poisson-based (runs_per_half_inning ≈ 0.5, derived from ~4.5 R/G avg)
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
    # (base_std_dev, total_game_units)
    # Clock sports: total_game_units = total seconds
    "football_nfl": (13.45, 3600),      # 60 minutes
    "football_ncaaf": (13.45, 3600),    # 60 minutes
    "basketball_nba": (12.0, 2880),     # 48 minutes
    "basketball_ncaab": (12.0, 2400),   # 40 minutes
    "basketball_wncaab": (12.0, 2880),  # 40 minutes (4x10 quarters)
    "hockey_nhl": (2.5, 3600),          # 60 minutes
    # Inning sports: total_game_units = total outs (9 innings × 6 outs/inning)
    # All baseball keys use Poisson model (dispatched by sport_key.startswith("baseball_"))
    # These entries are fallback for wall-clock estimation when period info is unavailable
    "baseball_mlb": (4.0, 54),              # 54 outs in regulation
    "baseball_mlb_preseason": (4.0, 54),    # Same rules as regular season
    "baseball_ncaa": (4.0, 54),             # NCAA baseball: 9 innings
}


def parse_mlb_inning(period_str: str | None) -> float | None:
    """
    Parse MLB inning/half info into outs remaining (0-54 scale).

    Thin wrapper around parse_baseball_state() for backward compatibility
    with parse_game_clock().
    """
    state = parse_baseball_state(period_str)
    if state is None:
        return None
    return state["outs_remaining"]


def parse_baseball_state(period_str: str | None) -> dict | None:
    """
    Parse baseball inning/half info into structured game state.

    Handles formats from ESPN and StatPal:
      - "Top 5th", "Bot 7th", "Mid 3rd", "End 6th"
      - "Top 5", "Bottom 7", "T5", "B7"
      - Numeric period with no half info (assumes mid-inning)

    Returns dict with:
      - inning: int (1-based)
      - is_top: bool | None (True=top/away batting, False=bottom/home batting)
      - outs_in_half: float (estimated outs completed in current half-inning)
      - home_half_innings_remaining: float
      - away_half_innings_remaining: float
      - outs_remaining: float (total, for backward compat)
    Or None if unparsable.
    """
    import re

    if not period_str:
        return None

    p = period_str.strip().lower()

    # Detect half: top (away batting) vs bottom (home batting)
    is_top = None
    is_mid = False  # between halves
    is_end = False  # between innings

    if p.startswith(("top", "t ")) or (p[:1] == "t" and len(p) >= 2 and p[1:2].isdigit()):
        is_top = True
    elif p.startswith(("bot", "bottom", "b ")) or (p[:1] == "b" and len(p) >= 2 and p[1:2].isdigit()):
        is_top = False
    elif p.startswith("mid"):
        is_mid = True
    elif p.startswith("end"):
        is_end = True

    # Extract inning number
    nums = re.findall(r'\d+', p)
    if not nums:
        return None
    inning = int(nums[0])
    if inning < 1:
        return None

    total_outs = 54  # 9 innings × 6 outs/inning
    regulation_innings = 9

    # Calculate remaining half-innings for each team
    # In regulation: away bats top 1-9 (9 HI), home bats bottom 1-9 (9 HI)
    if is_end:
        # End of inning N: both halves complete
        completed_full_innings = inning
        away_hi = max(regulation_innings - completed_full_innings, 0)
        home_hi = max(regulation_innings - completed_full_innings, 0)
        outs_in_half = 0.0
        outs_done = inning * 6
    elif is_mid:
        # Mid inning N: top complete, bottom about to start
        away_hi = max(regulation_innings - inning, 0)  # away done with top N
        home_hi = max(regulation_innings - inning + 1, 0)  # home still has bottom N
        outs_in_half = 0.0
        outs_done = (inning - 1) * 6 + 3
    elif is_top is True:
        # Top of inning N: away batting (~1.5 outs into half)
        outs_in_half = 1.5
        # Away: remaining in this HI + future tops
        away_hi_after = max(regulation_innings - inning, 0)
        away_hi = (3 - outs_in_half) / 3 + away_hi_after  # fractional current + full future
        # Home: all bottoms from N onward
        home_hi = max(regulation_innings - inning + 1, 0)
        outs_done = (inning - 1) * 6 + outs_in_half
    elif is_top is False:
        # Bottom of inning N: home batting (~1.5 outs into half)
        outs_in_half = 1.5
        # Away: future tops only (current inning top already done)
        away_hi = max(regulation_innings - inning, 0)
        # Home: remaining in this HI + future bottoms
        home_hi_after = max(regulation_innings - inning, 0)
        home_hi = (3 - outs_in_half) / 3 + home_hi_after
        outs_done = (inning - 1) * 6 + 3 + outs_in_half
    else:
        # Unknown half — assume mid-inning
        away_hi = max(regulation_innings - inning, 0)
        home_hi = max(regulation_innings - inning + 1, 0)
        outs_in_half = 0.0
        outs_done = (inning - 1) * 6 + 3

    outs_remaining = max(total_outs - outs_done, 0.5)

    return {
        "inning": inning,
        "is_top": is_top,
        "outs_in_half": outs_in_half,
        "home_half_innings_remaining": max(home_hi, 0.0),
        "away_half_innings_remaining": max(away_hi, 0.0),
        "outs_remaining": outs_remaining,
    }


# -------------------------------------------------------------------------
# Baseball Win Probability (Poisson run-scoring model)
# -------------------------------------------------------------------------

# Average runs per half-inning in MLB (~4.5 R/G ÷ 9 innings ÷ 2 halves × 2 teams)
# Adjustable for different leagues (college baseball averages ~5.5 R/G)
BASEBALL_RUNS_PER_HALF_INNING = 0.5

# Home field advantage: home teams win ~54% of MLB games historically.
# Modeled as a constant boost to expected home margin (≈ +0.13 runs).
BASEBALL_HOME_ADVANTAGE_RUNS = 0.13


def compute_baseball_win_prob(
    home_score: int,
    away_score: int,
    period_str: str | None,
    pregame_spread: float | None = None,
    runs_per_half_inning: float = BASEBALL_RUNS_PER_HALF_INNING,
) -> float | None:
    """
    Compute baseball win probability using a Poisson run-scoring model.

    Based on Tom Tango's methodology ("The Book") and FanGraphs' approach:
    remaining runs for each team are Poisson-distributed, and the normal
    approximation gives P(home wins) via the CDF.

    Key features vs. the generic clock-based model:
    - Asymmetric half-innings (home bats last → advantage)
    - Walk-off handling (home leading entering bottom 9th = game over)
    - Poisson variance (variance = mean, not a fixed base_std)
    - Works for any baseball league by adjusting runs_per_half_inning

    Args:
        home_score: Current home team score
        away_score: Current away team score
        period_str: Inning string (e.g., "Top 5th", "Bot 7th", "3")
        pregame_spread: Pregame Vegas spread (negative = home favored)
        runs_per_half_inning: Average runs scored per half-inning (default: 0.5)

    Returns:
        Home win probability (0.0-1.0) or None if game state can't be parsed.
    """
    state = parse_baseball_state(period_str)
    if state is None:
        return None

    score_diff = home_score - away_score
    home_hi = state["home_half_innings_remaining"]
    away_hi = state["away_half_innings_remaining"]

    # Walk-off rule: if home is leading and it's top 9+ or later,
    # and home has no remaining at-bats needed, game is effectively over
    if score_diff > 0 and state["inning"] >= 9 and state["is_top"] is True and home_hi < 0.01:
        return 0.999

    # Expected remaining runs for each team (Poisson λ)
    lambda_home = runs_per_half_inning * home_hi
    lambda_away = runs_per_half_inning * away_hi

    # Pregame spread adjustment: scale by fraction of game remaining
    spread = pregame_spread if pregame_spread is not None else 0.0
    total_hi = home_hi + away_hi
    fraction_remaining = total_hi / 18.0 if total_hi > 0 else 0.001
    spread_adjustment = -spread * fraction_remaining

    # Expected final margin (positive = home wins)
    # = current lead + expected remaining home runs - expected remaining away runs
    #   + home field advantage (decays with game) + spread adjustment
    home_advantage = BASEBALL_HOME_ADVANTAGE_RUNS * fraction_remaining
    expected_margin = score_diff + (lambda_home - lambda_away) + home_advantage + spread_adjustment

    # Poisson variance: Var(Poisson) = λ, and runs are independent
    # Total variance = λ_home + λ_away (variance of difference of independent Poissons)
    variance = lambda_home + lambda_away

    # Edge case: near end of game, very low variance
    if variance < 0.01:
        if score_diff > 0:
            return 0.999
        elif score_diff < 0:
            return 0.001
        else:
            # Tied at end of regulation → extra innings, slight home advantage
            return 0.5 + BASEBALL_HOME_ADVANTAGE_RUNS * 0.1

    std_dev = math.sqrt(variance)

    # P(home wins) = Φ(expected_margin / std_dev)
    win_prob = _norm_cdf(expected_margin / std_dev)

    return max(0.001, min(0.999, win_prob))


def parse_game_clock(clock_str: str | None, period: str | None, sport_key: str) -> float | None:
    """
    Parse game clock and period into total seconds remaining.

    Returns None if the game state can't be parsed.
    """
    if not period:
        return None

    sport_key = _normalize_sport_key(sport_key)
    params = SPORT_PARAMS.get(sport_key)
    if not params:
        return None

    # Baseball: inning-based, doesn't use clock_str
    if sport_key.startswith("baseball_"):
        return parse_mlb_inning(period)

    # Clock sports require clock_str
    if not clock_str:
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
    # Strip clock prefix: "6:55 - 1st Quarter" → "1st Quarter"
    period_cleaned = period.strip()
    if " - " in period_cleaned:
        period_cleaned = period_cleaned.split(" - ", 1)[1]
    period_lower = period_cleaned.lower().strip()

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
        "baseball_mlb": 11400,          # ~3h 10m (MLB average ~3h 04m)
        "baseball_mlb_preseason": 10800, # ~3h (spring training games often shorter)
        "baseball_ncaa": 10800,          # ~3h (college baseball)
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

    # Baseball: use dedicated Poisson-based model when we have inning info.
    # Falls through to wall-clock fallback below if period is None.
    if sport_key.startswith("baseball_") and period:
        result = compute_baseball_win_prob(
            home_score=home_score,
            away_score=away_score,
            period_str=period,
            pregame_spread=pregame_spread,
        )
        if result is not None:
            return result

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
