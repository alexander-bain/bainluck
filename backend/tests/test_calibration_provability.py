"""The selection-bias rule (Fable directive, CAL-P067 item 4).

**Any published cell whose graded share is under 50% renders NOT-PROVABLE, with
the graded share shown.**

The argument, because the rule looks like a coverage threshold and is not one. A
calibration cell answers "when this source said 30%, how often did it happen?"
Answering it requires knowing what happened — i.e. a GRADE. So the rows that
reach the curve are exactly the rows that got graded, and the rows that did not
are silently absent.

That is a sample selected **on the property being measured**. It is not a small
sample, which widening error bars would handle; it is a biased one, which they
would not. Soccer's published 3.54pp is computed on its graded quarter, and the
ungraded three-quarters are not a random three-quarters — CAL-P066's census
found the never-graded population concentrated in whole shapes of market that
one grader owns and another never claimed. Nothing licenses extrapolating from
one to the other, so the honest rendering of the number is not a wider interval
around it. It is a refusal to publish it as a measurement at all.

This is deliberately the same shape as CAL-P067's ruling-075 fix: a state in
which the instrument cannot answer must have its own rendering, and must never
share one with "checked, fine". Here the third state is ``unknown`` — the graded
share itself was never measured — and it renders as ``unknown``, never as
``provable``.
"""

import pytest

from app.utils.calibration_provability import (
    MIN_GRADED_SHARE,
    PROVABILITY_NOT_PROVABLE,
    PROVABILITY_PROVABLE,
    PROVABILITY_UNKNOWN,
    annotate_cells,
    graded_share,
    provability,
)

# CAL-P066's census, the two cells the directive says flip immediately.
SOCCER_GRADED, SOCCER_RESOLVED = 98_381, 393_524  # 25.0%
TABLE_TENNIS_GRADED, TABLE_TENNIS_RESOLVED = 4_400, 40_000  # 11.0%


def test_the_threshold_is_a_half():
    assert MIN_GRADED_SHARE == 0.50


def test_soccer_flips_to_not_provable_and_shows_its_share():
    verdict, share, why = provability(SOCCER_GRADED, SOCCER_RESOLVED)
    assert verdict == PROVABILITY_NOT_PROVABLE
    assert share == pytest.approx(0.25, abs=0.001)
    assert "25.0%" in why
    # The share is SHOWN, not merely computed — the directive's own wording.
    assert "graded" in why.lower()


def test_table_tennis_flips_to_not_provable():
    verdict, share, _ = provability(TABLE_TENNIS_GRADED, TABLE_TENNIS_RESOLVED)
    assert verdict == PROVABILITY_NOT_PROVABLE
    assert share == pytest.approx(0.11, abs=0.001)


def test_a_majority_graded_cell_is_provable():
    verdict, share, _ = provability(750, 1_000)
    assert verdict == PROVABILITY_PROVABLE
    assert share == pytest.approx(0.75)


def test_exactly_half_graded_is_provable_and_the_boundary_is_asserted():
    """A closed boundary, stated once here so nobody has to infer it from an
    inequality later."""
    assert provability(500, 1_000)[0] == PROVABILITY_PROVABLE
    assert provability(499, 1_000)[0] == PROVABILITY_NOT_PROVABLE


def test_an_unmeasured_denominator_is_unknown_and_never_provable():
    """The rule's third state, and the same discipline as the ruling-075 fix:
    could-not-check gets its own rendering. A cell whose total resolved
    population was never counted has NOT been shown to be unbiased — treating
    the absence of the denominator as a pass is how the biased cells kept
    publishing."""
    for resolved in (None, 0, -1):
        verdict, share, why = provability(1_000, resolved)
        assert verdict == PROVABILITY_UNKNOWN, resolved
        assert share is None, resolved
        assert "not measured" in why or "unknown" in why


def test_junk_inputs_degrade_to_unknown_rather_than_to_a_verdict():
    for graded, resolved in (
        (None, 1_000),
        ("x", 1_000),
        (True, 1_000),
        (1_000, "x"),
        (-5, 1_000),
    ):
        assert provability(graded, resolved)[0] == PROVABILITY_UNKNOWN, (graded, resolved)


def test_more_graded_than_resolved_is_incoherent_and_reads_unknown():
    """A share above 1.0 means the two numbers came from different populations.
    Believing it would publish a confident pass off mismatched inputs."""
    assert provability(1_200, 1_000)[0] == PROVABILITY_UNKNOWN


def test_graded_share_is_exact_and_none_when_undefined():
    assert graded_share(1, 4) == 0.25
    assert graded_share(1, 0) is None
    assert graded_share(1, None) is None


# =============================================================================
# Cell annotation — what the page and the sentinel both consume
# =============================================================================


def test_annotate_marks_each_cell_and_never_drops_one():
    cells = [
        {"category": "soccer", "mce": 3.54, "n": SOCCER_GRADED},
        {"category": "baseball", "mce": 1.94, "n": 192_090},
    ]
    out = annotate_cells(
        cells,
        resolved_by_category={"soccer": SOCCER_RESOLVED, "baseball": 200_000},
    )
    assert len(out) == 2
    by_cat = {c["category"]: c for c in out}
    assert by_cat["soccer"]["provability"] == PROVABILITY_NOT_PROVABLE
    assert by_cat["soccer"]["graded_share"] == pytest.approx(0.25, abs=0.001)
    assert by_cat["baseball"]["provability"] == PROVABILITY_PROVABLE


def test_annotate_leaves_the_mce_untouched():
    """The rule changes how a number is RENDERED, never the number. A biased
    estimate is still the estimate; we decline to present it as a measurement,
    we do not silently substitute a different one."""
    cells = [{"category": "soccer", "mce": 3.54, "n": SOCCER_GRADED}]
    out = annotate_cells(cells, resolved_by_category={"soccer": SOCCER_RESOLVED})
    assert out[0]["mce"] == 3.54
    assert out[0]["n"] == SOCCER_GRADED


def test_a_category_with_no_denominator_annotates_unknown_not_provable():
    """The page must be able to tell "we checked and it is fine" from "we have
    no denominator for this cell". Absent the census, this is EVERY cell, so
    getting it wrong would paint the whole page green."""
    cells = [{"category": "soccer", "mce": 3.54, "n": SOCCER_GRADED}]
    out = annotate_cells(cells, resolved_by_category={})
    assert out[0]["provability"] == PROVABILITY_UNKNOWN
    assert out[0]["graded_share"] is None


def test_annotate_tolerates_a_missing_resolved_map_entirely():
    cells = [{"category": "soccer", "mce": 3.54, "n": 10}]
    out = annotate_cells(cells, resolved_by_category=None)
    assert out[0]["provability"] == PROVABILITY_UNKNOWN


def test_annotate_does_not_mutate_its_input():
    cells = [{"category": "soccer", "mce": 3.54, "n": SOCCER_GRADED}]
    annotate_cells(cells, resolved_by_category={"soccer": SOCCER_RESOLVED})
    assert "provability" not in cells[0]


def test_a_cell_without_a_category_is_still_annotated_unknown():
    """No key to look the denominator up by is a could-not-check, not a pass."""
    out = annotate_cells([{"mce": 1.0, "n": 500}], resolved_by_category={"soccer": 10})
    assert out[0]["provability"] == PROVABILITY_UNKNOWN


# =============================================================================
# The sentinel must not file an all-clear on a cell it cannot prove
# =============================================================================


def test_selection_bias_outranks_every_raw_vs_published_disposition():
    """The coordination the directive asks for with #1911. ``exclusion_working``
    on a cell that is 25% graded is a FALSE ALL-CLEAR — the exclusion may well
    be working on the quarter we can see, and that says nothing about the
    three-quarters we cannot. So the provability check runs FIRST and short-
    circuits, rather than being averaged in afterwards."""
    from app.tasks.calibration_sentinel import (
        DISP_NOT_PROVABLE,
        raw_vs_published,
    )

    # Numbers that would otherwise be a clean ``exclusion_working``.
    disp, why = raw_vs_published(
        raw_mce=21.33,
        published_mce=3.69,
        published_n=14_315,
        threshold=5.0,
        graded_share=0.25,
    )
    assert disp == DISP_NOT_PROVABLE
    assert "25.0%" in why


def test_a_well_graded_cell_still_gets_its_ordinary_disposition():
    """The rule must not swallow the #1911 behaviour it sits in front of."""
    from app.tasks.calibration_sentinel import (
        DISP_EXCLUSION_WORKING,
        raw_vs_published,
    )

    disp, _ = raw_vs_published(
        raw_mce=21.33,
        published_mce=3.69,
        published_n=14_315,
        threshold=5.0,
        graded_share=0.92,
    )
    assert disp == DISP_EXCLUSION_WORKING


# =============================================================================
# Route wiring — the rule must be inert-but-armed, never silently wrong
# =============================================================================


def test_route_states_the_absent_census_once_instead_of_badging_every_row():
    """With no denominators measured, the payload says so ONCE and the cells are
    left alone. Stamping "unmeasured" on fifteen public rows would train a reader
    to ignore the badge that matters — but saying nothing at all is the defect
    this queue is otherwise removing, so it is said in the payload."""
    from app.routes.calibration import _apply_provability

    out = {"by_category": [{"category": "soccer", "mce": 3.54, "n": 98_381}]}
    _apply_provability(out)
    assert out["provability_census"]["measured"] is False
    assert "bisection" in out["provability_census"]["reason"]
    assert out["provability_census"]["min_graded_share"] == MIN_GRADED_SHARE
    # cells untouched
    assert "provability" not in out["by_category"][0]


def test_route_annotates_every_cell_once_a_census_exists(monkeypatch):
    """The rule ships complete and inert: populating the census is the only
    remaining step, and it needs no further code."""
    from app.routes import calibration as route

    monkeypatch.setattr(
        route, "PROVABILITY_CENSUS", {"soccer": SOCCER_RESOLVED, "baseball": 200_000}
    )
    out = {
        "by_category": [
            {"category": "soccer", "mce": 3.54, "n": SOCCER_GRADED},
            {"category": "baseball", "mce": 1.94, "n": 192_090},
            {"category": "darts", "mce": 2.0, "n": 5_000},
        ]
    }
    route._apply_provability(out)
    by_cat = {c["category"]: c for c in out["by_category"]}
    assert by_cat["soccer"]["provability"] == PROVABILITY_NOT_PROVABLE
    assert by_cat["baseball"]["provability"] == PROVABILITY_PROVABLE
    # A category the census does not cover reads unknown, never provable.
    assert by_cat["darts"]["provability"] == PROVABILITY_UNKNOWN
    assert out["provability_census"]["measured"] is True


def test_annotation_failure_can_never_take_the_endpoint_down(monkeypatch):
    """/api/calibration going dark is the failure ruling CAL-P017 exists to
    prevent. A rendering rule must degrade to unannotated, never to a 500."""
    from app.routes import calibration as route

    monkeypatch.setattr(route, "PROVABILITY_CENSUS", {"soccer": 10})

    def boom(*a, **k):
        raise RuntimeError("annotate exploded")

    monkeypatch.setattr(route, "annotate_cells", boom)
    out = {"by_category": [{"category": "soccer", "n": 5}]}
    route._apply_provability(out)  # must not raise
    assert out["provability_census"]["measured"] is False
    assert "annotation_failed" in out["provability_census"]["reason"]


def test_a_payload_without_categories_is_left_completely_alone():
    from app.routes.calibration import _apply_provability

    out = {"buckets": []}
    _apply_provability(out)
    assert out == {"buckets": []}


def test_an_unmeasured_graded_share_preserves_the_existing_behaviour():
    """Back-compatible by construction: callers that do not yet pass a graded
    share get exactly the dispositions they got before. The rule can only ever
    turn a cell MORE honest, never silently change an unrelated one."""
    from app.tasks.calibration_sentinel import (
        DISP_REAL_BREAK,
        raw_vs_published,
    )

    assert raw_vs_published(21.33, 7.57, 14_315, 5.0)[0] == DISP_REAL_BREAK
    assert raw_vs_published(21.33, 7.57, 14_315, 5.0, graded_share=None)[0] == DISP_REAL_BREAK
