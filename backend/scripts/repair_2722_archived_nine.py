"""#2722 — settle the nine venue-finalized archived Kalshi questions, reversibly.

PILLAR: TRUTH. SHIP: the nine venue-finalized archived questions show their
settled result instead of remaining Open, with a reversible first historical
repair.

THE NINE. Open Kalshi rows whose live event read returns no legs because the
venue moved every leg to its archive, where all are finalized (retained
2026-10-15: 18 public GETs, live + archive listing per event, hashes in the
fixture manifest pinned below). #2722's archive walk (26853512fb, merged) can
settle them, but ships INACTIVE: its ``UPDATE_SQL`` keys on ``id`` alone and
keeps no before-image. This is the first historical repair that disposition
requires — the nine exact ids, attended, undoable.

THE WRITE IS THE WALK'S, BYTE FOR BYTE. The plan runs the merged
``run_backfill`` (``archive_only``, the walk's own mode) over the nine rows as
the database holds them now, with the venue answered from the RETAINED bytes
and a session that RECORDS each ``UPDATE_SQL`` parameter set instead of
writing it. So the archive read, identity and exhaustion checks, settlement and
window derivations are the certified code, not a copy. A row the walk would not
settle from the archive (an unread, empty, malformed or incomplete listing, or
legs still open) stops the plan. A void the walk would also record is reported
and left out: this repair is the status lifecycle only — no grade, price,
snapshot or metadata.

THE OWNERSHIP CONTRACT (the #1853 lesson, CERT-4149 + Root 2026-10-16):

* backup FREEZES the approved set: ids, the planned values, the plan digest and
  each row's WHOLE before-image (``to_jsonb``). Apply reads that set back for
  this digest and never re-plans.
* apply is a whole-row compare-and-set: it writes only while the row still
  equals its backed-up before-image (the UPDATE's row lock makes compare and
  write one step). A drifted row is skipped and reported, never written over.
  The WHOLE after-image it produced is recorded.
* restore puts a row back only while it still equals that after-image; any
  later change to any column is reported and preserved, and that row's
  ownership is closed. A restore clears its markers, so no undo or retry can
  act on a stale one.
* A row the walk's write would not change is a NO-OP: reported, never backed
  up or written. A second apply of an applied plan writes nothing.

MODES (attended; nothing here runs on a schedule, and the beat's
``archive_walk`` stays False):

    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_2722_archived_nine.py
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_2722_archived_nine.py --backup --apply --digest <D>
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_2722_archived_nine.py --restore

Writes refuse unless ``HEROKU_APP_NAME`` is ``bainluck-heavy``; the backup table
is runtime DDL created only by an attended invocation (notice 47(c)).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

#: The nine reviewed rows: (futures_markets.id, external_id).
NINE: tuple[tuple[int, str], ...] = (
    (109776, "KXTXPRIMARY-04R26"),
    (110337, "KXWALESPARLIAMENT-26MAY07"),
    (110749, "KXPGAAWARDS-26-LIM"),
    (925648, "KXPAXTONPRIMARYCOUNTIES-26"),
    (925724, "KXTALARICOPRIMARYCOUNTIES-26"),
    (1631094, "KXINPRIMARY-01D26"),
    (3452978, "KXNEXTTEAMNFL-26THENDRICKSON"),
    (11757847, "KXPRIMARYTURNOUT-SENATETXR26"),
    (54069617, "KXDNCAUTOPSY-26"),
)
EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kalshi_2722_archived_nine"
MANIFEST_SHA256 = "d3484abdddd58e0487ca535e36c24e2029b81faba248edfc9f88969761540a7c"
REQUIRED_APP = "bainluck-heavy"
BACKUP_TABLE = "backup_2722_archived_nine"
#: Archive pages the plan may spend over the retained bytes (one per event).
PLAN_ARCHIVE_PAGES = 50

SQL = {
    "rows": """
        SELECT id, external_id, resolution_date, commence_time, market_tier
        FROM futures_markets
        WHERE id = ANY(CAST(:ids AS bigint[])) AND source = 'kalshi'
        ORDER BY id
    """,
    "current": """
        SELECT id, external_id, status, resolution_date, expiration_time, settled_at
        FROM futures_markets WHERE id = ANY(CAST(:ids AS bigint[])) ORDER BY id
    """,
    "bak_create": f"""
        CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
            market_id bigint PRIMARY KEY,
            plan_digest text NOT NULL,
            planned jsonb NOT NULL,
            before_row jsonb NOT NULL,
            after_row jsonb,
            applied boolean NOT NULL DEFAULT false,
            backed_up_at timestamptz NOT NULL DEFAULT NOW(),
            applied_at timestamptz,
            restored_at timestamptz,
            ownership_lost_at timestamptz
        )
    """,
    "bak_copy": f"""
        INSERT INTO {BACKUP_TABLE} (market_id, plan_digest, planned, before_row)
        SELECT fm.id, :digest, CAST(:planned AS jsonb), to_jsonb(fm)
        FROM futures_markets fm
        WHERE fm.id = :market_id AND fm.source = 'kalshi' AND fm.external_id = :ticker
        ON CONFLICT (market_id) DO NOTHING
    """,
    "bak_missing": f"""
        SELECT COUNT(*) FROM unnest(CAST(:ids AS bigint[])) AS t(id)
        WHERE NOT EXISTS (
            SELECT 1 FROM {BACKUP_TABLE} b
            WHERE b.market_id = t.id AND b.plan_digest = :digest)
    """,
    "bak_exists": f"SELECT to_regclass('{BACKUP_TABLE}') IS NOT NULL",
    "competing": f"""
        SELECT COUNT(*) FROM {BACKUP_TABLE}
        WHERE applied AND plan_digest <> :digest
    """,
    "frozen": f"""
        SELECT market_id, planned FROM {BACKUP_TABLE}
        WHERE plan_digest = :digest AND NOT applied AND ownership_lost_at IS NULL
        ORDER BY market_id
    """,
    # The walk's UPDATE_SQL values, as one whole-row compare-and-set.
    "apply_one": f"""
        UPDATE futures_markets fm
        SET resolution_date = COALESCE(CAST(:resolution_date AS timestamptz), fm.resolution_date),
            expiration_time = COALESCE(CAST(:expiration_time AS timestamptz), fm.expiration_time),
            status = CASE WHEN :venue_settled THEN 'resolved' ELSE fm.status END,
            settled_at = CASE WHEN :venue_settled
                              THEN COALESCE(fm.settled_at, NOW()) ELSE fm.settled_at END,
            updated_at = NOW()
        FROM {BACKUP_TABLE} b
        WHERE fm.id = :market_id
          AND b.market_id = fm.id AND b.plan_digest = :digest
          AND NOT b.applied AND b.ownership_lost_at IS NULL
          AND to_jsonb(fm) = b.before_row
        RETURNING to_jsonb(fm) AS after_row
    """,
    "mark_applied": f"""
        UPDATE {BACKUP_TABLE}
        SET applied = true, applied_at = NOW(), after_row = CAST(:after_row AS jsonb),
            restored_at = NULL
        WHERE market_id = :market_id AND plan_digest = :digest
    """,
    "restore": f"""
        UPDATE futures_markets fm
        SET status = b.before_row->>'status',
            resolution_date = (b.before_row->>'resolution_date')::timestamptz,
            expiration_time = (b.before_row->>'expiration_time')::timestamptz,
            settled_at = (b.before_row->>'settled_at')::timestamptz,
            updated_at = (b.before_row->>'updated_at')::timestamptz
        FROM {BACKUP_TABLE} b
        WHERE fm.id = b.market_id AND b.applied AND to_jsonb(fm) = b.after_row
        RETURNING fm.id
    """,
    "close_restored": f"""
        UPDATE {BACKUP_TABLE}
        SET applied = false, after_row = NULL, restored_at = NOW()
        WHERE market_id = ANY(CAST(:ids AS bigint[]))
    """,
    "close_lost": f"""
        UPDATE {BACKUP_TABLE}
        SET applied = false, ownership_lost_at = NOW()
        WHERE applied
        RETURNING market_id
    """,
}


class Refused(RuntimeError):
    pass


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _dt(value: Optional[str]) -> Optional[datetime]:
    """The frozen plan's ISO text back to the instant it names (asyncpg binds
    a ``timestamptz`` parameter only from a datetime)."""
    return datetime.fromisoformat(value) if value else None


def load_evidence(directory: Path = EVIDENCE_DIR) -> dict:
    """``ticker -> {"live": bytes, "archive": bytes}``, every hash checked."""
    import httpx

    raw = (directory / "manifest.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != MANIFEST_SHA256:
        raise Refused(f"evidence manifest hashes {digest}, expected {MANIFEST_SHA256}")
    out: dict = {}
    for entry in json.loads(raw)["responses"]:
        body = (directory / entry["file"]).read_bytes()
        if hashlib.sha256(body).hexdigest() != entry["sha256"]:
            raise Refused(f"evidence file {entry['file']} does not match its manifest hash")
        url = httpx.URL(entry["url"])
        kind = "archive" if "/historical/" in url.path else "live"
        out.setdefault(url.params["event_ticker"], {})[kind] = body
    missing = [t for _, t in NINE if set(out.get(t, {})) != {"live", "archive"}]
    if missing:
        raise Refused(f"no retained live+archive pair for {missing}")
    return out


def retained_venue(evidence: dict):
    """A ``KalshiAPIService`` whose transport answers ONLY from the retained bytes.

    GetEvent answers with the saved LIVE listing's legs (empty for all nine:
    the venue omits archived legs); ``/historical/markets`` answers the saved
    archive page. Anything else is a 404, so no request can leave the process.
    """
    import httpx

    from app.services.kalshi_api import KalshiAPIService

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/historical/markets" in path:
            ticker = request.url.params.get("event_ticker")
            if ticker in evidence and not request.url.params.get("cursor"):
                return httpx.Response(200, content=evidence[ticker]["archive"])
            return httpx.Response(404)
        if "/events/" in path:
            ticker = path.rsplit("/", 1)[-1]
            if ticker in evidence:
                markets = json.loads(evidence[ticker]["live"])["markets"]
                return httpx.Response(
                    200, json={"event": {"event_ticker": ticker, "markets": markets}}
                )
        return httpx.Response(404)

    svc = KalshiAPIService(api_key="")
    svc.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return svc


class _Recorder:
    """A session that RECORDS the walk's writes instead of making them."""

    def __init__(self):
        self.updates: list[dict] = []
        self.voids: list[int] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        from app.tasks import kalshi_resolution_sweep as sweep

        sql = str(stmt)
        if sql == sweep.UPDATE_SQL:
            self.updates.append(dict(params or {}))
        elif sql in (sweep.VOID_UPDATE_SQL, sweep.VOID_CHECKED_UPDATE_SQL):
            self.voids.append(int((params or {})["id"]))
        else:
            raise Refused("the plan's recorder saw an unexpected write")

    async def commit(self):
        return None


async def build_plan(session, evidence, *, now: datetime) -> dict:
    """Run the merged walk over the nine as stored, and record what it would write."""
    from sqlalchemy import text

    from app.tasks import kalshi_resolution_sweep as sweep

    ids = [i for i, _ in NINE]
    rows = [tuple(r) for r in (await session.execute(text(SQL["rows"]), {"ids": ids})).all()]
    current = {r[0]: r for r in (await session.execute(text(SQL["current"]), {"ids": ids})).all()}
    await session.rollback()
    found = {r[0]: r[1] for r in rows}
    wrong = [i for i, t in NINE if found.get(i) != t]
    if wrong:
        raise Refused(f"rows missing or not their reviewed ticker: {wrong}")

    recorder = _Recorder()
    report = await sweep.run_backfill(
        session_maker=lambda: recorder,
        client_factory=lambda: retained_venue(evidence),
        apply=True,
        now=now,
        rows=rows,
        archive_requests=PLAN_ARCHIVE_PAGES,
        archive_only=True,
    )
    stats = report.get("stats") or {}
    writes = {int(u["id"]): u for u in recorder.updates}
    planned, no_op, stop = [], [], []
    for market_id, ticker in NINE:
        w = writes.get(market_id)
        if w is None or not w.get("venue_settled"):
            stop.append(market_id)
            continue
        cur = current[market_id]
        values = {
            "resolution_date": _iso(w.get("resolution_date")),
            "expiration_time": _iso(w.get("expiration_time")),
            "venue_settled": True,
        }
        unchanged = (
            cur[2] == "resolved"
            and cur[5] is not None
            and (values["resolution_date"] is None or _iso(cur[3]) == values["resolution_date"])
            and (values["expiration_time"] is None or _iso(cur[4]) == values["expiration_time"])
        )
        (no_op if unchanged else planned).append({"market_id": market_id, "ticker": ticker, **values})
    return {
        "planned": planned,
        "no_op": no_op,
        "stop_not_settled_from_archive": stop,
        "voids_reported_not_written": sorted(set(recorder.voids)),
        "walk_stats": {k: v for k, v in stats.items() if v},
    }


def plan_digest(planned: list[dict]) -> str:
    body = MANIFEST_SHA256 + "|" + json.dumps(
        sorted(planned, key=lambda p: p["market_id"]), sort_keys=True
    )
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def refuse_unless_named_app(env) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app != REQUIRED_APP:
        raise Refused(f"HEROKU_APP_NAME={app!r}; writes run only on {REQUIRED_APP}")


async def backup(session, planned: list[dict], digest: str) -> int:
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    if (await session.execute(text(SQL["competing"]), {"digest": digest})).scalar_one():
        raise Refused("another plan's applied rows are still held; restore it first")
    for p in planned:
        await session.execute(
            text(SQL["bak_copy"]),
            {"market_id": p["market_id"], "ticker": p["ticker"], "digest": digest,
             "planned": json.dumps(p, sort_keys=True)},
        )
    missing = (await session.execute(
        text(SQL["bak_missing"]),
        {"ids": [p["market_id"] for p in planned], "digest": digest},
    )).scalar_one()
    return int(missing)


async def apply(session, digest: str) -> dict:
    """Write the FROZEN plan only — never a re-plan — each row by whole-row CAS."""
    from sqlalchemy import text

    frozen = (await session.execute(text(SQL["frozen"]), {"digest": digest})).all()
    written, skipped = [], []
    for market_id, planned in frozen:
        p = planned if isinstance(planned, dict) else json.loads(planned)
        row = (await session.execute(
            text(SQL["apply_one"]),
            {"market_id": market_id, "digest": digest,
             "resolution_date": _dt(p.get("resolution_date")),
             "expiration_time": _dt(p.get("expiration_time")),
             "venue_settled": bool(p.get("venue_settled"))},
        )).first()
        if row is None:
            skipped.append(market_id)
            continue
        after = row[0] if isinstance(row[0], str) else json.dumps(row[0])
        await session.execute(
            text(SQL["mark_applied"]),
            {"after_row": after, "market_id": market_id, "digest": digest},
        )
        written.append(market_id)
    return {"written_ids": written, "skipped_changed_since_backup": skipped}


async def restore(session) -> list[int]:
    return (await restore_report(session))["restored"]


async def restore_report(session) -> dict:
    from sqlalchemy import text

    if not (await session.execute(text(SQL["bak_exists"]))).scalar_one():
        raise Refused(f"{BACKUP_TABLE} does not exist; nothing was applied")
    restored = [r[0] for r in (await session.execute(text(SQL["restore"]))).all()]
    if restored:
        await session.execute(text(SQL["close_restored"]), {"ids": restored})
    preserved = [r[0] for r in (await session.execute(text(SQL["close_lost"]))).all()]
    return {"restored": restored, "preserved_changed_since_apply": preserved}


async def run(args, env) -> dict:
    from app.tasks.base import get_task_session

    out: dict = {"manifest_sha256": MANIFEST_SHA256}
    if args.restore:
        refuse_unless_named_app(env)
        async with get_task_session() as session:
            out.update(await restore_report(session))
            await session.commit()
        return out

    evidence = load_evidence()
    async with get_task_session() as session:
        plan = await build_plan(session, evidence, now=datetime.now(timezone.utc))
    digest = plan_digest(plan["planned"])
    out.update(plan, plan_digest=digest)
    if plan["stop_not_settled_from_archive"]:
        out["stop"] = (
            "the walk would not settle every reviewed row from its retained archive "
            "listing; do not apply this plan"
        )
        return out
    if not args.apply:
        return out
    refuse_unless_named_app(env)
    if not args.backup:
        raise Refused("--apply requires --backup (D51: the undo is written first)")
    if args.digest != digest:
        raise Refused(f"--digest {args.digest!r} does not match this plan ({digest})")
    async with get_task_session() as session:
        missing = await backup(session, plan["planned"], digest)
        if missing:
            await session.rollback()
            raise Refused(f"{missing} planned rows have no backup row; nothing written")
        await session.commit()
        out["applied"] = await apply(session, digest)
        await session.commit()
    out["undo"] = (
        f"heroku run:detached -a {REQUIRED_APP} -- python3 "
        "scripts/repair_2722_archived_nine.py --restore"
    )
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true", help="freeze the plan and its before-images")
    p.add_argument("--apply", action="store_true", help="write the frozen plan")
    p.add_argument("--digest", default="", help="the plan digest printed by a plan run")
    p.add_argument("--restore", action="store_true", help="undo an apply")
    args = p.parse_args(argv)
    try:
        out = asyncio.run(run(args, os.environ))
    except Refused as exc:
        print(json.dumps({"refused": str(exc)}))
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 1 if out.get("stop") else 0


if __name__ == "__main__":
    raise SystemExit(main())
