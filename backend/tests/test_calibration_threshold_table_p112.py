"""CAL-P112 — guards for the per-cohort threshold table and the cell replica bench.

The class this suite exists to catch: a finish line that reports a number
nobody can reproduce. Three ways that happens, one test each —

1. a cell lands in the wrong cohort class, so it is scored against a bar that
   was never argued for it;
2. the sigma gate stops doing work, so the queue fills with cells the sample
   cannot distinguish from the bar (the defect ``SIGMA_GATE`` was introduced
   for: *"15 of the 21 are under 3 sigma"*);
3. the NEEDLE line drifts from ``.claude/handoff/NEEDLE-SPEC.md``, so Fable's
   heartbeat copies a number into YOUR-TURN that means something else.

Plus the RED-first check ruling 133 wants on any gate: mutating a bar MUST move
``cells_at_bar``, or the table is decorative.

CAL-P115, after Alex ratified the table on 2026-08-28, adds a FOURTH: the two
instruments must not be able to disagree. The bars now live in
``calibration_scorecard.py`` and this module imports them, so
``test_the_table_and_the_scorecard_cannot_disagree`` and
``test_bars_are_imported_not_redeclared`` pin the single-declaration property
that makes ``29/49`` mean the same thing on both rails. The failure they exist
to stop is the one this program shipped for a day on purpose and named on the
page: RATIFIED IN PROSE, RENDERING THE OLD BAR.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tt = _load("calibration_threshold_table")
rep = _load("calibration_cell_replica")


def _payload(cells):
    """A payload whose ``buckets`` fold to exactly the requested cells.

    One bucket row per cell, at ``bucket_idx`` 5, with ``sum_prob`` and
    ``winners`` chosen so the folded ECE is the requested value. ``by_category``
    / ``by_source`` are derived the same way the fold derives them, so
    ``self_check`` passes on a payload that is internally consistent by
    construction — the check is doing real work only when it is given a
    consistent input to agree with.
    """
    buckets = []
    for source, category, ece, n in cells:
        winners = round(n * 0.5)
        buckets.append({
            "bucket_idx": 5, "source": source, "category": category,
            "price_moved": False, "n": n, "winners": winners,
            "sum_prob": winners + ece / 100.0 * n,
        })
    return {
        "generated_at": "2026-08-28T00:00:00+00:00",
        "population_version": "test",
        "total_outcomes": sum(b["n"] for b in buckets),
        "mce_closing_line": 1.9,
        "buckets": buckets,
        "by_category": [], "by_source": [],
    }


# --------------------------------------------------------------------------
# 1. cohort assignment
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source,category,expected", [
    # odds_api* is class A whatever the category — the class is about how the
    # PRICE is formed (a devigged multi-book consensus), not about the sport.
    ("odds_api", "basketball_nba", tt.CLASS_A),
    ("odds_api_bookmaker", "baseball_mlb", tt.CLASS_A),
    ("odds_api_spreads", "baseball_mlb", tt.CLASS_A),
    ("odds_api_totals", "basketball_ncaab", tt.CLASS_A),
    # single-venue exchange, scheduled contest
    ("kalshi", "football", tt.CLASS_B),
    ("polymarket", "esports", tt.CLASS_B),
    ("polymarket", "soccer", tt.CLASS_B),
    # single-venue exchange, standalone / long horizon
    ("kalshi", "tech", tt.CLASS_C),
    ("kalshi", "economics", tt.CLASS_C),
    ("polymarket", "politics", tt.CLASS_C),
    ("kalshi", "weather", tt.CLASS_C),
])
def test_cohort_class_is_structural(source, category, expected):
    assert tt.classify(source, category) == expected


def test_every_class_has_a_bar_and_a_rationale():
    for klass in (tt.CLASS_A, tt.CLASS_B, tt.CLASS_C):
        assert klass in tt.RATIFIED_BARS
        assert tt.CLASS_RATIONALE[klass].strip()


def test_no_class_is_looser_than_the_reader_bar():
    """The table may hold a class TIGHTER than reader-actionability. It may
    never hold one looser: every class already contains a published cell far
    under 3.0 pp, so a looser bar would be unearned. Encoded so a future edit
    that quietly relaxes class C has to delete this test to do it."""
    from calibration_scorecard import BAR_PP
    for klass, bar in tt.RATIFIED_BARS.items():
        assert bar <= BAR_PP, f"{klass} bar {bar} is looser than the reader bar {BAR_PP}"


def test_the_ratified_bars_are_the_numbers_alex_ruled():
    """Alex ruled A 2.5 / B 3.0 / C 3.0 by MC on 2026-08-28. A ratified
    threshold that a lane can move without a second MC is not ratified, so the
    literal numbers are pinned here and changing one requires deleting this."""
    assert tt.RATIFIED_BARS == {tt.CLASS_A: 2.5, tt.CLASS_B: 3.0, tt.CLASS_C: 3.0}


def test_bars_are_imported_not_redeclared():
    """One declaration, in the instrument that publishes the page.

    Before the wiring, this module owned the class map and the scorecard owned
    a flat bar — and for one day the two rails reported 30/49 and 29/49 off the
    same curve. ``is`` rather than ``==``: an equal COPY would pass an equality
    check and still drift the next time one of them is edited."""
    import calibration_scorecard as sc

    assert tt.RATIFIED_BARS is sc.CLASS_BARS_PP
    assert tt.classify is sc.classify
    assert tt.GAME_CATEGORIES is sc.GAME_CATEGORIES


# --------------------------------------------------------------------------
# 2. the gate does work
# --------------------------------------------------------------------------

def test_sigma_gate_keeps_an_indistinguishable_cell_out_of_the_queue():
    # 3.4 pp on 1,200 rows: over the 3.0 bar on the point estimate, but
    # se = 50/sqrt(1200) = 1.44 pp, so the excess is 0.28 sigma. Not queued.
    payload = _payload([("kalshi", "football", 3.4, 1200)])
    ev = tt.evaluate(tt.score(payload), tt.RATIFIED_BARS)
    assert ev["cells_queued"] == 0
    assert ev["cells_at_bar"] == 1
    assert ev["rows"][0]["sigma"] < tt.SIGMA_GATE


def test_an_established_cell_is_queued_and_carries_its_excess_outcomes():
    payload = _payload([("kalshi", "football", 8.0, 5000)])
    ev = tt.evaluate(tt.score(payload), tt.RATIFIED_BARS)
    assert ev["cells_queued"] == 1
    row = ev["rows"][0]
    assert row["bar_pp"] == 3.0
    assert row["excess_pp"] == pytest.approx(5.0, abs=0.05)
    assert row["excess_outcomes"] == pytest.approx(5.0 * 5000, rel=0.02)


def test_class_A_bar_is_what_separates_the_two_tables():
    """The cell that actually moves, at its measured 2026-08-28 values.
    ``odds_api_bookmaker/icehockey_nhl`` reads 3.89 pp on 8,658 rows: against
    the flat 3.0 bar its excess is 1.65 sigma and it is over-bar-unestablished;
    against the class-A 2.5 bar it is 2.59 sigma and it is queued. If this ever
    stops being true the ratification has become a relabelling, not a decision.

    Since CAL-P115 this is also the RED-first proof that the wiring reached the
    LIVE instrument: the third assertion asks ``score()`` itself, which is what
    renders the page, not ``evaluate()``, which only renders the side-by-side.
    A refactor that left the scorecard on the flat bar would pass the first two
    and fail the third."""
    payload = _payload([("odds_api_bookmaker", "icehockey_nhl", 3.89, 8658)])
    result = tt.score(payload)
    assert tt.evaluate(result, tt.INCUMBENT_BARS)["cells_queued"] == 0
    assert tt.evaluate(result, tt.RATIFIED_BARS)["cells_queued"] == 1
    assert result["counts"]["cells_queued"] == 1
    assert result["cells"][0]["bar_pp"] == 2.5


def test_the_table_and_the_scorecard_cannot_disagree():
    """``agreement()`` is a tautology on a good day and a tripwire on a bad one.

    A mixed payload — one cell per class, one of them the class-A cell whose
    verdict the ratification actually changed — must produce identical counts
    and an identical queued SET on both rails."""
    payload = _payload([
        ("odds_api_bookmaker", "icehockey_nhl", 3.89, 8658),   # A, queued at 2.5
        ("kalshi", "football", 8.00, 5000),                    # B, queued at 3.0
        ("polymarket", "politics", 1.20, 40000),               # C, passes
    ])
    result = tt.score(payload)
    ratified = tt.evaluate(result, tt.RATIFIED_BARS)
    agree = tt.agreement(result, ratified)
    assert agree["ok"], agree["mismatches"]
    assert result["counts"]["cells_at_bar"] == ratified["cells_at_bar"] == 1
    assert result["counts"]["cells_queued"] == 2


def test_agreement_reds_when_the_two_rails_are_scored_differently():
    """RED-first for the tripwire itself. Feeding ``evaluate`` the INCUMBENT
    bars is exactly the state the repo was in for one day — page on 3.0, table
    on 2.5 — and ``agreement`` must refuse it rather than print both."""
    payload = _payload([("odds_api_bookmaker", "icehockey_nhl", 3.89, 8658)])
    result = tt.score(payload)
    agree = tt.agreement(result, tt.evaluate(result, tt.INCUMBENT_BARS))
    assert agree["ok"] is False
    fields = {m["field"] for m in agree["mismatches"]}
    assert "cells_queued" in fields and "queued_cells" in fields


def test_mutating_a_bar_moves_cells_at_bar():
    """RED-first. A threshold table that scores the same at any threshold is
    not a threshold table."""
    payload = _payload([
        ("odds_api", "basketball_nba", 2.8, 20000),
        ("kalshi", "football", 3.4, 40000),
        ("polymarket", "politics", 4.0, 40000),
    ])
    result = tt.score(payload)
    loose = tt.evaluate(result, {tt.CLASS_A: 5.0, tt.CLASS_B: 5.0, tt.CLASS_C: 5.0})
    tight = tt.evaluate(result, {tt.CLASS_A: 1.0, tt.CLASS_B: 1.0, tt.CLASS_C: 1.0})
    assert loose["cells_at_bar"] == 3
    assert tight["cells_at_bar"] == 0


def test_material_floor_is_inherited_not_reimplemented():
    """Cells under the payload's own disclosure floor never reach the table —
    and they are inherited from the scorecard rather than re-declared here, so
    the two pages can never disagree about which cells are in scope."""
    payload = _payload([("kalshi", "tech", 40.0, 200)])
    ev = tt.evaluate(tt.score(payload), tt.RATIFIED_BARS)
    assert ev["cells_material"] == 0
    assert tt.MIN_CELL_N == 1000


# --------------------------------------------------------------------------
# 3. the NEEDLE contract
# --------------------------------------------------------------------------

def test_needle_matches_the_spec_shape():
    """The needle is emitted from the SCORECARD's counts since CAL-P115.

    It moved there with the bars, for the reason NEEDLE-SPEC gives: Fable only
    copies this line, so it has to come off the same counts the page's DONE
    verdict comes off. A needle rendered by the side-by-side could report a
    number the page does not agree with — which is precisely what happened on
    2026-08-28 between ratification and wiring."""
    payload = _payload([("kalshi", "football", 8.0, 5000),
                        ("kalshi", "tennis", 1.0, 5000)])
    result = tt.score(payload)
    result["generated_at"] = "2026-08-28T17:33:03+00:00"
    line = tt.needle(result)
    # NEEDLE: <lane> <value> <unit> @ <ISO timestamp>
    assert line.startswith("NEEDLE: calibration ")
    assert " cells-at-bar @ 2026-08-28T17:33:03+00:00" in line
    assert "1/2" in line
    # and it is the same object the scorecard exports, not a second copy
    import calibration_scorecard as sc

    assert tt.needle is sc.needle


# --------------------------------------------------------------------------
# 4. the replica bench's shape vocabulary
# --------------------------------------------------------------------------

def _row(n_all, w_all, cp_sum=1.0, cp=0.5, win=0):
    return {"n_all": n_all, "w_all": w_all, "cp_sum": cp_sum, "cp": cp,
            "adj": cp, "win": win, "mid": 1}


@pytest.mark.parametrize("n_all,w_all,expected", [
    (40, 40, "bundle_multiwin"),   # a cumulative ladder where every rung hit
    (20, 2, "bundle_multiwin"),
    (7, 1, "field_1win"),          # partition OR the 1-winner tail of a bundle
    (2, 1, "binary_1win"),
    (2, 2, "binary_other"),        # both sides won — impossible for a partition
    (2, 0, "void_0win"),           # w_all == 0 wins the branch before shape
    (1, 1, "single"),
])
def test_shape_class(n_all, w_all, expected):
    assert rep.shape_class(_row(n_all, w_all)) == expected


def test_nonpartition_sum_rule_separates_ladder_from_partition():
    """The realization-independent test. A captured partition sums to ~1; a
    bundle of independent binaries sums to N x p. This is the clause that
    catches the 1-winner tail the shipped ``>=2 winners`` test walks past."""
    ladder = _row(7, 1, cp_sum=2.85)
    partition = _row(7, 1, cp_sum=1.01)
    assert rep.RULES["nonpartition_sum"](ladder) is True
    assert rep.RULES["nonpartition_sum"](partition) is False
    # and it must not reach a two-outcome market, whatever its sum
    assert rep.RULES["nonpartition_sum"](_row(2, 1, cp_sum=1.9)) is False


def test_shipped_bundle_rule_is_realization_based():
    """Documents the defect the CAL-P112 designs address: the shipped esports
    test asks how many winners a market HAPPENED to have, so the same structure
    with one winner survives it."""
    assert rep.RULES["bundle_multiwin"](_row(7, 2)) is True
    assert rep.RULES["bundle_multiwin"](_row(7, 1)) is False


def test_fold_reproduces_a_hand_computed_cell():
    rows = [
        {"adj": 0.20, "win": 0}, {"adj": 0.20, "win": 0},
        {"adj": 0.20, "win": 1}, {"adj": 0.20, "win": 1},
        {"adj": 0.80, "win": 1}, {"adj": 0.80, "win": 1},
    ]
    n, ece, gap = rep.fold(rows)
    assert n == 6
    # bin 2: avg_p .20 vs win_rate .50 -> .30 x 4 rows; bin 8: .80 vs 1.0 -> .20 x 2
    assert ece == pytest.approx((0.30 * 4 + 0.20 * 2) / 6 * 100, abs=0.01)
    assert gap == pytest.approx((0.20 * 4 + 0.80 * 2 - 4) / 6 * 100, abs=0.01)


def test_fold_of_nothing_is_not_a_zero():
    """An empty cohort has no ECE. Returning 0.0 would read as perfect
    calibration — gotcha #53 in one line."""
    n, ece, gap = rep.fold([])
    assert n == 0 and ece is None and gap is None


def test_cell_se_convention_is_shared_with_the_board():
    assert tt.cell_se_pp(2500) == pytest.approx(1.0)
    assert tt.cell_se_pp(10000) == pytest.approx(50 / math.sqrt(10000))
