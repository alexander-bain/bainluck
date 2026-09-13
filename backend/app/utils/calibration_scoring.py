"""CAL-P998 — the cells-at-bar score, computed by the APP instead of by a script.

D46 = A (Alex, 2026-09-03). Until this module existed, the one number the
calibration program is steered by — *cells at bar* — existed only while
``backend/scripts/calibration_scorecard.py`` was running. Two consequences, both
observed:

* **Nobody could read the needle without running something.** The measurement
  bus therefore invented its own script-free read off ``by_category``
  (``14/36 cats ece<=3.0`` in ``ARTIFACT-M-R-NEEDLES-20260903-16``) while the
  lane quoted ``34/48`` off the script. Two true numbers, two cuts, no single
  place that said so — which reads as a contradiction to everyone downstream.
* **A number that only exists inside a script cannot be dated by the artifact
  it describes.** Re-running the script against a stale payload re-prints a
  current-looking figure for a curve that has not moved.

So the scoring moves here, next to the thing that publishes it, and
``/api/calibration`` carries BOTH cuts with the thresholds that produced them.
The two numbers now reconcile in one place because they are computed in one
place, from the one payload actually being served.

WHAT IS HERE AND WHAT IS DELIBERATELY NOT
-----------------------------------------
Here: the thresholds, the fold, the per-cell verdict, the counts, the category
cut, and — since CAL-P1002 — the MEASURED SIGMA OVERLAY. These are the parts
that decide a published number.

Not here: the ledger BUILDER, the markdown renderer and the history ledger.
Those are reporting machinery around the score; they decide nothing and they
write to ``artifacts/``, which has no business on a request path.

AMENDED 2026-09-04 (CAL-P1002) — D62 = A: THE MEASURED SIGMA DECIDES
---------------------------------------------------------------------
CAL-P998 shipped this module with the overlay deliberately left in the script,
and said why: the overlay reported and decided nothing, so it had no effect on
``cells_at_bar`` and dragging a file read onto the request path bought nothing.
Alex flipped that on 2026-09-04. ``SIGMA_GATE`` is a ratified rule about
STANDARD ERRORS; ``cell_se_pp`` is a documented *estimate* of that quantity and
the measured cluster bootstrap is a *measurement* of it, so substituting one for
the other honours the ratified rule rather than changing it.

Once it decides, it has to live here, and that is D46's rule doing the work
rather than a preference: ``cells_at_bar`` is a SERVED field computed in this
module, so an overlay that moves it from a script would make the served needle
and the script's needle two different numbers on day one — the exact condition
D46 ended six weeks after it was created.

**Nothing about the flip is silent.** Every cell carries ``sigma_row``,
``sigma_measured`` and ``sigma_basis``; every cell carries the verdict it would
have had on the estimate (``verdict_row_basis``); and the block publishes
``sigma_overlay`` with the counterfactual needle, the delta, and a named list of
every cell whose verdict the measurement actually changed. On the 2026-09-04
board that list has exactly one entry — ``kalshi/golf``, 3.19 sigma estimated,
1.86 measured, 23,194 excess-outcomes coming off the queue — and the needle
moves 34/48 to 35/48. A needle that moves as a side effect of an instrument
landing is how a board starts flattering itself; a needle that moves with its
receipt attached is a measurement.

ONE DEFINITION, TWO CALLERS. ``backend/scripts/calibration_scorecard.py``
imports every threshold, the fold and now the overlay from this module rather
than restating them. That direction is the load-bearing one: the app cannot
import the script (``scripts/`` is not on the dyno's path and never will be), so
if the script kept the definitions the served field would be a second
implementation of the bar — which is the exact drift this change exists to end.

THIS MODULE IMPORTS NOTHING FROM THE APP EXCEPT ``calibration_sigma``, which is
its sibling leaf and itself imports nothing. Same rule as ``sport_keys.py`` and
for the same reason: it is consumed by a route, by a task and by a standalone
script, and a circular import discovered on the dyno is discovered at boot. Two
leaves that both import nothing cannot form a cycle, which is why this one
import is admissible and a third would need the same argument made again.

NAMING, because one key does not mean here what it means in the script
----------------------------------------------------------------------
The script's ``counts.cells_total`` is EVERY folded cell (325 on the q269
curve), and its ``counts.cells_material`` is the needle's denominator (48).
D46 names the served field ``cells_total``, and the needle Alex reads is
"34 of 48" — so on the wire ``cells_total`` is the MATERIAL count and the
all-cells figure is published beside it as ``cells_scored``. Nothing is hidden
and nothing is renamed in place; the mapping is asserted by
``test_calibration_scoring_998.py`` so the two can never drift apart silently.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from app.utils import calibration_sigma as sigma_ledger

# ---------------------------------------------------------------------------
# THE FINISH LINE — thresholds. Each carries its derivation in the script's
# docstrings; the values are ratified and are changed in exactly one place.
# ---------------------------------------------------------------------------

#: The READER-ACTIONABILITY bar in pp — the default, the ceiling no class may
#: exceed, and the flat bar the category cut is scored against.
BAR_PP = 3.0

#: Categories that are a scheduled contest with a fixed, near-term settlement.
#: Splits EXCHANGE cells into B and C only; ``odds_api*`` is class A whatever
#: its category, because the class is about the price, not the sport.
GAME_CATEGORIES: frozenset[str] = frozenset({
    "baseball", "basketball", "soccer", "hockey", "football", "tennis", "golf",
    "cricket", "esports", "mma", "motorsports", "table_tennis", "boxing",
    "cycling", "horse_racing", "lacrosse", "rugby", "chess",
})

CLASS_A = "A_multibook_consensus"
CLASS_B = "B_exchange_contest"
CLASS_C = "C_exchange_standalone"

#: RATIFIED per-cohort bars, pp (Alex, MC, 2026-08-28).
CLASS_BARS_PP: dict[str, float] = {
    CLASS_A: 2.5,
    CLASS_B: BAR_PP,
    CLASS_C: BAR_PP,
}

#: Cells smaller than this are MATERIAL-EXEMPT: measured, listed, never queued.
#: 1,000 is the payload's OWN disclosure floor (``min_category_outcomes``), so
#: the score's scope and the page's scope are the same set.
MIN_CELL_N = 1000

#: A cell is only QUEUED if its excess over the bar is established at this many
#: standard errors.
SIGMA_GATE = 2.0

#: Overall published headline target, in pp, on ``mce_closing_line``. A
#: regression guard, not a goal — "fixed" is the per-cell table.
HEADLINE_TARGET_PP = 2.0

#: Cells HELD BACK from the published score because the prices underneath them
#: are known-bad, not because the cells are small or the sample is thin (#5401,
#: the #4745 defect surviving in the shape its predicate cannot see: Kalshi
#: openings with no order book behind them were published as ~0.95 confidence
#: and won 0.1-51%).
#:
#: WHY A SEPARATE SET AND NOT ``MIN_CELL_N``. These are not small — ``kalshi/golf``
#: carries 22,191 outcomes. Folding them into ``EXEMPT_BELOW_MIN_N`` would file a
#: data defect under "too small to matter" and make the needle read honest for the
#: wrong reason. A held-back cell is measured, named on the page and in the
#: methodology ledger, and excluded from BOTH the numerator and the denominator —
#: scoring a cell we already know is built on prices nobody quoted would publish a
#: verdict about our arithmetic that is really a verdict about our data.
#:
#: TEMPORARY BY CONSTRUCTION. This set empties when #5401's repair lands and the
#: affected rows are recounted; it is a deciding constant (it is in
#: :func:`scoring_policy_material`), so it cannot shrink or grow without moving
#: the fingerprint and forcing a ledger entry.
HELD_BACK_CELLS: frozenset[str] = frozenset(
    {"kalshi/golf", "kalshi/entertainment", "polymarket/golf"}
)

#: Why :data:`HELD_BACK_CELLS` are held, in the words the page and the payload
#: both use. One string, so the reader's line and the wire can never disagree.
HELD_BACK_REASON = (
    "built on opening prices that no order book stood behind (#5401); "
    "held back until the prices are repaired and the cells recounted"
)

#: The issue a held-back cell is waiting on.
HELD_BACK_ISSUE = "#5401"


# ---------------------------------------------------------------------------
# THE METHOD ID — D134 (Alex, 2026-09-11)
# ---------------------------------------------------------------------------
# "Every grading/blending/calibration calculation carries a versioned METHOD id;
# a METHODOLOGY LEDGER ... is kept forever and published with the accuracy page
# ... As long as we can inform a skeptical auditor of what changes we've made to
# our calculations, we can't be accused of anything nefarious if we are only
# trying to make the calculations better over time."
#
# A published cell already says WHICH POPULATION it was scored on
# (``population_version``). It did not say WHICH METHOD scored it, and the two
# are independent: the same rows graded under a different bar, a different
# ``SIGMA_GATE`` or a different carry rule are a different number. Without a
# method id, every figure this board has ever published is indistinguishable
# from every other, and "regrade under the old method" — the thing D134 says the
# retained evidence exists to make possible — has nothing to name.
#
# TWO FIELDS, AND THE SECOND ONE IS WHY THIS WORKS. ``version`` is set by hand
# and is what a ledger entry cites. ``fingerprint`` is DERIVED from the deciding
# constants themselves. A guard test pins the pair, so a constant cannot move
# without the fingerprint moving, and the fingerprint cannot move without
# somebody bumping the version and writing the ledger entry that explains it.
# A hand-set version alone would be a promise; the pair is a mechanism.

#: The id a methodology-ledger entry cites. Bump this — never edit it in place —
#: whenever :func:`scoring_policy_fingerprint` changes, and add the ledger entry
#: in the same commit. ``m1`` is the method in force since D62 (2026-09-04, the
#: measured sigma decides); changes BEFORE the scheme existed are narrated in the
#: ledger rather than numbered, because inventing ids for them retroactively
#: would imply a precision the record does not have.
#: ``m2`` (2026-09-12) holds back the three #5401 cells — see
#: :data:`HELD_BACK_CELLS`.
SCORING_POLICY_VERSION = "m2"

#: When ``SCORING_POLICY_VERSION`` came into force — the D62 deploy, not the day
#: the id was added. Dated from the ruling so the ledger and the wire agree.
SCORING_POLICY_IN_FORCE_SINCE = "2026-09-12"


def scoring_policy_material() -> dict:
    """Every constant that can change a published verdict, in one dict.

    THE SCOPE IS THE CLAIM. What is in here is what the fingerprint can defend;
    what is not in here can change silently, so the omissions are named rather
    than left to be discovered:

    * **``classify``'s ``odds_api`` prefix rule is CODE, not a constant**, and no
      hash of values can see it. A change there re-classes cells into a different
      bar without moving the fingerprint. It is the one deciding rule this guard
      does not cover, and it is called out in the ledger for that reason.
    * The fold (``CELL_KEYS``) and the bin count are shape, not thresholds; they
      change WHICH cells exist rather than how one is judged, and the payload's
      own ``population_version`` already moves when they do.

    ``sorted`` on the category set and ``sort_keys`` on the dump make this stable
    across processes — a fingerprint that depended on set iteration order would
    differ between two dynos scoring the same board, which is worse than none.
    """
    return {
        "bar_pp": BAR_PP,
        "class_bars_pp": dict(CLASS_BARS_PP),
        "game_categories": sorted(GAME_CATEGORIES),
        "min_cell_n": MIN_CELL_N,
        "sigma_gate": SIGMA_GATE,
        "headline_target_pp": HEADLINE_TARGET_PP,
        "se_convention_pp": SE_CONVENTION_PP,
        # Which cells are held back decides verdicts as directly as any
        # threshold: a cell in here is removed from the needle's numerator AND
        # its denominator, so the set cannot move without the published score
        # moving. `sorted` for the same cross-process stability as the
        # categories above.
        "held_back_cells": sorted(HELD_BACK_CELLS),
        # From the sibling leaf, because they decide too: these two bands say
        # which measured entries are allowed to set a cell's sigma at all, so a
        # change to either regrades cells without touching a threshold here.
        "cell_drift_band": list(sigma_ledger.CELL_DRIFT_BAND),
        "coverage_band": list(sigma_ledger.COVERAGE_BAND),
    }


def scoring_policy_fingerprint() -> str:
    """12 hex of sha256 over :func:`scoring_policy_material`.

    Deliberately NOT :func:`hash` — that is salted per process (``PYTHONHASHSEED``)
    and would give a different answer on every dyno for the same method.
    """
    blob = json.dumps(scoring_policy_material(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def classify(source: str, category: str) -> str:
    """The cohort class of a published cell. Structural, never numeric."""
    if (source or "").startswith("odds_api"):
        return CLASS_A
    return CLASS_B if category in GAME_CATEGORIES else CLASS_C


def bar_for(source: str, category: str) -> float:
    """The ratified bar this cell is scored against, in pp."""
    return CLASS_BARS_PP[classify(source, category)]


#: The numerator of the board's binomial standard-error convention, in pp. Named
#: rather than inlined for one reason: it DECIDES — it sets every cell's sigma on
#: the estimate basis — and :func:`scoring_policy_fingerprint` can only cover a
#: value that has a name. A literal buried in a function body is a deciding
#: constant that no guard can see.
SE_CONVENTION_PP = 50.0


def cell_se_pp(n: int) -> float:
    """Standard error of a cell's ECE in pp. ``50/sqrt(n)``, the board's convention."""
    return SE_CONVENTION_PP / math.sqrt(n) if n > 0 else float("inf")


# ---------------------------------------------------------------------------
# Fold
# ---------------------------------------------------------------------------

#: The published cell key. ``price_moved`` is a REPORTING stratum, not a cell:
#: the payload splits buckets by it but publishes ``by_category`` / ``by_source``
#: pooled across it, so pooling here is what reproduces the published number.
CELL_KEYS = ("source", "category")


def _pool(buckets: Iterable[dict], keys: tuple[str, ...]) -> dict[tuple, dict[int, dict]]:
    """``key -> {bucket_idx: {n, winners, sum_prob}}``, pooled to 10 bins.

    Pooling to ``bucket_idx`` is the load-bearing line. Folding at bucket-ROW
    granularity instead inflates every cell, because errors that cancel inside a
    bin no longer can — measured 2026-08-27 on the live payload, 34 of 34 cells
    wrong and every one high (soccer 2.80 -> 3.91, hockey 0.95 -> 2.32).
    """
    out: dict[tuple, dict[int, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"n": 0, "winners": 0, "sum_prob": 0.0})
    )
    for row in buckets:
        key = tuple(row.get(k) for k in keys)
        b = out[key][int(row["bucket_idx"])]
        b["n"] += int(row.get("n") or 0)
        b["winners"] += int(row.get("winners") or 0)
        b["sum_prob"] += float(row.get("sum_prob") or 0.0)
    return out


def _stats(bins: dict[int, dict]) -> dict:
    """n-weighted 10-bin ECE and signed gap, in pp.

    Signed gap travels beside ECE because ECE is an absolute value and therefore
    cannot say WHICH WAY a cell is wrong.
    """
    n = sum(b["n"] for b in bins.values())
    if not n:
        return {"ece": None, "n": 0, "gap": None}
    err = sum(
        abs(b["winners"] / b["n"] - b["sum_prob"] / b["n"]) * b["n"]
        for b in bins.values()
        if b["n"]
    )
    gap = sum(b["sum_prob"] - b["winners"] for b in bins.values())
    return {"ece": round(err / n * 100, 2), "n": n, "gap": round(gap / n * 100, 2)}


def fold(payload: dict, keys: tuple[str, ...] = CELL_KEYS) -> list[dict]:
    """Fold the payload's ``buckets`` into cells keyed by ``keys``."""
    cells = []
    for key, bins in _pool(payload.get("buckets") or [], keys).items():
        row = dict(zip(keys, key))
        row.update(_stats(bins))
        cells.append(row)
    return cells


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

#: Cell verdicts. The two "not queued" failures are DISTINCT on purpose: a cell
#: can fail the bar because it is genuinely bad but too small to matter
#: (``EXEMPT``), or because the sample cannot tell it from the bar
#: (``UNDER_SIGMA``). Collapsing them puts a real small-cell defect and a noise
#: reading in the same pile.
VERDICT_PASS = "PASS"
VERDICT_QUEUED = "OVER_BAR_ESTABLISHED"
VERDICT_UNDER_SIGMA = "OVER_BAR_UNESTABLISHED"
VERDICT_EXEMPT = "EXEMPT_BELOW_MIN_N"

#: A cell whose PRICES are known-bad (:data:`HELD_BACK_CELLS`). Distinct from
#: ``EXEMPT_BELOW_MIN_N`` for the reason that set is separate: "we are not
#: grading this because it is tiny" and "we are not grading this because we
#: should never have stored the prices" are different admissions, and a reader
#: who cannot tell them apart has been told the wrong thing.
VERDICT_HELD_BACK = "EXEMPT_HELD_BACK_PRICE_REPAIR"

#: Verdicts that take a cell OUT of the material set — the needle's denominator.
#: One tuple, so the three places that compute `material` cannot drift apart;
#: they did not drift before only because there was one member.
NON_MATERIAL_VERDICTS = (VERDICT_EXEMPT, VERDICT_HELD_BACK)


def is_material(cell: dict) -> bool:
    """Whether a scored cell counts toward the needle, either way.

    The needle is ``at_bar / material``, so a non-material cell is absent from
    both halves — this is the one predicate that decides which.
    """
    return cell["verdict"] not in NON_MATERIAL_VERDICTS


def verdict_for(
    n: int, excess_pp: float, sigma: float | None, cell: str | None = None
) -> str:
    """The one place a cell's verdict is decided.

    ``cell`` is the ``source/category`` key. It is checked FIRST and before
    ``n``: a held-back cell is held back whatever its size, and passing ``None``
    (every caller that is not scoring a real cell) keeps the pre-#5401
    behaviour exactly.
    """
    if cell is not None and cell in HELD_BACK_CELLS:
        return VERDICT_HELD_BACK
    if n < MIN_CELL_N:
        return VERDICT_EXEMPT
    if excess_pp <= 0:
        return VERDICT_PASS
    if sigma is not None and sigma >= SIGMA_GATE:
        return VERDICT_QUEUED
    return VERDICT_UNDER_SIGMA


#: Basis labels for a cell's sigma. A sigma on this board is one of two
#: different quantities and they must never share a column unlabelled
#: (CAL-P127 lesson 10: a proof and an estimate do not belong in the same one).
SIGMA_BASIS_ROW = "binomial_row_estimate"
SIGMA_BASIS_MEASURED = "measured_cluster_bootstrap"

#: A BOARD-level label, never a cell-level one: it says the gate was applied to
#: whichever of the two each cell actually had. A board where the overlay covers
#: 4 of 14 queued cells is not "measured" and it is not "estimated", and calling
#: it either would be the same kind of single-word overclaim the two cell-level
#: labels exist to prevent.
SIGMA_BASIS_PER_CELL = "per_cell_measured_where_available"


def attach_measured_sigma(cell: dict, ledger: dict | None, pop: str | None) -> None:
    """Overlay the measured cluster-bootstrap sigma onto a scored cell.

    Sets ``sigma_basis`` on every cell and, where a usable entry exists,
    ``sigma_measured`` plus the provenance a reader needs to age it. It does NOT
    set ``verdict`` — :func:`score_cells` does that from
    :func:`deciding_sigma`, so there is exactly one place a verdict is decided
    and it is the same place it was before D62.

    WHICH ENTRIES ARE ALLOWED TO DECIDE
    -----------------------------------
    ``FRESH`` and ``CARRIED`` (``DECIDING_STATUSES``). ``CARRIED`` decides
    because the ledger stores the SE precisely BECAUSE the SE is the term that
    does not move when the ECE, the bar or the population version do — the cell
    being the same size within ``CELL_DRIFT_BAND`` is the test that the sample
    is still the sample that was measured. Excluding it would have made D62 a
    no-op on the board it was ruled for: on 2026-09-04 all four measured queued
    cells are ``CARRIED`` from ``q268`` and none is ``FRESH``.

    ``STALE`` contributes nothing at all — gotcha #53, the ledger returning a
    number is not the number applying here.

    ``POPULATION_DIVERGENCE`` is the subtler case and gets the subtler
    treatment: its numbers ARE shown, because they are the only measurement of
    that cell anyone has, and it decides NOTHING. When the rail and the payload
    disagree about how many rows the cell holds, the SE and the excess describe
    different populations and their ratio is not a sigma of either. Which side
    is wrong is not decided here and must not be guessed — on
    ``polymarket/basketball`` the payload is the inflated side (CAL-P126: 43.44%
    phantom, 13,116 rows for 7,419 distinct outcomes); on ``polymarket/hockey``
    there is no phantom measurement and no warrant for assuming the same cause.

    THE RESIDUAL, NAMED. A stable ``n`` is necessary, not sufficient — a cell
    could exchange its rows wholesale and keep its count. There is no cheap
    payload-side test for that, so a carried row carries
    ``measured_at_population`` and ``measured_generated_at`` and the age of the
    measurement is a fact on the board rather than a constant buried in a file.
    A carried entry is a standing request to re-measure, and ``sigma_overlay``
    counts them so the measurement lane can see that backlog.
    """
    cell["sigma_basis"] = SIGMA_BASIS_ROW
    if not ledger:
        return
    entry, status = sigma_ledger.lookup(
        ledger, cell["source"], cell["category"], pop, cell.get("n")
    )
    cell["sigma_ledger_status"] = status
    if status not in (
        sigma_ledger.STATUS_FRESH,
        sigma_ledger.STATUS_CARRIED,
        sigma_ledger.STATUS_POPULATION_DIVERGENCE,
    ):
        return
    se = entry.get("se_bootstrap_pp")
    if not se:
        return
    # The PAYLOAD excess over the MEASURED SE. A deliberate, documented basis
    # shift: the quantity the gate is about is the significance of the PUBLISHED
    # excess, so the payload belongs in the numerator, and the best available
    # estimate of that excess's standard error is the one that measured the
    # correlation structure instead of assuming it away. See the ledger's
    # docstring — the two ECEs are never collapsed into one field.
    cell["sigma_measured"] = round(cell["excess_pp"] / se, 2)
    cell["se_measured_pp"] = round(se, 4)
    cell["variance_ratio_vs_board"] = entry.get("variance_ratio_vs_board")
    cell["effective_n"] = entry.get("effective_n")
    cell["exact_coverage"] = entry.get("exact_coverage")
    cell["measured_at_population"] = entry.get("population_version")
    if status == sigma_ledger.STATUS_CARRIED:
        cell["measured_carried"] = True
        cell["carried_drift"] = sigma_ledger.cell_drift(entry, cell.get("n"))
        cell["measured_generated_at"] = entry.get("generated_at")


def deciding_sigma(cell: dict) -> tuple[float | None, str]:
    """``(sigma, basis)`` — the ONE sigma this cell's verdict is taken from.

    A measurement of the gate's own quantity beats an estimate of it, so a
    measured sigma wins wherever the ledger says it may decide. Everywhere else
    the board's ``50/sqrt(n)`` estimate stands, unchanged and still doing real
    work: on the 2026-09-04 board it is what decides 10 of the 14 queued cells.
    """
    if (
        cell.get("sigma_measured") is not None
        and cell.get("sigma_ledger_status") in sigma_ledger.DECIDING_STATUSES
    ):
        return cell["sigma_measured"], SIGMA_BASIS_MEASURED
    return cell.get("sigma_row"), SIGMA_BASIS_ROW


def score_cells(payload: dict, ledger: dict | None = None) -> list[dict]:
    """Every ``(source, category)`` cell of the payload, scored and ranked.

    Ranked by excess-outcomes — how much wrongness the cell puts in front of
    readers — because a 22 pp cell over 118 rows and a 0.5 pp cell over 100,000
    are not the same repair job.

    ``ledger`` is the measured-sigma ledger (:mod:`app.utils.calibration_sigma`).
    Passing ``None`` scores on the board's row estimate alone — the pre-D62
    behaviour, kept reachable because it is the fallback when the ledger cannot
    be read and because every guard needs to be able to ask for it by name.
    """
    pop = payload.get("population_version")
    cells = []
    for c in fold(payload):
        n, ece = c["n"], c["ece"]
        if ece is None:
            continue
        cell_key = f"{c['source']}/{c['category']}"
        klass = classify(c["source"], c["category"])
        bar = CLASS_BARS_PP[klass]
        excess = round(ece - bar, 2)
        se = cell_se_pp(n)
        sigma_row = round(excess / se, 2) if se else None
        cell = {
            "cell": cell_key,
            "source": c["source"],
            "category": c["category"],
            "ece": ece,
            "n": n,
            "gap": c["gap"],
            # The bar travels WITH the cell: a queued row printing only its
            # excess cannot be checked without knowing which of three bars
            # produced it.
            "class": klass,
            "bar_pp": bar,
            "excess_pp": excess,
            # `sigma_row` is the board's estimate and is ALWAYS present.
            # `sigma` is whichever quantity actually decided, and `sigma_basis`
            # says which — CAL-P1002. Keeping both on the row is what makes the
            # flip auditable from the served payload alone.
            "sigma_row": sigma_row,
            "excess_outcomes": round(max(0.0, excess) * n),
            # The counterfactual, on every cell: what this verdict WOULD be on
            # the estimate. It is what `cells_at_bar_row_basis` is summed from,
            # so the published delta is derived from the same rows a reader can
            # check rather than from a second pass nobody sees.
            "verdict_row_basis": verdict_for(n, excess, sigma_row, cell_key),
        }
        attach_measured_sigma(cell, ledger, pop)
        sigma, basis = deciding_sigma(cell)
        cell["sigma"] = sigma
        cell["sigma_basis"] = basis
        cell["verdict"] = verdict_for(n, excess, sigma, cell_key)
        # The reason travels ON the cell, not only in the aggregate list: a
        # consumer that reads one row must be able to say why it is not graded
        # without joining back to a set it may not have.
        if cell["verdict"] == VERDICT_HELD_BACK:
            cell["held_back_reason"] = HELD_BACK_REASON
            cell["held_back_issue"] = HELD_BACK_ISSUE
        cells.append(cell)
    cells.sort(key=lambda c: (-c["excess_outcomes"], -c["n"]))
    return cells


def cell_counts(cells: list[dict]) -> dict:
    """The needle's arithmetic, over already-scored cells."""
    material = [c for c in cells if is_material(c)]
    queued = [c for c in cells if c["verdict"] == VERDICT_QUEUED]
    unestablished = [c for c in cells if c["verdict"] == VERDICT_UNDER_SIGMA]
    return {
        "cells_total": len(cells),
        "cells_material": len(material),
        "cells_material_outcomes": sum(c["n"] for c in material),
        "cells_pass": sum(1 for c in material if c["verdict"] == VERDICT_PASS),
        "cells_queued": len(queued),
        "cells_unestablished": len(unestablished),
        # `cells_exempt` keeps its meaning — every non-material cell — because
        # consumers already sum it against `cells_total`. The held-back cells
        # are a NAMED SUBSET of it, published separately rather than carved out,
        # so no existing arithmetic changes shape.
        "cells_exempt": len(cells) - len(material),
        "cells_held_back": sum(
            1 for c in cells if c["verdict"] == VERDICT_HELD_BACK
        ),
        "held_back_outcomes": sum(
            c["n"] for c in cells if c["verdict"] == VERDICT_HELD_BACK
        ),
        "queued_excess_outcomes": sum(c["excess_outcomes"] for c in queued),
        # The NEEDLE numerator. A material cell is "at bar" iff it is not queued
        # — the same test ``done`` applies, so the lane's one glanceable number
        # and the page's verdict can never disagree.
        "cells_at_bar": len(material) - len(queued),
        # The same needle on the board's row estimate alone — the number this
        # board read before D62. Published, not discarded: a needle that changes
        # basis without its counterfactual beside it is a needle nobody can
        # check. CAL-P1002.
        "cells_at_bar_row_basis": len(material) - sum(
            1 for c in material if c["verdict_row_basis"] == VERDICT_QUEUED
        ),
    }


def per_class(cells: list[dict]) -> dict:
    """Cells at bar split by the cohort class whose bar scored them."""
    material = [c for c in cells if is_material(c)]
    return {
        klass: {
            "bar_pp": CLASS_BARS_PP[klass],
            "cells": sum(1 for c in material if c["class"] == klass),
            "at_bar": sum(
                1 for c in material
                if c["class"] == klass and c["verdict"] != VERDICT_QUEUED
            ),
            "queued": sum(
                1 for c in material
                if c["class"] == klass and c["verdict"] == VERDICT_QUEUED
            ),
            "outcomes": sum(c["n"] for c in material if c["class"] == klass),
        }
        for klass in CLASS_BARS_PP
    }


# ---------------------------------------------------------------------------
# The overlay's own receipt — CAL-P1002 / D62
# ---------------------------------------------------------------------------

#: ``sigma_overlay.status``. ``applied`` means the ledger was read and its
#: measurements decided; ``unavailable`` means the score fell back to the row
#: estimate and says which reason. There is no third value, and in particular no
#: value meaning "read but empty": an empty ledger is ``applied`` over zero
#: cells, which the counts say plainly.
OVERLAY_APPLIED = "applied"
OVERLAY_UNAVAILABLE = "unavailable"

#: The authority this overlay decides under. On the wire because a served field
#: that changed what it means needs to name the decision that changed it.
OVERLAY_AUTHORITY = "D62 = A (Alex, 2026-09-04)"


def sigma_overlay(
    cells: list[dict], ledger: dict | None, reason: str | None = None
) -> dict:
    """What the measured sigma did to this board, with the receipt.

    The load-bearing field is ``cells_moved``: the named list of every cell
    whose verdict the measurement CHANGED, in both directions, each with both
    sigmas. Everything else here can be recomputed from the cell rows; this is
    the one thing that answers "what did flipping D62 actually do" without the
    reader running the counterfactual themselves.

    ``cells_moved`` is over MATERIAL cells only. An exempt cell's verdict is
    ``EXEMPT_BELOW_MIN_N`` on both bases by construction — the floor is checked
    before the sigma — so it can never move, and including 277 rows that cannot
    move would bury the ones that did.
    """
    material = [c for c in cells if is_material(c)]
    by_status: dict[str, int] = defaultdict(int)
    for c in material:
        by_status[c.get("sigma_ledger_status") or sigma_ledger.STATUS_ABSENT] += 1
    moved = [
        {
            "cell": c["cell"],
            "from": c["verdict_row_basis"],
            "to": c["verdict"],
            "sigma_row": c["sigma_row"],
            "sigma_measured": c.get("sigma_measured"),
            "se_measured_pp": c.get("se_measured_pp"),
            "ledger_status": c.get("sigma_ledger_status"),
            # A moved cell is the ONE row a reader will interrogate, so the
            # provenance travels on it rather than only in a summary count.
            "measured_at_population": c.get("measured_at_population"),
            "measured_generated_at": c.get("measured_generated_at"),
            "excess_outcomes": c["excess_outcomes"],
        }
        for c in material
        if c["verdict"] != c["verdict_row_basis"]
    ]
    return {
        "status": OVERLAY_APPLIED if ledger is not None else OVERLAY_UNAVAILABLE,
        # `None` when applied, rather than an upbeat string: a `reason` that is
        # always populated is a field consumers stop reading.
        "reason": reason,
        "authority": OVERLAY_AUTHORITY,
        # Said explicitly rather than implied by `status`. Before 2026-09-04
        # this overlay existed and decided nothing, and a consumer that cached
        # that fact needs the wire to contradict it.
        "decides": ledger is not None,
        "ledger_cells": len((ledger or {}).get("entries") or {}),
        "material_cells": len(material),
        "material_by_ledger_status": dict(sorted(by_status.items())),
        "carried_from_populations": sorted(
            {
                c["measured_at_population"]
                for c in material
                if c.get("measured_carried") and c.get("measured_at_population")
            }
        ),
        # A CARRIED cell is a standing request to re-measure. Counted so the
        # measurement lane reads its backlog off the wire instead of a note.
        "remeasure_backlog": sorted(
            c["cell"] for c in material if c.get("measured_carried")
        ),
        "cells_moved": sorted(moved, key=lambda m: -m["excess_outcomes"]),
    }


# ---------------------------------------------------------------------------
# The CATEGORY cut — the measurement bus's script-free read, made first-class
# ---------------------------------------------------------------------------


def category_scorecard(payload: dict) -> dict:
    """Categories at the flat reader bar, off the payload's OWN ``by_category``.

    This is the read the measurement bus has been doing by hand
    (``14/36 cats ece<=3.0``). It is published rather than replaced because it
    answers a different question from the cell cut and both are worth asking:

    * the CELL cut asks *is any published (source, category) pair wrong* — it is
      the repair queue, and it is scored at the ratified per-class bars;
    * the CATEGORY cut asks *is any published SUBJECT wrong* — a reader who
      cares about hockey does not care which venue priced it, and pooling the
      venues is what they actually see.

    A category can therefore be at bar while one of its cells is not (the
    venues' errors cancel), which is not a contradiction and is exactly why the
    two figures differ. Publishing them side by side with their own bars is the
    whole point of D46.

    ``gated`` rows are excluded: the payload sets that flag when it is
    withholding a category's number, and scoring a number the page declines to
    show would count a cell nobody can see.
    """
    rows = payload.get("by_category") or []
    floor = MIN_CELL_N
    eligible = [
        c for c in rows
        if (c.get("n") or c.get("outcomes") or 0) >= floor and not c.get("gated")
    ]
    at_bar = [c for c in eligible if c.get("ece") is not None and c["ece"] <= BAR_PP]
    over = [c for c in eligible if c.get("ece") is not None and c["ece"] > BAR_PP]
    return {
        "categories_at_bar": len(at_bar),
        "categories_total": len(eligible),
        "categories_bar_pp": BAR_PP,
        "categories_min_n": floor,
        "categories_gated": sum(1 for c in rows if c.get("gated")),
        "categories_over_bar": sorted(
            ({"category": c["category"], "ece": c["ece"], "n": c.get("n") or c.get("outcomes")}
             for c in over),
            key=lambda c: -(c["ece"] or 0),
        ),
        # gotcha #53: the payload's own floor moving out from under a hardcoded
        # one is silent. If these ever disagree the category cut and the cell cut
        # are scoring different populations, and this says so on the wire.
        "floor_matches_payload": (
            payload.get("min_category_outcomes") is None
            or int(payload["min_category_outcomes"]) == floor
        ),
        "payload_min_category_outcomes": payload.get("min_category_outcomes"),
    }


# ---------------------------------------------------------------------------
# The published block
# ---------------------------------------------------------------------------

#: The top-level key ``/api/calibration`` carries the score under.
SCORECARD_FIELD = "scorecard"

#: ``scorecard.status`` values. A block that could not be computed says so with
#: a reason — it is never simply absent, because an absent field and a zero read
#: identically to a consumer that uses ``.get(..., 0)`` (gotcha #53).
STATUS_MEASURED = "measured"
STATUS_UNAVAILABLE = "unavailable"


def unavailable(reason: str, *, computed_at: str | None = None) -> dict:
    """The explicit not-scored block. Loud, dated, and never mistakable for 0."""
    return {
        "status": STATUS_UNAVAILABLE,
        "reason": reason,
        "computed_at": computed_at or datetime.now(timezone.utc).isoformat(),
        "cells_at_bar": None,
        "cells_at_bar_row_basis": None,
        "cells_total": None,
        "categories_at_bar": None,
        "categories_total": None,
        # `None`, not `[]`: an unscored board does not know what is held back,
        # and an empty list here would claim it does (gotcha #53).
        "cells_held_back": None,
        "held_back_cells": None,
    }


def scorecard(
    payload: dict,
    *,
    computed_at: str | None = None,
    ledger: dict | None = None,
    ledger_reason: str | None = None,
    load_ledger: bool = True,
) -> dict:
    """The block published on ``/api/calibration``.

    Derived from the payload PASSED IN — so a dated last-good copy is scored as
    the copy it is, and the served figure can never describe a curve other than
    the one in the same response. That is why this is computed at the serving
    exit rather than baked in by the producer: a producer-baked score survives
    into fallback tiers describing a payload that is no longer there.

    ``computed_at`` is when the SCORE was taken; ``generated_at`` (carried
    beside it) is when the CURVE was built. They are different facts and a
    single timestamp for both is how a stale curve reads as a fresh reading.

    THE LEDGER. By default this loads the committed measured-sigma ledger
    itself (``load_ledger``), because the caller that matters is a route and a
    route should not have to remember. A caller supplies ``ledger`` explicitly
    to score against a fixture, and passes ``load_ledger=False`` to score on the
    row estimate deliberately. The distinction is kept because "no ledger
    because you asked for none" and "no ledger because the file is missing" are
    different facts and only one of them is a problem — they carry different
    ``sigma_overlay.reason`` values for exactly that reason.
    """
    if ledger is None and load_ledger:
        ledger, ledger_reason = sigma_ledger.load_default()
    elif ledger is None and ledger_reason is None:
        ledger_reason = "ledger_not_requested"
    cells = score_cells(payload, ledger)
    counts = cell_counts(cells)
    cats = category_scorecard(payload)
    overlay = sigma_overlay(cells, ledger, ledger_reason)
    headline = payload.get("mce_closing_line")
    queued = [c for c in cells if c["verdict"] == VERDICT_QUEUED]
    block = {
        "status": STATUS_MEASURED,
        "computed_at": computed_at or datetime.now(timezone.utc).isoformat(),
        # The curve this score describes. Repeated inside the block on purpose:
        # a needle copied out of `scorecard` alone must still carry its date.
        "generated_at": payload.get("generated_at"),
        "population_version": payload.get("population_version"),
        # D134: WHICH POPULATION is already here; this is WHICH METHOD. Beside
        # `population_version` rather than inside `bar` on purpose — the two are
        # the pair that identifies a published number, and a consumer that
        # copies the needle out should not have to reach into a nested block to
        # find half of its provenance.
        "scoring_policy": {
            "version": SCORING_POLICY_VERSION,
            "fingerprint": scoring_policy_fingerprint(),
            "in_force_since": SCORING_POLICY_IN_FORCE_SINCE,
        },
        # THE NEEDLE. `cells_total` is the MATERIAL count — the denominator of
        # the number Alex reads — and `cells_scored` is every folded cell. See
        # the module docstring for why the two names differ from the script's.
        "cells_at_bar": counts["cells_at_bar"],
        # The counterfactual needle and its delta, on the wire beside the
        # needle itself. CAL-P1002: the measured sigma now decides, and a
        # reader must be able to see what it decided differently without
        # re-running anything. `sigma_overlay.cells_moved` names the cells.
        "cells_at_bar_row_basis": counts["cells_at_bar_row_basis"],
        "cells_at_bar_delta_vs_row_basis": (
            counts["cells_at_bar"] - counts["cells_at_bar_row_basis"]
        ),
        "cells_total": counts["cells_material"],
        "cells_scored": counts["cells_total"],
        "cells_exempt": counts["cells_exempt"],
        # #5401 / klm = A (Alex, 2026-09-12). The cells whose prices we should
        # never have stored, named on the wire so the page can say so in one
        # line and a probe can prove they are accounted for rather than quietly
        # gone. Empty list once the repair lands — never absent, so "nothing is
        # held back" and "this payload predates the field" stay distinguishable
        # (gotcha #53).
        "cells_held_back": counts["cells_held_back"],
        "held_back_outcomes": counts["held_back_outcomes"],
        "held_back_reason": HELD_BACK_REASON,
        "held_back_issue": HELD_BACK_ISSUE,
        "held_back_cells": [
            {
                "cell": c["cell"],
                "source": c["source"],
                "category": c["category"],
                "ece": c["ece"],
                "n": c["n"],
                "class": c["class"],
                "bar_pp": c["bar_pp"],
            }
            for c in sorted(
                (c for c in cells if c["verdict"] == VERDICT_HELD_BACK),
                key=lambda c: -c["n"],
            )
        ],
        "cells_queued": counts["cells_queued"],
        "cells_unestablished": counts["cells_unestablished"],
        "cells_material_outcomes": counts["cells_material_outcomes"],
        "queued_excess_outcomes": counts["queued_excess_outcomes"],
        "bar": {
            "class_bars_pp": dict(CLASS_BARS_PP),
            "reader_bar_pp": BAR_PP,
            "min_cell_n": MIN_CELL_N,
            "sigma_gate": SIGMA_GATE,
            # WHICH sigma the gate is applied to. The gate's VALUE did not
            # change on 2026-09-04; its INPUT did, and a consumer reading
            # `sigma_gate: 2.0` alone would not know that. Not simply
            # "measured": the overlay covers 4 of 14 queued cells today and the
            # row estimate still decides the other 10, so the honest wire value
            # says per-cell and each cell carries its own `sigma_basis`.
            "sigma_gate_basis": (
                SIGMA_BASIS_PER_CELL if ledger is not None else SIGMA_BASIS_ROW
            ),
            "headline_target_pp": HEADLINE_TARGET_PP,
        },
        "sigma_overlay": overlay,
        "per_class": per_class(cells),
        # The repair queue itself, ranked. Bounded to what a reader can use: the
        # full 325-cell table is the script's job and would double the payload.
        "queued_cells": [
            {
                "cell": c["cell"],
                "ece": c["ece"],
                "n": c["n"],
                "gap": c["gap"],
                "class": c["class"],
                "bar_pp": c["bar_pp"],
                "excess_pp": c["excess_pp"],
                # BOTH sigmas and the label saying which one queued this cell.
                # `sigma` alone was unambiguous while only one existed; since
                # D62 a bare number is the ambiguity CAL-P127 lesson 10 warns
                # about, so the estimate never leaves the row it was replaced on.
                "sigma": c["sigma"],
                "sigma_basis": c["sigma_basis"],
                "sigma_row": c["sigma_row"],
                "sigma_measured": c.get("sigma_measured"),
                "se_measured_pp": c.get("se_measured_pp"),
                "ledger_status": c.get("sigma_ledger_status"),
                # Present only on a carried row, and both are here because the
                # residual a size test cannot cover is a question about AGE.
                "measured_at_population": c.get("measured_at_population"),
                "measured_generated_at": c.get("measured_generated_at"),
                "excess_outcomes": c["excess_outcomes"],
            }
            for c in queued
        ],
        "headline_mce_closing_line": headline,
        "headline_target_pp": HEADLINE_TARGET_PP,
        "headline_pass": (headline is not None and headline <= HEADLINE_TARGET_PP),
        # The MEASURED half of FIXED. The other half is Alex's eyeball on the
        # page, which no field can assert — hence `done`, not `fixed`.
        "done": (
            counts["cells_queued"] == 0
            and headline is not None
            and headline <= HEADLINE_TARGET_PP
        ),
    }
    block.update(cats)
    return block


def needle(block: dict) -> str:
    """The lane's ONE line, from the served block rather than from a script run.

    The NEEDLE-SPEC shape — ``<value> <unit> @ <ts>`` — is unchanged and the
    parenthetical follows the timestamp, so nothing that reads the spec's fields
    has to change. It is there because D62 changed the series' DEFINITION on
    2026-09-04 the way the 2026-08-28 bar ratification did: same curve, same
    unit, different input to the gate. A trend line across a definition change
    that its own points cannot describe is a chart that lies about its units, so
    every point says which basis produced it and what the other one read.
    """
    if block.get("status") != STATUS_MEASURED:
        return f"NEEDLE: calibration UNMEASURED ({block.get('reason')})"
    basis = (block.get("bar") or {}).get("sigma_gate_basis", SIGMA_BASIS_ROW)
    return (
        f"NEEDLE: calibration {block['cells_at_bar']}/{block['cells_total']} "
        f"cells-at-bar, {block['categories_at_bar']}/{block['categories_total']} "
        f"categories-at-bar @ {block.get('generated_at')} "
        f"(sigma {basis}; row-basis {block.get('cells_at_bar_row_basis')}/"
        f"{block['cells_total']})"
    )
