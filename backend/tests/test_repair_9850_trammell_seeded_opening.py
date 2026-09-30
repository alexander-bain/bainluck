"""#9850 — the repair that withdraws Trammell's seeded 47% opening (market 63386735).

Production 2026-09-30: both legs of "Taylor Trammell: Home Runs O/U 0.5" carry an
opening stamped from a 0.01 / 0.99 listing book with no trade (0.475 / 0.525), and
The script leads /events/15321836 with it. PR #9852 stops the writer; these tests
pin the one-market repair's state machine, its refusals, its backup-before-write
order and its compare-and-swap.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import repair_9850_trammell_seeded_opening as repair  # noqa: E402

OVER, UNDER = repair.OVER, repair.UNDER


def _legs(state: dict, *, source=None, is_winner=None, calibration=None) -> dict:
    return {oid: (*state[oid], source, is_winner, calibration) for oid in state}


class TestTheManifest:
    def test_the_specimen(self):
        assert repair.MARKET_ID == 63386735
        assert repair.PINNED_MARKET == (
            "polymarket",
            "Taylor Trammell: Home Runs O/U 0.5",
            15321836,
        )
        assert repair.BEFORE[OVER][1:3] == (Decimal("0.475000"), 111)
        assert repair.BEFORE[UNDER][1:3] == (Decimal("0.525000"), -111)
        assert repair.BEFORE[OVER][3] == repair.BEFORE[UNDER][3]
        assert repair.BEFORE[OVER][3].isoformat() == "2026-09-30T06:16:11.708357+00:00"

    def test_after_clears_all_three_opening_columns_on_both_legs(self):
        for oid in (OVER, UNDER):
            assert repair.AFTER[oid][1:] == (None, None, None)

    def test_it_writes_only_the_three_opening_columns(self):
        for stmt in (repair._CLEAR, repair._RESTORE):
            sql = str(stmt)
            set_clause = sql.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
            assert set(c.split("=")[0].strip() for c in set_clause.split(",")) == {
                "opening_probability",
                "opening_american_odds",
                "opening_captured_at",
            }
            assert "futures_odds_snapshots" not in sql
            assert "current_probability" not in sql

    def test_every_update_compare_and_swaps_on_the_full_state(self):
        # The fake below enforces CAS itself, so the SQL's own WHERE is pinned here.
        guards = (
            "id = :id", "market_id = :mid", "opening_source IS NULL",
            "is_winner IS NULL", "calibration_probability IS NULL",
        )
        clear = str(repair._CLEAR).split(" WHERE ", 1)[1]
        restore = str(repair._RESTORE).split(" WHERE ", 1)[1]
        for where in (clear, restore):
            for g in guards:
                assert g in where, g
        for col, param in (
            ("opening_probability", ":prob"),
            ("opening_american_odds", ":odds"),
            ("opening_captured_at", ":at"),
        ):
            assert f"{col} = {param}" in clear
            assert f"{col} IS NULL" in restore


class TestThePlan:
    def test_apply_clears_both_legs(self):
        writes = repair.plan(repair.PINNED_MARKET, _legs(repair.BEFORE), restore=False)
        assert [w[0] for w in writes] == [OVER, UNDER]
        assert all(w[2] == repair.AFTER[w[0]] for w in writes)

    def test_restore_writes_the_before_values_back(self):
        writes = repair.plan(repair.PINNED_MARKET, _legs(repair.AFTER), restore=True)
        assert all(w[2] == repair.BEFORE[w[0]] for w in writes)

    def test_a_second_apply_writes_nothing(self):
        assert repair.plan(repair.PINNED_MARKET, _legs(repair.AFTER), restore=False) == []

    def test_restore_before_any_apply_writes_nothing(self):
        assert repair.plan(repair.PINNED_MARKET, _legs(repair.BEFORE), restore=True) == []

    def test_a_db_decimal_and_a_float_read_the_same(self):
        # Production hands Decimal('0.475000'); a float spelling must not read as drift.
        state = {oid: (n, float(p), o, a) for oid, (n, p, o, a) in repair.BEFORE.items()}
        assert repair.plan(repair.PINNED_MARKET, _legs(state), restore=False)


class TestRefusals:
    @pytest.mark.parametrize(
        "state",
        [
            {OVER: repair.BEFORE[OVER], UNDER: repair.AFTER[UNDER]},  # half applied
            {OVER: ("Over", Decimal("0.060000"), 1567, repair._LISTED_AT), UNDER: repair.BEFORE[UNDER]},
        ],
    )
    def test_any_other_state_refuses_the_whole_run(self, state):
        with pytest.raises(repair.Refused):
            repair.plan(repair.PINNED_MARKET, _legs(state), restore=False)

    def test_a_restamped_opening_refuses_restore(self):
        # The writer stamped a real opening after the clear: never overwrite it.
        state = {OVER: ("Over", Decimal("0.060000"), 1567, repair._LISTED_AT), UNDER: repair.AFTER[UNDER]}
        with pytest.raises(repair.Refused):
            repair.plan(repair.PINNED_MARKET, _legs(state), restore=True)

    def test_a_graded_leg_refuses(self):
        with pytest.raises(repair.Refused, match="graded"):
            repair.plan(repair.PINNED_MARKET, _legs(repair.BEFORE, is_winner=False), restore=False)

    def test_a_calibration_probability_refuses(self):
        with pytest.raises(repair.Refused, match="calibration_probability"):
            repair.plan(
                repair.PINNED_MARKET,
                _legs(repair.BEFORE, calibration=Decimal("0.05")),
                restore=False,
            )

    def test_a_sourced_opening_refuses(self):
        with pytest.raises(repair.Refused, match="opening_source"):
            repair.plan(repair.PINNED_MARKET, _legs(repair.BEFORE, source="clob_history"), restore=False)

    def test_a_market_that_no_longer_reads_as_pinned_refuses(self):
        with pytest.raises(repair.Refused, match="pinned"):
            repair.plan(("polymarket", "Other: Home Runs O/U 0.5", 15321836), _legs(repair.BEFORE), restore=False)

    def test_a_missing_market_refuses(self):
        with pytest.raises(repair.Refused, match="missing"):
            repair.plan(None, _legs(repair.BEFORE), restore=False)

    def test_an_extra_leg_refuses(self):
        legs = _legs(repair.BEFORE)
        legs[999] = ("Push", None, None, None, None, None, None)
        with pytest.raises(repair.Refused, match="outcomes"):
            repair.plan(repair.PINNED_MARKET, legs, restore=False)

    def test_it_refuses_off_production(self):
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({})
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _FakeDB:
    """Holds the two legs and a backup table; interprets the script's own statements."""

    def __init__(self, state, *, bank_ok=True, drift_on_write=False):
        self.legs = {oid: list(v) for oid, v in state.items()}
        self.backup: dict[int, tuple] = {}
        self.bank_ok = bank_ok
        self.drift_on_write = drift_on_write
        self.log: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        if sql.startswith("SELECT source, name, event_id"):
            return _Result([SimpleNamespace(source="polymarket", name=repair.PINNED_MARKET[1], event_id=15321836)])
        if sql.startswith("SELECT id, name, opening_probability"):
            return _Result(
                SimpleNamespace(
                    id=oid, name=v[0], opening_probability=v[1], opening_american_odds=v[2],
                    opening_captured_at=v[3], opening_source=None, is_winner=None,
                    calibration_probability=None,
                )
                for oid, v in self.legs.items()
            )
        if sql.startswith("CREATE TABLE"):
            self.log.append("create_backup")
            return _Result()
        if sql.startswith(f"INSERT INTO {repair.BACKUP_TABLE}"):
            self.log.append("bank")
            if self.bank_ok:
                for oid in params["ids"]:
                    self.backup.setdefault(oid, tuple(self.legs[oid]))
            return _Result()
        if sql.startswith("SELECT outcome_id"):
            return _Result(
                SimpleNamespace(outcome_id=oid, name=v[0], opening_probability=v[1],
                                opening_american_odds=v[2], opening_captured_at=v[3])
                for oid, v in self.backup.items()
            )
        if sql.startswith("UPDATE futures_outcomes"):
            oid = params["id"]
            self.log.append(f"update:{oid}")
            if self.drift_on_write and oid == UNDER:
                return _Result(rowcount=0)
            restoring = "opening_probability IS NULL AND" in sql
            cur = repair._state(tuple(self.legs[oid]))
            expect = repair.AFTER[oid] if restoring else repair.BEFORE[oid]
            if cur != expect:
                return _Result(rowcount=0)
            self.legs[oid] = list(repair.BEFORE[oid] if restoring else repair.AFTER[oid])
            return _Result(rowcount=1)
        raise AssertionError(f"unexpected statement: {sql[:80]}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class TestTheRun:
    async def test_dry_run_writes_nothing(self):
        db = _FakeDB(repair.BEFORE)
        out = await repair.run(db, apply=False, restore=False)
        assert out["written"] == 0 and len(out["planned"]) == 2
        assert not any(e.startswith(("update", "bank")) for e in db.log)

    async def test_apply_banks_before_it_writes_and_reads_back(self):
        db = _FakeDB(repair.BEFORE)
        out = await repair.run(db, apply=True, restore=False)
        assert db.log.index("bank") < db.log.index(f"update:{OVER}")
        assert out["written"] == 2
        assert out["now"] == {str(o): str(repair.AFTER[o]) for o in (OVER, UNDER)}
        assert {o: repair._state(v) for o, v in db.backup.items()} == repair.BEFORE

    async def test_a_short_bank_refuses_before_any_write(self):
        db = _FakeDB(repair.BEFORE, bank_ok=False)
        with pytest.raises(repair.Refused, match="backup"):
            await repair.run(db, apply=True, restore=False)
        assert not any(e.startswith("update") for e in db.log)

    async def test_drift_mid_run_rolls_back(self):
        db = _FakeDB(repair.BEFORE, drift_on_write=True)
        with pytest.raises(repair.Refused, match="changed under the run"):
            await repair.run(db, apply=True, restore=False)
        assert db.rollbacks == 1

    async def test_restore_round_trips(self):
        db = _FakeDB(repair.BEFORE)
        await repair.run(db, apply=True, restore=False)
        out = await repair.run(db, apply=False, restore=True)
        assert out["written"] == 2
        assert {o: repair._state(tuple(v)) for o, v in db.legs.items()} == repair.BEFORE
