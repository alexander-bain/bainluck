"""CAL-P1215 (#1544, #997) — the paired early/late pre-start cohort, and why the page cannot use the one it has.

**The accuracy page currently splits DIFFERENT outcomes into two groups and
compares their aggregate errors. That is not a test of whether a forecast
improved, because no outcome appears on both sides of it.**

Alex, 2026-09-14: *"core question is whether trading brings forecasts closer to
truth before an event ... Current code compares DIFFERENT outcome cohorts by
price_moved and aggregate ECE; it is not an opening-to-close improvement test on
the SAME outcomes."* This module is the cohort that would be.

THE TRACE — what ``price_moved`` actually is
---------------------------------------------
``precompute_calibration``'s grouping dimension, verbatim::

    (fo.calibration_probability IS NOT NULL
     AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability)

It is a **value inequality between two columns**, not a timing comparison. It
reads no clock and no snapshot. Nothing in it can distinguish "the market traded
and did not move" from "we never captured a second price", and those are the two
populations it merges.

``price_moved = false`` is exactly ``cp_absent ∪ cp_eq_open``, the two classes
:mod:`app.utils.calibration_price_provenance` (CAL-P077) already named and
measured:

``cp_absent``
    ``calibration_probability IS NULL``; the read side supplies the opening.
``cp_eq_open``
    The WRITER already fell back. ``backfill_winners`` Part A banks
    ``COALESCE(closing.probability, opening_probability)``, so an outcome with no
    eligible pre-boundary snapshot **stores its opening under the closing line's
    name**. CAL-P077 measured this at **37% to 84% of every cell** — the larger
    half, and invisible to a ``cp IS NULL`` probe.

So the "false" arm is dominated by rows for which *we hold no second price at
all*. It is a statement about our capture, not about the market.

WHY THE LABELS COMPOUND IT
---------------------------
The page renders these two arms as "traded" and "untraded"
(``lib/calibrationMath.ts``, ``describeActivityComparison``). The repo's own
ruling-011 definition of trading evidence is
:mod:`app.utils.calibration_trade_evidence`, and it uses ``volume`` and
open interest — never this predicate. By that definition ``datagolf`` and
``odds_api`` are ``not_applicable``: they have no volume concept, and **datagolf
has ``calibration == opening`` BY CONSTRUCTION** (``backfill_winners`` Part A1-dg
sets ``calibration_probability = fo.opening_probability`` outright, because a
model prediction has no closing line). A whole source can therefore never leave
the "untraded" arm, and is being counted as evidence about trading.

The two arms differ by source mix and capture quality. An aggregate-ECE
comparison between them measures those, and cannot be read as a claim about what
trading does.

WHAT A HONEST PAIRED COHORT REQUIRES — and what this module enforces
---------------------------------------------------------------------
One outcome contributes BOTH legs, or it contributes nothing:

1. **Same question, same outcome, same resolution.** The pair is keyed on
   ``futures_outcomes.id``, and ``is_winner IS NOT NULL`` — NULL is ungraded
   truth, never a loss (gotcha #21, and the ``is_winner`` annotation in
   ``models.py``).
2. **Both legs are real observations**, taken from ``futures_odds_snapshots``.
   Neither leg may be ``opening_probability``: that column is a derived opening
   (see ``opening_source``) and, on the ``cp_eq_open`` population, it is *also*
   what the close fell back to — using it as the early leg would compare a value
   against itself and publish the artifact as a finding.
3. **Both legs are strictly pre-start**, before the SAME boundary
   ``LEAST(commence_time, resolution_date)`` from
   :func:`app.utils.calibration_closing_line.closing_line_boundary_sql`. That
   clamp is what keeps a mis-linked market's post-settlement quote out (Q436 /
   CAL-P117: 1,525 of 1,739 props rows had been re-priced against one).
4. **Both legs pass the SAME eligibility rule** — the shipped closing-line
   predicate, reused rather than restated, so the early leg cannot be selected
   under a laxer filter. An asymmetric filter manufactures improvement.
5. **The legs are separated in time.** A market polled twice in a minute yields a
   degenerate pair that reads as "no improvement" for a reason that has nothing
   to do with forecasting. :data:`DEFAULT_MIN_SEPARATION_SECONDS` is a policy
   choice, and it is deliberately **not** tuned against an outcome: it is set
   from the measured separation histogram that
   :func:`paired_feasibility_sql` exists to produce.

FEASIBILITY IS AN OPEN QUESTION, NOT A FORMALITY
--------------------------------------------------
CAL-P077 measured, on the hindsight rows of its three worst cells, how many had
**even one** snapshot before the boundary: **0 of 8,387** (basketball/quantity),
**0 of 1,259** (hockey/container_member), **32 of 3,737**
(basketball/container_member). A pair needs two. So "the data supports an early
vs final-pre-event comparison" must be MEASURED before any such label is
promised to a reader, which is what :func:`paired_feasibility_sql` measures and
why it classifies the failures separately instead of returning one count.

If the population is too thin, the honest output is that the page cannot answer
the question — not a thinner version of the claim it makes today.

Pure by construction: no session, no I/O, no clock. The reader that supplies
rows is ``backend/scripts/measure_paired_prestart.py``. Nothing here is wired
into ``precompute_calibration``, which stays frozen under ruling 009.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional, Sequence

from app.utils.calibration_closing_line import (
    closing_line_boundary_sql,
    closing_line_lateral_sql,
    is_eligible_closing_snapshot,
)
from app.utils.calibration_ece import bin_index, calibration_error
from app.utils.resolution_authority import calibration_truth_eligible_sql

__all__ = [
    "DEFAULT_MIN_SEPARATION_SECONDS",
    "PAIR_CLASSES",
    "PAIR_PAIRED",
    "PAIR_NO_LEG",
    "PAIR_SINGLE_LEG",
    "PAIR_TOO_CLOSE",
    "PAIR_UNANCHORED_BOUNDARY",
    "boundary_is_anchored",
    "brier",
    "classify_pair",
    "log_loss",
    "paired_feasibility_sql",
    "paired_improvement",
    "paired_legs_sql",
    "leg_calibration",
    "select_paired_legs",
]


#: Minimum gap between the two legs, in seconds. **Provisional, and it must be
#: set from the histogram, not from a result.** Six hours is a starting value
#: chosen because it is longer than every polling cadence in
#: ``SPORT_POLLING_TIERS``, so a pair that clears it is two genuinely different
#: looks rather than one look sampled twice.
DEFAULT_MIN_SEPARATION_SECONDS = 6 * 3600

#: Why an outcome did or did not yield a pair. Reported separately because
#: "no pair" has four different causes and only one of them is about liquidity.
PAIR_PAIRED = "paired"
PAIR_NO_LEG = "no_eligible_leg"
PAIR_SINGLE_LEG = "single_eligible_leg"
PAIR_TOO_CLOSE = "legs_too_close"

#: CAL-P1216b, on codex's 17:11Z finding: *"LEAST of two timestamps alone does
#: not prove real event start"*, and so a leg drawn before it may not be a
#: **pre-event** forecast at all.
#:
#: The boundary is ``LEAST(e.commence_time, fm.resolution_date)`` over a LEFT
#: JOIN, so it has two provenances and only one of them is a start:
#:
#: * ``e.commence_time`` present — the market is linked to an event that states
#:   when play begins. The LEAST can only move the boundary EARLIER, so every
#:   admitted snapshot is provably before the start. Usable.
#: * ``e.commence_time`` NULL — no linked event, and the boundary silently
#:   becomes ``resolution_date`` alone. That is a SETTLEMENT date: it is at or
#:   after the end of the thing, so a "final pre-event" leg drawn before it can
#:   sit anywhere inside the event, including after the result was effectively
#:   known. A pair built on it would make late forecasts look brilliant for the
#:   reason that they were not forecasts.
#:
#: This is a FOURTH reason an outcome yields no usable pair, not a filter applied
#: elsewhere, and it is deliberately decided FIRST. Only :data:`PAIR_PAIRED`
#: returns probabilities, so the score cannot include an outcome whose boundary
#: nobody can vouch for — the guarantee is structural rather than a rule a caller
#: has to remember. Counted separately so the feasibility walk reports what the
#: requirement COSTS instead of hiding it inside ``no_eligible_leg``.
PAIR_UNANCHORED_BOUNDARY = "unanchored_boundary"

PAIR_CLASSES: tuple[str, ...] = (
    PAIR_PAIRED,
    PAIR_NO_LEG,
    PAIR_SINGLE_LEG,
    PAIR_TOO_CLOSE,
    PAIR_UNANCHORED_BOUNDARY,
)


# ---------------------------------------------------------------------------
# The SQL half
# ---------------------------------------------------------------------------

#: The boundary both legs must precede. One expression, used by both, so they
#: cannot drift apart.
_BOUNDARY = closing_line_boundary_sql("e.commence_time", "fm.resolution_date")

#: The candidate population: resolved, graded, truth-eligible.
#:
#: ``is_winner IS NOT NULL`` is the graded-truth gate — NULL is ungraded truth,
#: never a loss.
#:
#: Truth-eligibility is rendered by :func:`calibration_truth_eligible_sql`, the
#: only sanctioned way to write it: the allowlist is keyed on
#: ``fo.resolution_source`` (HOW the outcome was graded), NOT on ``fm.source``
#: (which venue quoted it), and the function emits the D112 lone-claim shape term
#: with it as one unit. Interpolating the bare constant is what the drift-scan
#: test forbids, and reading it as a market-source list is the mistake it exists
#: to catch.
#:
#: ``n_outcomes_col`` is omitted deliberately: this module has no market-shape
#: join in scope, so the rendered predicate is the shape-blind allowlist, which
#: keeps the population identical to the other readers rather than silently
#: widening it.
_POPULATION_PREDICATE = f"""
      fm.status = 'resolved'
      AND fo.is_winner IS NOT NULL
      AND {calibration_truth_eligible_sql(source_col="fo.resolution_source")}
"""


def paired_legs_sql(
    *,
    min_separation_seconds: int = DEFAULT_MIN_SEPARATION_SECONDS,
    cursor: str = ":cursor",
    scan: str = ":scan",
) -> str:
    """Per-outcome early and late legs, with the separation guard applied.

    Two index seeks per outcome on ``idx_fos_outcome_captured``, the same cost
    profile the shipped closing-line LATERAL already carries in Part A.

    Emits one row per candidate outcome, carrying ``pair_class`` so the callers
    that want the failures (the feasibility fold) and the caller that wants the
    pairs (the score) read the SAME statement rather than two that can disagree.

    ROW-BOUNDED, NOT ID-WIDTH (``census_reachability``'s measured lesson): outcome
    ids are not uniformly dense, so a fixed id span is a few thousand rows in one
    region and millions in another, while ``LIMIT`` costs about the same wherever
    it lands.

    ``cursor``/``scan`` default to bind-parameter names for a task caller. The
    admin ``db-query`` rail the measurement bus uses does not bind, so
    :func:`paired_feasibility_sql` passes literals instead — same statement,
    substituted in one place rather than paraphrased into a second one.
    """
    early = closing_line_lateral_sql(
        outcome_id="fo.id",
        boundary=_BOUNDARY,
        order="ASC",
        columns="fos.probability, fos.captured_at",
    )
    late = closing_line_lateral_sql(
        outcome_id="fo.id",
        boundary=_BOUNDARY,
        order="DESC",
        columns="fos.probability, fos.captured_at",
    )
    return f"""
SELECT fo.id AS outcome_id,
       fm.source AS source,
       COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
       fo.is_winner AS is_winner,
       early.probability AS early_probability,
       early.captured_at AS early_captured_at,
       late.probability AS late_probability,
       late.captured_at AS late_captured_at,
       CASE
           WHEN e.commence_time IS NULL THEN '{PAIR_UNANCHORED_BOUNDARY}'
           WHEN early.captured_at IS NULL THEN '{PAIR_NO_LEG}'
           WHEN late.captured_at <= early.captured_at THEN '{PAIR_SINGLE_LEG}'
           WHEN EXTRACT(EPOCH FROM (late.captured_at - early.captured_at))
                < {min_separation_seconds} THEN '{PAIR_TOO_CLOSE}'
           ELSE '{PAIR_PAIRED}'
       END AS pair_class
FROM futures_outcomes fo
JOIN futures_markets fm ON fm.id = fo.market_id
LEFT JOIN events e ON e.id = fm.event_id
LEFT JOIN LATERAL {early} early ON true
LEFT JOIN LATERAL {late} late ON true
WHERE {_POPULATION_PREDICATE}
  AND fo.id > {cursor}
ORDER BY fo.id ASC
LIMIT {scan}
"""


def paired_feasibility_sql(
    *,
    min_separation_seconds: int = DEFAULT_MIN_SEPARATION_SECONDS,
    cursor: int = 0,
    scan: int = 200_000,
) -> str:
    """How many outcomes yield a usable pair, and why the rest do not — per source.

    This is the query that decides whether the page can answer Alex's question
    at all, so it reports the three failure classes separately: "we never looked
    twice" and "the market is illiquid" are different findings, and summing them
    into one "unusable" count would hide which one this is.

    Literal ``cursor``/``scan`` (ints, not binds) so the statement can be pasted
    straight into the admin ``db-query`` rail, which is what the measurement lane
    actually reaches. Walk the population by feeding the previous window's
    ``MAX(outcome_id)`` back as ``cursor``.

    The gap columns are the histogram input for
    :data:`DEFAULT_MIN_SEPARATION_SECONDS`: that constant is set FROM this
    measurement, never tuned until a cohort looks the way someone hoped.
    """
    if not isinstance(cursor, int) or not isinstance(scan, int):
        raise TypeError("cursor and scan are interpolated as literals; pass ints")
    return f"""
SELECT source,
       pair_class,
       COUNT(*) AS n,
       MIN(EXTRACT(EPOCH FROM (late_captured_at - early_captured_at))) AS min_gap_s,
       AVG(EXTRACT(EPOCH FROM (late_captured_at - early_captured_at))) AS avg_gap_s,
       MAX(EXTRACT(EPOCH FROM (late_captured_at - early_captured_at))) AS max_gap_s,
       MAX(outcome_id) AS max_outcome_id
FROM ({paired_legs_sql(
        min_separation_seconds=min_separation_seconds,
        cursor=str(cursor),
        scan=str(scan),
    )}) legs
GROUP BY source, pair_class
ORDER BY source, pair_class
"""


# ---------------------------------------------------------------------------
# The Python half — same semantics, so the decisions are testable without a DB
# ---------------------------------------------------------------------------


def boundary_is_anchored(event_commence: Any) -> bool:
    """Whether this outcome's boundary is a real event start.

    The whole test is "is there a linked event with a start time", and it is a
    named function rather than an inline ``is not None`` so that the SQL branch,
    the Python mirror and every caller are demonstrably asking one question.
    See :data:`PAIR_UNANCHORED_BOUNDARY` for why the answer decides eligibility.
    """
    return event_commence is not None


def classify_pair(
    early_captured_at: Any,
    late_captured_at: Any,
    *,
    event_commence: Any = None,
    boundary_anchored: Optional[bool] = None,
    min_separation_seconds: int = DEFAULT_MIN_SEPARATION_SECONDS,
) -> str:
    """The ``pair_class`` CASE above, in Python. Mirrors it branch for branch.

    ``boundary_anchored`` is derived from ``event_commence`` unless passed
    explicitly. It is a separate argument because a caller that has already
    resolved provenance (the row carries ``boundary_class``) should not have to
    re-supply a timestamp to say so — and because the unanchored branch is
    testable in isolation that way.
    """
    if boundary_anchored is None:
        boundary_anchored = boundary_is_anchored(event_commence)
    # FIRST, exactly as in the SQL: an outcome whose boundary cannot be proved to
    # precede the event is not a thin pair, it is not a pair at all.
    if not boundary_anchored:
        return PAIR_UNANCHORED_BOUNDARY
    if early_captured_at is None or late_captured_at is None:
        return PAIR_NO_LEG
    if late_captured_at <= early_captured_at:
        return PAIR_SINGLE_LEG
    gap = (late_captured_at - early_captured_at).total_seconds()
    if gap < min_separation_seconds:
        return PAIR_TOO_CLOSE
    return PAIR_PAIRED


def select_paired_legs(
    snapshots: Iterable[Sequence[Any]],
    *,
    event_commence: Any,
    resolution_date: Any = None,
    min_separation_seconds: int = DEFAULT_MIN_SEPARATION_SECONDS,
) -> tuple[str, Optional[float], Optional[float]]:
    """Pick the early and late legs the way :func:`paired_legs_sql` does.

    Args:
        snapshots: rows of ``(captured_at, probability, yes_bid, yes_ask)``, in
            any order — sorted here rather than trusted, exactly as the SQL's
            ``ORDER BY`` does.
        event_commence: the linked event's start.
        resolution_date: the market's own settlement date, or None.

    Returns:
        ``(pair_class, early_probability, late_probability)``. The two
        probabilities are ``None`` for every class except ``paired`` — a caller
        must not be able to score a pair this function refused.
    """
    # Provenance first, before any snapshot is looked at — the SQL's first CASE
    # branch. Without a linked event start the boundary is a settlement date, and
    # a "final pre-event" leg drawn before THAT may sit inside the event.
    if not boundary_is_anchored(event_commence):
        return PAIR_UNANCHORED_BOUNDARY, None, None

    boundary = event_commence
    if resolution_date is not None and resolution_date < boundary:
        boundary = resolution_date

    eligible = []
    for captured_at, probability, yes_bid, yes_ask in snapshots:
        if captured_at >= boundary:
            continue
        if not is_eligible_closing_snapshot(probability, yes_bid, yes_ask):
            continue
        eligible.append((captured_at, float(probability)))

    if not eligible:
        return PAIR_NO_LEG, None, None
    eligible.sort(key=lambda row: row[0])
    early, late = eligible[0], eligible[-1]
    klass = classify_pair(
        early[0],
        late[0],
        # Anchoring was decided above; stated rather than re-derived so this
        # cannot drift from the branch that already returned for it.
        boundary_anchored=True,
        min_separation_seconds=min_separation_seconds,
    )
    if klass != PAIR_PAIRED:
        return klass, None, None
    return PAIR_PAIRED, early[1], late[1]


# ---------------------------------------------------------------------------
# Proper scores. Defined here because the backend had none — and the two
# published numbers must come from ONE definition, not one per leg.
# ---------------------------------------------------------------------------

#: Log loss is unbounded at p in {0, 1}. Eligibility already rejects those
#: (``0 < p < 1``), so this clamp should never bind; it is here so that a caller
#: passing unfiltered rows gets a large finite penalty rather than ``inf``
#: silently poisoning a mean.
_LOG_EPS = 1e-9


def brier(probability: float, is_winner: bool) -> float:
    """Squared error of one forecast. Lower is better; range [0, 1]."""
    return (float(probability) - (1.0 if is_winner else 0.0)) ** 2


def log_loss(probability: float, is_winner: bool) -> float:
    """Negative log likelihood of one forecast. Lower is better."""
    p = min(max(float(probability), _LOG_EPS), 1.0 - _LOG_EPS)
    return -math.log(p) if is_winner else -math.log(1.0 - p)


def paired_improvement(
    pairs: Iterable[tuple[float, float, bool]],
    *,
    score: str = "brier",
) -> Optional[dict[str, Any]]:
    """Mean per-outcome score improvement from the early leg to the late leg.

    Args:
        pairs: ``(early_probability, late_probability, is_winner)`` — one tuple
            per OUTCOME. Both probabilities describe the same question and the
            same resolution, which is the entire point of the pairing.
        score: ``"brier"`` or ``"log_loss"``.

    Returns:
        ``None`` when there is nothing to report — an empty cohort, or a single
        pair, for which a standard error does not exist. **Never ``0.0``**: a
        perfect-looking score standing in for no data is gotcha #53 at the top of
        this product's most-cited number.

        Otherwise ``{"n", "mean_delta", "se", "early_mean", "late_mean"}``, where
        ``mean_delta = mean(early_score - late_score)`` — so a **POSITIVE
        ``mean_delta`` means the final pre-event forecast scored BETTER** than
        the early one. The sign convention is stated here because it is the
        sentence a reader will be shown, and getting it backwards inverts the
        product's claim.

        ``se`` is the standard error OF THE PAIRED DIFFERENCE — computed on the
        per-outcome deltas, not from the two means. The legs are strongly
        correlated (same question, hours apart), so an unpaired error bar
        computed from two marginal variances would be far too wide and would
        report "no detectable change" on a real one.
    """
    if score not in ("brier", "log_loss"):
        raise ValueError(f"unknown score {score!r}")
    fn = brier if score == "brier" else log_loss

    deltas: list[float] = []
    early_scores: list[float] = []
    late_scores: list[float] = []
    for early_p, late_p, is_winner in pairs:
        e = fn(early_p, is_winner)
        lt = fn(late_p, is_winner)
        early_scores.append(e)
        late_scores.append(lt)
        deltas.append(e - lt)

    n = len(deltas)
    if n < 2:
        return None

    mean_delta = sum(deltas) / n
    variance = sum((d - mean_delta) ** 2 for d in deltas) / (n - 1)
    return {
        "n": n,
        "mean_delta": mean_delta,
        "se": math.sqrt(variance / n),
        "early_mean": sum(early_scores) / n,
        "late_mean": sum(late_scores) / n,
    }


def leg_calibration(
    pairs: Iterable[tuple[float, float, bool]],
    *,
    min_bin_n: int = 0,
) -> dict[str, Optional[float]]:
    """ECE of each leg, over the SAME paired population. Reported separately.

    Alex asked for the proper-score comparison and the calibration comparison to
    be kept apart, and they answer different questions: a forecast can sharpen
    (better Brier) while drifting off the diagonal (worse ECE). Binning and the
    error itself are :mod:`app.utils.calibration_ece`'s, imported so this cannot
    disagree with the curve about what an ECE is.

    ``min_bin_n`` defaults to 0 here, not to the production floor: the paired
    population is a strict subset of the published one and will be small, so a
    floor borrowed from the full curve would silently empty it. The caller sets
    the floor it can defend and states it.
    """
    early_bins: dict[int, dict[str, float]] = {}
    late_bins: dict[int, dict[str, float]] = {}
    for early_p, late_p, is_winner in pairs:
        won = 1 if is_winner else 0
        for value, bins in ((early_p, early_bins), (late_p, late_bins)):
            b = bins.setdefault(bin_index(float(value)), {"n": 0, "winners": 0, "sum_prob": 0.0})
            b["n"] += 1
            b["winners"] += won
            b["sum_prob"] += float(value)
    return {
        "early_ece_pp": calibration_error(early_bins.values(), min_bin_n=min_bin_n),
        "late_ece_pp": calibration_error(late_bins.values(), min_bin_n=min_bin_n),
    }
