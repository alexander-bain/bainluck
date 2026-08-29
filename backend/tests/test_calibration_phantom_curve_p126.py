"""CAL-P126 — guards for the whole-curve phantom measurement.

WHAT THIS INSTRUMENT CLAIMS, AND THEREFORE WHAT BREAKING IT LOOKS LIKE
------------------------------------------------------------------------
16-CAL is a population defect: ``deduped`` is one row per outcome by
construction and it is not behaving that way, because ``vm_stats`` groups by
five columns and ``ranked_outcomes`` joins ``clean_vms`` on two. CAL-P125
measured 43.44% phantom on ``polymarket/basketball`` and 12.85% on
``cricket``. This file measures how much of the WHOLE curve is affected and what
it does to the published 1.89.

Every claim it makes is one an edit can break while leaving the instrument
printing a complete, plausible, well-formed table. So these are silent-failure
guards in the gotcha #53 sense, and they are grouped by the claim they defend:

  1. **The scan's all-clear is a PROOF, not a sample.** ``clean_vms`` filters
     ``vm_stats``; a filter cannot create a grain; so one distinct
     ``(category, is_grouped, mutually_exclusive)`` inside a ``(vm_id, source)``
     means at most one ``clean_vms`` row means zero phantom. That direction is
     the entire reason the cheap mode is allowed to answer anything. Reverse the
     inequality, count the wrong three columns, or scan a CTE downstream of the
     filter and the mode starts declaring dirty cells clean.

  2. **A cell that could not be scanned is not a clean cell.** An empty or
     failed result must surface as ``SCAN_TIMEOUT`` and be counted separately —
     gotcha #53, aimed at the one number that decides whether the curve is
     trustworthy.

  3. **De-duplication is measured, not assumed.** The copies of an outcome are
     produced by ``clean_vms`` rows carrying DIFFERENT ``eligible`` aggregates,
     and ``eligible`` is read downstream, so two copies can in principle be
     published at two prices in two buckets. The instrument attributes
     ``1/copies`` and separately COUNTS every disagreement; a change that drops
     the coherence census turns an unproved assumption into a silent one.

  4. **The headline substitution is a RATIO.** The rail reproduces a cell to
     within a fraction of a percent, not exactly (−0.14% on basketball). Replace
     the payload's absolute numbers with the rail's and that shortfall is
     reported as phantom damage. Scaling the payload's own bucket by the rail's
     ``dedup/ship`` ratio cancels any factor common to both.

  5. **``winners`` scales on the WINNER ratio, not the row ratio.** A bucket
     whose duplicated rows are disproportionately winners moves its actual rate,
     and that movement is the entire mechanism by which de-duplication changes a
     calibration error rather than just an ``n``. Scale winners by the row ratio
     and every delta collapses to approximately zero — a wrong answer that looks
     like a reassuring one.

  6. **The producer's arithmetic is copied, not approximated.** ``bucket_idx``
     and ``_cohort_mce`` are reproduced here; the live proof they still match is
     that the SERVED payload's own buckets reproduce the SERVED headline, which
     :func:`test_cohort_mce_reproduces_a_served_payload` pins against a captured
     body.

The live proof for claim 1 is recorded in ``artifacts/cal-p126/``: the scan
finds ``mutually_exclusive`` to be the ONLY fanning column on every cell of the
curve, which is CAL-P125's one-unit isolation promoted to a measurement.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"
ARTIFACTS = BACKEND.parent / "artifacts" / "cal-p126"


def _load(name: str):
    """Load a script WITHOUT registering it in ``sys.modules``.

    CAL-P121's suite goes red when a sibling is registered and is correct to:
    these modules mutate a shared ``DIMENSIONS`` dict at import time.
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pc = _load("calibration_phantom_curve")

SRC = (SCRIPTS / "calibration_phantom_curve.py").read_text()


# ---------------------------------------------------------------------------
# CLAIM 1 — the scan's all-clear is a proof
# ---------------------------------------------------------------------------
def test_scan_counts_the_three_columns_the_join_drops():
    """``vm_stats`` groups by five, ``ranked_outcomes`` joins on two.

    The three that are grouped-but-not-joined are exactly the ones that can fan
    out, and the scan's ``combos`` must count that triple. Counting two of them
    would declare a cell clean that fans on the third.
    """
    combos = re.search(r"COUNT\(DISTINCT \(([^)]*)\)\) AS combos", pc.SCAN_TAIL)
    assert combos, "the scan lost its combination count"
    named = {c.strip() for c in combos.group(1).split(",")}
    assert named == {"category", "is_grouped", "mutually_exclusive"}, (
        f"the scan counts {named}; the columns ``vm_stats`` GROUPs BY and "
        f"``ranked_outcomes`` does NOT join on are category, is_grouped and "
        f"mutually_exclusive")


def test_scan_groups_on_exactly_the_join_key():
    """``combos`` is counted WITHIN ``(vm_id, source)`` — the join's own key.

    Group on ``vm_id`` alone and a cross-source ``e:`` question reads as fanning
    when it is two clean questions; group on more and the fan-out disappears
    into the grouping.
    """
    assert "FROM virtual_market GROUP BY vm_id, source" in pc.SCAN_TAIL


def test_scan_reads_virtual_market_not_the_filtered_cte():
    """The proof direction only runs one way: a FILTER cannot create a grain.

    ``clean_vms`` is ``vm_stats`` filtered, so combinations counted BEFORE the
    filter bound those counted after. Counting over ``clean_vms`` instead would
    be exact but cost a fold, and counting over anything downstream of
    ``ranked_outcomes`` would count the duplication it is trying to predict.
    """
    assert "FROM virtual_market" in pc.SCAN_TAIL
    for downstream in ("clean_vms", "ranked_outcomes", "normalized", "deduped"):
        assert downstream not in pc.SCAN_TAIL, (
            f"the scan reads {downstream}; its cheapness AND its proof both "
            f"depend on stopping at virtual_market")


def test_scan_separates_the_three_columns():
    """CAL-P125 isolated ``mutually_exclusive`` on ONE unit of ONE cell.

    Lesson 1: a mechanism measured on one unit is a hypothesis until the rail
    scores it. The scan must therefore report the three columns separately so
    the isolation is re-proved per cell rather than inherited.
    """
    for col in ("mexc", "catc", "grpc"):
        assert f"AS {col}" in pc.SCAN_TAIL


def test_phantom_possible_is_true_iff_a_question_fans_out():
    for multi, expected in ((0, False), (1, True), (999, True)):
        row = {"vms": 10, "multi_vms": multi, "markets": 100, "multi_markets": 0,
               "combo_rows": 10 + multi, "mex_vms": multi, "cat_vms": 0,
               "grp_vms": 0}
        assert pc._scan_derived(row)["phantom_possible"] is expected


def test_the_scan_publishes_no_upper_bound_on_the_phantom_row_rate():
    """The correction CAL-P126 had to make to itself, pinned.

    The first version reported ``(combo_rows - vms) / combo_rows`` as
    ``max_phantom_pct``. It is a rate over virtual QUESTIONS and the exact folds
    went straight through it — ``kalshi/hockey`` 25.21% of questions against
    **47.08%** of rows, ``polymarket/basketball`` 13.22% against **43.44%** —
    because the questions that fan out are systematically the big ones.

    Three of four exact cells exceeded it. A number named ``max_*`` that is
    exceeded by the thing it bounds is worse than no number, so it is gone, and
    this test exists so it does not come back wearing the same name.

    **And the market-weighted replacement is not a ceiling either** —
    ``kalshi/basketball`` measured 43.11% of rows against 35.39% of markets
    inside fanning questions. Both real cells are pinned below, because the
    temptation to promote whichever figure happens to be larger into a "bound"
    is exactly what this test exists to block.
    """
    assert "max_phantom_pct" not in SRC, (
        "the question-level fan rate is not an upper bound on the row rate")

    # kalshi/hockey — the question figure sits BELOW the measured 47.08%.
    hockey = pc._scan_derived(
        {"vms": 1825, "multi_vms": 460, "markets": 4388, "multi_markets": 2954,
         "combo_rows": 2285, "mex_vms": 460, "cat_vms": 0, "grp_vms": 0})
    assert hockey["fanned_question_pct"] == 25.21
    assert hockey["fanned_market_pct"] == 67.32
    assert hockey["fanned_question_pct"] < 47.08 < hockey["fanned_market_pct"]

    # kalshi/basketball — BOTH figures sit below the measured 43.11%.
    kb = pc._scan_derived(
        {"vms": 21968, "multi_vms": 1141, "markets": 32358,
         "multi_markets": 11452, "combo_rows": 23109, "mex_vms": 1141,
         "cat_vms": 0, "grp_vms": 0})
    assert kb["fanned_question_pct"] == 5.19
    assert kb["fanned_market_pct"] == 35.39
    assert max(kb["fanned_question_pct"], kb["fanned_market_pct"]) < 43.11, (
        "neither coverage figure bounds the phantom row rate — do not promote "
        "either one into a ceiling")


def test_scan_derived_survives_an_empty_cell():
    d = pc._scan_derived({"vms": 0, "multi_vms": 0, "markets": 0,
                          "multi_markets": 0, "combo_rows": 0})
    assert d["phantom_possible"] is False
    assert d["fanned_question_pct"] == 0.0 and d["fanned_market_pct"] == 0.0


# ---------------------------------------------------------------------------
# CLAIM 2 — an unscannable cell is not a clean cell
# ---------------------------------------------------------------------------
def test_scan_timeout_is_a_status_not_a_zero(monkeypatch):
    """gotcha #53: an empty 200 is a response shape, not an absence.

    A cell whose scan is cancelled must NOT come back as a clean cell with zero
    fanning questions — that is the exact shape of a silent all-clear on the one
    number that decides whether the curve can be trusted.
    """
    def boom(sql, limit=5):
        raise pc.cce.QueryTimeout("statement_timeout")

    monkeypatch.setattr(pc.cce, "db_query", boom)
    r = pc.scan_cell("polymarket", "soccer")
    assert r["status"] == "SCAN_TIMEOUT"
    assert "phantom_possible" not in r, (
        "a cell nobody could scan must not carry a verdict about phantom")


def test_scan_never_retries_a_cancelled_statement(monkeypatch):
    """A retry loop turns a query sitting on the 10 s ceiling into a coin flip.

    ``_sum_over_residues``' rule, inherited: split, never retry at the same
    size — and where a split is not available (the chain, not the aggregate,
    is what costs), report rather than roll again.
    """
    calls = []

    def boom(sql, limit=5):
        calls.append(sql)
        raise pc.cce.QueryTimeout("statement_timeout")

    monkeypatch.setattr(pc.cce, "db_query", boom)
    pc.scan_cell("polymarket", "soccer")
    assert len(calls) == 1, f"the scan issued {len(calls)} statements for one cell"


def test_cell_list_refuses_a_truncated_read(monkeypatch):
    """735 open issues taught this lane that a capped list reads as a whole one.

    The cell list decides what gets measured. A silently truncated one produces
    a sweep that claims to cover the curve and covers its head.
    """
    monkeypatch.setattr(pc.cce, "db_query",
                        lambda sql, limit=500: {"row_count": 500, "rows": [],
                                                "truncated": True})
    with pytest.raises(RuntimeError, match="row cap"):
        pc.cell_list()


def test_futures_sources_are_named_not_inferred():
    """``futures_markets`` holds three sources; the curve serves seven.

    The four ``odds_api*`` sources publish 137,829 outcomes (15.1%) through a
    chain with no ``clean_vms`` in it. Scanning them returns zero rows, and zero
    rows must read as OUT OF SCOPE rather than as CLEAN.
    """
    assert set(pc.FUTURES_SOURCES) == {"polymarket", "kalshi", "datagolf"}
    assert "odds_api" not in pc.FUTURES_SOURCES


# ---------------------------------------------------------------------------
# CLAIM 3 — de-duplication is measured, not assumed
# ---------------------------------------------------------------------------
def test_cell_tail_counts_every_way_two_copies_can_disagree():
    """Bucket, price, winner and price_moved — the four that change the curve.

    Drop any one and a real incoherence is published as a clean re-weighting.
    """
    assert set(pc.COHERENCE) == {"incoherent_bucket", "incoherent_price",
                                 "incoherent_winner", "incoherent_price_moved"}
    for name in pc.COHERENCE:
        assert f"AS {name}" in pc.CELL_TAIL


def test_cell_tail_attributes_one_whole_outcome_across_its_copies():
    """``SUM(1/copies)`` is ``COUNT(DISTINCT outcome_id)`` when copies agree.

    And when they do not, it is a proportional split rather than a silent pick.
    The guard is that the divisor is the per-outcome copy count computed over
    the SAME bucketed set — a divisor computed anywhere else would not sum to 1.
    """
    assert "SUM(1.0 / c.copies)" in pc.CELL_TAIL
    assert "FROM bucketed GROUP BY outcome_id" in pc.CELL_TAIL


def test_cell_tail_uses_the_producers_own_bucket_expression():
    """A bucket boundary off by one publishes a real delta that is arithmetic.

    ``LEAST(FLOOR(p * 10)::int, 9)`` is copied from ``precompute_calibration``;
    this asserts the copy, and the served-payload test below asserts the
    original still matches.
    """
    producer = (BACKEND / "app" / "tasks" / "precompute_calibration.py").read_text()
    expr = "LEAST(FLOOR(adj_opening_probability * 10)::int, 9)"
    assert expr in producer, "the producer's bucket expression moved"
    assert expr in pc.CELL_TAIL


def test_cell_tail_keys_on_the_served_bucket_key():
    """``(bucket_idx, source, category, price_moved)`` — the payload's own key.

    This is what lets one cell be substituted into the served aggregate instead
    of rebuilding the other 102. Change the key and the substitution silently
    matches nothing, which reads as a delta of zero.
    """
    assert pc.BUCKET_KEY == ("bucket_idx", "source", "category", "price_moved")
    assert "GROUP BY 1, 2, 3, 4" in pc.CELL_TAIL


def test_merge_adds_units_rather_than_replacing_them():
    acc: dict = {}
    row = {"bucket_idx": 3, "source": "polymarket", "category": "cricket",
           "price_moved": True, "n_ship": 10.0, "w_ship": 4.0, "s_ship": 3.5,
           "n_dedup": 5.0, "w_dedup": 2.0, "s_dedup": 1.75, "rows_duplicated": 5,
           "incoherent_bucket": 0, "incoherent_price": 0, "incoherent_winner": 0,
           "incoherent_price_moved": 0}
    pc._merge(acc, [dict(row), dict(row)])
    (slot,) = acc.values()
    assert slot["n_ship"] == 20.0 and slot["n_dedup"] == 10.0
    assert slot["rows_duplicated"] == 10


def test_a_single_virtual_question_that_will_not_fit_is_raised_by_name():
    """Splitting a ``vm_id`` would split its own duplicate copies apart.

    That is the one failure mode that would make this instrument report the
    phantom as ABSENT, so it must raise rather than approximate.
    """
    fn = pc._unit_rows.__code__
    body = SRC[SRC.index("def _unit_rows"):SRC.index("#: Set by :func:`cell_over_roster`")]
    assert "MUST NOT be split" in body
    assert "raise RuntimeError" in body
    assert fn.co_argcount == 5


def test_cell_report_phantom_is_shipped_minus_distinct():
    acc = {}
    pc._merge(acc, [{"bucket_idx": 0, "source": "kalshi", "category": "golf",
                     "price_moved": False, "n_ship": 100.0, "w_ship": 40.0,
                     "s_ship": 30.0, "n_dedup": 80.0, "w_dedup": 32.0,
                     "s_dedup": 24.0, "rows_duplicated": 20,
                     "incoherent_bucket": 0, "incoherent_price": 0,
                     "incoherent_winner": 0, "incoherent_price_moved": 0}])
    rep = pc.cell_report(acc, "kalshi", "golf", "direct")
    assert rep["published_rows"] == 100
    assert rep["distinct_outcomes"] == 80
    assert rep["phantom_rows"] == 20
    assert rep["phantom_pct"] == 20.0
    assert rep["coherent"] is True


def test_cell_report_flags_incoherent_copies():
    acc = {}
    pc._merge(acc, [{"bucket_idx": 0, "source": "kalshi", "category": "golf",
                     "price_moved": False, "n_ship": 10.0, "w_ship": 4.0,
                     "s_ship": 3.0, "n_dedup": 8.0, "w_dedup": 3.2,
                     "s_dedup": 2.4, "rows_duplicated": 2,
                     "incoherent_bucket": 1, "incoherent_price": 2,
                     "incoherent_winner": 0, "incoherent_price_moved": 0}])
    rep = pc.cell_report(acc, "kalshi", "golf", "direct")
    assert rep["coherent"] is False
    assert rep["coherence"]["incoherent_price"] == 2


# ---------------------------------------------------------------------------
# CLAIM 4/5 — the substitution is a ratio, and winners carry their own
# ---------------------------------------------------------------------------
def _cell(bucket_idx, source, category, pm, ship, dedup):
    n_s, w_s, s_s = ship
    n_d, w_d, s_d = dedup
    return {"cell": f"{source}/{category}", "source": source, "category": category,
            "buckets": [{"bucket_idx": bucket_idx, "source": source,
                         "category": category, "price_moved": pm,
                         "n_ship": n_s, "w_ship": w_s, "s_ship": s_s,
                         "n_dedup": n_d, "w_dedup": w_d, "s_dedup": s_d,
                         "rows_duplicated": 0, "incoherent_bucket": 0,
                         "incoherent_price": 0, "incoherent_winner": 0,
                         "incoherent_price_moved": 0}]}


def test_substitution_cancels_a_uniform_rail_shortfall():
    """The rail reads a cell 10% short across the board; the delta must be 0.

    This is claim 4 in one assertion. If the rail's ABSOLUTE numbers were
    substituted, this cell would report a 10% loss of n as phantom damage.
    """
    payload = [{"bucket_idx": 5, "source": "polymarket", "category": "cricket",
                "price_moved": True, "n": 1000, "winners": 500, "sum_prob": 550.0}]
    # rail sees 900/450/495 as shipped and the SAME 900/450/495 de-duplicated:
    # it found no phantom, it is simply 10% short.
    cells = [_cell(5, "polymarket", "cricket", True,
                   (900.0, 450.0, 495.0), (900.0, 450.0, 495.0))]
    out, stats = pc.substitute(payload, cells)
    assert stats["substituted"] == 1
    assert out[0]["n"] == pytest.approx(1000.0)
    assert out[0]["winners"] == pytest.approx(500.0)
    assert out[0]["sum_prob"] == pytest.approx(550.0)


def test_winners_scale_on_the_winner_ratio_not_the_row_ratio():
    """Claim 5, and it is the one that decides whether any delta exists.

    A bucket where the duplicated rows are ALL winners: 100 rows / 60 winners
    shipped, 50 distinct outcomes / 10 winners de-duplicated. The actual rate
    must fall from 0.60 to 0.20. Scale winners by the ROW ratio and it stays at
    0.60 and the phantom looks harmless.
    """
    payload = [{"bucket_idx": 5, "source": "polymarket", "category": "cricket",
                "price_moved": True, "n": 100, "winners": 60, "sum_prob": 55.0}]
    cells = [_cell(5, "polymarket", "cricket", True,
                   (100.0, 60.0, 55.0), (50.0, 10.0, 27.5))]
    out, _ = pc.substitute(payload, cells)
    assert out[0]["n"] == pytest.approx(50.0)
    assert out[0]["winners"] == pytest.approx(10.0)
    assert out[0]["winners"] / out[0]["n"] == pytest.approx(0.20)


def test_an_unmeasured_bucket_is_carried_through_untouched():
    payload = [{"bucket_idx": 5, "source": "kalshi", "category": "golf",
                "price_moved": True, "n": 100, "winners": 60, "sum_prob": 55.0}]
    out, stats = pc.substitute(payload, [])
    assert stats["substituted"] == 0 and stats["untouched"] == 1
    assert out[0]["n"] == 100 and out[0]["winners"] == 60


def test_a_bucket_the_rail_invents_is_reported_not_dropped():
    """Two populations disagreeing about which buckets EXIST is a bigger finding
    than any ratio, so it may not be swallowed by a dict lookup that misses."""
    payload = [{"bucket_idx": 5, "source": "kalshi", "category": "golf",
                "price_moved": True, "n": 100, "winners": 60, "sum_prob": 55.0}]
    cells = [_cell(9, "kalshi", "golf", True, (10.0, 5.0, 9.0), (10.0, 5.0, 9.0))]
    _, stats = pc.substitute(payload, cells)
    assert stats["rail_only"] == [[9, "kalshi", "golf", True]]


def test_a_zero_shipped_bucket_does_not_divide_by_zero():
    payload = [{"bucket_idx": 5, "source": "kalshi", "category": "golf",
                "price_moved": True, "n": 100, "winners": 0, "sum_prob": 55.0}]
    cells = [_cell(5, "kalshi", "golf", True, (10.0, 0.0, 9.0), (10.0, 0.0, 9.0))]
    out, _ = pc.substitute(payload, cells)
    assert out[0]["winners"] == 0.0


# ---------------------------------------------------------------------------
# CLAIM 6 — the producer's arithmetic, copied and pinned against production
# ---------------------------------------------------------------------------
def test_cohort_mce_is_an_unweighted_mean_over_bucket_indices():
    """It is NOT n-weighted, and that is why a re-weighting can move it.

    ``_compute_horizon_mce`` next door IS n-weighted; copying the wrong one
    would produce a headline that reproduces nothing and a delta that means
    nothing. Two buckets, one huge and well calibrated, one tiny and 50 points
    out: the unweighted answer is 25.0, the weighted one is near 0.
    """
    buckets = [
        {"bucket_idx": 0, "price_moved": True, "n": 1_000_000,
         "winners": 500_000, "sum_prob": 500_000.0},
        {"bucket_idx": 9, "price_moved": True, "n": 2, "winners": 2,
         "sum_prob": 1.0},
    ]
    assert pc.cohort_mce(buckets, True) == 25.0


def test_a_null_price_moved_bucket_is_in_NEITHER_cohort():
    """The bug this suite actually caught, pinned so it cannot come back.

    ``price_moved`` is NULL on 890 of the served payload's 1,963 buckets,
    carrying exactly 137,829 outcomes — the four ``odds_api*`` sources to the
    row. The producer compares ``b.get("price_moved") != pred``, so a NULL
    bucket joins neither cohort. This file first wrote it as
    ``bool(b.get("price_moved")) != pred``, which swept every one of those
    buckets into the ``False`` cohort and moved ``mce_opening_price`` from 1.54
    to 1.06 — a reproduction that was wrong by half a point while still
    printing a clean, plausible table.

    It is also the finding underneath the headline delta: the published number
    is an average over the futures half only, which is exactly the half that
    carries 16-CAL.
    """
    buckets = [
        {"bucket_idx": 0, "price_moved": None, "n": 1_000_000,
         "winners": 1_000_000, "sum_prob": 0.0},
        {"bucket_idx": 0, "price_moved": False, "n": 10, "winners": 5,
         "sum_prob": 5.0},
    ]
    assert pc.cohort_mce(buckets, False) == 0.0, (
        "a NULL price_moved bucket leaked into the opening-price cohort")
    assert pc.cohort_mce(buckets, True) is None


def test_substitution_keys_on_the_raw_price_moved():
    """Same defect, the other side of it: keying on ``bool(price_moved)`` would
    match a NULL payload bucket onto a measured ``False`` one and rescale a
    bucket the rail never looked at."""
    payload = [{"bucket_idx": 5, "source": "kalshi", "category": "golf",
                "price_moved": None, "n": 100, "winners": 60, "sum_prob": 55.0}]
    cells = [_cell(5, "kalshi", "golf", False, (100.0, 60.0, 55.0),
                   (50.0, 10.0, 27.5))]
    out, stats = pc.substitute(payload, cells)
    assert stats["substituted"] == 0 and stats["untouched"] == 1
    assert out[0]["n"] == 100 and out[0]["winners"] == 60


def test_cohort_mce_splits_strictly_on_price_moved():
    buckets = [
        {"bucket_idx": 0, "price_moved": True, "n": 10, "winners": 10,
         "sum_prob": 5.0},
        {"bucket_idx": 0, "price_moved": False, "n": 10, "winners": 5,
         "sum_prob": 5.0},
    ]
    assert pc.cohort_mce(buckets, True) == 50.0
    assert pc.cohort_mce(buckets, False) == 0.0
    assert pc.cohort_mce([], True) is None


@pytest.mark.skipif(not (ARTIFACTS / "payload-q268.json").exists(),
                    reason="the captured payload is the live proof, not a fixture")
def test_cohort_mce_reproduces_a_served_payload():
    """THE live proof for claim 6, and the reason the substitution is legal.

    The served payload publishes every bucket it aggregated, so its own headline
    must be recomputable from them. If this ever goes red, the producer's
    aggregation has changed shape and every delta this instrument reports is
    against a number it can no longer rebuild — which is the failure mode that
    matters, because the delta would still print.
    """
    payload = json.loads((ARTIFACTS / "payload-q268.json").read_text())
    buckets = [{"bucket_idx": b["bucket_idx"], "price_moved": b["price_moved"],
                "n": b["n"], "winners": b["winners"], "sum_prob": b["sum_prob"]}
               for b in payload["buckets"]]
    assert pc.cohort_mce(buckets, True) == payload["mce_closing_line"]
    assert pc.cohort_mce(buckets, False) == payload["mce_opening_price"]


@pytest.mark.skipif(not (ARTIFACTS / "payload-q268.json").exists(),
                    reason="the captured payload is the live proof, not a fixture")
def test_headline_with_no_cells_measured_moves_nothing():
    """The null case, and it is a real guard: a substitution that quietly
    mangles untouched buckets would show up here as a delta out of nowhere."""
    payload = json.loads((ARTIFACTS / "payload-q268.json").read_text())
    h = pc.headline(payload, [])
    assert h["reproduction_exact"] is True
    assert h["delta_closing"] == 0.0 and h["delta_opening"] == 0.0


# ---------------------------------------------------------------------------
# Rail hygiene — the conventions this lane pays for when they are broken
# ---------------------------------------------------------------------------
def test_this_module_is_not_left_in_sys_modules():
    """CAL-P123's rule. A sibling in ``sys.modules`` leaks its dimension
    registrations into every other test in the pytest process."""
    assert "calibration_phantom_curve" not in sys.modules


def test_it_adds_no_dimensions_of_its_own():
    """This file measures the population; it does not attribute it. Registering
    a dimension here would change what ``--by`` means for every importer."""
    assert "DIMENSIONS[" not in SRC
    assert "DIMENSIONS.setdefault" not in SRC
    assert "ADDED_DIMENSIONS" not in SRC


def test_it_writes_nothing_to_the_database():
    """Ruling 134: a read-only instrument, and 0-PHANTOM option (a) is
    explicitly the read-only option. Every statement it issues is a SELECT."""
    for verb in ("INSERT", "UPDATE ", "DELETE", "CREATE ", "ALTER ", "DROP "):
        assert verb not in pc.SCAN_TAIL.upper()
        assert verb not in pc.CELL_TAIL.upper()


def test_it_does_not_reimplement_the_population():
    """It drives ``_calibration_population_ctes``; it does not copy it.

    A copy would be a second population that agrees with the first until the
    day it does not, which is how a self-check comes to prove the rail and not
    the population (CAL-P125's lesson 9).
    """
    assert "_calibration_population_ctes" in SRC
    assert "market_info AS" not in SRC
    assert "vm_stats AS" not in SRC


def test_the_frozen_file_is_imported_and_never_edited():
    """Ruling 009 freezes commits to ``precompute_calibration.py``."""
    assert "from app.tasks.precompute_calibration import" in SRC
