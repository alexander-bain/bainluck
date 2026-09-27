"""#2841 Chicago Fire v Vancouver — the one-pair fold's apply, re-run and undo, against a real PostgreSQL.

The unit file drives the refusals with plain values. What the repair DOES is SQL:

* ESPN ``761660`` cleared on the stale row and set on the kept one inside the
  real partial unique index ``uq_events_espn_id`` — the order matters, and only a
  real server enforces it;
* the Kalshi game market re-pointed with an immutable ``market_link_changes``
  row through the real ``flush_receipts`` (``ON CONFLICT`` upsert + append);
* the label appended with ``jsonb`` operators, and removed by the undo without
  touching any other tag;
* and the ship: ``not_a_proven_duplicate()`` — the predicate search, the rails
  and the feed all call — answers with the kept row only.

Built narrow, in a private schema, so it runs on the lane VM's Postgres 14 as
well as in CI.
"""

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2841 "
            "Chicago Fire v Vancouver fold apply/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_2841_pg", _SCRIPTS / "repair_2841_chifire_van_fold.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

_GATE_SCHEMA = "fold_chifire_gate_2841"
MLS = 28410001
OTHER_EVENT = 28410099  # an unrelated MLS game: the control the label must not touch
JULY_MARKET = 55687892  # a resolved July 16 market that stays on the stale row
NOW = datetime(2026, 9, 27, 7, 0, tzinfo=timezone.utc)
GHOST_TAGS = ["league:mls", "sport:soccer", "tier:2"]


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _event(id_, kickoff, espn, odds, tags):
    return (
        f"({id_}, {MLS}, 'Chicago Fire', 'Vancouver Whitecaps FC', '{kickoff.isoformat()}', "
        f"'scheduled', {m.HOME_TEAM_ID}, {m.AWAY_TEAM_ID}, "
        + ("NULL" if espn is None else f"'{espn}'")
        + f", '{odds}', CAST('{json.dumps(tags)}' AS jsonb))"
    )


@pytest.fixture
async def gate(pg_session):
    from app.models.models import MarketLinkChange, MarketMatchReceipt

    s = pg_session
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.execute(text(f"CREATE SCHEMA {_GATE_SCHEMA}"))
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    for ddl in (
        "CREATE TABLE sports (id int PRIMARY KEY, key varchar(50) NOT NULL, "
        "name varchar(100) NOT NULL, active boolean NOT NULL)",
        "CREATE TABLE events (id int PRIMARY KEY, sport_id int NOT NULL REFERENCES sports(id), "
        "home_team_name varchar(200) NOT NULL, away_team_name varchar(200) NOT NULL, "
        "commence_time timestamptz NOT NULL, status varchar(20) NOT NULL, "
        "home_team_id int, away_team_id int, espn_id varchar(50), "
        "external_id varchar(200), event_tags jsonb DEFAULT '[]')",
        # Production's index, verbatim (pg_indexes, 2026-09-27).
        "CREATE UNIQUE INDEX uq_events_espn_id ON events USING btree (espn_id) "
        "WHERE (espn_id IS NOT NULL)",
        "CREATE TABLE futures_markets (id int PRIMARY KEY, event_id int REFERENCES events(id), "
        "source varchar(50) NOT NULL, external_id varchar(200) NOT NULL, "
        "name varchar(300) NOT NULL, status varchar(20) NOT NULL, "
        "category varchar(50) NOT NULL, mutually_exclusive boolean NOT NULL)",
        # Only as a foreign-key target for the receipt table's `container_id`.
        "CREATE TABLE containers (id bigint PRIMARY KEY)",
    ):
        await s.execute(text(ddl))
    conn = await s.connection()
    await conn.run_sync(lambda c: MarketMatchReceipt.__table__.create(c))
    await conn.run_sync(lambda c: MarketLinkChange.__table__.create(c))
    await s.execute(text(
        f"INSERT INTO sports (id, key, name, active) VALUES ({MLS}, '{m.SPORT_KEY}', 'MLS', true)"
    ))
    await s.execute(text(
        "INSERT INTO events (id, sport_id, home_team_name, away_team_name, commence_time, "
        "status, home_team_id, away_team_id, espn_id, external_id, event_tags) VALUES "
        + ", ".join([
            _event(m.GHOST, m.GHOST_KICKOFF, m.ESPN_ID, m.GHOST_ODDS_ID, GHOST_TAGS),
            _event(m.CANON, m.CANON_KICKOFF, None, m.CANON_ODDS_ID,
                   ["provenance:source:odds_api", "provenance:unanchored"]),
            _event(OTHER_EVENT, m.CANON_KICKOFF, "761999", "other-odds-id", []),
        ])
    ))
    await s.execute(text(
        "INSERT INTO futures_markets (id, event_id, source, external_id, name, status, "
        "category, mutually_exclusive) VALUES "
        f"({m.GAME_MARKET}, {m.GHOST}, 'kalshi', '{m.GAME_TICKER}', "
        "'Chicago Fire vs Vancouver', 'open', 'game', true), "
        f"({JULY_MARKET}, {m.GHOST}, 'kalshi', 'KXMLSTOTAL-26JUL16CHIVAN', "
        "'Chicago Fire vs Vancouver: Total Goals', 'resolved', 'game', false)"
    ))
    await s.commit()
    yield s
    await s.rollback()
    await s.execute(text("SET search_path TO public"))
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.commit()


async def _scalar(s, sql, **params):
    return (await s.execute(text(sql), params)).scalar_one()


async def _state(s):
    ev = {
        int(r.id): (r.espn_id, json.loads(r.tags))
        for r in await s.execute(text(
            "SELECT id, espn_id, CAST(event_tags AS text) AS tags FROM events ORDER BY id"
        ))
    }
    mk = {
        int(r.id): r.event_id
        for r in await s.execute(text("SELECT id, event_id FROM futures_markets"))
    }
    return ev, mk


async def _visible(s) -> list[int]:
    """The ids the read side every one-card surface calls admits."""
    from app.models import Event
    from app.utils.proven_duplicates import not_a_proven_duplicate

    res = await s.execute(select(Event.id).where(not_a_proven_duplicate()).order_by(Event.id))
    return [int(i) for i in res.scalars()]


async def _repair(s, mode, evidence=None, now=NOW):
    return await m.repair(s, mode, evidence=evidence, now=now)


async def test_before_the_repair_both_rows_are_visible(gate):
    assert await _visible(gate) == sorted([m.GHOST, m.CANON, OTHER_EVENT])


async def test_dry_run_writes_nothing(gate):
    before = await _state(gate)
    code, lines = await _repair(gate, "dry")
    assert code == 0, lines
    assert "dry run" in "\n".join(lines)
    assert await _state(gate) == before
    assert await _scalar(gate, "SELECT to_regclass(:t) IS NULL", t=m.BACKUP)


async def test_apply_moves_espn_and_market_labels_the_stale_row_and_search_shows_one(gate):
    code, lines = await _repair(gate, "apply")
    assert code == 0, lines
    ev, mk = await _state(gate)
    assert ev[m.GHOST][0] is None and ev[m.CANON][0] == m.ESPN_ID
    assert ev[m.GHOST][1] == GHOST_TAGS + [m.TAG]
    assert mk[m.GAME_MARKET] == m.CANON
    assert mk[JULY_MARKET] == m.GHOST  # not this match's: stays on the hidden row
    assert ev[OTHER_EVENT] == ("761999", [])  # control untouched
    # The ship, through the predicate search/rails/feed call.
    assert await _visible(gate) == sorted([m.CANON, OTHER_EVENT])
    # The link change is on the immutable history, attributed to the repair.
    change = (await gate.execute(text(
        "SELECT market_id, previous_event_id, new_event_id, actor, phase, outcome "
        "FROM market_link_changes"
    ))).all()
    assert [tuple(r) for r in change] == [
        (m.GAME_MARKET, m.GHOST, m.CANON, "admin_repair", "admin_repair",
         "superseded_by_twin_merge")
    ]
    banked = dict((await gate.execute(text(f"SELECT item, before FROM {m.BACKUP}"))).all())
    assert banked["ghost_espn_id"] == m.ESPN_ID
    assert banked["canon_espn_id"] is None
    assert banked["market_event_id"] == str(m.GHOST)
    assert json.loads(banked["ghost_event_tags"]) == GHOST_TAGS


async def test_a_second_apply_is_a_no_op(gate):
    assert (await _repair(gate, "apply"))[0] == 0
    after_first = await _state(gate)
    code, lines = await _repair(gate, "apply")
    assert code == 0 and "already applied" in "\n".join(lines)
    assert await _state(gate) == after_first
    assert await _scalar(gate, "SELECT count(*) FROM market_link_changes") == 1


async def test_restore_puts_back_exactly_what_was_there(gate):
    before = await _state(gate)
    assert (await _repair(gate, "apply"))[0] == 0
    code, lines = await _repair(gate, "restore")
    assert code == 0, lines
    assert await _state(gate) == before
    assert await _visible(gate) == sorted([m.GHOST, m.CANON, OTHER_EVENT])
    # History is append-only: the undo is a second change, not an erasure.
    rows = (await gate.execute(text(
        "SELECT previous_event_id, new_event_id FROM market_link_changes ORDER BY id"
    ))).all()
    assert [tuple(r) for r in rows] == [(m.GHOST, m.CANON), (m.CANON, m.GHOST)]


async def test_restore_keeps_a_tag_another_sweep_added_since(gate):
    assert (await _repair(gate, "apply"))[0] == 0
    await gate.execute(text(
        "UPDATE events SET event_tags = event_tags || CAST('[\"signal:later\"]' AS jsonb) "
        "WHERE id = :g"
    ), {"g": m.GHOST})
    await gate.commit()
    assert (await _repair(gate, "restore"))[0] == 0
    ev, _ = await _state(gate)
    assert ev[m.GHOST][1] == GHOST_TAGS + ["signal:later"]


async def test_restore_leaves_a_market_someone_moved_since(gate):
    assert (await _repair(gate, "apply"))[0] == 0
    await gate.execute(text(
        "UPDATE futures_markets SET event_id = :o WHERE id = :m"
    ), {"o": OTHER_EVENT, "m": m.GAME_MARKET})
    await gate.commit()
    code, lines = await _repair(gate, "restore")
    assert code == 0, lines
    _, mk = await _state(gate)
    assert mk[m.GAME_MARKET] == OTHER_EVENT
    assert '"market": 0' in "\n".join(lines)


async def test_restore_without_an_apply_refuses_and_writes_nothing(gate):
    before = await _state(gate)
    code, lines = await _repair(gate, "restore")
    assert code == 1 and "does not exist" in "\n".join(lines)
    assert await _state(gate) == before


async def test_a_moved_kickoff_refuses_and_writes_nothing(gate):
    await gate.execute(text(
        "UPDATE events SET commence_time = :t WHERE id = :g"
    ), {"t": m.CANON_KICKOFF, "g": m.GHOST})
    await gate.commit()
    before = await _state(gate)
    code, lines = await _repair(gate, "apply")
    assert code == m.REFUSED and "kickoff moved" in "\n".join(lines)
    assert await _state(gate) == before
    assert await _scalar(gate, "SELECT to_regclass(:t) IS NULL", t=m.BACKUP)


async def test_an_evidence_refusal_writes_nothing(gate):
    before = await _state(gate)
    code, lines = await _repair(gate, "apply", evidence="ESPN places 761660 elsewhere")
    assert code == m.REFUSED and "REFUSED (evidence)" in "\n".join(lines)
    assert await _state(gate) == before


async def test_inside_the_last_hour_refuses_and_writes_nothing(gate):
    before = await _state(gate)
    late = m.CANON_KICKOFF.replace(minute=0)
    code, lines = await _repair(gate, "apply", now=late)
    assert code == m.REFUSED and "REFUSED (clock)" in "\n".join(lines)
    assert await _state(gate) == before


async def test_a_failure_mid_apply_rolls_back_everything(gate, monkeypatch):
    before = await _state(gate)
    import app.utils.match_receipts as receipts

    async def boom(session, rows, chunk=500):
        raise RuntimeError("receipt table unavailable")

    monkeypatch.setattr(receipts, "flush_receipts", boom)
    code, lines = await _repair(gate, "apply")
    assert code == 1 and "ROLLED BACK" in "\n".join(lines)
    assert await _state(gate) == before
    assert await _scalar(gate, "SELECT to_regclass(:t) IS NULL", t=m.BACKUP)


async def test_a_racing_writer_on_the_market_rolls_back_everything(gate, monkeypatch):
    """The market moved between the read and the write: the CAS declines, all undone."""
    before = await _state(gate)
    real_apply = m._apply

    async def racing(session, market, now):
        await session.execute(text(
            "UPDATE futures_markets SET event_id = :o WHERE id = :m"
        ), {"o": OTHER_EVENT, "m": m.GAME_MARKET})
        await real_apply(session, market, now)

    monkeypatch.setattr(m, "_apply", racing)
    code, lines = await _repair(gate, "apply")
    assert code == 1 and "move the Kalshi game market" in "\n".join(lines)
    assert await _state(gate) == before


async def test_the_readback_rolls_back_an_apply_that_skipped_a_step(gate, monkeypatch):
    """Every statement is a CAS, so this can only be reached by a changed `_apply`:
    one that returns cleanly having left the market behind. The readback is what
    refuses to commit a half-fold."""
    before = await _state(gate)

    async def espn_only(session, market, now):
        await session.execute(text("UPDATE events SET espn_id = NULL WHERE id = :g"), {"g": m.GHOST})
        await session.execute(
            text("UPDATE events SET espn_id = :e WHERE id = :c"), {"e": m.ESPN_ID, "c": m.CANON}
        )

    monkeypatch.setattr(m, "_apply", espn_only)
    code, lines = await _repair(gate, "apply")
    assert code == 1 and "market readback" in "\n".join(lines)
    assert await _state(gate) == before
