"""#10090: the Discover enrichment tasks never hold a transaction open across an LLM call.

WHAT PRODUCTION RECORDED
------------------------
Speed's read-only lock watch (``artifacts/10090-closure-board-20261028/
holder-watch/watch-20261029T0007Z.out``, polls 1145-1192, 00:54-00:56Z on
2026-10-29) caught pid 2702342 ``idle in transaction`` for 126 s -> 238 s, its
last statement ``UPDATE futures_markets SET story_key = $1 WHERE id = $2``.
Behind it waited ``SELECT events.win_probability_sources FROM events WHERE
events.id = $1 FOR UPDATE`` (a prediction-market JSONB writer), and behind that
an ``UPDATE futures_markets SET market_metadata=...`` whose own transaction aged
85 -> 106 s.

That statement is ``enrich_cu_v2_profiles``'s second UPDATE of a market. The
task wrote every market's profile inside ONE write transaction and committed
once at the end, with a blocking LLM call (up to 125 of them) between writes.

WHY AN UPDATE OF ``story_key`` LOCKS A GAME'S ``events`` ROW
-----------------------------------------------------------
Postgres skips the foreign-key check on an UPDATE that leaves the key unchanged,
EXCEPT when the old row version was written by the current transaction
(``RI_FKey_fk_upd_check_required``). The first UPDATE (``market_metadata``)
wrote that version, so the second UPDATE (``story_key``) runs the FK check on
``futures_markets.event_id`` and takes ``FOR KEY SHARE`` on the referenced
``events`` row until commit. ``FOR KEY SHARE`` conflicts with ``FOR UPDATE``.
``test_a_second_update_of_the_same_market_in_one_transaction_key_shares_its_event``
pins that on the real server, so the fix's single statement is shown to matter
and not merely asserted.

WHAT THIS FILE DRIVES
---------------------
The real ``enrich_cu_v2_profiles`` and ``enrich_discover_llm_metadata`` over real
rows: one live game, two open markets linked to it. The LLM is a stub. Its call
for the SECOND market is the moment production was in (the task between
markets, waiting on the model), and from there it probes the server on a
separate connection:

* ``FOR UPDATE NOWAIT`` on the game's ``events`` row (the prediction-market
  writers' lock),
* ``FOR UPDATE NOWAIT`` on the first market's ``futures_markets`` row,
* whether the first market's write is already visible to another session, and
* whether any session of the task is ``idle in transaction``.

On the parent, CU v2's probe is red: the game row is held by the FK check, the
first market's row is held, its write is invisible, and its sessions are idle in
a transaction. The Discover metadata task's reads stay open across the call.
With the fix every probe is free, and the CU v2 arm then checks both markets
were written in full, so a free row cannot come from a run that wrote less.

The CU v2 failure arm is the one behaviour that moves on purpose: on the
parent, a failed LLM call rolled back the whole batch, discarding every market
already written. The market is now the transaction unit, so the failure rolls
back only its own market.
"""

import contextlib
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10090 enrichment "
            "transaction gate (CI job `search-recall` provides one)"
        ),
    ),
]

APP_NAME = "enrich-10090-pg-gate"
SPORT_KEY = "americanfootball_nfl"
SPORT_ID = 1009081
EVENT_ID = 1009082
TEAM_IDS = (1009083, 1009084)
MARKET_IDS = (1009085, 1009086)
M1, M2 = MARKET_IDS
#: Far above anything another file seeds, so both enrichers pick these two first.
VOLUME = 9.0e15
STORY_KEY = "story:enrich_10090_gate"


@pytest.fixture
async def pg_engine():
    """Real schema with ``checkfirst``; only this file's id block is removed."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    tables = [
        Base.metadata.tables[name]
        for name in (
            "sports", "teams", "venues", "events", "futures_markets",
            "futures_outcomes", "entities", "entity_aliases", "team_identity_mapping",
        )
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        # Production has this column (migration ``c852a0story01``); the ORM model
        # does not map it, so ``create_all`` never makes it. CU v2 writes it with
        # Core SQL, and that write is the statement this file is about.
        await conn.execute(text(
            "ALTER TABLE futures_markets ADD COLUMN IF NOT EXISTS story_key VARCHAR(300)"
        ))
        await _clear(conn)
        await _seed(conn)
    yield engine
    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn):
    ids = list(MARKET_IDS)
    await conn.execute(text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"), {"ids": ids})
    await conn.execute(text("DELETE FROM futures_markets WHERE id = ANY(:ids)"), {"ids": ids})
    await conn.execute(text("DELETE FROM events WHERE id = :i"), {"i": EVENT_ID})
    await conn.execute(text("DELETE FROM teams WHERE id = ANY(:ids)"), {"ids": list(TEAM_IDS)})
    await conn.execute(text("DELETE FROM sports WHERE id = :i"), {"i": SPORT_ID})


async def _seed(conn):
    """One live NFL game and two open Polymarket markets linked to it.

    ``sports`` is reused by key when a sibling step already created it (the
    shared CI database keeps other files' rows).
    """
    sport_id = (
        await conn.execute(text("SELECT id FROM sports WHERE key = :k"), {"k": SPORT_KEY})
    ).scalar_one_or_none()
    if sport_id is None:
        await conn.execute(
            text("INSERT INTO sports (id, key, name, active) VALUES (:i, :k, :k, true)"),
            {"i": SPORT_ID, "k": SPORT_KEY},
        )
        sport_id = SPORT_ID
    home_id, away_id = TEAM_IDS
    for team_id, name in ((home_id, "Atlanta Falcons 10090e"), (away_id, "Baltimore Ravens 10090e")):
        await conn.execute(
            text("INSERT INTO teams (id, sport_id, name) VALUES (:i, :s, :n)"),
            {"i": team_id, "s": sport_id, "n": name},
        )
    await conn.execute(
        text(
            "INSERT INTO events (id, sport_id, external_id, home_team_id, away_team_id, "
            "home_team_name, away_team_name, commence_time, status) "
            "VALUES (:i, :s, :x, :ht, :at, :h, :a, :c, 'live')"
        ),
        {
            "i": EVENT_ID, "s": sport_id, "x": f"enrich-10090-pg-{EVENT_ID}",
            "ht": home_id, "at": away_id, "h": "Atlanta Falcons 10090e",
            "a": "Baltimore Ravens 10090e",
            "c": datetime.now(timezone.utc) - timedelta(minutes=30),
        },
    )
    for n, market_id in enumerate(MARKET_IDS):
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, sport_id, event_id, source, external_id, "
                "name, category, llm_sport_category, mutually_exclusive, status, "
                "volume_24h, market_metadata) "
                "VALUES (:i, :s, :e, 'polymarket', :x, :n, 'game', 'football', true, "
                "'open', :v, '{}'::jsonb)"
            ),
            {"i": market_id, "s": sport_id, "e": EVENT_ID, "x": f"pm-enrich-10090-{market_id}",
             "n": f"Falcons vs Ravens 10090e market {n}", "v": VOLUME - n},
        )
        await conn.execute(
            text(
                "INSERT INTO futures_outcomes (market_id, external_id, name, current_probability, rank) "
                "VALUES (:m, :x1, 'Falcons', 0.6, 1), (:m, :x2, 'Ravens', 0.4, 2)"
            ),
            {"m": market_id, "x1": f"{market_id}-falcons", "x2": f"{market_id}-ravens"},
        )


# ---------------------------------------------------------------------------
# The task's sessions: the real AsyncSession shape of ``get_task_session``
# (fresh engine, ``expire_on_commit=False``, commit on exit, dispose always),
# on the test database and tagged so the probe can find them.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _tagged_task_session():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"application_name": APP_NAME}}
    )
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()


def _probe():
    """What another session sees right now. Synchronous, like the LLM call it runs inside."""
    import psycopg2
    from psycopg2 import errors

    dsn = DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = psycopg2.connect(dsn)
    try:
        out = {}
        with conn.cursor() as cur:
            for name, sql, arg in (
                ("event_row", "SELECT win_probability_sources FROM events WHERE id = %s FOR UPDATE NOWAIT", EVENT_ID),
                ("first_market_row", "SELECT 1 FROM futures_markets WHERE id = %s FOR UPDATE NOWAIT", M1),
            ):
                try:
                    cur.execute(sql, (arg,))
                    out[name] = "free"
                except errors.LockNotAvailable:
                    out[name] = "held"
                conn.rollback()
            cur.execute("SELECT market_metadata FROM futures_markets WHERE id = %s", (M1,))
            out["first_market_metadata"] = cur.fetchone()[0] or {}
            cur.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE application_name = %s AND state LIKE 'idle in transaction%%'",
                (APP_NAME,),
            )
            out["idle_in_transaction"] = cur.fetchone()[0]
            conn.rollback()
        return out
    finally:
        conn.close()


def _cu_payload():
    return {
        "topic": "sports", "subtopic": "football",
        # A mention, so CU v2's grounding session really reads (and opens a
        # transaction) for the first market.
        "entities": [{"name": "Atlanta Falcons 10090e", "type": "team"}],
        "geography": "us", "story_key": STORY_KEY, "series_key": None,
        "temporal": "event_tied", "event_date": None, "recurrence": "one_off",
        "stakes": 2, "breadth": 3, "oddity": 1, "arc": None, "hook_facts": [],
        "junk_flags": [], "confidence": 0.9, "frame": None,
    }


def _discover_payload():
    return {
        "topic": "sports", "subtopic": "football", "entities": ["Falcons"],
        "archetype": "game", "audience_scope": "mainstream", "salience_score": 4,
        "junk_flags": [], "comparison_axes": ["sports"], "why_interesting": "live game",
    }


class _LLMStub:
    """``complete_chat_detailed`` stand-in. Probes the server during the 2nd call."""

    def __init__(self, payload, *, fail_on_call=None):
        self.payload = payload
        self.fail_on_call = fail_on_call
        self.calls = 0
        self.probe = None

    def __call__(self, _kind, _client, **_kwargs):
        self.calls += 1
        if self.calls == 2:
            self.probe = _probe()
        if self.calls == self.fail_on_call:
            raise RuntimeError("model timed out")
        return SimpleNamespace(
            response=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload)))],
                usage=SimpleNamespace(prompt_tokens=900, completion_tokens=260),
            ),
            model="gpt-4o-mini",
            cost_usd=0.0004,
        )


def _install(monkeypatch, stub):
    monkeypatch.setattr("app.tasks.enrich_markets.get_task_session", _tagged_task_session)
    monkeypatch.setattr("app.tasks.enrich_markets.complete_chat_detailed", stub)
    monkeypatch.setattr("app.services.llm._get_client", lambda: object())


async def _rows(engine):
    async with engine.connect() as conn:
        rows = (await conn.execute(
            text("SELECT id, story_key, market_metadata FROM futures_markets WHERE id = ANY(:ids) ORDER BY id"),
            {"ids": list(MARKET_IDS)},
        )).mappings().all()
    return {r["id"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# The mechanism, on the real server
# ---------------------------------------------------------------------------


async def test_a_second_update_of_the_same_market_in_one_transaction_key_shares_its_event(pg_engine):
    """Two UPDATEs of one market in one transaction lock its game row; one UPDATE does not."""
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(
            text("UPDATE futures_markets SET market_metadata = '{\"a\": 1}'::jsonb WHERE id = :i"),
            {"i": M1},
        )
        after_first = _probe()["event_row"]
        await conn.execute(text("UPDATE futures_markets SET story_key = :k WHERE id = :i"), {"k": STORY_KEY, "i": M1})
        after_second = _probe()["event_row"]
        await trans.rollback()

        trans = await conn.begin()
        await conn.execute(
            text(
                "UPDATE futures_markets SET market_metadata = '{\"a\": 1}'::jsonb, story_key = :k "
                "WHERE id = :i"
            ),
            {"k": STORY_KEY, "i": M1},
        )
        after_merged = _probe()["event_row"]
        await trans.rollback()

    assert (after_first, after_second, after_merged) == ("free", "held", "free")


# ---------------------------------------------------------------------------
# enrich_cu_v2_profiles
# ---------------------------------------------------------------------------


async def test_cu_v2_holds_nothing_while_it_waits_on_the_next_markets_llm_call(pg_engine, monkeypatch):
    from app.tasks.enrich_markets import DISCOVER_LLM_METADATA_KEY, enrich_cu_v2_profiles

    stub = _LLMStub(_cu_payload())
    _install(monkeypatch, stub)

    stats = await enrich_cu_v2_profiles(limit=2)

    probe = stub.probe
    assert probe is not None, "the stub never reached the second market"
    assert probe["event_row"] == "free", f"the game's events row was locked across the next LLM call: {probe}"
    assert probe["first_market_row"] == "free", f"the first market's row was locked across the next LLM call: {probe}"
    assert probe["idle_in_transaction"] == 0, f"a task session sat idle in a transaction across the LLM call: {probe}"
    assert probe["first_market_metadata"].get(DISCOVER_LLM_METADATA_KEY, {}).get("story_key") == STORY_KEY, (
        f"the first market's profile was not committed before the next LLM call: {probe}"
    )

    assert (stats["processed"], stats["generated"], stats["errors"]) == (2, 2, 0)
    rows = await _rows(pg_engine)
    for market_id in MARKET_IDS:
        assert rows[market_id]["story_key"] == STORY_KEY
        profile = rows[market_id]["market_metadata"][DISCOVER_LLM_METADATA_KEY]
        assert profile["story_key"] == STORY_KEY and profile["schema_version"] == 2


async def test_cu_v2_a_failed_llm_call_rolls_back_only_its_own_market(pg_engine, monkeypatch):
    from app.tasks.enrich_markets import DISCOVER_LLM_METADATA_KEY, enrich_cu_v2_profiles

    stub = _LLMStub(_cu_payload(), fail_on_call=2)
    _install(monkeypatch, stub)

    stats = await enrich_cu_v2_profiles(limit=2)

    assert (stats["processed"], stats["generated"], stats["errors"]) == (2, 1, 1)
    rows = await _rows(pg_engine)
    assert rows[M1]["story_key"] == STORY_KEY
    assert DISCOVER_LLM_METADATA_KEY in rows[M1]["market_metadata"]
    assert rows[M2]["story_key"] is None
    assert rows[M2]["market_metadata"] == {}


# ---------------------------------------------------------------------------
# enrich_discover_llm_metadata
#
# Its write cannot land today: it passes ``story_key=`` to an ORM UPDATE of
# FuturesMarket, which does not map that column, so SQLAlchemy refuses every
# market ("Unconsumed column names: story_key") after the paid call. That is a
# separate defect with its own owner, and this file does not pin it either way.
# What it pins is the transaction shape, which is wrong on the parent whether
# or not the write lands: the reads before each call stay open across it.
# ---------------------------------------------------------------------------


async def test_discover_metadata_holds_nothing_while_it_waits_on_the_next_markets_llm_call(pg_engine, monkeypatch):
    from app.tasks.enrich_markets import enrich_discover_llm_metadata

    stub = _LLMStub(_discover_payload())
    _install(monkeypatch, stub)

    stats = await enrich_discover_llm_metadata(limit=2)

    probe = stub.probe
    assert probe is not None, "the stub never reached the second market"
    assert probe["idle_in_transaction"] == 0, (
        f"the task session sat idle in a transaction across the LLM call: {probe}"
    )
    assert probe["event_row"] == "free", probe
    assert probe["first_market_row"] == "free", probe
    assert (stub.calls, stats["processed"]) == (2, 2)
