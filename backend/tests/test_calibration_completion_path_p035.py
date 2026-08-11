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

from app.utils.calibration_staged_futures import (
    GROUP_KEY_COLUMNS,
    REPRESENTATIVE_TIE_COLUMN,
    advance,
    collect_unit_results,
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


def _walk(units: int, *, round_trip: bool) -> object:
    """Bank ``units`` units, optionally through real JSON between each one."""
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
            raw = json.loads(json.dumps(cursor.as_payload(), default=str))
            cursor = cursor.__class__(**{**vars(cursor), "accumulator": raw["accumulator"]})
    return cursor


@pytest.fixture(scope="module")
def walked():
    return _walk(UNITS, round_trip=False)


class TestTheFullWalkFinalizes:
    """The event production is about to reach, executed."""

    def test_a_full_128_unit_walk_finalizes_identically_to_banking_every_row(self, walked):
        """The acceptance bar, at production scale rather than at three groups.

        ``bank-all-then-merge`` is the reference the fold must be
        indistinguishable from. CAL-P034 proves that over 5 units; the risk this
        closes is an error that only appears once the group space saturates and
        the accumulator is larger than any single unit.
        """
        folded = _finalize(collect_unit_results(walked, [f"u{i}" for i in range(UNITS)]))
        direct = _finalize([_unit_rows(i) for i in range(UNITS)])

        assert [vars(row) for row in folded] == [vars(row) for row in direct]

    def test_the_walk_survives_a_json_round_trip_between_every_one_of_128_units(self):
        """The only edge production takes, at the length production takes it.

        A beat banks ~18 units, so a 128-unit build is resumed from Postgres
        six or seven times. CAL-P034's version of this runs five units; the
        distinction that matters is that the accumulator here is re-encoded and
        re-decoded 128 times, each time carrying the full saturated group space.
        """
        resumed = _walk(UNITS, round_trip=True)
        through_json = _finalize(
            collect_unit_results(resumed, [f"u{i}" for i in range(UNITS)])
        )
        direct = _finalize([_unit_rows(i) for i in range(UNITS)])

        assert [vars(row) for row in through_json] == [vars(row) for row in direct]

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


class TestTheFinalizeSpike:
    """CAL-P034's unowned item 1, closed with a number."""

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

    def test_finalize_cost_is_bounded_by_the_group_space_not_the_unit_count(self):
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
            f"finalize peak scaled with units, not groups: "
            f"{small:,} B at 8 units -> {full:,} B at {UNITS} "
            f"({full / max(small, 1):.1f}x for 16x the units)"
        )

    def test_the_measured_peak_is_recorded(self, record_property):
        """Report the number, so 'unmeasured' stops being the answer.

        Recorded as a test property rather than asserted against a threshold:
        the useful output is the figure itself, and a threshold invented here
        would be a guess dressed as a bar. The ratio test above is the guard.
        """
        peak = self._finalize_peak(UNITS)
        record_property("finalize_peak_bytes_at_128_units", peak)

        assert peak > 0, "tracemalloc measured nothing — the harness is not exercising finalize"
