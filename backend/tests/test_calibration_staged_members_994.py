"""#994 — DataGolf membership rides beside the staged fold, keyed by unit.

THE READER SHIP. A reader who taps a DataGolf Accuracy bucket opens the exact
eligible examples behind that published curve on the first click, without the
drill-in re-running the population chain per click.

WHAT THIS FILE PINS (pure, no database). The staged bank used to keep each
cell's MASS and nothing about who made it. Stage B now emits, per DataGolf
group, the member records it counted (``datagolf_members``); the bank lifts them
out at ``advance`` time and keeps them beside the fold:

* a unit's membership is KNOWN-empty (``{}``) when the column was emitted and
  the unit holds no DataGolf rows, and UNKNOWN (``None``) when the column is
  absent or contradicts the row it rides on — absent is never empty;
* banking a unit twice, or units in a different order, yields the same
  membership (the idempotence guard plus unit keys, not arrival order);
* a bank resumed from before #994 stays unknown however many known units are
  added to it — known units cannot vouch for the earlier ones;
* promotion carries membership with the fold atomically, so the serving bank's
  members are always the serving bank's;
* the whole cursor round-trips through the durable codec (CAL-P033's lesson:
  the round trip is the edge production uses);
* the producer's Stage B change is a DELIBERATE next-generation transition: the
  unit and input digests move (so no in-flight bank is ever resumed into a
  mixed generation) and the published predicate does not.

What rows Stage B actually emits is a Postgres question:
``tests/integration/test_calibration_staged_members_994_pg.py``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.tasks import precompute_calibration as pc
from app.utils.calibration_examples_membership import verify_cells_against_fold
from app.utils.calibration_phase_ledger import INVALIDATE, MAIN_BUILD_TASK
from app.utils.calibration_staged_futures import (
    MEMBER_COLUMN,
    REASON_INPUT_FINGERPRINT,
    STAGED_FUTURES_SCHEMA,
    advance,
    collect_unit_members,
    collect_unit_results,
    decode_members,
    decode_staged_cursor_detailed,
    encode_members,
    merge_futures_rows,
    membership_cell_key,
    new_staged_cursor,
    retain_planned_units,
    split_unit_members,
    split_unit_rows,
)

OWNER = "beat-1"


def _row(bucket, source, *, n, winners, members, moved=True, category="golf", bundle=False, **extra):
    return SimpleNamespace(
        bucket_idx=bucket,
        source=source,
        category=category,
        price_moved=moved,
        is_nonexclusive_bundle=bundle,
        n=n,
        winners=winners,
        avg_prob=0.0,
        sum_prob=extra.pop("sum_prob", 0.0),
        sum_sq_err=0.0,
        **{MEMBER_COLUMN: members},
        **extra,
    )


def _carrier(**census):
    return SimpleNamespace(
        bucket_idx=None, source=None, category=None, price_moved=None,
        is_nonexclusive_bundle=None, n=0, winners=None, avg_prob=None,
        sum_prob=None, sum_sq_err=None, **{MEMBER_COLUMN: None}, **census,
    )


def _dg(bucket, records, *, moved=True, category="golf"):
    """A DataGolf group whose mass is derived from its own records."""
    winners = sum(r.endswith(",1") for r in records)
    total = sum(float(r.split(",")[2]) for r in records)
    return _row(
        bucket, "datagolf", n=len(records), winners=winners,
        members=";".join(records), moved=moved, category=category, sum_prob=total,
    )


UNIT_A = [
    _dg(6, ["11,1101,0.64,1", "11,1102,0.61,0"]),
    _dg(6, ["11,1103,0.62,0"], moved=False),
    _row(6, "kalshi", n=4, winners=2, members=None, sum_prob=2.4),
]
UNIT_B = [
    _dg(6, ["12,1201,0.65,1"]),
    _dg(2, ["12,1202,0.21,0", "12,1203,0.24,0"]),
]
UNIT_EMPTY = [_carrier()]
PLAN = ("u:a", "u:b", "u:c")


def _cursor():
    return new_staged_cursor(
        population_version="q271",
        input_fingerprint="fp",
        generation_fingerprint="gen",
        owner=OWNER,
        generation=1,
    )


def _bank(cursor, units):
    for key, rows in units:
        cursor = advance(cursor, key, rows, owner=OWNER, lease_expires_at=0.0)
    return cursor


# ---------------------------------------------------------------------------
# One unit's membership
# ---------------------------------------------------------------------------
class TestSplitUnitMembers:
    def test_a_datagolf_group_is_kept_under_its_cell(self):
        members = split_unit_members(UNIT_A)
        assert members == {
            membership_cell_key(UNIT_A[0]): "11,1101,0.64,1;11,1102,0.61,0",
            membership_cell_key(UNIT_A[1]): "11,1103,0.62,0",
        }

    def test_the_cell_key_drops_only_the_source(self):
        assert json.loads(membership_cell_key(UNIT_A[0])) == [6, "golf", True, False]
        assert membership_cell_key(UNIT_A[0]) != membership_cell_key(UNIT_A[1])

    def test_a_unit_with_no_datagolf_rows_is_known_empty(self):
        assert split_unit_members(UNIT_EMPTY) == {}
        assert split_unit_members([_row(3, "kalshi", n=2, winners=1, members=None)]) == {}

    def test_absent_column_is_unknown_not_empty(self):
        legacy = [SimpleNamespace(**{k: v for k, v in vars(r).items() if k != MEMBER_COLUMN}) for r in UNIT_A]
        assert split_unit_members(legacy) is None
        assert split_unit_members([]) is None

    @pytest.mark.parametrize(
        "rows",
        [
            # A DataGolf group with rows and no members.
            [_row(6, "datagolf", n=2, winners=1, members=None)],
            # Members on another source's group.
            [_row(6, "kalshi", n=1, winners=1, members="1,2,0.6,1")],
            # A census carrier claiming members.
            [SimpleNamespace(**{**vars(_carrier()), MEMBER_COLUMN: "1,2,0.6,1"})],
            # Record count disagrees with n.
            [_row(6, "datagolf", n=2, winners=1, members="1,2,0.6,1")],
            # Winner count disagrees with winners.
            [_row(6, "datagolf", n=1, winners=0, members="1,2,0.6,1")],
            # A malformed record.
            [_row(6, "datagolf", n=1, winners=0, members="1,2,0.6")],
            # The same cell twice in one unit.
            [_dg(6, ["1,2,0.6,1"]), _dg(6, ["1,3,0.61,0"])],
        ],
    )
    def test_a_contradiction_is_unknown(self, rows):
        assert split_unit_members(rows) is None

    def test_the_member_column_never_reaches_the_mass_or_the_carriers(self):
        mass, carriers = split_unit_rows(UNIT_A + UNIT_EMPTY)
        assert all(MEMBER_COLUMN not in values for _key, values in mass)
        assert all(MEMBER_COLUMN not in c for c in carriers)

    def test_the_merge_accepts_the_member_column(self):
        merged = merge_futures_rows([UNIT_A])
        assert {r.source for r in merged} == {"datagolf", "kalshi"}
        assert all(not hasattr(r, MEMBER_COLUMN) for r in merged)


# ---------------------------------------------------------------------------
# The bank
# ---------------------------------------------------------------------------
class TestTheBankCarriesMembership:
    def test_a_complete_bank_yields_every_cell_union(self):
        cursor = _bank(_cursor(), [("u:a", UNIT_A), ("u:b", UNIT_B), ("u:c", UNIT_EMPTY)])
        cells, reason = collect_unit_members(cursor, PLAN)
        assert reason == "complete"
        moved6 = membership_cell_key(UNIT_A[0])
        assert sorted(";".join(cells[moved6]).split(";")) == [
            "11,1101,0.64,1", "11,1102,0.61,0", "12,1201,0.65,1",
        ]
        assert len(cells) == 3

    def test_repeating_a_unit_does_not_duplicate_its_members(self):
        once = _bank(_cursor(), [("u:a", UNIT_A), ("u:b", UNIT_B), ("u:c", UNIT_EMPTY)])
        twice = _bank(
            _cursor(),
            [("u:a", UNIT_A), ("u:a", UNIT_A), ("u:b", UNIT_B), ("u:b", UNIT_B), ("u:c", UNIT_EMPTY)],
        )
        assert collect_unit_members(once, PLAN) == collect_unit_members(twice, PLAN)

    def test_order_does_not_change_the_membership(self):
        forward = _bank(_cursor(), [("u:a", UNIT_A), ("u:b", UNIT_B), ("u:c", UNIT_EMPTY)])
        backward = _bank(_cursor(), [("u:c", UNIT_EMPTY), ("u:b", UNIT_B), ("u:a", UNIT_A)])
        assert collect_unit_members(forward, PLAN) == collect_unit_members(backward, PLAN)

    def test_a_unit_that_cannot_vouch_leaves_the_bank_incomplete(self):
        bad = [_row(6, "datagolf", n=2, winners=1, members=None)]
        cursor = _bank(_cursor(), [("u:a", UNIT_A), ("u:b", bad), ("u:c", UNIT_EMPTY)])
        assert collect_unit_members(cursor, PLAN) == (None, "membership_incomplete")
        # ...while the curve's fold is untouched by it.
        assert collect_unit_results(cursor, PLAN)

    def test_an_old_bank_resumed_stays_unknown(self):
        """Units banked before #994 carry no membership; known units added on
        top cannot make the earlier ones known."""
        legacy_rows = [
            SimpleNamespace(**{k: v for k, v in vars(r).items() if k != MEMBER_COLUMN})
            for r in UNIT_A
        ]
        from dataclasses import replace

        cursor = _bank(_cursor(), [("u:a", legacy_rows)])
        # The envelope the pre-#994 code wrote: no ``members`` key at all.
        old = {k: v for k, v in cursor.accumulator.items() if k != "members"}
        cursor = replace(cursor, accumulator=old)
        cursor = _bank(cursor, [("u:b", UNIT_B), ("u:c", UNIT_EMPTY)])
        assert "members" not in cursor.accumulator
        assert collect_unit_members(cursor, PLAN) == (None, "membership_absent")

    def test_a_legacy_unit_in_a_new_bank_is_incomplete(self):
        legacy_rows = [
            SimpleNamespace(**{k: v for k, v in vars(r).items() if k != MEMBER_COLUMN})
            for r in UNIT_A
        ]
        cursor = _bank(_cursor(), [("u:a", legacy_rows), ("u:b", UNIT_B), ("u:c", UNIT_EMPTY)])
        assert collect_unit_members(cursor, PLAN) == (None, "membership_incomplete")

    def test_an_accumulator_without_members_is_absent_not_empty(self):
        cursor, _ = retain_planned_units(_cursor(), PLAN)
        cursor = _bank(cursor, [("u:a", UNIT_A), ("u:b", UNIT_B), ("u:c", UNIT_EMPTY)])
        served = dict(cursor.served_accumulator)
        served.pop("members")
        from dataclasses import replace

        stripped = replace(cursor, served_accumulator=served)
        assert collect_unit_members(stripped, PLAN) == (None, "membership_absent")

    def test_no_complete_bank_is_said_so(self):
        cursor = _bank(_cursor(), [("u:a", UNIT_A)])
        assert collect_unit_members(cursor, PLAN) == (None, "no_complete_bank")


class TestPromotionCarriesMembership:
    def _promoted(self):
        cursor, _ = retain_planned_units(_cursor(), PLAN)
        return _bank(cursor, [("u:a", UNIT_A), ("u:b", UNIT_B), ("u:c", UNIT_EMPTY)])

    def test_the_serving_bank_holds_the_members_of_its_own_fold(self):
        cursor = self._promoted()
        assert cursor.served_units and not cursor.committed_units
        assert decode_members(cursor.served_accumulator["members"]) is not None
        cells, reason = collect_unit_members(cursor, PLAN)
        assert reason == "complete" and cells

    def test_a_successor_bank_starts_known_and_does_not_leak_into_serving(self):
        cursor = self._promoted()
        served_before = collect_unit_members(cursor, PLAN)
        cursor = _bank(cursor, [("u:a", UNIT_A)])
        # The building bank is partial, so the SERVING bank still answers, whole.
        assert collect_unit_members(cursor, PLAN) == served_before
        assert set(decode_members(cursor.accumulator["members"])) == {"u:a"}

    def test_a_dropped_slot_wipes_membership_with_the_fold(self):
        cursor = self._promoted()
        cursor = _bank(cursor, [("u:a", UNIT_A)])
        cursor, dropped = retain_planned_units(cursor, ("u:b", "u:c"))
        assert dropped == ("u:a",)
        assert cursor.served_accumulator is None and cursor.accumulator is None
        assert collect_unit_members(cursor, ("u:b", "u:c")) == (None, "no_complete_bank")


class TestTheDurableRoundTrip:
    def test_a_persisted_cursor_decodes_with_its_membership(self):
        cursor, _ = retain_planned_units(_cursor(), PLAN)
        cursor = _bank(cursor, [("u:a", UNIT_A), ("u:b", UNIT_B), ("u:c", UNIT_EMPTY)])
        cursor = _bank(cursor, [("u:b", UNIT_B)])  # a successor bank in flight
        raw = json.loads(json.dumps(cursor.as_payload(), default=str))
        decoded, action, reason = decode_staged_cursor_detailed(
            raw,
            expected_population_version="q271",
            expected_input_fingerprint="fp",
            expected_generation_fingerprint="gen",
            owner=OWNER,
            generation=1,
            now=0.0,
        )
        assert action != INVALIDATE, reason
        assert collect_unit_members(decoded, PLAN) == collect_unit_members(cursor, PLAN)
        assert decode_members(decoded.accumulator["members"]) == decode_members(
            cursor.accumulator["members"]
        )

    def test_encode_decode_is_lossless_and_refuses_strangers(self):
        units = {"u:a": {"[6,\"golf\",true,false]": "1,2,0.6,1"}, "u:b": {}}
        assert decode_members(encode_members(units)) == units
        assert decode_members(None) is None
        assert decode_members({"schema": "other", "source": "datagolf", "units": {}}) is None
        assert decode_members({**encode_members(units), "source": "kalshi"}) is None
        assert decode_members({**encode_members(units), "units": {"u:a": "x"}}) is None


# ---------------------------------------------------------------------------
# The fold check the producer runs before offering anything for publication
# ---------------------------------------------------------------------------
class TestTheFinalizedFoldIsWhatTheMembersAreCheckedAgainst:
    def test_a_complete_bank_verifies_against_its_own_merge(self):
        cursor = _bank(_cursor(), [("u:a", UNIT_A), ("u:b", UNIT_B), ("u:c", UNIT_EMPTY)])
        merged = merge_futures_rows(collect_unit_results(cursor, PLAN))
        cells, _ = collect_unit_members(cursor, PLAN)
        verified, reason = verify_cells_against_fold(cells, merged)
        assert reason == "complete"
        assert sum(c["n"] for c in verified.values()) == 6

    def test_the_producer_stages_nothing_when_membership_is_incomplete(self):
        bad = [_row(6, "datagolf", n=2, winners=1, members=None)]
        cursor = _bank(_cursor(), [("u:a", UNIT_A), ("u:b", bad), ("u:c", UNIT_EMPTY)])
        runner = SimpleNamespace(ledger=SimpleNamespace(stages=[], record_stage=lambda n, v: runner.ledger.stages.append(n)))
        pc._stage_examples_membership(runner, cursor, PLAN, [])
        assert runner.examples_membership is None
        assert runner.examples_membership_reason == "membership_incomplete"
        assert "staged:examples_membership:membership_incomplete" in runner.ledger.stages

    def test_the_producer_never_raises(self, monkeypatch):
        import app.utils.calibration_staged_futures as sf

        def boom(*a, **k):
            raise RuntimeError("x")

        monkeypatch.setattr(sf, "collect_unit_members", boom)
        runner = SimpleNamespace(ledger=SimpleNamespace(record_stage=lambda n, v: None))
        pc._stage_examples_membership(runner, _cursor(), PLAN, [])
        assert runner.examples_membership is None
        assert runner.examples_membership_reason == "membership_error"

    def test_the_producer_stages_a_verified_membership(self):
        cursor = _bank(_cursor(), [("u:a", UNIT_A), ("u:b", UNIT_B), ("u:c", UNIT_EMPTY)])
        merged = merge_futures_rows(collect_unit_results(cursor, PLAN))
        runner = SimpleNamespace(ledger=SimpleNamespace(record_stage=lambda n, v: None))
        pc._stage_examples_membership(runner, cursor, PLAN, merged)
        assert runner.examples_membership_reason == "complete"
        assert sum(c["n"] for c in runner.examples_membership.values()) == 6
        assert runner.examples_membership_bank["units"] == 3


# ---------------------------------------------------------------------------
# The deliberate next-generation transition
# ---------------------------------------------------------------------------
#: The digests on master before #994 (origin/master 98d5c0aba7, 2026-10-16).
PRE_994_STAGED_UNIT = "5de54fd27524df3c6af470d7f3c15bb9"
PRE_994_INPUT = "dc2df778434ef3322f0b124214589736"
#: The published predicate, before AND after #994.
PREDICATE = "ea3ef49d2a15568e11d7d8e54240bfdb"


class TestTheTransitionIsDeliberate:
    def test_the_unit_and_input_digests_move(self):
        assert pc.staged_unit_fingerprint() != PRE_994_STAGED_UNIT
        assert pc._main_input_fingerprint() != PRE_994_INPUT

    def test_the_published_predicate_does_not_move(self):
        """The strict publish band is not re-armed: which rows qualify did not
        change, only what Stage B reports about them."""
        assert pc.population_predicate_fingerprint() == PREDICATE

    def test_both_forms_emit_the_member_column(self):
        for frozen in (True, False):
            assert f"AS {MEMBER_COLUMN}" in pc._main_futures_sql(frozen=frozen)

    @pytest.mark.parametrize("stamped", [PRE_994_STAGED_UNIT, PRE_994_INPUT])
    def test_an_in_flight_pre_994_bank_is_not_resumed(self, stamped):
        """The old runtime's bank is never mixed with new units: the cursor it
        wrote invalidates wholesale under this code, by either digest."""
        raw = {
            "schema": STAGED_FUTURES_SCHEMA,
            "task": MAIN_BUILD_TASK,
            "unit_key": "vm_id",
            "population_version": pc.CALIBRATION_POPULATION_VERSION,
            "input_fingerprint": stamped,
            "generation_fingerprint": "gen",
            "committed_units": ["u:a"],
            "accumulator": None,
        }
        _cursor_, action, reason = decode_staged_cursor_detailed(
            raw,
            expected_population_version=pc.CALIBRATION_POPULATION_VERSION,
            expected_input_fingerprint=pc.staged_unit_fingerprint(),
            expected_generation_fingerprint="gen",
            owner=OWNER,
            generation=1,
            now=0.0,
            legacy_input_fingerprint=pc._main_input_fingerprint(),
        )
        assert action == INVALIDATE
        assert reason == REASON_INPUT_FINGERPRINT
