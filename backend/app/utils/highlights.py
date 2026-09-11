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
from functools import lru_cache
from typing import Optional, Literal
import math
import re

from app.utils.league_classification import is_power_4_team
from app.utils.lifecycle import live_start_satisfied


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
    # The slams are spelled here WITHOUT the tour segment; real sport keys carry it
    # ("tennis_atp_us_open"), so `get_league_tier` drops the tour and re-reads this
    # same table rather than this table listing every tour × slam pair.
    "tennis_us_open": 2,
    "tennis_french_open": 2,
    "tennis_wimbledon": 2,
    "tennis_australian_open": 2,
    "tennis_aus_open": 2,               # The Odds API's own spelling of the same slam
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
    "live": 30,                    # Base live bonus (always awarded)
    "live_late_game": 10,          # Extra bonus for late-game (scales with game progress, up to +10)
    "live_overtime": 10,           # Extra bonus for overtime
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
    "momentum_accelerating": 8,    # Odds movement is speeding up (acceleration > 3%)
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
MOMENTUM_ACCEL_THRESHOLD = 0.03  # 3% acceleration = odds movement speeding up

# Season calendars for season context multiplier.
# (start_month, playoffs_start_month) — progress goes from 0 at start to 1.0 at playoffs.
# Seasons that wrap the year boundary (e.g., NBA: Oct to Apr) are handled automatically.
SEASON_CALENDARS: dict[str, tuple[int, int]] = {
    "basketball_nba": (10, 4),        # Oct → Apr
    "basketball_ncaab": (11, 3),      # Nov → Mar (March Madness)
    "basketball_wncaab": (11, 3),
    "basketball_wnba": (5, 9),        # May → Sep
    "americanfootball_nfl": (9, 1),    # Sep → Jan
    "americanfootball_ncaaf": (8, 12), # Aug → Dec (bowls/playoff)
    "baseball_mlb": (3, 10),          # Mar → Oct
    "icehockey_nhl": (10, 4),         # Oct → Apr
    "soccer_epl": (8, 5),             # Aug → May
    "soccer_spain_la_liga": (8, 5),
    "soccer_germany_bundesliga": (8, 5),
    "soccer_italy_serie_a": (8, 5),
    "soccer_france_ligue_one": (8, 5),
    "soccer_usa_mls": (2, 10),        # Feb → Oct
    "soccer_uefa_champs_league": (9, 5),  # Sep → May (knockouts Feb+)
    "soccer_mexico_ligamx": (7, 5),
    "mma_mixed_martial_arts": (1, 12),  # Year-round, no season effect
}

# Sport-specific total periods for game progress calculation
SPORT_TOTAL_PERIODS: dict[str, int] = {
    "basketball_nba": 4,
    "basketball_ncaab": 2,
    "basketball_wncaab": 4,
    "basketball_wnba": 4,
    "americanfootball_nfl": 4,
    "americanfootball_ncaaf": 4,
    "icehockey_nhl": 3,
    "baseball_mlb": 9,
    "soccer_epl": 2,
    "soccer_spain_la_liga": 2,
    "soccer_uefa_champs_league": 2,
    "soccer_germany_bundesliga": 2,
    "soccer_italy_serie_a": 2,
    "soccer_france_ligue_one": 2,
    "soccer_usa_mls": 2,
    "soccer_mexico_ligamx": 2,
    "soccer_fifa_world_cup": 2,
}


#: Soccer's regulation length. Progress for a minute-clock sport is minute/90,
#: so a 90+3' match reads as 1.0 rather than overflowing past it.
SOCCER_REGULATION_MINUTES = 90


#: A SCHEDULED DATETIME, not a period. ESPN keeps the pre-game status detail in
#: the `period` field until the first in-game update lands, so for the first few
#: minutes after a game flips to live its "period" is still its kickoff time:
#: "Thu, September 10th at 8:35 PM EDT". Every numeric reader below then finds
#: the DAY OF THE MONTH in it — on the 10th, "10th" read as period 10, which is
#: beyond regulation in every sport we map, so the night's marquee NFL game sat
#: at rank 2 of Discover badged "Overtime" two minutes after kickoff at 0-0
#: (#5012). There is no day on which the reading is right: days 5-31 claim
#: overtime and days 1-4 report a false progress fraction instead.
#:
#: Matched on any of the three things a period token can never contain — a month
#: name, a weekday, or a wall-clock time with a meridiem — so the sentence is
#: refused before it reaches a reader rather than each reader being taught to
#: distrust it. Same family as #3208, whose general lesson (never let a free-text
#: field reach a numeric reader unanchored) this applies to the rest of the
#: function.
_SCHEDULED_DATETIME_RE = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october"
    r"|november|december)\b"
    r"|\b(?:mon|tue|tues|wed|weds|thu|thur|thurs|fri|sat|sun)(?:day)?\b"
    r"|\b\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)\b"
)

#: A period-shaped ordinal token: "3rd", "1st Quarter", "Top 12th", "Mid 5th".
#: ANCHORED, and that is the whole point — an ordinal only says "period" when it
#: LEADS the token, optionally behind one of baseball's half-inning qualifiers.
#: An unanchored `re.search` is what let "September 10th" reach the period reader
#: (#5012); it would find an ordinal anywhere in an arbitrary sentence.
_ORDINAL_PERIOD_RE = re.compile(
    r"^(?:(?:top|bot|bottom|mid|middle|end|start)\s+(?:of\s+)?(?:the\s+)?)?"
    r"(\d{1,2})(?:st|nd|rd|th)\b"
)


def _is_minute_clock_sport(sport_key: Optional[str]) -> bool:
    """True when this sport's live period string is a running clock MINUTE.

    Soccer is the case that matters: ESPN reports "31'", not "1st Half". Keyed
    off the `soccer_` prefix rather than a list of leagues, so a competition we
    add next month is covered the day it arrives instead of silently falling
    through to the period reader that produced #3208.
    """
    return (sport_key or "").startswith("soccer_")


def parse_game_progress(period_str: Optional[str], sport_key: Optional[str]) -> tuple[float, bool]:
    """Parse game progress from ESPN period string.

    Returns:
        (progress, is_overtime) where progress is 0.0-1.0 (fraction of game elapsed)
        and is_overtime is True if the game is in overtime/extra time.
    """
    if not period_str:
        return 0.0, False  # Unknown — don't assume any progress

    # Strip clock prefix: "6:55 - 1st Quarter" → "1st Quarter"
    # The period field sometimes includes "clock - period" format
    cleaned = period_str.strip()
    if " - " in cleaned:
        cleaned = cleaned.split(" - ", 1)[1]

    period_lower = cleaned.lower().strip()

    # A scheduled datetime is not a period. Refused here, before ANY reader
    # below can find a number in it — see `_SCHEDULED_DATETIME_RE` (#5012).
    # 0.0 is the same claim the null-period case makes at the top of this
    # function: unknown, so assume no progress. It is also the truthful one —
    # a game still carrying its kickoff time in `period` has at most just
    # started, and a caller scaling a late-game bonus by this must not be
    # handed the 0.5 "mid-game" guess for a game that is two minutes old.
    if _SCHEDULED_DATETIME_RE.search(period_lower):
        return 0.0, False

    # Overtime detection — use word boundaries to avoid false matches
    # (e.g., "1st Quarter" should NOT match "ot" substring)
    if re.search(r"\bot\b|\bovertime\b|\bextra\s*time\b|\bshootout\b|\bpenalties\b|\bso\b", period_lower):
        return 1.0, True

    # Half-based sports (soccer, college basketball)
    if "1st half" in period_lower or "first half" in period_lower:
        return 0.25, False
    if "2nd half" in period_lower or "second half" in period_lower:
        return 0.75, False
    if "halftime" in period_lower:
        return 0.5, False

    # Soccer's live "period" from ESPN is a CLOCK MINUTE, not a period index:
    # "31'", "45+2'", "90+3'". Read as a period number it was catastrophic — the
    # bare-number branch below matched it, and every minute past the 2nd cleared
    # `period_num > total` (soccer has 2 halves), so an ordinary first-half match
    # scored as overtime: (1.0, True). That is #3208 — a 61' EPL card badged
    # "Overtime" in a competition whose league fixtures have no overtime at all.
    # Handle the minute clock explicitly, before any period reading can claim it.
    minute_match = re.match(r"^(\d{1,3})\s*(?:\+\s*\d{1,2})?\s*'?\s*$", period_lower)
    if minute_match and _is_minute_clock_sport(sport_key):
        minute = int(minute_match.group(1))
        # Stoppage time is not extra time. A 90+3' match is in regulation, and
        # this function has no way to tell a cup tie's extra time from a long
        # stoppage — the explicit "ET"/"extra time" check above is the only
        # trustworthy signal, and it has already run. So: never overtime here.
        return min(minute / SOCCER_REGULATION_MINUTES, 1.0), False

    # Quarter/period-based: extract number from "Q4", "3rd", "Period 2", etc.
    # Use specific patterns to avoid matching clock digits like "6:55"
    keyword_match = re.search(r"(?:q|quarter\s*|period\s*|half\s*)(\d+)", period_lower)
    # A number with no period word in front of it. "3" probably means period 3 —
    # but it is the one form that carries no evidence of being a period at all,
    # so it is not allowed to conclude overtime (see `explicit` below).
    bare_match = None if keyword_match else re.match(r"^(\d+)", period_lower)
    # Ordinals — "3rd", "Top 12th". These DO say period: 12th in a 9-inning sport
    # is extra innings and reading it as beyond-regulation is correct. That is
    # only true of an ordinal that IS the period token, though, not one buried in
    # prose, so the pattern is anchored (#5012).
    ordinal_match = _ORDINAL_PERIOD_RE.match(period_lower)

    num_match = keyword_match or ordinal_match or bare_match
    if num_match:
        # Only an explicitly-marked period may be read as beyond regulation.
        explicit = num_match is not bare_match
        period_num = int(num_match.group(1))
        total = SPORT_TOTAL_PERIODS.get(sport_key or "", 4)
        if period_num > total:
            if explicit:
                return 1.0, True  # Beyond regulation = overtime
            # An unlabelled number larger than the sport has periods is far more
            # likely a clock than a 31st period. Say "mid-game, don't know" —
            # the old code said "overtime", which is a strong claim built on the
            # weakest evidence on the card.
            return 0.5, False
        # Mid-period approximation: (period - 0.5) / total
        progress = min((period_num - 0.5) / total, 1.0)
        return progress, False

    # "Final" means game is over (shouldn't be "live" but handle gracefully)
    if "final" in period_lower:
        return 1.0, False

    return 0.5, False  # Unknown — assume mid-game


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
    momentum_acceleration: float = 0.0  # Change in momentum (recent 30m vs previous 30m)
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
    # #4580 — the scoreboard, for sentences that name it. Tri-state: None means
    # the row carries no score, which is never the same as "no".
    underdog_is_leading: Optional[bool] = None
    someone_is_leading: Optional[bool] = None
    # #5047 — how much doubt the market has left in an upset the scoreboard has
    # already earned. Tri-state for the same reason: None is "cannot say".
    upset_is_no_longer_in_doubt: Optional[bool] = None


def underdog_leads(
    opening_home_prob: Optional[float],
    home_score: Optional[int],
    away_score: Optional[int],
) -> Optional[bool]:
    """Is the pre-game underdog ahead on the scoreboard right now?

    THE ONE DETERMINATION behind every sentence that names the field (#4580).
    The capsule ("Upset brewing") and the footer badge ("{team} leading as
    underdog") are produced by two different modules; both call this, so they
    cannot drift into disagreeing about the same card.

    Tri-state, and the third state is load-bearing:

    * ``True``  — the side that opened as the underdog is ahead.
    * ``False`` — it is not: either the favourite leads, or the game is level.
      0-0 is a *known* answer, not a missing one; nobody is leading.
    * ``None``  — unanswerable. Measured on production 2026-09-10, **41 of 64
      live events carry no score at all** (both columns NULL). Collapsing that
      into ``False`` would read as "the underdog is not ahead" about 41 games we
      cannot see, so callers must treat ``None`` as "say nothing about the
      field" rather than as a denial.

    A price-derived favourite switch is NOT an answer to this question, which is
    the whole defect: it was standing in for one.
    """
    if opening_home_prob is None or home_score is None or away_score is None:
        return None
    if opening_home_prob == 0.5:
        # No underdog for anyone to be.
        return None
    if home_score == away_score:
        return False
    home_is_underdog = opening_home_prob < 0.5
    home_is_ahead = home_score > away_score
    return home_is_ahead == home_is_underdog


def score_is_decided(
    home_score: Optional[int],
    away_score: Optional[int],
) -> Optional[bool]:
    """Is anyone ahead on the scoreboard? Tri-state, for the same reason."""
    if home_score is None or away_score is None:
        return None
    return home_score != away_score


def upset_is_no_longer_in_doubt(
    opening_home_prob: Optional[float],
    current_home_prob: Optional[float],
) -> Optional[bool]:
    """Does the market say the pre-game UNDERDOG has this won? (#5047)

    #4580 gave the upset capsule a DIRECTION gate — the scoreboard has to agree
    that the underdog is ahead. It never gave it a DECIDEDNESS gate, so the same
    two words came out at 3-1 in the second half and at 24-7 with 12:05 left in
    the 4th. On production 2026-09-11 02:51Z that was Discover rank 2: SF @ LAR,
    "Upset brewing", 7-24, the favourite at 5%, and ``signal:blowout`` sitting on
    the very same payload. One card saying both "this might happen" and "this is
    over".

    Asking the price is legitimate HERE and only here. #4580's doctrine is that a
    price move must never *produce* a sentence about the field; this answers the
    narrower question of how much doubt the market has left, and it is read only
    after ``underdog_leads`` has already earned the branch off the scoreboard.

    Deliberately NOT ``flags.is_blowout``, though the two agree on every card
    that can reach the capsule TODAY. ``is_blowout`` is the same 0.85 threshold
    read without a direction, and it is only equivalent here because
    ``favorite_switched`` has already forced the pre-game underdog above 0.50 —
    i.e. the equivalence is a property of the *caller*, not of the flag. Read
    direction-free it is wrong in the obvious case: a 1-0 lead three minutes into
    a 92%-favourite's game leaves the favourite near 86%, which is a blowout by
    that flag while the upset is the opposite of decided. A capsule that means
    "the underdog has it won" should ask that question, so that loosening the
    branch above cannot silently turn the label into a lie.

    Basis note: "who was the underdog" is read from ``opening_home_prob``, the
    same input ``underdog_leads`` uses — NOT from the ``opening_favorite`` string
    that ``favorite_switched`` reads. Two derivations of one fact is how the
    capsule and the badge drifted apart in the first place (#4580).

    Tri-state, matching its two siblings above:

    * ``True``  — the pre-game underdog is now at or past ``BLOWOUT_THRESHOLD``.
    * ``False`` — the market still has real doubt in it.
    * ``None``  — unanswerable: a price is missing, or the game opened a pick'em
      and has no underdog for the question to be about.
    """
    if opening_home_prob is None or current_home_prob is None:
        return None
    if opening_home_prob == 0.5:
        # No underdog for anyone to be.
        return None
    home_is_underdog = opening_home_prob < 0.5
    underdog_prob_now = current_home_prob if home_is_underdog else 1 - current_home_prob
    return underdog_prob_now >= BLOWOUT_THRESHOLD


@dataclass
class HighlightResult:
    """Complete highlight analysis for an event."""
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    flags: EventFlags = field(default_factory=EventFlags)
    primary_reason: Optional[str] = None
    # Hours since the game actually ended (None unless status is completed/closed).
    # Derived ONCE here, off the best finish reference available, so the freshness
    # decay in `feed_scoring.compute_base_score` ranks off the same clock that set
    # `is_recently_finished` — one derivation, two consumers, no drift.
    hours_since_finish: Optional[float] = None


# Tour segments that sit between the sport and the tournament in a tennis sport key.
_TENNIS_TOUR_SEGMENTS = frozenset({"atp", "wta", "itf"})


def _tour_agnostic_tennis_key(sport_key: str) -> Optional[str]:
    """Strip the tour segment from a tennis sport key, or None if there isn't one.

    "tennis_atp_us_open" → "tennis_us_open"; "tennis_atp" and "tennis_other" → None.
    A slam is the same moment whichever tour is playing it, so the tier table names
    each one once and this drops the tour so the lookup can find it.
    """
    parts = sport_key.split("_")
    if len(parts) < 3 or parts[0] != "tennis" or parts[1] not in _TENNIS_TOUR_SEGMENTS:
        return None
    return "_".join([parts[0]] + parts[2:])


def get_league_tier(sport_key: Optional[str]) -> int:
    """Get the tier for a league (1=major, 2=notable, 3=niche, 4=minor).

    Exact spelling wins; a tennis key that misses falls back to its tour-agnostic
    form. Without that fallback every Grand Slam match ever ingested scored tier 4
    — a -45 penalty — because the table spells the slams "tennis_us_open" while the
    events carry "tennis_atp_us_open" (#2552). Regular tour stops have no entry
    under either spelling and stay tier 4.
    """
    if not sport_key:
        return 4
    tier = LEAGUE_TIERS.get(sport_key)
    if tier is not None:
        return tier
    tour_agnostic = _tour_agnostic_tennis_key(sport_key)
    if tour_agnostic is not None:
        return LEAGUE_TIERS.get(tour_agnostic, 4)
    return 4


@lru_cache(maxsize=1)
def tier_12_sport_keys() -> frozenset:
    """Every sport key `get_league_tier` scores 1 or 2, INCLUDING the tour-prefixed
    tennis spellings this table does not list.

    🔴 A SQL predicate cannot call `get_league_tier`, so anything building an
    `IN (...)` from tier has to expand the same fallback the function applies —
    and the obvious `{k for k, t in LEAGUE_TIERS.items() if t <= 2}` does not.
    That comprehension is #2552's defect in set form: it yields `tennis_us_open`,
    which no event carries, and omits `tennis_atp_us_open` and
    `tennis_wta_us_open`, which is what every US Open match in `events` is
    actually keyed on. A "tier 1-2 only" filter built that way silently drops
    every Grand Slam match — the exact rows the tier gate exists to keep.

    Round-tripped by the guard test in both directions: every key returned scores
    ≤2 through `get_league_tier`, and no tier-3+ key sneaks in via the expansion.
    """
    keys = {k for k, t in LEAGUE_TIERS.items() if t <= 2}
    for key, tier in list(LEAGUE_TIERS.items()):
        if tier > 2 or not key.startswith("tennis_"):
            continue
        rest = key.split("_", 1)[1]
        if rest.split("_", 1)[0] in _TENNIS_TOUR_SEGMENTS:
            continue  # already tour-qualified; nothing to expand
        keys.update(f"tennis_{tour}_{rest}" for tour in _TENNIS_TOUR_SEGMENTS)
    return frozenset(keys)


def get_season_multiplier(sport_key: Optional[str], now: Optional[datetime] = None) -> float:
    """Get a season progress multiplier for a sport.

    Returns 0.8 (early season) to 1.2 (late season / playoffs approaching).
    Returns 1.0 if sport is not in the calendar or is in the offseason.

    The multiplier is intended for tier 1/2 league score components only.
    """
    if not sport_key or sport_key not in SEASON_CALENDARS:
        return 1.0

    if now is None:
        now = datetime.now(timezone.utc)

    start_month, playoffs_month = SEASON_CALENDARS[sport_key]
    current_month = now.month

    if playoffs_month >= start_month:
        # Season within same calendar year (e.g., MLB: Mar-Oct, MLS: Feb-Oct)
        season_months = playoffs_month - start_month
        if current_month < start_month or current_month > playoffs_month:
            return 1.0  # Offseason
        months_elapsed = current_month - start_month
    else:
        # Season wraps year boundary (e.g., NBA: Oct-Apr, NFL: Sep-Jan)
        season_months = (12 - start_month) + playoffs_month
        if current_month >= start_month:
            months_elapsed = current_month - start_month
        elif current_month <= playoffs_month:
            months_elapsed = (12 - start_month) + current_month
        else:
            return 1.0  # Offseason

    if season_months <= 0:
        return 1.0

    progress = min(months_elapsed / season_months, 1.0)
    return 0.8 + (0.4 * progress)  # 0.8x early → 1.2x late


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
        sixty_min_ago = now - timedelta(minutes=60)

        # Find the value closest to 30 min ago
        recent_start_val = None
        for i, ts in enumerate(timestamps):
            if ts >= thirty_min_ago:
                recent_start_val = probabilities[i]
                break
        if recent_start_val is not None:
            metrics.recent_momentum = abs(probabilities[-1] - recent_start_val)

        # 4. Momentum acceleration: compare recent 30m shift vs previous 30m shift.
        # Positive acceleration means odds are moving faster now than before.
        prev_start_val = None
        prev_end_val = None
        for i, ts in enumerate(timestamps):
            if ts >= sixty_min_ago and prev_start_val is None:
                prev_start_val = probabilities[i]
            if ts >= thirty_min_ago and prev_end_val is None:
                prev_end_val = probabilities[i]
        if prev_start_val is not None and prev_end_val is not None:
            previous_momentum = abs(prev_end_val - prev_start_val)
            metrics.momentum_acceleration = metrics.recent_momentum - previous_momentum

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
    # Actual end time (from StatPal) for more accurate recently-finished timing
    end_time: Optional[datetime] = None,
    # When the row was marked final. Used as the finish reference when StatPal
    # has no end time, which is the overwhelmingly common case.
    completed_at: Optional[datetime] = None,
    # Game progress (from ESPN period string, e.g. "Q4", "2nd Half", "OT")
    period: Optional[str] = None,
    # The scoreboard (#4580). Optional because 41 of 64 live rows have no score;
    # absent means "we cannot see the field", never "nothing has happened on it".
    home_score: Optional[int] = None,
    away_score: Optional[int] = None,
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

    # #4580 — read the scoreboard ONCE, here, so the capsule and the footer
    # badge describe the same card.
    flags.underdog_is_leading = underdog_leads(opening_home_prob, home_score, away_score)
    flags.someone_is_leading = score_is_decided(home_score, away_score)
    # #5047 — and read the price ONCE too, for the same no-drift reason.
    flags.upset_is_no_longer_in_doubt = upset_is_no_longer_in_doubt(
        opening_home_prob, current_home_prob
    )

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
    # The commence-gate is the shared lifecycle invariant (Queue 283): live is
    # only valid once the authoritative start time has passed.
    flags.is_live = status == "live" and live_start_satisfied(commence_time, now)
    if flags.is_live:
        result.score += WEIGHTS["live"]
        result.reasons.append("live")

        # Graduated late-game bonus: "Live in overtime" is dramatically more
        # interesting than "Live in Q1". Scale bonus with game progress.
        game_progress, is_overtime = parse_game_progress(period, sport_key)
        if is_overtime:
            result.score += WEIGHTS["live_late_game"] + WEIGHTS["live_overtime"]
            result.reasons.append("overtime")
        elif game_progress >= 0.5:
            # Scale from 0 at 50% through the game to full at 100%
            late_bonus = int(WEIGHTS["live_late_game"] * min((game_progress - 0.5) * 2, 1.0))
            if late_bonus > 0:
                result.score += late_bonus
                result.reasons.append("late_game")

    # Starting soon
    if status == "scheduled" and 0 < hours_until <= 3:
        flags.is_starting_soon = True
        result.score += WEIGHTS["starting_soon_3h"]
        result.reasons.append("starting_soon")

        if hours_until <= 1:
            flags.is_starting_very_soon = True
            result.score += WEIGHTS["starting_soon_1h"]
            result.reasons.append("starting_very_soon")

    # Recently finished — prefer the most accurate end reference available.
    #
    # `statpal_end_time` is the authoritative final whistle but is very thinly
    # populated (measured 2026-09-06: NULL on 13/13 of the completed games then
    # holding the Sports feed's first page), so the old two-step cascade fell
    # through to `commence_time` on essentially every row. That measures age from
    # KICKOFF, which is wrong in both directions: a three-hour baseball game that
    # ended sixty seconds ago reads as three hours stale, and a game still being
    # graded reads older than it is. `completed_at` — when the row was actually
    # marked final — sits between the two in accuracy and is populated on the
    # rows `statpal_end_time` misses, so it goes in the middle of the cascade.
    if status in ("completed", "closed"):
        finish_ref = end_time or completed_at or commence_time
        if finish_ref.tzinfo is None:
            finish_ref = finish_ref.replace(tzinfo=timezone.utc)
        hours_since_finish = (now - finish_ref).total_seconds() / 3600
        # Published for the freshness decay even when the 24h eligibility test
        # below fails, so a caller never has to re-derive it off a worse clock.
        result.hours_since_finish = hours_since_finish
        if 0 < hours_since_finish <= 24:
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
            # When opening odds exactly match current odds, the event was
            # just discovered and we have no trend data yet.  Give benefit
            # of the doubt — a close game is interesting until proven
            # otherwise.  Without this, newly-discovered events (e.g.
            # after duplicate cleanup) get no close_matchup bonus and
            # fall below the feed threshold even for marquee matchups.
            no_trend_data = (
                opening_home_prob is not None
                and abs(current_home_prob - opening_home_prob) < 0.005
            )
            closeness_is_interesting = (
                not is_pre_game  # Live/finished: closeness always matters
                or flags.is_starting_soon  # Starting soon: closeness is action-relevant
                or not opening_was_close  # Line tightened from lopsided to close
                or has_movement  # Significant movement even if both close
                or opening_home_prob is None  # No opening data, give benefit of doubt
                or no_trend_data  # Just discovered — no movement data yet
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

        # Momentum acceleration: odds are moving increasingly fast (live only).
        # This catches the "something just happened" signal — a game that was
        # steady suddenly has rapid movement.
        if flags.is_live and time_series.momentum_acceleration >= MOMENTUM_ACCEL_THRESHOLD:
            result.score += WEIGHTS["momentum_accelerating"]
            result.reasons.append("momentum_accelerating")

    # === Clamp score to 0-100 ===
    result.score = max(0, min(100, result.score))

    # === Determine primary reason for display ===
    # Priority order for what to show users
    priority_order = [
        ("upset", "Recent upset"),
        ("overtime", "Overtime"),
        ("favorite_switched", "Possible upset"),
        ("lead_changes", "Lead change"),
        ("very_close", "Coin flip"),
        ("close_matchup", "Close matchup"),
        ("recent_momentum", "Odds shifting fast"),
        ("momentum_accelerating", "Momentum surge"),
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
    if flags.is_live and "overtime" in result.reasons:
        return "Overtime"
    # #4580 — "Upset brewing" names the SCOREBOARD, so the scoreboard has to
    # agree. `favorite_switched` is derived purely from price (see
    # `compute_highlight`), and on 2026-09-09 it put "Upset brewing" on the NFL
    # opener at 0-0 in Q1: the price had moved 0.62 → 0.44 and nothing at all
    # had happened on the field.
    #
    # "Odds moved" is the sentence that IS earned in every other case, because
    # a switched favourite is by definition a price event. That covers the
    # unknown-score rows too (41 of 64 live rows have no score): it asserts only
    # the thing we can actually see.
    if flags.is_live and flags.favorite_switched:
        if flags.underdog_is_leading is not True:
            return "Odds moved"
        # #5047 — and once the market has no doubt left, "brewing" is the wrong
        # tense. SF @ LAR on 2026-09-11 was rank 2 on Discover reading "Upset
        # brewing" at 24-7 with 12:05 left in the 4th, the favourite at 5%, while
        # `signal:blowout` sat on the same payload. Both replacements keep the
        # word "upset", which is what `_DISCOVER_EVENT_EXCEPTION_KEYWORDS`
        # matches on, so neither moves the card's rank.
        if flags.upset_is_no_longer_in_doubt is True:
            return "Upset underway"
        return "Upset brewing"
    if flags.is_live and flags.has_lead_changes:
        return "Lead change"
    if flags.is_live and flags.is_very_close:
        return "Coin flip"
    if flags.is_live and flags.is_close_matchup:
        return "Close game"
    if flags.is_live and flags.has_recent_momentum:
        return "Odds shifting fast"
    if flags.is_live and "momentum_accelerating" in result.reasons:
        return "Momentum surge"
    # #4580 — "Momentum shift" needs a move AND a score. A major swing over a
    # game where nobody has scored is a market event, not momentum; say so.
    if flags.is_live and flags.probability_swing == "major":
        return "Momentum shift" if flags.someone_is_leading is True else "Odds moved"
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

    # Pre-game: significant line movement is a real trend worth labeling.
    #
    # #4094 — "Line moving" is present progressive and pre-game by construction,
    # and this branch carried no settled guard while every branch above it is
    # gated on `flags.is_live`. So a finished game fell straight through to it —
    # and a finished game has a major swing BY CONSTRUCTION, because it opens
    # near 50/50 and ends at 100/0. The swing is the scoreboard restated, not a
    # trend. Measured on production 2026-09-08: two of the three finished MLB
    # cards on the feed (Cardinals @ Giants, Reds @ Dodgers) wore it over a game
    # that was already final.
    #
    # `hours_since_finish` is the settled test, not `flags.is_recently_finished`:
    # it is set unconditionally for every completed/closed row (see the finish
    # cascade above), whereas `is_recently_finished` is a 24h ELIGIBILITY window
    # that goes False again on an older game which is still just as final.
    if flags.probability_swing == "major" and result.hours_since_finish is None:
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
