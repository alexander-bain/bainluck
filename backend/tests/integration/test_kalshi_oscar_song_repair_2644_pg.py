"""#2644 — the Oscars Best Original Song row's exact, reversible lifecycle repair, on a real Postgres.

PILLAR: TRUTH. SHIP: the decided 2026 Best Original Song question stops
appearing Open with a December resolution date, through an exact-id reversible
lifecycle correction.

Row 109548 is seeded as the public detail served it (2026-10-15: open,
resolution_date 2026-12-31T15:00Z, updated 2026-06-27). The plan runs the
MERGED archive walk over the RETAINED venue bytes through #2722's rail, pointed
at this channel. What only Postgres can say: the whole-row CAS, the after-image
undo, the runtime backup DDL, that the two channels never touch each other's
rows, that legs/prices/history never move, and that the budgets reach the wire.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import importlib.util
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2644 Oscars repair",
    ),
]

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 17, 16, 0, tzinfo=timezone.utc)
OSCAR = 109548
TICKER = "KXOSCARSONG-26"
OUTCOMES = [(1598201, "KXOSCARSONG-26-GOL", "Golden", 0.42), (1598202, "KXOSCARSONG-26-AAY", "As Alive As You Need Me To Be", 0.31)]
# The nine's seed, as #2722's own gate holds it, for the cross-channel arms.
NINE = [
    (109776, "KXTXPRIMARY-04R26", "2027-11-03T15:00:00+00:00", 2, "2026-06-23T18:40:05+00:00", "2027-11-03T15:00:00+00:00"),
    (110337, "KXWALESPARLIAMENT-26MAY07", "2027-05-07T14:00:00+00:00", 2, "2026-05-11T18:41:56+00:00", "2027-05-07T14:00:00+00:00"),
    (110749, "KXPGAAWARDS-26-LIM", "2027-02-28T15:00:00+00:00", 3, "2026-09-25T03:06:56+00:00", "2027-02-28T15:00:00+00:00"),
    (925648, "KXPAXTONPRIMARYCOUNTIES-26", "2027-03-03T15:00:00+00:00", 2, "2026-07-21T05:54:31+00:00", "2027-03-03T15:00:00+00:00"),
    (925724, "KXTALARICOPRIMARYCOUNTIES-26", "2027-03-03T15:00:00+00:00", 2, "2026-06-27T00:40:00+00:00", "2027-03-03T15:00:00+00:00"),
    (1631094, "KXINPRIMARY-01D26", "2027-11-03T15:00:00+00:00", 2, "2026-07-19T09:06:08+00:00", "2027-11-03T15:00:00+00:00"),
    (3452978, "KXNEXTTEAMNFL-26THENDRICKSON", "2026-12-01T04:59:00+00:00", 5, "2026-06-30T17:07:16+00:00", "2026-12-08T15:00:00+00:00"),
    (11757847, "KXPRIMARYTURNOUT-SENATETXR26", "2026-06-12T20:46:58+00:00", 2, "2026-08-12T16:49:04+00:00", "2027-05-26T14:00:00+00:00"),
    (54069617, "KXDNCAUTOPSY-26", "2026-05-21T14:40:24+00:00", 2, "2026-07-18T14:49:03+00:00", "2026-11-10T15:00:00+00:00"),
]
NINE_IDS = [r[0] for r in NINE]
ALL_IDS = [OSCAR] + NINE_IDS
HEAVY = {"HEROKU_APP_NAME": "bainluck-heavy"}


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _oscar():
    return _load("repair_2644_oscar_song")


def _nine():
    return _load("repair_2722_archived_nine")


async def _clear(s):
    for table in ("backup_2644_oscar_song", "backup_2722_archived_nine"):
        await s.execute(text(f"DROP TABLE IF EXISTS {table}"))
    await s.execute(text(
        "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
        "(SELECT id FROM futures_outcomes WHERE market_id = ANY(CAST(:ids AS bigint[])))"),
        {"ids": ALL_IDS})
    await s.execute(text("DELETE FROM futures_outcomes WHERE market_id = ANY(CAST(:ids AS bigint[]))"),
                    {"ids": ALL_IDS})
    await s.execute(text("DELETE FROM futures_markets WHERE id = ANY(CAST(:ids AS bigint[]))"),
                    {"ids": ALL_IDS})


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await _clear(s)
        await s.execute(
            text(
                "INSERT INTO futures_markets (id, external_id, name, source, status, "
                "category, mutually_exclusive, market_type, llm_sport_category, volume, "
                "market_tier, commence_time, resolution_date, updated_at, created_at) VALUES "
                "(:id, :xid, '2026 Oscar for Best Music (Original Song)?', 'kalshi', 'open', "
                "'entertainment', true, 'field', 'entertainment', 10, NULL, "
                "CAST(:ct AS timestamptz), CAST(:rd AS timestamptz), CAST(:ua AS timestamptz), "
                "CAST(:ca AS timestamptz))"
            ),
            {"id": OSCAR, "xid": TICKER,
             "ct": datetime.fromisoformat("2026-01-22T21:59:21.089647+00:00"),
             "rd": datetime.fromisoformat("2026-12-31T15:00:00+00:00"),
             "ua": datetime.fromisoformat("2026-06-27T00:40:00.088647+00:00"),
             "ca": datetime.fromisoformat("2026-02-19T01:21:59.844113+00:00")},
        )
        for oid, xid, name, p in OUTCOMES:
            await s.execute(
                text(
                    "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
                    "opening_probability, calibration_probability, is_winner, "
                    "resolution_source, volume) VALUES "
                    "(:id, :mid, :xid, :nm, :p, :p, false, NULL, 10)"
                ),
                {"id": oid, "mid": OSCAR, "xid": xid, "nm": name, "p": p},
            )
            await s.execute(
                text(
                    "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                    "probability, reading_count, last_price, yes_bid, yes_ask, "
                    "captured_at) VALUES (:oid, 'kalshi', :p, 1, :p, :p, :p, "
                    "CAST(:at AS timestamptz))"
                ),
                {"oid": oid, "p": p, "at": datetime(2026, 3, 12, 6, 45, 17, tzinfo=timezone.utc)},
            )
        for mid, ticker, commence, tier, updated, rd in NINE:
            await s.execute(
                text(
                    "INSERT INTO futures_markets (id, external_id, name, source, status, "
                    "category, mutually_exclusive, market_type, llm_sport_category, volume, "
                    "market_tier, commence_time, resolution_date, updated_at) VALUES "
                    "(:id, :xid, :xid, 'kalshi', 'open', 'politics', true, 'binary', "
                    "'politics', 10, :tier, CAST(:ct AS timestamptz), CAST(:rd AS timestamptz), "
                    "CAST(:ua AS timestamptz))"
                ),
                {"id": mid, "xid": ticker, "tier": tier,
                 "ct": datetime.fromisoformat(commence), "rd": datetime.fromisoformat(rd),
                 "ua": datetime.fromisoformat(updated)},
            )
        await s.commit()
        yield s
        await s.rollback()
        await _clear(s)
        await s.commit()
    await engine.dispose()


async def _rows(s, ids=None) -> dict:
    rows = (await s.execute(
        text("SELECT id, to_jsonb(fm) FROM futures_markets fm "
             "WHERE id = ANY(CAST(:ids AS bigint[])) ORDER BY id"), {"ids": ids or ALL_IDS},
    )).all()
    await s.rollback()
    return {r[0]: (r[1] if isinstance(r[1], dict) else json.loads(r[1])) for r in rows}


async def _legs_and_history(s) -> tuple:
    legs = (await s.execute(text(
        "SELECT to_jsonb(o) FROM futures_outcomes o WHERE market_id = :m ORDER BY id"),
        {"m": OSCAR})).scalars().all()
    hist = (await s.execute(text(
        "SELECT to_jsonb(f) FROM futures_odds_snapshots f WHERE outcome_id IN "
        "(SELECT id FROM futures_outcomes WHERE market_id = :m) ORDER BY id"),
        {"m": OSCAR})).scalars().all()
    await s.rollback()
    return legs, hist


async def _plan(s, mod=None, evidence=None):
    mod = mod or _oscar()
    plan = await mod.build_plan(s, evidence or mod.load_evidence(), now=NOW)
    return mod, plan, mod.plan_digest(plan["planned"])


async def _backup_apply(s, mod, plan, digest):
    assert await mod.rail.backup(s, plan["planned"], digest, table=mod.BACKUP_TABLE) == []
    await s.commit()
    out = await mod.rail.apply(s, digest, table=mod.BACKUP_TABLE)
    await s.commit()
    return out


async def _restore(s, mod):
    out = await mod.rail.restore_report(s, table=mod.BACKUP_TABLE)
    await s.commit()
    return out


def _evidence_with(mod, *, archive=None, live=None):
    ev = mod.load_evidence()
    body = json.loads(ev[TICKER]["archive"])
    if archive:
        body = archive(copy.deepcopy(body))
    lv = json.loads(ev[TICKER]["live"])
    if live:
        lv = live(copy.deepcopy(lv))
    return {TICKER: {"archive": json.dumps(body).encode(), "live": json.dumps(lv).encode()}}


def _args(**kw):
    return argparse.Namespace(**{"backup": False, "apply": False, "digest": "",
                                 "restore": False, "status": False, **kw})


# ── the plan is the walk, held to the reviewed transition ────────────────────


async def test_the_plan_is_the_merged_walk_settling_the_row_as_006(session):
    mod, plan, digest = await _plan(session)
    assert plan["stop"] == [] and plan["no_op"] == []
    assert plan["stop_not_settled_from_archive"] == [] and plan["voids_reported_not_written"] == []
    assert plan["walk_stats"]["venue_settled_from_archive"] == 1
    assert plan["walk_stats"]["archive_requests"] == 1
    [entry] = plan["planned"]
    assert mod.rail._values(entry) == mod.REVIEWED_WRITE == {
        "market_id": 109548, "ticker": "KXOSCARSONG-26",
        "resolution_date": "2026-03-16T02:11:07+00:00",
        "expiration_time": "2026-12-31T15:00:00+00:00", "venue_settled": True,
    }
    before = json.loads(entry["approved_before"])
    assert before["id"] == OSCAR and before["status"] == "open"
    assert datetime.fromisoformat(before["resolution_date"]) == datetime(2026, 12, 31, 15, tzinfo=timezone.utc)


async def test_the_default_run_is_a_plan_with_no_ddl_and_no_write(session, monkeypatch):
    _real_db_task_session(monkeypatch)
    mod = _oscar()
    _fixed_clock_plan(monkeypatch, mod)
    before = await _rows(session)
    out = await mod.run(_args(), {})
    assert out["plan_digest"] and "stop" not in out and "applied" not in out
    [p] = out["planned"]
    assert p["approved_before"]["id"] == OSCAR and len(p["approved_before_sha256"]) == 64
    assert await _rows(session) == before
    exists = (await session.execute(text("SELECT to_regclass('backup_2644_oscar_song')"))).scalar()
    await session.rollback()
    assert exists is None, "a plan run created the backup table"


async def test_backup_apply_and_undo_restore_the_row_exactly(session):
    before = await _rows(session)
    mod, plan, digest = await _plan(session)
    t0 = datetime.now(timezone.utc)
    out = await _backup_apply(session, mod, plan, digest)
    assert out == {"written_ids": [OSCAR], "skipped_changed_since_backup": []}
    row = (await _rows(session))[OSCAR]
    assert row["status"] == "resolved"
    assert datetime.fromisoformat(row["resolution_date"]) == datetime(2026, 3, 16, 2, 11, 7, tzinfo=timezone.utc)
    assert datetime.fromisoformat(row["expiration_time"]) == datetime(2026, 12, 31, 15, tzinfo=timezone.utc)
    # settled_at is OUR transition, not the venue's 2026-03-16T03:11:09Z stamp.
    assert datetime.fromisoformat(row["settled_at"]) >= t0.replace(microsecond=0)
    undo = await _restore(session, mod)
    assert undo == {"restored": [OSCAR], "preserved_changed_since_apply": []}
    assert await _rows(session) == before, "every column of every row is back"


async def test_legs_prices_and_history_never_move(session):
    legs, hist = await _legs_and_history(session)
    assert len(legs) == 2 and len(hist) == 2
    mod, plan, digest = await _plan(session)
    await _backup_apply(session, mod, plan, digest)
    assert await _legs_and_history(session) == (legs, hist)
    await _restore(session, mod)
    assert await _legs_and_history(session) == (legs, hist)


async def test_a_second_apply_writes_nothing_and_a_replan_is_a_no_op(session, monkeypatch):
    mod, plan, digest = await _plan(session)
    await _backup_apply(session, mod, plan, digest)
    after = await _rows(session)
    assert await mod.rail.apply(session, digest, table=mod.BACKUP_TABLE) == {
        "written_ids": [], "skipped_changed_since_backup": []}
    await session.commit()
    _, replan, redigest = await _plan(session, mod)
    assert replan["planned"] == [] and replan["stop"] == []
    assert [mod.rail._values(e) for e in replan["no_op"]] == [mod.REVIEWED_WRITE]
    # run() on the no-op plan writes nothing either.
    _real_db_task_session(monkeypatch)
    _fixed_clock_plan(monkeypatch, mod)
    out = await mod.run(_args(backup=True, apply=True, digest=redigest), HEAVY)
    assert out["applied"] == {"written_ids": [], "skipped_changed_since_backup": []}
    assert await _rows(session) == after


# ── the approved version: drift is refused, never adopted ────────────────────


async def test_a_writer_between_plan_and_backup_is_refused_never_adopted(session):
    mod, plan, digest = await _plan(session)
    await session.execute(text(
        "UPDATE futures_markets SET resolution_date='2026-10-15T12:00:00Z', updated_at=NOW() "
        "WHERE id=:id"), {"id": OSCAR})
    await session.commit()
    later = (await _rows(session))[OSCAR]
    assert await mod.rail.backup(session, plan["planned"], digest, table=mod.BACKUP_TABLE) == [OSCAR]
    await session.commit()
    out = await mod.rail.apply(session, digest, table=mod.BACKUP_TABLE)
    await session.commit()
    assert out["written_ids"] == []
    assert (await _rows(session))[OSCAR] == later, "the later writer's row stands"


async def test_run_refuses_drift_between_plan_and_backup_and_writes_nothing(session, monkeypatch):
    """Through run(): the row moves after run() planned and before it backed up."""
    _real_db_task_session(monkeypatch)
    mod = _oscar()
    digest = (await mod.run(_args(), HEAVY))["plan_digest"]
    real = mod.build_plan

    async def plan_then_race(s, evidence, *, now):
        plan = await real(s, evidence, now=now)
        await session.execute(text(
            "UPDATE futures_markets SET volume = 77 WHERE id = :id"), {"id": OSCAR})
        await session.commit()
        return plan

    monkeypatch.setattr(mod, "build_plan", plan_then_race)
    raced = None
    with pytest.raises(mod.Refused, match="changed since the plan was approved"):
        raced = await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    assert raced is None
    row = (await _rows(session))[OSCAR]
    assert row["status"] == "open" and float(row["volume"]) == 77.0
    # The refused backup rolled back whole, its runtime DDL included.
    exists = (await session.execute(text("SELECT to_regclass('backup_2644_oscar_song')"))).scalar()
    await session.rollback()
    assert exists is None, "a drifted row was frozen"


async def test_the_digest_names_the_approved_version(session, monkeypatch):
    _real_db_task_session(monkeypatch)
    mod = _oscar()
    _fixed_clock_plan(monkeypatch, mod)
    digest = (await mod.run(_args(), HEAVY))["plan_digest"]
    await session.execute(text(
        "UPDATE futures_markets SET updated_at = updated_at + interval '1 second' WHERE id = :id"),
        {"id": OSCAR})
    await session.commit()
    with pytest.raises(mod.Refused, match="does not match this plan"):
        await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    assert (await _rows(session))[OSCAR]["status"] == "open"


async def test_a_later_writer_is_never_reverted(session):
    mod, plan, digest = await _plan(session)
    await _backup_apply(session, mod, plan, digest)
    await session.execute(text(
        "UPDATE futures_markets SET updated_at = NOW() + interval '1 minute' WHERE id = :id"),
        {"id": OSCAR})
    await session.commit()
    later = (await _rows(session))[OSCAR]
    undo = await _restore(session, mod)
    assert undo == {"restored": [], "preserved_changed_since_apply": [OSCAR]}
    assert (await _rows(session))[OSCAR] == later
    assert (await _restore(session, mod))["restored"] == [], "a lost row is closed for every later undo"


# ── two channels, never crossing ─────────────────────────────────────────────


async def test_each_channels_restore_touches_only_its_own_rows(session):
    nine = _nine()
    nplan = await nine.build_plan(session, nine.load_evidence(), now=NOW)
    ndigest = nine.plan_digest(nplan["planned"])
    assert await nine.backup(session, nplan["planned"], ndigest) == []
    await session.commit()
    assert sorted((await nine.apply(session, ndigest))["written_ids"]) == NINE_IDS
    await session.commit()
    # The nine's applied rows do not block this channel's backup, and back.
    mod, plan, digest = await _plan(session)
    assert (await _backup_apply(session, mod, plan, digest))["written_ids"] == [OSCAR]
    both = await _rows(session)
    nine_backup = (await session.execute(text(
        "SELECT to_jsonb(b) FROM backup_2722_archived_nine b ORDER BY market_id"))).scalars().all()
    await session.rollback()

    assert (await _restore(session, mod))["restored"] == [OSCAR]
    after = await _rows(session)
    assert after[OSCAR]["status"] == "open"
    assert {i: after[i] for i in NINE_IDS} == {i: both[i] for i in NINE_IDS}
    assert (await session.execute(text(
        "SELECT to_jsonb(b) FROM backup_2722_archived_nine b ORDER BY market_id"))).scalars().all() == nine_backup
    await session.rollback()

    # Re-apply here, then undo the nine: this row stays as this channel left it.
    _, plan2, digest2 = await _plan(session, mod)
    assert (await _backup_apply(session, mod, plan2, digest2))["written_ids"] == [OSCAR]
    mine = (await _rows(session))[OSCAR]
    restored = await nine.restore_report(session)
    await session.commit()
    assert sorted(restored["restored"]) == NINE_IDS and OSCAR not in restored["restored"]
    assert (await _rows(session))[OSCAR] == mine


# ── the retained authority: anything short of it stops the plan ──────────────


def _void(body):
    for leg in body["markets"]:
        leg["result"] = ""
    return body


def _one_open(body):
    body["markets"][0]["status"] = "active"
    return body


def _other_event(body):
    for leg in body["markets"]:
        leg["event_ticker"] = "KXOSCARSONG-27"
    return body


def _later_close(body):
    body["markets"][0]["close_time"] = "2026-03-20T02:11:07Z"
    return body


@pytest.mark.parametrize("name,archive,live,why", [
    ("empty archive", lambda b: {"cursor": "", "markets": []}, None, "would not settle the row"),
    ("incomplete archive (a further page)", lambda b: {**b, "cursor": "next-page"}, None, "would not settle the row"),
    ("legs name another event", _other_event, None, "would not settle the row"),
    ("a leg still trading", _one_open, None, "would not settle the row"),
    ("a void", _void, None, "would record a void"),
    ("a different transition", _later_close, None, "is not the reviewed transition"),
    ("the live read lists legs", None, lambda lv: {**lv, "markets": [{"ticker": "KXOSCARSONG-26-GOL", "status": "active", "event_ticker": TICKER}]}, "would not settle the row"),
])
async def test_short_or_changed_authority_stops_the_plan(session, name, archive, live, why):
    mod = _oscar()
    _, plan, _ = await _plan(session, mod, _evidence_with(mod, archive=archive, live=live))
    assert len(plan["stop"]) == 1 and why in plan["stop"][0], (name, plan["stop"])


async def test_a_stopped_plan_never_backs_up_or_writes(session, monkeypatch):
    _real_db_task_session(monkeypatch)
    mod = _oscar()
    void = _evidence_with(mod, archive=_void)
    monkeypatch.setattr(mod, "load_evidence", lambda: void)
    before = await _rows(session)
    out = await mod.run(_args(backup=True, apply=True, digest="x"), HEAVY)
    assert "void" in out["stop"] and "applied" not in out
    assert await _rows(session) == before
    exists = (await session.execute(text("SELECT to_regclass('backup_2644_oscar_song')"))).scalar()
    await session.rollback()
    assert exists is None


# ── budgets on the wire, a held lock, the readback ───────────────────────────


def _real_db_task_session(monkeypatch):
    import app.tasks.base as base

    monkeypatch.setattr(base, "DATABASE_URL", DB_URL)
    return base


def _fixed_clock_plan(monkeypatch, mod):
    real = mod.build_plan

    async def at_now(session, evidence, *, now):
        return await real(session, evidence, now=NOW)

    monkeypatch.setattr(mod, "build_plan", at_now)


async def test_every_session_run_opens_carries_both_budgets_on_the_wire(session, monkeypatch):
    base = _real_db_task_session(monkeypatch)
    mod = _oscar()
    _fixed_clock_plan(monkeypatch, mod)
    real = base.get_task_session
    seen = []

    @contextlib.asynccontextmanager
    async def spying(**kwargs):
        async with real(**kwargs) as s:
            async def read():
                return [(await s.execute(text(q))).scalar_one() for q in (
                    "SELECT pg_backend_pid()", "SHOW statement_timeout", "SHOW lock_timeout")]

            first = await read()
            await s.commit()
            await (await s.connection()).invalidate()
            await s.rollback()
            again = await read()
            await s.rollback()
            seen.append((kwargs, first, again))
            yield s

    monkeypatch.setattr(base, "get_task_session", spying)
    plan = await mod.run(_args(), HEAVY)
    out = await mod.run(_args(backup=True, apply=True, digest=plan["plan_digest"]), HEAVY)
    assert out["applied"]["written_ids"] == [OSCAR]
    status = await mod.run(_args(status=True), {})
    assert [r["row_is_after_image"] for r in status["rows"]] == [True]
    restored = await mod.run(_args(restore=True), HEAVY)
    assert restored["restored"] == [OSCAR]
    # plan; plan + backup/apply; status; restore
    assert len(seen) == 5
    for kwargs, first, again in seen:
        assert kwargs == {"statement_timeout_ms": 10_000, "lock_timeout_ms": 500}
        assert first[0] != again[0], "the second read must be a reconnected backend"
        assert first[1:] == again[1:] == ["10s", "500ms"]


async def test_a_held_row_lock_stops_the_apply_within_its_budget_and_writes_nothing(
    session, monkeypatch
):
    from sqlalchemy.ext.asyncio import create_async_engine

    _real_db_task_session(monkeypatch)
    mod = _oscar()
    _fixed_clock_plan(monkeypatch, mod)
    before = await _rows(session)
    digest = (await mod.run(_args(), HEAVY))["plan_digest"]
    holder = create_async_engine(DB_URL)
    conn = await holder.connect()
    try:
        await conn.begin()
        await conn.execute(
            text("SELECT 1 FROM futures_markets WHERE id = :id FOR UPDATE"), {"id": OSCAR})
        t0 = time.monotonic()
        with pytest.raises(mod.Refused) as refused:
            await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
        waited = time.monotonic() - t0
    finally:
        await conn.rollback()
        await conn.close()
        await holder.dispose()
    msg = str(refused.value)
    assert "stopped the" in msg and "sqlstate 55P03" in msg and "Not retried" in msg
    assert waited < 5, f"the lock wait was not bounded ({waited:.2f}s)"
    assert await _rows(session) == before
    status = await mod.run(_args(status=True), {})
    # The backup's own CAS read the locked row: either it stopped there (nothing
    # frozen) or at the apply (frozen, unapplied). Never written, never owned.
    assert all(not r["applied"] and r["row_is_before_image"] for r in status["rows"])
    again = await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    assert again["applied"] == {"written_ids": [OSCAR], "skipped_changed_since_backup": []}


async def test_status_reads_back_without_writing(session, monkeypatch):
    _real_db_task_session(monkeypatch)
    mod = _oscar()
    assert (await mod.run(_args(status=True), {}))["backup_table"] == "absent"
    _fixed_clock_plan(monkeypatch, mod)
    digest = (await mod.run(_args(), HEAVY))["plan_digest"]
    await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    applied = await _rows(session)
    [row] = (await mod.run(_args(status=True), {}))["rows"]
    assert row["market_id"] == OSCAR and row["plan_digest"] == digest and row["applied"]
    assert row["row_is_after_image"] and not row["row_is_before_image"]
    assert row["status"] == "resolved"
    assert await _rows(session) == applied


async def test_writes_refuse_off_the_named_app(session, monkeypatch):
    _real_db_task_session(monkeypatch)
    mod = _oscar()
    _fixed_clock_plan(monkeypatch, mod)
    digest = (await mod.run(_args(), {}))["plan_digest"]
    for args in (_args(backup=True, apply=True, digest=digest), _args(restore=True)):
        with pytest.raises(mod.Refused, match="bainluck-heavy"):
            await mod.run(args, {"HEROKU_APP_NAME": "bainluck"})
    assert (await _rows(session))[OSCAR]["status"] == "open"
