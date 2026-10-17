"""#2722 — the nine archived questions' first historical repair, on a real Postgres.

PILLAR: TRUTH. SHIP: the nine venue-finalized archived questions show their
settled result instead of remaining Open, with a reversible first historical
repair.

The nine rows are seeded as production held them (2026-10-15) and the plan runs
the MERGED archive walk over the retained venue bytes, recording its writes. What
only Postgres can say: the whole-row before-image CAS, the after-image undo, the
backup DDL, and that no later writer is ever overwritten or reverted.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2722 nine-row repair",
    ),
]

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 16, 3, 0, tzinfo=timezone.utc)
# id, external_id, commence_time, market_tier, updated_at, resolution_date
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
IDS = [r[0] for r in NINE]


def _script():
    spec = importlib.util.spec_from_file_location(
        "repair_2722_archived_nine", ROOT / "scripts" / "repair_2722_archived_nine.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _clear(s):
    mod = _script()
    await s.execute(text(f"DROP TABLE IF EXISTS {mod.BACKUP_TABLE}"))
    await s.execute(text("DELETE FROM futures_markets WHERE id = ANY(CAST(:ids AS bigint[]))"), {"ids": IDS})


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


async def _rows(s) -> dict:
    rows = (await s.execute(
        text("SELECT id, to_jsonb(fm) FROM futures_markets fm "
             "WHERE id = ANY(CAST(:ids AS bigint[])) ORDER BY id"), {"ids": IDS},
    )).all()
    await s.rollback()
    return {r[0]: (r[1] if isinstance(r[1], dict) else json.loads(r[1])) for r in rows}


async def _plan(s, mod=None, evidence=None):
    mod = mod or _script()
    plan = await mod.build_plan(s, evidence or mod.load_evidence(), now=NOW)
    return mod, plan, mod.plan_digest(plan["planned"])


async def _backup_apply(s, mod, plan, digest):
    assert await mod.backup(s, plan["planned"], digest) == []
    await s.commit()
    out = await mod.apply(s, digest)
    await s.commit()
    return out


async def test_the_plan_is_the_merged_walk_settling_all_nine_from_the_archive(session):
    mod, plan, digest = await _plan(session)
    assert [p["market_id"] for p in plan["planned"]] == IDS
    assert plan["no_op"] == [] and plan["stop_not_settled_from_archive"] == []
    assert plan["walk_stats"]["venue_settled_from_archive"] == 9
    assert plan["voids_reported_not_written"] == []
    assert all(p["venue_settled"] and p["resolution_date"] for p in plan["planned"])


async def test_backup_apply_and_undo_restore_every_row_exactly(session):
    before = await _rows(session)
    mod, plan, digest = await _plan(session)
    out = await _backup_apply(session, mod, plan, digest)
    assert out["written_ids"] == IDS and out["skipped_changed_since_backup"] == []
    after = await _rows(session)
    by_id = {p["market_id"]: p for p in plan["planned"]}
    for mid in IDS:
        assert after[mid]["status"] == "resolved" and after[mid]["settled_at"]
        assert datetime.fromisoformat(after[mid]["resolution_date"]) == datetime.fromisoformat(
            by_id[mid]["resolution_date"])
    undo = await mod.restore_report(session)
    await session.commit()
    assert sorted(undo["restored"]) == IDS and undo["preserved_changed_since_apply"] == []
    assert await _rows(session) == before, "every row is back, every column"


async def test_a_second_apply_writes_nothing_and_a_replan_is_all_no_op(session):
    mod, plan, digest = await _plan(session)
    await _backup_apply(session, mod, plan, digest)
    again = await mod.apply(session, digest)
    await session.commit()
    assert again == {"written_ids": [], "skipped_changed_since_backup": []}
    _, replan, _ = await _plan(session, mod)
    assert replan["planned"] == [] and [p["market_id"] for p in replan["no_op"]] == IDS


async def test_a_row_changed_after_backup_is_skipped_never_written_over(session):
    mod, plan, digest = await _plan(session)
    assert await mod.backup(session, plan["planned"], digest) == []
    await session.commit()
    drifted = IDS[0]
    await session.execute(
        text("UPDATE futures_markets SET volume = 99 WHERE id = :id"), {"id": drifted})
    await session.commit()
    out = await mod.apply(session, digest)
    await session.commit()
    assert out["skipped_changed_since_backup"] == [drifted] and len(out["written_ids"]) == 8
    row = (await _rows(session))[drifted]
    assert row["status"] == "open" and float(row["volume"]) == 99.0
    await mod.restore(session)
    await session.commit()
    assert (await _rows(session))[drifted]["status"] == "open"


async def test_a_later_writer_is_never_reverted(session):
    mod, plan, digest = await _plan(session)
    await _backup_apply(session, mod, plan, digest)
    later = IDS[1]
    await session.execute(
        text("UPDATE futures_markets SET updated_at = NOW() + interval '1 minute' WHERE id = :id"),
        {"id": later})
    await session.commit()
    undo = await mod.restore_report(session)
    await session.commit()
    assert undo["preserved_changed_since_apply"] == [later] and len(undo["restored"]) == 8
    assert (await _rows(session))[later]["status"] == "resolved"
    assert await mod.restore(session) == [], "a lost row is closed for every later undo"


async def test_undo_then_a_writer_then_retry_never_reowns_the_writers_row(session):
    mod, plan, digest = await _plan(session)
    before = await _rows(session)
    await _backup_apply(session, mod, plan, digest)
    assert len(await mod.restore(session)) == 9
    await session.commit()
    writer = IDS[2]
    await session.execute(
        text("UPDATE futures_markets SET status = 'resolved', settled_at = NOW(), "
             "updated_at = NOW() WHERE id = :id"), {"id": writer})
    await session.commit()
    retry = await mod.apply(session, digest)
    await session.commit()
    assert writer not in retry["written_ids"] and len(retry["written_ids"]) == 8
    second = await mod.restore(session)
    await session.commit()
    assert writer not in second and len(second) == 8
    final = await _rows(session)
    assert final[writer]["status"] == "resolved"
    for mid in set(IDS) - {writer}:
        assert final[mid] == before[mid]


async def test_another_plans_held_rows_refuse_a_new_backup(session):
    mod, plan, digest = await _plan(session)
    await _backup_apply(session, mod, plan, digest)
    with pytest.raises(mod.Refused, match="another plan"):
        await mod.backup(session, plan["planned"], "a-different-digest")
    await session.rollback()


async def test_an_unread_archive_stops_the_plan(session, monkeypatch, tmp_path):
    """An empty, 429 or errored archive answer: the walk settles nothing from
    it, so the plan stops rather than planning eight of nine."""
    import httpx

    mod = _script()
    real = mod.retained_venue

    def venue_with(answer):
        def factory(evidence):
            svc = real(evidence)
            inner = svc.client._transport.handle_request

            def handler(request):
                if "/historical/markets" in request.url.path and (
                    request.url.params.get("event_ticker") == NINE[0][1]
                ):
                    return answer
                return inner(request)

            svc.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            return svc
        return factory

    for answer in (
        httpx.Response(200, json={"cursor": "", "markets": []}),
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(500),
    ):
        monkeypatch.setattr(mod, "retained_venue", venue_with(answer))
        _, plan, _ = await _plan(session, mod)
        stop = plan["stop_not_settled_from_archive"]
        if answer.status_code == 429:
            # A 429 stops ADMISSION for the whole run (#2722's ArchiveBudget):
            # every read not yet started is owed too. Still a stop, never a guess.
            assert NINE[0][0] in stop, stop
        else:
            assert stop == [NINE[0][0]], (answer.status_code, stop)
        assert not set(stop) & {p["market_id"] for p in plan["planned"]}


async def test_tampered_evidence_is_refused(session, tmp_path):
    mod = _script()
    copy = tmp_path / "nine"
    shutil.copytree(mod.EVIDENCE_DIR, copy)
    manifest = json.loads((copy / "manifest.json").read_text())
    first = manifest["responses"][0]["file"]
    (copy / first).write_bytes((copy / first).read_bytes() + b" ")
    with pytest.raises(mod.Refused):
        mod.load_evidence(copy)
    assert hashlib.sha256((mod.EVIDENCE_DIR / "manifest.json").read_bytes()).hexdigest() == mod.MANIFEST_SHA256


# --- CERT-4152 / Root 003: the plan binds the APPROVED version ---------------


async def test_a_writer_between_plan_and_backup_is_refused_never_adopted(session):
    """Root's race, through the run() sequence: plan returns the nine, a
    lifecycle writer moves 109776's date, then backup. The row is no longer the
    version the plan was approved on, so it is named and nothing is frozen for
    it — and apply, if called anyway, writes nothing over it."""
    mod, plan, digest = await _plan(session)
    raced = IDS[0]
    await session.execute(
        text("UPDATE futures_markets SET resolution_date='2026-10-15T12:00:00Z', "
             "updated_at=NOW() WHERE id=:id"), {"id": raced})
    await session.commit()
    later = (await _rows(session))[raced]
    drifted = await mod.backup(session, plan["planned"], digest)
    await session.commit()
    assert drifted == [raced]
    out = await mod.apply(session, digest)
    await session.commit()
    assert raced not in out["written_ids"]
    assert (await _rows(session))[raced] == later, "the later writer's date stands"


async def test_without_drift_every_approved_row_is_frozen(session):
    """The positive control for the race above: the same sequence with no writer."""
    mod, plan, digest = await _plan(session)
    assert await mod.backup(session, plan["planned"], digest) == []
    await session.commit()
    assert sorted((await mod.apply(session, digest))["written_ids"]) == IDS
    await session.commit()


async def test_the_digest_names_the_approved_versions(session):
    """A row that moves between the reviewed dry run and the apply run changes
    the digest, so `--digest` from the dry run is refused by run()."""
    mod, plan, digest = await _plan(session)
    await session.execute(
        text("UPDATE futures_markets SET updated_at = updated_at + interval '1 second' "
             "WHERE id = :id"), {"id": IDS[3]})
    await session.commit()
    _, replan, redigest = await _plan(session, mod)
    assert redigest != digest
    assert [p["market_id"] for p in replan["planned"]] == IDS


async def test_root_plan_beforeimage_is_frozen_before_backup(session):
    """Root's witness (root-5f5ca4-replay.py), body verbatim."""
    mod, plan, digest = await _plan(session)
    assert len(plan['planned']) == 9
    raced = IDS[0]
    # A later lifecycle writer changes the same date this reviewed plan will write,
    # after plan() has returned and before backup() is called by run().
    await session.execute(text("UPDATE futures_markets SET resolution_date='2026-10-15T12:00:00Z', updated_at=NOW() WHERE id=:id"), {'id':raced})
    await session.commit()
    later = (await _rows(session))[raced]
    try:
        missing = await mod.backup(session, plan['planned'], digest)
        if missing:
            await session.rollback()
            return
        await session.commit()
        stats = await mod.apply(session, digest)
        await session.commit()
    except mod.Refused:
        await session.rollback()
        return
    after = (await _rows(session))[raced]
    print('ROOT_PLAN_BACKUP_DRIFT', json.dumps({'raced':raced,'approved_plan_digest':digest,'later_date':later['resolution_date'],'after_date':after['resolution_date'],'written':stats['written_ids']}))
    assert raced not in stats['written_ids'] and after == later, 'repair overwrote a lifecycle writer after review, before backup'


# ── #2722 near-apply prerequisite: every session run() opens is bounded ───────


def _real_db_task_session(monkeypatch):
    """Point the task engine at this database. The SAME get_task_session and
    build_connect_args run, so the budgets reach Postgres exactly as they would
    on bainluck-heavy (startup packet, not a SET)."""
    import app.tasks.base as base

    monkeypatch.setattr(base, "DATABASE_URL", DB_URL)
    return base


def _fixed_clock_plan(monkeypatch, mod):
    real = mod.build_plan

    async def at_now(session, evidence, *, now):
        return await real(session, evidence, now=NOW)

    monkeypatch.setattr(mod, "build_plan", at_now)


def _args(**kw):
    import argparse

    return argparse.Namespace(**{"backup": False, "apply": False, "digest": "",
                                 "restore": False, "status": False, **kw})


HEAVY = {"HEROKU_APP_NAME": "bainluck-heavy"}


async def test_every_session_run_opens_carries_both_budgets_on_the_wire(session, monkeypatch):
    """The budgets the script passes are what Postgres enforces, and they
    survive a commit (a bare SET would be lost at the next reconnect)."""
    import contextlib

    base = _real_db_task_session(monkeypatch)
    mod = _script()
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
            # A reconnect: the next statement runs on a NEW backend.
            await (await s.connection()).invalidate()
            await s.rollback()
            again = await read()
            await s.rollback()
            seen.append((kwargs, first, again))
            yield s

    monkeypatch.setattr(base, "get_task_session", spying)
    plan = await mod.run(_args(), HEAVY)
    out = await mod.run(_args(backup=True, apply=True, digest=plan["plan_digest"]), HEAVY)
    assert sorted(out["applied"]["written_ids"]) == IDS
    status = await mod.run(_args(status=True), {})
    assert [r["row_is_after_image"] for r in status["rows"]] == [True] * 9
    restored = await mod.run(_args(restore=True), HEAVY)
    assert sorted(restored["restored"]) == IDS
    # plan; plan + backup/apply; status; restore
    assert len(seen) == 5
    for kwargs, first, again in seen:
        assert kwargs == {"statement_timeout_ms": 10_000, "lock_timeout_ms": 500}
        assert first[0] != again[0], "the second read must be a reconnected backend"
        assert first[1:] == again[1:] == ["10s", "500ms"]


async def test_a_held_row_lock_stops_the_apply_within_its_budget_and_writes_nothing(
    session, monkeypatch
):
    """Another writer holds the FIFTH row: the apply has already written four,
    waits 500 ms, is refused with 55P03, and its whole transaction rolls back.
    The backup stays committed and unapplied, nothing is retried or restored,
    and a later attended re-run of the SAME digest applies all nine."""
    import time

    from sqlalchemy.ext.asyncio import create_async_engine

    _real_db_task_session(monkeypatch)
    mod = _script()
    _fixed_clock_plan(monkeypatch, mod)
    before = await _rows(session)
    digest = (await mod.run(_args(), HEAVY))["plan_digest"]

    holder = create_async_engine(DB_URL)
    conn = await holder.connect()
    try:
        await conn.begin()
        await conn.execute(
            text("SELECT 1 FROM futures_markets WHERE id = :id FOR UPDATE"), {"id": IDS[4]})
        t0 = time.monotonic()
        with pytest.raises(mod.Refused) as refused:
            await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
        waited = time.monotonic() - t0
    finally:
        await conn.rollback()
        await conn.close()
        await holder.dispose()

    msg = str(refused.value)
    assert "stopped the apply" in msg and "sqlstate 55P03" in msg and "nothing to restore" in msg
    assert waited < 5, f"the lock wait was not bounded ({waited:.2f}s)"
    assert await _rows(session) == before, "the four rows written before the lock rolled back"
    held = (await session.execute(text(
        f"SELECT market_id, applied, after_row IS NULL, ownership_lost_at IS NULL "
        f"FROM {mod.BACKUP_TABLE} WHERE plan_digest = :d ORDER BY market_id"), {"d": digest})).all()
    await session.rollback()
    assert [tuple(r) for r in held] == [(i, False, True, True) for i in IDS]

    again = await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    assert sorted(again["applied"]["written_ids"]) == IDS
    assert again["applied"]["skipped_changed_since_backup"] == []



# ── directive 024: a COMMIT whose acknowledgement is lost is UNKNOWN ──────────
#
# The commit is REAL: Postgres makes it durable, then the acknowledgement is
# "lost" (the client sees a connection failure). The run must say UNKNOWN —
# never "nothing was backed up / written / restored" — stop with no retry,
# reconnect-write, restore or cleanup, and ``--status`` must read back what
# actually landed.


def _lost_ack_after_real_commit(monkeypatch, *, session_no: int, commit_no: int):
    """Wrap the REAL task session: the ``commit_no``-th commit of the
    ``session_no``-th session commits on the server, then raises as a lost
    acknowledgement would (sqlstate 08006, connection failure)."""
    import contextlib

    from sqlalchemy.exc import OperationalError

    base = _real_db_task_session(monkeypatch)
    real = base.get_task_session
    opened = {"n": 0, "lost": 0}

    class _Orig(Exception):
        sqlstate = "08006"

    @contextlib.asynccontextmanager
    async def lossy(**kwargs):
        opened["n"] += 1
        mine, commits = opened["n"], {"n": 0}
        async with real(**kwargs) as s:
            real_commit = s.commit

            async def commit():
                await real_commit()  # durable on the server
                commits["n"] += 1
                if mine == session_no and commits["n"] == commit_no:
                    opened["lost"] += 1
                    raise OperationalError("COMMIT", {}, _Orig("connection reset by peer"))

            s.commit = commit
            yield s

    monkeypatch.setattr(base, "get_task_session", lossy)
    return opened


async def _backup_rows(s, mod) -> list:
    rows = (await s.execute(text(
        f"SELECT to_jsonb(b) FROM {mod.BACKUP_TABLE} b ORDER BY market_id"))).scalars().all()
    await s.rollback()
    return [r if isinstance(r, dict) else json.loads(r) for r in rows]


async def _table_exists(s, name) -> bool:
    out = (await s.execute(text(f"SELECT to_regclass('{name}') IS NOT NULL"))).scalar_one()
    await s.rollback()
    return out


async def test_backup_commit_lost_ack_is_unknown_and_status_reads_the_frozen_backup(
    session, monkeypatch
):
    mod = _script()
    _fixed_clock_plan(monkeypatch, mod)
    before = await _rows(session)
    plan = await mod.run(_args(), HEAVY)
    digest = plan["plan_digest"]
    approved = {p["market_id"]: p["approved_before_sha256"] for p in plan["planned"]}
    # session 1 = the plan, session 2 = backup/apply; its FIRST commit is the backup
    lost = _lost_ack_after_real_commit(monkeypatch, session_no=2, commit_no=1)
    with pytest.raises(mod.Unknown) as unknown:
        await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    assert lost == {"n": 2, "lost": 1}, "no further session: no retry, no reconnect-write"
    msg = str(unknown.value)
    assert unknown.value.phase == "backup-commit" and unknown.value.digest == digest
    assert "UNKNOWN" in msg and "nothing was backed up" not in msg and "rolled back" not in msg
    assert await _rows(session) == before, "the apply never started"
    status = await mod.run(_args(status=True), {})
    assert status["backup_table"] == mod.BACKUP_TABLE
    assert [r["market_id"] for r in status["rows"]] == IDS
    for r in status["rows"]:
        assert r["backed_up"] and r["plan_digest"] == digest and r["applied"] is False
        assert r["row_is_before_image"] and not r["row_is_after_image"]
        assert r["before_row_sha256"] == approved[r["market_id"]], "the backup IS the approved version"
        assert r["status"] == "open"
    # The attended operator's later decision — not the run's — can resume the same digest.
    monkeypatch.undo()
    _real_db_task_session(monkeypatch)
    _fixed_clock_plan(monkeypatch, mod)
    again = await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    assert sorted(again["applied"]["written_ids"]) == IDS


async def test_apply_commit_lost_ack_is_unknown_and_status_reads_the_durable_apply(
    session, monkeypatch
):
    mod = _script()
    _fixed_clock_plan(monkeypatch, mod)
    before = await _rows(session)
    digest = (await mod.run(_args(), HEAVY))["plan_digest"]
    lost = _lost_ack_after_real_commit(monkeypatch, session_no=2, commit_no=2)
    with pytest.raises(mod.Unknown) as unknown:
        await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    assert lost == {"n": 2, "lost": 1}
    msg = str(unknown.value)
    assert unknown.value.phase == "apply-commit"
    assert "nothing to restore" not in msg and "was not written" not in msg
    after = await _rows(session)
    assert all(after[i]["status"] == "resolved" for i in IDS), "the commit was durable"
    held = await _backup_rows(session, mod)
    status = await mod.run(_args(status=True), {})
    for r in status["rows"]:
        assert r["applied"] and r["row_is_after_image"] and not r["row_is_before_image"]
        assert r["status"] == "resolved" and r["applied_at"]
    # The readback wrote nothing: neither the nine nor their backup moved.
    assert await _rows(session) == after and await _backup_rows(session, mod) == held
    # Complete images: the attended undo still restores every column of every row.
    monkeypatch.undo()
    _real_db_task_session(monkeypatch)
    restored = await mod.run(_args(restore=True), HEAVY)
    assert sorted(restored["restored"]) == IDS
    assert await _rows(session) == before


async def test_restore_commit_lost_ack_is_unknown_and_status_reads_the_durable_restore(
    session, monkeypatch
):
    mod = _script()
    _real_db_task_session(monkeypatch)
    _fixed_clock_plan(monkeypatch, mod)
    before = await _rows(session)
    digest = (await mod.run(_args(), HEAVY))["plan_digest"]
    await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    lost = _lost_ack_after_real_commit(monkeypatch, session_no=1, commit_no=1)
    with pytest.raises(mod.Unknown) as unknown:
        await mod.run(_args(restore=True), HEAVY)
    assert lost == {"n": 1, "lost": 1}
    assert unknown.value.phase == "restore-commit"
    assert "no row was restored" not in str(unknown.value)
    assert await _rows(session) == before, "the restore was durable"
    status = await mod.run(_args(status=True), {})
    for r in status["rows"]:
        assert r["applied"] is False and r["restored_at"] and r["row_is_before_image"]
        assert not r["row_is_after_image"] and r["status"] == "open"


async def test_status_with_no_backup_table_reports_absence_and_creates_nothing(
    session, monkeypatch
):
    _real_db_task_session(monkeypatch)
    mod = _script()
    before = await _rows(session)
    status = await mod.run(_args(status=True), {})
    assert status["backup_table"] == "absent" and status["rows"] == []
    assert "applied" not in status, "absence is not an apply verdict"
    assert not await _table_exists(session, mod.BACKUP_TABLE), "the readback ran DDL"
    assert await _rows(session) == before


async def test_status_is_read_only_on_the_server(session, monkeypatch):
    """The readback session is READ ONLY: a write slipped into it is refused by
    Postgres itself (25006), not by convention."""
    from sqlalchemy.exc import DBAPIError

    base = _real_db_task_session(monkeypatch)
    mod = _script()
    _fixed_clock_plan(monkeypatch, mod)
    digest = (await mod.run(_args(), HEAVY))["plan_digest"]
    await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    import contextlib

    real = base.get_task_session

    @contextlib.asynccontextmanager
    async def sneaky(**kwargs):
        async with real(**kwargs) as s:
            real_execute = s.execute

            async def execute(stmt, *a, **k):
                result = await real_execute(stmt, *a, **k)
                if "row_is_after_image" in str(stmt):
                    await real_execute(text(
                        "UPDATE futures_markets SET volume = 7 WHERE id = :id"), {"id": IDS[0]})
                return result

            s.execute = execute
            yield s

    monkeypatch.setattr(base, "get_task_session", sneaky)
    with pytest.raises(DBAPIError, match="read-only transaction"):
        await mod.run(_args(status=True), {})
    assert float((await _rows(session))[IDS[0]]["volume"]) == 10.0


async def test_status_reads_a_later_writer_as_neither_image(session, monkeypatch):
    _real_db_task_session(monkeypatch)
    mod = _script()
    _fixed_clock_plan(monkeypatch, mod)
    digest = (await mod.run(_args(), HEAVY))["plan_digest"]
    await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
    later = IDS[1]
    await session.execute(
        text("UPDATE futures_markets SET updated_at = NOW() + interval '1 minute' WHERE id = :id"),
        {"id": later})
    await session.commit()
    rows = {r["market_id"]: r for r in (await mod.run(_args(status=True), {}))["rows"]}
    assert rows[later]["applied"] and not rows[later]["row_is_after_image"]
    assert not rows[later]["row_is_before_image"]
    assert all(rows[i]["row_is_after_image"] for i in IDS if i != later)
    restored = await mod.run(_args(restore=True), HEAVY)
    assert restored["preserved_changed_since_apply"] == [later]


async def test_status_never_reads_the_oscar_channel(session, monkeypatch):
    """A row held in the OTHER channel's table — even one naming a nine id —
    is invisible to this readback; only the nine's own table answers."""
    _real_db_task_session(monkeypatch)
    mod = _script()
    oscar = "backup_2644_oscar_song"
    oscar_sql = mod.channel_sql(oscar)
    current = json.dumps((await _rows(session))[IDS[0]])
    try:
        await session.execute(text(oscar_sql["bak_create"]))
        await session.execute(text(oscar_sql["bak_copy"]), {
            "market_id": IDS[0], "ticker": NINE[0][1], "digest": "oscar-digest",
            "planned": "{}", "approved_before": current})
        await session.execute(text(f"UPDATE {oscar} SET applied = true"))
        await session.commit()
        held = (await session.execute(text(f"SELECT COUNT(*) FROM {oscar} WHERE applied"))).scalar_one()
        await session.rollback()
        assert held == 1, "the other channel holds an applied row naming a nine id"
        assert (await mod.run(_args(status=True), {}))["backup_table"] == "absent"
        _fixed_clock_plan(monkeypatch, mod)
        digest = (await mod.run(_args(), HEAVY))["plan_digest"]
        await mod.run(_args(backup=True, apply=True, digest=digest), HEAVY)
        rows = (await mod.run(_args(status=True), {}))["rows"]
        assert [r["market_id"] for r in rows] == IDS
        assert {r["plan_digest"] for r in rows} == {digest}
    finally:
        await session.rollback()
        await session.execute(text(f"DROP TABLE IF EXISTS {oscar}"))
        await session.commit()


async def test_the_default_run_is_a_plan_with_no_ddl_and_no_write(session, monkeypatch):
    _real_db_task_session(monkeypatch)
    mod = _script()
    _fixed_clock_plan(monkeypatch, mod)
    before = await _rows(session)
    out = await mod.run(_args(), HEAVY)
    assert [p["market_id"] for p in out["planned"]] == IDS and "applied" not in out
    assert not await _table_exists(session, mod.BACKUP_TABLE), "a plan run created the backup table"
    assert await _rows(session) == before
