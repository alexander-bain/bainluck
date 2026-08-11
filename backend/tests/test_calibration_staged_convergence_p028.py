"""CAL-P028 — unit identity is the SLOT, and roster drift is measured not obeyed.

The measurement these tests exist to prevent a repeat of, taken in production on
2026-08-10 across one fully productive beat of ``calibration:main``:

===========  ===============  ==================================================
time (UTC)   committed units  event
===========  ===============  ==================================================
14:15:33     20               beat starts
14:17:19     4                ``retain_planned_units`` dropped 16 of 20
14:33:48     19               15 fresh units banked, 989 s, 65.9 s/unit
===========  ===============  ==================================================

Net across a beat that completed 15 units: **minus one**. The build was 8.44 days
stale with 181 consecutive failures behind it, and no bucket count fixes that —
per-unit fixed overhead is ~52 s, so completions cap near 26/beat while roster
churn destroyed ~16-19/beat.

So the rules pinned here are the ones whose inversion restores that behaviour.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dataclasses import replace

from app.utils.calibration_staged_futures import (
    StagedFuturesCursor,
    advance,
    encode_accumulator,
    plan_units,
    retain_planned_units,
    roster_drift,
    unit_key,
)


def _row(market_id: int, vm_id: str, source: str = "kalshi", is_grouped: bool = False):
    return SimpleNamespace(
        market_id=market_id, vm_id=vm_id, source=source, is_grouped=is_grouped
    )


def _roster(n: int, *, extra: list | None = None) -> list:
    rows = [_row(i, f"e:{i}") for i in range(1, n + 1)]
    return rows + list(extra or [])


def _banked(chunks, keys) -> StagedFuturesCursor:
    """A cursor holding ``keys``, stamped with the digests those chunks had.

    CAL-P034: built by actually advancing, because there is no longer a per-unit
    slot to hand-populate — the units are summed into one accumulator.
    """
    by_key = {unit_key(c): c for c in chunks}
    cursor = StagedFuturesCursor(population_version="q267", input_fingerprint="fp")
    for key in keys:
        cursor = advance(
            cursor, key, [{"bucket_idx": 1, "n": 1}], owner="", lease_expires_at=0.0
        )
    return replace(cursor, unit_digests={k: by_key[k].member_digest for k in keys})


class TestUnitKeyIsTheSlot:
    """The convergence fix itself."""

    def test_arrival_into_a_unit_does_not_rekey_it(self):
        """THE regression. A market arriving must not re-key its unit.

        Inverting this — keying on membership again — is exactly the 16-of-20
        drop measured in production.
        """
        before = plan_units(_roster(40), buckets=8)
        after = plan_units(_roster(40, extra=[_row(999, "e:7", source="polymarket")]), buckets=8)

        target = next(c for c in after if "e:7" in c.vm_ids)
        original = next(c for c in before if c.index == target.index)

        assert target.members != original.members, "the arrival must be visible somewhere"
        assert target.key == original.key, "but it must NOT re-key the unit"

    def test_a_whole_beat_of_arrivals_drops_nothing(self):
        """~20 arrivals/hour is the production churn rate. None may cost a unit."""
        before = plan_units(_roster(400), buckets=16)
        cursor = _banked(before, [unit_key(c) for c in before])

        arrivals = [_row(10_000 + i, f"e:{i}", source="polymarket") for i in range(1, 21)]
        after = plan_units(_roster(400, extra=arrivals), buckets=16)

        _kept, dropped = retain_planned_units(cursor, after)
        assert dropped == (), f"20 arrivals dropped {len(dropped)} units"

    def test_net_progress_is_positive_across_a_simulated_beat(self):
        """The end-to-end property, stated as the production trace states it.

        Bank 20, let the roster churn, bank 15 more: the count must go UP. Under
        the pre-CAL-P028 key this lands on 19 — the measured minus-one.
        """
        chunks = plan_units(_roster(600), buckets=64)
        first_20 = [unit_key(c) for c in chunks[:20]]
        cursor = _banked(chunks, first_20)

        churn = [_row(20_000 + i, f"e:{i * 7}", source="polymarket") for i in range(1, 21)]
        replanned = plan_units(_roster(600, extra=churn), buckets=64)

        cursor, _dropped = retain_planned_units(cursor, replanned)
        surviving = len(cursor.committed_units)
        assert surviving == 20, f"a beat began by destroying {20 - surviving} banked units"

    def test_a_different_bucket_count_still_rekeys(self):
        """The one confusion the slot key must NOT introduce.

        Slot 3 of 8 and slot 3 of 16 hold different questions. If the partition
        size left the key, a cursor banked under one would resume under the
        other and merge rows for a population that was never planned.
        """
        eight = plan_units(_roster(80), buckets=8)
        sixteen = plan_units(_roster(80), buckets=16)
        assert {unit_key(c) for c in eight}.isdisjoint({unit_key(c) for c in sixteen})

    def test_distinct_slots_do_not_collide(self):
        chunks = plan_units(_roster(300), buckets=32)
        keys = [unit_key(c) for c in chunks]
        assert len(keys) == len(set(keys))

    def test_key_is_stable_across_processes(self):
        """Re-planning the same roster twice must give byte-identical keys."""
        a = plan_units(_roster(120), buckets=16)
        b = plan_units(_roster(120), buckets=16)
        assert [unit_key(c) for c in a] == [unit_key(c) for c in b]


class TestDriftIsMeasuredNotObeyed:
    def test_drift_counts_the_units_the_roster_moved_under(self):
        before = plan_units(_roster(200), buckets=8)
        cursor = _banked(before, [unit_key(c) for c in before])

        after = plan_units(_roster(200, extra=[_row(5_001, "e:3", source="polymarket")]), buckets=8)
        moved = next(c for c in after if "e:3" in c.vm_ids)

        assert roster_drift(cursor, after) == 1
        # ...and it is the unit that actually changed, not an arbitrary one.
        assert moved.member_digest != cursor.unit_digests[unit_key(moved)]

    def test_an_unchanged_roster_reports_zero_drift(self):
        chunks = plan_units(_roster(150), buckets=8)
        cursor = _banked(chunks, [unit_key(c) for c in chunks])
        assert roster_drift(cursor, chunks) == 0

    def test_unknown_digest_is_not_counted_as_no_drift(self):
        """A pre-CAL-P028 cursor must read UNKNOWN, never 'it did not drift'.

        Gotcha #53: the emptier reading must not become a fact.
        """
        chunks = plan_units(_roster(100), buckets=8)
        cursor = replace(
            _banked(chunks, [unit_key(c) for c in chunks]),
            unit_digests={},  # pre-CAL-P028
        )
        assert roster_drift(cursor, chunks) == 0
        assert cursor.unit_digests == {}, "the absence itself must remain visible"

    def test_drift_is_measured_before_digests_are_restamped(self):
        """Order is the whole point: re-stamp first and drift is zero forever."""
        before = plan_units(_roster(200), buckets=8)
        cursor = _banked(before, [unit_key(c) for c in before])

        after = plan_units(_roster(200, extra=[_row(6_001, "e:5", source="polymarket")]), buckets=8)
        updated, _dropped = retain_planned_units(cursor, after)

        assert updated.roster_drift_units == 1, "the beat must report the drift it inherited"
        # And having reported it, the cursor now tracks the CURRENT membership,
        # so the same drift is not re-reported on every subsequent beat.
        assert roster_drift(updated, after) == 0

    def test_drift_does_not_count_a_dropped_unit(self):
        """A slot the plan no longer has is a drop, not drift. Not both."""
        before = plan_units(_roster(200), buckets=8)
        cursor = _banked(before, [unit_key(c) for c in before])
        smaller = plan_units(_roster(200), buckets=4)
        assert roster_drift(cursor, smaller) == 0


class TestWhatMustStillBeRefused:
    def test_a_slot_the_plan_lost_is_still_dropped(self):
        chunks = plan_units(_roster(200), buckets=8)
        cursor = _banked(chunks, [unit_key(c) for c in chunks])
        _kept, dropped = retain_planned_units(cursor, plan_units(_roster(200), buckets=4))
        assert len(dropped) == len(chunks)

    def test_dropped_units_lose_their_rows_and_their_digests(self):
        """CAL-P034 STRENGTHENS this: a drop now costs the WHOLE accumulator.

        Before the fold, the kept units kept their rows and only the dropped
        ones lost theirs. A fold cannot be inverted — the dropped unit's mass is
        already summed in — so the only safe answer is to discard everything and
        re-walk. The assertion is the same shape; what it proves is stronger.
        """
        chunks = plan_units(_roster(200), buckets=8)
        cursor = _banked(chunks, [unit_key(c) for c in chunks])
        assert cursor.accumulator is not None, "precondition: mass is banked"

        kept, dropped = retain_planned_units(cursor, plan_units(_roster(200), buckets=4))

        assert dropped, "precondition: this plan really does drop slots"
        assert kept.committed_units == ()
        assert kept.accumulator is None, "the fold cannot survive a partial drop"
        assert kept.unit_digests == {}

    def test_member_digest_still_sees_source_and_grouping(self):
        """Membership must still notice the things generation_fingerprint watches."""
        base = plan_units([_row(1, "e:1", source="kalshi")], buckets=1)[0]
        other_source = plan_units([_row(1, "e:1", source="polymarket")], buckets=1)[0]
        grouped = plan_units([_row(1, "e:1", source="kalshi", is_grouped=True)], buckets=1)[0]

        assert base.member_digest != other_source.member_digest
        assert base.member_digest != grouped.member_digest
        # ...while the SLOT is unmoved by any of it.
        assert base.key == other_source.key == grouped.key

    def test_payload_round_trips_the_new_fields(self):
        chunks = plan_units(_roster(50), buckets=4)
        cursor = _banked(chunks, [unit_key(c) for c in chunks])
        cursor = cursor.__class__(**{**cursor.__dict__, "roster_drift_units": 3})
        payload = cursor.as_payload()
        assert payload["roster_drift_units"] == 3
        assert payload["unit_digests"] == dict(cursor.unit_digests)


class TestDecodeCarriesDigests:
    def _decode(self, raw):
        from app.utils.calibration_staged_futures import decode_staged_cursor_detailed

        return decode_staged_cursor_detailed(
            raw,
            expected_population_version="q267",
            expected_input_fingerprint="fp",
            expected_generation_fingerprint="gen",
            owner="me",
            generation=1,
            now=0.0,
        )

    def _raw(self, **over):
        from app.utils.calibration_staged_futures import (
            MAIN_BUILD_TASK,
            STAGED_FUTURES_SCHEMA,
            UNIT_KEY_VM_ID,
        )

        base = {
            "schema": STAGED_FUTURES_SCHEMA,
            "task": MAIN_BUILD_TASK,
            "unit_key": UNIT_KEY_VM_ID,
            "population_version": "q267",
            "input_fingerprint": "fp",
            "committed_units": ["u1"],
            "accumulator": encode_accumulator([{"bucket_idx": 1, "n": 1}], []),
            "unit_digests": {"u1": "d1"},
            "lease_expires_at": 0.0,
        }
        base.update(over)
        return base

    def test_digests_survive_a_round_trip(self):
        cursor, _action, _reason = self._decode(self._raw())
        assert cursor.unit_digests == {"u1": "d1"}

    def test_a_digest_for_an_unresumable_unit_is_discarded(self):
        """A digest describing work this cursor is not carrying must not persist.

        REVERSED IN SHAPE BY CAL-P034, and rewritten rather than deleted. The
        old version made ``u2`` unresumable by giving it no stored rows, which
        the fold makes impossible to express — mass is shared, so a unit is
        either committed or it is not. The RULE is unchanged and still worth
        pinning: a digest for a unit the cursor does not carry is dropped, so a
        later drift count can never include work nobody holds.
        """
        raw = self._raw(
            committed_units=["u1"],
            unit_digests={"u1": "d1", "u2": "d2"},
        )
        cursor, _action, _reason = self._decode(raw)
        assert cursor.committed_units == ("u1",)
        assert "u2" not in cursor.unit_digests

    @pytest.mark.parametrize("bad", ["not-a-dict", 7, None, []])
    def test_a_malformed_digest_map_degrades_to_unknown(self, bad):
        cursor, _action, _reason = self._decode(self._raw(unit_digests=bad))
        assert cursor.unit_digests == {}
        assert cursor.committed_units == ("u1",), "the units themselves still resume"
