"""#10319 — the one-event identity repair's preflight, apply and restore against a real PostgreSQL.

REHEARSAL DATA ONLY. Every row below is synthetic, built in a private per-test
schema with the exact ids the tool pins (event 15321333, market 63152777, Sport
427850) and a fixed clock. Nothing here reads or writes an existing schema, and
nothing is copied from production beyond the retained identity strings the packet
already quotes.

What only a server can say, and so what this file grades:

* the preflight's REPEATABLE READ READ ONLY transaction leaves the database as it
  found it, and its plan names exactly one event and four columns;
* the apply writes exactly those four columns on exactly that row, with real NULL
  and jsonb binds, and leaves every other event column, every other event, the
  Sport rows, the market and the teams byte-identical;
* a stale score / FK / name / tag order / status, or a changed source / ticker /
  competition on the market, makes the compare-and-swap refuse with zero writes;
* another session holding the event row makes the apply refuse within its lock
  budget, and a concurrently linked market (an uncommitted FK insert) is fenced by
  that same lock;
* restore puts the full banked before-image back, refuses after a later change to
  a written or fenced column or a tag reorder, and leaves that later state alone.

    createdb bl_10319
    SEARCH_TEST_DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost:5432/bl_10319" \\
      python3 -m pytest tests/integration/test_repair_10319_event15321333_competition_identity_pg.py -v -rs
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10319 "
            "event 15321333 identity repair rehearsal"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_10319_pg", _SCRIPTS / "repair_10319_event15321333_competition_identity.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


r = _load()

MEN_SPORT_ID = 7  # rehearsal id for men's soccer_italy_serie_a
OTHER_EVENT = 15306081  # rehearsal sibling: a men's game that must never move
HOME_TEAM, AWAY_TEAM = 901, 902
FIXED = "2026-10-03T21:00:00+00:00"

PRE_TAGS = [
    "sport:soccer", "gender:men", "league:serie_a", "level:professional",
    "importance:regular", "tier:2", "class:international", "status:completed",
    "timing:past", "audience:niche",
]
WPS = {"kalshi": {"home": 0.31, "updated_at": "2026-10-03T12:20:00+00:00"}}


@pytest.fixture
async def factory():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    schema = f"r10319_{uuid.uuid4().hex[:10]}"
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
    eng = create_async_engine(DB_URL, connect_args={"server_settings": {"search_path": schema}})
    async with eng.begin() as conn:
        for ddl in (
            """CREATE TABLE sports (id integer PRIMARY KEY, key varchar(50) UNIQUE NOT NULL,
               name varchar(100) NOT NULL, "group" varchar(50), active boolean)""",
            """CREATE TABLE teams (id integer PRIMARY KEY, sport_id integer REFERENCES sports(id),
               name varchar(200) NOT NULL)""",
            """CREATE TABLE events (
                id integer PRIMARY KEY, sport_id integer REFERENCES sports(id),
                external_id varchar(100) UNIQUE,
                home_team_id integer REFERENCES teams(id), away_team_id integer REFERENCES teams(id),
                home_team_name varchar(200), away_team_name varchar(200),
                commence_time timestamptz, status varchar(20),
                home_score integer, away_score integer, completed_at timestamptz,
                espn_id varchar(50), llm_gender varchar(20), llm_level varchar(20),
                llm_league varchar(50), llm_importance varchar(20),
                event_tags jsonb DEFAULT '[]', win_probability_sources jsonb,
                score_source varchar(20), game_clock varchar(20))""",
            """CREATE TABLE futures_markets (
                id integer PRIMARY KEY, event_id integer REFERENCES events(id),
                sport_id integer REFERENCES sports(id), source varchar(50) NOT NULL,
                external_id varchar(200) NOT NULL, name varchar(300) NOT NULL,
                category varchar(50) NOT NULL, mutually_exclusive boolean NOT NULL,
                status varchar(20) NOT NULL, market_metadata jsonb)""",
            "CREATE INDEX ix_fm_event ON futures_markets(event_id)",
        ):
            await conn.execute(text(ddl))
        await conn.execute(text(
            'INSERT INTO sports (id, key, name, "group", active) VALUES '
            f"({MEN_SPORT_ID}, 'soccer_italy_serie_a', 'Serie A - Italy', 'Soccer', true), "
            f"({r.WOMEN_SPORT_ID}, '{r.WOMEN_SPORT_KEY}', '{r.WOMEN_SPORT_NAME}', 'Soccer', true), "
            "(8, 'soccer_epl', 'EPL', 'Soccer', true)"
        ))
        await conn.execute(text(
            f"INSERT INTO teams (id, sport_id, name) VALUES ({HOME_TEAM}, {r.WOMEN_SPORT_ID}, 'Parma Calcio'), "
            f"({AWAY_TEAM}, {r.WOMEN_SPORT_ID}, 'Ternana'), (903, {MEN_SPORT_ID}, 'Parma Calcio')"
        ))
        for eid, ext, tags in ((r.EVENT_ID, "kalshi_KXSERIEAWGAME-26OCT03PARTER", PRE_TAGS),
                               (OTHER_EVENT, "kalshi_KXSERIEAGAME-26SEP20PARGEN", PRE_TAGS)):
            await conn.execute(
                text(
                    "INSERT INTO events (id, sport_id, external_id, home_team_id, away_team_id, "
                    "home_team_name, away_team_name, commence_time, status, home_score, away_score, "
                    "completed_at, espn_id, llm_gender, llm_level, llm_league, llm_importance, "
                    "event_tags, win_probability_sources, score_source, game_clock) VALUES "
                    "(:id, :sid, :ext, :h, :a, 'Parma Calcio', 'Ternana', :ct, 'completed', 0, 1, "
                    ":done, NULL, 'men', 'professional', 'Serie_A', 'regular', "
                    "CAST(:tags AS jsonb), CAST(:wps AS jsonb), 'espn', 'FT')"
                ),
                {"id": eid, "sid": MEN_SPORT_ID, "ext": ext,
                 "h": HOME_TEAM if eid == r.EVENT_ID else None,
                 "a": AWAY_TEAM if eid == r.EVENT_ID else None,
                 "ct": datetime(2026, 10, 3, 10, 30, tzinfo=timezone.utc),
                 "done": datetime(2026, 10, 3, 12, 24, 5, 123456, tzinfo=timezone.utc),
                 "tags": json.dumps(tags), "wps": json.dumps(WPS)},
            )
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, event_id, sport_id, source, external_id, name, "
                "category, mutually_exclusive, status, market_metadata) VALUES "
                "(:mid, :eid, :msid, 'kalshi', 'KXSERIEAWGAME-26OCT03PARTER', 'Parma vs Ternana', "
                "'game', true, 'resolved', CAST(:meta AS jsonb)), "
                "(63000001, :other, :msid, 'kalshi', 'KXSERIEAGAME-26SEP20PARGEN', 'Parma vs Genoa', "
                "'game', true, 'resolved', '{\"competition\": \"Serie A\"}')"
            ),
            {"mid": r.MARKET_ID, "eid": r.EVENT_ID, "other": OTHER_EVENT, "msid": MEN_SPORT_ID,
             "meta": json.dumps({"competition": "Serie A Femminile", "competition_scope": "Game",
                                 "venue_note": "kept"})},
        )
    maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        yield maker
    finally:
        await eng.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await admin.dispose()


async def _exec(factory, sql, params=None):
    async with factory() as s:
        await s.execute(text(sql), params or {})
        await s.commit()


async def _snapshot(factory) -> dict:
    """Every row of every table, as text, for byte-level before/after comparison."""
    out = {}
    async with factory() as s:
        for table in ("sports", "teams", "events", "futures_markets"):
            rows = (await s.execute(text(f"SELECT to_jsonb(t)::text FROM {table} t ORDER BY id"))).scalars().all()
            out[table] = [json.loads(x) for x in rows]
        await s.rollback()
    return out


def _event(snap, eid=r.EVENT_ID):
    return next(e for e in snap["events"] if e["id"] == eid)


async def _plan(factory, tmp_path):
    out = await r.run_preflight(factory, plan_out=str(tmp_path / "plan.json"), clock=lambda: FIXED)
    assert out["state"] == r.PLANNED, out
    return out["plan"]


async def _apply(factory, tmp_path, plan, **kw):
    return await r.run_apply(
        factory, plan_path=plan["path"], plan_hash=plan["sha256"],
        backup_out=str(tmp_path / "backup.json"), clock=lambda: FIXED, **kw,
    )


async def test_preflight_is_read_only_and_names_one_row_four_columns(factory, tmp_path):
    before = await _snapshot(factory)
    out = await r.run_preflight(factory, plan_out=str(tmp_path / "plan.json"), clock=lambda: FIXED)
    assert out["state"] == r.PLANNED and out["counts"]["written_rows"] == 0
    assert await _snapshot(factory) == before
    assert set(out["proposed_diff"]) == set(r.WRITTEN_COLUMNS)
    assert out["proposed_diff"]["sport_id"] == {"from": MEN_SPORT_ID, "to": r.WOMEN_SPORT_ID}
    assert out["preserved"]["completed_at"] == "2026-10-03T12:24:05.123456+00:00"
    assert out["preserved"]["espn_id"] is None
    plan = json.loads(Path(out["plan"]["path"]).read_bytes())
    assert plan["banked_unwritten"]["win_probability_sources"] == WPS
    assert plan["corroboration"]["market_recorded"] == {"sport_id": MEN_SPORT_ID,
                                                        "sport_key": "soccer_italy_serie_a"}
    assert [s["verdict"] for s in plan["team_compatibility"]] == ["SOUND", "SOUND"]


async def test_preflight_transaction_is_really_read_only(factory):
    """The SET TRANSACTION the preflight issues makes a write in it fail on the server."""
    async with factory() as s:
        await s.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        with pytest.raises(Exception, match="read-only transaction"):
            await s.execute(text("UPDATE events SET status = 'x' WHERE id = :e"), {"e": r.EVENT_ID})
        await s.rollback()


async def test_apply_writes_exactly_one_row_four_columns(factory, tmp_path):
    plan = await _plan(factory, tmp_path)
    before = await _snapshot(factory)
    out = await _apply(factory, tmp_path, plan)
    assert out["state"] == r.APPLIED, out
    assert out["counts"] == {"event_id": r.EVENT_ID, "written_rows": 1, "written_columns": 4,
                             "concurrent_drift": 0}
    after = await _snapshot(factory)
    for table in ("sports", "teams", "futures_markets"):
        assert after[table] == before[table]
    assert _event(after, OTHER_EVENT) == _event(before, OTHER_EVENT)
    b, a = _event(before), _event(after)
    changed = {k for k in a if a[k] != b[k]}
    assert changed == set(r.WRITTEN_COLUMNS)
    assert a["sport_id"] == r.WOMEN_SPORT_ID
    assert (a["llm_gender"], a["llm_league"]) == ("women", "Serie_A_Femminile")
    want = list(PRE_TAGS)
    for old, new in r.TAG_SUBSTITUTIONS:
        want[want.index(old)] = new
    assert a["event_tags"] == want
    assert a["win_probability_sources"] == WPS and a["espn_id"] is None
    assert Path(out["backup"]["path"] + ".sha256").read_text().split()[0] == out["backup"]["sha256"]
    assert Path(out["receipt"]["path"]).exists()


@pytest.mark.parametrize(
    "sql, reason_prefix",
    [
        ("UPDATE events SET home_score = 2 WHERE id = :e", "concurrent_drift:home_score"),
        ("UPDATE events SET away_team_id = NULL WHERE id = :e", "concurrent_drift:away_team_id"),
        ("UPDATE events SET home_team_name = 'Parma' WHERE id = :e", "concurrent_drift:home_team_name"),
        ("UPDATE events SET status = 'scheduled' WHERE id = :e", "concurrent_drift:status"),
        ("UPDATE events SET event_tags = (SELECT jsonb_agg(x ORDER BY x) FROM "
         "jsonb_array_elements(event_tags) x) WHERE id = :e", "concurrent_drift:event_tags"),
        ("UPDATE futures_markets SET source = 'polymarket' WHERE id = 63152777", "identity_drift:source"),
        ("UPDATE futures_markets SET external_id = 'KXSERIEAWGAME-26OCT03PARTER-PAR' WHERE id = 63152777",
         "identity_drift:external_id"),
        ("UPDATE futures_markets SET market_metadata = market_metadata || "
         "'{\"competition\": \"Serie A\"}' WHERE id = 63152777", "identity_drift:competition"),
        ("UPDATE futures_markets SET market_metadata = market_metadata - 'competition_scope' "
         "WHERE id = 63152777", "identity_drift:competition_scope"),
        ("UPDATE futures_markets SET event_id = NULL WHERE id = 63152777", "identity_drift:event_id"),
        ("UPDATE teams SET sport_id = 7 WHERE id = 901", "identity_drift:team_home"),
    ],
)
async def test_stale_pre_image_or_identity_writes_nothing(factory, tmp_path, sql, reason_prefix):
    plan = await _plan(factory, tmp_path)
    await _exec(factory, sql, {"e": r.EVENT_ID})
    before = await _snapshot(factory)
    out = await _apply(factory, tmp_path, plan)
    assert out["state"] == r.REFUSED and out["reason"].startswith(reason_prefix), out
    assert out["counts"]["written_rows"] == 0 and out["counts"]["concurrent_drift"] == 1
    assert await _snapshot(factory) == before


async def test_cas_alone_refuses_when_the_compare_was_bypassed(factory, tmp_path, monkeypatch):
    """The UPDATE's own fence, not just the Python compare, stops a stale write."""
    plan = await _plan(factory, tmp_path)
    await _exec(factory, "UPDATE events SET away_score = 3 WHERE id = :e", {"e": r.EVENT_ID})
    monkeypatch.setattr(r, "diff_compared", lambda *a, **k: [])
    before = await _snapshot(factory)
    out = await _apply(factory, tmp_path, plan)
    assert out["state"] == r.REFUSED and out["reason"] == "fence_lost", out
    assert await _snapshot(factory) == before


@pytest.mark.parametrize("sql", [
    "UPDATE futures_markets SET source = 'polymarket' WHERE id = 63152777",
    "UPDATE futures_markets SET market_metadata = market_metadata || "
    "'{\"competition_scope\": \"Season\"}' WHERE id = 63152777",
    "UPDATE sports SET active = false WHERE id = 427850",
])
async def test_cas_market_and_sport_fence_refuses_when_identity_compare_was_bypassed(
    factory, tmp_path, monkeypatch, sql
):
    """The UPDATE's own EXISTS fences, not just the Python identity compare, stop the write."""
    plan = await _plan(factory, tmp_path)
    await _exec(factory, sql)
    monkeypatch.setattr(r, "_identity_drift", lambda *a, **k: None)
    before = await _snapshot(factory)
    out = await _apply(factory, tmp_path, plan)
    assert out["state"] == r.REFUSED and out["reason"] == "fence_lost", out
    assert await _snapshot(factory) == before


async def test_held_event_row_refuses_within_the_lock_budget(factory, tmp_path):
    plan = await _plan(factory, tmp_path)
    before = await _snapshot(factory)
    async with factory() as holder:
        await holder.execute(text("SELECT 1 FROM events WHERE id = :e FOR UPDATE"), {"e": r.EVENT_ID})
        t0 = asyncio.get_running_loop().time()
        out = await _apply(factory, tmp_path, plan, lock_timeout_ms=300)
        elapsed = asyncio.get_running_loop().time() - t0
        await holder.rollback()
    assert out["state"] == r.REFUSED and out["reason"] == "lock_timeout", out
    assert elapsed < 5 and out["counts"]["written_rows"] == 0
    assert await _snapshot(factory) == before


async def test_uncommitted_linked_market_is_fenced_by_the_event_lock(factory, tmp_path):
    """An FK insert linking a new market takes KEY SHARE on the event: FOR UPDATE waits, refuses."""
    plan = await _plan(factory, tmp_path)
    before = await _snapshot(factory)
    async with factory() as linker:
        await linker.execute(text(
            "INSERT INTO futures_markets (id, event_id, sport_id, source, external_id, name, "
            "category, mutually_exclusive, status) "
            "VALUES (63999999, :e, 7, 'kalshi', 'KXSERIEAGAME-X', 'men', 'game', true, 'open')"
        ), {"e": r.EVENT_ID})
        out = await _apply(factory, tmp_path, plan, lock_timeout_ms=300)
        await linker.rollback()
    assert out["state"] == r.REFUSED and out["reason"] == "lock_timeout", out
    assert await _snapshot(factory) == before


async def test_committed_extra_linked_market_refuses(factory, tmp_path):
    plan = await _plan(factory, tmp_path)
    await _exec(factory, "INSERT INTO futures_markets (id, event_id, sport_id, source, external_id, "
                "name, category, mutually_exclusive, status) "
                "VALUES (63999999, :e, 7, 'kalshi', 'X', 'm', 'game', true, 'open')",
                {"e": r.EVENT_ID})
    before = await _snapshot(factory)
    out = await _apply(factory, tmp_path, plan)
    assert out["state"] == r.REFUSED and out["reason"] == "identity_drift:linked_set", out
    assert await _snapshot(factory) == before


async def test_restore_puts_back_the_full_before_image(factory, tmp_path):
    before = await _snapshot(factory)
    plan = await _plan(factory, tmp_path)
    applied = await _apply(factory, tmp_path, plan)
    assert applied["state"] == r.APPLIED
    out = await r.run_restore(factory, backup_path=applied["backup"]["path"],
                              backup_hash=applied["backup"]["sha256"])
    assert out["state"] == r.APPLIED and out["counts"]["written_rows"] == 1, out
    assert await _snapshot(factory) == before
    again = await r.run_restore(factory, backup_path=applied["backup"]["path"],
                                backup_hash=applied["backup"]["sha256"])
    assert again["state"] == r.NOT_APPLIED and again["reason"] == "already_at_before_image"
    assert again["counts"]["written_rows"] == 0 and r.exit_code(again) == 0
    assert await _snapshot(factory) == before


@pytest.mark.parametrize(
    "sql, col",
    [
        ("UPDATE events SET llm_league = 'Serie_A_Women' WHERE id = :e", "llm_league"),
        ("UPDATE events SET home_score = 4 WHERE id = :e", "home_score"),
        ("UPDATE events SET event_tags = (SELECT jsonb_agg(x ORDER BY x) FROM "
         "jsonb_array_elements(event_tags) x) WHERE id = :e", "event_tags"),
    ],
)
async def test_restore_refuses_after_a_later_change_and_keeps_it(factory, tmp_path, sql, col):
    plan = await _plan(factory, tmp_path)
    applied = await _apply(factory, tmp_path, plan)
    assert applied["state"] == r.APPLIED
    await _exec(factory, sql, {"e": r.EVENT_ID})
    later = await _snapshot(factory)
    out = await r.run_restore(factory, backup_path=applied["backup"]["path"],
                              backup_hash=applied["backup"]["sha256"])
    assert out["state"] == r.REFUSED and out["reason"] == f"restore_after_drift:{col}", out
    assert out["counts"]["written_rows"] == 0
    assert await _snapshot(factory) == later


async def test_unrelated_column_change_does_not_block_restore_and_is_not_written(factory, tmp_path):
    """Restore compares only its 17 columns: a later score_source edit survives the undo."""
    plan = await _plan(factory, tmp_path)
    applied = await _apply(factory, tmp_path, plan)
    await _exec(factory, "UPDATE events SET score_source = 'statpal' WHERE id = :e", {"e": r.EVENT_ID})
    out = await r.run_restore(factory, backup_path=applied["backup"]["path"],
                              backup_hash=applied["backup"]["sha256"])
    assert out["state"] == r.APPLIED, out
    assert _event(await _snapshot(factory))["score_source"] == "statpal"


async def test_restore_refuses_tampered_backup_without_connecting(factory, tmp_path):
    plan = await _plan(factory, tmp_path)
    applied = await _apply(factory, tmp_path, plan)
    after = await _snapshot(factory)
    out = await r.run_restore(factory, backup_path=applied["backup"]["path"],
                              backup_hash="0" * 64)
    assert out["state"] == r.REFUSED and out["reason"] == "backup_hash_mismatch"
    assert await _snapshot(factory) == after


async def test_wrong_sport_team_binding_returns_p3_with_zero_writes(factory, tmp_path):
    await _exec(factory, "UPDATE events SET home_team_id = 903 WHERE id = :e", {"e": r.EVENT_ID})
    before = await _snapshot(factory)
    out = await r.run_preflight(factory, plan_out=str(tmp_path / "plan.json"), clock=lambda: FIXED)
    assert out["state"] == r.REFUSED and out["reason"] == r.TEAM_BINDING_SCOPE_REQUIRED
    assert out["detail"][0]["verdict"] == "WRONG_SPORT" and out["detail"][0]["team_id"] == 903
    assert not (tmp_path / "plan.json").exists()
    assert await _snapshot(factory) == before
