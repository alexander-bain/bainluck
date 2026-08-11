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

import gc
import json
import random
import tracemalloc
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.utils.durable_state import canonical_json
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
    REASON_UNENCODED_UNITS,
    UndeclaredColumnError,
    UnencodableValueError,
    UnitChunk,
    bucket_of,
    advance,
    can_advance,
    collect_unit_results,
    decode_staged_cursor,
    decode_staged_cursor_detailed,
    decode_unit_rows,
    encode_accumulator,
    encode_unit_rows,
    fold_unit_rows,
    generation_fingerprint,
    is_complete,
    is_encoded_unit_rows,
    merge_futures_rows,
    new_staged_cursor,
    plan_units,
    retain_planned_units,
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
    chunks = plan_units(rows, buckets=4)
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
    # Few enough buckets that a naive (vm_id, source) split would separate them.
    chunks = plan_units(rows, buckets=2)
    holder = [chunk for chunk in chunks if "e:123" in chunk.vm_ids]
    assert len(holder) == 1
    # Containment, not equality: a neighbouring question may share the bucket.
    assert {1, 2, 3, 4} <= set(holder[0].market_ids)


def test_an_oversized_virtual_question_is_never_truncated():
    """Never truncated, never split.

    CAL-P016 narrowed what this can promise, deliberately. Under the positional
    planner an oversized ``vm_id`` got a chunk to ITSELF; under content-addressed
    bucketing it may share a bucket with whatever else hashes there, because unit
    size is a distribution and stability is what is being bought. The invariant
    that actually matters is unchanged and is what is asserted: all ten of the
    oversized question's markets are in ONE unit, whole.
    """
    rows = _roster(
        *[(i, "polymarket", "g:huge", True) for i in range(10)],
        (100, "kalshi", "m:100", False),
        (101, "kalshi", "m:101", False),
    )
    chunks = plan_units(rows, buckets=3)
    huge = [chunk for chunk in chunks if "g:huge" in chunk.vm_ids]
    assert len(huge) == 1
    assert set(range(10)) <= set(huge[0].market_ids)


def test_every_market_appears_exactly_once_across_the_plan():
    rows = _roster(*[(i, "kalshi", f"g:{i % 5}", True) for i in range(23)])
    chunks = plan_units(rows, buckets=6)
    seen = [m for chunk in chunks for m in chunk.market_ids]
    assert sorted(seen) == list(range(23))
    assert len(seen) == len(set(seen))


def test_chunking_is_deterministic_and_the_keys_are_stable():
    rows = _roster(*[(i, "kalshi", f"g:{i % 7}", True) for i in range(20)])
    first = plan_units(rows, buckets=5)
    second = plan_units(list(reversed(rows)), buckets=5)
    assert [c.vm_ids for c in first] == [c.vm_ids for c in second]
    assert [c.key for c in first] == [c.key for c in second]
    # Unit index is now the BUCKET index, so it is strictly increasing and inside
    # the bucket range — but not contiguous, because an empty bucket plans no
    # unit at all rather than an empty one.
    indices = [c.index for c in first]
    assert indices == sorted(set(indices))
    assert all(0 <= i < 5 for i in indices)
    # Keys identify the CONTENT, so a different cut yields different keys.
    recut = plan_units(rows, buckets=2)
    assert {c.key for c in first} != {c.key for c in recut}


def test_a_duplicate_roster_row_does_not_double_count_a_market():
    rows = _roster((1, "kalshi", "e:1", True), (1, "kalshi", "e:1", True))
    chunks = plan_units(rows, buckets=10)
    assert chunks[0].market_ids == (1,)


def _plan_units_per_vm_reference(rows, *, buckets):
    """The per-``vm_id`` accumulator CAL-P036 replaced, kept as the ORACLE.

    CAL-P036 re-keyed the planner's intermediates from ``vm_id`` to bucket index
    for memory reasons alone, so "the output did not move" is the entire safety
    argument and it is worth checking against the real prior code rather than
    against a golden file that would have to be regenerated by the very change
    it is meant to police.
    """
    by_vm: dict[str, list[int]] = {}
    seen: dict[str, set[int]] = {}
    members_by_vm: dict[str, set[str]] = {}
    for row in rows:
        vm_id = str(row.vm_id)
        market_id = int(row.market_id)
        bucket = by_vm.setdefault(vm_id, [])
        market_seen = seen.setdefault(vm_id, set())
        if market_id not in market_seen:
            market_seen.add(market_id)
            bucket.append(market_id)
        members_by_vm.setdefault(vm_id, set()).add(
            "\x1e".join(
                (str(market_id), str(row.source), vm_id, "1" if row.is_grouped else "0")
            )
        )
    grouped: dict[int, list[str]] = {}
    for vm_id in sorted(by_vm):
        grouped.setdefault(bucket_of(vm_id, buckets), []).append(vm_id)
    chunks = []
    for index in sorted(grouped):
        vm_ids = grouped[index]
        market_ids: list[int] = []
        members: set[str] = set()
        for vm_id in vm_ids:
            market_ids.extend(by_vm[vm_id])
            members |= members_by_vm[vm_id]
        chunks.append(
            UnitChunk(
                index=index,
                vm_ids=tuple(vm_ids),
                market_ids=tuple(sorted(market_ids)),
                members=tuple(sorted(members)),
                buckets=buckets,
            )
        )
    return tuple(chunks)


@pytest.mark.parametrize("buckets", [1, 2, 7, 128])
def test_the_planner_is_output_identical_to_the_per_vm_id_accumulator(buckets):
    """CAL-P036 moved the intermediates, and nothing else may move with them."""
    rng = random.Random(20260811)
    rows = []
    for market_id in range(1, 1200):
        if rng.random() < 0.4:
            rows.append(
                _roster((market_id, rng.choice(("kalshi", "polymarket")),
                         f"e:{rng.randint(1, 90)}", True))[0]
            )
        else:
            rows.append(
                _roster((market_id, rng.choice(("kalshi", "polymarket")),
                         f"m:{market_id}", False))[0]
            )
        # A second source for the same market, which is what makes one
        # market_id able to carry two different vm_ids.
        if rng.random() < 0.15:
            rows.append(_roster((market_id, "polymarket", f"m:{market_id}", False))[0])

    produced = plan_units(rows, buckets=buckets)
    expected = _plan_units_per_vm_reference(rows, buckets=buckets)
    assert produced == expected
    assert [c.key for c in produced] == [c.key for c in expected]
    assert [c.member_digest for c in produced] == [c.member_digest for c in expected]


def test_a_market_under_two_virtual_questions_is_kept_under_both():
    """The dedupe is per ``vm_id`` and deliberately NOT global.

    ``vm_id`` is derived with SOURCE-SCOPED group and event sizes, so the same
    ``market_id`` can be a peer inside ``e:1`` on one source and its own
    ``m:7`` on another. Both are real memberships and the chunk restriction
    predicate needs both.

    This is the case a bucket-keyed accumulator can most easily get wrong:
    deduping on ``market_id`` alone inside a bucket looks equivalent, costs less
    memory, and silently shrinks a chunk. Pinned because CAL-P036 rewrote
    exactly this dedupe.
    """
    rows = _roster(
        (7, "kalshi", "e:1", True),
        (8, "kalshi", "e:1", True),
        (7, "polymarket", "m:7", False),
    )
    # One bucket, so both virtual questions land in the same chunk and market 7
    # is present TWICE — once for each virtual question it belongs to.
    (only,) = plan_units(rows, buckets=1)
    assert only.market_ids == (7, 7, 8)
    assert only.vm_ids == ("e:1", "m:7")


def test_planning_does_not_allocate_a_container_per_virtual_question():
    """The capacity guard — CAL-P036's whole reason to exist.

    The planner used to key three intermediates on ``vm_id``, and ``vm_id`` is
    near-unique in this population (an ungrouped market's virtual question is
    ``m:<market_id>``). An empty CPython ``set`` costs 216 bytes regardless of
    contents, so a per-``vm_id`` accumulator reserves at least

        2 sets x 216 bytes = 432 bytes PER ROW

    in ``seen`` and ``members_by_vm`` alone, before any payload. Measured at the
    production roster cardinality (669,383 rows) that shape peaked at ~440 MB
    of transient inside this one function, on a worker limited to 512 MB — which
    is why ~62% of calibration beats were being hard-killed.

    The bar is expressed per row against an all-unique roster, where distinct
    ``vm_id`` count equals row count. It sits below the 432 B/row structural
    floor of the old shape plus its payload (measured ~691 B/row here) and well
    above the bucket-keyed shape (measured ~383 B/row), so it fails on a
    reintroduced per-``vm_id`` container and passes with real headroom.
    """
    rows = 40_000
    roster = [
        SimpleNamespace(
            market_id=i, source="kalshi" if i % 2 else "polymarket",
            vm_id=f"m:{i}", is_grouped=False,
        )
        for i in range(1, rows + 1)
    ]
    gc.collect()
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        chunks = plan_units(roster, buckets=128)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert len(chunks) == 128
    bytes_per_row = (peak - before) / rows
    assert bytes_per_row < 550, (
        f"planning cost {bytes_per_row:.0f} B/row; a per-vm_id accumulator's set "
        f"headers alone are 432 B/row, so this has regressed to one container "
        f"per virtual question"
    )


def test_an_empty_roster_plans_no_units():
    assert plan_units([], buckets=10) == ()


@pytest.mark.parametrize("cap", [0, -1])
def test_a_nonsense_chunk_size_is_refused(cap):
    with pytest.raises(ValueError):
        plan_units(_roster((1, "k", "m:1", False)), buckets=cap)


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
        plan_units([row], buckets=10)


def test_a_chunk_key_is_short_and_reproducible():
    chunk = UnitChunk(index=0, vm_ids=("e:1", "e:2"), market_ids=(1, 2), buckets=16)
    assert len(chunk.key) == 16
    assert chunk.key == UnitChunk(index=0, vm_ids=(), market_ids=(), buckets=16).key
    assert unit_key(chunk) == chunk.key
    assert unit_key("abc") == "abc"


def test_a_chunk_key_is_its_slot_and_survives_the_units_contents_moving():
    """REVERSED BY CAL-P028, deliberately — this used to assert the opposite.

    CAL-P016 put the unit's full roster MEMBERSHIP in the key so that a market
    resolving into a question could not be silently resumed over. The hole was
    real. The remedy was fatal, and production measured the cost on 2026-08-10:
    a beat that completed 15 units began by dropping 16, so the cursor went
    20 -> 19 across a fully productive beat and the 128-unit build could never
    finish. ``/api/calibration`` was 8.44 days stale behind 181 failed beats.

    So the key is now the SLOT, and staleness is measured instead of obeyed —
    see ``roster_drift`` and ``test_calibration_staged_convergence_p028.py``.
    What must still be true is pinned below: membership is still digested, it
    just no longer throws work away.
    """
    base = UnitChunk(index=0, vm_ids=("e:1",), market_ids=(1,), buckets=4)
    gained_a_market = UnitChunk(index=0, vm_ids=("e:1",), market_ids=(1, 2), buckets=4)
    assert base.key == gained_a_market.key

    planned = plan_units(_roster((1, "kalshi", "e:1", True)), buckets=4)
    gained_a_source = plan_units(
        _roster((1, "kalshi", "e:1", True), (1, "polymarket", "e:1", True)), buckets=4
    )
    regrouped = plan_units(_roster((1, "kalshi", "e:1", False)), buckets=4)
    # Same slot, so one key — the unit is not re-keyed by any of it...
    assert len({planned[0].key, gained_a_source[0].key, regrouped[0].key}) == 1
    # ...while source and is_grouped remain visible in the MEMBERSHIP digest,
    # which is what reports the drift.
    assert (
        len(
            {
                planned[0].member_digest,
                gained_a_source[0].member_digest,
                regrouped[0].member_digest,
            }
        )
        == 3
    )


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
    chunks = plan_units(roster, buckets=3)
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
        # Enough buckets to separate all three questions, so ``e:1`` (two
        # markets, two sources, one question) is the multi-market-unit case AND
        # the cross-source peer case at once, in a plan of three real units.
        buckets=4,
    )


GENERATION_FP = generation_fingerprint(
    _roster(
        (1, "kalshi", "e:1", True),
        (2, "polymarket", "e:1", True),
        (3, "kalshi", "m:3", False),
        (4, "kalshi", "m:4", False),
    )
)


#: The one row the raw-cursor fixture banks. Carries a ``bucket_idx`` because a
#: row without one is a census carrier, not a bucket — which is what the
#: finalizer has always done with a null-keyed row, and what the fold does now.
_BANKED_ROW = {"bucket_idx": 1, "n": 1}


def _folded_dicts(cursor) -> tuple[list[dict], list[dict]]:
    """The cursor's running fold as ``(bucket dicts, carrier dicts)``."""
    buckets, carriers = cursor.folded()
    return _row_dicts(buckets), _row_dicts(carriers)


def _mass(cursor) -> dict[tuple, tuple]:
    """Bucket mass keyed by group key — what a fold is allowed to be judged on.

    Comparing whole rows would pin ``avg_prob`` and column ORDER, neither of
    which the fold promises; the sums by group key are the thing that must not
    move.
    """
    buckets, _carriers = cursor.folded()
    return {
        (r.bucket_idx, r.source, r.category, r.price_moved, r.is_nonexclusive_bundle): (
            r.n,
            r.winners,
            r.sum_prob,
            r.sum_sq_err,
        )
        for r in buckets
    }


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
        # CAL-P033 — DECLARED REVERSAL. This helper used to write the rows as a
        # bare ``[{"bucket_idx": 1}]``, which is what the cursor really stored
        # and is the shape the durable round trip destroys: production wrote
        # driver ``Row`` objects, ``canonical_json``'s ``default=str``
        # stringified them, and the next beat resumed ``list[str]``. Banked rows
        # are now an ``encode_unit_rows`` envelope, so this helper writes one.
        # CAL-P034 — SECOND DECLARED REVERSAL, same helper. The cursor no longer
        # holds units at all; it holds the running fold they were summed into.
        # Built through the real fold rather than hand-written, so the fixture
        # cannot drift from what ``advance`` actually produces.
        "accumulator": encode_accumulator(*fold_unit_rows([], [], [_BANKED_ROW])),
        "terminal": TERMINAL_PARTIAL,
    }
    raw.update(overrides)
    return raw


def _row_dicts(rows) -> list[dict]:
    """Banked rows as plain dicts.

    Rows come back as ``SimpleNamespace`` now — the same type
    ``calibration_main_build.decode_rows`` produces and the type finalization
    already expects — so the tests below compare on contents, not on the
    container type they used to assert.
    """
    return [dict(vars(row)) for row in rows or []]


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
    assert _mass(cursor) == {(1, None, None, None, None): (1, 0, 0.0, 0.0)}


@pytest.mark.parametrize(
    "override",
    [
        {"schema": "something-else"},
        {"task": "other_task"},
        {"unit_key": "source"},
        {"population_version": "q999"},
        {"input_fingerprint": "fp-changed"},
        {"committed_units": "not-a-list"},
        {"accumulator": "not-a-dict"},
        {"accumulator": None},
    ],
)
def test_anything_we_cannot_vouch_for_is_invalidated(override):
    _, action = _decode(_raw_cursor(**override))
    assert action == INVALIDATE


def test_a_non_dict_cursor_is_invalidated():
    _, action = _decode(["not", "a", "cursor"])
    assert action == INVALIDATE


def test_a_moved_roster_no_longer_discards_the_whole_cursor():
    """CAL-P016 — the deliberate semantic change, and the reason the build can
    finish at all.

    This test previously asserted the OPPOSITE (``test_a_moved_roster_
    invalidates_every_banked_unit``): a changed generation fingerprint threw away
    every banked unit. That reading of ``LATE_ARRIVAL_NOT_INVALIDATED`` was
    correct in isolation and fatal in production. The roster is
    ``futures_markets WHERE status='resolved'`` and markets resolve continuously,
    so the digest moved between EVERY pair of hourly beats: the 2026-08-03 flip
    banked one unit at 19:15Z and discarded it at 20:15Z, no generation could
    ever complete, nothing was published after 2026-08-02, and /api/calibration
    went dark on 2026-08-09.

    The guarantee is not dropped — it moves to :func:`retain_planned_units`, one
    level finer, and the test below pins it there.
    """
    cursor, action = _decode(_raw_cursor(), gen_fp="fp-a-market-arrived-late")
    assert action == RESUME
    assert cursor.committed_units == (_chunks()[0].key,)
    assert cursor.generation_fingerprint == "fp-a-market-arrived-late"


def test_late_arrival_is_enforced_per_unit_not_per_generation():
    """The finer guarantee: a unit survives a moved roster iff IT did not move.

    This is ``LATE_ARRIVAL_NOT_INVALIDATED`` as it now holds. Rows computed
    against two different definitions of the SAME unit still cannot be mixed —
    that unit re-keys and is recomputed — while a unit the arrival never touched
    stays banked, which is what lets successive beats accumulate.
    """
    before = _roster(
        (1, "kalshi", "e:1", True),
        (2, "polymarket", "e:1", True),
        (3, "kalshi", "m:3", False),
        (4, "kalshi", "m:4", False),
    )
    # A market resolves INTO the existing question e:1. Nothing else changes.
    after = before + _roster((5, "kalshi", "e:1", True))
    assert generation_fingerprint(before) != generation_fingerprint(after)

    planned_before = plan_units(before, buckets=8)
    planned_after = plan_units(after, buckets=8)

    # Bank every unit against the OLD roster.
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=generation_fingerprint(before),
        owner=OWNER,
        generation=1,
    )
    for chunk in planned_before:
        cursor = advance(
            cursor,
            chunk.key,
            [_population_row(bucket_idx=chunk.index + 1)],
            owner=OWNER,
            lease_expires_at=0.0,
        )
    assert is_complete(cursor, planned_before)

    # ``advance`` banks a unit by KEY and never sees the chunk, so the digests
    # are stamped by the first ``retain_planned_units`` of the NEXT beat. Drift
    # is therefore unmeasurable for exactly one beat after banking, and reads 0
    # as UNKNOWN rather than as "nothing moved" — pinned in
    # ``test_calibration_staged_convergence_p028.py``. This is that first beat.
    warm, dropped_warm = retain_planned_units(cursor, planned_before)
    assert dropped_warm == ()
    assert warm.roster_drift_units == 0
    assert warm.unit_digests, "the warm-up beat must leave the digests stamped"

    kept, dropped = retain_planned_units(warm, planned_after)

    # REVERSED BY CAL-P028. This used to assert that exactly the touched unit was
    # DROPPED. Dropping it is what made the build diverge: ~20 markets arrive
    # every hour, each landing in its own unit, and a beat can only complete ~20
    # units — so the drop rate met the completion rate and the cursor went
    # backwards (measured 20 -> 19 on 2026-08-10). The touched unit is now KEPT
    # and COUNTED, which is the same information without the work destroyed.
    touched = [c for c in planned_before if "e:1" in c.vm_ids]
    assert len(touched) == 1
    assert dropped == ()
    assert len(kept.committed_units) == len(planned_before)
    assert kept.roster_drift_units == 1, "the moved unit must be reported, not silently kept"
    # Every surviving unit is one the new plan still asks for.
    planned_keys = {c.key for c in planned_after}
    assert set(kept.committed_units) <= planned_keys
    # The generation IS finished, and honestly so: its rows are a census taken
    # ~one arrival ago, and the payload says how many units that describes.
    assert is_complete(kept, planned_after)


def test_the_partition_is_stable_so_an_arrival_cannot_disturb_its_neighbours():
    """CAL-P016's second half, and the one 300E's note did not name.

    Per-unit keys alone would NOT have converged: ``plan_units`` cut chunks with
    a positional accumulator over sorted ``vm_id``s, so one new ``vm_id`` early
    in sort order pushed every later boundary along and re-keyed every later
    unit. The cursor would then have discarded everything again, by a second
    route, and the fix would have looked like it failed.

    Content-addressed bucketing is what closes that: a question's unit depends on
    the question and nothing else.
    """
    before = _roster(*[(i, "kalshi", f"m:{i:03d}", False) for i in range(40)])
    # A new question that sorts FIRST — worst case for a positional accumulator.
    after = _roster((999, "kalshi", "m:000a", False)) + before

    planned_before = {c.key for c in plan_units(before, buckets=8)}
    planned_after = {c.key for c in plan_units(after, buckets=8)}

    survivors = planned_before & planned_after
    assert len(survivors) >= len(planned_before) - 1, (
        "an arrival disturbed more than its own unit — the partition is not stable"
    )


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
    """CAL-P034: the same rule, now necessarily all-or-nothing.

    A unit claimed with no mass behind it was a per-unit refusal while each unit
    carried its own rows. One shared fold cannot answer "does THIS unit have
    mass", so the refusal is the whole cursor — and it INVALIDATES rather than
    reporting FRESH, because a cursor that claims units it cannot back is a
    bookkeeping error worth naming, not an empty start.
    """
    cursor, action = _decode(_raw_cursor(accumulator=None))
    assert cursor.committed_units == ()
    assert action == INVALIDATE


def test_the_cursor_payload_round_trips():
    cursor, _ = _decode(_raw_cursor())
    reloaded, action = _decode(cursor.as_payload())
    assert action == RESUME
    assert reloaded.committed_units == cursor.committed_units
    assert reloaded.accumulator == cursor.accumulator
    assert _mass(reloaded) == _mass(cursor)


def test_advancing_banks_a_unit():
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    advanced = advance(
        cursor, chunks[0], [_BANKED_ROW], owner=OWNER, lease_expires_at=500.0
    )
    assert advanced.committed_units == (chunks[0].key,)
    assert _mass(advanced) == {(1, None, None, None, None): (1, 0, 0.0, 0.0)}
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
    once = advance(cursor, chunks[0], [_BANKED_ROW], owner=OWNER, lease_expires_at=100.0)
    twice = advance(
        once,
        chunks[0],
        [{"bucket_idx": 1, "n": 999}],
        owner=OWNER,
        lease_expires_at=200.0,
    )
    assert twice.committed_units == (chunks[0].key,)
    # CAL-P034 makes this guard LOAD-BEARING rather than tidy. A fold cannot be
    # un-added, so a duplicate advance would silently double the mass instead of
    # merely replacing a stored list. 1, not 1000 and not 999.
    assert _mass(twice) == {(1, None, None, None, None): (1, 0, 0.0, 0.0)}
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


def test_the_merged_result_does_not_depend_on_commit_order():
    """REPLACES ``..._collected_in_plan_order_whatever_the_commit_order``.

    CAL-P034 makes plan order unexpressible — units are summed into one running
    fold as they arrive, so there is no per-unit list left to order. Plan order
    was never the point though; it was the MECHANISM by which the merge saw the
    same sequence however the beats interleaved. This asserts the property that
    mechanism existed for, and asserts it end to end through the real merge,
    which is strictly more than the old test proved.
    """
    chunks = _chunks()
    rows = {
        chunk.key: [_population_row(bucket_idx=i + 1, n=i + 1, source="kalshi")]
        for i, chunk in enumerate(chunks)
    }

    def build(order):
        cursor = new_staged_cursor(
            population_version=VERSION,
            input_fingerprint=INPUT_FP,
            generation_fingerprint=GENERATION_FP,
            owner=OWNER,
            generation=1,
        )
        for chunk in order:
            cursor = advance(
                cursor, chunk, rows[chunk.key], owner=OWNER, lease_expires_at=1.0
            )
        return [
            vars(r)
            for r in merge_futures_rows(
                collect_unit_results(cursor, chunks), census_columns=CENSUS
            )
        ]

    forward = build(chunks)
    assert forward, "the merge produced nothing to compare against"
    assert forward == build(list(reversed(chunks)))


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
            cursor,
            chunk,
            [_population_row(bucket_idx=beat + 1, n=beat + 1)],
            owner=OWNER,
            lease_expires_at=float(beat),
        )
        banked_over_time.append(len(cursor.committed_units))
        if is_complete(cursor, chunks):
            published.append(merge_futures_rows([], census_columns=CENSUS))
        raw = cursor.as_payload()

    assert banked_over_time == sorted(banked_over_time)
    assert banked_over_time == list(range(1, len(chunks) + 1))
    assert len(published) == 1


def test_the_build_converges_when_the_roster_moves_between_every_beat():
    """CAL-P016's whole reason for existing, and the test that would have caught
    the 2026-08-09 outage.

    ``test_progress_is_monotonic_across_three_beats_and_only_the_last_publishes``
    proves the design works against a roster that HOLDS STILL. Production's
    roster never does: it is ``futures_markets WHERE status='resolved'`` and
    markets resolve continuously, so something arrives between every pair of
    hourly beats. Under the pre-CAL-P016 cursor that moved the generation
    fingerprint and discarded every banked unit, so the build banked 1-2 units of
    40+ per beat forever, published nothing after 2026-08-02, and the public page
    went dark a week later when the last-good copy aged out.

    Here a market arrives DURING every beat and each beat does one unit's work.
    The property under test is simply that it finishes — and that publication
    still waits for a plan every unit of which is banked against the current
    roster.
    """
    roster = _roster(*[(i, "kalshi", f"m:{i:03d}", False) for i in range(12)])
    next_market_id = 100
    raw = None
    published = []
    progress = []

    for beat in range(40):
        chunks = plan_units(roster, buckets=6)
        cursor, action = _decode(
            raw, gen_fp=generation_fingerprint(roster)
        )
        assert action in (FRESH, RESUME)
        cursor, _dropped = retain_planned_units(cursor, chunks)

        # One unit of work per beat — the deadline-bound case.
        todo = [c for c in chunks if not cursor.has(c.key)]
        if todo:
            cursor = advance(
                cursor,
                todo[0].key,
                [_population_row(bucket_idx=beat + 1, n=beat + 1)],
                owner=OWNER,
                lease_expires_at=0.0,
            )
        progress.append(len(cursor.committed_units))

        if is_complete(cursor, chunks):
            published.append(beat)
            break
        raw = cursor.as_payload()

        # A market resolves into the population mid-build, every single beat.
        roster = roster + _roster((next_market_id, "kalshi", f"m:{next_market_id}", False))
        next_market_id += 1

    assert published, (
        f"the build never converged in 40 beats; units banked per beat: {progress}"
    )
    # It finished, and it finished by ACCUMULATING rather than by luck.
    assert max(progress) > 1


# =============================================================================
# CAL-P033 — the durable round trip, which is the only trip production takes
# =============================================================================
#
# Every test above this line hands rows from ``advance`` to the merge inside one
# process. That is not what production does. Production writes the cursor
# through ``durable_state.canonical_json`` — ``json.dumps(..., default=str)`` —
# and reads it back on the NEXT beat. Under ``default=str`` an unencodable value
# is not refused, it is stringified, so every banked row reached Postgres as its
# ``repr()`` and came back a ``str``. The cursor still said RESUME, and the
# merge only touched those rows in finalization, which needs all 128 units and
# therefore never ran. The build has not published since 2026-08-02.
#
# So the rule these tests encode: a banked unit must survive the SAME trip the
# real one takes, and ``as_payload()`` alone is not that trip.


def _durable_round_trip(cursor):
    """The cursor as the next beat really receives it: through JSON."""
    return json.loads(canonical_json(cursor.as_payload()))


def _population_row(**overrides):
    row = {
        "bucket_idx": 3,
        "source": "kalshi",
        "category": "baseball",
        "price_moved": False,
        "is_nonexclusive_bundle": False,
        "n": 14,
        "winners": 6,
        # NUMERIC out of Postgres. json.dumps cannot encode a Decimal, which is
        # what dragged the whole row through ``default=str``.
        "sum_prob": Decimal("0.03071428571428571429"),
        "sum_sq_err": 0.0238,
        "avg_prob": 0.43,
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def test_a_banked_unit_survives_the_durable_round_trip():
    """THE regression. Same unit, merged in-process and after a JSON trip."""
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    cursor = advance(cursor, chunks[0], [_population_row()], owner=OWNER, lease_expires_at=1e12)
    in_process = merge_futures_rows(collect_unit_results(cursor, chunks[:1]))

    resumed, action = _decode(_durable_round_trip(cursor))
    assert action == RESUME
    after_trip = merge_futures_rows(collect_unit_results(resumed, chunks[:1]))

    assert in_process, "the in-process merge produced nothing to compare against"
    assert [vars(r) for r in after_trip] == [vars(r) for r in in_process]


def test_a_resumed_row_is_the_same_type_as_a_freshly_banked_one():
    """The invariant, stated directly: the bug was two representations, not a
    wrong one. A unit banked this beat and a unit resumed from disk must be
    indistinguishable, because finalization reads them out of one list."""
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    cursor = advance(cursor, chunks[0], [_population_row()], owner=OWNER, lease_expires_at=1e12)
    fresh_buckets, fresh_carriers = cursor.folded()
    resumed, _ = _decode(_durable_round_trip(cursor))
    resumed_buckets, resumed_carriers = resumed.folded()

    assert fresh_buckets and fresh_carriers, "precondition: both kinds are present"
    assert type(resumed_buckets[0]) is type(fresh_buckets[0])
    assert type(resumed_carriers[0]) is type(fresh_carriers[0])
    # CAL-P034 raises the bar from "same type" to "same value". With one shared
    # fold there is no longer a per-unit list whose identity could differ, so
    # the round trip either reproduces the running total exactly or it is broken.
    assert _row_dicts(resumed_buckets) == _row_dicts(fresh_buckets)
    assert _row_dicts(resumed_carriers) == _row_dicts(fresh_carriers)


def test_finalization_can_read_columns_off_a_resumed_row():
    """``precompute_calibration`` finalization does
    ``dict(row._mapping) if hasattr(row, "_mapping") else dict(vars(row))`` on
    every banked row before merging. That is the exact expression that raised on
    a ``str``, so it is asserted here rather than only through the merge."""
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    cursor = advance(cursor, chunks[0], [_population_row()], owner=OWNER, lease_expires_at=1e12)
    resumed, _ = _decode(_durable_round_trip(cursor))
    row = collect_unit_results(resumed, chunks[:1])[0][0]
    mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(vars(row))
    assert mapping["bucket_idx"] == 3
    assert mapping["n"] == 14


def test_a_numeric_column_round_trips_as_a_decimal_not_a_float():
    """CAL-P033's rule, REWRITTEN by CAL-P034 rather than dropped.

    The rule was "do not let the cursor's encoding change the addends the merge
    sums". CAL-P033 kept that by storing ``Decimal``; the fold keeps it by
    converting each addend through ``_as_float`` at exactly the point, and with
    exactly the granularity, ``merge_futures_rows`` would have — so the addends
    are the same numbers, computed by the same call, one step earlier.

    What is genuinely reversed: an additive column is a ``float`` in the cursor
    now, because it is a running total rather than a stored row. So both halves
    are pinned — the ENCODER still round-trips ``Decimal`` exactly (carriers and
    census values still rely on it), and the FOLD produces the merge's own
    addend.
    """
    exact = Decimal("0.03071428571428571429")

    # 1. The encoder is unchanged: exact digits in, exact Decimal out.
    (decoded,) = decode_unit_rows(encode_unit_rows([{"sum_prob": exact}]))
    assert isinstance(decoded.sum_prob, Decimal)
    assert decoded.sum_prob == exact

    # 2. The fold produces the merge's addend, not a re-rounded one.
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    cursor = advance(cursor, chunks[0], [_population_row()], owner=OWNER, lease_expires_at=1e12)
    resumed, _ = _decode(_durable_round_trip(cursor))
    (row,) = [r for r in resumed.folded()[0] if r.bucket_idx == 3]
    assert row.sum_prob == float(exact)
    assert row.sum_prob == merge_futures_rows([[_population_row()]])[0].sum_prob


def test_a_pre_encoding_cursor_is_refused_with_its_own_reason():
    """The 63 units banked before this shipped are ``list[str]`` and carry no
    column names, so they are not recoverable. Refusing them is the honest
    answer, and it gets its own token so the one expected reset is not confused
    with a real ``malformed_units``."""
    legacy = _raw_cursor(
        unit_results={_chunks()[0].key: ["(3, 'kalshi', 'baseball', False, False, 14)"]}
    )
    cursor, action, reason = decode_staged_cursor_detailed(
        legacy,
        expected_population_version=VERSION,
        expected_input_fingerprint=INPUT_FP,
        expected_generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=9,
        now=100.0,
    )
    assert action == INVALIDATE
    assert reason == REASON_UNENCODED_UNITS
    assert cursor.committed_units == ()


def test_a_legacy_cursor_is_never_partially_resumed():
    """One good unit next to one legacy unit must not resume the good one. A
    cursor is vouched for whole; publishing a generation half of whose units
    were computed under a representation we could not read is worse than
    re-walking."""
    chunks = _chunks()
    good = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    good = advance(good, chunks[0], [_population_row()], owner=OWNER, lease_expires_at=1e12)
    raw = _durable_round_trip(good)
    raw["committed_units"] = [chunks[0].key, chunks[1].key]
    # CAL-P034: a legacy unit can no longer sit BESIDE a good one in the same
    # cursor — there is no per-unit slot to put it in. The equivalent state is a
    # cursor that carries a valid fold and ALSO a leftover ``unit_results`` map
    # from the pre-fold shape. It is still refused whole, and still under the
    # unencoded token, because that is the older and more specific of the two.
    raw["unit_results"] = {chunks[1].key: ["(1, 'kalshi')"]}
    _, action, reason = decode_staged_cursor_detailed(
        raw,
        expected_population_version=VERSION,
        expected_input_fingerprint=INPUT_FP,
        expected_generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=9,
        now=100.0,
    )
    assert action == INVALIDATE
    assert reason == REASON_UNENCODED_UNITS


def test_an_undeclared_value_type_is_refused_loudly_not_stringified():
    """``default=str`` is the behaviour being replaced, so the encoder must not
    reimplement it. An unencodable value raises where it is banked, not four
    hours later in finalization."""
    class Opaque:
        pass

    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    # CAL-P034 — the column must be a DECLARED one, or the fold's undeclared-
    # column guard fires first and this test would pass for the wrong reason.
    # The hazard being pinned is an undeclared VALUE TYPE in a legitimate
    # column, which only the encoder can catch.
    with pytest.raises(UnencodableValueError):
        advance(
            cursor,
            chunks[0],
            [SimpleNamespace(bucket_idx=None, published_questions=Opaque())],
            owner=OWNER,
            lease_expires_at=1e12,
        )


def test_an_undeclared_column_is_refused_at_bank_time_not_broadcast():
    """CAL-P034's own half of the same guard, and the more dangerous half.

    ``merge_futures_rows`` refuses an undeclared column because there is no safe
    default: summing a census column double-counts it, and BROADCASTING an
    additive one freezes a single unit's mass onto every row. The fold routes
    every non-group, non-additive column into the carrier — i.e. it broadcasts —
    so without this guard at bank time, a column the statement grew would take
    the silent-broadcast path instead of raising. Same refusal, moved to the
    last point where a unit's rows are seen whole.
    """
    chunks = _chunks()
    cursor = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GENERATION_FP,
        owner=OWNER,
        generation=1,
    )
    with pytest.raises(UndeclaredColumnError):
        advance(
            cursor,
            chunks[0],
            [{"bucket_idx": 1, "n": 5, "a_column_nobody_declared": 3}],
            owner=OWNER,
            lease_expires_at=1e12,
        )


def test_rows_with_differing_columns_keep_absent_distinct_from_none():
    """The merge treats a census column that is ABSENT differently from one
    reported as ``None``. A columnar envelope would flatten that, so a
    heterogeneous unit falls back to presence-preserving pairs."""
    encoded = encode_unit_rows(
        [SimpleNamespace(bucket_idx=1, n=2), SimpleNamespace(bucket_idx=2, n=3, published_questions=7)]
    )
    decoded = decode_unit_rows(encoded)
    assert not hasattr(decoded[0], "published_questions")
    assert decoded[1].published_questions == 7


def test_an_empty_unit_encodes_and_decodes_as_no_rows():
    """A chunk that legitimately produced nothing is a real state, not an error."""
    assert decode_unit_rows(encode_unit_rows([])) == []
    assert is_encoded_unit_rows(encode_unit_rows([]))


def test_the_convergence_walk_still_converges_through_real_json():
    """The multi-beat test above round-trips through ``as_payload()``, which is a
    dict and keeps ``Row`` objects alive. THAT is why it stayed green while the
    build could not finish. This one takes the same walk through JSON."""
    roster = _roster(*[(i, "kalshi", f"m:{i}", False) for i in range(30)])
    next_market_id = 1000
    raw = None
    published = None
    for beat in range(40):
        chunks = plan_units(roster, buckets=6)
        cursor, action = _decode(raw, gen_fp=generation_fingerprint(roster))
        assert action in (FRESH, RESUME)
        cursor, _dropped = retain_planned_units(cursor, chunks)
        todo = [c for c in chunks if not cursor.has(c.key)]
        if todo:
            cursor = advance(
                cursor,
                todo[0].key,
                [_population_row(bucket_idx=todo[0].index, n=beat + 1)],
                owner=OWNER,
                lease_expires_at=0.0,
            )
        if is_complete(cursor, chunks):
            published = merge_futures_rows(collect_unit_results(cursor, chunks))
            break
        raw = _durable_round_trip(cursor)
        roster = roster + _roster((next_market_id, "kalshi", f"m:{next_market_id}", False))
        next_market_id += 1

    assert published, "the build never reached a merge through a real JSON round trip"
    assert sum(row.n for row in published) > 0
