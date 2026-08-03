"""Queue 300D — staging the futures population, and putting it back together.

C126 committed the ORACLE
(``scripts/evals/futures_population_subdivision_contract.py`` + its 44-case
corpus). These tests drive the PURE objects the staged build is made of and pin
the refusals that corpus names: ``CROSS_CHUNK_PEER_SPLIT`` /
``FIELD_ROSTER_SPLIT`` (a virtual question is never cut in half),
``GLOBAL_FINALIZATION_MISSING`` / ``PARTIAL_GENERATION_PUBLISHED`` (nothing
publishes until every unit is in), ``LATE_ARRIVAL_NOT_INVALIDATED`` (the roster
moved, so the banked work is void), ``RETRY_NOT_IDEMPOTENT`` and
``NON_OWNER_ADVANCES_CHECKPOINT``.

The load-bearing test is ``test_a_three_chunk_split_merges_back_to_the_monolith``:
a synthetic population aggregated whole, and the same population aggregated in
three chunks and merged, compared on every field the payload consumes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.utils.calibration_phase_ledger import (
    FRESH,
    INVALIDATE,
    MAIN_BUILD_TASK,
    REFUSE,
    RESUME,
    TERMINAL_PARTIAL,
)
from app.utils.calibration_staged_futures import (
    DEFAULT_CENSUS_COLUMNS,
    DISTINCT_CENSUS_COLUMNS,
    GROUP_KEY_COLUMNS,
    STAGED_FUTURES_SCHEMA,
    UNIT_KEY_VM_ID,
    StagedFuturesCursor,
    UndeclaredColumnError,
    UnitChunk,
    advance,
    can_advance,
    collect_unit_results,
    decode_staged_cursor,
    generation_fingerprint,
    is_complete,
    merge_futures_rows,
    new_staged_cursor,
    plan_units,
    unit_key,
)

VERSION = "q300d"
INPUT_FP = "fp-input"
OWNER = "worker-a"


# =============================================================================
# Stage A — the roster and its fingerprint
# =============================================================================


def _roster(*specs) -> list[SimpleNamespace]:
    """``(market_id, source, vm_id, is_grouped)`` tuples as roster rows."""
    return [
        SimpleNamespace(market_id=m, source=s, vm_id=v, is_grouped=g) for m, s, v, g in specs
    ]


def test_the_generation_fingerprint_is_stable_and_order_independent():
    rows = _roster(
        (1, "kalshi", "e:123", True),
        (2, "polymarket", "e:123", True),
        (3, "kalshi", "m:3", False),
    )
    assert generation_fingerprint(rows) == generation_fingerprint(list(reversed(rows)))
    assert len(generation_fingerprint(rows)) == 32


def test_a_changed_roster_changes_the_generation_fingerprint():
    """The late-arrival detector: a market appearing mid-build is a new roster."""
    base = _roster((1, "kalshi", "e:123", True), (2, "polymarket", "e:123", True))
    added = base + _roster((3, "kalshi", "m:3", False))
    removed = base[:1]
    moved = _roster((1, "kalshi", "g:xyz", True), (2, "polymarket", "e:123", True))
    regrouped = _roster((1, "kalshi", "e:123", False), (2, "polymarket", "e:123", True))

    fingerprints = {
        generation_fingerprint(base),
        generation_fingerprint(added),
        generation_fingerprint(removed),
        generation_fingerprint(moved),
        generation_fingerprint(regrouped),
    }
    assert len(fingerprints) == 5


def test_an_empty_roster_still_has_a_fingerprint():
    assert generation_fingerprint([]) != generation_fingerprint(_roster((1, "k", "m:1", False)))


# =============================================================================
# Stage B — a vm_id is never split
# =============================================================================


def test_a_vm_id_is_never_split_across_chunks():
    rows = _roster(
        *[(i, "kalshi", f"g:{i // 3}", True) for i in range(12)],
    )
    chunks = plan_units(rows, max_markets_per_chunk=4)
    placement: dict[str, int] = {}
    for chunk in chunks:
        for vm_id in chunk.vm_ids:
            assert vm_id not in placement, f"{vm_id} appears in two chunks"
            placement[vm_id] = chunk.index
    assert len(placement) == 4


def test_cross_source_peers_of_one_virtual_question_land_in_the_same_chunk():
    """The subtle one. ``mode_prices`` groups by vm_id WITHOUT source and the
    representative window partitions by vm_id WITHOUT source, so e:123 on Kalshi
    and e:123 on Polymarket are peers. Split them and each chunk elects its own
    representative — CROSS_CHUNK_PEER_SPLIT."""
    rows = _roster(
        (1, "kalshi", "e:123", True),
        (2, "kalshi", "e:123", True),
        (3, "polymarket", "e:123", True),
        (4, "polymarket", "e:123", True),
        (5, "kalshi", "m:5", False),
    )
    # A cap small enough that a naive (vm_id, source) split would separate them.
    chunks = plan_units(rows, max_markets_per_chunk=2)
    holder = [chunk for chunk in chunks if "e:123" in chunk.vm_ids]
    assert len(holder) == 1
    assert set(holder[0].market_ids) == {1, 2, 3, 4}


def test_an_oversized_virtual_question_gets_its_own_whole_chunk():
    """Never truncated, never merged with a neighbour."""
    rows = _roster(
        *[(i, "polymarket", "g:huge", True) for i in range(10)],
        (100, "kalshi", "m:100", False),
        (101, "kalshi", "m:101", False),
    )
    chunks = plan_units(rows, max_markets_per_chunk=3)
    huge = [chunk for chunk in chunks if "g:huge" in chunk.vm_ids]
    assert len(huge) == 1
    assert huge[0].vm_ids == ("g:huge",)
    assert huge[0].market_count == 10  # > the cap, and whole


def test_every_market_appears_exactly_once_across_the_plan():
    rows = _roster(*[(i, "kalshi", f"g:{i % 5}", True) for i in range(23)])
    chunks = plan_units(rows, max_markets_per_chunk=6)
    seen = [m for chunk in chunks for m in chunk.market_ids]
    assert sorted(seen) == list(range(23))
    assert len(seen) == len(set(seen))


def test_chunking_is_deterministic_and_the_keys_are_stable():
    rows = _roster(*[(i, "kalshi", f"g:{i % 7}", True) for i in range(20)])
    first = plan_units(rows, max_markets_per_chunk=5)
    second = plan_units(list(reversed(rows)), max_markets_per_chunk=5)
    assert [c.vm_ids for c in first] == [c.vm_ids for c in second]
    assert [c.key for c in first] == [c.key for c in second]
    assert [c.index for c in first] == list(range(len(first)))
    # Keys identify the CONTENT, so a different cut yields different keys.
    recut = plan_units(rows, max_markets_per_chunk=2)
    assert {c.key for c in first} != {c.key for c in recut}


def test_a_duplicate_roster_row_does_not_double_count_a_market():
    rows = _roster((1, "kalshi", "e:1", True), (1, "kalshi", "e:1", True))
    chunks = plan_units(rows, max_markets_per_chunk=10)
    assert chunks[0].market_ids == (1,)


def test_an_empty_roster_plans_no_units():
    assert plan_units([], max_markets_per_chunk=10) == ()


@pytest.mark.parametrize("cap", [0, -1])
def test_a_nonsense_chunk_size_is_refused(cap):
    with pytest.raises(ValueError):
        plan_units(_roster((1, "k", "m:1", False)), max_markets_per_chunk=cap)


@pytest.mark.parametrize(
    "row",
    [
        SimpleNamespace(market_id=1, source="k", vm_id=None, is_grouped=False),
        SimpleNamespace(market_id=1, source="k", vm_id="", is_grouped=False),
        SimpleNamespace(market_id=None, source="k", vm_id="m:1", is_grouped=False),
    ],
)
def test_an_unplaceable_roster_row_is_refused_not_skipped(row):
    """Skipping it would drop real markets while every count looked plausible."""
    with pytest.raises(ValueError):
        plan_units([row], max_markets_per_chunk=10)


def test_a_chunk_key_is_short_and_reproducible():
    chunk = UnitChunk(index=0, vm_ids=("e:1", "e:2"), market_ids=(1, 2))
    assert len(chunk.key) == 16
    assert chunk.key == UnitChunk(index=9, vm_ids=("e:1", "e:2"), market_ids=(7,)).key
    assert unit_key(chunk) == chunk.key
    assert unit_key("abc") == "abc"


# =============================================================================
# Stage C — the merge
# =============================================================================

CENSUS = ("kalshi_included", "published_outcomes", "published_questions")


def _row(bucket_idx, source, category, price_moved, bundle, n, winners, sum_prob, sse, **census):
    fields = {
        "bucket_idx": bucket_idx,
        "source": source,
        "category": category,
        "price_moved": price_moved,
        "is_nonexclusive_bundle": bundle,
        "n": n,
        "winners": winners,
        "avg_prob": (sum_prob / n) if n else 0.0,
        "sum_prob": sum_prob,
        "sum_sq_err": sse,
    }
    for name in CENSUS:
        fields[name] = census.get(name, 0)
    return SimpleNamespace(**fields)


def _merge(chunks, **kwargs):
    kwargs.setdefault("census_columns", CENSUS)
    return merge_futures_rows(chunks, **kwargs)


def test_empty_input_merges_to_an_empty_list():
    assert _merge([]) == []
    assert _merge([[], []]) == []
    assert _merge([[], []], extra_censuses=[{"kalshi_included": 5}]) == []


def test_matching_group_keys_sum_their_bucket_mass():
    rows = _merge(
        [
            [_row(3, "kalshi", "politics", False, False, 10, 4, 3.0, 1.5)],
            [_row(3, "kalshi", "politics", False, False, 6, 2, 2.0, 0.5)],
        ]
    )
    assert len(rows) == 1
    assert rows[0].n == 16
    assert rows[0].winners == 6
    assert rows[0].sum_prob == 5.0
    assert rows[0].sum_sq_err == 2.0
    assert isinstance(rows[0].n, int)
    assert isinstance(rows[0].winners, int)


def test_different_group_keys_stay_separate_rows():
    rows = _merge(
        [
            [_row(3, "kalshi", "politics", False, False, 10, 4, 3.0, 1.5)],
            [_row(3, "kalshi", "politics", True, False, 6, 2, 2.0, 0.5)],
            [_row(4, "kalshi", "politics", False, False, 1, 1, 0.4, 0.36)],
        ]
    )
    assert len(rows) == 3
    assert {r.n for r in rows} == {10, 6, 1}


def test_avg_prob_is_recomputed_from_the_merged_mass():
    """Belt and braces — the payload builder already does this, but a merged row
    must not carry a stale per-chunk average that nobody recomputes."""
    rows = _merge(
        [
            [_row(2, "kalshi", "tech", False, False, 4, 1, 1.0, 0.5)],
            [_row(2, "kalshi", "tech", False, False, 4, 2, 3.0, 0.5)],
        ]
    )
    assert rows[0].avg_prob == pytest.approx(4.0 / 8)
    # NOT the mean of the two per-chunk averages, which happens to agree here
    # only because the chunks are the same size; make that explicit.
    lopsided = _merge(
        [
            [_row(2, "kalshi", "tech", False, False, 1, 0, 0.1, 0.01)],
            [_row(2, "kalshi", "tech", False, False, 9, 9, 8.1, 0.09)],
        ]
    )
    assert lopsided[0].avg_prob == pytest.approx(8.2 / 10)
    assert lopsided[0].avg_prob != pytest.approx((0.1 + 0.9) / 2)


def test_a_zero_n_group_does_not_divide_by_zero():
    rows = _merge([[_row(0, "kalshi", None, False, False, 0, 0, 0.0, 0.0)]])
    assert rows[0].avg_prob == 0.0


def test_census_columns_are_summed_and_broadcast_onto_every_row():
    rows = _merge(
        [
            [
                _row(1, "kalshi", "a", False, False, 5, 1, 1.0, 1.0,
                     kalshi_included=100, published_outcomes=40, published_questions=7),
                _row(2, "kalshi", "a", False, False, 5, 1, 1.0, 1.0,
                     kalshi_included=100, published_outcomes=40, published_questions=7),
            ],
            [
                _row(3, "kalshi", "a", False, False, 5, 1, 1.0, 1.0,
                     kalshi_included=25, published_outcomes=10, published_questions=3),
            ],
        ]
    )
    assert len(rows) == 3
    for row in rows:
        assert row.kalshi_included == 125
        assert row.published_outcomes == 50
        assert row.published_questions == 10
    # The consumer reads census off rows[0] only, so "constant across every row"
    # is the property that has to survive finalization.
    assert len({r.kalshi_included for r in rows}) == 1


def test_a_census_nobody_could_measure_stays_unknown_and_never_becomes_zero():
    """The 300C lie this exists to prevent: unknown rendered as a confident 0."""
    rows = _merge(
        [
            [_row(1, "kalshi", "a", False, False, 5, 1, 1.0, 1.0,
                  kalshi_included=None, published_outcomes=None, published_questions=None)],
            [_row(2, "kalshi", "a", False, False, 5, 1, 1.0, 1.0,
                  kalshi_included=None, published_outcomes=None, published_questions=None)],
        ]
    )
    for row in rows:
        assert row.kalshi_included is None
        assert row.published_outcomes is None
        assert row.published_questions is None


def test_a_partially_unknown_census_sums_the_chunks_that_did_measure():
    rows = _merge(
        [
            [_row(1, "kalshi", "a", False, False, 5, 1, 1.0, 1.0,
                  kalshi_included=None, published_outcomes=4, published_questions=1)],
            [_row(2, "kalshi", "a", False, False, 5, 1, 1.0, 1.0,
                  kalshi_included=8, published_outcomes=6, published_questions=2)],
        ]
    )
    assert rows[0].kalshi_included == 8
    assert rows[0].published_outcomes == 10
    assert rows[0].published_questions == 3


def test_a_census_column_no_chunk_returned_is_unknown_not_zero():
    rows = merge_futures_rows(
        [[_row(1, "kalshi", "a", False, False, 5, 1, 1.0, 1.0)]],
        census_columns=CENSUS + ("cb_coverage_total",),
    )
    assert rows[0].cb_coverage_total is None
    assert rows[0].kalshi_included == 0  # measured zero, and it stays a zero


def test_an_empty_chunks_census_can_be_supplied_out_of_band():
    """A chunk whose vm_ids all get filtered out of ``deduped`` returns no rows,
    so it carries no census; ``extra_censuses`` is how its candidate-side counts
    still reach the total."""
    rows = _merge(
        [[_row(1, "kalshi", "a", False, False, 5, 1, 1.0, 1.0, kalshi_included=10)], []],
        extra_censuses=[{"kalshi_included": 7, "published_outcomes": 0, "published_questions": 0}],
    )
    assert rows[0].kalshi_included == 17


def test_only_the_first_row_of_a_chunk_votes_in_the_census():
    """It is CROSS JOINed off a 1-row summary, so every row in a chunk carries
    the same value; counting each row would multiply the census by the bucket
    count."""
    rows = _merge(
        [
            [
                _row(1, "kalshi", "a", False, False, 1, 0, 0.5, 0.25, kalshi_included=9),
                _row(2, "kalshi", "a", False, False, 1, 0, 0.5, 0.25, kalshi_included=9),
                _row(3, "kalshi", "a", False, False, 1, 0, 0.5, 0.25, kalshi_included=9),
            ]
        ]
    )
    assert rows[0].kalshi_included == 9


def test_rows_come_back_sorted_by_the_group_key_with_nulls_last():
    rows = _merge(
        [
            [
                _row(5, "polymarket", "sports", True, False, 1, 0, 0.5, 0.25),
                _row(1, "kalshi", None, False, False, 1, 0, 0.5, 0.25),
                _row(1, None, "politics", False, False, 1, 0, 0.5, 0.25),
                _row(1, "kalshi", "politics", True, False, 1, 0, 0.5, 0.25),
                _row(1, "kalshi", "politics", False, True, 1, 0, 0.5, 0.25),
                _row(1, "kalshi", "politics", False, False, 1, 0, 0.5, 0.25),
            ]
        ]
    )
    assert [(r.bucket_idx, r.source, r.category, r.price_moved, r.is_nonexclusive_bundle) for r in rows] == [
        (1, "kalshi", "politics", False, False),
        (1, "kalshi", "politics", False, True),
        (1, "kalshi", "politics", True, False),
        (1, "kalshi", None, False, False),
        (1, None, "politics", False, False),
        (5, "polymarket", "sports", True, False),
    ]


def test_a_null_category_merges_with_another_null_category():
    rows = _merge(
        [
            [_row(1, "kalshi", None, False, False, 3, 1, 1.0, 0.5)],
            [_row(1, "kalshi", None, False, False, 2, 0, 0.5, 0.25)],
        ]
    )
    assert len(rows) == 1
    assert rows[0].n == 5


def test_a_sqlalchemy_style_row_merges_the_same_as_a_namespace():
    class FakeRow:
        def __init__(self, mapping):
            self._mapping = mapping

        def __getattr__(self, name):
            return self._mapping[name]

    base = vars(_row(1, "kalshi", "a", False, False, 4, 2, 2.0, 1.0, kalshi_included=3))
    rows = _merge([[FakeRow(dict(base))], [_row(1, "kalshi", "a", False, False, 1, 0, 0.5, 0.25)]])
    assert rows[0].n == 5
    assert rows[0].kalshi_included == 3


def test_an_undeclared_column_is_refused_rather_than_silently_dropped():
    row = _row(1, "kalshi", "a", False, False, 1, 0, 0.5, 0.25)
    row.brand_new_census_column = 42
    with pytest.raises(UndeclaredColumnError) as excinfo:
        _merge([[row]])
    assert "brand_new_census_column" in str(excinfo.value)


def test_the_declared_column_lists_match_the_production_statement():
    assert GROUP_KEY_COLUMNS == (
        "bucket_idx",
        "source",
        "category",
        "price_moved",
        "is_nonexclusive_bundle",
    )
    assert DISTINCT_CENSUS_COLUMNS <= set(DEFAULT_CENSUS_COLUMNS)
    assert "published_questions" in DISTINCT_CENSUS_COLUMNS


# =============================================================================
# The equivalence oracle: monolith vs a three-chunk split
# =============================================================================

#: ``(vm_id, market_id, source, category, price_moved, bundle, prob, is_winner)``
#: Probabilities are exact binary fractions so the comparison below is exact;
#: the float-associativity caveat gets its own test underneath.
POPULATION = [
    ("e:1", 11, "kalshi", "politics", False, False, 0.25, False),
    ("e:1", 11, "kalshi", "politics", False, False, 0.75, True),
    ("e:1", 12, "polymarket", "politics", True, False, 0.5, True),
    ("g:2", 21, "kalshi", "sports", False, False, 0.125, False),
    ("g:2", 21, "kalshi", "sports", False, True, 0.875, True),
    ("g:2", 22, "kalshi", "sports", True, False, 0.25, False),
    ("m:3", 31, "polymarket", None, False, False, 0.5, False),
    ("m:3", 31, "polymarket", None, False, False, 0.5, True),
    ("m:4", 41, "kalshi", "tech", True, False, 0.75, False),
    ("m:5", 51, "polymarket", "tech", False, False, 0.25, True),
    ("m:5", 51, "polymarket", "tech", False, False, 0.375, False),
    # Two questions deliberately land in the SAME bucket group as questions in
    # other chunks — a price band is not a question, so the same band really is
    # populated from several chunks and the merge really has to fold them.
    ("m:6", 61, "kalshi", "politics", False, False, 0.25, True),
    ("m:7", 71, "polymarket", "tech", False, False, 0.25, False),
]


def _pg_order(key: tuple) -> tuple:
    """``ORDER BY ...`` the way Postgres does it: NULLs last, ASC.

    Written out here rather than imported so the equivalence assertion below is
    graded against an independent oracle, not against the module's own helper.
    """
    return tuple((1,) if value is None else (0, value) for value in key)


def _aggregate(population) -> list[SimpleNamespace]:
    """What the production statement does to a set of published outcomes.

    Group by the five keys, sum the mass, and CROSS JOIN a census computed over
    the same scope — ``COUNT(*)``-shaped (``kalshi_included``,
    ``published_outcomes``) and ``COUNT(DISTINCT ...)``-shaped
    (``published_questions``) alike.
    """
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for vm_id, _market_id, source, category, moved, bundle, prob, winner in population:
        bucket_idx = min(int(prob * 10), 9)
        key = (bucket_idx, source, category, moved, bundle)
        acc = groups.get(key)
        if acc is None:
            acc = {"n": 0, "winners": 0, "sum_prob": 0.0, "sum_sq_err": 0.0}
            groups[key] = acc
            order.append(key)
        acc["n"] += 1
        acc["winners"] += 1 if winner else 0
        acc["sum_prob"] += prob
        acc["sum_sq_err"] += (prob - (1.0 if winner else 0.0)) ** 2

    census = {
        "kalshi_included": sum(1 for row in population if row[2] == "kalshi"),
        "published_outcomes": len(population),
        "published_questions": len({row[0] for row in population}),
    }
    out = []
    for key in sorted(order, key=_pg_order):
        acc = groups[key]
        out.append(
            _row(*key, acc["n"], acc["winners"], acc["sum_prob"], acc["sum_sq_err"], **census)
        )
    return out


def _consumed(row) -> tuple:
    """Every field the payload builder reads off a futures bucket row."""
    return (
        row.bucket_idx,
        row.source,
        row.category,
        row.price_moved,
        row.is_nonexclusive_bundle,
        row.n,
        row.winners,
        row.sum_prob,
        row.sum_sq_err,
        row.avg_prob,
        row.kalshi_included,
        row.published_outcomes,
        row.published_questions,
    )


def test_a_three_chunk_split_merges_back_to_the_monolith():
    """The whole point of Queue 300D, in one assertion.

    Cut on whole ``vm_id``s (so ``e:1``'s two sources stay together), aggregate
    each chunk exactly as the statement would, merge — and every field the
    payload consumes, including the two ``COUNT(*)`` census columns and the
    ``COUNT(DISTINCT vm_id)`` one, matches the un-split build.
    """
    monolith = _aggregate(POPULATION)

    chunk_plan = (("e:1", "g:2", "m:7"), ("m:3", "m:4", "m:6"), ("m:5",))
    chunks = [
        _aggregate([row for row in POPULATION if row[0] in vm_ids]) for vm_ids in chunk_plan
    ]
    # The split is only a real test if some bucket group is genuinely populated
    # by more than one chunk; otherwise the merge is a concatenation.
    assert sum(len(chunk) for chunk in chunks) > len(monolith)

    merged = _merge(chunks)

    assert len(merged) == len(monolith)
    assert [_consumed(r) for r in merged] == [_consumed(r) for r in monolith]


def test_the_split_matches_the_plan_the_planner_would_actually_produce():
    """The equivalence above is only meaningful for a cut ``plan_units`` allows."""
    roster = _roster(
        *sorted({(row[1], row[2], row[0], row[0].startswith(("e:", "g:"))) for row in POPULATION})
    )
    chunks = plan_units(roster, max_markets_per_chunk=3)
    monolith = _aggregate(POPULATION)
    merged = _merge(
        [_aggregate([row for row in POPULATION if row[0] in chunk.vm_ids]) for chunk in chunks]
    )
    assert [_consumed(r) for r in merged] == [_consumed(r) for r in monolith]


def test_one_chunk_per_virtual_question_still_merges_to_the_monolith():
    """The pathological cut: maximum chunks, maximum census fragmentation."""
    monolith = _aggregate(POPULATION)
    vm_ids = sorted({row[0] for row in POPULATION})
    merged = _merge([_aggregate([r for r in POPULATION if r[0] == vm]) for vm in vm_ids])
    assert [_consumed(r) for r in merged] == [_consumed(r) for r in monolith]


def test_float_reassociation_is_the_one_thing_the_merge_cannot_promise_bit_exactly():
    """Stated, not papered over: summing 0.1 in two groups and adding the two
    partial sums is not bit-identical to summing all of them at once. The payload
    rounds to 4 decimals, so the PUBLISHED number is unaffected — but the raw
    double can differ in the last bits and this test says so out loud."""
    population = [("m:%d" % i, i, "kalshi", "a", False, False, 0.1, False) for i in range(10)]
    monolith = _aggregate(population)
    merged = _merge(
        [
            _aggregate(population[:3]),
            _aggregate(population[3:7]),
            _aggregate(population[7:]),
        ]
    )
    assert len(merged) == len(monolith) == 1
    assert merged[0].sum_prob == pytest.approx(monolith[0].sum_prob)
    assert round(merged[0].sum_prob, 4) == round(monolith[0].sum_prob, 4)


# =============================================================================
# The cursor
# =============================================================================


def _chunks() -> tuple[UnitChunk, ...]:
    return plan_units(
        _roster(
            (1, "kalshi", "e:1", True),
            (2, "polymarket", "e:1", True),
            (3, "kalshi", "m:3", False),
            (4, "kalshi", "m:4", False),
        ),
        # One market per chunk, so ``e:1`` (two markets, two sources, one
        # question) is the oversized-unit case AND the peer case at once.
        max_markets_per_chunk=1,
    )


GENERATION_FP = generation_fingerprint(
    _roster(
        (1, "kalshi", "e:1", True),
        (2, "polymarket", "e:1", True),
        (3, "kalshi", "m:3", False),
        (4, "kalshi", "m:4", False),
    )
)


def _raw_cursor(**overrides) -> dict:
    raw = {
        "schema": STAGED_FUTURES_SCHEMA,
        "task": MAIN_BUILD_TASK,
        "unit_key": UNIT_KEY_VM_ID,
        "population_version": VERSION,
        "input_fingerprint": INPUT_FP,
        "generation_fingerprint": GENERATION_FP,
        "generation": 5,
        "owner": OWNER,
        "lease_expires_at": 0.0,
        "committed_units": [_chunks()[0].key],
        "unit_results": {_chunks()[0].key: [{"bucket_idx": 1}]},
        "terminal": TERMINAL_PARTIAL,
    }
    raw.update(overrides)
    return raw


def _decode(raw, *, owner=OWNER, version=VERSION, input_fp=INPUT_FP, gen_fp=GENERATION_FP, now=100.0):
    return decode_staged_cursor(
        raw,
        expected_population_version=version,
        expected_input_fingerprint=input_fp,
        expected_generation_fingerprint=gen_fp,
        owner=owner,
        generation=9,
        now=now,
    )


def test_an_absent_cursor_is_fresh_not_an_error():
    cursor, action = _decode(None)
    assert action == FRESH
    assert cursor.committed_units == ()
    assert cursor.owner == OWNER


def test_a_matching_cursor_resumes_with_its_banked_units():
    cursor, action = _decode(_raw_cursor())
    assert action == RESUME
    assert cursor.committed_units == (_chunks()[0].key,)
    assert cursor.result(_chunks()[0]) == [{"bucket_idx": 1}]


@pytest.mark.parametrize(
    "override",
    [
        {"schema": "something-else"},
        {"task": "other_task"},
        {"unit_key": "source"},
        {"population_version": "q999"},
        {"input_fingerprint": "fp-changed"},
        {"committed_units": "not-a-list"},
        {"unit_results": "not-a-dict"},
    ],
)
def test_anything_we_cannot_vouch_for_is_invalidated(override):
    _, action = _decode(_raw_cursor(**override))
    assert action == INVALIDATE


def test_a_non_dict_cursor_is_invalidated():
    _, action = _decode(["not", "a", "cursor"])
    assert action == INVALIDATE


def test_a_moved_roster_invalidates_every_banked_unit():
    """LATE_ARRIVAL_NOT_INVALIDATED: half the buckets against yesterday's roster
    and half against today's is not a population."""
    cursor, action = _decode(_raw_cursor(), gen_fp="fp-a-market-arrived-late")
    assert action == INVALIDATE
    assert cursor.committed_units == ()
    assert cursor.generation_fingerprint == "fp-a-market-arrived-late"


def test_a_population_version_change_invalidates_every_banked_unit():
    cursor, action = _decode(_raw_cursor(), version="q999")
    assert action == INVALIDATE
    assert cursor.committed_units == ()
    assert cursor.population_version == "q999"


def test_a_live_lease_held_by_another_owner_is_refused_not_stolen():
    cursor, action = _decode(
        _raw_cursor(owner="worker-b", lease_expires_at=500.0), now=100.0
    )
    assert action == REFUSE
    assert cursor.owner == "worker-b"
    assert cursor.committed_units == ()


def test_an_expired_lease_from_another_owner_is_resumable():
    _, action = _decode(_raw_cursor(owner="worker-b", lease_expires_at=50.0), now=100.0)
    assert action == RESUME


def test_our_own_live_lease_is_never_refused_to_us():
    _, action = _decode(_raw_cursor(owner=OWNER, lease_expires_at=500.0), now=100.0)
    assert action == RESUME


def test_a_unit_marked_committed_with_no_stored_rows_is_not_resumed():
    cursor, action = _decode(_raw_cursor(unit_results={}))
    assert cursor.committed_units == ()
    assert action == FRESH


def test_the_cursor_payload_round_trips():
    cursor, _ = _decode(_raw_cursor())
    reloaded, action = _decode(cursor.as_payload())
    assert action == RESUME
    assert reloaded.committed_units == cursor.committed_units
    assert reloaded.unit_results == cursor.unit_results


def test_advancing_banks_a_unit():
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    advanced = advance(cursor, chunks[0], [{"n": 1}], owner=OWNER, lease_expires_at=500.0)
    assert advanced.committed_units == (chunks[0].key,)
    assert advanced.result(chunks[0]) == [{"n": 1}]
    assert advanced.lease_expires_at == 500.0
    # The input cursor is untouched — a new cursor, never a mutation.
    assert cursor.committed_units == ()


def test_re_advancing_the_same_unit_is_idempotent():
    """RETRY_NOT_IDEMPOTENT: a retry of an already-committed unit must not
    duplicate it, and must not quietly replace what was validated and banked."""
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    once = advance(cursor, chunks[0], [{"n": 1}], owner=OWNER, lease_expires_at=100.0)
    twice = advance(once, chunks[0], [{"n": 999}], owner=OWNER, lease_expires_at=200.0)
    assert twice.committed_units == (chunks[0].key,)
    assert twice.result(chunks[0]) == [{"n": 1}]
    assert twice.lease_expires_at == 200.0  # the lease still renews


def test_a_non_owner_cannot_advance_the_cursor():
    """NON_OWNER_ADVANCES_CHECKPOINT, enforced in the helper rather than trusted
    to the call site — and observable, because is_complete stays False."""
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    assert can_advance(cursor, "worker-b") is False
    refused = advance(cursor, chunks[0], [{"n": 1}], owner="worker-b", lease_expires_at=1.0)
    assert refused == cursor
    assert refused.committed_units == ()


def test_an_unclaimed_cursor_can_be_taken_by_anyone():
    chunks = _chunks()
    cursor = StagedFuturesCursor(population_version=VERSION)
    assert can_advance(cursor, "worker-b") is True
    taken = advance(cursor, chunks[0], [], owner="worker-b", lease_expires_at=1.0)
    assert taken.owner == "worker-b"


def test_nothing_is_complete_until_every_planned_unit_is_banked():
    chunks = _chunks()
    assert len(chunks) >= 3
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    for index, chunk in enumerate(chunks):
        assert is_complete(cursor, chunks) is False, index
        cursor = advance(cursor, chunk, [{"n": index}], owner=OWNER, lease_expires_at=1.0)
    assert is_complete(cursor, chunks) is True


def test_an_empty_plan_is_vacuously_complete():
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    assert is_complete(cursor, ()) is True


def test_a_banked_unit_that_matches_no_planned_chunk_blocks_completion():
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    for chunk in chunks:
        cursor = advance(cursor, chunk, [], owner=OWNER, lease_expires_at=1.0)
    cursor = advance(cursor, "a-key-from-another-plan", [], owner=OWNER, lease_expires_at=1.0)
    assert is_complete(cursor, chunks) is False


def test_banked_units_are_collected_in_plan_order_whatever_the_commit_order():
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    for chunk in reversed(chunks):
        cursor = advance(
            cursor, chunk, [{"index": chunk.index}], owner=OWNER, lease_expires_at=1.0
        )
    assert collect_unit_results(cursor, chunks) == [
        [{"index": chunk.index}] for chunk in chunks
    ]


def test_progress_is_monotonic_across_three_beats_and_only_the_last_publishes():
    """The visible payoff: a build that cannot finish in one beat finishes in
    three, and publishes exactly once."""
    chunks = _chunks()
    raw = None
    published = []
    banked_over_time = []

    for beat, chunk in enumerate(chunks):
        cursor, action = _decode(raw)
        assert action in (FRESH, RESUME)
        cursor = advance(
            cursor, chunk, [{"beat": beat}], owner=OWNER, lease_expires_at=float(beat)
        )
        banked_over_time.append(len(cursor.committed_units))
        if is_complete(cursor, chunks):
            published.append(merge_futures_rows([], census_columns=CENSUS))
        raw = cursor.as_payload()

    assert banked_over_time == sorted(banked_over_time)
    assert banked_over_time == list(range(1, len(chunks) + 1))
    assert len(published) == 1
