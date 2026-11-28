"""#1809 resumes the existing journal and never buys a written profile twice."""

import hashlib
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import DurableStateSnapshot
from scripts.cu_coverage import budget, frozen, store, worker


def test_paid_run_limits():
    assert budget.RUN_LIMIT_MICROS + budget.PRIOR_SPEND_MICROS == 50_000_000
    assert budget.daily_coverage_micros(10_000_000, use_elevated_cap=False) == 4_000_000
    assert budget.daily_coverage_micros(10_000_000, use_elevated_cap=True) == 4_000_000
    assert budget.daily_coverage_micros(40_000_000, use_elevated_cap=False) == 4_000_000
    assert budget.daily_coverage_micros(40_000_000, use_elevated_cap=True) == 25_000_000


def test_frozen_roster_checks_later_blocks(monkeypatch):
    ids = list(range(1001, 2001))
    digest = hashlib.sha256("".join(f"{mid}\n" for mid in ids).encode()).hexdigest()
    monkeypatch.setattr(frozen, "BLOCK_SHA256", (frozen.PILOT_SHA256, digest))
    assert frozen.approved_block(1000, 1834, ids)
    assert not frozen.approved_block(1000, 2001, ids)
    assert not frozen.approved_block(1000, 1834, ids[::-1])


@pytest.fixture
async def database():
    url = os.getenv("SEARCH_TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "set SEARCH_TEST_DATABASE_URL for the real PostgreSQL coverage recovery test"
        )
    schema = "cu_recovery_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as db:
        await db.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with engine.begin() as db:
            await db.run_sync(DurableStateSnapshot.__table__.create)
            ddl = (
                """CREATE TABLE futures_markets (
                    id integer PRIMARY KEY, name text, source text, status text, updated_at timestamptz,
                    story_key text, market_metadata jsonb, resolution_date timestamptz,
                    category text, llm_sport_category text, event_id integer
                )""",
                "CREATE TABLE sports (id integer, key text)",
                "CREATE TABLE teams (id integer, sport_id integer)",
                """CREATE TABLE events (
                    id integer, sport_id integer, home_team_id integer, away_team_id integer,
                    commence_time timestamptz, commence_time_source text
                )""",
                """CREATE TABLE futures_outcomes (
                    id integer PRIMARY KEY, market_id integer, name text, rank integer,
                    current_probability numeric, probability_change_24h numeric
                )""",
            )
            for statement in ddl:
                await db.execute(text(statement))
        yield engine, async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as db:
            await db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def test_recover_567_and_retry_settlement_without_buying_twice(
    database, monkeypatch
):
    engine, sessions = database
    failed_market = budget.LOCK_TIMEOUT_MARKET
    previous_ids = list(range(1, 568))
    day = datetime.now(timezone.utc).date().isoformat()
    async with sessions() as db, db.begin():
        await db.execute(
            text(
                """
                INSERT INTO futures_markets
                    (id, name, source, status, updated_at, story_key, market_metadata, category)
                VALUES (:id, 'Will it rain 10 inches?', 'kalshi', 'open',
                        '2024-01-01T08:00:00Z', 'keep', jsonb_build_object('sibling', 1), 'weather')
            """
            ),
            [{"id": mid} for mid in [*previous_ids, failed_market]],
        )
        await budget._stage(
            db,
            budget.BUDGET_ID,
            {
                "manifest_sha256": frozen.ROSTER_SHA256,
                "pilot_sha256": frozen.PILOT_SHA256,
                "model": worker.MODEL,
                "held_micros": 267_842,
                "spent_micros": 266_190,
                "days": {day: 267_842},
                "in_flight": 1,
                "uncertain": 0,
            },
            None,
        )
        await budget._stage(
            db,
            budget.attempt_identity(failed_market),
            {
                "market_id": failed_market,
                "utc_day": day,
                "model": worker.MODEL,
                "prompt_sha256": "a" * 64,
                "reserved_micros": 1_652,
                "status": "in_flight",
            },
            None,
        )
    for mid in previous_ids:
        async with sessions() as db:
            assert (
                await store.write_profile(
                    db,
                    mid,
                    expected_source="kalshi",
                    expected_title="Will it rain 10 inches?",
                    expected_profile_json=None,
                    profile={"schema_version": 2, "writer_rev": 10},
                )
                == "written"
            )

    calls = 0

    def complete(*args, **kwargs):
        nonlocal calls
        calls += 1
        content = json.dumps({"topic": "weather", "entities": []})
        return SimpleNamespace(
            model=worker.MODEL,
            cost_usd=0.0004,
            response=SimpleNamespace(
                id="test-completion",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=content)),
                ],
            ),
        )

    settle = budget.settle
    saw_timeout = False
    lost_ack = False

    async def settle_with_faults(db, **kwargs):
        nonlocal saw_timeout, lost_ack
        if not saw_timeout:
            async with engine.begin() as blocker:
                await blocker.execute(
                    budget._LOCK_BUDGET, {"identity": budget.BUDGET_ID}
                )
                try:
                    await settle(db, **kwargs)
                except DBAPIError as error:
                    assert error.orig.sqlstate == "55P03"
                    saw_timeout = True
                    raise
                raise AssertionError("expected PostgreSQL to time out on the spend row")
        totals = await settle(db, **kwargs)
        if not lost_ack:
            lost_ack = True
            raise budget.CoverageJournalWriteError(
                "the commit acknowledgement was lost"
            )
        return totals

    monkeypatch.setattr(worker, "complete_chat_detailed", complete)
    monkeypatch.setattr(worker, "daily_budget_micros", lambda: 10_000_000)
    monkeypatch.setattr(budget, "settle", settle_with_faults)
    payload = {
        "manifest_sha256": frozen.ROSTER_SHA256,
        "pilot_sha256": frozen.PILOT_SHA256,
        "model": worker.MODEL,
        "start": 0,
        "end": 568,
        "roster_ids": [*previous_ids[:564], failed_market, *previous_ids[564:]],
        "sample_seed": "fixture",
        "sample_cutoff": None,
        "excluded_sample_ids": [],
        "recover_failed_ids": [failed_market],
    }
    report = await worker.run_chunk(payload, engine, object())
    repeat = await worker.run_chunk(payload, engine, object())
    assert saw_timeout and lost_ack and calls == 1
    assert report["counts"] == {"already_written": 567, "written": 1}
    assert repeat["counts"] == {"already_written": 568}
    assert report["actual_usd"] == repeat["actual_usd"] == 0.268242
    assert report["retained_usd"] == repeat["retained_usd"] == 0.001652
    assert report["in_flight"] == report["uncertain"] == 0
    async with sessions() as db:
        assert (
            await db.scalar(
                text(
                    "SELECT count(*) FROM durable_state_snapshots WHERE schema_version = :kind"
                ),
                {"kind": store.UNDO_SCHEMA},
            )
            == 568
        )


async def test_unknown_cost_with_saved_answer_retains_reserve(database):
    _, sessions = database
    digest = "b" * 64
    day = datetime.now(timezone.utc).date().isoformat()
    reservation = budget.Reservation(5, day, worker.MODEL, digest, 1200)
    async with sessions() as db:
        await budget.initialize(db, manifest_sha256=digest, model=worker.MODEL)
        await budget.reserve(
            db,
            manifest_sha256=digest,
            reservation=reservation,
            shared_daily_micros=10_000_000,
        )
        result = await budget.settle(
            db,
            manifest_sha256=digest,
            reservation=reservation,
            actual_micros=None,
            content='{"topic":"weather"}',
        )
        assert (
            result["held_micros"]
            == result["spent_micros"]
            == result["retained_micros"]
            == 1200
        )
        assert result["in_flight"] == result["uncertain"] == 0
        assert (await budget.read_attempt(db, 5))["status"] == "charged"
