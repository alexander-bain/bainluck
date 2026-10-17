"""#683 archive store against a REAL PostgreSQL: schema, import, restore, readers, forecast.

PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
real recoverable pre-resolution probability journey on web (``/history``) and
native (``/probability-timeline``), with archive provenance and honest
forecast eligibility.

Why a real server. Every claim here belongs to PostgreSQL, not to our code:
the CHECK and UNIQUE constraints that make the store refuse a post-settlement
interval or a doubled one; ``ON CONFLICT ON CONSTRAINT`` naming a key that
exists; the migration building the SAME schema as the models; restore deleting
exactly one import's rows; the routes' SAVEPOINT-guarded read; and the forecast
lateral's revalidation joins. A double cannot hold any of them.

The specimen is synthetic and shaped like ``KXNCAAMBSPREAD-26APR05OKLAWVU``: an
11-hour spread market, hourly archive candles, a tip-off six hours in. Outcome
A has NO live snapshot (the #683 cohort). Outcome B has two: one inside the
first archive interval and one inside the fifth, so the reader must withhold
exactly those two intervals and keep the gap between them and everything after.

Gated like every ``_pg`` file: set ``SEARCH_TEST_DATABASE_URL`` (CI's
``search-recall`` job provides one). A skip is NOT a pass.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #683 archive-store "
            "gate (CI job `search-recall` provides one)"
        ),
    ),
]

UTC = timezone.utc
LABEL = "SYNTHETIC-683"
EVT = "KXNCAAMBSPREAD-26APR05SYNTH"
TA = f"{EVT}-SYNA9"
TB = f"{EVT}-SYNB3"
OPEN = (datetime.now(UTC) - timedelta(days=120)).replace(minute=0, second=0, microsecond=0)
TIPOFF = OPEN + timedelta(hours=6)
SETTLED = OPEN + timedelta(hours=11, minutes=3)
ARCHIVE_CUTOFF = datetime.now(UTC) - timedelta(days=60)
HOURS = 24 * 200


def _candle(end, close):
    return {
        "end_period_ts": int(end.timestamp()),
        "open_interest": "10.00",
        "price": {"close": close, "mean": None, "previous": None},
        "volume": "7.00",
        "yes_ask": {"close": None},
        "yes_bid": {"close": None},
    }


def _candles(base):
    """Hourly closes ending OPEN+1h … OPEN+12h; the last crosses settlement."""
    return [
        _candle(OPEN + timedelta(hours=h), f"{base + h / 100:.4f}") for h in range(1, 13)
    ]


async def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _factory(engine):
    from sqlalchemy.ext.asyncio import AsyncSession

    return lambda: AsyncSession(engine, expire_on_commit=False)


async def _seed(engine) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import (
        Event,
        FuturesMarket,
        FuturesOddsSnapshot,
        FuturesOutcome,
        Sport,
    )

    async with AsyncSession(engine, expire_on_commit=False) as s:
        async with s.begin():
            sport = Sport(key="basketball_ncaab", name="NCAAB")
            s.add(sport)
            await s.flush()
            event = Event(
                sport_id=sport.id,
                home_team_name=f"{LABEL} Home",
                away_team_name=f"{LABEL} Away",
                commence_time=TIPOFF,
                commence_time_source="espn",
                status="completed",
                completed_at=SETTLED,
            )
            s.add(event)
            await s.flush()
            market = FuturesMarket(
                source="kalshi",
                external_id=EVT,
                name=f"{LABEL} spread",
                category="game",
                market_tier=5,
                mutually_exclusive=False,
                status="resolved",
                resolution_date=SETTLED,
                event_id=event.id,
            )
            other = FuturesMarket(
                source="polymarket",
                external_id=f"{LABEL}-poly",
                name=f"{LABEL} poly control",
                category="championship",
                market_tier=5,
                mutually_exclusive=True,
                status="resolved",
                resolution_date=SETTLED,
            )
            s.add_all([market, other])
            await s.flush()
            a = FuturesOutcome(
                market_id=market.id, external_id=TA, name="A 9+", rank=1,
                current_probability=0.0, is_winner=False,
                resolution_source="api_settlement",
            )
            b = FuturesOutcome(
                market_id=market.id, external_id=TB, name="B 3+", rank=2,
                current_probability=1.0, is_winner=True,
                resolution_source="api_settlement",
            )
            p = FuturesOutcome(
                market_id=other.id, external_id=f"{LABEL}-poly-1", name="P", rank=1,
                current_probability=0.5,
            )
            s.add_all([a, b, p])
            await s.flush()
            for minutes, prob in ((30, 0.505), (4 * 60 + 20, 0.555)):
                s.add(
                    FuturesOddsSnapshot(
                        outcome_id=b.id, bookmaker="kalshi", probability=prob,
                        yes_bid=prob - 0.01, yes_ask=prob + 0.01, last_price=prob,
                        captured_at=OPEN + timedelta(minutes=minutes),
                    )
                )
            s.add(
                FuturesOddsSnapshot(
                    outcome_id=p.id, bookmaker="polymarket", probability=0.5,
                    captured_at=OPEN + timedelta(hours=2),
                )
            )
        return {
            "market": market.id, "other": other.id, "event": event.id,
            "a": a.id, "b": b.id,
        }


async def _plan(engine, ids, candles=None):
    from app.services import kalshi_archive_recovery as rec
    from tests.test_kalshi_archive_recovery_683 import FakeService

    listed = [
        {"ticker": t, "event_ticker": EVT, "status": "finalized",
         "open_time": OPEN.isoformat(), "settlement_ts": SETTLED.isoformat()}
        for t in (TA, TB)
    ]
    svc = FakeService(
        {EVT: [(listed, None)]},
        candles or {TA: _candles(0.30), TB: _candles(0.50)},
        cutoff=ARCHIVE_CUTOFF.isoformat(),
    )

    async def _sleep(_s):
        return None

    report = await rec.plan_archive_recovery(
        outcome_ids=ids,
        session_factory=_factory(engine),
        service_factory=lambda: svc,
        cooldown_reader=lambda: 0.0,
        max_wait_seconds=1.0,
        sleep=_sleep,
        pace_seconds=0.5,
    )
    import json

    return json.loads(json.dumps(report, default=str))


async def _count(engine, table):
    async with engine.connect() as c:
        return (await c.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()


@pytest.fixture
async def world():
    engine = await _engine()
    ids = await _seed(engine)
    yield engine, ids
    await engine.dispose()


# ── the migration builds the models' schema ───────────────────────────────


async def test_the_migration_builds_exactly_the_models_schema():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect as sa_inspect

    engine = await _engine()
    tables = (
        "kalshi_archive_intervals",
        "kalshi_archive_outcome_evidence",
        "kalshi_archive_imports",
    )

    def shape(sync_conn):
        insp = sa_inspect(sync_conn)
        out = {}
        for t in tables:
            out[t] = {
                "columns": sorted(
                    (c["name"], str(c["type"]), c["nullable"]) for c in insp.get_columns(t)
                ),
                "unique": sorted(u["name"] for u in insp.get_unique_constraints(t)),
                "checks": sorted(
                    (c["name"], re.sub(r"\s+", " ", c["sqltext"]))
                    for c in insp.get_check_constraints(t)
                ),
                "indexes": sorted(
                    (i["name"], tuple(i["column_names"]), bool(i["unique"]))
                    for i in insp.get_indexes(t)
                ),
                "fks": sorted(
                    (tuple(f["constrained_columns"]), f["referred_table"])
                    for f in insp.get_foreign_keys(t)
                ),
            }
        return out

    async with engine.begin() as conn:
        from_models = await conn.run_sync(shape)
        for t in tables:
            await conn.execute(text(f"DROP TABLE {t}"))
        path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "kalshi_archive_store_683.py"
        spec = importlib.util.spec_from_file_location("kalshi_archive_store_683", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def upgrade(sync_conn):
            with Operations.context(MigrationContext.configure(sync_conn)):
                mod.upgrade()

        await conn.run_sync(upgrade)
        from_migration = await conn.run_sync(shape)

        def downgrade(sync_conn):
            with Operations.context(MigrationContext.configure(sync_conn)):
                mod.downgrade()

        await conn.run_sync(downgrade)
        gone = (
            await conn.execute(
                text("SELECT to_regclass('public.kalshi_archive_intervals') IS NULL")
            )
        ).scalar_one()
    await engine.dispose()
    assert mod.revision == "kalshi_archive_store_683" and len(mod.revision) <= 32
    assert from_migration == from_models
    assert gone is True


# ── the database refuses what the store must never hold ───────────────────


async def test_the_constraints_refuse_impossible_rows(world):
    from sqlalchemy.exc import DBAPIError

    engine, ids = world
    async with engine.begin() as c:
        imp_id = (
            await c.execute(
                text(
                    "INSERT INTO kalshi_archive_imports (import_key, plan_digest, "
                    "archive_cutoff, status) VALUES ('k', repeat('a', 64), :cut, "
                    "'applying') RETURNING id"
                ),
                {"cut": ARCHIVE_CUTOFF},
            )
        ).scalar_one()
        ev_id = (
            await c.execute(
                text(
                    "INSERT INTO kalshi_archive_outcome_evidence (import_id, outcome_id, "
                    "market_ticker, event_ticker, period_minutes, venue_settlement_ts, "
                    "archive_cutoff, coverage, input_fingerprint, cutoff_inputs, "
                    "cutoff_refusal, windows) VALUES (:i, :o, :t, :e, 60, :s, :cut, "
                    "'complete', repeat('f', 64), '{}'::jsonb, 'no_event', '[]'::jsonb) "
                    "RETURNING id"
                ),
                {"i": imp_id, "o": ids["a"], "t": TA, "e": EVT, "s": SETTLED,
                 "cut": ARCHIVE_CUTOFF},
            )
        ).scalar_one()

    base = {
        "i": imp_id, "ev": ev_id, "o": ids["a"], "t": TA, "e": EVT,
        "start": OPEN, "end": OPEN + timedelta(hours=1), "s": SETTLED, "p": 0.4,
        "basis": "traded_interval", "echo": TA,
    }
    insert = text(
        "INSERT INTO kalshi_archive_intervals (import_id, evidence_id, outcome_id, "
        "market_ticker, event_ticker, period_minutes, interval_start, interval_end, "
        "venue_settlement_ts, probability, price_basis, echoed_ticker, "
        "raw_response_sha256, retrieved_at, admission_at_plan, admission_at_apply) "
        "VALUES (:i, :ev, :o, :t, :e, 60, :start, :end, :s, :p, :basis, :echo, "
        "repeat('b', 64), now(), 'forecast', 'forecast')"
    )
    async with engine.begin() as c:
        await c.execute(insert, base)

    bad = {
        "ck_kaiv_before_settlement": {"start": SETTLED - timedelta(hours=1), "end": SETTLED},
        "ck_kaiv_probability": {"start": OPEN + timedelta(hours=1),
                                "end": OPEN + timedelta(hours=2), "p": 1.0},
        "ck_kaiv_span": {"start": OPEN, "end": OPEN + timedelta(hours=3)},
        "ck_kaiv_echo": {"start": OPEN + timedelta(hours=2),
                         "end": OPEN + timedelta(hours=3), "echo": TB},
        "ck_kaiv_basis": {"start": OPEN + timedelta(hours=3),
                          "end": OPEN + timedelta(hours=4), "basis": "previous_only"},
        "uq_kai_interval": {},
    }
    for name, patch in bad.items():
        with pytest.raises(DBAPIError) as info:
            async with engine.begin() as c:
                await c.execute(insert, {**base, **patch})
        assert name in str(info.value), name

    with pytest.raises(DBAPIError) as info:
        async with engine.begin() as c:
            await c.execute(
                text(
                    "UPDATE kalshi_archive_outcome_evidence SET forecast_cutoff_ts = :t "
                    "WHERE id = :id"
                ),
                {"t": TIPOFF, "id": ev_id},
            )
    assert "ck_kaoe_cutoff_xor_refusal" in str(info.value)


# ── the attended import ───────────────────────────────────────────────────


async def test_dry_run_writes_nothing_and_apply_writes_reads_back_and_is_idempotent(world):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    report = await _plan(engine, [ids["a"], ids["b"]])
    assert report["archive_store"] == "present"
    digest = report["plan_digest"]

    dry = await imp.apply_archive_plan(
        report, expected_digest=digest, session_factory=_factory(engine)
    )
    assert dry["mode"] == "dry_run" and dry["inserted"] == 0
    assert sum(o["would_insert"] for o in dry["outcomes"]) == 22
    for t in ("kalshi_archive_imports", "kalshi_archive_intervals",
              "kalshi_archive_outcome_evidence"):
        assert await _count(engine, t) == 0, t

    done = await imp.apply_archive_plan(
        report, expected_digest=digest, write=True, session_factory=_factory(engine)
    )
    assert done["status"] == "applied" and done["inserted"] == 22
    assert all(o["readback"] == "ok" for o in done["outcomes"])
    # A is in the original zero-snapshot cohort; B had live snapshots.
    assert done["zero_snapshot_cohort_gained_ids"] == [ids["a"]]
    assert done["gained_history_outcome_ids"] == sorted([ids["a"], ids["b"]])
    async with engine.connect() as c:
        row = (
            await c.execute(
                text("SELECT status, inserted_ids, finished_at FROM kalshi_archive_imports")
            )
        ).one()
        assert row.status == "applied" and len(row.inserted_ids) == 22
        adm = dict(
            (
                await c.execute(
                    text(
                        "SELECT admission_at_apply, COUNT(*) FROM kalshi_archive_intervals "
                        "WHERE outcome_id = :a GROUP BY 1"
                    ),
                    {"a": ids["a"]},
                )
            ).all()
        )
        # Ends at +1..+6h are wholly before tip-off; +7..+11h are in play.
        assert adm == {"forecast": 6, "reader_only": 5}
        assert (
            await c.execute(
                text(
                    "SELECT COUNT(*) FROM futures_odds_snapshots WHERE outcome_id = :a"
                ),
                {"a": ids["a"]},
            )
        ).scalar_one() == 0  # the snapshot table is untouched

    again = await imp.apply_archive_plan(
        report, expected_digest=digest, write=True, session_factory=_factory(engine)
    )
    assert again["inserted"] == 0 and again["identical"] == 22
    assert await _count(engine, "kalshi_archive_intervals") == 22


async def test_conflicting_evidence_is_reported_never_overwritten(world):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    first = await _plan(engine, [ids["a"]])
    await imp.apply_archive_plan(
        first, expected_digest=first["plan_digest"], write=True,
        session_factory=_factory(engine),
    )
    second = await _plan(engine, [ids["a"]], candles={TA: _candles(0.20)})
    # The planner marks every interval already stored, so nothing is importable.
    assert second["importable_points"] == 0
    # Force the question at the store: rebuild the second plan with no store read.
    async with engine.begin() as c:
        await c.execute(text("UPDATE kalshi_archive_intervals SET probability = 0.11"))
    result = await imp.apply_archive_plan(
        first, expected_digest=first["plan_digest"], write=True,
        session_factory=_factory(engine),
    )
    assert result["inserted"] == 0 and len(result["conflicts"]) == 11
    assert result["status"] == "partial"
    async with engine.connect() as c:
        kept = (
            await c.execute(text("SELECT DISTINCT probability FROM kalshi_archive_intervals"))
        ).scalars().all()
    assert [float(v) for v in kept] == [0.11]


async def test_input_drift_refuses_the_outcome(world):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    report = await _plan(engine, [ids["a"]])
    async with engine.begin() as c:
        await c.execute(
            text("UPDATE events SET commence_time = commence_time - interval '2 hours'")
        )
    result = await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        session_factory=_factory(engine),
    )
    assert result["refused"] == [{"outcome_id": ids["a"], "reason": "input_drift"}]
    assert await _count(engine, "kalshi_archive_intervals") == 0


async def test_restore_removes_exactly_one_imports_rows(world):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    ra = await _plan(engine, [ids["a"]])
    rb = await _plan(engine, [ids["b"]])
    ia = await imp.apply_archive_plan(
        ra, expected_digest=ra["plan_digest"], write=True, session_factory=_factory(engine)
    )
    ib = await imp.apply_archive_plan(
        rb, expected_digest=rb["plan_digest"], write=True, session_factory=_factory(engine)
    )
    dry = await imp.restore_archive_import(ia["import_key"], session_factory=_factory(engine))
    assert dry["would_delete"] == 11 and dry["deleted"] == 0
    assert await _count(engine, "kalshi_archive_intervals") == 22

    done = await imp.restore_archive_import(
        ia["import_key"], write=True, session_factory=_factory(engine)
    )
    assert done["deleted"] == 11 and done["readback_remaining"] == 0
    assert done["evidence_deleted"] == 1
    async with engine.connect() as c:
        left = (
            await c.execute(text("SELECT DISTINCT outcome_id FROM kalshi_archive_intervals"))
        ).scalars().all()
        status = dict(
            (await c.execute(text("SELECT import_key, status FROM kalshi_archive_imports"))).all()
        )
    assert left == [ids["b"]]
    assert status == {ia["import_key"]: "restored", ib["import_key"]: "applied"}
    twice = await imp.restore_archive_import(
        ia["import_key"], write=True, session_factory=_factory(engine)
    )
    assert twice["refused"] == "already_restored"


async def test_restore_refuses_when_rows_and_record_disagree(world):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    r = await _plan(engine, [ids["a"]])
    done = await imp.apply_archive_plan(
        r, expected_digest=r["plan_digest"], write=True, session_factory=_factory(engine)
    )
    async with engine.begin() as c:
        await c.execute(
            text(
                "UPDATE kalshi_archive_imports SET inserted_ids = inserted_ids[2:] "
                "WHERE import_key = :k"
            ),
            {"k": done["import_key"]},
        )
    refused = await imp.restore_archive_import(
        done["import_key"], write=True, session_factory=_factory(engine)
    )
    assert refused["refused"] == "rows_not_recorded_by_import"
    assert await _count(engine, "kalshi_archive_intervals") == 11


# ── restore refuses rows changed after the import (Root, WIP38c6 review) ──


async def _applied(engine, ids, which="a"):
    from app.services import kalshi_archive_apply as imp

    r = await _plan(engine, [ids[which]])
    return await imp.apply_archive_plan(
        r, expected_digest=r["plan_digest"], write=True, session_factory=_factory(engine)
    )


@pytest.mark.parametrize(
    "change,reason",
    [
        # Root's counterexample shape: a legitimate stored value changed later.
        ("SET probability = 0.7", "row_content_changed_since_import"),
        ("SET raw_response_sha256 = repeat('c', 64)", "row_content_changed_since_import"),
        ("SET admission_at_apply = 'reader_only'", "row_content_changed_since_import"),
        # Same content, new row version: still not the row this import wrote.
        ("SET probability = probability", "row_version_changed_since_import"),
    ],
)
async def test_restore_refuses_an_interval_changed_after_the_import(world, change, reason):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    done = await _applied(engine, ids)
    target = done["outcomes"][0]["inserted_ids"][0]
    async with engine.begin() as c:
        await c.execute(text(f"UPDATE kalshi_archive_intervals {change} WHERE id = :id"),
                        {"id": target})
    for write in (False, True):
        refused = await imp.restore_archive_import(
            done["import_key"], write=write, session_factory=_factory(engine)
        )
        assert refused["refused"] == reason and refused["ids"] == [target], write
    assert await _count(engine, "kalshi_archive_intervals") == 11
    async with engine.connect() as c:
        status = (await c.execute(text("SELECT status FROM kalshi_archive_imports"))).scalar()
    assert status == "applied"


async def test_restore_refuses_changed_evidence(world):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    done = await _applied(engine, ids)
    async with engine.begin() as c:
        await c.execute(text("UPDATE kalshi_archive_outcome_evidence SET coverage = coverage"))
    refused = await imp.restore_archive_import(
        done["import_key"], write=True, session_factory=_factory(engine)
    )
    assert refused["refused"] == "evidence_changed_since_import"
    assert await _count(engine, "kalshi_archive_intervals") == 11


async def test_an_update_committed_while_restore_waits_is_refused(world):
    """Interleaved: a writer holds the row, restore queues on it, the writer commits."""
    import asyncio

    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    done = await _applied(engine, ids)
    target = done["outcomes"][0]["inserted_ids"][3]
    async with engine.connect() as writer:
        await writer.begin()
        await writer.execute(
            text("UPDATE kalshi_archive_intervals SET probability = 0.5 WHERE id = :id"),
            {"id": target},
        )
        task = asyncio.create_task(
            imp.restore_archive_import(
                done["import_key"], write=True, session_factory=_factory(engine)
            )
        )
        for _ in range(100):  # until the restore is really queued on the row lock
            async with engine.connect() as probe:
                waiting = (await probe.execute(text(
                    "SELECT COUNT(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                    " AND datname = current_database()"
                ))).scalar_one()
            if waiting:
                break
            await asyncio.sleep(0.05)
        assert waiting and not task.done()
        await writer.commit()
    result = await asyncio.wait_for(task, 10)
    assert result["refused"] == "row_content_changed_since_import"
    assert result["ids"] == [target]
    async with engine.connect() as c:
        kept = (await c.execute(text(
            "SELECT probability FROM kalshi_archive_intervals WHERE id = :id"
        ), {"id": target})).scalar_one()
    assert float(kept) == 0.5 and await _count(engine, "kalshi_archive_intervals") == 11


async def test_restore_holds_its_rows_locked_from_check_to_delete(world):
    """A writer arriving after the check cannot slip a change in before the delete."""
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    done = await _applied(engine, ids)
    target = done["outcomes"][0]["inserted_ids"][0]
    seen: dict = {}

    class Probing(AsyncSession):
        async def execute(self, statement, *a, **k):
            out = await super().execute(statement, *a, **k)
            if "FOR UPDATE" in str(statement) and "kalshi_archive_intervals" in str(statement):
                async with engine.connect() as other:
                    await other.execute(text("SET lock_timeout = '300ms'"))
                    try:
                        await other.execute(
                            text("UPDATE kalshi_archive_intervals SET probability = 0.5"
                                 " WHERE id = :id"), {"id": target})
                        seen["blocked"] = False
                    except DBAPIError as e:
                        seen["blocked"] = "lock timeout" in str(e).lower() or "55P03" in str(e)
            return out

    result = await imp.restore_archive_import(
        done["import_key"], write=True,
        session_factory=lambda: Probing(engine, expire_on_commit=False),
    )
    assert seen == {"blocked": True}
    assert result["refused"] is None and result["deleted"] == 11
    assert await _count(engine, "kalshi_archive_intervals") == 0


async def test_the_import_records_a_version_and_seal_for_every_row(world):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    done = await _applied(engine, ids)
    async with engine.connect() as c:
        rec = (await c.execute(text(
            "SELECT inserted_ids, inserted_seals, evidence_versions FROM kalshi_archive_imports"
        ))).one()
        rows = (await c.execute(text(
            f"SELECT {imp._SEAL_SELECT} FROM kalshi_archive_intervals"
        ))).fetchall()
    assert set(map(int, rec.inserted_seals)) == set(rec.inserted_ids) == {r.id for r in rows}
    for r in rows:
        assert rec.inserted_seals[str(r.id)] == [r.version, imp.row_seal(r)]
    assert len(rec.evidence_versions) == 1 and done["status"] == "applied"


# ── the two chart routes ──────────────────────────────────────────────────


@pytest.fixture
async def client(world, monkeypatch):
    async for served in _serve(world, monkeypatch):
        yield served


async def _serve(world, monkeypatch):
    """Import the specimen through the real planner + apply, then serve the app."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services import kalshi_archive_apply as imp
    from app.services.database import get_db, get_db_rw
    from app.utils import kalshi_archive_reader as reader

    engine, ids = world
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    monkeypatch.setitem(reader._presence, "value", None)
    report = await _plan(engine, [ids["a"], ids["b"]])
    await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        session_factory=_factory(engine),
    )

    async def _get_db():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    async def _anon():
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_db_rw] = _get_db
    app.dependency_overrides[get_optional_user] = _anon
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, ids
    app.dependency_overrides.clear()


def _archive_points(history_outcome):
    return [p for p in history_outcome["history"] if p.get("provenance") == "kalshi_archive"]


async def test_history_draws_the_zero_snapshot_outcome_from_the_archive(client):
    c, ids = client
    r = await c.get(
        f"/api/futures/{ids['market']}/history", params={"hours": HOURS, "top_n": 50}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    by_id = {o["outcome_id"]: o for o in body["outcomes"]}
    a = _archive_points(by_id[ids["a"]])
    assert [p["timestamp"] for p in a] == [
        (OPEN + timedelta(hours=h)).isoformat() for h in range(1, 12)
    ]
    assert all(p["period_minutes"] == 60 and p["bookmaker"] == "kalshi_archive" for p in a)
    assert a[0]["interval_start"] == OPEN.isoformat()
    # Nothing at or after settlement, ever.
    assert all(datetime.fromisoformat(p["timestamp"]) < SETTLED for p in a)
    block = body["archive_history"]
    assert block["state"] == "warm" and block["provenance"] == "kalshi_archive"
    assert block["withheld_overlapping_live"] == 2


async def test_history_live_wins_actual_overlap_only(client):
    c, ids = client
    body = (
        await c.get(
            f"/api/futures/{ids['market']}/history", params={"hours": HOURS, "top_n": 50}
        )
    ).json()
    b = {o["outcome_id"]: o for o in body["outcomes"]}[ids["b"]]
    archive_ends = [p["timestamp"] for p in _archive_points(b)]
    # Live at +0:30 claims the +1h interval; live at +4:20 claims +5h. The gap
    # between them (+2h..+4h) and everything after (+6h..+11h) stands.
    assert archive_ends == [
        (OPEN + timedelta(hours=h)).isoformat() for h in (2, 3, 4, 6, 7, 8, 9, 10, 11)
    ]
    live = [p for p in b["history"] if p.get("provenance") is None]
    assert any(
        datetime.fromisoformat(p["timestamp"]) == OPEN + timedelta(minutes=30) for p in live
    )


async def test_the_native_timeline_draws_the_archive_and_marks_it(client):
    c, ids = client
    r = await c.get(
        f"/api/futures/{ids['market']}/probability-timeline",
        params={"hours": 4320, "top": 50},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    marked = [e for e in body["timeline"] if "archive" in e]
    a_name = "A 9+"
    a_marks = [e for e in marked if a_name in e["archive"]]
    assert len(a_marks) == 11
    assert all(e["archive"][a_name]["provenance"] == "kalshi_archive" for e in a_marks)
    assert body["archive_history"]["points_served"] >= 11
    # A value with no mark is never an archive value in disguise.
    for e in body["timeline"]:
        for name in e.get("archive", {}):
            assert name in e["outcomes"]


async def test_the_combined_chart_draws_an_archive_only_kalshi_arm(client, world):
    """The web evolution view's >1-market path (`/multi-history`), Kalshi arm archive-only."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome

    c, ids = client
    engine, _ = world
    async with AsyncSession(engine, expire_on_commit=False) as s:
        async with s.begin():
            poly = FuturesMarket(
                source="polymarket", external_id=f"{LABEL}-poly-same", name=f"{LABEL} same",
                category="game", market_tier=5, mutually_exclusive=False,
                status="resolved", resolution_date=SETTLED,
            )
            s.add(poly)
            await s.flush()
            twin = FuturesOutcome(market_id=poly.id, external_id=f"{LABEL}-pa", name="A 9+",
                                  rank=1, current_probability=0.0)
            s.add(twin)
            await s.flush()
            for at, p in ((OPEN + timedelta(hours=3), 0.31), (OPEN + timedelta(hours=8, minutes=30), 0.33)):
                s.add(FuturesOddsSnapshot(outcome_id=twin.id, bookmaker="polymarket",
                                          probability=p, captured_at=at))
    body = (await c.get("/api/futures/multi-history", params={
        "market_ids": f"{ids['market']},{poly.id}", "hours": HOURS, "top_n": 50,
    })).json()
    line = next(o for o in body["outcomes"] if o["name"] == "A 9+")
    archive = [p for p in line["history"] if p.get("provenance") == "kalshi_archive"]
    live = [p for p in line["history"] if p.get("bookmaker") == "consensus"]
    # The +3h instant already holds a live (Polymarket) value, so the archive
    # value there is not averaged in. Every other archive close stands.
    assert [p["timestamp"] for p in archive] == [
        (OPEN + timedelta(hours=h)).isoformat() for h in (1, 2, 4, 5, 6, 7, 8, 9, 10, 11)
    ]
    assert all(p["interval_start"] and p["period_minutes"] == 60 for p in archive)
    assert [datetime.fromisoformat(p["timestamp"]) for p in live] == [
        OPEN + timedelta(hours=3), OPEN + timedelta(hours=8, minutes=30)
    ]
    b_line = next(o for o in body["outcomes"] if o["name"] == "B 3+")
    assert [p["timestamp"] for p in b_line["history"] if p.get("provenance")] == [
        (OPEN + timedelta(hours=h)).isoformat() for h in (2, 3, 4, 6, 7, 8, 9, 10, 11)
    ]
    assert body["archive_history"]["state"] == "warm"


# ── the ACTUAL client "Full" request reaches an archive older than 180 days ──
#
# Root's finding on d58/c3 (683-ROOT-FULL-RANGE-REVIEW.md): the same import drew
# its archive at a hand-picked `hours=4800` and NOTHING at the web's real "Full"
# request, `hours=4320`, once the archive was 189 days old. The tests above all
# ask 4800, which is exactly how they missed it. These ask what the clients send:
# web EvolutionView "Full" and /futures "All" (`hours` floor + `range=full`, ux
# PR #11085's successor) and native's widest range (`hours=4320`). Each carries
# its own control: the identical request WITHOUT `range=full` still draws none,
# so the boundary the fix crosses is shown on the same specimen, not assumed.

#: Older than any window a client sends, and than the reader's own 2160h reach.
OLD_AGE = timedelta(days=189)
#: The web's "Full" `hours` (EvolutionView.tsx) and native's `.season`.
CLIENT_FULL_HOURS = 4320


@pytest.fixture
async def old_world(monkeypatch):
    """The same specimen, opened 189 days ago. Module constants are read at call
    time by the seed, the candles and the planner, and by the assertions."""
    mod = importlib.import_module(__name__)
    opened = (datetime.now(UTC) - OLD_AGE).replace(minute=0, second=0, microsecond=0)
    monkeypatch.setattr(mod, "OPEN", opened)
    monkeypatch.setattr(mod, "TIPOFF", opened + timedelta(hours=6))
    monkeypatch.setattr(mod, "SETTLED", opened + timedelta(hours=11, minutes=3))
    engine = await _engine()
    ids = await _seed(engine)
    yield engine, ids
    await engine.dispose()


@pytest.fixture
async def old_client(old_world, monkeypatch):
    async for served in _serve(old_world, monkeypatch):
        yield served


def _hours_ago(at) -> float:
    return (datetime.now(UTC) - at).total_seconds() / 3600


async def test_the_specimen_is_older_than_every_client_window(old_client):
    _c, _ids = old_client
    assert _hours_ago(OPEN) > CLIENT_FULL_HOURS
    assert _hours_ago(OPEN) > 2160  # the reader's own widest tier, too


async def test_web_full_on_one_market_reaches_the_189_day_archive(old_client):
    c, ids = old_client
    url = f"/api/futures/{ids['market']}/history"
    base = {"hours": CLIENT_FULL_HOURS, "top_n": 50}
    control = (await c.get(url, params=base)).json()
    assert not any(
        p.get("provenance") == "kalshi_archive"
        for o in control["outcomes"] for p in o["history"]
    ), "control: without range=full the 4320h window cannot reach a 189-day archive"
    assert "history_range" not in control

    r = await c.get(url, params={**base, "range": "full"})
    assert r.status_code == 200, r.text
    body = r.json()
    a = _archive_points({o["outcome_id"]: o for o in body["outcomes"]}[ids["a"]])
    assert [p["timestamp"] for p in a] == [
        (OPEN + timedelta(hours=h)).isoformat() for h in range(1, 12)
    ]
    assert all(p["period_minutes"] == 60 and p["interval_start"] for p in a)
    assert all(datetime.fromisoformat(p["timestamp"]) < SETTLED for p in a)
    rng = body["history_range"]
    assert rng["requested"] == "full"
    assert rng["window_start_basis"] == "archive_first_interval"
    assert datetime.fromisoformat(rng["window_start"]) == OPEN
    assert rng["archive_coverage"] == "complete"
    assert datetime.fromisoformat(rng["archive_venue_open"]) == OPEN
    assert rng["thinned_outcomes"] == []
    assert rng["live_thinned"] is False
    # `hours` echoes the request; the live arm reached its lifetime anyway.
    assert body["hours"] == CLIENT_FULL_HOURS
    # Root's executed BLOCK on aa2f140af6: B's two 189-day captures are OUR
    # evidence, so they draw and each still claims its own interval (+1h, +5h)
    # exactly as at the 120-day age — never painted over by the archive.
    b = {o["outcome_id"]: o for o in body["outcomes"]}[ids["b"]]
    assert _live_times(b) == {OPEN + timedelta(minutes=30), OPEN + timedelta(hours=4, minutes=20)}
    assert [p["timestamp"] for p in _archive_points(b)] == [
        (OPEN + timedelta(hours=h)).isoformat() for h in (2, 3, 4, 6, 7, 8, 9, 10, 11)
    ]
    assert body["archive_history"]["withheld_overlapping_live"] == 2


async def test_web_full_on_the_combined_chart_reaches_the_189_day_archive(
    old_client, old_world
):
    """Root's exact arm: `/multi-history`, Kalshi archive-only + a Polymarket twin."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome

    c, ids = old_client
    engine, _ = old_world
    async with AsyncSession(engine, expire_on_commit=False) as s:
        async with s.begin():
            poly = FuturesMarket(
                source="polymarket", external_id=f"{LABEL}-poly-old", name=f"{LABEL} old",
                category="game", market_tier=5, mutually_exclusive=False,
                status="resolved", resolution_date=SETTLED,
            )
            s.add(poly)
            await s.flush()
            twin = FuturesOutcome(market_id=poly.id, external_id=f"{LABEL}-po", name="A 9+",
                                  rank=1, current_probability=0.0)
            s.add(twin)
            await s.flush()
            s.add(FuturesOddsSnapshot(outcome_id=twin.id, bookmaker="polymarket",
                                      probability=0.31, captured_at=OPEN + timedelta(hours=3)))
    base = {"market_ids": f"{ids['market']},{poly.id}", "hours": CLIENT_FULL_HOURS, "top_n": 50}

    def _arm(body, name):
        line = next((o for o in body["outcomes"] if o["name"] == name), None)
        return [] if line is None else [
            p["timestamp"] for p in line["history"] if p.get("provenance") == "kalshi_archive"
        ]

    control = (await c.get("/api/futures/multi-history", params=base)).json()
    assert _arm(control, "A 9+") == [], "control: Root's 4320h FAIL, unchanged without range"
    assert "history_range" not in control

    body = (await c.get("/api/futures/multi-history", params={**base, "range": "full"})).json()
    # Root's executed BLOCK on aa2f140af6: this test used to assert the twin's
    # +3h capture DISAPPEARED under Full. It is our own evidence, so Full draws
    # it and the merged +3h instant keeps its live value (the archive is never
    # averaged into a capture) — the same answer as at the 120-day age above.
    a_line = next(o for o in body["outcomes"] if o["name"] == "A 9+")
    assert [datetime.fromisoformat(p["timestamp"]) for p in a_line["history"]
            if p.get("bookmaker") == "consensus"] == [OPEN + timedelta(hours=3)]
    assert _arm(body, "A 9+") == [
        (OPEN + timedelta(hours=h)).isoformat() for h in (1, 2, 4, 5, 6, 7, 8, 9, 10, 11)
    ]
    # B's own 189-day captures claim their intervals (+1h, +5h), as at 120 days.
    assert _arm(body, "B 3+") == [
        (OPEN + timedelta(hours=h)).isoformat() for h in (2, 3, 4, 6, 7, 8, 9, 10, 11)
    ]
    rng = body["history_range"]
    assert rng["window_start_basis"] == "archive_first_interval"
    assert datetime.fromisoformat(rng["window_start"]) == OPEN
    assert rng["archive_coverage"] == "complete"
    assert body["hours"] == CLIENT_FULL_HOURS


async def test_native_widest_range_reaches_the_189_day_archive(old_client):
    c, ids = old_client
    url = f"/api/futures/{ids['market']}/probability-timeline"
    base = {"hours": CLIENT_FULL_HOURS, "top": 50}
    control = (await c.get(url, params=base)).json()
    assert not any("archive" in e for e in control.get("timeline", []))
    assert "history_range" not in control

    body = (await c.get(url, params={**base, "range": "full"})).json()
    a_marks = [e for e in body["timeline"] if "A 9+" in e.get("archive", {})]
    assert [e["timestamp"] for e in a_marks] == [
        (OPEN + timedelta(hours=h)).isoformat() for h in range(1, 12)
    ]
    assert body["history_range"]["window_start_basis"] == "archive_first_interval"
    assert datetime.fromisoformat(body["history_range"]["window_start"]) == OPEN


async def test_a_full_read_over_the_cap_keeps_the_first_interval_and_says_it_thinned(
    old_client, monkeypatch
):
    """Span-keeping, never tail-cut: the bounded read alone drops the OLDEST."""
    from app.utils import kalshi_archive_reader as reader

    c, ids = old_client
    monkeypatch.setattr(reader, "READ_CAP_PER_OUTCOME", 4)
    url = f"/api/futures/{ids['market']}/history"

    bounded = (await c.get(url, params={"hours": 4800, "top_n": 50})).json()
    a = _archive_points({o["outcome_id"]: o for o in bounded["outcomes"]}[ids["a"]])
    assert [p["timestamp"] for p in a] == [
        (OPEN + timedelta(hours=h)).isoformat() for h in (8, 9, 10, 11)
    ], "control: the bounded read keeps only the newest run"
    assert ids["a"] in bounded["archive_history"]["read_capped_outcomes"]

    full = (await c.get(url, params={"hours": CLIENT_FULL_HOURS, "top_n": 50,
                                     "range": "full"})).json()
    a = _archive_points({o["outcome_id"]: o for o in full["outcomes"]}[ids["a"]])
    # 11 intervals, cap 4: newest four in full (+8h..+11h); the skeleton (rank
    # stride ceil(11/4)=3 → ranks 1, 4, 7, 10, 11) supplies the older +1h, +4h, +7h.
    assert [p["timestamp"] for p in a] == [
        (OPEN + timedelta(hours=h)).isoformat() for h in (1, 4, 7, 8, 9, 10, 11)
    ]
    assert ids["a"] in full["history_range"]["thinned_outcomes"]
    assert "read_capped_outcomes" not in full["archive_history"]
    assert datetime.fromisoformat(full["history_range"]["window_start"]) == OPEN


# ── Full keeps OUR older captures and their precedence (Root, aa2f140af6) ──
#
# Root executed aa2f140af6 on this exact fixture: B's two 189-day captures drew
# at `hours=4800` and VANISHED at the web's real Full request, with archive
# intervals painted over the span they had claimed. The test below is Root's
# control VERBATIM (683-ROOT-aa2-FULL-OLDER-LIVE-CONTROL.py); the rest pin the
# repair's other arms: native, the window's basis when live predates the
# archive, the bounded (thinned) read, and an unchanged in-window response.


def _live_times(history_outcome):
    return {
        datetime.fromisoformat(p["timestamp"]) for p in history_outcome["history"]
        if p.get("provenance") is None and p.get("bookmaker") != "settlement"
    }


async def test_root_full_retains_older_live_forecasts_and_overlap(old_client):
    c, ids = old_client
    url = f"/api/futures/{ids['market']}/history"
    def live_times(body):
        b = next(o for o in body['outcomes'] if o['outcome_id']==ids['b'])
        return {datetime.fromisoformat(p['timestamp']) for p in b['history']
                if p.get('provenance') is None and p.get('bookmaker') != 'settlement'}
    expected = {OPEN+timedelta(minutes=30), OPEN+timedelta(hours=4,minutes=20)}
    wide = await c.get(url, params={'hours':4800,'top_n':50})
    assert wide.status_code==200,wide.text
    assert expected.issubset(live_times(wide.json())), 'positive control: existing old live observations must be drawable'
    full = await c.get(url, params={'hours':4320,'top_n':50,'range':'full'})
    assert full.status_code==200,full.text
    assert expected.issubset(live_times(full.json())), 'Full hides older live forecasts that the ordinary wide reader can draw'


async def test_native_full_keeps_older_live_captures_and_their_intervals(old_client):
    c, ids = old_client
    url = f"/api/futures/{ids['market']}/probability-timeline"
    base = {"hours": CLIENT_FULL_HOURS, "top": 50}
    control = (await c.get(url, params=base)).json()
    assert not any("B 3+" in e.get("outcomes", {}) for e in control.get("timeline", [])), (
        "control: the 4320h window alone reaches none of B's 189-day evidence"
    )
    body = (await c.get(url, params={**base, "range": "full"})).json()
    b_marks = [e["timestamp"] for e in body["timeline"] if "B 3+" in e.get("archive", {})]
    # Live at +0:30 and +4:20 claim the +1h and +5h intervals, so neither is an
    # archive value; the gap between and everything after stand.
    assert (OPEN + timedelta(hours=1)).isoformat() not in b_marks
    assert (OPEN + timedelta(hours=5)).isoformat() not in b_marks
    assert {(OPEN + timedelta(hours=h)).isoformat() for h in (2, 3, 6, 7, 8, 9, 10, 11)} <= set(b_marks)
    live_b = [e["timestamp"] for e in body["timeline"]
              if "B 3+" in e.get("outcomes", {}) and "B 3+" not in e.get("archive", {})]
    assert OPEN.isoformat() in live_b, "B's +0:30 capture draws, unmarked, in its own bucket"
    assert body["archive_history"]["withheld_overlapping_live"] == 2
    assert body["history_range"]["live_thinned"] is False
    assert body["hours"] == CLIENT_FULL_HOURS


async def test_full_starts_at_our_first_capture_when_it_predates_the_archive(
    old_client, old_world
):
    """Nothing is assumed about the question's open: the evidence says it."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesOddsSnapshot

    c, ids = old_client
    engine, _ = old_world
    early = OPEN - timedelta(hours=2)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        async with s.begin():
            s.add(FuturesOddsSnapshot(
                outcome_id=ids["b"], bookmaker="kalshi", probability=0.48,
                yes_bid=0.47, yes_ask=0.49, last_price=0.48, captured_at=early,
            ))
    body = (await c.get(f"/api/futures/{ids['market']}/history", params={
        "hours": CLIENT_FULL_HOURS, "top_n": 50, "range": "full",
    })).json()
    rng = body["history_range"]
    assert rng["window_start_basis"] == "live_first_capture"
    assert datetime.fromisoformat(rng["window_start"]) == early
    b = {o["outcome_id"]: o for o in body["outcomes"]}[ids["b"]]
    assert early in _live_times(b)


async def test_a_thinned_older_live_read_claims_only_the_intervals_its_skipped_capture_sits_in(
    old_client, old_world, monkeypatch
):
    """Bounded by instant, span-keeping, and a skipped capture claims exactly
    the interval it lies in — never the empty hours around it (Root, 6804c13fc2)."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesOddsSnapshot
    from app.utils import full_range_live

    c, ids = old_client
    engine, _ = old_world
    skipped = OPEN + timedelta(hours=2, minutes=30)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        async with s.begin():
            s.add(FuturesOddsSnapshot(
                outcome_id=ids["b"], bookmaker="kalshi", probability=0.53,
                yes_bid=0.52, yes_ask=0.54, last_price=0.53, captured_at=skipped,
            ))
    url = f"/api/futures/{ids['market']}/history"
    params = {"hours": CLIENT_FULL_HOURS, "top_n": 50, "range": "full"}

    def _b(body):
        return {o["outcome_id"]: o for o in body["outcomes"]}[ids["b"]]

    whole = (await c.get(url, params=params)).json()
    assert _live_times(_b(whole)) == {
        OPEN + timedelta(minutes=30), skipped, OPEN + timedelta(hours=4, minutes=20)
    }, "control: under the cap every older instant is read"
    whole_archive = [p["timestamp"] for p in _archive_points(_b(whole))]
    assert whole_archive == [
        (OPEN + timedelta(hours=h)).isoformat() for h in (2, 4, 6, 7, 8, 9, 10, 11)
    ]
    assert whole["history_range"]["live_thinned"] is False

    # Three instants, cap 1: rank stride 3 keeps the first and the last only.
    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 1)
    thin = (await c.get(url, params=params)).json()
    assert _live_times(_b(thin)) == {
        OPEN + timedelta(minutes=30), OPEN + timedelta(hours=4, minutes=20)
    }
    assert thin["history_range"]["live_thinned"] is True
    # +2:30 was not drawn, but it still claims +3h (2h..3h), the one interval it
    # sits in. +2h and +4h hold no capture of B and stand exactly as unthinned.
    assert [p["timestamp"] for p in _archive_points(_b(thin))] == whole_archive
    assert thin["archive_history"]["withheld_overlapping_live"] == (
        whole["archive_history"]["withheld_overlapping_live"]
    )
    # Oldest capture kept, never tail-cut; the window still opens on the archive.
    assert datetime.fromisoformat(thin["history_range"]["window_start"]) == OPEN


# ── Root's executed BLOCK on 6804c13fc2: the ACTUAL cap and a sparse gap ──
#
# Root's control below is VERBATIM (683-ROOT-6804-DEFAULT-CAP-SPARSE-CONTROL.py,
# second test): 2,000 dense captures plus +0:30, +4:20 and +8:20 cross the real
# 2,000-instant cap with no monkeypatch. +4:20 is a skipped instant; the span
# cut stretched B's presence from +0:10 to +8:20 and erased the valid +2h
# interval. The tests after it hold the same fixture on native's timeline and
# the combined chart, a refused skipped capture, and the venue arm.


async def _add_actual_cap_captures(engine, ids, *extra, dense=2000):
    """Root's fixture: +8:20 plus 2,000 distinct supported captures in +0:10..+0:44."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesOddsSnapshot

    async with AsyncSession(engine, expire_on_commit=False) as db:
        async with db.begin():
            db.add(FuturesOddsSnapshot(
                outcome_id=ids["b"], bookmaker="kalshi", probability=0.44,
                yes_bid=0.43, yes_ask=0.45, last_price=0.44,
                captured_at=OPEN + timedelta(hours=8, minutes=20),
            ))
            db.add_all([FuturesOddsSnapshot(
                outcome_id=ids["b"], bookmaker="kalshi", probability=0.44,
                yes_bid=0.43, yes_ask=0.45, last_price=0.44,
                captured_at=OPEN + timedelta(minutes=10, milliseconds=123, seconds=i),
            ) for i in range(dense)])
            db.add_all(list(extra))


async def test_root_thinning_preserves_nonoverlapping_archive(old_client, old_world, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.models import FuturesOddsSnapshot
    from app.utils import full_range_live as fr
    c, ids = old_client
    engine, _ = old_world
    async with AsyncSession(engine,expire_on_commit=False) as db:
        async with db.begin():
            db.add(FuturesOddsSnapshot(outcome_id=ids['b'],bookmaker='kalshi',probability=0.44,
                yes_bid=0.43,yes_ask=0.45,last_price=0.44,captured_at=OPEN+timedelta(hours=8,minutes=20)))
    async with AsyncSession(engine,expire_on_commit=False) as db:
        async with db.begin():
            db.add_all([FuturesOddsSnapshot(outcome_id=ids['b'],bookmaker='kalshi',probability=0.44,
                yes_bid=0.43,yes_ask=0.45,last_price=0.44,
                captured_at=OPEN+timedelta(minutes=10,milliseconds=123,seconds=i)) for i in range(2000)])
    def archived_times(body):
        b=next(o for o in body['outcomes'] if o['outcome_id']==ids['b'])
        return {datetime.fromisoformat(p['timestamp']) for p in b['history'] if p.get('provenance')=='kalshi_archive'}
    url=f"/api/futures/{ids['market']}/history"
    wide=await c.get(url,params={'hours':4800,'top_n':50})
    assert wide.status_code==200,wide.text
    valid=OPEN+timedelta(hours=2)
    overlapping=OPEN+timedelta(hours=5)
    assert valid in archived_times(wide.json()),'positive control: +1h..+2h contains no live capture'
    assert overlapping not in archived_times(wide.json()),'positive control: +4h..+5h contains a live capture'
    assert fr.OLDER_LIVE_INSTANT_CAP==2000, 'exercise actual production cap'
    full=await c.get(url,params={'hours':4320,'top_n':50,'range':'full'})
    assert full.status_code==200,full.text
    assert valid in archived_times(full.json()),'Thinning invents dense live coverage and hides a nonoverlapping archive interval'
    assert overlapping not in archived_times(full.json()),'Archive must still yield to a skipped real live capture'


async def test_actual_cap_full_is_thinned_and_serves_the_same_archive_as_the_wide_read(
    old_client, old_world
):
    """The same fixture, every interval: Full equals the ordinary wide window."""
    c, ids = old_client
    engine, _ = old_world
    await _add_actual_cap_captures(engine, ids)
    url = f"/api/futures/{ids['market']}/history"

    def _b(body):
        return {o["outcome_id"]: o for o in body["outcomes"]}[ids["b"]]

    wide = (await c.get(url, params={"hours": 4800, "top_n": 50})).json()
    full = (await c.get(url, params={"hours": CLIENT_FULL_HOURS, "top_n": 50,
                                     "range": "full"})).json()
    assert full["history_range"]["live_thinned"] is True, "the real cap is crossed"
    # +4:20 is rank 2002 of 2003 (stride 2): skipped, so this is the case rule 4
    # exists for, not one the skeleton happened to draw.
    assert OPEN + timedelta(hours=4, minutes=20) not in _live_times(_b(full))
    expected = [(OPEN + timedelta(hours=h)).isoformat() for h in (2, 3, 4, 6, 7, 8, 10, 11)]
    assert [p["timestamp"] for p in _archive_points(_b(wide))] == expected
    assert [p["timestamp"] for p in _archive_points(_b(full))] == expected


async def test_actual_cap_native_timeline_and_combined_chart_keep_the_sparse_gap(
    old_client, old_world, monkeypatch
):
    from app.utils import full_range_live

    c, ids = old_client
    engine, _ = old_world
    await _add_actual_cap_captures(engine, ids)
    gap = (OPEN + timedelta(hours=2)).isoformat()      # 1h..2h holds no capture
    skipped = (OPEN + timedelta(hours=5)).isoformat()  # 4h..5h holds the skipped +4:20

    # Native: the thinned timeline serves exactly the unthinned one's archive
    # marks. (Its seat rule also lets B's +4:20 cell hold +4h, so the timeline
    # never draws +4h either way; that is why it is compared, not enumerated.)
    url = f"/api/futures/{ids['market']}/probability-timeline"
    params = {"hours": CLIENT_FULL_HOURS, "top": 50, "range": "full"}

    def _marks(body):
        return {e["timestamp"] for e in body["timeline"] if "B 3+" in e.get("archive", {})}

    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 4000)
    whole = (await c.get(url, params=params)).json()
    assert whole["history_range"]["live_thinned"] is False
    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 2000)
    timeline = (await c.get(url, params=params)).json()
    assert timeline["history_range"]["live_thinned"] is True
    assert _marks(timeline) == _marks(whole)
    assert gap in _marks(timeline) and skipped not in _marks(timeline)

    # The combined chart seats by exact instant: Root's pair, and the rest of B.
    multi = (await c.get("/api/futures/multi-history", params={
        "market_ids": str(ids["market"]), "hours": CLIENT_FULL_HOURS, "top_n": 50,
        "range": "full",
    })).json()
    assert multi["history_range"]["live_thinned"] is True
    line = next(o for o in multi["outcomes"] if o["name"] == "B 3+")
    arm = {p["timestamp"] for p in line["history"] if p.get("provenance") == "kalshi_archive"}
    assert arm == {(OPEN + timedelta(hours=h)).isoformat() for h in (2, 3, 4, 6, 7, 8, 10, 11)}


# ── CERT-4139/4140's executed BLOCK: the merged question's skipped twin ──
#
# The reviewer's independent test, VERBATIM (/private/tmp/cert4139-review,
# test_cert4139_independent_pg.py; only its star-import line is dropped, as it
# lives in this module): a Polymarket twin's 2,001 old captures cross the cap,
# rank-striding away its +3h capture, and the Kalshi archive close at that same
# instant on the same merged question must still yield to it.


async def test_default_cap_combined_twin_retains_skipped_live_precedence(old_client, old_world, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
    from app.utils import full_range_live
    import tests.integration.test_kalshi_archive_store_683_pg as specimen
    opened = specimen.OPEN
    settled = specimen.SETTLED
    c, ids = old_client
    engine, _ = old_world
    async with AsyncSession(engine, expire_on_commit=False) as s:
        async with s.begin():
            poly = FuturesMarket(source="polymarket", external_id="CERT4139-twin", name="CERT4139 twin", category="game", market_tier=5, mutually_exclusive=False, status="resolved", resolution_date=settled)
            s.add(poly); await s.flush()  # noqa: E702 — verbatim
            twin = FuturesOutcome(market_id=poly.id, external_id="CERT4139-A", name="A 9+", rank=1, current_probability=0.0)
            s.add(twin); await s.flush()  # noqa: E702 — verbatim
            s.add_all([FuturesOddsSnapshot(outcome_id=twin.id, bookmaker="polymarket", probability=0.31, captured_at=opened + timedelta(seconds=i*10)) for i in range(1, 2002)])
    params = {"market_ids": f"{ids['market']},{poly.id}", "hours": 4320, "top_n": 50, "range": "full"}
    at = (opened + timedelta(hours=3)).isoformat()
    def line(body): return next(o for o in body["outcomes"] if o["name"] == "A 9+")['history']
    monkeypatch.setattr(full_range_live, 'OLDER_LIVE_INSTANT_CAP', 4000)
    wide_r = await c.get('/api/futures/multi-history', params=params)
    assert wide_r.status_code == 200, wide_r.text
    wide = wide_r.json()
    assert any(p['timestamp'] == at and p.get('bookmaker') == 'consensus' for p in line(wide))
    assert not any(p['timestamp'] == at and p.get('provenance') == 'kalshi_archive' for p in line(wide))
    monkeypatch.setattr(full_range_live, 'OLDER_LIVE_INSTANT_CAP', 2000)
    thin_r = await c.get('/api/futures/multi-history', params=params)
    assert thin_r.status_code == 200, thin_r.text
    thin = thin_r.json()
    assert thin['history_range']['live_thinned'] is True
    assert not any(p['timestamp'] == at and p.get('bookmaker') == 'consensus' for p in line(thin)), 'control: rank stride skipped the old twin instant'
    print('WITNESS', {'at':at, 'uncapped_at':[p for p in line(wide) if p['timestamp']==at], 'default_cap_at':[p for p in line(thin) if p['timestamp']==at], 'live_thinned':thin['history_range']['live_thinned']})
    assert not any(p['timestamp'] == at and p.get('provenance') == 'kalshi_archive' for p in line(thin)), 'Full replaces a skipped live twin capture with an archive value on the same merged question'


async def test_actual_cap_timeline_keeps_a_skipped_captures_own_cell_from_the_archive(
    old_client, old_world, monkeypatch
):
    """Native's seat rule: a capture cell STARTING at an archive close seats the
    outcome there, so the archive yields. Thinned, the cell's only capture is
    skipped; it must still hold the seat (no archive at +6h), as unthinned."""
    from app.models.models import FuturesOddsSnapshot
    from app.utils import full_range_live

    c, ids = old_client
    engine, _ = old_world
    in_cell = OPEN + timedelta(hours=6, minutes=20)  # cell [+6h, +7h); interval 5h..6h untouched
    # 1,999 dense + +0:30 + +4:20 + +6:20 + +8:20 = 2,003 instants, stride 2:
    # +6:20 is rank 2002, the one skipped.
    await _add_actual_cap_captures(engine, ids, FuturesOddsSnapshot(
        outcome_id=ids["b"], bookmaker="kalshi", probability=0.46,
        yes_bid=0.45, yes_ask=0.47, last_price=0.46, captured_at=in_cell,
    ), dense=1999)
    url = f"/api/futures/{ids['market']}/probability-timeline"
    params = {"hours": CLIENT_FULL_HOURS, "top": 50, "range": "full"}
    seat = (OPEN + timedelta(hours=6)).isoformat()

    def _marks(body):
        return {e["timestamp"] for e in body["timeline"] if "B 3+" in e.get("archive", {})}

    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 4000)
    whole = (await c.get(url, params=params)).json()
    assert whole["history_range"]["live_thinned"] is False
    assert seat not in _marks(whole), "control: unthinned, B's +6:20 cell seats B at +6h"
    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 2000)
    thin = (await c.get(url, params=params)).json()
    assert thin["history_range"]["live_thinned"] is True
    assert seat not in _marks(thin), "a skipped capture's cell must not hand its seat to the archive"
    assert _marks(thin) == _marks(whole)
    assert (OPEN + timedelta(hours=2)).isoformat() in _marks(thin), "the empty gap still stands"


async def test_actual_cap_admission_pages_past_refused_captures_on_the_real_store(old_world):
    """Exact admission on PostgreSQL: a window is claimed only by a capture the
    route's own support filter keeps, found by keyset paging (ties by id).

    The support filter is passed here as a stand-in that refuses one marked
    price, so the paging itself is what is pinned; the routes pass
    `_drop_unsupported_snapshot_points` (unit-pinned by count), which DOES
    refuse rows on archive-eligible outcomes — a graded loser priced above its
    ask, and every arm on an ungraded or retracted outcome. CERT-4141's
    route-level witness below runs that real filter.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesOddsSnapshot
    from app.utils.full_range_live import read_older_live

    engine, ids = old_world

    # The stand-in refuses by a marker the row carries, never by a float.
    REFUSED = "refused-by-stand-in"

    def _snap(at, bookmaker="kalshi"):
        return FuturesOddsSnapshot(outcome_id=ids["b"], bookmaker=bookmaker, probability=0.41,
                                   yes_bid=0.40, yes_ask=0.42, last_price=0.41,
                                   captured_at=at)

    await _add_actual_cap_captures(
        engine, ids,
        _snap(OPEN + timedelta(hours=2, minutes=30), REFUSED),
        _snap(OPEN + timedelta(hours=6, minutes=10), REFUSED),
        _snap(OPEN + timedelta(hours=6, minutes=10), REFUSED),  # a tie on the instant
        _snap(OPEN + timedelta(hours=6, minutes=40)),
    )
    before = datetime.now(UTC) - timedelta(hours=CLIENT_FULL_HOURS)
    windows = [
        (ids["b"], OPEN + timedelta(hours=2), OPEN + timedelta(hours=3)),  # refused only
        (ids["b"], OPEN + timedelta(hours=4), OPEN + timedelta(hours=5)),  # +4:20
        (ids["b"], OPEN + timedelta(hours=6), OPEN + timedelta(hours=7)),  # 2 refused, then kept
        (ids["a"], OPEN + timedelta(hours=4), OPEN + timedelta(hours=5)),  # A holds nothing
        (ids["b"], OPEN + timedelta(hours=1), OPEN + timedelta(hours=2)),  # Root's empty gap
    ]
    async with AsyncSession(engine, expire_on_commit=False) as db:
        older = await read_older_live(db, [ids["a"], ids["b"]], before=before)
        assert older.thinned is True
        hits = await older.admit(
            db, windows, supported=lambda rows: [r for r in rows if r.bookmaker != REFUSED]
        )
    assert [None if h is None else h.captured_at for h in hits] == [
        None,
        OPEN + timedelta(hours=4, minutes=20),
        OPEN + timedelta(hours=6, minutes=40),
        None,
        None,
    ]
    assert older.unresolved == 0


async def test_actual_cap_venue_points_yield_only_to_a_skipped_capture_beside_them(
    old_world,
):
    """The venue arm's admission on the real store: the exact SQL, real types."""
    from types import SimpleNamespace

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.full_range_live import read_older_live

    engine, ids = old_world
    await _add_actual_cap_captures(engine, ids)
    before = datetime.now(UTC) - timedelta(hours=CLIENT_FULL_HOURS)
    beside = OPEN + timedelta(hours=4, minutes=20)  # the skipped instant
    venue = [
        SimpleNamespace(outcome_id=ids["b"], captured_at=OPEN + timedelta(hours=h),
                        tier="kalshi_candle_60m")
        for h in (2, 3)
    ] + [
        SimpleNamespace(outcome_id=ids["b"], captured_at=beside + timedelta(minutes=10),
                        tier="kalshi_candle_60m"),
        SimpleNamespace(outcome_id=ids["a"], captured_at=beside, tier="kalshi_candle_60m"),
    ]
    async with AsyncSession(engine, expire_on_commit=False) as db:
        older = await read_older_live(db, [ids["a"], ids["b"]], before=before)
        assert older.thinned is True and beside not in {r.captured_at for r in older.rows}
        kept, unknown = await older.withhold_venue(db, venue, supported=lambda rows: rows)
    assert unknown == []
    # +2h and +3h sit in the empty gap and stand; +4:30 is ten minutes from B's
    # skipped capture and yields; A holds no capture, so its point stands.
    assert [(r.outcome_id, r.captured_at) for r in kept] == [
        (ids["b"], OPEN + timedelta(hours=2)), (ids["b"], OPEN + timedelta(hours=3)),
        (ids["a"], beside),
    ]


# ── CERT-4141's executed BLOCK: an exhausted admission budget is UNKNOWN ──
#
# The reviewer's specimen (/private/tmp/cert4141-review,
# test_cert4141_independent_pg.py): A ungraded, 2,001 empty-book captures inside
# +1h..+2h, every one refused by the route's own support filter. On 6a25781e00
# the default cap drew nine archive prices where the unthinned read drew
# eleven: the budget-exhausted window became a synthetic capture at +1h, which
# was counted as live's AND erased the preceding +0h..+1h interval through
# inclusive overlap. Under rule 5 the +1h price returns; +1h..+2h, whose unread
# remainder (rows 74..2,001) the bounded read cannot see, is withheld fail
# closed and DISCLOSED, never counted as live's. Root's disposition accepts this
# separation (ROOT-ARGON-UNKNOWN-DISPOSITION.md: 73+ refused rows stay UNKNOWN
# within these limits). The reviewer's last assertion, that +2h itself draws at
# the default cap, is therefore not what this asserts.


async def _cert4141_specimen(engine, ids):
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesOddsSnapshot, FuturesOutcome
    from app.routes.futures import _drop_unsupported_snapshot_points

    async with AsyncSession(engine, expire_on_commit=False) as s:
        async with s.begin():
            await s.execute(update(FuturesOutcome).where(FuturesOutcome.id == ids["a"]).values(
                resolution_source=None, is_winner=None))
            s.add_all([FuturesOddsSnapshot(
                outcome_id=ids["a"], bookmaker="kalshi", probability=0.5, yes_bid=0.01,
                yes_ask=0.99, last_price=None, captured_at=OPEN + timedelta(hours=1, seconds=i),
            ) for i in range(1, 2002)])
        outcome = await s.get(FuturesOutcome, ids["a"])
        raw = list((await s.execute(select(FuturesOddsSnapshot).where(
            FuturesOddsSnapshot.outcome_id == ids["a"]))).scalars().all())
    assert len(raw) == 2001
    assert _drop_unsupported_snapshot_points(raw, [outcome]) == [], (
        "control: the actual route refuses every empty-book capture"
    )


async def test_cert4141_default_cap_restores_the_adjacent_price_and_discloses_the_unknown(
    old_client, old_world, monkeypatch
):
    from app.utils import full_range_live

    c, ids = old_client
    engine, _ = old_world
    await _cert4141_specimen(engine, ids)
    url = f"/api/futures/{ids['market']}/history"
    params = {"hours": CLIENT_FULL_HOURS, "top_n": 50, "range": "full"}
    adjacent = (OPEN + timedelta(hours=1)).isoformat()
    undecided = (OPEN + timedelta(hours=2)).isoformat()

    def _a(body):
        line = next(o for o in body["outcomes"] if o["outcome_id"] == ids["a"])
        return [p["timestamp"] for p in line["history"] if p.get("provenance") == "kalshi_archive"]

    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 4000)
    whole = (await c.get(url, params=params)).json()
    assert whole["history_range"]["live_thinned"] is False
    assert adjacent in _a(whole) and undecided in _a(whole), "positive control"
    assert whole["history_range"]["served_history"] == "complete"
    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 2000)
    r = await c.get(url, params=params)
    assert r.status_code == 200, r.text
    thin = r.json()
    assert full_range_live.ADMIT_ROUND_LIMITS == (1, 8, 64)
    assert thin["history_range"]["live_thinned"] is True
    assert adjacent in _a(thin), "the synthetic capture no longer erases its neighbour"
    assert undecided not in _a(thin), "unread rows 74..2,001 may hold a supported capture"
    assert _a(thin) == [t for t in _a(whole) if t != undecided], "every verified sibling stands"
    arch = thin["archive_history"]
    assert arch["withheld_overlapping_live"] == whole["archive_history"]["withheld_overlapping_live"], (
        "an exhausted budget is never counted as live ownership"
    )
    assert arch["withheld_unresolved_overlap"] == 1
    assert {"scope": "overlap_admission", "reason": "live_overlap_unresolved",
            "intervals": 1} in arch["refusals"]
    assert thin["history_range"]["served_history"] == "partial"
    assert thin["history_range"]["unresolved_withheld"] == {
        "archive_intervals": 1, "venue_points": 0
    }


async def test_cert4141_specimen_on_the_native_timeline_and_the_combined_chart(
    old_client, old_world, monkeypatch
):
    from app.utils import full_range_live

    c, ids = old_client
    engine, _ = old_world
    await _cert4141_specimen(engine, ids)
    adjacent = (OPEN + timedelta(hours=1)).isoformat()
    undecided = (OPEN + timedelta(hours=2)).isoformat()

    url = f"/api/futures/{ids['market']}/probability-timeline"
    params = {"hours": CLIENT_FULL_HOURS, "top": 50, "range": "full"}

    def _marks(body):
        return {e["timestamp"] for e in body["timeline"] if "A 9+" in e.get("archive", {})}

    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 4000)
    whole = (await c.get(url, params=params)).json()
    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 2000)
    thin = (await c.get(url, params=params)).json()
    assert thin["history_range"]["live_thinned"] is True
    assert adjacent in _marks(whole) and undecided in _marks(whole), "positive control"
    # The timeline seats a close in the capture cell STARTING at it: +1h's cell
    # [+1h, +2h) is the same 2,001 refused captures, so that seat is UNKNOWN
    # too. Two undecided candidates, both withheld, both counted, none live's.
    assert _marks(thin) == _marks(whole) - {adjacent, undecided}
    assert thin["archive_history"]["withheld_unresolved_overlap"] == 2
    assert thin["archive_history"]["withheld_overlapping_live"] == (
        whole["archive_history"]["withheld_overlapping_live"]
    )
    assert thin["history_range"]["served_history"] == "partial"

    multi_params = {"market_ids": str(ids["market"]), "hours": CLIENT_FULL_HOURS,
                    "top_n": 50, "range": "full"}

    def _arm(body):
        line = next(o for o in body["outcomes"] if o["name"] == "A 9+")
        return {p["timestamp"] for p in line["history"] if p.get("provenance") == "kalshi_archive"}

    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 4000)
    m_whole = (await c.get("/api/futures/multi-history", params=multi_params)).json()
    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 2000)
    m_thin = (await c.get("/api/futures/multi-history", params=multi_params)).json()
    assert m_thin["history_range"]["live_thinned"] is True
    assert adjacent in _arm(m_whole) and undecided in _arm(m_whole), "positive control"
    assert _arm(m_thin) == _arm(m_whole) - {undecided}
    assert m_thin["archive_history"]["withheld_overlapping_live"] == (
        m_whole["archive_history"]["withheld_overlapping_live"]
    )
    assert m_thin["history_range"]["unresolved_withheld"]["archive_intervals"] == 1


async def test_full_timeline_with_only_unknown_history_still_discloses_partial(old_world, monkeypatch):
    """CERT-4144 / Root 616 witness: the SOLE interval withheld UNKNOWN empties the chart.

    The real planner+apply import ONE traded A interval; every live capture is
    the CERT-4141 empty book the support filter refuses. cap 4000 draws the
    interval (positive control). The default cap 2000 correctly withholds it, and
    the empty `timeline` must still say so: `served_history=partial`, not a
    response with no `history_range` that reads as "this market has no history".
    """
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesOddsSnapshot
    from app.utils import full_range_live

    engine, ids = old_world
    async with AsyncSession(engine) as session:
        await session.execute(delete(FuturesOddsSnapshot))
        await session.commit()
    original_plan = _plan

    async def one_valid_interval(engine, _ids, candles=None):
        return await original_plan(engine, [ids["a"]], candles={
            TA: [_candle(OPEN + timedelta(hours=2), 0.32)]
        })

    monkeypatch.setattr(importlib.import_module(__name__), "_plan", one_valid_interval)
    async for client, _seeded in _serve(old_world, monkeypatch):
        await _cert4141_specimen(engine, ids)
        url = f"/api/futures/{ids['market']}/probability-timeline"
        params = {"hours": CLIENT_FULL_HOURS, "top": 50, "range": "full"}
        monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 4000)
        whole = (await client.get(url, params=params)).json()
        assert whole["timeline"], "positive control: the real imported archive interval draws"
        assert whole["history_range"]["served_history"] == "complete"
        monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 2000)
        r = await client.get(url, params=params)
        assert r.status_code == 200, r.text
        thin = r.json()
        assert thin["timeline"] == [] and thin["outcomes"] == [], (
            "the only interval is correctly withheld fail-closed")
        rng = thin.get("history_range")
        assert rng is not None, "an empty Full chart dropped its range statement"
        assert rng["served_history"] == "partial"
        assert rng["unresolved_withheld"] == {"archive_intervals": 1, "venue_points": 0}
        assert rng["live_thinned"] is True
        arch = thin["archive_history"]
        assert arch["points_served"] == 0
        assert arch["withheld_unresolved_overlap"] == 1
        assert {"scope": "overlap_admission", "reason": "live_overlap_unresolved",
                "intervals": 1} in arch["refusals"]
        # The same bytes, not `range=full`: no range statement is invented.
        plain = (await client.get(url, params={"hours": CLIENT_FULL_HOURS, "top": 50})).json()
        assert "history_range" not in plain


async def test_default_cap_combined_seat_a_twin_cannot_decide_is_withheld_and_disclosed(
    old_client, old_world, monkeypatch
):
    """The merged SEAT rule's UNKNOWN (CERT-4139's shape, refused twin): a
    second Kalshi market's ungraded "A 9+" holds 74 empty-book rows AT the +3h
    close, so the route refuses every one (no historical Polymarket row is
    refusable today, so the twin is Kalshi's). Unthinned nothing draws there
    and the archive close stands; thinned, the seat's admission runs out at 73
    rows and the close is withheld and counted, never painted over row 74."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.utils import full_range_live

    c, ids = old_client
    engine, _ = old_world
    at_dt = OPEN + timedelta(hours=3)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        async with s.begin():
            poly = FuturesMarket(source="kalshi", external_id="CERT4141-twin",
                                 name="CERT4141 twin", category="game", market_tier=5,
                                 mutually_exclusive=False, status="resolved",
                                 resolution_date=SETTLED)
            s.add(poly)
            await s.flush()
            twin = FuturesOutcome(market_id=poly.id, external_id="CERT4141-A", name="A 9+",
                                  rank=1, current_probability=0.0)
            s.add(twin)
            await s.flush()
            # 2,001 supported instants off the hour cross the cap...
            s.add_all([FuturesOddsSnapshot(
                outcome_id=twin.id, bookmaker="kalshi", probability=0.31, yes_bid=0.30,
                yes_ask=0.32, last_price=0.31, captured_at=OPEN + timedelta(seconds=i * 10 + 5),
            ) for i in range(1, 2002)])
            # ...and 74 refused rows sit exactly at the close.
            s.add_all([FuturesOddsSnapshot(
                outcome_id=twin.id, bookmaker="kalshi", probability=0.5,
                yes_bid=0.01, yes_ask=0.99, last_price=None, captured_at=at_dt,
            ) for _ in range(74)])
    params = {"market_ids": f"{ids['market']},{poly.id}", "hours": CLIENT_FULL_HOURS,
              "top_n": 50, "range": "full"}
    at = at_dt.isoformat()

    def _line(body):
        return next(o for o in body["outcomes"] if o["name"] == "A 9+")["history"]

    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 4000)
    whole = (await c.get("/api/futures/multi-history", params=params)).json()
    assert whole["history_range"]["live_thinned"] is False
    assert not any(p["timestamp"] == at and p.get("bookmaker") == "consensus"
                   for p in _line(whole)), "control: the route refuses every row at +3h"
    assert any(p["timestamp"] == at and p.get("provenance") == "kalshi_archive"
               for p in _line(whole)), "control: unthinned, the close stands"
    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 2000)
    thin = (await c.get("/api/futures/multi-history", params=params)).json()
    assert thin["history_range"]["live_thinned"] is True
    assert not any(p["timestamp"] == at for p in _line(thin)), "UNKNOWN fails closed"
    assert thin["archive_history"]["withheld_unresolved_overlap"] == 1
    assert thin["history_range"]["unresolved_withheld"]["archive_intervals"] == 1
    others = {p["timestamp"] for p in _line(whole) if p.get("provenance") == "kalshi_archive"}
    assert {p["timestamp"] for p in _line(thin)
            if p.get("provenance") == "kalshi_archive"} == others - {at}


async def test_actual_cap_timeline_cell_admission_cannot_decide_is_withheld_and_disclosed(
    old_client, old_world, monkeypatch
):
    """The timeline SEAT rule's UNKNOWN: A's cell [+6h, +7h) holds 74 refused
    captures and nothing else; interval +5h..+6h holds none, so it is admitted
    and its close is asked of the cell, which runs out of budget."""
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesOddsSnapshot, FuturesOutcome
    from app.utils import full_range_live

    c, ids = old_client
    engine, _ = old_world
    await _add_actual_cap_captures(engine, ids)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        async with s.begin():
            await s.execute(update(FuturesOutcome).where(FuturesOutcome.id == ids["a"]).values(
                resolution_source=None, is_winner=None))
            s.add_all([FuturesOddsSnapshot(
                outcome_id=ids["a"], bookmaker="kalshi", probability=0.5, yes_bid=0.01,
                yes_ask=0.99, last_price=None,
                captured_at=OPEN + timedelta(hours=6, minutes=20, seconds=i),
            ) for i in range(74)])
    url = f"/api/futures/{ids['market']}/probability-timeline"
    params = {"hours": CLIENT_FULL_HOURS, "top": 50, "range": "full"}
    seat = (OPEN + timedelta(hours=6)).isoformat()

    def _marks(body):
        return {e["timestamp"] for e in body["timeline"] if "A 9+" in e.get("archive", {})}

    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 4000)
    whole = (await c.get(url, params=params)).json()
    assert whole["history_range"]["live_thinned"] is False
    assert seat in _marks(whole), "control: unthinned, a refused-only cell seats nothing"
    monkeypatch.setattr(full_range_live, "OLDER_LIVE_INSTANT_CAP", 2000)
    thin = (await c.get(url, params=params)).json()
    assert thin["history_range"]["live_thinned"] is True
    assert seat not in _marks(thin), "UNKNOWN fails closed"
    assert thin["archive_history"]["withheld_unresolved_overlap"] >= 1
    assert thin["history_range"]["served_history"] == "partial"


async def test_actual_cap_an_unknown_venue_point_is_withheld_and_still_claims_its_interval(
    old_world,
):
    """The venue arm on the real store: 74 refused rows beside a venue point."""
    from types import SimpleNamespace

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesOddsSnapshot
    from app.utils.full_range_live import read_older_live

    engine, ids = old_world
    REFUSED = "refused-by-stand-in"
    near = OPEN + timedelta(hours=2, minutes=30)
    await _add_actual_cap_captures(engine, ids, *[FuturesOddsSnapshot(
        outcome_id=ids["b"], bookmaker=REFUSED, probability=0.41, yes_bid=0.40,
        yes_ask=0.42, last_price=0.41, captured_at=near + timedelta(seconds=i),
    ) for i in range(74)])
    before = datetime.now(UTC) - timedelta(hours=CLIENT_FULL_HOURS)
    venue = [
        SimpleNamespace(outcome_id=ids["b"], captured_at=near + timedelta(minutes=5),
                        tier="kalshi_candle_60m"),
        SimpleNamespace(outcome_id=ids["b"], captured_at=OPEN + timedelta(hours=3, minutes=40),
                        tier="kalshi_candle_60m"),
    ]
    async with AsyncSession(engine, expire_on_commit=False) as db:
        older = await read_older_live(db, [ids["a"], ids["b"]], before=before)
        assert older.thinned is True
        kept, unknown = await older.withhold_venue(
            db, venue, supported=lambda rows: [r for r in rows if r.bookmaker != REFUSED]
        )
    assert [r.captured_at for r in kept] == [OPEN + timedelta(hours=3, minutes=40)]
    assert [r.captured_at for r in unknown] == [near + timedelta(minutes=5)]


async def test_full_on_a_window_that_already_holds_every_capture_changes_no_live_point(
    client,
):
    """The ordinary window already reaches every capture: Full adds nothing live."""
    c, ids = client
    url = f"/api/futures/{ids['market']}/history"
    plain = (await c.get(url, params={"hours": HOURS, "top_n": 50})).json()
    full = (await c.get(url, params={"hours": HOURS, "top_n": 50, "range": "full"})).json()
    for oid in (ids["a"], ids["b"]):
        p = {o["outcome_id"]: o for o in plain["outcomes"]}[oid]
        f = {o["outcome_id"]: o for o in full["outcomes"]}[oid]
        assert [x for x in p["history"] if x.get("provenance") is None] == [
            x for x in f["history"] if x.get("provenance") is None
        ]
        assert _archive_points(p) == _archive_points(f)
    # The requested window already opens before every capture and interval.
    assert full["history_range"]["window_start_basis"] == "hours"
    assert full["history_range"]["live_thinned"] is False
    assert full["actual_hours"] == plain["actual_hours"]


async def test_a_non_kalshi_board_is_untouched(client):
    c, ids = client
    body = (
        await c.get(
            f"/api/futures/{ids['other']}/history", params={"hours": HOURS, "top_n": 50}
        )
    ).json()
    assert "archive_history" not in body
    assert not any(
        p.get("provenance") == "kalshi_archive"
        for o in body["outcomes"] for p in o["history"]
    )


async def test_before_the_migration_the_chart_is_exactly_as_it_was(client, world):
    c, ids = client
    engine, _ = world
    from app.utils import kalshi_archive_reader as reader

    with_store = (
        await c.get(
            f"/api/futures/{ids['market']}/history", params={"hours": HOURS, "top_n": 50}
        )
    ).json()
    async with engine.begin() as conn:
        for t in ("kalshi_archive_intervals", "kalshi_archive_outcome_evidence",
                  "kalshi_archive_imports"):
            await conn.execute(text(f"DROP TABLE {t}"))
    reader._presence.update(value=None, checked=0.0)
    without = (
        await c.get(
            f"/api/futures/{ids['market']}/history", params={"hours": HOURS, "top_n": 50}
        )
    ).json()
    assert "archive_history" not in without
    stripped = {
        o["outcome_id"]: [p for p in o["history"] if p.get("provenance") != "kalshi_archive"]
        for o in with_store["outcomes"]
    }
    before = {o["outcome_id"]: o["history"] for o in without["outcomes"]}
    # B (live captures) is byte-identical with and without the store.
    assert before[ids["b"]] == stripped[ids["b"]]
    # A had no line at all; with the store its line exists, so the settled
    # freeze completes it at settlement (settled means settled) and adds
    # nothing else.
    assert ids["a"] not in before
    assert [p["bookmaker"] for p in stripped[ids["a"]]] == ["settlement"]
    assert datetime.fromisoformat(stripped[ids["a"]][0]["timestamp"]) == SETTLED


async def test_a_board_whose_every_leg_has_zero_snapshots_is_drawn_on_the_timeline(
    world, monkeypatch
):
    """The #683 cohort shape at board level: no capture anywhere, archive only."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services import kalshi_archive_apply as imp
    from app.services.database import get_db, get_db_rw
    from app.utils import kalshi_archive_reader as reader

    engine, ids = world
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    monkeypatch.setitem(reader._presence, "value", None)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        async with s.begin():
            m = FuturesMarket(
                source="kalshi", external_id=EVT + "C", name=f"{LABEL} solo",
                category="game", market_tier=5, mutually_exclusive=False,
                status="resolved", resolution_date=SETTLED, event_id=ids["event"],
            )
            s.add(m)
            await s.flush()
            o = FuturesOutcome(
                market_id=m.id, external_id=f"{EVT}C-SOLO1", name="Solo 1+", rank=1,
                current_probability=0.0, is_winner=False,
                resolution_source="api_settlement",
            )
            s.add(o)
    from app.services import kalshi_archive_recovery as rec
    from tests.test_kalshi_archive_recovery_683 import FakeService

    listed = [{"ticker": f"{EVT}C-SOLO1", "event_ticker": EVT + "C",
               "status": "finalized", "open_time": OPEN.isoformat(),
               "settlement_ts": SETTLED.isoformat()}]
    svc = FakeService({EVT + "C": [(listed, None)]}, {f"{EVT}C-SOLO1": _candles(0.6)},
                      cutoff=ARCHIVE_CUTOFF.isoformat())

    async def _sleep(_s):
        return None

    import json

    report = json.loads(json.dumps(await rec.plan_archive_recovery(
        outcome_ids=[o.id], session_factory=_factory(engine),
        service_factory=lambda: svc, cooldown_reader=lambda: 0.0,
        max_wait_seconds=1.0, sleep=_sleep, pace_seconds=0.5,
    ), default=str))
    await imp.apply_archive_plan(report, expected_digest=report["plan_digest"],
                                 write=True, session_factory=_factory(engine))

    async def _get_db():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    async def _anon():
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_db_rw] = _get_db
    app.dependency_overrides[get_optional_user] = _anon
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            body = (await c.get(f"/api/futures/{m.id}/probability-timeline",
                                params={"hours": 4320, "top": 50})).json()
    finally:
        app.dependency_overrides.clear()
    assert len(body["timeline"]) == 11
    assert all(e["archive"]["Solo 1+"]["period_minutes"] == 60 for e in body["timeline"])


async def test_a_forged_plan_with_a_resealed_digest_writes_nothing(world):
    from app.services import kalshi_archive_apply as imp
    from app.utils import kalshi_archive_history as kah

    engine, ids = world
    report = await _plan(engine, [ids["a"]])
    report["plans"][0]["points"][0]["probability"] = 0.77
    report["plan_digest"] = kah.plan_digest(
        kah.PlannedPoint(**p) for p in report["plans"][0]["points"]
    )
    result = await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        session_factory=_factory(engine),
    )
    assert result["refused"] == [
        {"outcome_id": ids["a"], "reason": "points_do_not_follow_from_raw"}
    ]
    assert await _count(engine, "kalshi_archive_intervals") == 0


async def test_forecast_admission_is_re_decided_at_apply_never_inherited(world):
    """A plan claiming a LATER forecast cutoff than the event allows is demoted.

    The forger keeps the plan self-consistent (points re-classified at the
    claimed cutoff, digest resealed), so only the apply's own recomputation
    from the current event row can catch it.
    """
    from app.services import kalshi_archive_apply as imp
    from app.utils import kalshi_archive_history as kah

    engine, ids = world
    report = await _plan(engine, [ids["a"]])
    plan = report["plans"][0]
    claimed = TIPOFF + timedelta(hours=3)
    plan["forecast_cutoff"] = claimed.isoformat()
    candles, lineage = [], []
    for w in plan["windows"]:
        import json as _json

        body = _json.loads(w["raw_body"])
        candles += body["candlesticks"]
        lineage += [w["raw_sha256"]] * len(body["candlesticks"])
    points, _ = kah.classify_candles(
        outcome_id=plan["outcome_id"], ticker=plan["ticker"], candles=candles,
        period_minutes=60, settled_at=SETTLED, cutoff=claimed, cutoff_refusal=None,
        candle_lineage=lineage,
    )
    from dataclasses import asdict

    plan["points"] = [asdict(p) for p in points]
    report["plan_digest"] = kah.plan_digest(points)
    result = await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        session_factory=_factory(engine),
    )
    assert result["inserted"] == 11 and result["demoted_to_reader_only"] == 3
    async with engine.connect() as c:
        rows = dict((await c.execute(text(
            "SELECT admission_at_apply, COUNT(*) FROM kalshi_archive_intervals GROUP BY 1"
        ))).all())
        plan_claims = (await c.execute(text(
            "SELECT COUNT(*) FROM kalshi_archive_intervals WHERE admission_at_plan = 'forecast'"
        ))).scalar_one()
    assert rows == {"forecast": 6, "reader_only": 5} and plan_claims == 9


# ── the forecast lateral (switch ON only inside this test) ────────────────


def _part_a(on: bool) -> str:
    b = importlib.import_module("app.tasks.backfill_winners")
    src = (Path(b.__file__)).read_text()
    churn = re.search(r'    _WOULD_CHURN = """(.*?)"""', src, re.S).group(1)
    return b._part_a_calibration_sql(churn, b._part_a_value_sql(on), archive_forecast=on)


async def _run_part_a(engine, on):
    async with engine.begin() as c:
        await c.execute(text("UPDATE futures_outcomes SET calibration_probability = NULL"))
        await c.execute(text(_part_a(on)), {"cursor": 0, "batch": 1000})
    async with engine.connect() as c:
        return dict(
            (
                await c.execute(
                    text("SELECT id, calibration_probability FROM futures_outcomes")
                )
            ).all()
        )


async def test_the_forecast_lateral_admits_only_revalidated_pregame_intervals(world):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    report = await _plan(engine, [ids["a"], ids["b"]])
    await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        session_factory=_factory(engine),
    )
    off = await _run_part_a(engine, False)
    assert off[ids["a"]] is None  # switch off: the archive is invisible
    on = await _run_part_a(engine, True)
    # A: the last interval wholly before tip-off ends at +6h, close 0.36.
    assert float(on[ids["a"]]) == pytest.approx(0.36)
    # B: its own live pregame capture still wins over the archive.
    assert float(on[ids["b"]]) == pytest.approx(0.555)

    async with engine.begin() as c:  # the event's start moves after the apply
        await c.execute(text("UPDATE events SET commence_time = commence_time + interval '1 minute'"))
    moved = await _run_part_a(engine, True)
    assert moved[ids["a"]] is None  # evidence voided at consumption


# ── #683 first attended import rail: operational bounds on a REAL server ──
#
# PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
# real recoverable older probability journey on web and native, with explicit
# archive provenance. These cases hold the bounds the first attended import
# relies on (``app.services.kalshi_archive_bounds``) where only PostgreSQL can:
# startup parameters across COMMIT and reconnect, the 500 ms lock bound, the
# FOR SHARE identity fence, and receipts for COMMITs whose answer was lost.


def _archive_url(monkeypatch):
    """Point the task engine (and so ``archive_session``) at this test database."""
    import app.tasks.base as base

    monkeypatch.setattr(base, "DATABASE_URL", DB_URL)


async def _budget(session):
    rows = (await session.execute(text(
        "SELECT name, setting FROM pg_settings"
        " WHERE name IN ('statement_timeout', 'lock_timeout')"
    ))).all()
    pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
    return dict(rows), pid


async def test_the_archive_session_carries_both_bounds_across_commit_and_reconnect(
    world, monkeypatch
):
    from app.services.kalshi_archive_bounds import archive_session
    from app.tasks.base import get_task_session

    _archive_url(monkeypatch)
    want = {"statement_timeout": "10000", "lock_timeout": "500"}
    async with archive_session() as s:
        first, pid1 = await _budget(s)
        await s.commit()
        after_commit, _ = await _budget(s)
        await (await s.connection()).invalidate()  # the pool must open a NEW backend
        await s.rollback()
        after_reconnect, pid2 = await _budget(s)
    assert first == after_commit == after_reconnect == want
    assert pid1 != pid2, "the reconnect case must really be a new connection"
    # Control: the house task session is untouched (no lock bound, resting statement bound).
    async with get_task_session() as s:
        house, _ = await _budget(s)
    assert house["lock_timeout"] == "0" and house["statement_timeout"] != "10000"


async def test_an_unarmed_session_is_refused_before_its_first_statement(world):
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.kalshi_archive_bounds import (
        ArchiveSessionUnarmed,
        verify_session_budget,
    )

    engine, _ = world
    async with AsyncSession(engine) as s:
        with pytest.raises(ArchiveSessionUnarmed):
            await verify_session_budget(s)


async def test_the_archive_lock_bound_gives_up_after_500ms(world, monkeypatch):
    import time

    from sqlalchemy.exc import DBAPIError

    from app.services.kalshi_archive_bounds import archive_session

    engine, ids = world
    _archive_url(monkeypatch)
    async with engine.connect() as holder:
        await holder.begin()
        await holder.execute(
            text("SELECT id FROM futures_outcomes WHERE id = :a FOR UPDATE"), {"a": ids["a"]}
        )
        t0 = time.monotonic()
        with pytest.raises(DBAPIError) as info:
            async with archive_session() as s:
                await s.execute(
                    text("SELECT id FROM futures_outcomes WHERE id = :a FOR UPDATE"),
                    {"a": ids["a"]},
                )
        waited = time.monotonic() - t0
        await holder.rollback()
    assert "lock timeout" in str(info.value).lower() or "55P03" in str(info.value)
    assert 0.4 <= waited < 5.0


async def test_the_default_factory_applies_through_the_bounded_session(world, monkeypatch):
    """Control for the fence cases: the production factory, real startup bounds, a clean apply."""
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    _archive_url(monkeypatch)
    report = await _plan(engine, [ids["a"]])
    done = await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        max_outcomes=1, max_points=26,
    )
    assert done["status"] == "applied" and done["inserted"] == 11
    assert done["committed_outcomes"][0]["inserted_ids"] == done["outcomes"][0]["inserted_ids"]
    assert done["import_row"] == "applied" and done["uncertain_commits"] == []


async def test_an_outcome_whose_row_is_being_written_is_refused_within_the_lock_bound(
    world, monkeypatch
):
    import time

    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    _archive_url(monkeypatch)
    report = await _plan(engine, [ids["a"]])
    async with engine.connect() as writer:
        await writer.begin()
        await writer.execute(
            text("UPDATE futures_outcomes SET name = name WHERE id = :a"), {"a": ids["a"]}
        )
        t0 = time.monotonic()
        result = await imp.apply_archive_plan(
            report, expected_digest=report["plan_digest"], write=True,
            max_outcomes=1, max_points=26,
        )
        waited = time.monotonic() - t0
        await writer.rollback()
    assert waited < 5.0
    assert result["status"] == "partial" and result["inserted"] == 0
    [err] = result["errors"]
    assert err["outcome_id"] == ids["a"] and err["committed"] is False
    assert "lock" in err["error"].lower()
    assert await _count(engine, "kalshi_archive_intervals") == 0
    assert await _count(engine, "kalshi_archive_outcome_evidence") == 0


async def test_the_fence_holds_identity_from_the_fingerprint_check_to_the_commit(world):
    """While the outcome's transaction is open, an identity edit must wait for it."""
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    report = await _plan(engine, [ids["a"]])
    seen: dict = {}

    class Probing(AsyncSession):
        async def execute(self, statement, *a, **k):
            out = await super().execute(statement, *a, **k)
            if "FROM events e" in str(statement) and "FOR SHARE" in str(statement):
                for table, sql in (
                    ("events", "UPDATE events SET commence_time = commence_time"
                               " - interval '1 hour' WHERE id = :id"),
                    ("futures_outcomes", "UPDATE futures_outcomes SET resolution_source"
                                         " = 'x' WHERE id = :id"),
                ):
                    async with engine.connect() as other:
                        await other.execute(text("SET lock_timeout = '300ms'"))
                        try:
                            await other.execute(
                                text(sql),
                                {"id": ids["event"] if table == "events" else ids["a"]},
                            )
                            seen[table] = "changed"
                        except DBAPIError as e:
                            seen[table] = (
                                "blocked" if "55P03" in str(e) or "lock timeout" in str(e).lower()
                                else str(e)[:80]
                            )
            return out

    result = await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        session_factory=lambda: Probing(engine, expire_on_commit=False),
    )
    assert seen == {"events": "blocked", "futures_outcomes": "blocked"}
    assert result["status"] == "applied" and result["inserted"] == 11


def _losing_commit(engine, *, when, really_commit):
    """Sessions whose COMMIT for ``when`` loses its acknowledgement.

    ``really_commit`` decides whether the server applied it first: the receipt
    must read the same either way, because the client cannot tell.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    class Losing(AsyncSession):
        wrote = False

        async def execute(self, statement, *a, **k):
            if when in str(statement):
                self.wrote = True
            return await super().execute(statement, *a, **k)

        async def commit(self):
            if not self.wrote:
                return await super().commit()
            if really_commit:
                await super().commit()
            else:
                await super().rollback()
            raise ConnectionResetError("connection lost before the COMMIT answer")

    return lambda: Losing(engine, expire_on_commit=False)


@pytest.mark.parametrize("really_commit", [True, False])
async def test_a_lost_outcome_commit_ack_is_uncertain_never_nothing_never_retried(
    world, really_commit
):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    report = await _plan(engine, [ids["a"], ids["b"]])
    result = await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        session_factory=_losing_commit(
            engine, when="ON CONFLICT ON CONSTRAINT uq_kai_interval",
            really_commit=really_commit,
        ),
    )
    assert result["stopped"] == f"commit_unacknowledged:{ids['a']}"
    assert result["status"] == "partial" and result["committed_outcomes"] == []
    [u] = result["uncertain_commits"]
    assert u["outcome_id"] == ids["a"] and len(u["inserted_ids"]) == 11
    assert result["readback_owed"]["durability"] == "unknown"
    assert result["import_row"] == "applying"  # FINISH never ran; B never tried
    durable = await _count(engine, "kalshi_archive_intervals")
    assert durable == (11 if really_commit else 0)
    assert await _count(engine, "kalshi_archive_outcome_evidence") == (1 if really_commit else 0)
    # The disposition: the read-only restore dry-run tells which world this is.
    held = await imp.restore_archive_import(result["import_key"], session_factory=_factory(engine))
    assert held["refused"] == "import_still_applying"
    told = await imp.restore_archive_import(
        result["import_key"], allow_applying=True, session_factory=_factory(engine)
    )
    if really_commit:
        assert told["refused"] is None and told["would_delete"] == 11
    else:
        assert told["refused"] is None and told["would_delete"] == 0


async def test_an_error_after_a_commit_still_reports_the_rows_durable(world):
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    report = await _plan(engine, [ids["a"]])

    class BrokenReadback(AsyncSession):
        async def execute(self, statement, *a, **k):
            if "SELECT id FROM kalshi_archive_intervals" in str(statement):
                raise ConnectionResetError("readback connection dropped")
            return await super().execute(statement, *a, **k)

    result = await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        session_factory=lambda: BrokenReadback(engine, expire_on_commit=False),
    )
    [err] = result["errors"]
    assert err["committed"] is True and len(err["inserted_ids"]) == 11
    assert result["gained_history_outcome_ids"] == [ids["a"]]
    assert result["status"] == "partial" and result["import_row"] == "partial"
    assert await _count(engine, "kalshi_archive_intervals") == 11


async def test_a_lost_restore_ack_reports_unknown_and_a_readback_settles_it(world):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    done = await _applied(engine, ids)
    lost = await imp.restore_archive_import(
        done["import_key"], write=True,
        session_factory=_losing_commit(
            engine, when="DELETE FROM kalshi_archive_intervals", really_commit=True
        ),
    )
    assert lost["refused"] == "commit_unacknowledged" and lost["deleted"] == "unknown"
    assert len(lost["uncertain_commits"][0]["would_delete_ids"]) == 11
    again = await imp.restore_archive_import(done["import_key"], session_factory=_factory(engine))
    assert again["refused"] == "already_restored"
    assert await _count(engine, "kalshi_archive_intervals") == 0


async def test_a_partial_plan_writes_its_subset_but_is_never_applied(world):
    import json as _json

    from app.services import kalshi_archive_apply as imp
    from app.services import kalshi_archive_recovery as rec
    from tests.test_kalshi_archive_recovery_683 import FakeService

    engine, ids = world
    listed = [
        {"ticker": t, "event_ticker": EVT, "status": "finalized",
         "open_time": OPEN.isoformat(), "settlement_ts": SETTLED.isoformat()}
        for t in (TA, TB)
    ]

    async def _sleep(_s):
        return None

    svc = FakeService({EVT: [(listed, None)]}, {TA: _candles(0.30), TB: _candles(0.50)},
                      cutoff=ARCHIVE_CUTOFF.isoformat())
    # cutoff + listing + A's one window: B is held by the request budget.
    report = _json.loads(_json.dumps(await rec.plan_archive_recovery(
        outcome_ids=[ids["a"], ids["b"]], session_factory=_factory(engine),
        service_factory=lambda: svc, cooldown_reader=lambda: 0.0, sleep=_sleep,
        pace_seconds=0.5, max_requests=3,
    ), default=str))
    assert report["terminal"] == "partial" and report["budget_stop"] == "requests"
    result = await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        session_factory=_factory(engine),
    )
    assert result["inserted"] == 11 and result["status"] == "partial"
    assert result["incomplete_reasons"] == [
        "plan_terminal:partial", "plan_held_outcome", "plan_budget_stop:requests",
    ]
    async with engine.connect() as c:
        status = (await c.execute(text("SELECT status FROM kalshi_archive_imports"))).scalar_one()
    assert status == "partial"


async def test_a_zero_point_plan_is_never_applied(world):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    await _applied(engine, ids)
    again = await _plan(engine, [ids["a"]])
    assert again["importable_points"] == 0
    result = await imp.apply_archive_plan(
        again, expected_digest=again["plan_digest"], session_factory=_factory(engine)
    )
    assert result["status"] == "partial" and result["inserted"] == 0
    assert result["incomplete_reasons"] == ["plan_has_no_importable_points"]


async def test_the_import_cli_runs_the_first_sample_profile_on_a_real_server(
    world, monkeypatch, tmp_path, capsys
):
    import json as _json

    engine, ids = world
    _archive_url(monkeypatch)
    report = await _plan(engine, [ids["a"]])
    plan = tmp_path / "P.json"
    plan.write_text(_json.dumps(report))
    path = Path(__file__).resolve().parents[2] / "scripts" / "kalshi_archive_import.py"
    spec = importlib.util.spec_from_file_location("kalshi_archive_import", path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    import asyncio

    base = ["apply", "--plan", str(plan), "--expected-digest", report["plan_digest"],
            "--max-outcomes", "1", "--max-points", "26", "--deadline", "30"]
    # The CLI owns its own event loop; run it off this test's loop.
    dry = await asyncio.to_thread(cli.main, base + ["--output", str(tmp_path / "dry.json")])
    assert dry == 0
    receipt = _json.loads((tmp_path / "dry.json").read_text())
    assert receipt["status"] == "applied" and receipt["mode"] == "dry_run"
    assert receipt["outcomes"][0]["would_insert"] == 11 and receipt["incomplete_reasons"] == []
    assert await _count(engine, "kalshi_archive_intervals") == 0
    # The attended write without the reviewed versions is refused whole (exit 2):
    # it never falls back to the fingerprint-only fence.
    capsys.readouterr()
    bare = await asyncio.to_thread(
        cli.main, base + ["--write", "--output", str(tmp_path / "bare.json")]
    )
    assert bare == 2 and "input_versions_missing" in capsys.readouterr().err
    assert await _count(engine, "kalshi_archive_imports") == 0
    doc, digest = await _reviewed(engine, report)
    versions = tmp_path / "V.json"
    versions.write_text(_json.dumps(doc))
    attended = ["--input-versions", str(versions), "--expected-input-digest", digest]
    wrote = await asyncio.to_thread(
        cli.main, base + attended + ["--write", "--output", str(tmp_path / "write.json")]
    )
    assert wrote == 0 and await _count(engine, "kalshi_archive_intervals") == 11
    assert _json.loads((tmp_path / "write.json").read_text())["input_fence"] == "rowversion"
    key = _json.loads((tmp_path / "write.json").read_text())["import_key"]
    capsys.readouterr()
    restore_dry = await asyncio.to_thread(
        cli.main, ["restore", "--import-key", key, "--deadline", "30"]
    )
    assert restore_dry == 0
    assert _json.loads(capsys.readouterr().out)["would_delete"] == 11


# ── the attended input fence: reviewed identity AND row versions ──────────
# PACKET (683-stored-identity-delta-20261016): "a later compared fingerprint OR
# ANY ROWVERSION change refuses". Each drift case below leaves the input
# fingerprint unchanged and proves it, then shows the fingerprint-only control
# writing the same drifted outcome — the gap this fence closes.

REVIEW_SQL = text(
    """
    SELECT fo.id AS outcome_id, fo.external_id AS ticker, fm.external_id AS event_ticker,
           fo.market_id AS market_id, fm.event_id AS event_id,
           fo.xmin::text AS outcome_xmin, fm.xmin::text AS market_xmin,
           e.xmin::text AS event_xmin
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    LEFT JOIN events e ON e.id = fm.event_id
    WHERE fo.id = ANY(:ids)
    ORDER BY fo.id
    """
)


async def _reviewed(engine, report, **over):
    """What the operator's reviewed read returned, sealed and bound to ``report``."""
    from app.services import kalshi_archive_apply as imp

    plans = {int(p["outcome_id"]): p for p in report["plans"]}
    async with engine.connect() as c:
        rows = (await c.execute(REVIEW_SQL, {"ids": sorted(plans)})).mappings().all()
    outcomes = [
        {**dict(r), "input_fingerprint": plans[r["outcome_id"]]["input_fingerprint"], **over}
        for r in rows
    ]
    doc = imp.seal_input_versions(report["plan_digest"], outcomes)
    return doc, doc["digest"]


async def _current_fingerprint(engine, oid):
    from app.services import kalshi_archive_apply as imp
    from app.utils.kalshi_archive_history import input_fingerprint

    async with engine.connect() as c:
        row = (await c.execute(text(imp.CURRENT_INPUT_SQL), {"oid": oid})).first()
    return input_fingerprint(row)


async def _attended(engine, report, doc, digest, **kw):
    from app.services import kalshi_archive_apply as imp

    return await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        input_versions=doc, expected_input_digest=digest, require_input_versions=True,
        session_factory=kw.pop("session_factory", _factory(engine)), **kw,
    )


async def _nothing_of(engine, oid):
    async with engine.connect() as c:
        for table in ("kalshi_archive_intervals", "kalshi_archive_outcome_evidence"):
            n = (await c.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE outcome_id = :o"), {"o": oid}
            )).scalar_one()
            assert n == 0, table


async def test_the_attended_fence_applies_a_stable_reviewed_outcome(world):
    engine, ids = world
    report = await _plan(engine, [ids["a"], ids["b"]])
    doc, digest = await _reviewed(engine, report)
    assert all(o["event_xmin"] for o in doc["outcomes"])  # a real event version each
    done = await _attended(engine, report, doc, digest, max_outcomes=2, max_points=26)
    assert done["status"] == "applied" and done["inserted"] == 22
    assert done["input_fence"] == "rowversion" and done["refused"] == []
    assert done["input_versions_digest"] == digest
    async with engine.connect() as c:
        rep = (await c.execute(text("SELECT report FROM kalshi_archive_imports"))).scalar_one()
    assert rep["input_fence"] == "rowversion"


@pytest.mark.parametrize(
    "row,sql,reason",
    [
        ("outcome", "UPDATE futures_outcomes SET current_probability = 0.25 WHERE id = :a",
         "input_version_drift:outcome"),
        # An identical-content UPDATE is still a new row version.
        ("market", "UPDATE futures_markets SET name = name WHERE id = :m",
         "input_version_drift:market"),
        ("event", "UPDATE events SET home_score = 71, away_score = 64 WHERE id = :e",
         "input_version_drift:event"),
    ],
)
async def test_a_non_fingerprint_change_with_an_unchanged_fingerprint_is_refused(
    world, row, sql, reason
):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    report = await _plan(engine, [ids["a"]])
    doc, digest = await _reviewed(engine, report)
    before = await _current_fingerprint(engine, ids["a"])
    async with engine.begin() as c:
        await c.execute(text(sql), {"a": ids["a"], "m": ids["market"], "e": ids["event"]})
    after = await _current_fingerprint(engine, ids["a"])
    assert before == after == report["plans"][0]["input_fingerprint"]

    result = await _attended(engine, report, doc, digest)
    assert result["refused"] == [{"outcome_id": ids["a"], "reason": reason}]
    assert result["status"] == "partial" and result["inserted"] == 0
    [out] = result["outcomes"]
    assert out["input_fence"]["expected"][f"{row}_xmin"] != out["input_fence"]["observed"][f"{row}_xmin"]
    await _nothing_of(engine, ids["a"])
    async with engine.connect() as c:
        imp_row = (await c.execute(text("SELECT status, report FROM kalshi_archive_imports"))).one()
    assert imp_row.status == "partial"
    assert imp_row.report["refused"] == [{"outcome_id": ids["a"], "reason": reason}]

    # Control: the fingerprint-only fence writes this very drifted outcome.
    legacy = await imp.apply_archive_plan(
        report, expected_digest=report["plan_digest"], write=True,
        session_factory=_factory(engine),
    )
    assert legacy["input_fence"] == "fingerprint_only"
    assert legacy["status"] == "applied" and legacy["inserted"] == 11


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("UPDATE futures_outcomes SET external_id = external_id || 'X' WHERE id = :a",
         "input_identity_drift"),
        ("UPDATE events SET commence_time = commence_time - interval '2 hours' WHERE id = :e",
         "input_drift"),
    ],
)
async def test_identity_and_fingerprint_changes_are_refused_by_the_fence(world, sql, reason):
    engine, ids = world
    report = await _plan(engine, [ids["a"]])
    doc, digest = await _reviewed(engine, report)
    async with engine.begin() as c:
        await c.execute(text(sql), {"a": ids["a"], "e": ids["event"]})
    result = await _attended(engine, report, doc, digest)
    assert result["refused"] == [{"outcome_id": ids["a"], "reason": reason}]
    await _nothing_of(engine, ids["a"])


async def test_a_document_naming_another_stored_identity_is_refused_in_the_transaction(world):
    engine, ids = world
    report = await _plan(engine, [ids["a"]])
    doc, digest = await _reviewed(engine, report, market_id=ids["other"])
    result = await _attended(engine, report, doc, digest)
    assert result["refused"] == [{"outcome_id": ids["a"], "reason": "input_identity_drift"}]
    await _nothing_of(engine, ids["a"])


@pytest.mark.parametrize("case", ["other_plan", "typed_digest", "tampered", "missing", "event_wildcard"])
async def test_a_loose_missing_or_invalid_document_refuses_before_anything_is_written(
    world, case
):
    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    report = await _plan(engine, [ids["a"]])
    doc, digest = await _reviewed(engine, report)
    if case == "other_plan":
        other = await _plan(engine, [ids["b"]])
        doc, digest = await _reviewed(engine, other)  # sealed, but for another plan
        want = "input_versions_plan_mismatch"
    elif case == "typed_digest":
        digest = "0" * 64
        want = "expected_input_digest_mismatch"
    elif case == "tampered":
        doc["outcomes"][0]["outcome_xmin"] = "1"  # edited, not resealed
        want = "input_versions_digest_mismatch"
    elif case == "missing":
        doc, digest = None, None
        want = "input_versions_missing"
    else:
        # A present event with no version: never a wildcard, even when sealed.
        doc, digest = await _reviewed(engine, report, event_xmin=None)
        want = "input_versions_malformed:event"
    with pytest.raises(imp.PlanRefused) as info:
        await _attended(engine, report, doc, digest)
    assert info.value.reason == want
    for t in ("kalshi_archive_imports", "kalshi_archive_intervals",
              "kalshi_archive_outcome_evidence"):
        assert await _count(engine, t) == 0, t


async def test_a_market_with_no_event_is_fenced_explicitly(world):
    engine, ids = world
    async with engine.begin() as c:
        await c.execute(text("UPDATE futures_markets SET event_id = NULL WHERE id = :m"),
                        {"m": ids["market"]})
    report = await _plan(engine, [ids["a"]])
    doc, digest = await _reviewed(engine, report)
    assert doc["outcomes"][0]["event_id"] is None and doc["outcomes"][0]["event_xmin"] is None
    done = await _attended(engine, report, doc, digest)
    assert done["status"] == "applied" and done["inserted"] == 11


async def test_an_event_attached_after_a_no_event_review_is_refused(world):
    engine, ids = world
    async with engine.begin() as c:
        await c.execute(text("UPDATE futures_markets SET event_id = NULL WHERE id = :m"),
                        {"m": ids["market"]})
    report = await _plan(engine, [ids["a"]])
    doc, digest = await _reviewed(engine, report)
    async with engine.begin() as c:
        await c.execute(text("UPDATE futures_markets SET event_id = :e WHERE id = :m"),
                        {"e": ids["event"], "m": ids["market"]})
    result = await _attended(engine, report, doc, digest)
    assert result["refused"] == [{"outcome_id": ids["a"], "reason": "input_identity_drift"}]
    await _nothing_of(engine, ids["a"])


async def test_a_no_event_expectation_is_not_a_wildcard_for_a_present_event(world):
    engine, ids = world
    report = await _plan(engine, [ids["a"]])  # the market HAS an event
    doc, digest = await _reviewed(engine, report, event_id=None, event_xmin=None)
    result = await _attended(engine, report, doc, digest)
    assert result["refused"] == [{"outcome_id": ids["a"], "reason": "input_identity_drift"}]
    await _nothing_of(engine, ids["a"])


async def test_the_fence_holds_every_row_version_from_the_comparison_to_the_commit(world):
    """Inside the outcome's transaction, a non-fingerprint write to any fenced row waits."""
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services import kalshi_archive_apply as imp

    engine, ids = world
    report = await _plan(engine, [ids["a"]])
    doc, digest = await _reviewed(engine, report)
    seen: dict = {}

    class Probing(AsyncSession):
        async def execute(self, statement, *a, **k):
            out = await super().execute(statement, *a, **k)
            # After the comparison, before the evidence row: the write window.
            if statement is imp.EVIDENCE_SQL and not seen:
                for table, sql, key in (
                    ("futures_outcomes", "UPDATE futures_outcomes SET current_probability = 0.2"
                                         " WHERE id = :id", "a"),
                    ("futures_markets", "UPDATE futures_markets SET name = name WHERE id = :id",
                     "market"),
                    ("events", "UPDATE events SET home_score = 1 WHERE id = :id", "event"),
                ):
                    async with engine.connect() as other:
                        await other.execute(text("SET lock_timeout = '300ms'"))
                        try:
                            await other.execute(text(sql), {"id": ids[key]})
                            seen[table] = "changed"
                        except DBAPIError as e:
                            seen[table] = (
                                "blocked" if "55P03" in str(e) or "lock timeout" in str(e).lower()
                                else str(e)[:80]
                            )
            return out

    result = await _attended(
        engine, report, doc, digest,
        session_factory=lambda: Probing(engine, expire_on_commit=False),
    )
    assert seen == {"futures_outcomes": "blocked", "futures_markets": "blocked",
                    "events": "blocked"}
    assert result["status"] == "applied" and result["inserted"] == 11


@pytest.mark.parametrize("writer_commits", [True, False])
async def test_the_version_is_compared_on_the_locked_row_not_a_preflight_read(
    world, writer_commits
):
    """A writer holding the outcome row while the apply waits for its lock.

    When the writer commits, the row the lock returns is the NEW version and
    the outcome is refused; a comparison made before the lock (on the old,
    still-committed version) would have written it. When the writer rolls
    back, the reviewed version stands and the outcome applies (control).
    """
    import asyncio

    engine, ids = world
    report = await _plan(engine, [ids["a"]])
    doc, digest = await _reviewed(engine, report)
    async with engine.connect() as writer:
        await writer.begin()
        await writer.execute(
            text("UPDATE futures_outcomes SET current_probability = 0.33 WHERE id = :a"),
            {"a": ids["a"]},
        )
        task = asyncio.create_task(_attended(engine, report, doc, digest))
        async with engine.connect() as watch:
            for _ in range(200):
                waiting = (await watch.execute(text(
                    "SELECT COUNT(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                    " AND query LIKE '%FOR SHARE OF fo, fm%'"
                ))).scalar_one()
                await watch.rollback()  # pg_stat_activity is snapshotted per transaction
                if waiting or task.done():
                    break
                await asyncio.sleep(0.025)
        assert waiting == 1 and not task.done(), "the apply must be waiting on the row lock"
        await (writer.commit() if writer_commits else writer.rollback())
        result = await asyncio.wait_for(task, 10)
    if writer_commits:
        assert result["refused"] == [
            {"outcome_id": ids["a"], "reason": "input_version_drift:outcome"}
        ]
        await _nothing_of(engine, ids["a"])
    else:
        assert result["status"] == "applied" and result["inserted"] == 11
