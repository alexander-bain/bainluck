#!/usr/bin/env python3
"""CAL-P108 — the PUBLISHED calibration curve, scored against the finish line.

Alex, 2026-08-27: *"We haven't made any tangible progress on calibration in
months, if anything it's regressed... I'd strongly prefer to get to a point
where calibration is just FIXED."*

This script is the one measurement that sentence gets. It scores **the numbers
users actually see** — nothing else.

WHY IT READS THE SERVED PAYLOAD AND NOT THE DATABASE
-----------------------------------------------------
Every previous calibration instrument in this repo measures a *parallel rail*:

* ``fold_cohort_cell_eligible.py`` (the 21-cell board in
  ``artifacts/subcohort2/SUBCOHORT_DIAGNOSIS.md``) folds
  ``source='polymarket'`` only, over ``market_type IN (quantity,
  container_member)``, applying exactly ONE of the curve's thirteen live
  exclusion filters (truth-eligibility). It is a real measurement of a real
  population — but not of the published one.
* ``calibration_published_twin.py`` DOES fold the published predicate, and is
  the right idea. Its last production run (2026-08-25) died on a statement
  timeout after 241 s against a 240 s budget, and it has never returned a
  measured verdict since.

Both are DB-direct, and a DB-direct rail can drift from the served payload
without anyone noticing. This script cannot: it reads the payload the site
serves and folds *that*. The population predicate is not re-derived, not
re-implemented, and not trusted — it is simply not needed, because the rows
have already been through it.

THE INSTRUMENT PROVES ITSELF BEFORE IT REPORTS
------------------------------------------------
``/api/calibration`` ships a ``buckets`` array AND its own pre-aggregated
``by_category`` / ``by_source`` cells. :func:`self_check` re-derives the second
from the first and refuses to report anything if they disagree.

That check is the whole warrant for this file. It is not decoration:

* It pins the fold. The published fold pools ``(source, category,
  price_moved, bucket_idx)`` rows into **10 bins per cell** before taking the
  error. Folding at bucket-row granularity instead — the obvious first
  implementation — inflates every cell, because errors that cancel inside a bin
  no longer can. Measured 2026-08-27 on the live payload: 34 of 34 cells wrong,
  every one high (soccer 2.80 -> 3.91, hockey 0.95 -> 2.32). A silent +40%
  scorecard is worse than no scorecard.
* It makes a schema change LOUD. If the payload's shape moves, this reds
  instead of quietly scoring a different quantity under the same name.

A cut this script reports that the payload does not pre-aggregate — the
``(source, category)`` cell — is therefore computed by a fold that has been
proved against two cuts the payload DOES pre-aggregate, on the same rows, in
the same run.

WHAT "DONE" MEANS — thresholds are declared here, in code, once
-----------------------------------------------------------------
See :data:`CLASS_BARS_PP`, :data:`MIN_CELL_N`, :data:`SIGMA_GATE`. Each carries
its derivation. Alex ratified the per-cohort bar by MC on 2026-08-28 (A 2.5 pp /
B 3.0 pp / C 3.0 pp); changing one is a one-line change here and the scorecard
re-renders.

Ratification added a clause that no script can evaluate and this one therefore
does not pretend to: at 49/49, **Alex eyeballs the calibration page and confirms
it is up to standard**, and his sign-off is the final gate. ``done`` below is the
MEASURED half of that conjunction, which is why it is named ``done`` and not
``fixed``.

Usage::

    python3 backend/scripts/calibration_scorecard.py --live
    python3 backend/scripts/calibration_scorecard.py --payload artifacts/x.json
    python3 backend/scripts/calibration_scorecard.py --live --markdown

``--record`` appends the run to ``artifacts/calibration-scorecard/history.jsonl``,
keyed on ``(the payload's own generated_at, the class bars it was scored at)``.
Re-running against a STALE payload (the producer has been stalling — see
``producer.stalled``) therefore cannot mint a second datapoint for the same
curve at the same bars, which would otherwise draw a flat trend line out of one
measurement repeated. A re-score of the same curve at a DIFFERENT finish line
is a different reading and does bank — see :func:`_point_key`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# `backend/`, so `app.utils.calibration_scoring` imports whether this script is
# run from the repo root or from `backend/`. CAL-P998.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The MEASURED sigma ledger. Imported, never re-implemented, and deliberately
# one-way: the ledger imports nothing from this file, so
# `calibration_cluster_sigma` can keep importing BOTH without a cycle.
#
# CAL-P1002: the ledger's CONSUMING half (statuses, bands, `lookup`, `load`)
# moved to `app/utils/calibration_sigma.py` when D62 made it decide a served
# number; this script's import still resolves every one of those names, because
# the builder re-exports them for exactly this reason.
import calibration_sigma_ledger as sigma_ledger  # noqa: E402

# --------------------------------------------------------------------------
# THE FINISH LINE AND THE FOLD NOW LIVE IN THE APP — CAL-P998, D46 = A.
#
# Every threshold, the fold, and the per-cell verdict moved to
# `app/utils/calibration_scoring.py` so `/api/calibration` can publish
# `cells_at_bar` itself instead of the number existing only while this script
# runs. They are IMPORTED here, never restated: the app cannot import
# `scripts/` (it is not on the dyno's path), so if this file kept the
# definitions the served field would be a second implementation of the bar —
# and a bar that exists twice is a bar that moves once.
#
# CAL-P1002 / D62 = A: THE OVERLAY WENT WITH THEM. The measured
# cluster-bootstrap sigma used to live in this file and decide nothing. It now
# decides which cells are queued, so by the same argument it had to move to
# where `cells_at_bar` is computed — otherwise the served needle and this
# script's needle are two numbers from day one, which is what D46 ended.
#
# What stays in this file is what the app has no business carrying: the markdown
# renderer, the history ledger, and the self-check. Each constant's full
# derivation now lives with it in the app module.
# --------------------------------------------------------------------------
from app.utils.calibration_scoring import (  # noqa: E402
    BAR_PP,
    CELL_KEYS,
    CLASS_A,
    CLASS_B,
    CLASS_BARS_PP,
    CLASS_C,
    GAME_CATEGORIES,
    HEADLINE_TARGET_PP,
    MIN_CELL_N,
    SIGMA_BASIS_MEASURED,
    SIGMA_BASIS_PER_CELL,
    SIGMA_BASIS_ROW,
    SIGMA_GATE,
    VERDICT_EXEMPT,
    VERDICT_PASS,
    VERDICT_QUEUED,
    VERDICT_UNDER_SIGMA,
    attach_measured_sigma,
    bar_for,
    category_scorecard,
    cell_counts,
    cell_se_pp,
    classify,
    deciding_sigma,
    fold,
    per_class,
    score_cells,
    sigma_overlay,
)

# `attach_measured_sigma` and `deciding_sigma` are re-exported without being
# called here: this file's own consumers and its guards resolve them through
# `calibration_scorecard`, and the point of CAL-P1002 is that the name they get
# is the APP's function and not a local one. Listing them says that on purpose,
# rather than a `noqa` that reads as an oversight someone tidied around.
__all__ = [
    "BAR_PP", "CELL_KEYS", "CLASS_A", "CLASS_B", "CLASS_BARS_PP", "CLASS_C",
    "CLASS_RATIONALE",
    "GAME_CATEGORIES", "HEADLINE_TARGET_PP", "MIN_CELL_N",
    "SIGMA_BASIS_MEASURED", "SIGMA_BASIS_PER_CELL", "SIGMA_BASIS_ROW",
    "SIGMA_GATE",
    "VERDICT_EXEMPT", "VERDICT_PASS", "VERDICT_QUEUED", "VERDICT_UNDER_SIGMA",
    "attach_measured_sigma", "bar_for", "cell_se_pp", "classify",
    "deciding_sigma", "fold", "needle", "record", "score", "self_check",
    "sigma_overlay", "load_history", "render_markdown",
]

CLASS_RATIONALE: dict[str, str] = {
    CLASS_A: (
        "Devigged consensus of many bookmakers. The published price is an "
        "average of independent estimates, so its idiosyncratic quoting error "
        "is structurally smaller than a single order book's — the one external "
        "reason to hold a class tighter than reader-actionability requires. "
        "These cells also carry the game cards, the most-read surface."
    ),
    CLASS_B: (
        "Single-venue exchange price on a scheduled contest. Real order book, "
        "near-term settlement, no averaging across venues. Reader "
        "actionability sets the bar and nothing about the class earns a "
        "departure from it."
    ),
    CLASS_C: (
        "Single-venue exchange price on a standalone or long-horizon question. "
        "Thin books and distant settlement raise the VARIANCE of a cell's "
        "estimate, which the sigma gate already prices; they do not license a "
        "larger BIAS. The class's own cells prove 3.0 pp reachable — "
        "polymarket/weather 1.64 pp, kalshi/politics 2.12 pp on the 2026-08-28 20:37Z curve."
    ),
}


DEFAULT_HISTORY = Path("artifacts/calibration-scorecard/history.jsonl")

# --------------------------------------------------------------------------
# Self-check — the instrument's warrant
# --------------------------------------------------------------------------


def self_check(payload: dict) -> dict:
    """Re-derive the payload's own pre-aggregated cells from its buckets.

    Returns a report; ``ok`` false means this scorecard MUST NOT be published.
    ``n`` is compared as well as ``ece``: an ECE that matches on a different
    row count is a coincidence, not agreement.
    """
    checks = []
    for dim, field in (("category", "by_category"), ("source", "by_source")):
        published = payload.get(field) or []
        derived = {c[dim]: c for c in fold(payload, (dim,))}
        mismatches = []
        for pub in published:
            got = derived.get(pub[dim])
            if got is None:
                mismatches.append({"cell": pub[dim], "reason": "absent_from_buckets"})
                continue
            # `is None`, never a falsy test: a cell whose ECE is exactly 0.00 is
            # a PERFECTLY calibrated cell, and `got["ece"] or -1` would score it
            # as a mismatch — the self-check reddest on the one result it should
            # be happiest about. Found by `test_agrees_with_a_consistent_payload`.
            if got["ece"] is None:
                mismatches.append({"cell": pub[dim], "reason": "unfoldable"})
                continue
            # 0.015 absorbs the payload's own 2-dp rounding and nothing else.
            if abs(got["ece"] - pub["ece"]) > 0.015 or got["n"] != pub["n"]:
                mismatches.append(
                    {
                        "cell": pub[dim],
                        "published": {"ece": pub["ece"], "n": pub["n"]},
                        "derived": {"ece": got["ece"], "n": got["n"]},
                    }
                )
        checks.append(
            {
                "dimension": field,
                "cells": len(published),
                "matched": len(published) - len(mismatches),
                "mismatches": mismatches,
            }
        )
    # A run that compared ZERO cells has not agreed with anything — it has
    # declined to check. Reporting that as `ok` is gotcha #53 inside the very
    # guard written to prevent it, and it is exactly what an empty or
    # shape-changed payload would produce.
    compared = sum(c["cells"] for c in checks)
    return {
        "ok": bool(checks) and compared > 0 and all(not c["mismatches"] for c in checks),
        "cells_compared": compared,
        "checks": checks,
    }


# --------------------------------------------------------------------------
# Score
# --------------------------------------------------------------------------

def score(payload: dict, ledger: dict | None = None) -> dict:
    """Score the published payload.

    ``ledger`` is the MEASURED sigma ledger. Since D62 = A it DECIDES: a cell
    with a usable measured standard error is queued or not on that number
    rather than on ``50/sqrt(n)``. Passing ``None`` scores on the estimate
    alone, which is the pre-D62 board and is still what runs when the ledger
    cannot be read.

    CAL-P1002: the fold, the bars, the verdict AND the overlay are all the
    APP's (:mod:`app.utils.calibration_scoring`) — this file holds no second
    copy of any of them, so a figure printed here and a figure served by
    ``/api/calibration`` are the same number by construction rather than by
    agreement.
    """
    cells = score_cells(payload, ledger)
    counts = cell_counts(cells)
    material = [c for c in cells if c["verdict"] != VERDICT_EXEMPT]
    queued = [c for c in cells if c["verdict"] == VERDICT_QUEUED]
    headline = payload.get("mce_closing_line")

    # The overlay's audit trail, in this file's own vocabulary. `measured` and
    # `carried` stay SPLIT — both are verdict-capable, only one was measured on
    # the population being scored, and a count that cannot be split back into
    # those two halves is a count nobody can audit. A POPULATION_DIVERGENCE cell
    # is in neither: it shows its numbers and decides nothing.
    def _decided(rows, carried):
        return [
            c
            for c in rows
            if c.get("sigma_basis") == SIGMA_BASIS_MEASURED
            and bool(c.get("measured_carried")) is carried
        ]

    # Over MATERIAL cells, not just queued ones: since the overlay decides, a
    # cell it took OFF the queue is no longer in `queued` and counting the
    # overlay's coverage there would make it shrink as it succeeds.
    measured = _decided(material, False)
    carried = _decided(material, True)
    low_cov = [
        c
        for c in material
        if c.get("sigma_ledger_status") == sigma_ledger.STATUS_POPULATION_DIVERGENCE
    ]
    # The cells the measurement actually took off the queue — over-bar on the
    # estimate, not established on the measurement.
    refuted = [
        c
        for c in measured
        if c["verdict_row_basis"] == VERDICT_QUEUED and c["verdict"] != VERDICT_QUEUED
    ]
    refuted_carried = [
        c
        for c in carried
        if c["verdict_row_basis"] == VERDICT_QUEUED and c["verdict"] != VERDICT_QUEUED
    ]
    # And the other direction, which must be counted with the same care: a cell
    # the estimate cleared and the measurement queues. There are none on the
    # 2026-09-04 board, and a projection that can only ever shorten the queue is
    # one nobody should trust — so it is computed, not assumed.
    added = [
        c
        for c in material
        if c["verdict"] == VERDICT_QUEUED and c["verdict_row_basis"] != VERDICT_QUEUED
    ]

    return {
        "generated_at": payload.get("generated_at"),
        "population_version": payload.get("population_version"),
        "total_outcomes": payload.get("total_outcomes"),
        "headline_mce_closing_line": headline,
        "headline_ci": [payload.get("mce_ci_lower"), payload.get("mce_ci_upper")],
        "headline_target_pp": HEADLINE_TARGET_PP,
        "headline_pass": (headline is not None and headline <= HEADLINE_TARGET_PP),
        # Producer state travels WITH the number. A scorecard that reports a
        # figure without saying the producer that made it has missed five beats
        # is reporting a stale reading as a current one (gotcha #53).
        "availability": payload.get("availability"),
        "producer_stalled": (payload.get("producer") or {}).get("stalled"),
        "producer_beats_missed": (payload.get("producer") or {}).get("beats_missed"),
        # `bar_pp` is deliberately ABSENT and not renamed in place: until the
        # 2026-08-28 ratification this key held THE bar, and a consumer that
        # keeps reading it would now be reading one of three. A KeyError is a
        # story; a silently-wrong threshold is gotcha #53.
        "thresholds": {
            "class_bars_pp": dict(CLASS_BARS_PP),
            "reader_bar_pp": BAR_PP,
            "min_cell_n": MIN_CELL_N,
            "sigma_gate": SIGMA_GATE,
            # The gate's VALUE is unchanged since the 2026-08-28 ratification;
            # D62 changed its INPUT. Banked with every history point for the
            # same reason `class_bars_pp` is: a series that changes definition
            # and cannot say so is a chart that lies about its units.
            "sigma_gate_basis": (
                SIGMA_BASIS_PER_CELL if ledger is not None else SIGMA_BASIS_ROW
            ),
            "headline_target_pp": HEADLINE_TARGET_PP,
        },
        # The NEEDLE and its arithmetic — computed by the same function
        # `/api/calibration` publishes from, so the script's figure and the
        # served field are the same number by construction rather than by
        # agreement. NOTE the served block renames two of these: on the wire
        # `cells_total` is this `cells_material` (the needle's denominator) and
        # this `cells_total` is published as `cells_scored`. The mapping is
        # pinned by `test_calibration_scoring_998.py`.
        "counts": counts,
        # DECIDING since D62 = A (2026-09-04). Until then every field in this
        # block was a projection named `_if_applied`; the projection became the
        # reading, so the fields that used to hold the counterfactual now hold
        # what happened and the counterfactual is the ROW basis. The direction
        # of the "if" flipped, not the arithmetic.
        "measured_sigma": {
            "decides": ledger is not None,
            "material_cells": len(material),
            "material_cells_measured": len(measured),
            "material_cells_carried": len(carried),
            "material_cells_low_coverage": len(low_cov),
            "material_cells_unmeasured": (
                len(material) - len(measured) - len(carried) - len(low_cov)
            ),
            "low_coverage_cells": [c["cell"] for c in low_cov],
            # CARRIED (CAL-P998) stays its own bucket even though it now
            # decides alongside FRESH: the whole warrant for carrying an entry
            # is that a reader can still tell the two apart, and it is the
            # re-measure backlog the measurement lane works off.
            "carried_cells": [c["cell"] for c in carried],
            "carried_from_populations": sorted(
                {
                    c["measured_at_population"]
                    for c in carried
                    if c.get("measured_at_population")
                }
            ),
            # What the measurement DID: cells taken off the queue, and cells
            # put on it. Both directions, because a correction that can only
            # ever shorten the board is one nobody should trust.
            "cells_refuted": len(refuted) + len(refuted_carried),
            "refuted_cells": [c["cell"] for c in refuted],
            "refuted_cells_carried": [c["cell"] for c in refuted_carried],
            "refuted_excess_outcomes": sum(
                c["excess_outcomes"] for c in refuted + refuted_carried
            ),
            "cells_added": len(added),
            "added_cells": [c["cell"] for c in added],
            # The needle on the estimate alone — what this board read before
            # D62, published beside what it reads now.
            "cells_at_bar_row_basis": counts["cells_at_bar_row_basis"],
            "cells_at_bar_delta_vs_row_basis": (
                counts["cells_at_bar"] - counts["cells_at_bar_row_basis"]
            ),
        },
        # The served block's own receipt, computed by the same function
        # `/api/calibration` publishes — so the script cannot describe the flip
        # differently from the wire.
        "sigma_overlay": sigma_overlay(cells, ledger),
        "per_class": per_class(cells),
        # The CATEGORY cut the measurement bus has been doing by hand off
        # `by_category` (`14/36 cats ece<=3.0`). Rendered here beside the cell
        # cut for the same reason it is served beside it: two true numbers with
        # no single place that says they are different cuts read as a
        # contradiction. CAL-P998.
        "by_category_cut": category_scorecard(payload),
        # The MEASURED half of FIXED. The other half is Alex's eyeball on the
        # page at 49/49 (ratification, 2026-08-28) and no script can assert it.
        "done": len(queued) == 0
        and headline is not None
        and headline <= HEADLINE_TARGET_PP,
        "cells": cells,
    }


def needle(result: dict) -> str:
    """The lane's ONE number, per ``.claude/handoff/NEEDLE-SPEC.md``.

    Lives here rather than in the threshold table because the scorecard is the
    live instrument: a needle emitted by a side-by-side renderer could drift
    from the page's own verdict, and this is the number Fable copies.
    """
    c = result["counts"]
    return (
        f"NEEDLE: calibration {c['cells_at_bar']}/{c['cells_material']} "
        f"cells-at-bar @ {result['generated_at']}"
    )


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------


def _point_key(point: dict) -> tuple:
    """A datapoint's identity: the CURVE it measured and the BARS it used.

    Not the wall clock, because the producer stalls: on 2026-08-20 fourteen
    hourly samples all carried the same ``generated_at`` (17:17:43Z), and
    keying on the clock would have drawn a fourteen-point flat line out of one
    measurement.

    The bars are in the key because a re-score of the same curve at a DIFFERENT
    finish line is a different reading, not a repeat — which is exactly what
    2026-08-28's `20:37Z` curve is, banked once at the flat 3.0 pp bar before
    Alex's ratification was wired and once at 2.5/3.0/3.0 after. Keying on the
    curve alone would have silently refused the ratified reading and left the
    series' first needle point missing. The stall guard is untouched: same
    curve AND same bars is still a duplicate.

    Points banked before the ratification carry no ``thresholds`` key at all;
    they are keyed as the flat bar they were actually scored against, never as
    "unknown", so the pre-ratification history cannot collide with a re-score.

    THE SIGMA BASIS IS IN THE KEY FOR THE SAME REASON THE BARS ARE — CAL-P1002.
    D62 changed the gate's INPUT on 2026-09-04, so one curve now has two
    defensible readings (34/48 on the estimate, 35/48 on the measurement) and
    they are different readings, not a repeat. Without the basis in the key the
    second one is silently refused as a duplicate and the series' first
    post-D62 point goes missing — which is exactly what happened to the first
    ratified point until the bars were added here. Points banked before D62
    carry no basis and are keyed as the row estimate they were actually scored
    against, never as "unknown".
    """
    thresholds = point.get("thresholds") or {}
    bars = thresholds.get("class_bars_pp")
    if not bars:
        bars = {k: BAR_PP for k in CLASS_BARS_PP}
    basis = thresholds.get("sigma_gate_basis") or SIGMA_BASIS_ROW
    return (point.get("generated_at"), tuple(sorted(bars.items())), basis)


def record(result: dict, path: Path) -> str:
    """Append one datapoint, keyed on ``(generated_at, class bars)``.

    See :func:`_point_key` for why the key is that pair and not the wall clock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    key = _point_key(result)
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and _point_key(json.loads(line)) == key:
                return "duplicate_curve_generated_at"
    point = {
        k: result[k]
        for k in (
            "generated_at",
            "population_version",
            "total_outcomes",
            "headline_mce_closing_line",
            "availability",
            "producer_stalled",
            # Banked with every point since the 2026-08-28 ratification, because
            # the series changes DEFINITION on that date: points before it were
            # scored at a flat 3.0 and points after at 2.5/3.0/3.0. A trend line
            # across a threshold change that the datapoints cannot describe is a
            # chart that lies about its own units.
            "thresholds",
            "counts",
            "done",
        )
    }
    # Per-cell ECE for material cells only — enough to trend every cell that
    # can ever be queued, without banking 287 rows of noise per beat.
    point["material_cells"] = {
        c["cell"]: {"ece": c["ece"], "n": c["n"], "verdict": c["verdict"]}
        for c in result["cells"]
        if c["verdict"] != VERDICT_EXEMPT
    }
    with path.open("a") as fh:
        fh.write(json.dumps(point, sort_keys=True) + "\n")
    return "recorded"


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    pts = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return sorted(pts, key=lambda p: p.get("generated_at") or "")


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------


def render_markdown(result: dict, history: list[dict]) -> str:
    L: list[str] = []
    hl = result["headline_mce_closing_line"]
    arrow, trend = "—", "no prior datapoint"
    if len(history) >= 2:
        prev = history[-2]["headline_mce_closing_line"]
        if prev is not None and hl is not None:
            delta = round(hl - prev, 2)
            arrow = "🔴 ↑" if delta > 0.05 else ("🟢 ↓" if delta < -0.05 else "🟡 →")
            trend = (
                f"{prev} -> {hl} pp ({delta:+.2f}) since "
                f"{(history[-2].get('generated_at') or '?')[:10]}"
            )
    L.append(f"**Published curve: {hl} pp** (`mce_closing_line`)  {arrow}  {trend}")
    L.append("")
    L.append(
        f"- population `{result['population_version']}`, "
        f"{result['total_outcomes']:,} published outcomes, "
        f"curve generated `{result['generated_at']}`"
    )
    L.append(
        f"- availability **{result['availability']}**, producer stalled "
        f"**{result['producer_stalled']}** (beats missed "
        f"{result['producer_beats_missed']})"
    )
    c = result["counts"]
    bars = result["thresholds"]["class_bars_pp"]
    L.append(
        f"- ratified per-cohort bars **A {bars[CLASS_A]} / B {bars[CLASS_B]} / "
        f"C {bars[CLASS_C]} pp** (Alex, MC, 2026-08-28)"
    )
    L.append(
        f"- **{c['cells_queued']} cells over bar and established** "
        f"({c['queued_excess_outcomes']:,} excess-outcomes) | "
        f"{c['cells_pass']} pass | {c['cells_unestablished']} over-bar-unestablished | "
        f"{c['cells_exempt']} exempt (n < {MIN_CELL_N})"
    )
    L.append(
        f"- **cells at bar {c['cells_at_bar']}/{c['cells_material']}** — "
        f"**DONE (measured): {'YES' if result['done'] else 'NO'}**"
    )
    L.append(
        "- FIXED also requires **Alex's eyeball on the calibration page at "
        f"{c['cells_material']}/{c['cells_material']}** — his sign-off is the "
        "final gate, not the number alone."
    )
    L.append("")
    L.append("| class | bar pp | cells | at bar | queued | outcomes |")
    L.append("|---|--:|--:|--:|--:|--:|")
    for klass in (CLASS_A, CLASS_B, CLASS_C):
        p = result["per_class"][klass]
        L.append(
            f"| `{klass}` | **{p['bar_pp']}** | {p['cells']} | {p['at_bar']} | "
            f"{p['queued']} | {p['outcomes']:,} |"
        )
    ms = result.get("measured_sigma") or {}
    if not ms.get("decides"):
        L.append(
            "- ⚠️ **scored on the row-grain estimate alone** — no measured-sigma "
            "ledger was supplied, so `50/sqrt(n)` decided every cell. Since "
            "D62 = A that is a degraded reading, not the normal one."
        )
    else:
        L.append(
            f"- **the measured sigma DECIDES** (D62 = A, 2026-09-04): the "
            f"ratified {SIGMA_GATE} sigma gate is applied to the measured "
            f"cluster-bootstrap SE on **"
            f"{ms['material_cells_measured'] + ms['material_cells_carried']}** of "
            f"the {ms['material_cells']} material cells and to `50/sqrt(n)` on "
            f"the other {ms['material_cells_unmeasured'] + ms['material_cells_low_coverage']}. "
            f"On the estimate alone the needle reads "
            f"**{ms['cells_at_bar_row_basis']}/{c['cells_material']}**; measured, "
            f"**{c['cells_at_bar']}/{c['cells_material']}** "
            f"({ms['cells_at_bar_delta_vs_row_basis']:+d})."
        )
    moved = (result.get("sigma_overlay") or {}).get("cells_moved") or []
    if moved:
        # The cells the measurement moved get their OWN table, because a cell
        # taken OFF the queue is by definition absent from the queued table
        # below — and a board that hides the rows its own correction removed is
        # a board you cannot check the correction against.
        L.append("")
        L.append(
            f"**What the measurement changed** — {ms.get('cells_refuted', 0)} off "
            f"the queue, {ms.get('cells_added', 0)} on. Both directions: a "
            "correction that can only ever shorten the board is one nobody "
            "should trust."
        )
        L.append("")
        L.append(
            "| cell | from | to | sigma row | sigma meas | SE meas pp | "
            "ledger | excess-outcomes |"
        )
        L.append("|---|---|---|--:|--:|--:|---|--:|")
        for m in moved:
            sm = m["sigma_measured"]
            se = m["se_measured_pp"]
            sm_txt = "—" if sm is None else format(sm, ".2f")
            if m.get("measured_at_population") and m["ledger_status"] == (
                sigma_ledger.STATUS_CARRIED
            ):
                # CARRIED marks itself in the CELL, not only in a bullet above
                # it: a reader scanning a sigma must not have to remember a
                # summary line to know it was measured on another population.
                sm_txt += f"↩{m['measured_at_population']}"
            L.append(
                f"| `{m['cell']}` | {m['from']} | {m['to']} | "
                f"{m['sigma_row']:.2f} | {sm_txt} | "
                f"{'—' if se is None else format(se, '.4f')} | "
                f"{m['ledger_status']} | {m['excess_outcomes']:,} |"
            )
    if ms.get("material_cells_low_coverage"):
        L.append(
            f"- ⚠️ **{ms['material_cells_low_coverage']} cell(s) have a measured "
            f"sigma that is NOT allowed to decide** — the exact rail and the "
            f"payload disagree about the cell's population by more than "
            f"{round((1 - sigma_ledger.COVERAGE_BAND[0]) * 100)}%, so the SE and "
            f"the excess are not measurements of the same rows: "
            f"{', '.join(ms['low_coverage_cells'])}. They keep being decided by "
            "the estimate. Which side is inflated is a per-cell question — "
            "basketball is 43.44% phantom (CAL-P126)."
        )
    if ms.get("material_cells_carried"):
        L.append(
            f"- **{ms['material_cells_carried']}** of the deciding measurements "
            f"were taken on an EARLIER population "
            f"({', '.join(ms['carried_from_populations']) or 'unknown'}) whose "
            f"cell has not moved by more than "
            f"{round((1 - sigma_ledger.CELL_DRIFT_BAND[0]) * 100)}%: "
            f"{', '.join(ms['carried_cells'])}. They decide — the SE is the term "
            "that does not move when the ECE, the bar or the population version "
            "do — and they are still counted apart, because each one is a "
            "standing re-measure request."
        )
    L.append("")
    L.append(
        "| # | cell | class | ECE pp | n | gap pp | bar | excess pp | sigma row | "
        "sigma meas | var ratio | eff n | excess-outcomes |"
    )
    # `sigma row` is the ESTIMATE, always. The deciding sigma is whichever of
    # the two columns is not "—" — since D62 the measured one wins where it
    # exists — and printing a merged "sigma" column would put a proof and an
    # estimate under one heading, which is the defect these two columns exist
    # to expose (CAL-P127 lesson 10).
    L.append("|--:|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for i, cell in enumerate(
        [x for x in result["cells"] if x["verdict"] == VERDICT_QUEUED], 1
    ):
        # An unmeasured cell prints "—", never a number. Filling this column
        # with the row-grain figure would put a proof and an estimate in the
        # same column, which is the defect the column was added to expose.
        sm = cell.get("sigma_measured")
        if sm is None:
            sm_txt, deff_txt, eff_txt = "—", "—", "—"
        else:
            if cell.get("sigma_basis") != SIGMA_BASIS_MEASURED:
                # POPULATION_DIVERGENCE: shown in parentheses, which is the render's way
                # of saying this number is evidence and not a verdict.
                sm_txt = f"({sm:.2f})⚠️"
            else:
                sm_txt = f"{sm:.2f}" + (" 🔴" if sm < SIGMA_GATE else "")
                if cell.get("measured_carried"):
                    # CARRIED marks itself in the cell, not only in the summary
                    # line above it. Claim 5 is about the COLUMN: a number
                    # measured on the payload being scored and one carried
                    # forward from an earlier population are different evidence,
                    # and a reader scanning the table must not have to remember
                    # a bullet to know which one they are looking at.
                    sm_txt += f"↩{cell.get('measured_at_population') or '?'}"
            deff = cell.get("variance_ratio_vs_board")
            eff = cell.get("effective_n")
            deff_txt = "—" if deff is None else f"{deff:.2f}"
            eff_txt = "—" if eff is None else f"{eff:,}"
        L.append(
            f"| {i} | `{cell['cell']}` | {cell['class'][0]} | {cell['ece']:.2f} | "
            f"{cell['n']:,} | {cell['gap']:+.2f} | {cell['bar_pp']} | "
            f"{cell['excess_pp']:+.2f} | {cell['sigma_row']:.1f} | {sm_txt} | "
            f"{deff_txt} | {eff_txt} | {cell['excess_outcomes']:,} |"
        )
    return "\n".join(L)


# --------------------------------------------------------------------------


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=90) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true", help="fetch $BAINLUCK_API/api/calibration")
    src.add_argument("--payload", help="score a saved payload JSON instead")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--history", default=str(DEFAULT_HISTORY))
    ap.add_argument("--out", help="write the full JSON result here")
    ap.add_argument(
        "--sigma-ledger",
        default=str(sigma_ledger.LEDGER_PATH),
        help="measured cluster-bootstrap SEs (CAL-P128). Reported, not applied.",
    )
    ap.add_argument(
        "--no-sigma-ledger",
        action="store_true",
        help="score with the row-grain estimate alone, as before CAL-P128",
    )
    args = ap.parse_args()

    if args.live:
        base = os.environ.get("BAINLUCK_API", "https://api.bainluck.com").rstrip("/")
        payload = fetch(f"{base}/api/calibration")
    else:
        payload = json.loads(Path(args.payload).read_text())

    check = self_check(payload)
    if not check["ok"]:
        print("SELF-CHECK FAILED — scorecard NOT valid, nothing reported.", file=sys.stderr)
        print(json.dumps(check, indent=2)[:4000], file=sys.stderr)
        return 1

    # A ledger that fails its own coherence check RAISES rather than being
    # skipped. A scorecard that silently drops the measured column because a
    # file was malformed reports the old, too-optimistic board under the new
    # heading — the exact shape of gotcha #53.
    ledger = None if args.no_sigma_ledger else sigma_ledger.load(args.sigma_ledger)

    result = score(payload, ledger)
    result["self_check"] = {
        "ok": True,
        "detail": [
            f"{c['dimension']}: {c['matched']}/{c['cells']} cells reproduced exactly"
            for c in check["checks"]
        ],
    }

    hist_path = Path(args.history)
    if args.record:
        result["record_status"] = record(result, hist_path)
    history = load_history(hist_path)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True))

    if args.markdown:
        print(render_markdown(result, history))
    else:
        print(json.dumps({k: v for k, v in result.items() if k != "cells"}, indent=2))
        print(f"\nself-check: {result['self_check']['detail']}")
        print(f"\nQUEUED CELLS ({result['counts']['cells_queued']}):")
        for i, cell in enumerate(
            [c for c in result["cells"] if c["verdict"] == VERDICT_QUEUED], 1
        ):
            print(
                f"{i:3d}. {cell['cell']:42s} [{cell['class'][0]}] "
                f"ece={cell['ece']:6.2f} n={cell['n']:>8,} "
                f"gap={cell['gap']:+7.2f} bar={cell['bar_pp']:.1f} "
                f"sigma={cell['sigma']:6.1f} "
                f"excess-outcomes={cell['excess_outcomes']:>8,}"
            )
    print()
    print(needle(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
