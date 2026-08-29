"""CAL-P125 — guards for the exhaustive exclusion-rule search.

CAL-P123's lesson 7: *"NO RULE FOUND" and "NO RULE EXISTS" are different claims,
and the second one is cheap.* This instrument licenses the second claim, so the
way it fails is not "it prints a wrong ECE" — it is **"it prints a refusal that
was never earned"**, which is the same class as gotcha #53.

Three ways that can happen, and every test below is aimed at one of them:

  1. **Silent truncation of the search.** A powerset that was sampled, capped or
     cut by a row floor, reported as though it were exhaustive.
  2. **Pooling done wrong.** ECE is `sum |winrate_b - meanprice_b| * n_b / n`
     over BUCKETS. Average the per-class ECEs instead of re-pooling the buckets
     and every multi-arm rule is mis-scored — always in the direction of
     understating the best rule, because it forbids the cancellation that is the
     only reason a multi-arm rule beats its best single arm.
  3. **Ranking on the pooled number.** An exhaustive search over 2^k subsets is
     an exhaustive search for an overfit, and the pooled ECE is the thing it
     overfits. With a holdout present the ranking must use the WORSE half.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rs = _load("calibration_rule_search")


def _bins(*triples):
    """``{bucket: {n, w, sp}}`` from ``(bucket, n, winners, sum_prob)``."""
    return {str(b): {"n": n, "w": w, "sp": sp} for b, n, w, sp in triples}


#: Two classes that are each badly calibrated and CANCEL when pooled: in
#: bucket 5, A is 100 rows priced 0.5 with 100 winners and B is 100 rows priced
#: 0.5 with 0 winners. Each alone is 50 pp of error; together they are 0.
CANCELLING = {
    "A": _bins((5, 100, 100, 50.0)),
    "B": _bins((5, 100, 0, 50.0)),
}


# ==========================================================================
# 2 — the pooling
# ==========================================================================

def test_pooling_merges_buckets_before_taking_the_absolute_value():
    """The whole reason a multi-arm rule can beat its best single arm."""
    assert rs.score(CANCELLING, ["A"])[1] == 50.0
    assert rs.score(CANCELLING, ["B"])[1] == 50.0
    assert rs.score(CANCELLING, ["A", "B"])[1] == 0.0


def test_the_search_finds_the_cancelling_pair_a_greedy_pass_would_miss():
    """Dropping 'the classes with big numbers' is exactly wrong here: both
    classes have the worst possible ECE and keeping BOTH is the answer."""
    res = rs.search(CANCELLING, None, bar=3.0, min_rows=1, min_share=0.0)
    assert res["ranked"][0]["keep"] == ["A", "B"]
    assert res["ranked"][0]["ece"] == 0.0
    assert len(res["passing"]) == 1


def test_score_returns_n_ece_and_gap():
    n, ece, gap = rs.score({"A": _bins((5, 10, 5, 5.0))}, ["A"])
    assert n == 10 and ece == 0.0 and gap == 0.0


def test_gap_is_signed_and_ece_is_not():
    over = {"A": _bins((8, 100, 0, 80.0))}
    n, ece, gap = rs.score(over, ["A"])
    assert ece == 80.0 and gap == 80.0
    under = {"A": _bins((1, 100, 100, 20.0))}
    n, ece, gap = rs.score(under, ["A"])
    assert ece == 80.0 and gap == -80.0


def test_an_empty_keep_set_is_zero_rows_not_a_crash():
    assert rs.score(CANCELLING, []) == (0, None, None)


def test_score_ignores_classes_outside_the_keep_set():
    n, _, _ = rs.score(CANCELLING, ["A"])
    assert n == 100


# ==========================================================================
# 1 — the search is exhaustive, or it refuses
# ==========================================================================

def test_subsets_are_exhaustive_and_non_empty():
    got = list(rs.subsets(["a", "b", "c"]))
    assert len(got) == 7
    assert set(map(frozenset, got)) == {
        frozenset(s) for s in
        [("a",), ("b",), ("c",), ("a", "b"), ("a", "c"), ("b", "c"),
         ("a", "b", "c")]}


def test_subsets_are_ordered_smallest_first():
    """Ties break toward fewer arms: every arm is a sentence a reader has to
    accept, so a two-arm and a five-arm rule at the same ECE are not equal."""
    sizes = [len(s) for s in rs.subsets(["a", "b", "c", "d"])]
    assert sizes == sorted(sizes)


def test_too_many_classes_is_refused_by_number_not_sampled():
    """A sampled search reporting '0 under the bar' is the false all-clear this
    whole lane exists to prevent."""
    big = {f"c{i}": _bins((5, 10, 5, 5.0)) for i in range(rs.MAX_CLASSES + 1)}
    with pytest.raises(SystemExit, match=r"Refusing rather than sampling"):
        rs.search(big, None, bar=3.0, min_rows=1, min_share=0.0)


def test_the_row_floor_is_reported_so_a_bounded_search_is_visible(capsys):
    res = rs.search(CANCELLING, None, bar=3.0, min_rows=150, min_share=0.0)
    rs.render(res, top=5)
    out = capsys.readouterr().out
    assert "retaining >= 150 rows" in out
    assert f"of {res['searched']}" in out


def test_the_binding_floor_is_the_larger_of_rows_and_share():
    res = rs.search(CANCELLING, None, bar=3.0, min_rows=10, min_share=0.5)
    assert res["floor_rows"] == 100
    res = rs.search(CANCELLING, None, bar=3.0, min_rows=150, min_share=0.1)
    assert res["floor_rows"] == 150


def test_subsets_below_the_floor_are_excluded_from_the_count_not_from_the_bar():
    """The refusal sentence says 'every subset retaining >= N rows'. If the
    floor silently changed which subsets were searched without changing the
    reported N, the sentence would be false."""
    res = rs.search(CANCELLING, None, bar=3.0, min_rows=150, min_share=0.0)
    assert res["searched"] == 1
    assert res["floor_rows"] == 150


def test_the_refusal_sentence_appears_only_when_nothing_passes(capsys):
    res = rs.search({"A": _bins((8, 500, 0, 400.0))}, None, bar=3.0,
                    min_rows=1, min_share=0.0)
    rs.render(res, top=3)
    assert "NO RULE EXISTS" in capsys.readouterr().out

    rs.render(rs.search(CANCELLING, None, bar=3.0, min_rows=1, min_share=0.0), 3)
    assert "NO RULE EXISTS" not in capsys.readouterr().out


def test_the_refusal_says_it_is_about_one_partition(capsys):
    """CAL-P123 lesson 7: pooling can cancel opposite-signed arms, so a refusal
    on one partition is not a refusal."""
    res = rs.search({"A": _bins((8, 500, 0, 400.0))}, None, bar=3.0,
                    min_rows=1, min_share=0.0)
    rs.render(res, top=3)
    out = capsys.readouterr().out
    assert "ONE partition" in out and "second" in out


# ==========================================================================
# 3 — the holdout outranks the pooled number
# ==========================================================================

#: 'A' is PERFECT pooled and 20 pp out on each half — it under-predicts on OLD
#: and over-predicts on NEW by exactly as much, so the halves cancel. 'B' is
#: mediocre and stable at 2 pp.
#:
#: This is the overfit an exhaustive search actually produces: not a subset that
#: is good on one half and bad on the other, but one whose errors cancel in the
#: pooled number the search is ranking on. Pooled ranking puts A first (0.0 vs
#: 2.0); worst-half ranking puts B first (20.0 vs 2.0). B is the right answer.
OVERFIT = {"A": _bins((5, 200, 100, 100.0)), "B": _bins((5, 200, 104, 100.0))}
OVERFIT_HALVES = {
    "OLD": {"A": _bins((5, 100, 70, 50.0)), "B": _bins((5, 100, 52, 50.0))},
    "NEW": {"A": _bins((5, 100, 30, 50.0)), "B": _bins((5, 100, 52, 50.0))},
}


def test_ranking_uses_the_worse_half_when_a_holdout_is_present():
    res = rs.search(OVERFIT, OVERFIT_HALVES, bar=3.0, min_rows=1, min_share=0.0)
    a = next(r for r in res["ranked"] if r["keep"] == ["A"])
    b = next(r for r in res["ranked"] if r["keep"] == ["B"])
    assert a["ece"] == 0.0 and a["worst_half"] == 20.0
    assert b["ece"] == 2.0 and b["worst_half"] == 2.0
    assert res["ranked"][0]["keep"] == ["B"], "the overfit was ranked first"


def test_a_subset_that_passes_pooled_but_fails_on_a_half_does_not_pass():
    res = rs.search(OVERFIT, OVERFIT_HALVES, bar=3.0, min_rows=1, min_share=0.0)
    assert ["A"] not in [r["keep"] for r in res["passing"]]
    assert ["B"] in [r["keep"] for r in res["passing"]]


def test_both_halves_are_reported_per_subset():
    res = rs.search(OVERFIT, OVERFIT_HALVES, bar=3.0, min_rows=1, min_share=0.0)
    rec = next(r for r in res["ranked"] if r["keep"] == ["A"])
    assert rec["OLD"]["ece"] == 20.0 and rec["OLD"]["gap"] == -20.0
    assert rec["NEW"]["ece"] == 20.0 and rec["NEW"]["gap"] == +20.0
    # ...and the pooled number, which is what the search would have ranked on,
    # shows neither.
    assert rec["ece"] == 0.0


def test_a_class_absent_from_one_half_is_skipped_not_crashed():
    halves = {"OLD": {"A": _bins((5, 10, 5, 5.0))}, "NEW": {}}
    res = rs.search({"A": _bins((5, 20, 10, 10.0))}, halves, bar=3.0,
                    min_rows=1, min_share=0.0)
    rec = res["ranked"][0]
    assert rec["OLD"]["n"] == 10
    assert rec["NEW"]["n"] == 0 and rec["NEW"]["ece"] is None


def test_without_a_holdout_the_pooled_number_ranks():
    res = rs.search(OVERFIT, None, bar=3.0, min_rows=1, min_share=0.0)
    assert res["ranked"][0]["worst_half"] is None if "worst_half" in res["ranked"][0] \
        else True
    assert res["ranked"][0]["keep"] == ["A"]


# ==========================================================================
# Loading, reporting, and reuse across both rails
# ==========================================================================

def test_it_loads_either_rails_out_file(tmp_path):
    """``calibration_cell_exact`` and ``calibration_whole_vm_fold`` write the
    same ``by_key`` / ``halves`` shape deliberately, so a rule benched on one
    can be re-benched on the other without touching this file."""
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"by_key": CANCELLING, "halves": None}))
    by_key, halves = rs.load_partition(str(p))
    assert set(by_key) == {"A", "B"} and halves is None


def test_a_file_with_no_by_key_is_refused_by_name(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"exact": {"n": 1}}))
    with pytest.raises(SystemExit, match="has no 'by_key'"):
        rs.load_partition(str(p))


def test_the_out_file_carries_the_full_ranking_not_only_the_winners():
    """A reviewer's first question is 'how close was the next one', and a file
    holding only passes cannot answer it."""
    src = (SCRIPTS / "calibration_rule_search.py").read_text()
    assert '"ranked": rows' in src
    assert '"passing": passing' in src


def test_the_report_states_the_cell_before_any_rule():
    res = rs.search(CANCELLING, None, bar=3.0, min_rows=1, min_share=0.0)
    assert res["total"] == {"n": 200, "ece": 0.0, "gap": 0.0}


def test_dropped_counts_are_relative_to_the_whole_cell():
    res = rs.search(CANCELLING, None, bar=3.0, min_rows=1, min_share=0.0)
    a = next(r for r in res["ranked"] if r["keep"] == ["A"])
    assert a["dropped"] == 100 and a["dropped_pct"] == 50.0


def test_it_touches_neither_the_network_nor_the_database():
    """It reads a fold's output. A rule search that could re-query would be a
    second rail, and a second rail is a second population."""
    src = (SCRIPTS / "calibration_rule_search.py").read_text()
    for banned in ("db_query", "urllib", "requests", "ADMIN_TOKEN",
                   "BAINLUCK_API", "psycopg", "sqlalchemy"):
        assert banned not in src, banned


def test_it_does_not_reimplement_the_bar():
    """The bar is an argument, not a constant this file gets to pick."""
    src = (SCRIPTS / "calibration_rule_search.py").read_text()
    assert not re.search(r"^BAR\s*=", src, re.M)
    assert 'default=3.0' in src
