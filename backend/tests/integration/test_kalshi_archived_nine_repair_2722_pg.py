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
    assert await mod.backup(s, plan["planned"], digest) == 0
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
    assert await mod.backup(session, plan["planned"], digest) == 0
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
