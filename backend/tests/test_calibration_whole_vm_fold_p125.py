"""CAL-P125 — guards for the whole-virtual-market fold rail.

WHAT THIS RAIL CLAIMS, AND THEREFORE WHAT BREAKING IT LOOKS LIKE
------------------------------------------------------------------
``calibration_cell_exact`` chunks on ``fm.id`` and re-derives ``virtual_market``
per chunk, so ``group_sizes`` / ``event_sizes`` are counted over a FILTERED
``market_info`` and a cluster split across a chunk boundary silently collapses
below the ``>= 3`` gate — re-assigning its markets to ``m:<market_id>``, a
different question identity with a different representative and a different
bucket. Measured on ``polymarket/basketball``, curve ``q268``: **8,426 of 13,135
published rows, −35.85%**.

This rail replays the producer's OWN frozen-roster path instead
(``_calibration_population_ctes(frozen_vm_roster=True)``), cut by the producer's
OWN planner (``plan_units``). Its correctness is by construction — but only if
four structural premises hold, and every one of them can be broken by an edit
that leaves the instrument printing a complete, plausible, well-formed table:

  1. Stage B really is on the frozen path (``frozen_vm_roster``), not the global
     one. Break it and this rail becomes the id-range rail with extra steps.
  2. The Stage A hash filter is on the OUTER select. Push it into
     ``market_info`` and it becomes exactly the filtered-population defect it
     exists to remove.
  3. Both refinements are EXACT — ``x % 2n in {k, k+n}`` iff ``x % n == k``, and
     ``bucket_of(v, 2B) % B == bucket_of(v, B)``. Break either and a ``vm_id``
     lands in two chunks (double-counted) or in none (silently dropped).
  4. A ``vm_id`` is NEVER split, and the one case that cannot be measured is
     raised BY NAME rather than approximated.

Most of these tests are therefore SILENT-failure guards in the gotcha #53 sense:
the fold keeps working and starts lying. The live proof that the premises hold
in production is the SELF-CHECK, and it is recorded in
``artifacts/cal-p125/``: ``polymarket/cricket`` reproduces the published cell at
**+0.00%** on this rail against −0.18% on the id-range rail.
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


def _load(name: str):
    """Load a script WITHOUT registering it in ``sys.modules``.

    CAL-P121's suite goes red when a sibling script is registered, and it is
    correct to: the fold modules mutate a shared ``DIMENSIONS`` dict on import.
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wvf = _load("calibration_whole_vm_fold")


def _roster(*triples):
    return [wvf.RosterRow(m, s, v, g) for m, s, v, g in triples]


SAMPLE = _roster(
    (1, "polymarket", "g:polymarket:99", True),
    (2, "polymarket", "g:polymarket:99", True),
    (3, "polymarket", "g:polymarket:99", True),
    (4, "polymarket", "m:4", False),
    (5, "polymarket", "e:7", True),
)


def _unit_sql(rows, dim="none", holdout=None, buckets=4):
    assignment = {r.market_id: (r.vm_id, r.is_grouped) for r in rows}
    unit = wvf.plan_units(rows, buckets=buckets)[0]
    return wvf.unit_sql(unit, assignment, dim, holdout)


# ==========================================================================
# PREMISE 1 — Stage B is on the FROZEN path
# ==========================================================================

def test_stage_b_injects_the_frozen_roster():
    assert "frozen_vm_roster AS (" in _unit_sql(SAMPLE)


def test_stage_b_does_not_re_derive_group_or_event_sizes():
    """THE claim of this whole file.

    ``group_sizes`` / ``event_sizes`` counted over a chunk-filtered
    ``market_info`` is the −35.85% defect. On the frozen path the producer
    deletes both CTEs outright; if they reappear here the rail has silently
    reverted to re-deriving question identity per chunk.
    """
    sql = _unit_sql(SAMPLE)
    assert "group_sizes AS (" not in sql
    assert "event_sizes AS (" not in sql


def test_the_id_range_rail_really_does_re_derive_them():
    """The differential. Without it, test above could pass on both rails.

    If ``calibration_cell_exact`` ever moves to the frozen path too, this test
    fails and says so — at which point this rail is redundant rather than
    wrong, and that is a conversation, not a silent overlap.
    """
    cce_sql = wvf.cce.cell_sql("polymarket", "basketball", 0, 1_000_000, "none")
    assert "group_sizes AS (" in cce_sql
    assert "frozen_vm_roster" not in cce_sql


def test_stage_b_scopes_market_info_with_the_producers_own_constant():
    """Not a hand-written ``fm.id = ANY(...)``. CAL-P115's rule: an equal copy drifts."""
    from app.tasks.precompute_calibration import VM_ROSTER_MARKET_INFO_EXTRA
    marker = VM_ROSTER_MARKET_INFO_EXTRA.split(":")[0].strip()
    assert marker and marker in _unit_sql(SAMPLE)


def test_all_three_roster_parameters_are_substituted():
    from app.tasks.precompute_calibration import (
        VM_ROSTER_IS_GROUPED_PARAM,
        VM_ROSTER_MARKET_IDS_PARAM,
        VM_ROSTER_VM_IDS_PARAM,
    )
    sql = _unit_sql(SAMPLE)
    for p in (VM_ROSTER_MARKET_IDS_PARAM, VM_ROSTER_VM_IDS_PARAM,
              VM_ROSTER_IS_GROUPED_PARAM):
        assert f":{p}" not in sql, f"{p} reached the server as a literal bind"


def test_an_unsubstituted_bind_raises_rather_than_reaching_the_server(monkeypatch):
    """A ``:name`` reaching PG fails with a syntax error that reads like a guard
    refusal, and a chunked sweep reads a refused chunk as an empty range."""
    monkeypatch.setattr(wvf, "_bigint_array", lambda vals: ":vm_roster_market_ids")
    with pytest.raises(RuntimeError, match="was not substituted"):
        _unit_sql(SAMPLE)


def test_the_three_roster_arrays_are_parallel_and_market_ordered():
    """``unnest(a, b, c)`` zips positionally — a mis-ordered array silently
    assigns one market's question identity to another."""
    rows = SAMPLE
    assignment = {r.market_id: (r.vm_id, r.is_grouped) for r in rows}
    unit = max(wvf.plan_units(rows, buckets=4), key=lambda u: len(u.market_ids))
    sql = wvf.unit_sql(unit, assignment, "none", None)

    ids = re.search(r"CAST\(ARRAY\[([^\]]*)\] AS bigint\[\]\)", sql).group(1)
    vms = re.search(r"CAST\(ARRAY\[([^\]]*)\] AS text\[\]\)", sql).group(1)
    got_ids = [int(x) for x in ids.split(",")]
    got_vms = [x.strip().strip("'") for x in vms.split(",")]

    assert got_ids == list(unit.market_ids)
    assert got_vms == [assignment[m][0] for m in unit.market_ids]
    assert len(got_ids) == len(got_vms)


# ==========================================================================
# PREMISE 2 — the Stage A hash filter is on the OUTER select
# ==========================================================================

def test_stage_a_filters_after_from_virtual_market_not_inside_market_info():
    sql = wvf.stage_a_sql("polymarket", "basketball", 64, 3)
    at_vm = sql.index("FROM virtual_market")
    at_hash = sql.index("HASHTEXT")
    assert at_hash > at_vm, "the hash filter moved into the population CTEs"


def test_stage_a_market_info_is_scoped_only_by_source_and_category():
    """``market_info``'s WHERE is what group/event sizes are counted over. Any
    extra predicate there changes the sizes, which changes ``vm_id``."""
    sql = wvf.stage_a_sql("polymarket", "basketball", 64, 3)
    where = sql[sql.index("FROM futures_markets fm"):sql.index("),", sql.index("FROM futures_markets fm"))]
    assert "HASHTEXT" not in where
    assert "fm.id >=" not in where and "fm.id <" not in where
    assert "fm.source = 'polymarket'" in where
    assert "llm_sport_category" in where


def test_stage_a_selects_only_from_virtual_market():
    """The cheapness argument: PG does not execute an unreferenced ``WITH``
    subquery, so everything below ``virtual_market`` is planned away. Selecting
    from ``deduped`` here would make Stage A cost a full fold."""
    sql = wvf.stage_a_sql("polymarket", "basketball", 8, 0)
    tail = sql[sql.rindex("\nSELECT "):]
    assert "FROM virtual_market" in tail
    assert "deduped" not in tail


def test_stage_a_casts_hashtext_to_bigint_before_abs():
    """``hashtext`` returns int4 and ``abs(-2147483648)`` overflows. Without the
    cast one residue class in billions errors out and reads as empty."""
    sql = wvf.stage_a_sql("polymarket", "basketball", 8, 0)
    assert re.search(r"ABS\(HASHTEXT\(vm_id\)::bigint\)", sql)


def test_stage_a_hashes_the_vm_id_not_the_market_id():
    """Hashing ``market_id`` would scatter a cluster across residue classes —
    which is the id-range rail's defect wearing a hash."""
    sql = wvf.stage_a_sql("polymarket", "basketball", 8, 0)
    assert "HASHTEXT(vm_id)" in sql
    assert "HASHTEXT(market_id" not in sql


@pytest.mark.parametrize("bad", ["o'brien", "x'; DROP TABLE futures_markets; --"])
def test_stage_a_and_arrays_escape_quotes(bad):
    assert "''" in wvf._text_array([bad])


# ==========================================================================
# PREMISE 3 — both refinements are EXACT
# ==========================================================================

@pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 64])
def test_residue_split_is_an_exact_refinement(n):
    """``x % 2n in {k, k+n}`` iff ``x % n == k`` — for every k and every x.

    This is the property that lets a truncated Stage A chunk be halved. Lose it
    and a ``vm_id`` is read twice or not at all, and the roster still looks
    like a plausible roster.
    """
    for k in range(n):
        for x in range(0, 40 * n + 7):
            in_parent = (x % n == k)
            in_children = (x % (2 * n) == k) or (x % (2 * n) == k + n)
            assert in_parent == in_children, (n, k, x)


@pytest.mark.parametrize("buckets", [1, 2, 4, 16, 64])
def test_bucket_of_doubling_is_an_exact_refinement(buckets):
    """``bucket_of(v, 2B) % B == bucket_of(v, B)``.

    This is what makes "re-plan the unit at 2x buckets" a refinement of THAT
    unit rather than a global reshuffle. ``bucket_of`` is SHA-256 mod B, so the
    property is arithmetic — but it is the arithmetic the re-plan rests on, and
    nothing else in the repo asserts it.
    """
    from app.utils.calibration_staged_futures import bucket_of
    for i in range(400):
        vm = f"g:polymarket:{i}"
        assert bucket_of(vm, 2 * buckets) % buckets == bucket_of(vm, buckets)


def test_replanning_at_double_buckets_never_splits_a_vm_id():
    rows = _roster(*[(i, "polymarket", f"g:polymarket:{i % 37}", True)
                     for i in range(1, 300)])
    for buckets in (4, 8, 16):
        seen: dict[str, int] = {}
        for unit in wvf.plan_units(rows, buckets=buckets):
            for vm in unit.vm_ids:
                assert vm not in seen, f"{vm} in two units at {buckets}"
                seen[vm] = unit.index
        assert set(seen) == {r.vm_id for r in rows}


def test_replanning_partitions_a_units_markets_without_loss():
    rows = _roster(*[(i, "polymarket", f"g:polymarket:{i % 37}", True)
                     for i in range(1, 300)])
    parent = wvf.plan_units(rows, buckets=4)[0]
    mine = set(parent.vm_ids)
    sub_rows = [r for r in rows if r.vm_id in mine]
    children = wvf.plan_units(sub_rows, buckets=8)
    assert {v for c in children for v in c.vm_ids} == mine
    assert sum(len(c.market_ids) for c in children) == len(parent.market_ids)


# ==========================================================================
# PREMISE 4 — a vm_id is never split, and the unmeasurable case is NAMED
# ==========================================================================

def test_a_single_oversized_virtual_question_raises_by_name(monkeypatch):
    """The one thing this rail cannot do. It must say which question, not
    approximate — CAL-P124's lesson 8 in reverse: no silent all-clear."""
    monkeypatch.setattr(wvf.cce, "MAX_SQL_CHARS", 10)
    rows = _roster(*[(i, "polymarket", "g:polymarket:1", True) for i in range(1, 6)])
    assignment = {r.market_id: (r.vm_id, r.is_grouped) for r in rows}
    unit = wvf.plan_units(rows, buckets=1)[0]
    with pytest.raises(RuntimeError, match=r"g:polymarket:1.*MUST NOT be split"):
        wvf.fold_unit(rows, unit, assignment, "none", None, 1)


def test_an_oversized_unit_is_replanned_rather_than_cut(monkeypatch):
    """Two distinct questions in one over-budget unit: re-plan, do not split."""
    calls: list[int] = []
    # The frozen chain alone is ~17.9k chars, so the budget has to leave room
    # for a real unit's arrays or EVERY unit is unmeasurable and this test would
    # be asserting the other branch. ~19.5k fits roughly 40 markets.
    budget = len(_unit_sql(SAMPLE)) + 1_400

    def fake_db_query(sql, limit=1000, **kw):
        calls.append(len(sql))
        if len(sql) > budget:
            raise wvf.cce.QueryTimeout("too big")
        return {"rows": [["all", 5, "ALL", 1, 1, 0.5]], "row_count": 1,
                "truncated": False}

    monkeypatch.setattr(wvf.cce, "db_query", fake_db_query)
    rows = _roster(*[(i, "polymarket", f"g:polymarket:{i % 20}", True)
                     for i in range(1, 200)])
    assignment = {r.market_id: (r.vm_id, r.is_grouped) for r in rows}
    unit = wvf.plan_units(rows, buckets=1)[0]
    out = wvf.fold_unit(rows, unit, assignment, "none", None, 1)
    assert out, "the re-plan produced no rows at all"
    assert len(calls) > 1, "nothing was re-planned"


def test_a_reply_at_the_row_cap_is_treated_as_a_failure_not_an_answer(monkeypatch):
    """gotcha #53 — a silently short answer reads as 'the class is small'."""
    seen = {"n": 0}

    def fake_db_query(sql, limit=1000, **kw):
        seen["n"] += 1
        if seen["n"] == 1:
            return {"rows": [], "row_count": wvf.cce.ROW_CAP, "truncated": True}
        return {"rows": [["all", 5, "ALL", 1, 1, 0.5]], "row_count": 1,
                "truncated": False}

    monkeypatch.setattr(wvf.cce, "db_query", fake_db_query)
    rows = _roster(*[(i, "polymarket", f"g:polymarket:{i}", True) for i in range(1, 9)])
    assignment = {r.market_id: (r.vm_id, r.is_grouped) for r in rows}
    unit = wvf.plan_units(rows, buckets=1)[0]
    wvf.fold_unit(rows, unit, assignment, "none", None, 1)
    assert seen["n"] > 1, "a truncated reply was accepted as the answer"


def test_truncated_flag_is_read_not_only_the_row_count(monkeypatch):
    """The server reports ``truncated`` explicitly. Reading only ``row_count >=
    ROW_CAP`` would miss a cap the server applied for another reason."""
    seen = {"n": 0}

    def fake_db_query(sql, limit=1000, **kw):
        seen["n"] += 1
        if seen["n"] == 1:
            return {"rows": [], "row_count": 3, "truncated": True}
        return {"rows": [], "row_count": 0, "truncated": False}

    monkeypatch.setattr(wvf.cce, "db_query", fake_db_query)
    wvf._read_hash_chunk("polymarket", "cricket", 1, 0)
    assert seen["n"] > 1


def test_stage_a_split_is_bounded_and_raises_rather_than_looping(monkeypatch):
    monkeypatch.setattr(
        wvf.cce, "db_query",
        lambda *a, **k: {"rows": [], "row_count": wvf.cce.ROW_CAP, "truncated": True})
    with pytest.raises(RuntimeError, match="irreducible"):
        wvf._read_hash_chunk("polymarket", "cricket", 1, 0)


# ==========================================================================
# The CAL-P124-2 residual: measured, chunked on the GROUPING key
# ==========================================================================

@pytest.mark.parametrize("col", ["group_id", "event_id"])
def test_span_sql_chunks_on_the_grouping_key_not_the_market_id(col):
    """Chunking this aggregate on ``fm.id`` would cut groups apart and every
    piece would look like a group that does not span — a zero residual reported
    with total confidence."""
    sql = wvf.SPAN_SQL.format(col=col, source="polymarket", category="basketball",
                              chunk=f"AND ABS(HASHTEXT(fm.{col}::text)::bigint) % 4 = 1")
    assert f"HASHTEXT(fm.{col}::text)" in sql
    assert "fm.id %" not in sql
    assert f"GROUP BY 1" in sql


def test_span_sql_requires_members_on_both_sides():
    sql = wvf.SPAN_SQL.format(col="group_id", source="polymarket",
                              category="basketball", chunk="")
    assert "= 'basketball'\n           ) > 0" in sql
    assert "<> 'basketball'\n           ) > 0" in sql


def test_span_sql_uses_the_same_category_coalesce_as_the_fold():
    """A residual measured under a different definition of 'the cell' is not a
    residual for this cell."""
    sql = wvf.SPAN_SQL.format(col="group_id", source="polymarket",
                              category="basketball", chunk="")
    assert "COALESCE(fm.llm_sport_category, 'uncategorized')" in sql
    assert "COALESCE(fm.llm_sport_category, 'uncategorized')" in \
        wvf.stage_a_sql("polymarket", "basketball", 4, 0)


def test_sum_over_residues_adds_the_halves(monkeypatch):
    calls = {"n": 0}

    def fake(sql, limit=5, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise wvf.cce.QueryTimeout("slow")
        return {"rows": [[3, 7]], "row_count": 1, "truncated": False}

    monkeypatch.setattr(wvf.cce, "db_query", fake)
    assert wvf._sum_over_residues(lambda n, k: f"-- {n} {k}", 2) == [6, 14]


def test_sum_over_residues_is_bounded(monkeypatch):
    monkeypatch.setattr(
        wvf.cce, "db_query",
        lambda *a, **k: (_ for _ in ()).throw(wvf.cce.QueryTimeout("always")))
    with pytest.raises(RuntimeError, match="irreducible"):
        wvf._sum_over_residues(lambda n, k: "-- x", 1)


def test_sum_over_residues_treats_null_as_zero(monkeypatch):
    monkeypatch.setattr(
        wvf.cce, "db_query",
        lambda *a, **k: {"rows": [[None, 4]], "row_count": 1, "truncated": False})
    assert wvf._sum_over_residues(lambda n, k: "-- x", 2) == [0, 4]


def test_a_zero_residual_is_reported_as_a_number_not_omitted():
    """'0' and 'not measured' are different facts and only one is an all-clear."""
    src = (SCRIPTS / "calibration_whole_vm_fold.py").read_text()
    assert "UPPER BOUND re-assigned" in src


# ==========================================================================
# The phantom census — rows the curve counts more than once
# ==========================================================================
# `deduped` is `SELECT ro.* FROM normalized ro`, one row per outcome. So
# COUNT(*) > COUNT(DISTINCT outcome_id) is not a threshold judgement, it is an
# arithmetic impossibility — and the payload carries the same rows, so no
# SELF-CHECK and no fold can see it.
#
# MEASURED 2026-08-29 against q268, whole cell, every unit:
#   polymarket/basketball  13,116 rows / 7,419 outcomes = 5,697 phantom (43.44%)
#   polymarket/cricket      3,252 rows / 2,834 outcomes =   418 phantom (12.85%)
#
# CAUSE, isolated by differential: `vm_stats` GROUPs BY
# (vm_id, source, category, is_grouped, mutually_exclusive); `clean_vms`
# inherits that grain; `ranked_outcomes` joins it on (vm_id, source) ALONE. On
# one basketball unit clean_vms held 491 rows for 387 distinct (vm_id, source),
# and adding `mutually_exclusive` — not category, not is_grouped — accounted for
# all 491. De-duplicating clean_vms to (vm_id, source) took phantom 1,362 -> 0.

def test_phantom_census_compares_rows_to_distinct_outcomes():
    assert "COUNT(*) AS legs" in wvf.PHANTOM_TAIL
    assert "COUNT(DISTINCT outcome_id) AS dlegs" in wvf.PHANTOM_TAIL


def test_phantom_census_reads_deduped_the_published_population():
    """Counting anywhere earlier counts rows the curve never published."""
    assert "FROM deduped" in wvf.PHANTOM_TAIL
    assert "futures_outcomes" not in wvf.PHANTOM_TAIL


def test_phantom_census_reports_the_denominator_too():
    """A phantom COUNT with no market total is a number nobody can size."""
    assert "COUNT(*) AS markets" in wvf.PHANTOM_TAIL
    assert "markets_affected" in wvf.PHANTOM_TAIL


def test_phantom_census_sums_every_unit(monkeypatch):
    """Never a sample: a partial sweep reads as a low duplication rate rather
    than as a partial sweep (gotcha #53), on the one number that decides
    whether the curve's weights are trustworthy."""
    seen = []

    def fake(sql, limit=5, **kw):
        seen.append(sql)
        return {"rows": [[10, 7, 1, 3]], "row_count": 1, "truncated": False}

    monkeypatch.setattr(wvf.cce, "db_query", fake)
    rows = _roster(*[(i, "polymarket", f"g:polymarket:{i}", True)
                     for i in range(1, 40)])
    units = wvf.plan_units(rows, buckets=8)
    ph = wvf.phantom_census(rows, buckets=8)
    assert len(seen) == len(units), "not every unit was swept"
    assert ph["published_rows"] == 10 * len(units)
    assert ph["distinct_outcomes"] == 7 * len(units)
    assert ph["phantom_rows"] == 3 * len(units)


def test_phantom_pct_is_a_share_of_published_rows(monkeypatch):
    monkeypatch.setattr(
        wvf.cce, "db_query",
        lambda *a, **k: {"rows": [[100, 75, 5, 20]], "row_count": 1,
                         "truncated": False})
    rows = _roster((1, "polymarket", "m:1", False))
    assert wvf.phantom_census(rows, buckets=1)["phantom_pct"] == 25.0


def test_phantom_pct_is_none_not_zero_on_an_empty_cell(monkeypatch):
    """'no rows' and 'no duplication' are different facts and only one is an
    all-clear (gotcha #53)."""
    monkeypatch.setattr(
        wvf.cce, "db_query",
        lambda *a, **k: {"rows": [[0, 0, 0, 0]], "row_count": 1,
                         "truncated": False})
    rows = _roster((1, "polymarket", "m:1", False))
    assert wvf.phantom_census(rows, buckets=1)["phantom_pct"] is None


def test_the_fan_out_join_is_still_on_two_of_five_columns():
    """THE FINDING, pinned against the frozen file.

    If someone widens the ``clean_vms`` join — or narrows ``vm_stats``' GROUP BY
    — this test fails, and that is the signal that 16-CAL has been acted on. It
    asserts the DEFECT, deliberately, so its removal is loud rather than silent.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes
    sql = _calibration_population_ctes()
    grp = sql.split("vm_stats AS (", 1)[1].split("GROUP BY", 1)[1].split("),", 1)[0]
    for col in ("vm_id", "source", "category", "is_grouped", "mutually_exclusive"):
        assert col in grp, f"vm_stats no longer groups by {col} — re-measure 16-CAL"
    join = sql.split("JOIN clean_vms cv ON", 1)[1].split("\n", 2)[0]
    assert "cv.vm_id = vm.vm_id" in join and "cv.source = vm.source" in join
    assert "mutually_exclusive" not in join, (
        "clean_vms is now joined on mutually_exclusive too — the 16-CAL fan-out "
        "may be fixed. Re-run --phantom on polymarket/basketball (was 43.44%) "
        "and update the measured numbers in this file.")


# ==========================================================================
# The roster cache — a reuse that must never become a merge
# ==========================================================================

def test_roster_cache_round_trips(tmp_path, monkeypatch):
    cache = tmp_path / "r.json"
    monkeypatch.setattr(wvf, "stage_a", lambda s, c, n: list(SAMPLE))
    rows, secs, how = wvf.load_or_freeze("polymarket", "cricket", 4, str(cache))
    assert how == "frozen" and rows == SAMPLE
    again, secs2, how2 = wvf.load_or_freeze("polymarket", "cricket", 4, str(cache))
    assert how2 == "reused" and again == SAMPLE and secs2 == 0.0


def test_roster_cache_refuses_another_cell(tmp_path, monkeypatch):
    """A roster is a claim about ONE cell's eligibility and question identity.
    Replaying it under another cell's name folds a complete, plausible,
    well-formed table about the wrong population."""
    cache = tmp_path / "r.json"
    monkeypatch.setattr(wvf, "stage_a", lambda s, c, n: list(SAMPLE))
    wvf.load_or_freeze("polymarket", "cricket", 4, str(cache))
    with pytest.raises(SystemExit, match="Refusing"):
        wvf.load_or_freeze("polymarket", "basketball", 4, str(cache))


def test_roster_cache_refuses_another_source(tmp_path, monkeypatch):
    cache = tmp_path / "r.json"
    monkeypatch.setattr(wvf, "stage_a", lambda s, c, n: list(SAMPLE))
    wvf.load_or_freeze("polymarket", "cricket", 4, str(cache))
    with pytest.raises(SystemExit, match="Refusing"):
        wvf.load_or_freeze("kalshi", "cricket", 4, str(cache))


def test_roster_cache_prints_its_age_on_every_reuse(tmp_path, monkeypatch, capsys):
    """EVERY reuse, not just the first. A roster's age is the one thing that
    makes a cached fold wrong, so it cannot be a write-time footnote."""
    cache = tmp_path / "r.json"
    monkeypatch.setattr(wvf, "stage_a", lambda s, c, n: list(SAMPLE))
    wvf.load_or_freeze("polymarket", "cricket", 4, str(cache))
    for _ in range(3):
        capsys.readouterr()
        wvf.load_or_freeze("polymarket", "cricket", 4, str(cache))
        out = capsys.readouterr().out
        assert "REUSED" in out and "ago" in out


def test_a_stale_roster_is_flagged_loudly(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "r.json"
    monkeypatch.setattr(wvf, "stage_a", lambda s, c, n: list(SAMPLE))
    wvf.load_or_freeze("polymarket", "cricket", 4, str(cache))
    blob = json.loads(cache.read_text())
    blob["captured_at"] -= 3 * 24 * 3600
    cache.write_text(json.dumps(blob))
    capsys.readouterr()
    wvf.load_or_freeze("polymarket", "cricket", 4, str(cache))
    assert "over a day old" in capsys.readouterr().out


def test_no_cache_path_means_no_file_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(wvf, "stage_a", lambda s, c, n: list(SAMPLE))
    monkeypatch.chdir(tmp_path)
    wvf.load_or_freeze("polymarket", "cricket", 4, None)
    assert list(tmp_path.iterdir()) == []


# ==========================================================================
# Composition — this file adds a SWEEP, not a dimension
# ==========================================================================

def test_it_adds_exactly_one_dimension_and_no_more():
    """CAL-P121's rule, and the form its suite enforces.

    ``setdefault`` has a quiet failure — a name collision becomes a no-op and
    the fold runs somebody else's dimension under this file's name — so the
    name is asserted ABSENT before registration and PRESENT after.
    """
    cce_alone = _load("calibration_cell_exact")
    ffold_alone = _load("calibration_family_fold")
    inherited = set(cce_alone.DIMENSIONS) | set(ffold_alone.ADDED_DIMENSIONS)
    assert set(wvf.ADDED_DIMENSIONS) == {"publegs"}
    assert "publegs" not in inherited, "the name collided; setdefault was a no-op"
    assert set(wvf.cce.DIMENSIONS) == inherited | {"publegs"}
    assert set(wvf._PRE_EXISTING) == inherited


def test_it_registers_with_setdefault_never_a_rebind():
    src = (SCRIPTS / "calibration_whole_vm_fold.py").read_text()
    assert "cce.DIMENSIONS.setdefault(" in src
    assert not re.search(r"cce\.DIMENSIONS\[[^\]]+\]\s*=", src)


def test_publegs_counts_published_legs_rather_than_banding_their_sum():
    """The distinction the whole dimension exists for.

    ``sumband`` cannot tell 'both legs published and coherent' (sum ~1) from
    'one leg published at a low price' (sum <= 1.15 by having one term). A COUNT
    can; a SUM cannot.
    """
    expr, join, pre = wvf.cce.DIMENSIONS["publegs"]
    assert "COUNT(*) AS legs FROM deduped" in pre
    assert "ml.legs" in expr
    assert "adj_opening_probability" not in expr


def test_publegs_counts_over_deduped_the_published_population():
    """Counting anywhere earlier in the chain counts a different set — the
    eligible outcomes, not the ones that reached the curve."""
    _, _, pre = wvf.cce.DIMENSIONS["publegs"]
    assert "FROM deduped" in pre
    assert "futures_outcomes" not in pre


def test_publegs_reports_published_legs_against_market_legs():
    """``pub1/2`` is the finding; ``pub1`` alone would not say whether the
    market HAD another leg to publish."""
    expr, _, _ = wvf.cce.DIMENSIONS["publegs"]
    assert "sh.mn" in expr and "ml.legs" in expr


def test_publegs_shape_arms_match_the_rails_sumband_term_for_term():
    """Two dimensions that classify the same shape must classify it
    identically, or their tables cannot be read against each other."""
    expr, _, _ = wvf.cce.DIMENSIONS["publegs"]
    for arm in ("sh.mw = 0", "sh.mn >= 3 AND sh.mw >= 2",
                "sh.mn >= 3 AND sh.mw = 1", "sh.mn = 2"):
        assert arm in expr
        assert arm in wvf.cce.SUMBAND_EXPR


def test_publegs_is_null_safe_on_both_joins():
    """Both joins are LEFT. An unmatched row must land in a named class, not
    render as ``binary|pub/`` — a class name that is silently a hole."""
    expr, _, _ = wvf.cce.DIMENSIONS["publegs"]
    assert "ml.legs IS NULL THEN 'na'" in expr
    assert "sh.mn IS NULL THEN 'na'" in expr


def test_publegs_buckets_its_tail_so_the_partition_stays_searchable():
    """An unbounded leg count makes one class per ladder width and the
    exhaustive subset search refuses the fold (2^k)."""
    expr, _, _ = wvf.cce.DIMENSIONS["publegs"]
    assert "'4plus'" in expr


def test_it_reaches_the_rail_through_the_family_fold():
    """So ``--by family`` — the only dimension that can name a Polymarket
    family — is available on the cell type that needs it most."""
    assert "family" in wvf.cce.DIMENSIONS
    assert "none" in wvf.cce.DIMENSIONS


def test_its_loader_registers_nothing_in_sys_modules():
    """CAL-P121's hazard, guarded on what THIS module controls.

    An earlier draft asserted the global ``"calibration_cell_exact" not in
    sys.modules`` and went red the moment it ran in the same process as
    ``test_calibration_missing_loser_census_p122``, because that script uses a
    plain ``import calibration_cell_exact as cce`` (harmless there — it
    registers no dimensions). **A guard that another queue's file can break by
    being imported is not a guard** — the family fold's own docstring says so —
    so this asserts the property this file owns: ``_load`` adds nothing.
    """
    before = set(sys.modules)
    mod = wvf._load("calibration_cell_exact")
    added = {k for k in set(sys.modules) - before if "calibration" in k}
    assert added == set(), f"_load registered {added}"
    assert mod is not sys.modules.get("calibration_cell_exact")


def test_its_loader_returns_a_fresh_module_each_call():
    """The reason a fresh object matters: these modules mutate a shared
    ``DIMENSIONS`` dict at import, so a cached one would leak this file's
    registration into every other test in the process."""
    a = wvf._load("calibration_cell_exact")
    b = wvf._load("calibration_cell_exact")
    assert a is not b
    assert "publegs" not in a.DIMENSIONS and "publegs" not in b.DIMENSIONS


def test_its_loader_never_assigns_to_sys_modules():
    """Matches an ASSIGNMENT, not a mention. ``RosterRow``'s docstring names
    ``sys.modules[cls.__module__]`` to explain why it is not a dataclass, and a
    substring check would forbid documenting the hazard it guards."""
    src = (SCRIPTS / "calibration_whole_vm_fold.py").read_text()
    assert not re.search(r"sys\.modules\[[^\]]*\]\s*=", src)


def test_it_reuses_the_rails_caps_rather_than_copying_them():
    """CAL-P115's rule: an equal copy drifts on the next edit. A second
    ``MAX_SQL_CHARS`` here would let the two rails disagree about what fits."""
    src = (SCRIPTS / "calibration_whole_vm_fold.py").read_text()
    assert not re.search(r"^MAX_SQL_CHARS\s*=", src, re.M)
    assert not re.search(r"^ROW_CAP\s*=", src, re.M)
    assert "cce.MAX_SQL_CHARS" in src and "cce.ROW_CAP" in src


def test_it_reuses_the_rails_fold_and_payload_arithmetic():
    src = (SCRIPTS / "calibration_whole_vm_fold.py").read_text()
    assert "cce.payload_cell(" in src
    assert "cce.fold(" in src and "cce.pool(" in src
    assert not re.search(r"^def (fold|pool|payload_cell)\(", src, re.M)


# ==========================================================================
# Dimensions this rail must refuse rather than mis-handle
# ==========================================================================

def test_an_id_range_dimension_is_refused_by_name():
    """``ladder`` is handed lo/hi and pre-computes per id range. This rail has
    no id ranges. Running it would silently fold an empty arm."""
    assert "ladder" in wvf.cce.PER_CHUNK_DIMENSIONS
    assignment = {r.market_id: (r.vm_id, r.is_grouped) for r in SAMPLE}
    unit = wvf.plan_units(SAMPLE, buckets=4)[0]
    with pytest.raises(ValueError, match="id-RANGE dimension"):
        wvf.unit_sql(unit, assignment, "ladder", None)


def test_an_empty_unit_is_refused():
    class _Empty:
        index, vm_ids, market_ids = 0, (), ()
    with pytest.raises(ValueError, match="no markets"):
        wvf.unit_sql(_Empty(), {}, "none", None)


# ==========================================================================
# The holdout, and the reason it is better here than on the id-range rail
# ==========================================================================

def test_holdout_is_part_of_the_group_key_not_a_chunk_edge():
    """The id-range rail needs the holdout id to BE a chunk edge or the halves
    are contaminated. Here it is a column in the GROUP BY, so it is exact for
    any id and does not perturb the partition at all."""
    sql = _unit_sql(SAMPLE, holdout=7_000_000)
    assert "CASE WHEN d.market_id < 7000000 THEN 'OLD' ELSE 'NEW' END" in sql
    assert "GROUP BY 1, 2, 3" in sql


def test_no_holdout_folds_a_single_labelled_arm():
    sql = _unit_sql(SAMPLE, holdout=None)
    assert "'ALL' AS h" in sql
    assert "GROUP BY 1, 2, 3" in sql


def test_holdout_label_is_not_a_bucket_the_halves_dict_would_miss():
    """``stage_b`` routes on ``h in halves``; a label neither 'OLD' nor 'NEW'
    must fall through to the pooled total only, never be dropped."""
    src = (SCRIPTS / "calibration_whole_vm_fold.py").read_text()
    assert "[by_key] + ([halves[h]] if h in halves else [])" in src


# ==========================================================================
# Array rendering
# ==========================================================================

def test_bigint_array_renders_ints():
    assert wvf._bigint_array([3, 1, 2]) == "ARRAY[3,1,2]"


def test_bool_array_renders_sql_booleans():
    assert wvf._bool_array([True, False]) == "ARRAY[true,false]"


def test_text_array_quotes_every_element():
    assert wvf._text_array(["a", "b"]) == "ARRAY['a','b']"


def test_roster_row_is_usable_by_the_producers_planner():
    """``plan_units`` reads production SQLAlchemy ``Row`` objects by attribute.
    A dict-shaped roster would exercise a branch production never takes."""
    units = wvf.plan_units(SAMPLE, buckets=4)
    assert units
    assert sum(len(u.market_ids) for u in units) == len(SAMPLE)


def test_roster_row_is_not_a_dataclass():
    """Deliberate: ``from __future__ import annotations`` + ``_load``'s refusal
    to register the module makes ``@dataclass`` raise at import time. If someone
    'tidies' it back, the whole instrument stops importing — and it would do so
    only under the loader, not under a plain import."""
    import dataclasses
    assert not dataclasses.is_dataclass(wvf.RosterRow)


def test_roster_census_counts_questions_not_only_rows():
    census = wvf.roster_census(SAMPLE)
    assert census["roster_rows"] == 5
    assert census["distinct_markets"] == 5
    assert census["distinct_vm_ids"] == 3
    assert census["vm_by_kind"] == {"e": 1, "g": 3, "m": 1}
    assert census["largest_vm_markets"] == 3


# ==========================================================================
# Ruling 009 — the frozen file is imported, never modified
# ==========================================================================

def test_the_instrument_only_imports_the_frozen_producer():
    src = (SCRIPTS / "calibration_whole_vm_fold.py").read_text()
    assert "from app.tasks.precompute_calibration import" in src
    for verb in ("open(", "write(", "UPDATE ", "DELETE ", "INSERT "):
        assert verb not in src.replace('with open(args.out, "w") as fh:', ""), verb
