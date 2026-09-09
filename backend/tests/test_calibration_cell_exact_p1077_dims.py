"""CAL-P1077 — guards for the ``loneclaim`` and ``pubband`` dimensions.

Both dimensions were built to answer a queued cell, and both returned a verdict
that changed the queue rather than confirming it:

* ``loneclaim`` on ``polymarket/economics`` found the named mechanism REAL but
  measured its removal at **4.56 -> 3.78**, not the ~0.5-1.0 the superset fold
  predicted. The cell does not close.
* ``pubband`` on ``polymarket/hockey`` found the named mechanism **ABSENT** —
  the published cell contains ZERO legs at a certain price, because the
  admission gate already refuses them.

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
import re
from pathlib import Path

from app.utils.resolution_authority import is_calibration_truth_eligible

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


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
