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


# ── the two chart routes ──────────────────────────────────────────────────


@pytest.fixture
async def client(world, monkeypatch):
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
