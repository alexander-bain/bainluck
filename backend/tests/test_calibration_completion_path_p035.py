"""CAL-P035 — the completion path, at full scale, for the first time.

**This path has not run in production since 2026-08-02.** Every beat since has
died in the unit loop, so `staged:finalize` has never been entered and
``rss:at:staged:finalize`` has never been recorded on any ledger. In that window
CAL-P033 fixed a defect in it by reasoning plus a five-unit test, and CAL-P034
then changed its *input representation* from banked rows to a running fold.
Neither could execute it at the scale production will.

That is CAL-P033's own lesson pointed at the next edge. Its finding was that
~8,000 tests missed a fatal cursor bug because they handed rows from ``advance``
straight to the merge in one process — *"the round trip was the untested edge and
it is the only edge production takes."* The completion path is now that edge:
production reached 109/128 on 2026-08-11 before the P033/P034 deploy reset it,
and it is walking there again.

What this file adds that CAL-P034's suite does not
--------------------------------------------------
CAL-P034 pins the fold's *rules* thoroughly, but at 5 units over 3 groups. Two
things only appear at production shape:

1. **Scale and saturation.** The live cursor carried ~470 rows per unit over a
   group space that saturates near ~1,650 distinct keys — rows linear, groups
   flat. That ratio is the entire premise of the fold, and it is where an
   accidentally-linear accumulator would show up.
2. **The finalize cost, which is CAL-P034's own unowned item 1** — it left the
   spike "UNMEASURED … the one step no beat has ever reached", and noted that
   shrinking the cursor makes it *reachable*, hence more urgent. Measured here.

Deliberately NOT re-asserted here: the fold's arithmetic rules, census routing,
``UndeclaredColumnError``, and the frozen-mirror pin. Those are CAL-P034's and
duplicating them would create the second derivation this lane keeps paying for.
"""

from __future__ import annotations

import json
import tracemalloc
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.utils.calibration_phase_ledger import RESUME
from app.utils.calibration_staged_futures import (
    GROUP_KEY_COLUMNS,
    REPRESENTATIVE_TIE_COLUMN,
    advance,
    collect_unit_results,
    decode_staged_cursor_detailed,
    new_staged_cursor,
)

from tests.test_calibration_staged_fold_p034 import (  # the established mirror
    GEN_FP,
    INPUT_FP,
    OWNER,
    VERSION,
    _finalize,
)

# Production shape, from the live cursor read on 2026-08-11 (91/128 units:
# 44,272 rows over 1,586 distinct group keys, ~470 rows/unit).
UNITS = 128
ROWS_PER_UNIT = 470
CORE_GROUPS = 400  # every unit restates these — the saturating core
TAIL_GROUPS = 1_250  # entered gradually, so the space fills over the walk
POOL = CORE_GROUPS + TAIL_GROUPS  # 1,650, matching the measured saturation

_CATEGORIES = ("baseball", "soccer", "basketball", "hockey", "golf", "tennis", "mma", "politics")


def _group_key(index: int) -> dict:
    """One point in the group space, deterministically.

    A bucket is a PRICE BAND, not a question — which is why the space saturates
    while rows do not. Derived from ``index`` rather than randomised so a failure
    reproduces exactly (and because ``Math.random``-style nondeterminism in a
    memory test produces unfalsifiable flakes).
    """
    return {
        "bucket_idx": index % 100,
        "source": "kalshi" if (index // 100) % 2 else "polymarket",
        "category": _CATEGORIES[(index // 200) % len(_CATEGORIES)],
        "price_moved": bool((index // 1_600) % 2),
        "is_nonexclusive_bundle": bool((index // 800) % 2),
    }


def _unit_rows(unit_index: int) -> list[SimpleNamespace]:
    """~470 rows for one unit: a shared core plus a rotating tail slice."""
    census = {
        "published_outcomes": 1_000 + unit_index,
        "published_questions": 100 + unit_index,
        "kalshi_included": 7 + unit_index,
        REPRESENTATIVE_TIE_COLUMN: unit_index,
    }
    tail_width = ROWS_PER_UNIT - CORE_GROUPS
    start = (unit_index * tail_width) % TAIL_GROUPS
    indices = list(range(CORE_GROUPS)) + [
        CORE_GROUPS + ((start + offset) % TAIL_GROUPS) for offset in range(tail_width)
    ]
    return [
        SimpleNamespace(
            **_group_key(i),
            n=unit_index + i + 1,
            winners=(i % 5),
            sum_prob=Decimal("0.5") * (i + 1),
            sum_sq_err=0.01 * (i + 1),
            avg_prob=0.43,
            **census,
        )
        for i in indices
    ]


def _cursor():
    return new_staged_cursor(
        population_version=VERSION,
        input_fingerprint=INPUT_FP,
        generation_fingerprint=GEN_FP,
        owner=OWNER,
        generation=1,
    )


def _walk(units: int, *, round_trip: bool, transitions: list | None = None) -> object:
    """Bank ``units`` units, optionally through real JSON between each one.

    **CAL-P035 repair (C276 item 2).** The round trip used to re-inflate the
    cursor by hand — ``cursor.__class__(**{**vars(cursor), ...})`` — which reads
    like a resume and is not one: it never touched the production decoder, so
    every predicate that decides whether a persisted cursor is *usable* was
    skipped, and deleting the round trip entirely changed nothing that any
    assertion could see. It now goes through
    :func:`decode_staged_cursor_detailed`, the same function the beat calls, and
    each transition is recorded so a test can prove the decode actually happened.
    """
    cursor = _cursor()
    for index in range(units):
        cursor = advance(
            cursor,
            f"u{index}",
            _unit_rows(index),
            owner=OWNER,
            lease_expires_at=1e12,
        )
        if round_trip:
            # Through canonical JSON exactly as ``save_staged_cursor`` persists
            # it, then back through the PRODUCTION decoder.
            raw = json.loads(json.dumps(cursor.as_payload(), default=str))
            cursor, action, reason = decode_staged_cursor_detailed(
                raw,
                expected_population_version=VERSION,
                expected_input_fingerprint=INPUT_FP,
                expected_generation_fingerprint=GEN_FP,
                owner=OWNER,
                generation=1,
                now=0.0,
            )
            if transitions is not None:
                transitions.append((action, reason))
    return cursor


# =============================================================================
# The INDEPENDENT oracle (CAL-P035 repair, C276 item 1)
# =============================================================================
#
# The previous version compared ``_finalize(fold)`` against
# ``_finalize(all_rows)``. Both sides ran the same finalizer, so any defect in
# the finalizer itself cancelled: dropping its first output row dropped it from
# both, and the assertion still passed. That is the "two derivations of one
# fact" failure this lane keeps paying for, wearing the costume of a reference
# comparison.
#
# The oracle below is computed from the GENERATED ROWS by plain arithmetic in
# this file. It shares no code with the merge, so it can disagree with it.


def _expected_from_generated_rows(units: int) -> tuple[dict, dict]:
    """``(groups, census_totals)`` derived only from ``_unit_rows``."""
    groups: dict[tuple, dict] = {}
    for unit_index in range(units):
        for row in _unit_rows(unit_index):
            key = tuple(getattr(row, name) for name in GROUP_KEY_COLUMNS)
            acc = groups.setdefault(
                key, {"n": 0, "winners": 0, "sum_prob": Decimal(0), "sum_sq_err": 0.0}
            )
            acc["n"] += row.n
            acc["winners"] += row.winners
            acc["sum_prob"] += row.sum_prob
            acc["sum_sq_err"] += row.sum_sq_err

    # Census columns are per-unit constants that finalization SUMS across units
    # and broadcasts onto every merged row.
    census_totals = {
        "published_outcomes": sum(1_000 + i for i in range(units)),
        "published_questions": sum(100 + i for i in range(units)),
        "kalshi_included": sum(7 + i for i in range(units)),
        REPRESENTATIVE_TIE_COLUMN: sum(range(units)),
    }
    return groups, census_totals


@pytest.fixture(scope="module")
def walked():
    return _walk(UNITS, round_trip=False)


class TestTheFullWalkFinalizes:
    """The event production is about to reach, executed."""

    @staticmethod
    def _assert_matches_the_oracle(finalized, units=UNITS):
        """Compare finalized output against arithmetic done in THIS file."""
        expected_groups, expected_census = _expected_from_generated_rows(units)

        produced = {
            tuple(getattr(row, name) for name in GROUP_KEY_COLUMNS): row
            for row in finalized
        }
        # Key SET, independently derived — this is what a dropped output row
        # violates, and what comparing two runs of the same finalizer cannot see.
        assert set(produced) == set(expected_groups), (
            f"group keys differ from the independently derived set: "
            f"{len(produced)} produced vs {len(expected_groups)} expected"
        )
        assert len(finalized) == len(expected_groups)

        for key, want in expected_groups.items():
            row = produced[key]
            assert row.n == want["n"], f"n mismatch at {key}"
            assert row.winners == want["winners"], f"winners mismatch at {key}"
            assert float(row.sum_prob) == pytest.approx(float(want["sum_prob"])), key
            assert float(row.sum_sq_err) == pytest.approx(float(want["sum_sq_err"])), key
            # Derived, never summed.
            assert float(row.avg_prob) == pytest.approx(
                float(want["sum_prob"]) / want["n"] if want["n"] else 0.0
            ), key

        # Census totals are broadcast identically onto every row.
        for column, total in expected_census.items():
            values = {getattr(row, column) for row in finalized}
            assert values == {total}, (
                f"census {column}: expected {total} broadcast onto every row, got {values}"
            )

    def test_a_full_128_unit_walk_finalizes_to_the_independently_derived_totals(self, walked):
        """The acceptance bar, against an oracle that shares no code with the merge.

        ``bank-all-then-merge`` used to be the reference here. It is not a
        reference — it is the same finalizer run twice, so it certifies the fold
        only against itself. The oracle is now the arithmetic in
        :func:`_expected_from_generated_rows`.
        """
        folded = _finalize(collect_unit_results(walked, [f"u{i}" for i in range(UNITS)]))
        self._assert_matches_the_oracle(folded)

    def test_the_walk_survives_a_json_round_trip_through_the_production_decoder(self):
        """The only edge production takes, at the length production takes it.

        A beat banks ~18 units, so a 128-unit build is resumed from Postgres six
        or seven times. Every one of the 128 steps here is persisted through
        canonical JSON and read back through ``decode_staged_cursor_detailed``,
        and the transition log is asserted — so removing the round trip fails
        this test rather than silently making it a second copy of the one above.
        """
        transitions: list = []
        resumed = _walk(UNITS, round_trip=True, transitions=transitions)

        assert len(transitions) == UNITS, (
            f"expected {UNITS} persist/decode transitions, saw {len(transitions)} — "
            "the round trip is not happening"
        )
        assert {action for action, _reason in transitions} == {RESUME}, (
            f"every transition must be a production RESUME, saw "
            f"{ {a for a, _ in transitions} }"
        )

        through_json = _finalize(
            collect_unit_results(resumed, [f"u{i}" for i in range(UNITS)])
        )
        self._assert_matches_the_oracle(through_json)

    def test_the_saturating_group_space_is_actually_reproduced(self, walked):
        """Guards the FIXTURE, not the code.

        If the generator quietly emitted one group per row, every assertion
        above would still pass and prove nothing about saturation — the exact
        shape of vacuous test this lane keeps catching by mutation. Pin the
        premise: rows are linear in units, groups are not.
        """
        buckets, _carriers = walked.folded()
        distinct = {tuple(getattr(row, name) for name in GROUP_KEY_COLUMNS) for row in buckets}

        assert len(distinct) == len(buckets), "the fold must hold each group exactly once"
        assert 1_000 < len(buckets) < 2_000, f"expected production-like saturation, got {len(buckets)}"
        assert UNITS * ROWS_PER_UNIT > 20 * len(buckets), "rows must dwarf groups, or there is nothing to fold"


class TestTheFinalizeAllocation:
    """CAL-P034's unowned item 1 — measured, and labelled for what it is.

    **CAL-P035 repair (C276 item 3).** This measures ``tracemalloc``, which
    counts **Python allocation requested inside the traced block**. It is not
    process RSS: it cannot see the interpreter, the driver's result buffers,
    arena fragmentation, or anything C-level, and the worker's 512 MB limit is
    enforced against RSS. So the number below bounds *incremental Python
    allocation across the completion path* and supports exactly one conclusion —
    that this cost scales with the group space and not the unit count.

    **It does not establish that finalization is safe on the dyno**, and the
    earlier version of this file said it did. RSS closure can only come from a
    process-RSS reading around the real finalizer in production — the
    ``rss:at:staged:finalize`` gauge on the first beat that completes.
    """

    @staticmethod
    def _finalize_peak(units: int) -> int:
        cursor = _walk(units, round_trip=False)
        keys = [f"u{i}" for i in range(units)]
        tracemalloc.start()
        try:
            tracemalloc.reset_peak()
            _finalize(collect_unit_results(cursor, keys))
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        return peak

    def test_finalize_allocation_is_bounded_by_the_group_space_not_the_unit_count(self):
        """The property, asserted as a RATIO so it cannot flake on absolutes.

        Peak bytes are machine- and version-sensitive, so an absolute ceiling
        would be either meaningless or brittle. The invariant that actually
        matters is scaling: 16x the units must not cost anything like 16x the
        memory, because the fold's whole claim is that finalization sees the
        saturated group space rather than the accumulated rows. Pre-CAL-P034
        this ratio was ~linear.
        """
        small = self._finalize_peak(8)
        full = self._finalize_peak(UNITS)

        assert full < 3 * small, (
            f"finalize allocation scaled with units, not groups: "
            f"{small:,} B at 8 units -> {full:,} B at {UNITS} "
            f"({full / max(small, 1):.1f}x for 16x the units)"
        )

    def test_the_measured_allocation_is_recorded(self, record_property):
        """Report the number, so 'unmeasured' stops being the answer.

        Recorded under a name that says what was measured. "peak" alone reads as
        peak MEMORY, and this is peak Python ALLOCATION — the distinction the
        C276 block was raised on.

        Recorded as a test property rather than asserted against a threshold:
        the useful output is the figure itself, and a threshold invented here
        would be a guess dressed as a bar. The ratio test above is the guard.
        """
        peak = self._finalize_peak(UNITS)
        record_property("finalize_python_allocation_bytes_at_128_units", peak)

        assert peak > 0, "tracemalloc measured nothing — the harness is not exercising finalize"
