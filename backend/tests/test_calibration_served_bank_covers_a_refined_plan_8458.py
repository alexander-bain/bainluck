"""#8458 — a finished served bank still publishes after the builder re-cuts the plan.

Production, 2026-09-25: the 140-unit served bank finished at 20:25Z, and the
publish gate's declared succession (#8458, PR #8473) went live on
``bainluck-heavy`` at 02:46Z. The 03:15Z beat did not publish. It never reached
the gate. At 01:30Z the builder's packing sweep had refined 121 slots in one
beat, so the plan went from 140 to 249 units. ``served_covers`` compared unit
KEYS with exact equality. A refined slot's children have new keys, so the
complete served census read as incomplete and the publish-first path (D45(A))
switched off until the 249-unit successor finished, about 31 more beats.

The census does not depend on the cut (a ``128m``-way partition is an exact
refinement of the 128-way one), so the served bank covered the new plan all
along. :func:`refined_cover` says so. These tests pin:

* the production cursor's own keys (the specimen), and
* the real publish pass over the real loop, and
* the controls that must still refuse: an empty child, a missing slot, a bank
  finer than the plan, a slot reached twice, and
* the served drift disclosure, which must count a re-cut served unit as
  uncheckable, not as undrifted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tasks import calibration_main_build as cmb
from app.utils.calibration_staged_futures import (
    UnitChunk,
    bucket_of,
    is_complete,
    new_staged_cursor,
    plan_units,
    refined_cover,
    slot_key,
)
from tests.test_calibration_publish_first_994 import (
    _FakeLedger,
    _publish_pass,
    _roster,
    _serving_state,
    wiring,  # noqa: F401 — the fixture, reused so the loop under test is the same one
)

FIXTURE = Path(__file__).parent / "fixtures" / "calibration_staged_cursor_keys_8458.json"


def _chunk(buckets, index):
    return UnitChunk(index=index, vm_ids=(), market_ids=(), buckets=buckets)


def _cursor(*, served=(), committed=(), splits=None):
    from dataclasses import replace

    cursor = new_staged_cursor(
        population_version="q8458",
        input_fingerprint="fp-8458",
        generation_fingerprint="gen-8458",
        owner="owner-8458",
        generation=1,
    )
    return replace(
        cursor,
        served_units=tuple(served),
        committed_units=tuple(committed),
        unit_splits=dict(splits or {}),
    )


def _slots_by_key(max_buckets=512):
    table = {}
    buckets = 128
    while buckets <= max_buckets:
        for index in range(buckets):
            table[slot_key(buckets, index)] = (buckets, index)
        buckets *= 2
    return table


# =============================================================================
# The one derivation
# =============================================================================


def test_slot_key_is_the_unit_key():
    """``refined_cover`` names parents that have no chunk. If its key recipe
    drifted from :attr:`UnitChunk.key`, every parent would miss and the fix
    would ship inert."""
    for buckets, index in ((128, 0), (128, 127), (256, 133), (512, 5)):
        assert slot_key(buckets, index) == _chunk(buckets, index).key


# =============================================================================
# The specimen: the production cursor at 2026-09-25T03:28:46Z
# =============================================================================


class TestTheProductionCursor:
    @pytest.fixture
    def specimen(self):
        raw = json.loads(FIXTURE.read_text())
        table = _slots_by_key()
        planned = [_chunk(*table[key]) for key in raw["planned_units"]]
        return raw, planned

    def test_the_specimen_is_the_shape_the_issue_describes(self, specimen):
        raw, planned = specimen
        assert len(raw["served_units"]) == 140
        assert len(planned) == 249
        assert len(raw["unit_splits"]) == 121
        assert {unit.key for unit in planned} == set(raw["planned_units"])

    def test_exact_equality_refuses_it(self, specimen):
        """The defect. Without this arm the rest of the class is not testing the fix."""
        raw, planned = specimen
        assert {unit.key for unit in planned} != set(raw["served_units"])

    def test_the_served_bank_covers_the_refined_plan(self, specimen):
        raw, planned = specimen
        cursor = _cursor(served=raw["served_units"], splits=raw["unit_splits"])
        assert cursor.served_covers(planned) is True
        assert is_complete(cursor, planned) is True

    def test_without_the_splits_map_it_is_refused(self, specimen):
        """The map is the evidence. A cover must not be inferred without it."""
        raw, planned = specimen
        cursor = _cursor(served=raw["served_units"], splits={})
        assert cursor.served_covers(planned) is False

    def test_one_served_unit_missing_is_refused(self, specimen):
        raw, planned = specimen
        cursor = _cursor(served=raw["served_units"][1:], splits=raw["unit_splits"])
        assert cursor.served_covers(planned) is False
        assert is_complete(cursor, planned) is False

    def test_one_planned_child_missing_is_refused(self, specimen):
        """An empty child plans no chunk. The served parent then holds questions
        the plan may no longer ask about, so it is not a cover."""
        raw, planned = specimen
        splits = raw["unit_splits"]
        # A child of a slot the served bank holds WHOLE — one cut after it
        # finished. (A child the served bank already holds as itself would be
        # refused as a stranger key, which is a different clause.)
        served = set(raw["served_units"])
        child = next(u for u in planned if u.buckets == 256 and u.key not in served)
        assert slot_key(128, child.index % 128) in served
        cursor = _cursor(served=raw["served_units"], splits=splits)
        rest = [u for u in planned if u is not child]
        assert cursor.served_covers(rest) is False


# =============================================================================
# The controls, on hand-built partitions
# =============================================================================


class TestTheControlsStillRefuse:
    def test_a_slot_reached_twice_is_refused(self):
        """Parent AND its child both banked: the child's questions would be
        counted twice."""
        splits = {"128:5": 2}
        planned = [_chunk(256, 5), _chunk(256, 133)]
        banked = [slot_key(128, 5), slot_key(256, 5)]
        assert refined_cover(banked, planned, splits) is False

    def test_a_bank_finer_than_the_plan_is_refused(self):
        splits = {"128:5": 2}
        planned = [_chunk(128, 5)]
        banked = [slot_key(256, 5), slot_key(256, 133)]
        assert refined_cover(banked, planned, splits) is False

    def test_a_stranger_key_is_refused(self):
        splits = {"128:5": 2}
        planned = [_chunk(256, 5), _chunk(256, 133)]
        banked = [slot_key(128, 5), slot_key(128, 6)]
        assert refined_cover(banked, planned, splits) is False

    def test_a_two_level_refinement_expands_all_the_way_down(self):
        splits = {"128:5": 2, "256:133": 2}
        planned = [_chunk(256, 5), _chunk(512, 133), _chunk(512, 389)]
        assert refined_cover([slot_key(128, 5)], planned, splits) is True
        # The intermediate bank (256-way) is a cover too.
        banked = [slot_key(256, 5), slot_key(256, 133)]
        assert refined_cover(banked, planned, splits) is True
        # And one grandchild short is not.
        assert refined_cover([slot_key(128, 5)], planned[:2], splits) is False

    def test_bare_keys_take_no_refinement_path(self):
        splits = {"128:5": 2}
        planned = [slot_key(256, 5), slot_key(256, 133)]
        assert refined_cover([slot_key(128, 5)], planned, splits) is False

    def test_the_building_bank_is_still_exact(self):
        """``covers`` describes the bank built against THIS plan and must not
        pick up the refinement arm: a coarse building bank is a bank the
        retention step fails closed on."""
        splits = {"128:5": 2}
        planned = [_chunk(256, 5), _chunk(256, 133)]
        cursor = _cursor(committed=[slot_key(128, 5)], splits=splits)
        assert cursor.covers(planned) is False


# =============================================================================
# The real publish pass
# =============================================================================


def _splittable_slots(roster, count):
    """Slots of the 128-way partition whose two 256-way children are both non-empty."""
    halves: dict[int, set[int]] = {}
    for row in roster:
        index = bucket_of(row.vm_id, 128)
        halves.setdefault(index, set()).add(bucket_of(row.vm_id, 256))
    return [index for index, kids in sorted(halves.items()) if len(kids) == 2][:count]


class TestThePublishPassPublishesAcrossARecut:
    @pytest.mark.asyncio
    async def test_a_recut_plan_still_publishes_the_served_bank_first(self, wiring):  # noqa: F811
        """THE SHIP, on the real loop: a complete served bank, then the builder
        refines slots that bank covered whole. The next pass must still publish
        from it without reading a unit, exactly as it did before the cut."""
        pc, store = wiring
        roster = _roster(3000)
        await _serving_state(pc, roster)

        payload = store["cursor"]
        assert payload["served_units"], "precondition: a served bank"
        assert not payload["committed_units"], (
            "precondition: nothing banked in the building slot, as in production "
            "(refine_unit refuses a banked slot)"
        )
        chosen = _splittable_slots(roster, 10)
        assert len(chosen) == 10
        payload["unit_splits"] = {f"128:{index}": 2 for index in chosen}
        refined_plan = plan_units(roster, buckets=128, refinements=payload["unit_splits"])
        assert len(refined_plan) == len(payload["served_units"]) + 10
        assert {u.key for u in refined_plan} != set(payload["served_units"])

        merged, runner, db = await _publish_pass(pc, roster=roster, window_ms=10_000_000)

        assert runner.rebuild_deferred is True, (
            "the re-cut switched the publish-first path off — #8458's third blocker"
        )
        assert merged is not None, "the served bank must publish"
        assert db.unit_reads == 0

    @pytest.mark.asyncio
    async def test_a_recut_with_an_empty_child_does_not_publish_first(self, wiring):  # noqa: F811
        """Control: a split slot with one empty child is not a cover, so the pass
        runs its loop inline as it would with no served bank at all."""
        pc, store = wiring
        # Slot 128:0 keeps only the vm_ids of its child 256:0; child 256:128 is empty.
        roster = [r for r in _roster(3000) if bucket_of(r.vm_id, 256) != 128]
        assert any(bucket_of(r.vm_id, 256) == 0 for r in roster)
        await _serving_state(pc, roster)

        payload = store["cursor"]
        payload["unit_splits"] = {"128:0": 2}

        merged, runner, db = await _publish_pass(pc, roster=roster, window_ms=10_000_000)

        assert runner.rebuild_deferred is False
        assert db.unit_reads > 0


# =============================================================================
# The disclosure beside the published curve
# =============================================================================


class _GaugeRunner:
    def __init__(self):
        self.ledger = _FakeLedger(0)


def test_a_recut_served_unit_is_uncheckable_not_undrifted():
    """``served_drift`` skips a served unit that is not in the plan. Before this
    change the gauge counted only units with no stored digest, so 109 re-cut
    parents in production read as measured and undrifted."""
    served = [slot_key(128, 5), slot_key(128, 6)]
    payload = {
        "served_units": served,
        "served_digests": {name: "d" for name in served},
        "served_drift_units": 0,
        "planned_units": [slot_key(256, 5), slot_key(256, 133), slot_key(128, 6)],
        "served_at": 1_700_000_000.0,
    }
    runner = _GaugeRunner()
    cmb._record_served_bank(runner, payload)
    assert runner.ledger.gauges["staged:served_drift_uncheckable"] == 1


def test_an_absent_plan_is_not_read_as_a_recut():
    served = [slot_key(128, 5)]
    payload = {
        "served_units": served,
        "served_digests": {served[0]: "d"},
        "served_drift_units": 0,
        "served_at": 1_700_000_000.0,
    }
    runner = _GaugeRunner()
    cmb._record_served_bank(runner, payload)
    assert runner.ledger.gauges["staged:served_drift_uncheckable"] == 0
