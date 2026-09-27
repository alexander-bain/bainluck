"""#8910 — the one admission rule every live writer of a source entry now shares.

## the ship

Right after a goal the live headline stops jumping back to the pre-goal number,
and a genuinely newer price is never held back. Three writers stamp a venue's
entry in `win_probability_sources` (the 15-minute matcher, the two-minute poll,
the WebSocket lane), each can hold a reading across the others' commits, and the
real-Postgres gates (`tests/integration/test_live_writers_observation_order_8910_pg.py`
and `..._poll_stamp_race_8910_pg.py`) force those interleavings on the real
writers. This file pins the rule they share, case by case.

## the rule

A reading is refused when ANY row behind it was seen EARLIER than the writer of
the stored value saw that same row. Both sides are observation clocks of the
same rows — never a publication clock, which is what refused Codex's genuinely
newer reading B. Per row, not per minimum, because a stale copy of a devig can
share its minimum with the current one. Unknown, legacy, unbound or disjoint:
no opinion, the write proceeds.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.aggregation import (
    OBSERVED_BASIS_KEY,
    OBSERVED_VALUE_KEY,
    observation_basis,
    reading_regresses_stored_observation,
    stamp_source_reading,
    stored_observation_basis,
)

T0 = datetime(2026, 9, 26, 19, 51, 0, tzinfo=timezone.utc)


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _row(row_id, seconds):
    return SimpleNamespace(
        id=row_id, last_updated=None if seconds is None else _at(seconds)
    )


def _stored(value=0.035, **seen_by_row) -> dict:
    """A stored Kalshi entry whose writer saw each row at T0 + seconds."""
    return stamp_source_reading(
        None, "kalshi", value, now=_at(max(seen_by_row.values(), default=0)),
        observed_basis={k.lstrip("r"): _at(v).timestamp() for k, v in seen_by_row.items()},
    )


def _basis(**seen_by_row) -> dict:
    return observation_basis([_row(int(k.lstrip("r")), v) for k, v in seen_by_row.items()],
                             now=_at(3600))


class TestTheBasis:
    def test_one_clock_per_row_keyed_by_its_id(self):
        assert observation_basis([_row(7, 1), _row(9, 4)], now=_at(3600)) == {
            "7": _at(1).timestamp(), "9": _at(4).timestamp(),
        }

    def test_abstains_like_oldest_observation_time(self):
        assert observation_basis([], now=_at(10)) is None
        assert observation_basis(None, now=_at(10)) is None
        assert observation_basis([_row(7, 1), _row(9, None)], now=_at(10)) is None
        assert observation_basis([SimpleNamespace(id=None, last_updated=_at(1))]) is None

    def test_a_future_clock_is_clamped_like_source_observation_time(self):
        assert observation_basis([_row(7, 50)], now=_at(10)) == {"7": _at(10).timestamp()}


class TestTheRule:
    def test_the_specimen_stale_reading_is_refused(self):
        # The socket saw row 2 post-goal at +23; the poll's reading saw it at +8.
        assert reading_regresses_stored_observation(
            _stored(r2=23), "kalshi", _basis(r2=8)
        ) is True

    def test_equal_and_later_are_admitted(self):
        assert reading_regresses_stored_observation(_stored(r2=23), "kalshi", _basis(r2=23)) is False
        assert reading_regresses_stored_observation(_stored(r2=23), "kalshi", _basis(r2=24)) is False

    def test_newer_b_is_admitted_whatever_a_published_at(self):
        """Codex's clock-domain control: A saw the row at t1, published at t3;
        B saw it at t2 (t1 < t2 < t3). The publication clock is not consulted."""
        stored = stamp_source_reading(
            None, "kalshi", 0.60, now=_at(30),  # published t3
            observed_basis={"2": _at(10).timestamp()},  # observed t1
        )
        assert reading_regresses_stored_observation(stored, "kalshi", _basis(r2=20)) is False

    def test_a_stale_copy_of_a_devig_with_the_same_minimum_is_refused(self):
        """Frozen leg seen at 1, ticking leg seen at 4 in the store; the stale
        copy read the ticking leg at 2. Same minimum (1) — a min-clock rule
        admits it and puts the older price back."""
        assert reading_regresses_stored_observation(
            _stored(r7=1, r9=4), "kalshi", _basis(r7=1, r9=2)
        ) is True

    def test_one_leg_advancing_with_the_other_unchanged_is_admitted(self):
        assert reading_regresses_stored_observation(
            _stored(r7=1, r9=2), "kalshi", _basis(r7=1, r9=4)
        ) is False

    def test_a_crossed_reading_is_refused(self):
        assert reading_regresses_stored_observation(
            _stored(r7=3, r9=2), "kalshi", _basis(r7=1, r9=4)
        ) is True

    def test_it_reads_only_its_own_source(self):
        stored = stamp_source_reading(
            None, "polymarket", 0.04, observed_basis={"2": _at(50).timestamp()},
        )
        assert reading_regresses_stored_observation(stored, "kalshi", _basis(r2=1)) is False


class TestAbstentions:
    @pytest.mark.parametrize(
        "stored",
        [
            None,
            {},
            {"kalshi": 0.03},
            {"kalshi": {"value": 0.03, "updated_at": _at(50).isoformat()}},  # legacy
            {"kalshi": {"value": 0.03, OBSERVED_BASIS_KEY: "garbage", OBSERVED_VALUE_KEY: 0.03}},
            {"kalshi": {"value": 0.03, OBSERVED_BASIS_KEY: {"2": "x"}, OBSERVED_VALUE_KEY: 0.03}},
        ],
        ids=["none", "empty", "bare-float", "legacy-stamp", "basis-not-object", "clock-not-number"],
    )
    def test_nothing_to_order_against(self, stored):
        assert reading_regresses_stored_observation(stored, "kalshi", _basis(r2=1)) is False

    def test_a_reading_with_no_basis(self):
        assert reading_regresses_stored_observation(_stored(r2=50), "kalshi", None) is False

    def test_no_shared_row(self):
        """The group changed which market speaks: not older copies of the same rows."""
        assert reading_regresses_stored_observation(_stored(r2=50), "kalshi", _basis(r5=1)) is False


class TestTheBinding:
    def test_a_basis_is_believed_only_while_it_dates_the_stored_value(self):
        stored = _stored(value=0.035, r2=50)
        assert stored_observation_basis(stored, "kalshi") == {"2": _at(50).timestamp()}
        # A writer outside the helpers changes the value and copies the rest.
        stored["kalshi"]["value"] = 0.77
        assert stored_observation_basis(stored, "kalshi") is None
        assert reading_regresses_stored_observation(stored, "kalshi", _basis(r2=1)) is False

    def test_the_helper_strips_the_basis_from_an_undated_write(self):
        stored = _stored(value=0.035, r2=50)
        rewritten = stamp_source_reading(stored, "kalshi", 0.5)
        assert OBSERVED_BASIS_KEY not in rewritten["kalshi"]
        assert OBSERVED_VALUE_KEY not in rewritten["kalshi"]

    def test_the_helper_binds_the_basis_to_the_value_it_writes(self):
        written = stamp_source_reading(
            {"kalshi": {"value": 0.1, "weight": 2}}, "kalshi", 0.2,
            observed_basis={"2": 1.5},
        )
        assert written["kalshi"][OBSERVED_BASIS_KEY] == {"2": 1.5}
        assert written["kalshi"][OBSERVED_VALUE_KEY] == 0.2
        assert written["kalshi"]["weight"] == 2, "a sibling key was dropped"
