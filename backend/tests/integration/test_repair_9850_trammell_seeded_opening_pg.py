"""#9850 — the seeded-opening repair's apply, re-run, undo and refusals, against a real PostgreSQL.

The unit file drives the state machine with a fake. What the repair DOES is SQL,
and its binds are typed values (``Decimal``, an aware ``datetime``, ``int``)
compared against ``numeric(7,6)``, ``timestamptz`` and ``integer`` columns — the
part only a real server can prove:

* the pinned read of the market and its two legs;
* the banked pre-image in ``backup_9850_opening`` (runtime DDL);
* the compare-and-swap clear of the three opening columns, and nothing else;
* a re-run that finds nothing left to write;
* an undo that writes the exact BEFORE values back;
* the refusals that must leave both legs untouched.

CERT-3878's follow-up ``9850-REPAIR-REAL-PG-GUARD``. Built narrow, in a private
schema, so it runs on the lane VM's Postgres 14 as well as in CI.
"""

import importlib.util
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9850 "
            "seeded-opening apply/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_9850_pg", _SCRIPTS / "repair_9850_trammell_seeded_opening.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

_GATE_SCHEMA = "seeded_opening_gate_9850"
EVENT = 15321836
#: A neighbouring leg on another market: the repair must never touch it.
NEIGHBOUR_MARKET, NEIGHBOUR_LEG = 63363780, 238762817


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _leg(oid, market_id, name, prob, odds, current, *, is_winner="NULL", calib="NULL"):
    prob_sql = "NULL" if prob is None else f"{prob}"
    odds_sql = "NULL" if odds is None else f"{odds}"
    at_sql = "NULL" if prob is None else "'2026-09-30 06:16:11.708357+00'"
    return (
        f"({oid}, {market_id}, '{oid}', '{name}', {prob_sql}, {odds_sql}, {at_sql}, "
        f"NULL, {is_winner}, {calib}, {current}, now())"
    )


async def _seed(s, *, over=None, under=None):
    over = over or _leg(m.OVER, m.MARKET_ID, "Over", "0.475000", 111, "0.050000")
    under = under or _leg(m.UNDER, m.MARKET_ID, "Under", "0.525000", -111, "0.950000")
    await s.execute(
        text(
            "INSERT INTO futures_markets (id, source, external_id, name, category, "
            "mutually_exclusive, status, event_id) VALUES "
            f"({m.MARKET_ID}, 'polymarket', '0x9850', '{m.PINNED_MARKET[1]}', 'game_prop', "
            f"true, 'open', {EVENT}), "
            f"({NEIGHBOUR_MARKET}, 'polymarket', '0x9850n', "
            f"'Christian Walker: Home Runs O/U 0.5', 'game_prop', true, 'open', {EVENT})"
        )
    )
    await s.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
            "opening_probability, opening_american_odds, opening_captured_at, "
            "opening_source, is_winner, calibration_probability, current_probability, "
            "last_updated) VALUES "
            + ", ".join(
                [
                    over,
                    under,
                    _leg(NEIGHBOUR_LEG, NEIGHBOUR_MARKET, "Over", "0.155000", 545, "0.085000"),
                ]
            )
        )
    )
    await s.commit()
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))


@pytest.fixture
async def schema(pg_session):
    s = pg_session
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.execute(text(f"CREATE SCHEMA {_GATE_SCHEMA}"))
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    for ddl in (
        "CREATE TABLE futures_markets (id int PRIMARY KEY, source varchar(20) NOT NULL, "
        "external_id varchar(200) NOT NULL, name varchar(500) NOT NULL, "
        "category varchar(50) NOT NULL, mutually_exclusive boolean NOT NULL, "
        "status varchar(20) NOT NULL, event_id int)",
        "CREATE TABLE futures_outcomes (id int PRIMARY KEY, "
        "market_id int NOT NULL REFERENCES futures_markets(id), "
        "external_id varchar(200) NOT NULL, name varchar(300) NOT NULL, "
        "opening_probability numeric(7,6), opening_american_odds int, "
        "opening_captured_at timestamptz, opening_source varchar(30), is_winner boolean, "
        "calibration_probability numeric(7,6), current_probability numeric(7,6), "
        "last_updated timestamptz NOT NULL)",
    ):
        await s.execute(text(ddl))
    await s.commit()
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    yield s
    await s.rollback()
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.commit()


async def _legs(s):
    rows = await s.execute(
        text(
            "SELECT id, opening_probability, opening_american_odds, opening_captured_at, "
            "current_probability FROM futures_outcomes ORDER BY id"
        )
    )
    return {int(r.id): tuple(r)[1:] for r in rows}


class TestTheRepairOnARealServer:
    async def test_apply_clears_only_the_three_opening_columns_and_banks_first(self, schema):
        s = schema
        await _seed(s)
        before = await _legs(s)
        out = await m.run(s, apply=True, restore=False)
        await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
        assert out["written"] == 2
        after = await _legs(s)
        for oid in (m.OVER, m.UNDER):
            assert after[oid][:3] == (None, None, None), oid
            assert after[oid][3] == before[oid][3], "current price moved"
        assert after[NEIGHBOUR_LEG] == before[NEIGHBOUR_LEG], "a neighbouring leg moved"
        banked = await s.execute(
            text(
                f"SELECT outcome_id, name, opening_probability, opening_american_odds, "
                f"opening_captured_at FROM {m.BACKUP_TABLE} ORDER BY outcome_id"
            )
        )
        assert {
            int(r.outcome_id): m._state(tuple(r)[1:]) for r in banked
        } == m.BEFORE

    async def test_a_second_apply_writes_nothing(self, schema):
        s = schema
        await _seed(s)
        await m.run(s, apply=True, restore=False)
        await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
        out = await m.run(s, apply=True, restore=False)
        assert out["planned"] == [] and out["written"] == 0

    async def test_restore_writes_the_exact_before_back(self, schema):
        s = schema
        await _seed(s)
        before = await _legs(s)
        await m.run(s, apply=True, restore=False)
        await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
        out = await m.run(s, apply=False, restore=True)
        await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
        assert out["written"] == 2
        assert await _legs(s) == before
        assert before[m.OVER][0] == Decimal("0.475000")

    async def test_drift_refuses_and_writes_nothing(self, schema):
        s = schema
        await _seed(
            s, over=_leg(m.OVER, m.MARKET_ID, "Over", "0.060000", 1567, "0.050000")
        )
        before = await _legs(s)
        with pytest.raises(m.Refused):
            await m.run(s, apply=True, restore=False)
        await s.rollback()
        await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
        assert await _legs(s) == before

    async def test_a_graded_leg_refuses_and_writes_nothing(self, schema):
        s = schema
        await _seed(
            s,
            under=_leg(
                m.UNDER, m.MARKET_ID, "Under", "0.525000", -111, "0.950000", is_winner="true"
            ),
        )
        before = await _legs(s)
        with pytest.raises(m.Refused, match="graded"):
            await m.run(s, apply=True, restore=False)
        await s.rollback()
        await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
        assert await _legs(s) == before
