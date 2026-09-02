"""The one decision that turns a venue's outcome prices into a blend reading.

Queue 460. `Event.win_probability_sources` is the number every card and every
hero renders, and until this module existed exactly one writer could move it:
the 120-second `poll_live_prediction_markets` pass. The Kalshi WebSocket dyno
has been streaming sub-second prices into `futures_outcomes.current_probability`
the whole time — measured 2026-08-30, 4 of 10 live outcomes moved inside a 25s
window — and not one of those moves reached the blend. The fast lane stopped one
table short of the number.

The fix is to let the WS dyno stamp the blend too. That immediately raises the
question this module answers: **the poll and the fast lane must compute the same
number from the same rows, or the hero flickers between two writers' opinions
every two minutes.** So the decision is extracted here, once, and both callers
use it. A second copy of this arithmetic is the #1951 failure mode — a drifted
predicate does not throw, it just quietly disagrees with itself.

WHAT IS AND IS NOT IN HERE. This is the *pure* half: given the markets and
outcomes already loaded for one (event, source) pair, what home probability does
that source assert? It does no I/O, so it is testable without a database and it
cannot be the thing that makes a 2-second flush loop slow. The impure half — the
inversion cross-check against sportsbook consensus, and the JSONB stamp itself —
stays with its callers, because the two callers legitimately differ there (the
poll can afford a per-event consensus query every 120s; the fast lane caches
that verdict, see `app/tasks/live_blend_refresh.py`).

DUCK-TYPED ON PURPOSE. `market` and `outcome` are whatever the caller loaded —
ORM rows in both live callers. The attributes read are named in
`MarketOutcomes`, and nothing here writes to them. That keeps the extraction
faithful: the poll's behaviour is unchanged because it is literally the same
expression, moved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from app.utils.prediction_market_matching import (
    extract_matchup_with_ticker_fallback,
    feeds_win_prob_blend,
    find_moneyline_outcome,
)


@dataclass(frozen=True)
class MarketOutcomes:
    """One linked market plus the outcomes already loaded for it.

    ``market`` must expose ``id``, ``source``, ``external_id`` and ``name``.
    ``outcomes`` items must expose ``rank``, ``name`` and ``current_probability``
    (``find_moneyline_outcome`` reads the latter two).
    """

    market: Any
    outcomes: Sequence[Any]


def is_game_winner_market(market: Any) -> bool:
    """Whether this market's YES side is a game winner that feeds the blend.

    Only Kalshi is gated: its tickers distinguish game winners from spreads,
    totals and props, and `feeds_win_prob_blend` is the measured admission rule.
    Polymarket game markets arrive already decomposed, so the source itself
    carries no equivalent signal and the caller's linkage is trusted — which is
    exactly how the poll has always treated it.
    """
    if market.source != "kalshi" or not market.external_id:
        return False
    return feeds_win_prob_blend(market.external_id)


def select_primary_market(group: Sequence[MarketOutcomes]) -> Optional[MarketOutcomes]:
    """Pick the one market in a (event, source) group that speaks for the source.

    Kalshi mints a separate binary market per team ("Celtics win?" and
    "76ers win?"), both linked to the same event. A game-winner market always
    beats a non-game-winner; among equals the lowest market id wins, so the
    choice is stable across passes rather than dependent on row order.
    """
    if not group:
        return None
    primary = group[0]
    for candidate in group[1:]:
        primary_is_gw = is_game_winner_market(primary.market)
        candidate_is_gw = is_game_winner_market(candidate.market)
        if candidate_is_gw and not primary_is_gw:
            primary = candidate
        elif primary_is_gw == candidate_is_gw and candidate.market.id < primary.market.id:
            primary = candidate
    return primary


@dataclass(frozen=True)
class BlendReading:
    """What one source asserts about one event, plus the row it came from.

    Callers need more than the number: the poll stamps the originating outcome's
    name and raw YES price into the snapshot's ``game_state``, which is the audit
    trail for "why did the blend say that". Returning the number alone would have
    forced the caller to re-find the outcome and risk finding a different one.
    """

    home_probability: float
    market: Any
    outcome: Any
    yes_probability: float
    devigged: bool


def _home_probability_for_market(
    entry: MarketOutcomes, matchup: Any, home_team_name: str, away_team_name: str
) -> Optional[tuple[float, Any, float]]:
    """This single market's implied home probability, or None if it can't say.

    ``matchup`` is the PRIMARY market's parse, deliberately, and it is passed in
    rather than re-derived per market. Kalshi's per-team pair carries two
    different market names for one game, so re-deriving would let the two halves
    of a devig disagree about which side is home — averaging a home reading with
    an away one, silently, only on the two-market path.
    """
    ordered = sorted(entry.outcomes, key=lambda o: o.rank or 999)
    if not ordered:
        return None

    ml_result = find_moneyline_outcome(
        ordered, matchup, home_team_name, away_team_name,
    )
    if not ml_result:
        return None

    outcome, yes_is_home = ml_result
    if outcome.current_probability is None:
        return None
    yes_prob = float(outcome.current_probability)
    home_prob = yes_prob if yes_is_home else 1.0 - yes_prob
    return home_prob, outcome, yes_prob


def compute_source_home_probability(
    group: Sequence[MarketOutcomes],
    home_team_name: str,
    away_team_name: str,
) -> Optional[BlendReading]:
    """The home win probability this source asserts, or None if it asserts none.

    ``group`` is every linked market of ONE source for ONE event, each with its
    outcomes. Returns None — never a guess — whenever the market is not a game
    winner, the matchup cannot be parsed, or no moneyline outcome is found.

    DEVIG. When the source published exactly two markets for the game (Kalshi's
    per-team pair), both sides are resolved and averaged, which cancels the vig
    the two YES prices carry in opposite directions. With one market, or when
    the sibling cannot be resolved, the single reading stands as-is: an average
    of one usable number and one absent one is not a devig, it is a coin flip
    wearing the word.
    """
    primary = select_primary_market(group)
    if primary is None:
        return None

    # Kalshi props/spreads never write the blend, whatever they are linked to.
    if primary.market.source == "kalshi" and primary.market.external_id:
        if not feeds_win_prob_blend(primary.market.external_id):
            return None

    # Uses the ticker fallback for generically-named Kalshi markets.
    matchup = extract_matchup_with_ticker_fallback(
        primary.market.name, external_id=primary.market.external_id,
    )
    if not matchup:
        return None

    primary_reading = _home_probability_for_market(
        primary, matchup, home_team_name, away_team_name,
    )
    if primary_reading is None:
        return None

    home_prob, outcome, yes_prob = primary_reading
    devigged = False

    if len(group) == 2:
        for sibling in group:
            if sibling.market.id == primary.market.id:
                continue
            sibling_reading = _home_probability_for_market(
                sibling, matchup, home_team_name, away_team_name,
            )
            if sibling_reading is not None:
                home_prob = (home_prob + sibling_reading[0]) / 2.0
                devigged = True

    return BlendReading(
        home_probability=home_prob,
        market=primary.market,
        outcome=outcome,
        yes_probability=yes_prob,
        devigged=devigged,
    )
