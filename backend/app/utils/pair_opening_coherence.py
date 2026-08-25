"""Whether a two-sided market's two opening prices may be stamped at all.

WHAT WENT WRONG. A decomposed Polymarket sub-market writes an Over/Yes leg and an
Under/No leg. The Over leg's price is *source-resolved* — ``outcome_prices[0]``, or
a bid/ask midpoint, or ``last_trade_price``, or a bare ask, whichever survives the
placeholder and fabricated-midpoint guards. The Under leg's price was taken raw
from ``outcome_prices[1]`` with no guard at all. When the resolver did NOT pick
``outcome_prices[0]``, the two legs of one binary were therefore written **from two
different price sources**, and summed to 1 only by luck.

MEASURED (2026-08-24, whole resolved Polymarket population, 470,976 two-leg
markets, ``artifacts/cal-p094/ou_pair_census_all.json``):

    complementary       339,587  72.10%   67.688% captured post-2026-07-08
    partial_open        106,948  22.71%    0.913%
    identical_noncomp    18,875   4.01%    0.058%   <- fixed at 231e39c3
    other_noncomp         5,566   1.18%   11.337%   <- STILL BEING WRITTEN

The ``identical_noncomp`` class — the Over price copied verbatim onto the Under
leg — is dead: 11 markets carry an opening stamped after the ``231e39c3``
(2026-07-08) Under-side fix, against a 67.7% post-fix base rate. That defect was
already repaired. ``other_noncomp`` was not, and it is the mixed-source pair above.

WHY THIS REFUSES RATHER THAN REPAIRS. The tempting fix is to write the Under leg
as ``1 - prob``. That invents a price: it asserts the book was two-sided at a
level nobody quoted, and it would be indistinguishable afterwards from a real
quote. ``calibration_probability`` falls back to ``opening_probability``, so an
invented opening becomes a *published forecast* the platform is then graded on.
A NULL opening means the leg is simply not on the curve — which is the honest
treatment of a pair we cannot price coherently, and it is reversible: the snapshot
path fills ``calibration_probability`` from real prices whenever real prices exist.

So the gate is fail-closed and symmetric: incoherent pair -> stamp NEITHER leg.
Stamping only the coherent-looking side would leave a half-open pair whose single
published number carries no partner to check it against, which is how a 22.7%
``partial_open`` population came to exist in the first place.
"""

from __future__ import annotations

from typing import Optional

#: A two-outcome Polymarket market's ``outcome_prices`` are normalised upstream, so
#: a real pair sums to 1 up to float noise: the measured ``complementary`` class
#: averages 1.0001 across 339,587 markets. 0.02 is loose enough that ordinary
#: rounding and any residual vig pass, and far tighter than the defect — the
#: original specimen (Purdue/UCLA O/U 143.5, both legs 0.040) sums to 0.08, and the
#: ``other_noncomp`` class averages sums like 0.88, 1.12 and 1.33.
#:
#: This is the same constant the census folds use. It is defined HERE and imported
#: there rather than restated, because a tolerance that drifted between the writer
#: and the census would let the writer's own guard disagree with the measurement
#: that justified it.
PAIR_SUM_TOLERANCE = 0.02

#: The only resolver source that is a leg of the same normalised pair as
#: ``outcome_prices[1]``. Every other source is a different instrument — a
#: midpoint we computed, a trade that happened at some earlier moment, a one-sided
#: ask — and pairing it with the raw complement is a category error even when the
#: two numbers happen to sum to 1.
PAIRED_PRICE_SOURCE = "outcome_prices"

#: Verdicts. Named rather than boolean because the refusal reasons are counted
#: separately in task stats: "we declined 900 pairs" is not actionable, "we
#: declined 900 pairs because the resolver fell back to last-trade" is.
OK = "ok"
REFUSED_UNPAIRED_SOURCE = "refused_unpaired_source"
REFUSED_SUM_OUT_OF_TOLERANCE = "refused_sum_out_of_tolerance"
REFUSED_IDENTICAL_LEGS = "refused_identical_legs"
REFUSED_MISSING_LEG = "refused_missing_leg"

REFUSAL_VERDICTS = (
    REFUSED_UNPAIRED_SOURCE,
    REFUSED_SUM_OUT_OF_TOLERANCE,
    REFUSED_IDENTICAL_LEGS,
    REFUSED_MISSING_LEG,
)


def classify_pair_opening(
    yes_prob: Optional[float],
    no_prob: Optional[float],
    *,
    price_source: Optional[str] = PAIRED_PRICE_SOURCE,
    tolerance: float = PAIR_SUM_TOLERANCE,
) -> str:
    """Return :data:`OK` if both legs of this pair may be stamped as openings.

    ``price_source`` is where ``yes_prob`` came from — see
    :data:`PAIRED_PRICE_SOURCE`. Callers that genuinely hold both raw legs of one
    normalised pair pass the default.

    The checks run in this order deliberately. Provenance is tested BEFORE
    arithmetic, because a mixed-source pair that happens to sum to 1.00 is still
    two different instruments glued together and would otherwise pass silently —
    the sum is evidence about the numbers, the source is evidence about what they
    are. Identical legs are then named apart from a general sum failure even
    though the sum check would already catch them, because that is the historical
    ``231e39c3`` class and a regression there must be legible as itself rather
    than buried in a generic counter.
    """
    if yes_prob is None or no_prob is None:
        return REFUSED_MISSING_LEG
    if price_source != PAIRED_PRICE_SOURCE:
        return REFUSED_UNPAIRED_SOURCE
    if yes_prob == no_prob and abs(2.0 * yes_prob - 1.0) > tolerance:
        return REFUSED_IDENTICAL_LEGS
    if abs((yes_prob + no_prob) - 1.0) > tolerance:
        return REFUSED_SUM_OUT_OF_TOLERANCE
    return OK


def pair_opening_allowed(
    yes_prob: Optional[float],
    no_prob: Optional[float],
    *,
    price_source: Optional[str] = PAIRED_PRICE_SOURCE,
    tolerance: float = PAIR_SUM_TOLERANCE,
) -> bool:
    """Boolean form of :func:`classify_pair_opening` for call sites that only branch."""
    return (
        classify_pair_opening(
            yes_prob, no_prob, price_source=price_source, tolerance=tolerance
        )
        == OK
    )
