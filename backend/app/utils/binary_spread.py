"""
Binary contract → implied spread/total/projected score utilities.

Prediction markets (Kalshi, Polymarket) offer binary "Team wins by X+"
contracts at multiple thresholds. This module:
1. Derives an implied spread by interpolating the 50% probability crossover
2. Derives an implied total from "Total exceeds X" contracts
3. Combines spread + total into a projected final score

Example:
    contracts = [
        {"threshold": 1.0, "probability": 0.87},
        {"threshold": 3.5, "probability": 0.76},
        {"threshold": 5.5, "probability": 0.66},
        {"threshold": 7.5, "probability": 0.60},
        {"threshold": 10.5, "probability": 0.48},
        {"threshold": 14.5, "probability": 0.26},
    ]
    implied = binary_to_implied_spread(contracts)
    # => {"spread": -10.0, "confidence": 0.95}
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


# Fallback preference between venues when their readings are equally trusted.
PROJECTION_SOURCE_ORDER: tuple[str, ...] = ("kalshi", "polymarket", "sportsbook")


def _projection_source_rank(
    implied: dict,
    source: str,
    order: Sequence[str],
) -> tuple[float, int, str]:
    """Sort key for one source's arm: best first.

    Negated confidence so ``min``/``sorted`` read as "best first"; the trailing
    name keeps two unknown sources at equal confidence deterministic.
    """
    entry = implied.get(source) or {}
    try:
        confidence = float(entry.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    try:
        tie_break = order.index(source)
    except ValueError:
        tie_break = len(order)
    return (-confidence, tie_break, source)


def rank_projection_sources(
    implied: Optional[dict],
    order: Sequence[str] = PROJECTION_SOURCE_ORDER,
) -> list[str]:
    """Every source's arm, best first, by the rule ``select_projection_source`` picks with.

    The ranked list exists so a caller that finds the best arm unusable can walk
    to the next one instead of serving the unusable answer or nothing at all
    (#3921 repair `3921-PROJECTION-SELECTION-CANNOT-EMIT-NEGATIVE-SCORES`).
    """
    if not implied:
        return []
    return sorted(implied, key=lambda s: _projection_source_rank(implied, s, order))


def select_projection_source(
    implied: Optional[dict],
    order: Sequence[str] = PROJECTION_SOURCE_ORDER,
) -> Optional[str]:
    """Pick which source's implied value feeds the projected final score.

    Highest ``confidence`` wins; ``order`` breaks ties. Until #3921 the choice
    was position in ``order`` alone, so a Kalshi spread at confidence 0.3 beat
    a sportsbook spread at confidence 1.0 sitting in the same dict — the
    confidence was computed, serialised, and never read by the one thing it
    was computed for.

    A source missing from ``order`` is still eligible: it sorts after the
    known ones rather than being dropped, so a venue added after this list
    was written can never be silently discarded by an allowlist that predates
    it. A missing or unparseable ``confidence`` sorts as 0.0 — still eligible,
    because a sole arm is better than no projection, but never preferred over
    an arm that states one.

    This is ``rank_projection_sources(...)[0]`` and is kept as the name callers
    use when they want the single best arm; the two can never disagree because
    there is one ranking rule.
    """
    ranked = rank_projection_sources(implied, order)
    return ranked[0] if ranked else None


@dataclass
class ImpliedSpread:
    """Result of binary-to-spread derivation."""
    spread: float  # Negative = favorite (e.g., -10 means favorite by 10)
    confidence: float  # 0-1, how close the bracketing contracts are to 50%
    lower_threshold: float
    upper_threshold: float
    lower_prob: float
    upper_prob: float


@dataclass
class ImpliedTotal:
    """Result of binary-to-total derivation."""
    total: float
    confidence: float
    lower_threshold: float
    upper_threshold: float
    lower_prob: float
    upper_prob: float


@dataclass
class ProjectedScore:
    """Projected final score from spread + total."""
    home_score: float
    away_score: float
    spread: float
    total: float
    spread_source: Optional[str] = None
    total_source: Optional[str] = None


def binary_to_implied_spread(
    contracts: list[dict],
    crossover: float = 0.50,
) -> Optional[ImpliedSpread]:
    """
    Derive implied spread from binary "wins by X+" contracts.

    Args:
        contracts: List of dicts with "threshold" (float) and "probability" (float, 0-1).
                   Threshold is the margin (e.g., 7.5 means "wins by 7.5+").
                   Probability is the market's implied probability of that outcome.
        crossover: The probability to interpolate at (default 0.50).

    Returns:
        ImpliedSpread with the interpolated spread, or None if not enough data.
    """
    if not contracts or len(contracts) < 2:
        return None

    # Sort by threshold ascending
    sorted_contracts = sorted(contracts, key=lambda c: c["threshold"])

    # Find two adjacent contracts that straddle the crossover
    for i in range(len(sorted_contracts) - 1):
        low = sorted_contracts[i]
        high = sorted_contracts[i + 1]

        low_prob = low["probability"]
        high_prob = high["probability"]

        # Probabilities should decrease as threshold increases
        # (harder to win by more points)
        if low_prob >= crossover >= high_prob:
            # Linear interpolation
            prob_range = low_prob - high_prob
            if prob_range < 0.001:
                # Degenerate case: both ~50%
                spread = (low["threshold"] + high["threshold"]) / 2
            else:
                fraction = (low_prob - crossover) / prob_range
                spread = low["threshold"] + fraction * (high["threshold"] - low["threshold"])

            # Confidence based on how tight the bracket is
            bracket_width = high["threshold"] - low["threshold"]
            confidence = max(0.0, min(1.0, 1.0 - (bracket_width / 20.0)))

            return ImpliedSpread(
                spread=-round(spread, 1),  # Negative = favorite
                confidence=round(confidence, 2),
                lower_threshold=low["threshold"],
                upper_threshold=high["threshold"],
                lower_prob=low_prob,
                upper_prob=high_prob,
            )

    # Edge cases: all above or all below crossover
    if sorted_contracts[0]["probability"] < crossover:
        # All below 50% — team is a big underdog at every threshold
        return ImpliedSpread(
            spread=-sorted_contracts[0]["threshold"] * 0.5,
            confidence=0.3,
            lower_threshold=0,
            upper_threshold=sorted_contracts[0]["threshold"],
            lower_prob=crossover,
            upper_prob=sorted_contracts[0]["probability"],
        )

    if sorted_contracts[-1]["probability"] > crossover:
        # All above 50% — team is a massive favorite at every threshold
        last = sorted_contracts[-1]
        return ImpliedSpread(
            spread=-last["threshold"] * 1.5,
            confidence=0.3,
            lower_threshold=last["threshold"],
            upper_threshold=last["threshold"] * 2,
            lower_prob=last["probability"],
            upper_prob=crossover,
        )

    return None


def binary_to_implied_total(
    contracts: list[dict],
    crossover: float = 0.50,
) -> Optional[ImpliedTotal]:
    """
    Derive implied total from binary "total exceeds X" contracts.

    Same interpolation logic as spread, but for total points.

    Args:
        contracts: List of dicts with "threshold" (float) and "probability" (float, 0-1).
                   Threshold is the points total (e.g., 220.5 means "over 220.5").
        crossover: The probability to interpolate at (default 0.50).
    """
    if not contracts or len(contracts) < 2:
        return None

    sorted_contracts = sorted(contracts, key=lambda c: c["threshold"])

    for i in range(len(sorted_contracts) - 1):
        low = sorted_contracts[i]
        high = sorted_contracts[i + 1]

        low_prob = low["probability"]
        high_prob = high["probability"]

        if low_prob >= crossover >= high_prob:
            prob_range = low_prob - high_prob
            if prob_range < 0.001:
                total = (low["threshold"] + high["threshold"]) / 2
            else:
                fraction = (low_prob - crossover) / prob_range
                total = low["threshold"] + fraction * (high["threshold"] - low["threshold"])

            bracket_width = high["threshold"] - low["threshold"]
            confidence = max(0.0, min(1.0, 1.0 - (bracket_width / 10.0)))

            return ImpliedTotal(
                total=round(total, 1),
                confidence=round(confidence, 2),
                lower_threshold=low["threshold"],
                upper_threshold=high["threshold"],
                lower_prob=low_prob,
                upper_prob=high_prob,
            )

    return None


def projected_final_score(
    spread: float,
    total: float,
    home_is_favorite: bool = True,
) -> ProjectedScore:
    """
    Calculate projected final score from spread + total.

    Formula:
        If home is favorite (spread is negative):
            home_score = (total - spread) / 2   (higher because they're favored)
            away_score = (total + spread) / 2
        If away is favorite:
            home_score = (total + spread) / 2
            away_score = (total - spread) / 2

    Note: spread should be negative for the favorite.
    """
    # spread is negative for favorite, so:
    # home_score = (total + abs(spread)) / 2 when home is favorite
    # which is (total - spread) / 2 since spread is negative
    home_score = (total - spread) / 2
    away_score = (total + spread) / 2

    return ProjectedScore(
        home_score=round(home_score, 1),
        away_score=round(away_score, 1),
        spread=spread,
        total=total,
    )


def projection_is_renderable(projection: ProjectedScore) -> bool:
    """Can this pair be shown to a reader as a final score?

    A team cannot score a negative number of points, so a pair whose margin
    exceeds its total is not a scoreline — it is proof that the spread and the
    total came from two different quantities. Production served
    ``7.9 – -6.4`` on a Detroit v Minnesota page (#3951) because a spread
    derived from 1st-5-innings rungs (−14.25) was combined with a real
    9-inning total (8.0).

    This is the arithmetic invariant, not a plausibility heuristic: it asks
    only whether ``|spread| <= total``, and so can never reject a pair that
    describes one real game.
    """
    return projection.home_score >= 0 and projection.away_score >= 0


def select_projected_final(
    implied_spreads: Optional[dict],
    implied_totals: Optional[dict],
    order: Sequence[str] = PROJECTION_SOURCE_ORDER,
) -> Optional[tuple[str, str, ProjectedScore]]:
    """Best ``(spread_source, total_source, projection)`` whose scores are renderable.

    Pairs are walked best-first by combined confidence with ``order`` as the
    tie-break, so **when the preferred pair is renderable this returns exactly
    what picking each arm independently returns** — the two arms' confidences
    are independent, so maximising their sum maximises each. The walk therefore
    only becomes visible when the preferred pair is *not* renderable, which is
    the whole of its job: the required repair
    `3921-PROJECTION-SELECTION-CANNOT-EMIT-NEGATIVE-SCORES` asks that an
    unusable pair fall back to the next valid source rather than be served.

    ``None`` when no pair is renderable. Serving no projection is the correct
    end of the walk: a reader who sees nothing has lost a number, while a
    reader who sees ``8 – -6`` has been told something false about the game.
    """
    if not implied_spreads or not implied_totals:
        return None

    pairs = [
        (spread_source, total_source)
        for spread_source in rank_projection_sources(implied_spreads, order)
        for total_source in rank_projection_sources(implied_totals, order)
    ]
    pairs.sort(
        key=lambda pair: (
            _projection_source_rank(implied_spreads, pair[0], order)[0]
            + _projection_source_rank(implied_totals, pair[1], order)[0],
            _projection_source_rank(implied_spreads, pair[0], order)[1:],
            _projection_source_rank(implied_totals, pair[1], order)[1:],
        )
    )

    for spread_source, total_source in pairs:
        spread = (implied_spreads.get(spread_source) or {}).get("spread")
        total = (implied_totals.get(total_source) or {}).get("total")
        if spread is None or total is None:
            continue
        projection = projected_final_score(spread, total)
        if projection_is_renderable(projection):
            return (spread_source, total_source, projection)

    return None


# =========================================================================
# Market title parsing — extract threshold from outcome/market names
# =========================================================================

# Spread patterns: "Team wins by 9.5+", "BOS -9.5", "+9.5", etc.
_SPREAD_THRESHOLD_RE = re.compile(
    r"(?:wins?\s+by|margin)\s+(\d+(?:\.\d+)?)\+?"
    r"|(?:^|[a-zA-Z]\s+)([+-]\d+(?:\.\d+)?)\s*(?:points?|pts?)?\s*$"
    r"|(?:spread|by)\s+([+-]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Total patterns: "Over 220.5", "Total exceeds 219.5", "O/U 222", etc.
_TOTAL_THRESHOLD_RE = re.compile(
    r"(?:over|exceeds?|above)\s+(\d+(?:\.\d+)?)"
    r"|(?:total|o/u)\s+(\d+(?:\.\d+)?)"
    r"|(\d+(?:\.\d+)?)\s+(?:or\s+more|total)",
    re.IGNORECASE,
)


def extract_spread_threshold(text: str) -> Optional[float]:
    """Extract the spread threshold from a market title or outcome name."""
    m = _SPREAD_THRESHOLD_RE.search(text)
    if m:
        for g in m.groups():
            if g is not None:
                try:
                    return abs(float(g))
                except ValueError:
                    continue
    return None


def extract_total_threshold(text: str) -> Optional[float]:
    """Extract the total threshold from a market title or outcome name."""
    m = _TOTAL_THRESHOLD_RE.search(text)
    if m:
        for g in m.groups():
            if g is not None:
                try:
                    return float(g)
                except ValueError:
                    continue
    return None
