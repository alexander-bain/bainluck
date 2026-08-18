"""ONE canonical calibration-error definition (Fable addendum, CAL-P067).

The addendum's instruction: reconcile the v3835 cohort-market-type table's
methodology (200k sample, 10-bin, n-weighted, n>=30) with the sentinel's into
one canonical ECE, because *two parallel instruments measuring ECE differently
is a contradiction machine*.

**Measured first, before reconciling anything: the contradiction machine is
already running, and it predates v3835.** On the live payload, 2026-08-17:

    baseball    mce=1.94  ece=1.94  mce_unweighted=1.81  mce_worst=1.81
    soccer      mce=3.54  ece=3.54  mce_unweighted=3.90  mce_worst=3.90

``ece == mce`` on EVERY published cell, and ``mce_worst == mce_unweighted`` on
every published cell. So the API ships **four field names carrying two
quantities** — and the two names for each are not synonyms in anyone's
vocabulary:

* The n-weighted number is published as both ``mce`` AND ``ece``, and is
  computed by a function called ``_compute_horizon_mce``. The frontend's own
  docstring calls that same number ECE ("the n-weighted headline metric").
* The equal-weighted number is published as both ``mce_unweighted`` AND
  ``mce_worst``.

Textbook usage is ECE = expected (n-weighted) calibration error, MCE = maximum
calibration error. Ours is neither consistently: the equal-weighted MEAN is
published under a name that says MAX. Anyone comparing "the MCE" across two of
our own surfaces can therefore be comparing two different statistics while both
call themselves MCE. That is the contradiction machine, and no amount of adding
the shape axis fixes it — it would just multiply it by seven shapes.

So this module states the definition ONCE, parameterised, and everything else
becomes a named configuration of it rather than a reimplementation.

WHAT ACTUALLY DIFFERS between the two instruments, once written down:

===================  ======================  =========================
parameter            production curve        v3835 shape table
===================  ======================  =========================
bins                 10 fixed-width          10 fixed-width      AGREE
bin assignment       min(floor(p*10), 9)     same                AGREE
weighting            n-weighted              n-weighted          AGREE
per-bin floor        **none**                **n >= 30**         DIFFER
population           full                    200k sample         DIFFER
===================  ======================  =========================

Only two knobs differ, and they pull in known directions. The floor is the one
that changes a number: without it a bin of n=2 is still a bin, which is the
r108 "mlb spreads 16.4pp" artifact class (harmless under n-weighting, dominant
under equal weighting — which is exactly why the equal-weighted variant is the
one we call "worst-bucket sensitive"). Sampling widens the interval; it does
not move the estimate.

This module does NOT rewrite the production call sites. ``precompute_calibration``
is frozen (ruling 009) and its ``_compute_horizon_mce`` is inside the digest
that invalidates the in-flight staged cursor. Reconciliation here means: state
the definition once, and PIN with a test that the frozen implementation already
computes it. A second implementation that provably agrees is not a second
definition — it is the first one, written down.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional

#: Ten fixed-width bins over [0, 1]. Both instruments already agree on this, so
#: it is recorded as the canonical choice rather than proposed as one.
CANONICAL_BINS = 10

#: n-weighted: each bin contributes in proportion to how many outcomes are in
#: it. This is the headline number — it reflects the outcomes users actually
#: saw. Textbook ECE.
WEIGHTING_N = "n"

#: Equal-weighted: every bin counts the same, so a thin tail bin can dominate.
#: Deliberately kept, because worst-bucket sensitivity is a real thing to want;
#: it is simply not ECE, and must not be published under a name that says MCE
#: either, since it is a MEAN and not a MAX.
WEIGHTING_EQUAL = "equal"

#: v3835's per-bin floor. Production uses 0 (no floor). Named rather than
#: inlined so the one real methodological difference between the two
#: instruments is a value you can pass, diff and test — not a property of
#: whichever file you happened to read.
V3835_MIN_BIN_N = 30
PRODUCTION_MIN_BIN_N = 0

#: The published field names, and the (weighting, floor) each one actually is.
#: Four names, two quantities — see the module docstring. Recorded here so the
#: duplication is at least documented while it exists, and so a test can assert
#: it has not silently grown a fifth name.
PUBLISHED_FIELD_DEFINITIONS: dict[str, tuple[str, int]] = {
    "ece": (WEIGHTING_N, PRODUCTION_MIN_BIN_N),
    "mce": (WEIGHTING_N, PRODUCTION_MIN_BIN_N),
    "mce_unweighted": (WEIGHTING_EQUAL, PRODUCTION_MIN_BIN_N),
    "mce_worst": (WEIGHTING_EQUAL, PRODUCTION_MIN_BIN_N),
}


def bin_index(probability: float, *, bins: int = CANONICAL_BINS) -> int:
    """Which bin a probability falls in — the Python twin of the build's SQL.

    The build computes ``LEAST(FLOOR(prob * 10)::int, 9)``. The ``LEAST`` is
    load-bearing and easy to drop: ``p = 1.0`` floors to 10, which is an
    eleventh bin in a ten-bin scheme. Reproduced exactly, and pinned by a test,
    because a Python scorer that bins differently from the SQL is a
    contradiction machine with extra steps.
    """
    idx = int(math.floor(probability * bins))
    return max(0, min(idx, bins - 1))


def calibration_error(
    bins: Iterable[dict[str, Any]],
    *,
    weighting: str = WEIGHTING_N,
    min_bin_n: int = PRODUCTION_MIN_BIN_N,
) -> Optional[float]:
    """Mean |actual - predicted| over bins, in percentage points.

    ``bins`` is any iterable of ``{"n", "winners", "sum_prob"}``. Returns
    ``None`` for an empty or fully-floored cohort — never ``0.0``, which would
    be a perfect score standing in for no data (gotcha #53, and the same rule
    this queue's ruling-075 fix enforces on the phase plan).

    ``min_bin_n`` drops bins below the floor entirely rather than reweighting
    them, which is what v3835 does and what "n >= 30" means.
    """
    live = []
    for b in bins:
        n = b.get("n") or 0
        if n <= 0 or n < min_bin_n:
            continue
        live.append(b)
    if not live:
        return None

    total_err = 0.0
    total_w = 0.0
    for b in live:
        n = b["n"]
        actual = b["winners"] / n
        predicted = b["sum_prob"] / n
        w = n if weighting == WEIGHTING_N else 1
        total_err += abs(actual - predicted) * w
        total_w += w
    if total_w == 0:
        return None
    return round(total_err / total_w * 100, 2)


def ece(bins: Iterable[dict[str, Any]], *, min_bin_n: int = PRODUCTION_MIN_BIN_N):
    """The headline calibration error: n-weighted. Textbook ECE."""
    return calibration_error(bins, weighting=WEIGHTING_N, min_bin_n=min_bin_n)


def equal_weighted_error(
    bins: Iterable[dict[str, Any]], *, min_bin_n: int = PRODUCTION_MIN_BIN_N
):
    """Equal-weighted mean error — worst-bucket sensitive.

    Named for what it IS. Published today as both ``mce_unweighted`` and
    ``mce_worst``; the latter name claims a maximum and this is a mean.
    """
    return calibration_error(bins, weighting=WEIGHTING_EQUAL, min_bin_n=min_bin_n)


def v3835_ece(bins: Iterable[dict[str, Any]]):
    """The shape table's parameterisation: n-weighted with an n>=30 bin floor.

    A named configuration of the one definition above, which is the whole point
    of this module — the shape table and the curve now differ by a VALUE you can
    read, not by an implementation you have to go and compare.
    """
    return calibration_error(bins, weighting=WEIGHTING_N, min_bin_n=V3835_MIN_BIN_N)


def floor_divergence(bins: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """How much the v3835 floor moves this cohort's number, and off what.

    The reconciliation's practical output: applying a floor is legitimate, and
    silently applying a *different* floor from the surface next to it is not.
    This makes the delta explicit so a shape cell and a category cell that
    disagree can be attributed rather than argued about.
    """
    materialized = [dict(b) for b in bins]
    unfloored = ece(materialized, min_bin_n=PRODUCTION_MIN_BIN_N)
    floored = ece(materialized, min_bin_n=V3835_MIN_BIN_N)
    dropped = [b for b in materialized if 0 < (b.get("n") or 0) < V3835_MIN_BIN_N]
    return {
        "production_ece": unfloored,
        "v3835_ece": floored,
        "delta_pp": (
            None if unfloored is None or floored is None else round(floored - unfloored, 2)
        ),
        "bins_dropped_by_floor": len(dropped),
        "outcomes_dropped_by_floor": sum(b.get("n") or 0 for b in dropped),
        "min_bin_n": V3835_MIN_BIN_N,
    }
