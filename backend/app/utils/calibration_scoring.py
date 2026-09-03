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
Here: the thresholds, the fold, the per-cell verdict, the counts, and the
category cut. These are the parts that decide a published number.

Not here: the measured cluster-bootstrap sigma overlay, the markdown renderer
and the history ledger. Those are reporting machinery around the score, they
have no effect on ``cells_at_bar`` (see ``_attach_measured_sigma``'s docstring
in the script — the overlay reports and decides nothing), and dragging a
``artifacts/`` writer into ``app/`` would put a filesystem dependency on the
request path for no gain.

ONE DEFINITION, TWO CALLERS. ``backend/scripts/calibration_scorecard.py``
imports every threshold and the fold from this module rather than restating
them. That direction is the load-bearing one: the app cannot import the script
(``scripts/`` is not on the dyno's path and never will be), so if the script
kept the definitions the served field would be a second implementation of the
bar — which is the exact drift this change exists to end.

THIS MODULE IMPORTS NOTHING FROM THE APP. Same rule as ``sport_keys.py`` and
for the same reason: it is consumed by a route, by a task and by a standalone
script, and a circular import discovered on the dyno is discovered at boot.

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

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

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


def classify(source: str, category: str) -> str:
    """The cohort class of a published cell. Structural, never numeric."""
    if (source or "").startswith("odds_api"):
        return CLASS_A
    return CLASS_B if category in GAME_CATEGORIES else CLASS_C


def bar_for(source: str, category: str) -> float:
    """The ratified bar this cell is scored against, in pp."""
    return CLASS_BARS_PP[classify(source, category)]


def cell_se_pp(n: int) -> float:
    """Standard error of a cell's ECE in pp. ``50/sqrt(n)``, the board's convention."""
    return 50.0 / math.sqrt(n) if n > 0 else float("inf")


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


def verdict_for(n: int, excess_pp: float, sigma: float | None) -> str:
    """The one place a cell's verdict is decided."""
    if n < MIN_CELL_N:
        return VERDICT_EXEMPT
    if excess_pp <= 0:
        return VERDICT_PASS
    if sigma is not None and sigma >= SIGMA_GATE:
        return VERDICT_QUEUED
    return VERDICT_UNDER_SIGMA


def score_cells(payload: dict) -> list[dict]:
    """Every ``(source, category)`` cell of the payload, scored and ranked.

    Ranked by excess-outcomes — how much wrongness the cell puts in front of
    readers — because a 22 pp cell over 118 rows and a 0.5 pp cell over 100,000
    are not the same repair job.
    """
    cells = []
    for c in fold(payload):
        n, ece = c["n"], c["ece"]
        if ece is None:
            continue
        klass = classify(c["source"], c["category"])
        bar = CLASS_BARS_PP[klass]
        excess = round(ece - bar, 2)
        se = cell_se_pp(n)
        sigma = round(excess / se, 2) if se else None
        cells.append(
            {
                "cell": f"{c['source']}/{c['category']}",
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
                "sigma": sigma,
                "excess_outcomes": round(max(0.0, excess) * n),
                "verdict": verdict_for(n, excess, sigma),
            }
        )
    cells.sort(key=lambda c: (-c["excess_outcomes"], -c["n"]))
    return cells


def cell_counts(cells: list[dict]) -> dict:
    """The needle's arithmetic, over already-scored cells."""
    material = [c for c in cells if c["verdict"] != VERDICT_EXEMPT]
    queued = [c for c in cells if c["verdict"] == VERDICT_QUEUED]
    unestablished = [c for c in cells if c["verdict"] == VERDICT_UNDER_SIGMA]
    return {
        "cells_total": len(cells),
        "cells_material": len(material),
        "cells_material_outcomes": sum(c["n"] for c in material),
        "cells_pass": sum(1 for c in material if c["verdict"] == VERDICT_PASS),
        "cells_queued": len(queued),
        "cells_unestablished": len(unestablished),
        "cells_exempt": len(cells) - len(material),
        "queued_excess_outcomes": sum(c["excess_outcomes"] for c in queued),
        # The NEEDLE numerator. A material cell is "at bar" iff it is not queued
        # — the same test ``done`` applies, so the lane's one glanceable number
        # and the page's verdict can never disagree.
        "cells_at_bar": len(material) - len(queued),
    }


def per_class(cells: list[dict]) -> dict:
    """Cells at bar split by the cohort class whose bar scored them."""
    material = [c for c in cells if c["verdict"] != VERDICT_EXEMPT]
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
        "cells_total": None,
        "categories_at_bar": None,
        "categories_total": None,
    }


def scorecard(payload: dict, *, computed_at: str | None = None) -> dict:
    """The block published on ``/api/calibration``.

    Derived from the payload PASSED IN — so a dated last-good copy is scored as
    the copy it is, and the served figure can never describe a curve other than
    the one in the same response. That is why this is computed at the serving
    exit rather than baked in by the producer: a producer-baked score survives
    into fallback tiers describing a payload that is no longer there.

    ``computed_at`` is when the SCORE was taken; ``generated_at`` (carried
    beside it) is when the CURVE was built. They are different facts and a
    single timestamp for both is how a stale curve reads as a fresh reading.
    """
    cells = score_cells(payload)
    counts = cell_counts(cells)
    cats = category_scorecard(payload)
    headline = payload.get("mce_closing_line")
    queued = [c for c in cells if c["verdict"] == VERDICT_QUEUED]
    block = {
        "status": STATUS_MEASURED,
        "computed_at": computed_at or datetime.now(timezone.utc).isoformat(),
        # The curve this score describes. Repeated inside the block on purpose:
        # a needle copied out of `scorecard` alone must still carry its date.
        "generated_at": payload.get("generated_at"),
        "population_version": payload.get("population_version"),
        # THE NEEDLE. `cells_total` is the MATERIAL count — the denominator of
        # the number Alex reads — and `cells_scored` is every folded cell. See
        # the module docstring for why the two names differ from the script's.
        "cells_at_bar": counts["cells_at_bar"],
        "cells_total": counts["cells_material"],
        "cells_scored": counts["cells_total"],
        "cells_exempt": counts["cells_exempt"],
        "cells_queued": counts["cells_queued"],
        "cells_unestablished": counts["cells_unestablished"],
        "cells_material_outcomes": counts["cells_material_outcomes"],
        "queued_excess_outcomes": counts["queued_excess_outcomes"],
        "bar": {
            "class_bars_pp": dict(CLASS_BARS_PP),
            "reader_bar_pp": BAR_PP,
            "min_cell_n": MIN_CELL_N,
            "sigma_gate": SIGMA_GATE,
            "headline_target_pp": HEADLINE_TARGET_PP,
        },
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
                "sigma": c["sigma"],
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
    """The lane's ONE line, from the served block rather than from a script run."""
    if block.get("status") != STATUS_MEASURED:
        return f"NEEDLE: calibration UNMEASURED ({block.get('reason')})"
    return (
        f"NEEDLE: calibration {block['cells_at_bar']}/{block['cells_total']} "
        f"cells-at-bar, {block['categories_at_bar']}/{block['categories_total']} "
        f"categories-at-bar @ {block.get('generated_at')}"
    )
