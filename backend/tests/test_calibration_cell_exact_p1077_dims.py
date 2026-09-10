"""CAL-P1077 — guards for the ``loneclaim`` and ``pubband`` dimensions.

Both dimensions were built to answer a queued cell, and both returned a verdict
that changed the queue rather than confirming it:

* ``loneclaim`` on ``polymarket/economics`` found the named mechanism REAL but
  measured the cell at **3.80** with the whole arm removed, against a 3.0 bar —
  not the ~0.5-1.0 the superset fold predicted. The cell does not close.
* ``pubband`` on ``polymarket/hockey`` found the named mechanism **ABSENT** —
  the published cell contains ZERO legs at a certain price, because the
  admission gate already refuses them.

CERT-2428 BLOCKED the first presentation of both, and not on the arithmetic: the
evidence came from ``calibration_cell_exact``'s id-range ``sweep()``, which
re-derives question identity inside each slice. Re-folded on
``calibration_whole_vm_fold`` — twice each, 21.7 and 27.0 minutes apart, on a
roster that was byte-identical between folds — **both conclusions held**
(3.78 -> 3.80, and the certain arm still absent). The provenance guards at the
bottom of this file exist so the next P1077 artifact cannot be banked off the
blocked rail; the finding that it happened to agree here is a measurement about
these two cells, not a licence.

An absence is the most dangerous thing a fold can report, because a broken
dimension reports the same shape as a clean cell (gotcha #53). Every test here
exists to make one specific way of being wrong loud:

* **``pubband`` reading ``opening_probability`` instead of the published price.**
  This is the trap the dimension was built to avoid and it is invisible: the
  producer's admission gate already demands ``opening_probability > 0 AND < 1``,
  so a band computed on that column is empty BY CONSTRUCTION. It would have
  reported "no legs at a certain price" — the same sentence the real fold
  returned — for a completely different reason, and the hockey verdict would
  have been a measurement of the gate rather than of the cell.
* **``loneclaim`` re-deriving its own outcome count.** "Lone claim" has to mean
  what it means in the producer's own D13 arm (``mrs.n_outcomes = 1``), or the
  fold is about a different population than the one the ruling admits.
* **Either dimension joining on ``market_id``.** ``deduped`` is at OUTCOME grain.
  A join to ``futures_outcomes`` on the market fans every multi-leg market out,
  and the fold still returns well-formed arms.
* **Losing a control arm.** ``b_lone_*`` is what separates "the defect is
  loneness" from "the defect is the grading channel", and ``z_*`` is the arm
  doctrine 18 grades a row-dropping fix on. Neither is decoration.
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path

from app.utils.resolution_authority import is_calibration_truth_eligible

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPO = Path(__file__).resolve().parents[2]

#: Where this subject's folds are banked, and where the rail it was BLOCKED for
#: using is kept so the differential below has a real specimen on both sides.
P1077_ARTIFACTS = REPO / "artifacts" / "cal-p1077"
SUPERSEDED_ARTIFACTS = P1077_ARTIFACTS / "superseded-id-range-rail"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")


# --------------------------------------------------------------------------
# Both dimensions are reachable at all
# --------------------------------------------------------------------------

def test_both_dimensions_are_registered_and_therefore_selectable():
    """A dimension absent from ``DIMENSIONS`` is an ``argparse`` error, not a
    silent empty fold — but only if it is registered under the name the
    artifacts are filed under."""
    assert "loneclaim" in cce.DIMENSIONS
    assert "pubband" in cce.DIMENSIONS
    assert "loneclaim" not in cce.PER_CHUNK_DIMENSIONS
    assert "pubband" not in cce.PER_CHUNK_DIMENSIONS


def test_neither_dimension_declares_a_pre_pass_it_does_not_have():
    """The third element of the tuple is SQL prepended to the chain. Both of
    these read columns that already exist, so a non-empty pre-pass here would
    mean someone added a CTE without adding it to ``PER_CHUNK_CONTEXT``."""
    for name in ("loneclaim", "pubband"):
        _expr, _join, pre = cce.DIMENSIONS[name]
        assert pre == "", f"{name} grew a pre-pass with no context registration"


# --------------------------------------------------------------------------
# pubband — the absence it reported has to be the cell's, not the gate's
# --------------------------------------------------------------------------

def test_pubband_bands_the_published_price_not_the_admission_price():
    """🔴 THE ONE THAT MATTERS.

    The producer admits an outcome on ``opening_probability > 0 AND < 1`` and
    then publishes ``COALESCE(calibration_probability, opening_probability)``.
    Banding the first column can only ever produce an empty ``a_pub_certain``
    arm, and it produces it for a reason that has nothing to do with the cell.
    """
    expr = cce.PUBBAND_EXPR
    coalesced = re.findall(
        r"COALESCE\(\s*fo14\.calibration_probability\s*,\s*fo14\.opening_probability\s*\)",
        expr,
    )
    assert len(coalesced) >= 4, (
        "every band comparison must read the published price; found "
        f"{len(coalesced)} COALESCE(...) reads"
    )
    # The COALESCE fallback argument is the ONLY legal mention of the admission
    # column; anything not preceded by a comma is a bare comparison.
    outside = [
        m for m in re.finditer(r"fo14\.opening_probability", expr)
        if not expr[max(0, m.start() - 40):m.start()].rstrip().endswith(",")
    ]
    assert not outside, (
        "pubband compares a bare opening_probability somewhere: "
        f"{[expr[max(0, m.start()-40):m.end()] for m in outside]}"
    )


def test_pubband_keeps_the_certain_arm_separate_from_the_near_certain_shoulder():
    """Pooling 1.0000 with 0.99 would have hidden which of the two the bus's
    'exactly 1.0000' claim was about."""
    expr = cce.PUBBAND_EXPR
    assert "a_pub_certain" in expr
    assert "b_pub_near_certain" in expr
    assert "z_pub_ordinary" in expr
    assert ">= 1.0" in expr and "<= 0.0" in expr
    assert ">= 0.99" in expr and "<= 0.01" in expr


def test_pubband_records_which_column_the_price_came_from():
    """``from_calibration`` vs ``from_opening`` is what makes the COALESCE
    visible in the output instead of assumed in the reader's head."""
    assert "from_opening" in cce.PUBBAND_EXPR
    assert "from_calibration" in cce.PUBBAND_EXPR


def test_pubband_joins_the_outcome_row_not_the_market():
    assert "fo14.id = d.outcome_id" in cce.PUBBAND_JOIN
    assert "d.market_id" not in cce.PUBBAND_JOIN


# --------------------------------------------------------------------------
# loneclaim — "lone" must mean what the producer's own D13 arm means
# --------------------------------------------------------------------------

def test_loneclaim_takes_its_outcome_count_from_the_producers_own_shape_cte():
    """``market_result_shape.n_outcomes`` is the column the D13 arm counts on.
    A re-derived ``COUNT(*)`` here would fold a different population than the
    one the ruling admits, and would agree with it most of the time."""
    expr, join, _pre = cce.DIMENSIONS["loneclaim"]
    assert "market_result_shape mrs13" in join
    assert "mrs13.market_id = d.market_id" in join
    assert re.search(r"mrs13\.n_outcomes\s*=\s*1", expr)
    assert "COUNT(" not in expr.upper(), "loneclaim must not re-derive the count"


def test_loneclaim_joins_the_outcome_row_not_the_market():
    """``deduped`` is at outcome grain; a market-grain join to
    ``futures_outcomes`` fans out and still returns well-formed arms."""
    _expr, join, _pre = cce.DIMENSIONS["loneclaim"]
    assert "fo13.id = d.outcome_id" in join
    assert "fo13.market_id" not in join


def test_loneclaim_keeps_the_control_arm_that_separates_channel_from_loneness():
    """``b_lone_<source>`` is the control. Collapsing it into ``z_not_lone``
    would make a channel defect and a shape defect look identical — and on
    ``polymarket/economics`` the arm came back EMPTY, which is itself the
    finding (every published lone claim there is api_settlement-graded)."""
    expr, _join, _pre = cce.DIMENSIONS["loneclaim"]
    assert "a_lone_api_settlement" in expr
    assert "b_lone_" in expr
    assert "z_not_lone" in expr
    assert "fo13.resolution_source" in expr
    assert "COALESCE(fo13.resolution_source, 'null')" in expr, (
        "an ungraded lone claim must land in a named arm, not in NULL"
    )


def test_neither_dimension_reuses_a_sibling_or_producer_table_alias():
    """🔴 THE GUARD THIS SESSION LEARNED THE HARD WAY.

    ``pubband`` was first written with ``fo9``, which is ``bandratio``'s alias
    AND appears in the producer's own chain. Nothing errors: the join binds to
    the nearer scope and a CROSSED dimension quietly aggregates something else.
    ``test_the_outcome_alias_does_not_collide_with_another_dimension`` in
    ``test_calibration_cell_exact_p131_bandratio.py`` caught it from the other
    side; this is the same guard facing this way, so the next dimension added
    here is refused rather than the next one added there.
    """
    mine = {"LONECLAIM_JOIN", "PUBBAND_JOIN"}
    my_aliases = {"fo13", "mrs13", "fo14"}
    siblings = [
        blob
        for name, blob in vars(cce).items()
        if isinstance(blob, str)
        and name.endswith(("_JOIN", "_PRE", "_EXPR"))
        and name not in mine
        and not name.startswith(("LONECLAIM", "PUBBAND"))
    ]
    assert siblings, "no sibling joins found — the guard would pass vacuously"
    for alias in my_aliases:
        for blob in siblings:
            assert not re.search(rf"\b{alias}\b", blob), (
                f"{alias} is already taken by a sibling dimension"
            )
    producer = (
        Path(__file__).resolve().parents[1]
        / "app" / "tasks" / "precompute_calibration.py"
    ).read_text()
    for alias in my_aliases:
        assert not re.search(rf"\b{alias}\b", producer), (
            f"{alias} is already used inside the producer's own chain"
        )


def test_the_source_the_arm_names_can_actually_reach_the_published_curve():
    """If ``api_settlement`` ever left the truth-eligible allowlist, this arm
    would read 0 rows on every cell and the dimension would report 'mechanism
    absent' with no way to tell that from a fixed cell (gotcha #53)."""
    assert is_calibration_truth_eligible("api_settlement")


# --------------------------------------------------------------------------
# Both compose into a sendable statement
# --------------------------------------------------------------------------

def test_both_dimensions_compose_into_one_sendable_statement():
    """``POST /api/admin/db-query`` refuses a multi-statement body, and the
    producer's SQL carries prose comments that contain semicolons — so the
    composed statement is only sendable after comment stripping. A dimension
    whose own comment carries a semicolon breaks the send, not the parse."""
    for name in ("loneclaim", "pubband"):
        sql = cce.cell_sql("polymarket", "economics", 0, 1, name)
        assert sql.count(";") == 0, f"{name} composes a multi-statement body"
        assert len(sql) < cce.MAX_SQL_CHARS, f"{name} composes past the length cap"
        assert "FROM deduped d" in sql
        assert " AS k," in sql


# --------------------------------------------------------------------------
# CERT-2428 — the artifact must name the POPULATION it was folded on
# --------------------------------------------------------------------------
#
# The dimensions above were correct and the arithmetic inside the first banked
# artifacts was correct. The BLOCK was about neither: both files came from
# ``calibration_cell_exact``'s ``sweep()``, which partitions on raw
# ``futures_markets.id`` ranges and re-derives ``group_sizes``/``event_sizes``
# inside every slice. That is the CAL-P124 defect — on ``polymarket/basketball``
# it reproduced 8,426 of 13,135 published rows, -35.85% — and it does not just
# lose rows, it re-assigns markets between the very classes a dimension names.
# So a conclusion about the PUBLISHED cell cannot be read off it, however many
# times the number repeats: repetition proves the partition is stable, not that
# it is the published one.
#
# Nothing about that is visible in a fold's numbers. The two rails print the
# same table with the same column headings, and the ID-range one is FASTER and
# has no cache to warm — so the way a future session re-banks the wrong rail is
# not stubbornness, it is convenience. These tests are the only thing standing
# between that and a cert body.
#
# The check is deliberately on the ARTIFACTS rather than on a helper, because
# the artifact is what a cert reads and what a later session quotes.


def _banked_json() -> list[tuple[Path, dict]]:
    """EVERY json banked for this subject, recursively, minus the negative
    control — not a name-matched subset.

    Globbing ``whole-vm-fold*.json``, or only the top level, would make the
    guard below unfailable by the two routes that actually matter: an artifact
    banked under a different name, or one dropped into a subdirectory.
    """
    return [(p, json.loads(p.read_text()))
            for p in sorted(P1077_ARTIFACTS.rglob("*.json"))
            if SUPERSEDED_ARTIFACTS not in p.parents]


def _banked_folds() -> list[tuple[Path, dict]]:
    """The subset that is a FOLD — it carries a replica result block.

    Shape, not filename. A fold is the thing a cert quotes an arm out of, and it
    is the only thing the rail distinction is ABOUT; a receipt (a roster hash, an
    exposure count) is neither, and demanding it name a rail would either be
    vacuous or push it into a lie.
    """
    return [(p, d) for p, d in _banked_json() if "exact" in d]


def test_p1077_artifacts_name_the_whole_vm_rail():
    """THE guard CERT-2428 required. Every banked P1077 fold is whole-VM.

    Two independent markers, so neither rail can be mistaken for the other by
    one key going missing: the whole-VM writer stamps ``rail`` and has no id
    ranges at all, the ID-range writer stamps ``width`` and no ``rail``. The
    ``width`` half is checked over EVERY banked json rather than only the folds,
    because a file the fold-detector does not recognise is exactly how an
    id-range artifact would get back in.
    """
    folds = _banked_folds()
    assert folds, (
        f"no fold artifacts under {P1077_ARTIFACTS} — this guard must never "
        f"pass by having nothing to grade (gotcha #53)"
    )
    for path, doc in folds:
        assert doc.get("rail") == "whole_vm", (
            f"{path.name} does not name the whole-vm rail (rail="
            f"{doc.get('rail')!r}). CERT-2428: a conclusion about the "
            f"published cell may not be banked off the id-range rail."
        )
    for path, doc in _banked_json():
        assert "width" not in doc, (
            f"{path.name} carries an id-range width — it was written by "
            f"calibration_cell_exact.sweep(), not by the whole-vm rail"
        )


def test_both_p1077_dimensions_are_banked_and_each_is_folded_twice():
    """Fable's rule 1, made executable.

    "Fold twice, at least twenty minutes apart; quote only what repeats" was
    adopted as written because a SINGLE fold of a live population banked
    ECE 39.0 as a mechanism's size and it was under 12 an hour later. A cert on
    one fold is refused, so one fold must not be bankable either.
    """
    by_cell: dict[tuple, list[str]] = defaultdict(list)
    for path, doc in _banked_folds():
        by_cell[(doc["source"], doc["category"], doc["by"])].append(path.name)

    dims = {cell[2] for cell in by_cell}
    assert dims == {"loneclaim", "pubband"}, (
        f"CERT-2428 required BOTH dimensions re-folded on the whole-vm rail; "
        f"banked: {sorted(dims)}"
    )
    for cell, names in sorted(by_cell.items()):
        assert len(names) >= 2, (
            f"{cell[0]}/{cell[1]} --by {cell[2]} is banked from a single fold "
            f"({names}) — the two-fold rule refuses it"
        )


def test_the_id_range_rail_really_does_leave_a_different_fingerprint():
    """The differential, on real specimens of BOTH rails for the SAME cells.

    Without this, the test above could be passing because ``rail`` is a key
    every fold happens to carry. The superseded directory holds the exact two
    files CERT-2428 blocked — same source, same category, same dimension — and
    they must still read as the other rail, or the marker is not a marker.
    """
    old = sorted(SUPERSEDED_ARTIFACTS.glob("*.json"))
    assert old, (
        f"{SUPERSEDED_ARTIFACTS} is empty — the blocked artifacts are the "
        f"negative control for this guard and are kept, not deleted"
    )
    new_cells = {(d["source"], d["category"], d["by"]) for _p, d in _banked_folds()}
    for path in old:
        doc = json.loads(path.read_text())
        assert "rail" not in doc, f"{path.name} is not an id-range artifact"
        assert "width" in doc, f"{path.name} is not an id-range artifact"
        assert (doc["source"], doc["category"], doc["by"]) in new_cells, (
            f"{path.name} grades a cell the whole-vm rail never re-folded, so "
            f"it is not a control for anything"
        )


def test_only_the_whole_vm_writer_can_stamp_the_whole_vm_marker():
    """A guard on an artifact key is worth exactly as much as the key's owner.

    If ``calibration_cell_exact`` ever learns to write ``"rail"``, the artifact
    check above becomes satisfiable from the blocked path and says nothing.
    (If that script is genuinely moved onto the frozen roster one day, this
    fails and that is the conversation, not a silent overlap — the same
    contract ``test_the_id_range_rail_really_does_re_derive_them`` states in
    ``test_calibration_whole_vm_fold_p125.py``.)
    """
    wvf_src = (SCRIPTS / "calibration_whole_vm_fold.py").read_text()
    cce_src = (SCRIPTS / "calibration_cell_exact.py").read_text()
    assert '"rail": "whole_vm"' in wvf_src
    assert '"rail"' not in cce_src, (
        "calibration_cell_exact now writes a rail marker; the P1077 artifact "
        "provenance check can no longer tell the two rails apart"
    )
    assert '"width": args.width' in cce_src
    assert '"width":' not in wvf_src.split("def main(")[-1], (
        "the whole-vm rail has no id ranges; a width in its output means it "
        "grew one"
    )
