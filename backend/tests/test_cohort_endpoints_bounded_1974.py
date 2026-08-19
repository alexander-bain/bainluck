"""CAL-P071 — the two cohort diagnostic endpoints, which had no tests at all.

`/api/admin/cohort-provenance-split` and `/api/admin/cohort-sums-histogram`
shipped in `codex-adhoc/cohort-views`, which INT-085 merged with no PR and
therefore with no CI run. Both sorted their entire joined result set with
``ORDER BY random()`` and shipped up to 300,000 / 100,000 rows to Python. The
histogram H12'd at Heroku's hard 30s router limit on all three of INT-085's
attempts (#1974); the split returned once in **29.99s** and has H12'd on every
attempt since (4/4 on 2026-08-18), taking the #1912 per-cell evidence base with
it.

The property that failed is not "the query is slow". It is that **the response
cost grew with the population** — a diagnostic that answers today and cannot
answer tomorrow is not a diagnostic. Every number both endpoints publish is an
aggregate, so the database now computes it and a bounded number of rows crosses
the wire.

These tests assert three things, in descending order of what they are worth:

1. **The refactor did not move a number.** The bin-aggregate path must produce
   exactly what the old pair-list path produced, including at the bin edges
   where an off-by-one in ``LEAST(FLOOR(p*10),9)`` would hide.
2. **The response size does not grow with the population.** Two populations
   three orders of magnitude apart, same cell cardinality, same wire shape.
3. **The fatal idiom is gone**, as a plain source tripwire. It is here because
   the failure is operational — no unit test can observe an H12 — and because
   the idiom is textual. It stands *beside* the behavioural tests above, never
   instead of them.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routes import admin_cohort


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _bin(p: float) -> int:
    """Production's bin assignment, restated so the tests do not import it."""
    return min(int(p * 10), 9)


def _ece_from_pairs_raw(pairs) -> float | None:
    """The PRE-refactor definition, UNROUNDED, from raw (prob, actual) pairs.

    This is the arithmetic the endpoint used to run in Python. It is reproduced
    here rather than imported so that the parity test compares two independent
    implementations instead of one function against itself.
    """
    n = len(pairs)
    if n < 30:
        return None
    bins: dict[int, list] = {}
    for prob, actual in pairs:
        bins.setdefault(_bin(prob), []).append((prob, actual))
    total = 0.0
    for b in bins.values():
        avg_p = sum(p for p, _ in b) / len(b)
        avg_a = sum(a for _, a in b) / len(b)
        total += len(b) / n * abs(avg_p - avg_a)
    return total * 100


def _ece_from_pairs(pairs) -> float | None:
    """``_ece_from_pairs_raw`` on the endpoint's 2-decimal publication grid."""
    raw = _ece_from_pairs_raw(pairs)
    return None if raw is None else round(raw, 2)


def _ece_from_bin_aggregates_raw(agg_rows) -> float | None:
    """The BINNED definition, UNROUNDED, from the same aggregates the SQL emits.

    A third independent summation, deliberately: it consumes ``(n, sum_prob,
    winners)`` per bin — never the pairs — which is the whole difference the
    parity test exists to grade.
    """
    n = sum(r.n for r in agg_rows)
    if n < 30:
        return None
    total = 0.0
    for r in agg_rows:
        if not r.n:
            continue
        total += r.n / n * abs(r.sum_prob / r.n - r.winners / r.n)
    return total * 100


def _aggregate(rows):
    """Turn (league, mt, venue, prob, actual) rows into the SQL group-by result.

    Exactly the reduction the new query asks Postgres for, so a test can drive
    the endpoint from a row-level fixture and still exercise the aggregate path.
    """
    acc: dict[tuple, list] = {}
    for league, mt, venue, prob, actual in rows:
        key = (league, mt, venue, _bin(prob))
        cur = acc.setdefault(key, [0, 0.0, 0.0])
        cur[0] += 1
        cur[1] += prob
        cur[2] += actual
    return [
        SimpleNamespace(league=k[0], market_type=k[1], venue=k[2], bin=k[3],
                        n=v[0], sum_prob=v[1], winners=v[2])
        for k, v in sorted(acc.items())
    ]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _db(*result_sets):
    db = SimpleNamespace()
    db.execute = AsyncMock(side_effect=[_Result(rs) for rs in result_sets])
    return db


@pytest.fixture(autouse=True)
def _no_admin_auth(monkeypatch):
    monkeypatch.setattr(admin_cohort, "_check_admin_secret", lambda **kw: None)


# --------------------------------------------------------------------------
# 1. the refactor did not move a number
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bin_aggregate_ece_equals_the_pair_list_ece():
    """The SQL-binned path reproduces the pair-list path to FLOAT PRECISION.

    ⚠️ **CAL-P073 — this assertion was rewritten after it turned master red, and
    it is now STRICTLY STRONGER than the version it replaces.** History, because
    the obvious reading of the change is the wrong one:

    The original asserted ``cell["ece_all"] == _ece_from_pairs(...)`` — exact
    equality on values both sides had already ROUNDED to 2 decimals. It passed
    21/21 locally on Python 3.12.13 and failed on CI (run 32197877377, shard
    1/4) with ``assert 26.32 == 26.33``, the only failure in the entire run.
    CAL-P071 was reverted whole (``e61ef179``) to reopen the deploy pipeline and
    bounced here, because loosening someone else's deliberate assertion is not
    the Integrator's call to make.

    **It is not a logic error and not an ordinary flake.** Both paths are pure
    Python here (a simulated ``_aggregate``, no Postgres). They compute the same
    mathematical quantity by different SUMMATION ORDERS — the pair path
    accumulates per-bin from raw pairs, the aggregate path from pre-summed
    ``(n, sum_prob, winners)``. Float addition is not associative, so the two
    totals differ by ~1 ULP; when the true value sits within 1 ULP of a
    ``x.xx5`` boundary, ``round`` sends them to different hundredths. **Exact
    2-decimal equality is therefore not a property either implementation can
    offer, on any interpreter.** The docstring's old claim — "to the last
    decimal" — was false as stated, and the test was enforcing it by luck.

    Note what the old assertion ALSO did, which is why the replacement is not a
    loosening: comparing two ROUNDED values for equality silently admits a real
    divergence of up to ~0.005 pp whenever it does not straddle a boundary. It
    was simultaneously too strict (red on a sub-ULP tie-break) and too loose
    (green on a divergence 10⁷ times larger than the one it failed on).

    So the property is restated where it is actually true and actually strong:

    1. the two independent summations agree to **1e-9**, unrounded — the parity
       claim, at full precision;
    2. the PUBLISHED field sits on the 2-decimal grid of that agreed value,
       within one grid step, which is all a rounded field can promise.

    Ruling 083's discipline, applied to ourselves: the band is relaxed only
    where the code proves the underlying quantity did not move. Assertion 1 is
    that proof. Without it, assertion 2 alone would be exactly the "widen the
    tolerance until it passes" move that ruling forbids.
    """
    rows = []
    # A spread wide enough that several bins are populated and the per-bin
    # means differ from the cell mean — otherwise any binning agrees by luck.
    for i in range(200):
        p = 0.01 + (i % 97) / 100.0
        actual = 1.0 if i % 3 == 0 else 0.0
        rows.append(("basketball", "container_member", True, p, actual))

    aggregates = _aggregate(rows)
    raw_pairs = _ece_from_pairs_raw([(p, a) for _, _, _, p, a in rows])
    raw_bins = _ece_from_bin_aggregates_raw(aggregates)

    # 1. THE PARITY CLAIM, at full precision. This is the real assertion.
    assert raw_pairs == pytest.approx(raw_bins, rel=0, abs=1e-9), (
        "the two summations disagree by more than float error — this is a real "
        "divergence, not a rounding tie-break"
    )

    # 2. The published field, on its own grid, within one step of the agreed
    #    value. One step and no more: a two-step gap is a genuine defect.
    resp = await admin_cohort.cohort_provenance_split(
        request=None, db=_db(aggregates)
    )
    cell = resp["cells"][0]
    for field in ("ece_all", "ece_venue"):  # every row is venue-graded here
        assert abs(cell[field] - round(raw_pairs, 2)) <= 0.01, (
            f"{field}={cell[field]} is more than one rounding step from the "
            f"agreed value {raw_pairs}"
        )
    assert cell["n_all"] == len(rows)


def test_exact_two_decimal_parity_is_not_a_property_float_summation_can_offer():
    """Why the assertion above cannot be tightened back. Pinned, not narrated.

    A direct demonstration, independent of the endpoint: the same five numbers,
    summed in two orders, land on opposite sides of a ``x.xx5`` boundary and
    round to DIFFERENT hundredths. Anyone tempted to restore ``==`` on the
    rounded values should read this first — the next occurrence will not
    reproduce on the machine where it is investigated, which is precisely how
    the last one cost a merge and a revert.

    ⚠️ The first draft of this test used ``[0.1 … 0.7]`` and asserted
    ``forward != backward``. Both orders sum to exactly 2.8 there, so the
    assertion was false and the test caught its own author — a demonstration of
    a general fact, written with an example in which the fact does not occur.
    The specimen below is searched-for, not assumed, and is pinned by value so
    it cannot quietly stop demonstrating anything.
    """
    terms = [2.461, 2.55, 2.031, 2.839, 1.224]
    forward = 0.0
    for t in terms:
        forward += t
    backward = 0.0
    for t in reversed(terms):
        backward += t

    # Same mathematical sum, different float, DIFFERENT PUBLISHED VALUE — the
    # 26.32-vs-26.33 mechanism in five lines, with no calibration code in sight.
    assert forward != backward
    assert round(forward, 2) != round(backward, 2)
    assert (round(forward, 2), round(backward, 2)) == (11.11, 11.10)
    # ...and the tolerance the parity test uses does hold across that boundary.
    assert forward == pytest.approx(backward, rel=0, abs=1e-9)


@pytest.mark.asyncio
@pytest.mark.parametrize("p", [0.0999, 0.1, 0.2999, 0.3, 0.8999, 0.9, 0.99, 0.999])
async def test_bin_edges_land_where_the_pair_path_put_them(p):
    """LEAST(FLOOR(p*10),9) in SQL must agree with min(int(p*10),9) in Python.

    A one-bin drift is invisible in an aggregate ECE most of the time and
    catastrophic at the top bin, where it would fold 0.9-1.0 into a tenth bin
    that does not exist.
    """
    rows = [("t", "quantity", True, p, float(i % 2)) for i in range(40)]
    aggregates = _aggregate(rows)

    # The BIN ASSIGNMENT is the subject here, and it is exact integer
    # arithmetic — so it is asserted exactly, on the bin keys themselves,
    # rather than inferred from an ECE that happens to differ when it drifts.
    # Reading a one-bin drift off a float is what made the sibling assertion
    # above interpreter-dependent; the thing this test is about never was.
    assert {r.bin for r in aggregates} == {_bin(p)}

    # The ECE is then corroboration, on the same one-rounding-step grid the
    # sibling uses and for the same reason.
    raw = _ece_from_pairs_raw([(p, a) for _, _, _, p, a in rows])
    resp = await admin_cohort.cohort_provenance_split(
        request=None, db=_db(aggregates)
    )
    assert abs(resp["cells"][0]["ece_all"] - round(raw, 2)) <= 0.01


@pytest.mark.asyncio
async def test_venue_split_counts_and_null_default_share():
    rows = [("soccer", "quantity", True, 0.4, 1.0)] * 30
    rows += [("soccer", "quantity", False, 0.4, 0.0)] * 70
    resp = await admin_cohort.cohort_provenance_split(
        request=None, db=_db(_aggregate(rows))
    )
    cell = resp["cells"][0]
    assert cell["n_all"] == 100
    assert cell["n_venue"] == 30
    assert cell["n_default"] == 70
    assert cell["null_default_share"] == 0.7
    assert cell["graded_share"] == 0.3
    # graded_share < 0.5 must win before the <=5pp test (LAUNCH-LEDGER)
    assert cell["verdict_all"] == "NOT-PROVABLE-selection-biased"


@pytest.mark.asyncio
async def test_a_cell_under_thirty_rows_reports_no_ece_rather_than_a_number():
    rows = [("cricket", "quantity", True, 0.5, 1.0)] * 29
    resp = await admin_cohort.cohort_provenance_split(
        request=None, db=_db(_aggregate(rows))
    )
    cell = resp["cells"][0]
    assert cell["ece_all"] is None
    assert cell["verdict_all"] == "NOT-PROVABLE"


# --------------------------------------------------------------------------
# 2. response size does not grow with the population — the property that failed
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wire_shape_is_bounded_by_cell_cardinality_not_row_count():
    """1e3 rows and 1e7 rows over the same cells produce the same wire shape.

    This is the whole point of the fix. `rows_scanned` is allowed — required,
    even — to differ; the number of objects serialised is not.
    """
    small = [SimpleNamespace(league="basketball", market_type="quantity",
                             venue=True, bin=b, n=100, sum_prob=100 * (b / 10 + 0.05),
                             winners=30.0) for b in range(10)]
    huge = [SimpleNamespace(league="basketball", market_type="quantity",
                            venue=True, bin=b, n=1_000_000,
                            sum_prob=1_000_000 * (b / 10 + 0.05),
                            winners=300_000.0) for b in range(10)]

    r_small = await admin_cohort.cohort_provenance_split(request=None, db=_db(small))
    r_huge = await admin_cohort.cohort_provenance_split(request=None, db=_db(huge))

    assert len(r_small["cells"]) == len(r_huge["cells"]) == 1
    assert r_small["bin_rows_returned"] == r_huge["bin_rows_returned"] == 10
    assert r_small["rows_scanned"] == 1_000
    assert r_huge["rows_scanned"] == 10_000_000
    # identical distribution => identical ECE, four orders of magnitude apart
    assert r_small["cells"][0]["ece_all"] == r_huge["cells"][0]["ece_all"]


@pytest.mark.asyncio
async def test_the_split_declares_it_is_not_a_sample():
    """The old endpoint's n_all was a 300k-sample count and said nothing about it.

    A reader who scales a population off `n_all` gets a wrong answer silently;
    the declaration is what makes that impossible.
    """
    rows = [("weather", "quantity", True, 0.5, 1.0)] * 40
    resp = await admin_cohort.cohort_provenance_split(
        request=None, db=_db(_aggregate(rows))
    )
    assert resp["sampled"] is False
    assert resp["population"] == "full"


# --------------------------------------------------------------------------
# ece_label_* — INT-085's open question, answered in both directions
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ece_label_is_null_when_the_canonical_implementation_answers():
    """`null` on every cell is the HEALTHY reading, not a cold-heavy read.

    INT-085 flagged `ece_label_all: null` across the board as possibly wrong.
    It is right: the label exists only to mark a number produced by the local
    fallback rather than by `_compute_horizon_mce`, so null everywhere means
    the canonical definition answered every cell.
    """
    rows = [("politics", "quantity", True, 0.3 + (i % 5) / 10, float(i % 2))
            for i in range(60)]
    resp = await admin_cohort.cohort_provenance_split(
        request=None, db=_db(_aggregate(rows))
    )
    assert resp["cells"][0]["ece_label_all"] is None
    assert resp["cells"][0]["ece_label_venue"] is None


@pytest.mark.asyncio
async def test_ece_label_marks_the_fallback_when_the_canonical_one_cannot_answer(
    monkeypatch,
):
    """The negative control: without it, the test above passes for any reason."""
    from app.tasks import precompute_calibration

    def _boom(*a, **k):
        raise RuntimeError("canonical implementation unavailable")

    monkeypatch.setattr(precompute_calibration, "_compute_horizon_mce", _boom)

    rows = [("politics", "quantity", True, 0.3 + (i % 5) / 10, float(i % 2))
            for i in range(60)]
    resp = await admin_cohort.cohort_provenance_split(
        request=None, db=_db(_aggregate(rows))
    )
    cell = resp["cells"][0]
    assert cell["ece_label_all"] == "fallback-nonparity"
    # and the fallback still produces the same arithmetic, which is why the
    # label is a provenance marker rather than a warning about the value
    assert cell["ece_all"] == _ece_from_pairs([(p, a) for _, _, _, p, a in rows])


# --------------------------------------------------------------------------
# 3. the sums histogram (#1974)
# --------------------------------------------------------------------------

def _hist_row(bucket_idx, has_venue, groups, total_sum, total_members):
    return SimpleNamespace(bucket_idx=bucket_idx, has_venue=has_venue,
                           groups=groups, total_sum=total_sum,
                           total_members=total_members)


def _size_row(members, groups, avg_sum, median_sum, distinct_sizes=1):
    return SimpleNamespace(members=members, groups=groups, avg_sum=avg_sum,
                           median_sum=median_sum, distinct_sizes=distinct_sizes)


@pytest.mark.asyncio
async def test_histogram_reports_every_bucket_including_the_empty_ones():
    """A missing bucket and an empty bucket must not look the same.

    The SQL group-by only returns buckets that have rows; the endpoint has to
    put the zeroes back, or "no extreme ladders" and "we did not look" render
    identically.
    """
    resp = await admin_cohort.cohort_sums_histogram(
        request=None,
        db=_db([_hist_row(0, True, 5, 4.0, 10),
                _hist_row(5, False, 2, 14.0, 20)], []),
    )
    labels = [h["bucket"] for h in resp["histogram_all"]]
    assert labels == ["0–1.0 (under)", "1.0–1.5 (slightly over)",
                      "1.5–2.0 (over)", "2.0–3.0 (ladder)",
                      "3.0–5.0 (strong ladder)", "5.0+ (extreme ladder)"]
    assert [h["groups"] for h in resp["histogram_all"]] == [5, 0, 0, 0, 0, 2]
    assert resp["histogram_all"][1]["avg_sum"] is None
    assert resp["groups_scanned"] == 7


@pytest.mark.asyncio
async def test_histogram_venue_only_counts_only_venue_graded_groups():
    resp = await admin_cohort.cohort_sums_histogram(
        request=None,
        db=_db([_hist_row(3, True, 9, 22.5, 40),
                _hist_row(3, False, 4, 10.0, 16)], []),
    )
    assert resp["histogram_all"][3]["groups"] == 13
    assert resp["histogram_venue_only"][3]["groups"] == 9
    assert resp["histogram_all"][3]["avg_sum"] == 2.5
    assert resp["histogram_all"][3]["avg_members"] == 4.3


@pytest.mark.asyncio
async def test_histogram_wire_shape_is_fixed_regardless_of_population():
    tiny = await admin_cohort.cohort_sums_histogram(
        request=None, db=_db([_hist_row(2, True, 1, 1.7, 3)], []))
    vast = await admin_cohort.cohort_sums_histogram(
        request=None, db=_db([_hist_row(2, True, 5_000_000, 8_500_000.0,
                                        15_000_000)], []))
    assert len(tiny["histogram_all"]) == len(vast["histogram_all"]) == 6
    assert len(tiny["histogram_venue_only"]) == len(vast["histogram_venue_only"]) == 6
    assert tiny["histogram_all"][2]["avg_sum"] == vast["histogram_all"][2]["avg_sum"]
    assert vast["sampled"] is False


@pytest.mark.asyncio
async def test_histogram_per_size_is_capped_and_carries_a_median():
    sizes = [_size_row(m, 3, 1.5, 1.4, distinct_sizes=38) for m in range(2, 22)]
    resp = await admin_cohort.cohort_sums_histogram(
        request=None, db=_db([_hist_row(1, True, 114, 171.0, 500)], sizes))
    # the SQL LIMIT 20 is what bounds this; the endpoint must not re-slice
    # a longer list and thereby hide that the bound moved
    assert len(resp["per_size"]) == len(sizes)
    assert resp["per_size"][0] == {"members": 2, "groups": 3,
                                   "avg_sum": 1.5, "median_sum": 1.4}


@pytest.mark.asyncio
async def test_histogram_per_size_announces_what_the_top_n_dropped():
    """A truncated list that does not say it is truncated reads as complete.

    `per_size` was `size_stats[:20]` before #1974 and is `LIMIT 20` after; either
    way a reader seeing 20 rows cannot tell whether that is all of them.
    """
    sizes = [_size_row(m, 3, 1.5, 1.4, distinct_sizes=57) for m in range(2, 22)]
    resp = await admin_cohort.cohort_sums_histogram(
        request=None, db=_db([_hist_row(1, True, 60, 90.0, 300)], sizes))
    assert resp["per_size_shown"] == 20
    assert resp["per_size_total"] == 57


# --------------------------------------------------------------------------
# 4. source tripwire on the fatal idiom
# --------------------------------------------------------------------------

def test_neither_cohort_endpoint_sorts_the_population_before_limiting():
    """`ORDER BY random() ... LIMIT n` is what put both endpoints over the cliff.

    A source assertion, deliberately. No unit test can observe an H12, and the
    defect is a literal idiom rather than a behaviour — so this catches exactly
    the reintroduction it names, and nothing else. It is worth having only
    because the behavioural tests above already assert the property it guards.

    The docstring is stripped first. Written naively this test failed on its own
    subject's PROSE — both endpoints now explain in their docstrings which idiom
    they removed and why, and a grep cannot tell an explanation from a call.
    That is the grep-test failure mode in miniature: it matched a string with no
    behaviour behind it, and it would equally have missed the behaviour arriving
    under a different string.
    """
    import ast
    import inspect

    for fn in (admin_cohort.cohort_provenance_split,
               admin_cohort.cohort_sums_histogram):
        tree = ast.parse(inspect.getsource(fn).lstrip())
        node = tree.body[0]
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:]
        src = ast.unparse(tree)
        assert "ORDER BY random()" not in src, (
            f"{fn.__name__} sorts its whole result set before LIMIT again — "
            "that is the #1974 H12."
        )
        assert "GROUP BY" in src, (
            f"{fn.__name__} no longer aggregates in SQL; its response size is "
            "back to growing with the population."
        )
