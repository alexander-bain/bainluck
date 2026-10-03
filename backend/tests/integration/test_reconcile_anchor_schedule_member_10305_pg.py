"""#10305 — the anchor-schedule rail moves ONE named row, only as stated (real Postgres).

The claims are about a lock, a transaction and which rows a write reaches, and
only a server can answer those: a fake session returns whatever rowcount it is
told and never blocks. Each test pairs a refusal with the row it protects:

* the stated move lands, with the rail's own undo record naming only it, and
  the rail's restore puts it back;
* a non-member anchored at the SAME clock is decided and left alone;
* drift in a fenced column, or a new anchor on the ESPN id, writes nothing;
* ESPN answering any other time writes nothing (dry says not admissible);
* a row held by another writer is refused, not waited on;
* while the member call holds the row, another writer to it BLOCKS — the fence
  is a lock held through the rail's commit, not a read made before it.

ESPN is stubbed at the rail's own seam (`_fetch_record`). Rows use ids, an ESPN
id range and a clock no other file uses, and only those rows are removed.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10305 one-row "
        "anchor-schedule move (CI job `search-recall` provides one)"
    ),
)
pytestmark = [needs_postgres, pytest.mark.asyncio]

UTC = timezone.utc
MEMBER = 910305001
SIBLING = 910305002   # same clock, same sport, its own ESPN id
DUP = 910305003       # the duplicate: no ESPN id, never in the window
OURS = datetime(2031, 3, 7, 5, 17, tzinfo=UTC)
THEIRS = datetime(2031, 3, 7, 22, 17, tzinfo=UTC)
ESPN_MEMBER = "9103050001"
ESPN_SIBLING = "9103050002"
EXT_MEMBER = "member-10305-odds-a"
EXT_DUP = "member-10305-odds-b"
TAGS = ["provenance:source:odds_api", "provenance:unanchored"]


def _expect(**over):
    base = {
        "espn_id": ESPN_MEMBER,
        "external_id": EXT_MEMBER,
        "home_team_id": None,
        "away_team_id": None,
        "home_team_name": "Atlanta Dream",
        "away_team_name": "New York Liberty",
        "commence_time": OURS.isoformat(),
        "commence_time_source": "odds_api",
        "status": "scheduled",
        "completed_at": None,
        "home_score": None,
        "away_score": None,
        "statpal_fixture_id": None,
        "event_tags": list(TAGS),
    }
    base.update(over)
    return base


EXPECT_ANCHORS = [
    {"event_id": MEMBER, "source": "odds_api", "source_id": EXT_MEMBER, "id_kind": "game"},
]


async def _clear(conn):
    from sqlalchemy import text

    await conn.execute(text(
        "DELETE FROM event_provider_anchors WHERE event_id IN (:a, :b, :c)"
    ), {"a": MEMBER, "b": SIBLING, "c": DUP})
    await conn.execute(text("DELETE FROM events WHERE id IN (:a, :b, :c)"),
                       {"a": MEMBER, "b": SIBLING, "c": DUP})
    await conn.execute(text(
        "DELETE FROM durable_state_snapshots WHERE identity LIKE 'repair:anchor_schedule:undo%' "
        "AND payload::text LIKE '%' || :m || '%'"
    ), {"m": str(MEMBER)})


@pytest.fixture
async def pg_engine():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    tables = [
        Base.metadata.tables[name]
        for name in (
            "sports", "teams", "venues", "events", "event_provider_anchors",
            "durable_state_snapshots",
        )
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        await _clear(conn)
        sport_id = (await conn.execute(text(
            "SELECT id FROM sports WHERE key = 'basketball_wnba'"
        ))).scalar()
        if sport_id is None:
            sport_id = (await conn.execute(text(
                "INSERT INTO sports (key, name, active) VALUES ('basketball_wnba', 'WNBA', true) RETURNING id"
            ))).scalar()
        ins = text("""
            INSERT INTO events (id, sport_id, external_id, espn_id, home_team_name, away_team_name,
                                commence_time, commence_time_source, status, event_tags)
            VALUES (:id, :sp, :ext, :espn, :h, :a, :ct, :src, 'scheduled', CAST(:tags AS jsonb))
        """)
        import json
        for r in (
            dict(id=MEMBER, ext=EXT_MEMBER, espn=ESPN_MEMBER, h="Atlanta Dream", a="New York Liberty",
                 ct=OURS, src="odds_api", tags=json.dumps(TAGS)),
            dict(id=SIBLING, ext=None, espn=ESPN_SIBLING, h="Atlanta Dream", a="Seattle Storm",
                 ct=OURS, src="odds_api", tags="[]"),
            dict(id=DUP, ext=EXT_DUP, espn=None, h="Atlanta Dream", a="New York Liberty",
                 ct=THEIRS, src="espn", tags="[]"),
        ):
            await conn.execute(ins, {**r, "sp": sport_id})
        await conn.execute(text("""
            INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind)
            VALUES (:m, 'odds_api', :em, 'game'), (:d, 'odds_api', :ed, 'game')
        """), {"m": MEMBER, "em": EXT_MEMBER, "d": DUP, "ed": EXT_DUP})
    yield engine
    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


@pytest.fixture
def espn(monkeypatch):
    """ESPN at the rail's own seam. `answers[espn_id] = starts_at`."""
    from app.utils.authority_id_collisions import AuthorityRecord

    answers = {ESPN_MEMBER: THEIRS, ESPN_SIBLING: datetime(2031, 3, 9, 0, 0, tzinfo=UTC)}
    away = {ESPN_MEMBER: "New York Liberty", ESPN_SIBLING: "Seattle Storm"}
    hooks = {"before": None}

    async def fake(service, sport_keys, authority_id):
        if hooks["before"] is not None:
            await hooks["before"]()
        return AuthorityRecord(
            authority_id=authority_id,
            home_names=frozenset({"Atlanta Dream"}),
            away_names=frozenset({away[authority_id]}),
            starts_at=answers[authority_id],
            label="stub",
        )

    monkeypatch.setattr("app.tasks.repair_authority_id_collisions._fetch_record", fake)
    monkeypatch.setattr("app.services.espn_api.get_espn_service", lambda: object())
    return answers, hooks


async def _call(engine, *, apply, expect=None, anchors=None):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.tasks.reconcile_anchor_schedule import reconcile_member

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        return await reconcile_member(
            s, event_id=MEMBER, expect=expect or _expect(),
            expect_anchors=EXPECT_ANCHORS if anchors is None else anchors,
            authority_start=THEIRS.isoformat(), apply=apply,
        )


async def _clock(engine, event_id):
    from sqlalchemy import text

    async with engine.connect() as c:
        row = (await c.execute(text(
            "SELECT commence_time, commence_time_source FROM events WHERE id = :i"
        ), {"i": event_id})).first()
    return row[0].astimezone(UTC), row[1]


async def test_the_stated_move_lands_alone_and_the_rails_restore_puts_it_back(pg_engine, espn):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.tasks.reconcile_anchor_schedule import restore

    dry = await _call(pg_engine, apply=False)
    # The sibling shares the clock, so the page holds two rows: dry must say the
    # plan is NOT the single stated move, and still name the member's move.
    assert dry["examined"] == 2 and dry["member"]["admissible"] is False
    assert await _clock(pg_engine, MEMBER) == (OURS, "odds_api")

    result = await _call(pg_engine, apply=True)
    assert result["moved_event_ids"] == [MEMBER], result
    assert await _clock(pg_engine, MEMBER) == (THEIRS, "espn")
    assert await _clock(pg_engine, SIBLING) == (OURS, "odds_api")  # decided, never written
    assert await _clock(pg_engine, DUP) == (THEIRS, "espn")

    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as s:
        record = await restore(s, result["undo_identity"], apply=False)
    assert [int(r["event_id"]) for r in record["rows"]] == [MEMBER]
    async with maker() as s:
        back = await restore(s, result["undo_identity"], apply=True)
    assert back["reverted"] == 1
    assert await _clock(pg_engine, MEMBER) == (OURS, "odds_api")


async def test_dry_is_admissible_only_for_the_exact_stated_move(pg_engine, espn):
    from sqlalchemy import text

    answers, _ = espn
    async with pg_engine.begin() as c:  # take the sibling out of the window
        await c.execute(text("UPDATE events SET espn_id = NULL WHERE id = :i"), {"i": SIBLING})
    assert (await _call(pg_engine, apply=False))["member"]["admissible"] is True

    answers[ESPN_MEMBER] = datetime(2031, 3, 7, 23, 17, tzinfo=UTC)  # ESPN says another time
    dry = await _call(pg_engine, apply=False)
    assert dry["member"]["admissible"] is False
    applied = await _call(pg_engine, apply=True)
    assert applied["moved_event_ids"] == [] and "MEMBER_MOVE_NOT_ADMITTED" in applied["reason_codes"]
    assert await _clock(pg_engine, MEMBER) == (OURS, "odds_api")


async def test_drift_in_a_fenced_column_writes_nothing(pg_engine, espn):
    from sqlalchemy import text

    async with pg_engine.begin() as c:
        await c.execute(text(
            "UPDATE events SET event_tags = event_tags || '[\"x\"]'::jsonb WHERE id = :i"
        ), {"i": MEMBER})
    result = await _call(pg_engine, apply=True)
    assert result["terminal"] == "refused" and result["reason_codes"] == ["MEMBER_STATE_DRIFT"]
    assert set(result["member"]["fence_diff"]) == {"event_tags"}
    assert await _clock(pg_engine, MEMBER) == (OURS, "odds_api")


async def test_a_new_anchor_on_the_espn_id_writes_nothing(pg_engine, espn):
    from sqlalchemy import text

    async with pg_engine.begin() as c:
        await c.execute(text("""
            INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind)
            VALUES (:d, 'espn', :e, 'game')
        """), {"d": DUP, "e": ESPN_MEMBER})
    result = await _call(pg_engine, apply=True)
    assert result["reason_codes"] == ["MEMBER_STATE_DRIFT"]
    assert set(result["member"]["fence_diff"]) == {"anchors"}
    assert await _clock(pg_engine, MEMBER) == (OURS, "odds_api")


async def test_a_row_held_by_another_writer_is_refused_not_waited_on(pg_engine, espn):
    from sqlalchemy import text

    holder = await pg_engine.connect()
    tx = await holder.begin()
    await holder.execute(text("SELECT 1 FROM events WHERE id = :i FOR UPDATE"), {"i": MEMBER})
    try:
        result = await asyncio.wait_for(_call(pg_engine, apply=True), timeout=30)
    finally:
        await tx.rollback()
        await holder.close()
    assert result["reason_codes"] == ["MEMBER_ROW_LOCKED"]
    assert await _clock(pg_engine, MEMBER) == (OURS, "odds_api")


async def test_while_the_member_call_holds_the_row_another_writer_blocks(pg_engine, espn):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    _, hooks = espn
    seen = {}

    async def other_writer():
        if "blocked" in seen:
            return
        w = create_async_engine(DB_URL, connect_args={"server_settings": {"lock_timeout": "1500"}})
        try:
            async with w.begin() as c:
                await c.execute(text("UPDATE events SET status = 'in_progress' WHERE id = :i"),
                                {"i": MEMBER})
            seen["blocked"] = False
        except Exception as exc:  # noqa: BLE001 — the lock timeout is the observation
            seen["blocked"] = "lock" in str(exc).lower()
        finally:
            await w.dispose()

    hooks["before"] = other_writer
    result = await _call(pg_engine, apply=True)
    assert seen["blocked"] is True
    assert result["moved_event_ids"] == [MEMBER]
    async with pg_engine.connect() as c:
        status = (await c.execute(text("SELECT status FROM events WHERE id = :i"),
                                  {"i": MEMBER})).scalar()
    assert status == "scheduled"
