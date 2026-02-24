"""
Event highlight scoring and classification.

Computes highlight scores and flags for events based on various factors
like closeness, upset potential, momentum shifts, etc.

Level 1: Snapshot scoring (opening vs current — two points in time)
Level 2: Time-series scoring (uses odds_snapshots for volatility,
         lead changes, and recent momentum)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal
import math

from app.utils.league_classification import is_power_4_team


# League tier definitions — the most important ranking signal for anonymous users.
# Tier 1 = must-see (major US pro leagues, premier international soccer)
# Tier 2 = notable (major college, top secondary leagues, WNBA)
# Tier 3 = niche (mid-tier international, smaller college)
# Tier 4 = anything not explicitly listed (minor leagues, obscure leagues)
LEAGUE_TIERS: dict[str, int] = {
    # Tier 1: Big 4 US leagues + top international soccer
    "basketball_nba": 1,
    "americanfootball_nfl": 1,
    "baseball_mlb": 1,
    "icehockey_nhl": 1,
    "soccer_epl": 1,
    "soccer_spain_la_liga": 1,
    "soccer_uefa_champs_league": 1,
    # Tier 2: Major college + top secondary
    "americanfootball_ncaaf": 2,
    "basketball_ncaab": 2,
    "basketball_wnba": 2,
    "basketball_wncaab": 2,
    "soccer_usa_mls": 2,
    "soccer_germany_bundesliga": 2,
    "soccer_italy_serie_a": 2,
    "soccer_france_ligue_one": 2,
    "soccer_uefa_europa_league": 2,
    "mma_mixed_martial_arts": 2,
    "cricket_t20_world_cup": 2,          # Major international tournament
    "cricket_icc_world_cup": 2,          # Major international tournament
    "soccer_fifa_world_cup": 1,          # Biggest sporting event
    "soccer_conmebol_copa_libertadores": 2,
    # Olympics — always tier 1 during the Games
    "icehockey_olympics": 1,
    "basketball_olympics": 1,
    "soccer_olympics": 1,
    "fieldhockey_olympics": 1,
    "curling_olympics": 2,
    # Tier 3: Niche but legit
    "soccer_mexico_ligamx": 3,
    "soccer_brazil_campeonato": 3,
    "soccer_brazil_serie_a": 3,
    "boxing_boxing": 3,
    "soccer_netherlands_eredivisie": 3,
    "soccer_portugal_primeira_liga": 3,
    "soccer_efl_champ": 3,              # English Championship (2nd division)
    "soccer_fa_cup": 3,
    "soccer_uefa_europa_conference_league": 3,
    "cricket_international_t20": 3,      # Regular T20s (not World Cup)
    "cricket_test_match": 3,
    "rugby_nrl": 3,
    "rugbyleague_nrl": 3,
    "rugbyunion_six_nations": 3,
    "aussierules_afl": 3,
    "basketball_euroleague": 3,
    # Tier 4: Preseason/spring training + minor leagues (explicit)
    "baseball_mlb_preseason": 4,
    "soccer_england_league1": 4,         # English League 1 (3rd division)
    "soccer_england_league2": 4,         # English League 2 (4th division)
    "icehockey_liiga": 4,               # Finnish top league
    "icehockey_mestis": 4,              # Finnish 2nd division
    "icehockey_ahl": 4,                 # AHL (NHL minor league)
    "icehockey_sweden_allsvenskan": 4,  # Swedish 2nd division
    "icehockey_sweden_hockey_league": 4, # SHL
    # Tennis: Grand Slams → tier 2, regular tour → tier 4
    # Regular ATP/WTA tour events are not interesting to the anonymous US audience.
    # Grand Slams ARE the moments casual fans care about.
    "tennis_us_open": 2,
    "tennis_french_open": 2,
    "tennis_wimbledon": 2,
    "tennis_australian_open": 2,
    "tennis_atp_aus_open_singles": 2,
    "tennis_wta_aus_open_singles": 2,
    "tennis_atp_dubai": 4,              # Regular ATP tour event
    "tennis_wta_dubai": 4,
    "tennis_atp_qatar_open": 4,
    "tennis_wta_qatar_open": 4,
    # Golf Majors → tier 2
    "golf_masters_tournament_winner": 2,
    "golf_pga_championship_winner": 2,
    "golf_us_open_winner": 2,
    "golf_the_open_championship_winner": 2,
}

# Highlight score weights
WEIGHTS = {
    "live": 30,                    # Being live is inherently interesting
    "close_matchup": 25,           # 40-60% probability
    "very_close": 10,              # 45-55% probability (bonus)
    "favorite_switched": 20,       # Upset potential
    "major_probability_swing": 15, # >15% change from open
    "major_score_swing": 10,       # >20% projected score change
    "starting_soon_3h": 15,        # Starting in <3 hours
    "starting_soon_1h": 10,        # Starting in <1 hour (bonus)
    "tier_1_league": 20,           # Major league bonus (substantial — keeps big leagues on top)
    "tier_2_league": 10,           # College/secondary league bonus (Power 4 matchups)
    "tier_2_power4_mixed": 5,      # Power 4 vs mid-major college
    "tier_2_midmajor": 2,          # Mid-major vs mid-major college
    "tier_3_league": -5,            # Niche — small penalty to keep below threshold without other signals
    "tier_4_penalty": -45,         # Minor league penalty — tier 4 should never appear for anonymous
                                   # users unless championship/playoff. Live+close only gives 55,
                                   # so -45 keeps score at ~10 (well below min_score 30).
    "recent_finish_upset": 20,     # Recently finished + upset
    "recent_finish": 5,            # Recently finished (24h)
    # Event importance (from llm_importance / ESPN season type)
    "championship": 25,            # Championship/final — always a big moment
    "playoff": 15,                 # Playoff/postseason game — significant boost
    "exhibition": -20,             # Preseason/all-star — deprioritize
    # Level 2: Time-series weights
    "high_volatility": 10,         # Line has been volatile (RMS of deltas > 0.06)
    "lead_changes": 8,             # Probability crossed 50% (per crossing, max 3)
    "recent_momentum": 10,         # Fast movement in last 30 min (>8% shift)
}

# Thresholds
CLOSE_MATCHUP_MIN = 0.40
CLOSE_MATCHUP_MAX = 0.60
VERY_CLOSE_MIN = 0.45
VERY_CLOSE_MAX = 0.55
BLOWOUT_THRESHOLD = 0.85
MAJOR_PROB_SWING = 0.15  # 15% change
MAJOR_SCORE_SWING = 0.20  # 20% change
MIN_PREGAME_MOVEMENT = 0.05  # 5% change needed for pre-game closeness to be a trend

# Level 2 thresholds
HIGH_VOLATILITY_RMS = 0.06  # 6% RMS of probability deltas = volatile
RECENT_MOMENTUM_THRESHOLD = 0.08  # 8% shift in last 30 min = fast-moving


@dataclass
class TimeSeriesMetrics:
    """
    Pre-computed time-series metrics from odds_snapshots.

    These are computed outside compute_highlight (by the caller that has DB access)
    and passed in, keeping compute_highlight pure and testable.
    """
    volatility_rms: float = 0.0  # RMS of probability deltas between consecutive snapshots
    lead_changes: int = 0  # Number of times probability crossed 50%
    recent_momentum: float = 0.0  # Absolute probability shift in last 30 minutes
    snapshot_count: int = 0  # Number of aggregated time buckets used


@dataclass
class EventFlags:
    """Boolean flags describing event characteristics."""
    is_live: bool = False
    is_close_matchup: bool = False
    is_very_close: bool = False
    is_blowout: bool = False
    favorite_switched: bool = False
    probability_swing: Literal["major", "minor", "stable"] = "stable"
    score_swing: Literal["major", "minor", "stable"] = "stable"
    is_starting_soon: bool = False  # <3h
    is_starting_very_soon: bool = False  # <1h
    is_recently_finished: bool = False  # <24h
    is_upset: bool = False  # Closed + favorite switched
    league_tier: int = 4
    # Event importance flags
    is_playoff: bool = False
    is_championship: bool = False
    # Level 2 flags
    is_volatile: bool = False
    has_lead_changes: bool = False
    has_recent_momentum: bool = False


@dataclass
class HighlightResult:
    """Complete highlight analysis for an event."""
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    flags: EventFlags = field(default_factory=EventFlags)
    primary_reason: Optional[str] = None


def get_league_tier(sport_key: Optional[str]) -> int:
    """Get the tier for a league (1=major, 2=notable, 3=niche, 4=minor)."""
    if not sport_key:
        return 4
    return LEAGUE_TIERS.get(sport_key, 4)


def compute_time_series_metrics(
    probabilities: list[float],
    timestamps: Optional[list[datetime]] = None,
) -> TimeSeriesMetrics:
    """
    Compute time-series metrics from a sequence of home probabilities.

    Args:
        probabilities: List of home_probability values in chronological order.
                      These should be pre-aggregated (e.g., one per minute bucket).
        timestamps: Optional list of corresponding timestamps (same length as
                   probabilities). Used for recent_momentum calculation.

    Returns:
        TimeSeriesMetrics with volatility, lead changes, and recent momentum.
    """
    metrics = TimeSeriesMetrics(snapshot_count=len(probabilities))

    if len(probabilities) < 2:
        return metrics

    # 1. Volatility: RMS of consecutive probability deltas
    deltas = [
        probabilities[i] - probabilities[i - 1]
        for i in range(1, len(probabilities))
    ]
    sum_sq = sum(d * d for d in deltas)
    metrics.volatility_rms = math.sqrt(sum_sq / len(deltas))

    # 2. Lead changes: count 50% crossings
    for i in range(1, len(probabilities)):
        prev = probabilities[i - 1]
        curr = probabilities[i]
        # Crossed 50% if one is above and other below (not equal)
        if (prev < 0.5 and curr > 0.5) or (prev > 0.5 and curr < 0.5):
            metrics.lead_changes += 1

    # 3. Recent momentum: absolute shift in last 30 minutes
    if timestamps and len(timestamps) == len(probabilities):
        now = timestamps[-1]
        thirty_min_ago = now - timedelta(minutes=30)
        # Find the value closest to 30 min ago
        recent_start_val = None
        for i, ts in enumerate(timestamps):
            if ts >= thirty_min_ago:
                recent_start_val = probabilities[i]
                break
        if recent_start_val is not None:
            metrics.recent_momentum = abs(probabilities[-1] - recent_start_val)

    return metrics


def compute_highlight(
    # Event basics
    status: str,
    commence_time: datetime,
    sport_key: Optional[str] = None,
    # Current odds
    current_home_prob: Optional[float] = None,
    current_away_prob: Optional[float] = None,
    current_home_spread: Optional[float] = None,
    current_over_under: Optional[float] = None,
    # Opening odds (for comparison)
    opening_home_prob: Optional[float] = None,
    opening_away_prob: Optional[float] = None,
    opening_home_spread: Optional[float] = None,
    opening_over_under: Optional[float] = None,
    opening_favorite: Optional[str] = None,
    # Timing
    now: Optional[datetime] = None,
    # Level 2: Time-series metrics (optional — gracefully degrades to Level 1)
    time_series: Optional[TimeSeriesMetrics] = None,
    # Team names for Power 4 scoring (optional)
    home_team_name: Optional[str] = None,
    away_team_name: Optional[str] = None,
    # Event importance (from llm_importance / ESPN season type)
    importance: Optional[str] = None,
) -> HighlightResult:
    """
    Compute highlight score and flags for an event.

    Returns a HighlightResult with:
    - score: 0-100 indicating how "highlight-worthy" the event is
    - reasons: list of reason codes explaining the score
    - flags: EventFlags with boolean characteristics
    - primary_reason: the most important reason for display

    Level 1 (always available): Uses opening vs current odds (two points).
    Level 2 (when time_series is provided): Adds volatility, lead changes,
    and recent momentum from odds_snapshots time series.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    result = HighlightResult()
    flags = result.flags

    # Ensure commence_time is timezone-aware
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)

    # === Time-based flags ===
    time_until_start = (commence_time - now).total_seconds()
    time_since_start = -time_until_start
    hours_until = time_until_start / 3600
    hours_since = time_since_start / 3600

    # Live status - require both status="live" AND commence_time has passed.
    # The Odds API sometimes reports events as "live" before their commence_time,
    # which causes false "Upset brewing" labels from pre-game line noise.
    flags.is_live = status == "live" and commence_time <= now
    if flags.is_live:
        result.score += WEIGHTS["live"]
        result.reasons.append("live")

    # Starting soon
    if status == "scheduled" and 0 < hours_until <= 3:
        flags.is_starting_soon = True
        result.score += WEIGHTS["starting_soon_3h"]
        result.reasons.append("starting_soon")

        if hours_until <= 1:
            flags.is_starting_very_soon = True
            result.score += WEIGHTS["starting_soon_1h"]
            result.reasons.append("starting_very_soon")

    # Recently finished
    if status in ("completed", "closed") and 0 < hours_since <= 24:
        flags.is_recently_finished = True
        result.score += WEIGHTS["recent_finish"]
        result.reasons.append("recent_finish")

    # === League tier ===
    flags.league_tier = get_league_tier(sport_key)
    if flags.league_tier == 1:
        result.score += WEIGHTS["tier_1_league"]
        result.reasons.append("tier_1")
    elif flags.league_tier == 2:
        # For college sports, differentiate Power 4 vs mid-major
        is_college = sport_key and sport_key in (
            "americanfootball_ncaaf", "basketball_ncaab", "basketball_wncaab",
        )
        if is_college and home_team_name and away_team_name:
            home_p4 = is_power_4_team(home_team_name)
            away_p4 = is_power_4_team(away_team_name)
            if home_p4 and away_p4:
                result.score += WEIGHTS["tier_2_league"]
                result.reasons.append("tier_2")
            elif home_p4 or away_p4:
                result.score += WEIGHTS["tier_2_power4_mixed"]
                result.reasons.append("tier_2_p4_mixed")
            else:
                result.score += WEIGHTS["tier_2_midmajor"]
                result.reasons.append("tier_2_midmajor")
        else:
            # Non-college tier 2 (WNBA, MLS, MMA, etc.) or no team names
            result.score += WEIGHTS["tier_2_league"]
            result.reasons.append("tier_2")
    elif flags.league_tier == 3:
        result.score += WEIGHTS["tier_3_league"]
        result.reasons.append("tier_3")
    elif flags.league_tier == 4:
        result.score += WEIGHTS["tier_4_penalty"]
        result.reasons.append("tier_4")

    # === Event importance ===
    if importance == "championship":
        flags.is_championship = True
        result.score += WEIGHTS["championship"]
        result.reasons.append("championship")
    elif importance == "playoff":
        flags.is_playoff = True
        result.score += WEIGHTS["playoff"]
        result.reasons.append("playoff")
    elif importance == "exhibition":
        result.score += WEIGHTS["exhibition"]
        result.reasons.append("exhibition")

    # === Probability-based flags ===
    is_pre_game = not flags.is_live and status not in ("completed", "closed")

    if current_home_prob is not None:
        # Closeness
        if CLOSE_MATCHUP_MIN <= current_home_prob <= CLOSE_MATCHUP_MAX:
            flags.is_close_matchup = True

            # For pre-game events, closeness from a single snapshot could be noise
            # (e.g., 51/49 across 13 books). Only award score points if there's
            # evidence of a trend: the line moved toward close from opening, or
            # the game is starting soon (making closeness action-relevant).
            opening_was_close = (
                opening_home_prob is not None
                and CLOSE_MATCHUP_MIN <= opening_home_prob <= CLOSE_MATCHUP_MAX
            )
            has_movement = (
                opening_home_prob is not None
                and abs(current_home_prob - opening_home_prob) >= MIN_PREGAME_MOVEMENT
            )
            closeness_is_interesting = (
                not is_pre_game  # Live/finished: closeness always matters
                or flags.is_starting_soon  # Starting soon: closeness is action-relevant
                or not opening_was_close  # Line tightened from lopsided to close
                or has_movement  # Significant movement even if both close
                or opening_home_prob is None  # No opening data, give benefit of doubt
            )

            if closeness_is_interesting:
                result.score += WEIGHTS["close_matchup"]
                result.reasons.append("close_matchup")

            if VERY_CLOSE_MIN <= current_home_prob <= VERY_CLOSE_MAX:
                flags.is_very_close = True
                if closeness_is_interesting:
                    result.score += WEIGHTS["very_close"]
                    result.reasons.append("very_close")

        # Blowout
        if current_home_prob >= BLOWOUT_THRESHOLD or current_home_prob <= (1 - BLOWOUT_THRESHOLD):
            flags.is_blowout = True
            # Blowouts reduce score (less interesting)
            result.score = max(0, result.score - 15)
            result.reasons.append("blowout")

        # Probability swing from open
        if opening_home_prob is not None:
            prob_change = abs(current_home_prob - opening_home_prob)
            if prob_change >= MAJOR_PROB_SWING:
                flags.probability_swing = "major"
                result.score += WEIGHTS["major_probability_swing"]
                result.reasons.append("major_prob_swing")
            elif prob_change >= 0.08:  # 8% change
                flags.probability_swing = "minor"

        # Favorite switched - only meaningful for live/completed games
        # Pre-game line movement is just market noise, not an "upset brewing"
        if opening_favorite and (flags.is_live or status in ("completed", "closed")):
            current_favorite = "home" if current_home_prob > 0.5 else "away" if current_home_prob < 0.5 else "even"
            if opening_favorite != current_favorite and opening_favorite != "even" and current_favorite != "even":
                flags.favorite_switched = True
                result.score += WEIGHTS["favorite_switched"]
                result.reasons.append("favorite_switched")

                # If finished with upset, big bonus
                if flags.is_recently_finished:
                    flags.is_upset = True
                    result.score += WEIGHTS["recent_finish_upset"]
                    result.reasons.append("upset")

    # === Projected score swing ===
    if (current_over_under is not None and opening_over_under is not None
        and opening_over_under > 0):
        score_change_pct = abs(current_over_under - opening_over_under) / opening_over_under
        if score_change_pct >= MAJOR_SCORE_SWING:
            flags.score_swing = "major"
            result.score += WEIGHTS["major_score_swing"]
            result.reasons.append("major_score_swing")
        elif score_change_pct >= 0.10:  # 10% change
            flags.score_swing = "minor"

    # === Level 2: Time-series scoring ===
    if time_series and time_series.snapshot_count >= 3:
        # High volatility: lots of line movement
        if time_series.volatility_rms >= HIGH_VOLATILITY_RMS:
            flags.is_volatile = True
            result.score += WEIGHTS["high_volatility"]
            result.reasons.append("high_volatility")

        # Lead changes: probability crossed 50%
        if time_series.lead_changes > 0:
            flags.has_lead_changes = True
            # Award up to 3 lead changes worth of points
            lc_bonus = min(time_series.lead_changes, 3) * WEIGHTS["lead_changes"]
            result.score += lc_bonus
            result.reasons.append("lead_changes")

        # Recent momentum: fast movement in last 30 min (live games only)
        if flags.is_live and time_series.recent_momentum >= RECENT_MOMENTUM_THRESHOLD:
            flags.has_recent_momentum = True
            result.score += WEIGHTS["recent_momentum"]
            result.reasons.append("recent_momentum")

    # === Clamp score to 0-100 ===
    result.score = max(0, min(100, result.score))

    # === Determine primary reason for display ===
    # Priority order for what to show users
    priority_order = [
        ("upset", "Recent upset"),
        ("favorite_switched", "Possible upset"),
        ("lead_changes", "Lead change"),
        ("very_close", "Coin flip"),
        ("close_matchup", "Close matchup"),
        ("recent_momentum", "Odds shifting fast"),
        ("major_prob_swing", "Big line movement"),
        ("high_volatility", "Wild game"),
        ("championship", "Championship game"),
        ("playoff", "Playoff game"),
        ("live", "Live"),
        ("starting_very_soon", "Starting soon"),
        ("starting_soon", "Starting soon"),
        ("recent_finish", "Recently finished"),
    ]

    for reason_code, display_text in priority_order:
        if reason_code in result.reasons:
            result.primary_reason = display_text
            break

    return result


def get_highlight_label(result: HighlightResult) -> Optional[str]:
    """
    Get a short label for display in the Highlights section.

    Returns None if event shouldn't be highlighted.
    """
    flags = result.flags

    if flags.is_upset:
        return "Recent upset"
    if flags.is_live and flags.favorite_switched:
        return "Upset brewing"
    if flags.is_live and flags.has_lead_changes:
        return "Lead change"
    if flags.is_live and flags.is_very_close:
        return "Coin flip"
    if flags.is_live and flags.is_close_matchup:
        return "Close game"
    if flags.is_live and flags.has_recent_momentum:
        return "Odds shifting fast"
    if flags.is_live and flags.probability_swing == "major":
        return "Momentum shift"
    if flags.is_live and flags.is_volatile:
        return "Wild game"
    if flags.is_starting_very_soon and flags.is_close_matchup:
        return "Close matchup"
    if flags.is_starting_soon and flags.is_close_matchup:
        return "Close matchup"
    if flags.is_live:
        return "Live"

    # Importance labels (meaningful for pre-game events)
    if flags.is_championship:
        return "Championship game"
    if flags.is_playoff:
        return "Playoff game"

    # Pre-game: significant line movement is a real trend worth labeling
    if flags.probability_swing == "major":
        return "Line moving"

    return None


def should_highlight(result: HighlightResult, min_score: int = 30) -> bool:
    """Determine if an event should appear in the Highlights section."""
    # Always highlight live close games or upsets
    if result.flags.is_live and (result.flags.is_close_matchup or result.flags.favorite_switched):
        return True

    # Always highlight recent upsets
    if result.flags.is_upset:
        return True

    # Always highlight live games with lead changes
    if result.flags.is_live and result.flags.has_lead_changes:
        return True

    # Otherwise, use score threshold
    return result.score >= min_score
