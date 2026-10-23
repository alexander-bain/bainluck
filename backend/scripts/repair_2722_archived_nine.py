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

* the PLAN binds each row's approved version: its WHOLE before-image is read
  with the plan and its hash rides the digest, so a row that moves between the
  reviewed dry run and the apply changes the digest and is refused.
* backup FREEZES the approved set — ids, planned values, digest — and backs a
  row up only while it still IS that approved before-image (CERT-4152 / Root:
  a writer between planning and backup is refused and named, never adopted as
  a new baseline). Apply reads that set back for this digest and never
  re-plans.
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
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_2722_archived_nine.py --status

Writes refuse unless ``HEROKU_APP_NAME`` is ``bainluck-heavy``; the backup table
is runtime DDL created only by an attended invocation (notice 47(c)).

EVERY SESSION IS BOUNDED (#4482). Plan, backup/apply and restore each open their
session with ``STATEMENT_TIMEOUT_MS`` / ``LOCK_TIMEOUT_MS`` passed to
``get_task_session``, so the budgets ride the connection's startup packet and
survive every commit and reconnect (a bare ``SET`` would not: the task engine's
resting bound is 30 minutes and its lock bound is none). A budget that fires is
a refusal naming the phase and SQLSTATE: that phase's transaction rolls back
whole, and the run never retries and never restores on its own.

A COMMIT THAT DOES NOT RETURN IS NEITHER (directive 024, CERT-4198's caveat).
The server can make a commit durable and the acknowledgement still be lost, so
"nothing was written" is not knowable from the client. Once a backup, apply or
restore COMMIT has been sent and not acknowledged, the run reports UNKNOWN
(exit 3, ``"outcome": "UNKNOWN"``) and stops: no retry, no reconnect-write, no
restore, no cleanup. ``--status`` is the read-only readback: a READ ONLY
transaction over this channel's table and the exact nine only, no DDL, and a
missing table is reported as absent, never as an apply verdict.
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
#: Per-engine budgets for every session this script opens. Each phase is a few
#: primary-key statements over nine rows (milliseconds on a real Postgres), so
#: 10 s only fires on a stuck server, and 500 ms of lock wait means another
#: writer holds one of the nine: the attended run stops rather than queue
#: behind it. Both fail closed.
STATEMENT_TIMEOUT_MS = 10_000
LOCK_TIMEOUT_MS = 500

_SQL_TEMPLATES = {
    "rows": """
        SELECT id, external_id, resolution_date, commence_time, market_tier
        FROM futures_markets
        WHERE id = ANY(CAST(:ids AS bigint[])) AND source = 'kalshi'
        ORDER BY id
    """,
    "current": """
        SELECT id, external_id, status, resolution_date, expiration_time, settled_at,
               to_jsonb(fm)::text AS before_row
        FROM futures_markets fm WHERE id = ANY(CAST(:ids AS bigint[])) ORDER BY id
    """,
    "bak_create": """
        CREATE TABLE IF NOT EXISTS {table} (
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
    "bak_copy": """
        INSERT INTO {table} (market_id, plan_digest, planned, before_row)
        SELECT fm.id, :digest, CAST(:planned AS jsonb), to_jsonb(fm)
        FROM futures_markets fm
        WHERE fm.id = :market_id AND fm.source = 'kalshi' AND fm.external_id = :ticker
          -- CERT-4152 / Root 003: the row must still be EXACTLY the version the
          -- plan was approved on. A writer between planning and backup is a
          -- refusal, never a new baseline adopted in silence.
          AND to_jsonb(fm) = CAST(:approved_before AS jsonb)
        ON CONFLICT (market_id) DO NOTHING
    """,
    "bak_missing": """
        SELECT t.id FROM unnest(CAST(:ids AS bigint[])) AS t(id)
        WHERE NOT EXISTS (
            SELECT 1 FROM {table} b
            WHERE b.market_id = t.id AND b.plan_digest = :digest)
        ORDER BY t.id
    """,
    "bak_exists": "SELECT to_regclass('{table}') IS NOT NULL",
    "competing": """
        SELECT COUNT(*) FROM {table}
        WHERE applied AND plan_digest <> :digest
    """,
    "frozen": """
        SELECT market_id, planned FROM {table}
        WHERE plan_digest = :digest AND NOT applied AND ownership_lost_at IS NULL
        ORDER BY market_id
    """,
    # The walk's UPDATE_SQL values, as one whole-row compare-and-set.
    "apply_one": """
        UPDATE futures_markets fm
        SET resolution_date = COALESCE(CAST(:resolution_date AS timestamptz), fm.resolution_date),
            expiration_time = COALESCE(CAST(:expiration_time AS timestamptz), fm.expiration_time),
            status = CASE WHEN :venue_settled THEN 'resolved' ELSE fm.status END,
            settled_at = CASE WHEN :venue_settled
                              THEN COALESCE(fm.settled_at, NOW()) ELSE fm.settled_at END,
            updated_at = NOW()
        FROM {table} b
        WHERE fm.id = :market_id
          AND b.market_id = fm.id AND b.plan_digest = :digest
          AND NOT b.applied AND b.ownership_lost_at IS NULL
          AND to_jsonb(fm) = b.before_row
        RETURNING to_jsonb(fm) AS after_row
    """,
    "mark_applied": """
        UPDATE {table}
        SET applied = true, applied_at = NOW(), after_row = CAST(:after_row AS jsonb),
            restored_at = NULL
        WHERE market_id = :market_id AND plan_digest = :digest
    """,
    "restore": """
        UPDATE futures_markets fm
        SET status = b.before_row->>'status',
            resolution_date = (b.before_row->>'resolution_date')::timestamptz,
            expiration_time = (b.before_row->>'expiration_time')::timestamptz,
            settled_at = (b.before_row->>'settled_at')::timestamptz,
            updated_at = (b.before_row->>'updated_at')::timestamptz
        FROM {table} b
        WHERE fm.id = b.market_id AND b.applied AND to_jsonb(fm) = b.after_row
        RETURNING fm.id
    """,
    "close_restored": """
        UPDATE {table}
        SET applied = false, after_row = NULL, restored_at = NOW()
        WHERE market_id = ANY(CAST(:ids AS bigint[]))
    """,
    "close_lost": """
        UPDATE {table}
        SET applied = false, ownership_lost_at = NOW()
        WHERE applied
        RETURNING market_id
    """,
}
#: The backup channels these statements may run against. Each is its own frozen
#: cohort in its own script — the nine here; #2644's single Oscars row in
#: ``repair_2644_oscar_song.py`` — and one channel's restore never reads the
#: other's table. No caller can name a third, and no CLI takes a table.
CHANNEL_TABLES = (BACKUP_TABLE, "backup_2644_oscar_song")


def channel_sql(table: str) -> dict:
    """The repair's statements over ONE frozen channel's backup table."""
    if table not in CHANNEL_TABLES:
        raise ValueError(f"{table!r} is not a frozen repair channel")
    return {k: v.replace("{table}", table) for k, v in _SQL_TEMPLATES.items()}


SQL = channel_sql(BACKUP_TABLE)

#: The readback (``--status``): the exact nine, each beside this channel's
#: backup row (if any) and the live row, compared whole against both images.
#: ``before_row_sha256`` is the plan's ``approved_before_sha256`` for the same
#: version (jsonb text is canonical), so the backup can be matched to review.
STATUS_IDS = [i for i, _ in NINE]
STATUS_SQL = f"""
    SELECT t.id AS market_id, b.market_id IS NOT NULL AS backed_up, b.plan_digest,
           b.applied, b.backed_up_at, b.applied_at, b.restored_at, b.ownership_lost_at,
           encode(sha256(convert_to(b.before_row::text, 'UTF8')), 'hex') AS before_row_sha256,
           b.market_id IS NOT NULL AND to_jsonb(fm) = b.before_row AS row_is_before_image,
           b.after_row IS NOT NULL AND to_jsonb(fm) = b.after_row AS row_is_after_image,
           fm.status, fm.resolution_date, fm.expiration_time, fm.settled_at, fm.updated_at
    FROM unnest(CAST(:ids AS bigint[])) AS t(id)
    LEFT JOIN {BACKUP_TABLE} b ON b.market_id = t.id
    LEFT JOIN futures_markets fm ON fm.id = t.id
    ORDER BY t.id
"""


class Refused(RuntimeError):
    pass


class Unknown(RuntimeError):
    """A COMMIT whose acknowledgement never came back: it may or may not be durable."""

    def __init__(self, message: str, *, phase: str, digest: Optional[str] = None):
        super().__init__(message)
        self.phase = phase
        self.digest = digest


#: What is still certain when each commit fails to return.
_UNKNOWN_AFTER = {
    "backup-commit": "the backup's durability is UNKNOWN; futures_markets was not written "
                     "(the apply had not started)",
    "apply-commit": "the apply's durability is UNKNOWN; the backup is committed",
    "restore-commit": "the restore's durability is UNKNOWN",
}


def _unknown(phase: str, exc: BaseException, digest: Optional[str] = None) -> Unknown:
    return Unknown(
        f"the {phase} did not return ({type(exc).__name__}); {_UNKNOWN_AFTER[phase]}. "
        "Not retried, not restored — read it back with --status before any further step",
        phase=phase, digest=digest,
    )


def _stopped(phase: str, exc, consequence: str) -> Refused:
    """A budget firing (lock_timeout 55P03, statement_timeout 57014) or any other
    server refusal, as a refusal that names the phase and what it left behind."""
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return Refused(
        f"the database stopped the {phase} ({type(orig or exc).__name__}, sqlstate "
        f"{code}); its transaction rolled back, {consequence}. Not retried, not "
        "restored — re-run the plan and review it before any further step"
    )


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


def load_evidence(
    directory: Path = EVIDENCE_DIR, *, manifest_sha256: str = MANIFEST_SHA256,
    members: tuple[tuple[int, str], ...] = NINE,
) -> dict:
    """``ticker -> {"live": bytes, "archive": bytes}``, every hash checked."""
    import httpx

    raw = (directory / "manifest.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != manifest_sha256:
        raise Refused(f"evidence manifest hashes {digest}, expected {manifest_sha256}")
    out: dict = {}
    for entry in json.loads(raw)["responses"]:
        body = (directory / entry["file"]).read_bytes()
        if hashlib.sha256(body).hexdigest() != entry["sha256"]:
            raise Refused(f"evidence file {entry['file']} does not match its manifest hash")
        url = httpx.URL(entry["url"])
        kind = "archive" if "/historical/" in url.path else "live"
        out.setdefault(url.params["event_ticker"], {})[kind] = body
    missing = [t for _, t in members if set(out.get(t, {})) != {"live", "archive"}]
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


async def build_plan(
    session, evidence, *, now: datetime, members: tuple[tuple[int, str], ...] = NINE
) -> dict:
    """Run the merged walk over ``members`` (the nine) as stored, and record what
    it would write."""
    from sqlalchemy import text

    from app.tasks import kalshi_resolution_sweep as sweep

    ids = [i for i, _ in members]
    rows = [tuple(r) for r in (await session.execute(text(SQL["rows"]), {"ids": ids})).all()]
    current = {r[0]: r for r in (await session.execute(text(SQL["current"]), {"ids": ids})).all()}
    await session.rollback()
    found = {r[0]: r[1] for r in rows}
    wrong = [i for i, t in members if found.get(i) != t]
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
    for market_id, ticker in members:
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
        entry = {"market_id": market_id, "ticker": ticker, **values}
        if unchanged:
            no_op.append(entry)
            continue
        # The version this write is approved on: the whole row, bound into the
        # digest with the values it will receive.
        entry["approved_before"] = cur[6]
        planned.append(entry)
    return {
        "planned": planned,
        "no_op": no_op,
        "stop_not_settled_from_archive": stop,
        "voids_reported_not_written": sorted(set(recorder.voids)),
        "walk_stats": {k: v for k, v in stats.items() if v},
    }


def _values(entry: dict) -> dict:
    """A plan entry without its approved before-image: what the write applies."""
    return {k: v for k, v in entry.items() if k != "approved_before"}


def plan_digest(planned: list[dict], *, manifest_sha256: str = MANIFEST_SHA256) -> str:
    body = manifest_sha256 + "|" + json.dumps(
        sorted(planned, key=lambda p: p["market_id"]), sort_keys=True
    )
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def refuse_unless_named_app(env) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app != REQUIRED_APP:
        raise Refused(f"HEROKU_APP_NAME={app!r}; writes run only on {REQUIRED_APP}")


async def backup(
    session, planned: list[dict], digest: str, *, table: str = BACKUP_TABLE
) -> list[int]:
    """Freeze the plan: each row is backed up only if it is still EXACTLY its
    approved before-image. Returns the ids that drifted (empty = all frozen)."""
    from sqlalchemy import text

    sql = channel_sql(table)
    await session.execute(text(sql["bak_create"]))
    if (await session.execute(text(sql["competing"]), {"digest": digest})).scalar_one():
        raise Refused("another plan's applied rows are still held; restore it first")
    for p in planned:
        before = p.get("approved_before")
        if not before:
            raise Refused(f"market {p['market_id']} has no approved before-image")
        await session.execute(
            text(sql["bak_copy"]),
            {"market_id": p["market_id"], "ticker": p["ticker"], "digest": digest,
             "planned": json.dumps(_values(p), sort_keys=True), "approved_before": before},
        )
    return [r[0] for r in (await session.execute(
        text(sql["bak_missing"]),
        {"ids": [p["market_id"] for p in planned], "digest": digest},
    )).all()]


async def apply(session, digest: str, *, table: str = BACKUP_TABLE) -> dict:
    """Write the FROZEN plan only — never a re-plan — each row by whole-row CAS."""
    from sqlalchemy import text

    sql = channel_sql(table)
    frozen = (await session.execute(text(sql["frozen"]), {"digest": digest})).all()
    written, skipped = [], []
    for market_id, planned in frozen:
        p = planned if isinstance(planned, dict) else json.loads(planned)
        row = (await session.execute(
            text(sql["apply_one"]),
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
            text(sql["mark_applied"]),
            {"after_row": after, "market_id": market_id, "digest": digest},
        )
        written.append(market_id)
    return {"written_ids": written, "skipped_changed_since_backup": skipped}


async def restore(session) -> list[int]:
    return (await restore_report(session))["restored"]


async def restore_report(session, *, table: str = BACKUP_TABLE) -> dict:
    from sqlalchemy import text

    sql = channel_sql(table)
    if not (await session.execute(text(sql["bak_exists"]))).scalar_one():
        raise Refused(f"{table} does not exist; nothing was applied")
    restored = [r[0] for r in (await session.execute(text(sql["restore"]))).all()]
    if restored:
        await session.execute(text(sql["close_restored"]), {"ids": restored})
    preserved = [r[0] for r in (await session.execute(text(sql["close_lost"]))).all()]
    return {"restored": restored, "preserved_changed_since_apply": preserved}


async def status() -> dict:
    """Read-only readback of this channel's backup rows for the exact nine."""
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session(
        statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
    ) as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        exists = (await session.execute(text(SQL["bak_exists"]))).scalar_one()
        rows = (await session.execute(
            text(STATUS_SQL), {"ids": STATUS_IDS})).mappings().all() if exists else []
        await session.rollback()
    return {
        "backup_table": BACKUP_TABLE if exists else "absent",
        "rows": [{k: _iso(v) if isinstance(v, datetime) else v for k, v in r.items()} for r in rows],
    }


async def run(args, env) -> dict:
    from sqlalchemy.exc import DBAPIError

    from app.tasks.base import get_task_session

    out: dict = {"manifest_sha256": MANIFEST_SHA256}
    if args.status:
        if args.backup or args.apply or args.restore:
            raise Refused("--status is the read-only readback; it takes no write flag")
        out.update(await status())
        return out
    if args.restore:
        refuse_unless_named_app(env)
        phase = "restore"
        try:
            async with get_task_session(
                statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
            ) as session:
                out.update(await restore_report(session))
                phase = "restore-commit"
                await session.commit()
                phase = "done"
        except Exception as exc:
            if phase == "restore-commit":
                raise _unknown(phase, exc) from exc
            if phase == "restore" and isinstance(exc, DBAPIError):
                raise _stopped("restore", exc, "no row was restored and no marker closed") from exc
            raise  # "done": the restore is durable; never report it as rolled back
        return out

    evidence = load_evidence()
    try:
        async with get_task_session(
            statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
        ) as session:
            plan = await build_plan(session, evidence, now=datetime.now(timezone.utc))
    except DBAPIError as exc:
        raise _stopped("plan", exc, "nothing was read into a plan and nothing written") from exc
    digest = plan_digest(plan["planned"])
    out.update(plan, plan_digest=digest)
    # Printed with each approved version as its hash; the digest covers the row.
    out["planned"] = [
        {**_values(p), "approved_before_sha256": hashlib.sha256(p["approved_before"].encode()).hexdigest()}
        for p in plan["planned"]
    ]
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
    phase = "backup"
    try:
        async with get_task_session(
            statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
        ) as session:
            drifted = await backup(session, plan["planned"], digest)
            if drifted:
                await session.rollback()
                raise Refused(
                    f"rows changed since the plan was approved: {drifted}; nothing written "
                    "— re-plan and re-review"
                )
            phase = "backup-commit"
            await session.commit()
            phase = "apply"
            out["applied"] = await apply(session, digest)
            phase = "apply-commit"
            await session.commit()
            phase = "done"
    except Exception as exc:
        if phase in _UNKNOWN_AFTER:
            raise _unknown(phase, exc, digest) from exc
        if phase == "backup" and isinstance(exc, DBAPIError):
            raise _stopped("backup", exc, "nothing was backed up or written") from exc
        if phase == "apply" and isinstance(exc, DBAPIError):
            raise _stopped(
                "apply", exc,
                f"no row of futures_markets was written; the backup for plan {digest} "
                "stays committed and unapplied, so there is nothing to restore",
            ) from exc
        raise  # "done": the apply is durable; never report it as rolled back
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
    p.add_argument("--status", action="store_true",
                   help="read back this channel's backup rows (read-only, no DDL)")
    args = p.parse_args(argv)
    try:
        out = asyncio.run(run(args, os.environ))
    except Unknown as exc:
        print(json.dumps({
            "outcome": "UNKNOWN", "phase": exc.phase, "plan_digest": exc.digest,
            "unknown": str(exc),
            "readback": f"heroku run:detached -a {REQUIRED_APP} -- python3 "
                        "scripts/repair_2722_archived_nine.py --status",
        }))
        return 3
    except Refused as exc:
        print(json.dumps({"refused": str(exc)}))
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 1 if out.get("stop") else 0


if __name__ == "__main__":
    raise SystemExit(main())
