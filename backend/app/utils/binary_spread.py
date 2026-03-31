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
from typing import Optional

logger = logging.getLogger(__name__)


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
