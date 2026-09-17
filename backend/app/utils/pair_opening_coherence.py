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

THIS MODULE NOW ANSWERS TWO QUESTIONS, NOT ONE (#6793). The opening gate above
shipped in 2026-08 and left ``current_probability`` — the number on the page —
ungoverned, so the same mixed-source pair that is refused an opening is still
*displayed*. :func:`classify_pair_price` is the second question. The two differ in
exactly one clause (provenance; see its docstring) and share this module's
tolerance so that the writer's two gates cannot drift apart the way the writer and
its census could not. Both remain fail-closed and symmetric for the same reason:
one honest-looking leg beside a withdrawn partner is a number with nothing to
check it against.
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


def classify_pair_price(
    yes_prob: Optional[float],
    no_prob: Optional[float],
    *,
    tolerance: float = PAIR_SUM_TOLERANCE,
) -> str:
    """Return :data:`OK` if this pair's two CURRENT prices may both be stored (#6793).

    Same arithmetic as :func:`classify_pair_opening`, asked of the two numbers a
    reader is about to see rather than of the two we publish a forecast from.

    PROVENANCE IS DELIBERATELY NOT TESTED HERE, and that is the whole difference
    between the two questions. :data:`REFUSED_UNPAIRED_SOURCE` fires whenever the
    resolver fell back to ``last_trade_price``, a midpoint or a bare ask — which is
    exactly right for an *opening*, because ``calibration_probability`` falls back
    to ``opening_probability`` and a mixed-source pair becomes a published forecast
    we are then graded on. A current price is not graded: a real last trade is an
    honest answer to "what is this worth now", and refusing it would blank
    thousands of working markets to fix a few hundred broken ones. So this asks
    only the question a reader can check with their own eyes — do these two numbers
    describe one question.

    MEASURED ON PRODUCTION, 2026-09-17, open Polymarket markets. The stored-row
    counts are read-only db-query; the served count is the actual payload of
    ``/api/futures/{id}`` fetched for every one of the 152, NOT a re-derivation of
    the serve predicate against the database (an earlier pass modelled it that way
    and over-counted by more than twentyfold)::

        two-leg decomposed sub-markets                          8,961
        pairs not summing to 1 (tolerance 0.02)                   282
          ... live: both legs ungraded, resolution date ahead      148
          ... of those, last written within 7 days                 139
        SERVED  both contradictory legs rendered              4 and 6
        GRADED  polymarket snapshot rows on that set            3,437
          ... written in the preceding 24 hours                    552

    THE TWO HALVES ARE VERY DIFFERENT SIZES AND THAT IS THE POINT. Serve already
    hides most of this by other means — a leg with no price, a single-leg render,
    the empty-book withdrawal — so only a handful of markets show a reader both
    halves at once, and WHICH ones churns every poll: six at 21:05Z, four at 21:25Z,
    overlapping but not equal. ``Galaxy vs Rapids: O/U 8.5 Total Corners`` was
    photographed on ``/futures/60976220`` reading **Under 50% / Over 48%**.

    Nothing hides the SNAPSHOT half. ``calibration_probability`` reads snapshots
    before it falls back to the opening, so every one of these pairs is graded on a
    price its own partner refutes — and the opening gate that has guarded this
    arithmetic since 2026-08 never reached it. That is the larger half and the
    reason this is worth doing even on a day when the served count is four.

    Why the ingest writer and not the refresh task: ``futures_price_refresh``
    derives the No leg from one price and so cannot produce these, and the measured
    rows are stamped in ``poll_polymarket_markets``' ``:15`` pass.

    OUT OF SCOPE, and measured so the boundary is not guesswork: 419 open
    Polymarket FIELD markets carry a ``_yes``/``_no`` pair among more than two
    outcomes (36 of them incoherent). An earlier sizing pass of this work did not
    require the market to have exactly two outcomes and swept them in. Those are the duplicate-condition-leg shape
    :mod:`app.utils.winner_field_coherence` describes, not this one, and a field of
    independent or cumulative rungs is allowed to sum past 1 (gotcha #23). This
    function cannot reach them: its call site judges the two prices of ONE Gamma
    market, which is a binary by construction, and never a field.

    A ONE-SIDED MARKET IS NOT A PAIR. ``no_prob`` of ``None`` means there is no
    second leg to disagree with, which is the ordinary shape of a great many real
    markets — callers must not ask this of one. :data:`REFUSED_MISSING_LEG` is
    still returned rather than :data:`OK` so that a caller which asks anyway fails
    closed and is legible in the stats, but the ingest call site guards on the leg
    existing before it asks at all.
    """
    return classify_pair_opening(
        yes_prob, no_prob, price_source=PAIRED_PRICE_SOURCE, tolerance=tolerance
    )


def pair_price_allowed(
    yes_prob: Optional[float],
    no_prob: Optional[float],
    *,
    tolerance: float = PAIR_SUM_TOLERANCE,
) -> bool:
    """Boolean form of :func:`classify_pair_price` for call sites that only branch."""
    return classify_pair_price(yes_prob, no_prob, tolerance=tolerance) == OK
