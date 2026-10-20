"""#1853 — grade a settled Kalshi event's never-graded legs from RETAINED archive bytes.

PILLAR: TRUTH. SHIP: a settled Kalshi question gets its venue-backed result
instead of remaining ungraded.

THE SPECIMEN. ``KXUECLSCORE-26JUL30LEVIFK`` (market 59280512). The venue's
exhausted exact-event archive listing (retained 2026-10-15, sha256 pinned below)
holds all 30 legs finalized on a binary result: 29 ``no``, 1 ``yes``. 8 stored
legs already carry ``api_settlement`` (including the lone ``yes``); 22 stayed
``resolution_source = NULL`` / ``is_winner = NULL`` because the live grader's
event read came back legless once the venue archived the markets. This script
plans ONLY those 22 legs — all ``no`` — from the retained bytes. It recovers no
new WINNER, and it does not claim the event's place in any grader cohort.

THE DECISION IS SHARED, THE WRITE IS NOT. :func:`app.utils.kalshi_archive_grades.
plan_archive_grades` decides which legs may be graded, for this script and for
the grader's dormant archive arm alike. The WRITE here is this script's own,
under the ownership contract above ``SQL`` (CERT-4149 + Root, 2026-10-16): a
frozen approved set, a whole-row compare-and-set on each backed-up before-image,
the whole after-image recorded, and an undo that touches only rows still holding
it. The live arm's "still ungraded" CAS is not enough for an undoable repair.

MODES (attended; nothing here runs on a schedule):

    # 1. plan (read-only): prints the plan and its digest
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_1853_archive_grades.py
    # 2. apply: backup first, then the planned legs only — the digest must match
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_1853_archive_grades.py --backup --apply --digest <D>
    # 3. undo: puts back every leg still exactly as the apply wrote it
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_1853_archive_grades.py --restore
    # 4. status (read-only): what the backup table says each phase left durable
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_1853_archive_grades.py --status

``--backup`` / ``--apply`` / ``--restore`` refuse unless ``HEROKU_APP_NAME`` is
``bainluck-heavy``. The backup table is runtime DDL created only by an attended
invocation (notice 47(c)): never by a deploy.

A COMMIT THAT DOES NOT RETURN IS UNKNOWN (exit 3). The server can make a COMMIT
durable and its acknowledgement still be lost, and a rollback sent afterwards
proves nothing about it. So every write phase (backup, apply, restore) records
whether it is still running, has SENT its COMMIT, or had it acknowledged, and
whatever ends the run, the receipt prints the plan's identity, the exact set the
phase carried and each phase's state: ``committed`` (acknowledged),
``UNKNOWN`` (sent, never acknowledged) or ``not_committed`` (it stopped before
its COMMIT was sent, so its transaction cannot have committed). Nothing is
retried, restored or written again; ``--status`` reads the answer back. A cancel
or interrupt prints the same receipt and keeps propagating as itself. The write
session leaves ``get_task_session`` by its exception path after any failure, so
the wrapper's normal-exit COMMIT is never sent behind an unacknowledged one; a
failure in the wrapper's cleanup — after an UNKNOWN, or after every COMMIT was
acknowledged — is noted on stderr and changes neither the receipt nor its exit;
an interrupt there still propagates as itself. A refusal is the same: the phase
records it before anything rolls back, so a rollback failing on a dead
connection never replaces the refusal, its reason or its exit 2.

THE PLAN READ IS BOUNDED AND READ ONLY (Root, 2026-10-20). Its session carries
its own statement and lock budgets through ``get_task_session``'s keyword
channel (#4482) — never the helper's resting thirty minutes and unbounded lock
wait — and declares ``SET TRANSACTION READ ONLY`` before its first data read.
That is the same read in plan mode and at the top of ``--apply``, so the digest
an apply re-derives comes from the same bounded read that was reviewed. A plan
that times out, waits too long for a lock or is cancelled stops there: no
digest is printed, no write session opens, nothing is committed. The write,
restore and status sessions are unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import NamedTuple, Optional

EVENT_TICKER = "KXUECLSCORE-26JUL30LEVIFK"
ARCHIVE_PATH = Path(__file__).parent / "data" / "1853-KXUECLSCORE-26JUL30LEVIFK-archive.json"
ARCHIVE_SHA256 = "80b3540db0c39dd2894207625eee742a8033eec59725e0c82158accc1217c543"
#: The plan the retained bytes and the 2026-10-15 stored read prove. A plan of a
#: different size means the stored legs moved; the script stops and says so.
EXPECTED_PLAN = 22
REQUIRED_APP = "bainluck-heavy"
BACKUP_TABLE = "backup_1853_archive_grades"
_SCRIPT = "scripts/repair_1853_archive_grades.py"
UNDO_COMMAND = f"heroku run:detached -a {REQUIRED_APP} -- python3 {_SCRIPT} --restore"
STATUS_COMMAND = f"heroku run:detached -a {REQUIRED_APP} -- python3 {_SCRIPT} --status"
#: The plan session's budgets, in milliseconds: a plan reads one event's 30 legs,
#: so a statement past two seconds or a lock wait past half a second is refused
#: rather than waited out. Proposed source bounds, not a production measurement.
PLAN_STATEMENT_TIMEOUT_MS = 2_000
PLAN_LOCK_TIMEOUT_MS = 500

#: THE OWNERSHIP CONTRACT (CERT-4149 + Root's three counterexamples, 2026-10-16).
#:
#: * The PLAN binds each leg's approved version (Root 004): its WHOLE row
#:   (``to_jsonb``) is read with the plan and its hash rides the digest, so a
#:   leg that moves between the reviewed dry run and the apply changes the
#:   digest and the reviewed ``--digest`` is refused.
#: * The approved set is FROZEN at backup: the plan's ids, verdicts and digest,
#:   and each row's FULL before-image — backed up only while the row still IS
#:   its approved version. A writer between planning and backup (Root 004: a
#:   price 0.47 -> 0.61 on a still-ungraded leg) is named and refused, never
#:   adopted as a new baseline. Apply reads that set back and never re-plans,
#:   so a row that becomes ungraded after the review (Root: control 220314801
#:   retracted) is not written.
#: * Apply is a compare-and-set on the WHOLE row: it writes only while the row
#:   still equals its backed-up before-image AND is still ungraded. A price
#:   that moved after the backup (Root: 0.47 -> 0.61) is skipped, never written
#:   over, so the undo can never reinstall a stale value.
#: * Apply records the FULL after-image it produced. Restore puts a row back
#:   only while it still equals that after-image exactly — any later writer,
#:   including one confirming the identical grade with a later stamp, or one
#:   touching any other column, is reported and preserved.
#: * Markers end with the operation: a restore clears ``applied`` and the
#:   after-image, and a row whose ownership was lost is closed, so a retry or
#:   a second undo can never act on a stale marker (CERT-4149's apply-undo-
#:   retry case).
SQL = {
    "bak_create": f"""
        CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
            outcome_id bigint PRIMARY KEY,
            plan_digest text NOT NULL,
            planned_is_winner boolean NOT NULL,
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
        INSERT INTO {BACKUP_TABLE} (outcome_id, plan_digest, planned_is_winner, before_row)
        SELECT fo.id, :digest, :planned, to_jsonb(fo)
        FROM futures_outcomes fo
        WHERE fo.id = :outcome_id
          AND fo.resolution_source IS NULL AND fo.is_winner IS NULL
          -- Root 004: only the version the plan was approved on is frozen.
          AND to_jsonb(fo) = CAST(:approved_before AS jsonb)
        ON CONFLICT (outcome_id) DO NOTHING
    """,
    # Planned legs NOT frozen at their approved version: no backup row for
    # this digest holding exactly that version, or the row itself is no longer
    # it. The second arm is what a retry needs — its frozen row already exists,
    # so presence alone proves nothing about the row as it stands now.
    "bak_unfrozen": f"""
        SELECT a.id FROM unnest(CAST(:ids AS bigint[]), CAST(:images AS text[])) AS a(id, image)
        WHERE NOT EXISTS (
            SELECT 1 FROM {BACKUP_TABLE} b
            WHERE b.outcome_id = a.id AND b.plan_digest = :digest
              AND b.before_row = CAST(a.image AS jsonb))
           OR NOT EXISTS (
            SELECT 1 FROM futures_outcomes fo
            WHERE fo.id = a.id AND to_jsonb(fo) = CAST(a.image AS jsonb))
        ORDER BY a.id
    """,
    # Each planned leg's whole row, read with the plan: the approved version.
    "approved": """
        SELECT fo.id, to_jsonb(fo)::text FROM futures_outcomes fo
        WHERE fo.id = ANY(CAST(:ids AS bigint[]))
          AND fo.resolution_source IS NULL AND fo.is_winner IS NULL
    """,
    "bak_missing": f"""
        SELECT COUNT(*) FROM unnest(CAST(:ids AS bigint[])) AS t(id)
        WHERE NOT EXISTS (
            SELECT 1 FROM {BACKUP_TABLE} b
            WHERE b.outcome_id = t.id AND b.plan_digest = :digest)
    """,
    "bak_exists": f"SELECT to_regclass('{BACKUP_TABLE}') IS NOT NULL",
    "frozen": f"""
        SELECT outcome_id, planned_is_winner FROM {BACKUP_TABLE}
        WHERE plan_digest = :digest AND NOT applied AND ownership_lost_at IS NULL
        ORDER BY outcome_id
    """,
    # One leg: the live arm's own values, only while the row is still exactly
    # its backed-up before-image and still ungraded. The row lock this UPDATE
    # takes makes the comparison and the write one step.
    "apply_one": """
        UPDATE futures_outcomes fo
        SET is_winner = :is_winner,
            resolution_source = 'api_settlement',
            last_updated = NOW(),
            {settled}
        FROM {table} b
        WHERE fo.id = :outcome_id
          AND b.outcome_id = fo.id AND b.plan_digest = :digest
          AND NOT b.applied AND b.ownership_lost_at IS NULL
          AND to_jsonb(fo) = b.before_row
          AND fo.resolution_source IS NULL AND fo.is_winner IS NULL
        RETURNING to_jsonb(fo) AS after_row
    """,
    "mark_applied": f"""
        UPDATE {BACKUP_TABLE}
        SET applied = true, applied_at = NOW(), after_row = CAST(:after_row AS jsonb),
            restored_at = NULL
        WHERE outcome_id = :outcome_id AND plan_digest = :digest
    """,
    # Undo only rows still holding EXACTLY what this operation wrote.
    "restore": f"""
        UPDATE futures_outcomes fo
        SET resolution_source = b.before_row->>'resolution_source',
            is_winner = (b.before_row->>'is_winner')::boolean,
            current_probability = (b.before_row->>'current_probability')::numeric,
            current_american_odds = (b.before_row->>'current_american_odds')::integer,
            price_changed_at = (b.before_row->>'price_changed_at')::timestamptz,
            last_updated = (b.before_row->>'last_updated')::timestamptz
        FROM {BACKUP_TABLE} b
        WHERE fo.id = b.outcome_id AND b.applied AND to_jsonb(fo) = b.after_row
        RETURNING fo.id
    """,
    "close_restored": f"""
        UPDATE {BACKUP_TABLE}
        SET applied = false, after_row = NULL, restored_at = NOW()
        WHERE outcome_id = ANY(CAST(:ids AS bigint[]))
    """,
    # Applied rows a later writer changed: no longer this operation's to undo.
    "close_lost": f"""
        UPDATE {BACKUP_TABLE}
        SET applied = false, ownership_lost_at = NOW()
        WHERE applied
        RETURNING outcome_id
    """,
    # Read-only: what each phase left durable. The backup, the apply and the
    # restore each commit as ONE transaction with their markers, so a frozen
    # row, an ``applied`` flag or a ``restored_at`` stamp answers whether that
    # phase's COMMIT landed — no write needed to find out.
    "status": f"""
        SELECT b.outcome_id, b.plan_digest, b.planned_is_winner, b.applied,
               b.backed_up_at, b.applied_at, b.restored_at, b.ownership_lost_at,
               fo.id IS NOT NULL AS row_exists,
               COALESCE(to_jsonb(fo) = b.before_row, false) AS holds_before,
               COALESCE(to_jsonb(fo) = b.after_row, false) AS holds_after
        FROM {BACKUP_TABLE} b
        LEFT JOIN futures_outcomes fo ON fo.id = b.outcome_id
        ORDER BY b.plan_digest, b.outcome_id
    """,
}


class Refused(RuntimeError):
    pass


#: A write phase's state. ``_RUNNING``: its statements are in flight and no
#: COMMIT has been sent. ``_SENT``: the COMMIT went out and has not come back.
_RUNNING, _SENT, _COMMITTED = "running", "commit_sent", "committed"
_RECEIPT_STATE = {_RUNNING: "not_committed", _SENT: "UNKNOWN", _COMMITTED: "committed"}


class Progress:
    """What the write session has done so far: the receipt if the run never returns.

    ``out`` is the run's output as it is built. ``failure`` is the exception
    that stopped a phase — the COMMIT's own, never the session wrapper's cleanup
    raised after it, which happens outside every phase.
    """

    def __init__(self) -> None:
        self.out: dict = {"event_ticker": EVENT_TICKER, "archive_sha256": ARCHIVE_SHA256}
        self.mode: Optional[str] = None
        self.phases: dict[str, str] = {}
        self.failure: Optional[BaseException] = None

    @contextlib.contextmanager
    def phase(self, name: str):
        self.phases[name] = _RUNNING
        try:
            yield
        except BaseException as exc:
            self.failure = exc
            raise

    async def commit(self, session, name: str) -> None:
        self.phases[name] = _SENT
        await session.commit()
        self.phases[name] = _COMMITTED

    @property
    def unknown(self) -> bool:
        return _SENT in self.phases.values()

    def receipt(self) -> dict:
        """The run's output so far, with the state each phase reached.

        After a failed phase there is no ``undo`` line: whether there is anything
        to undo is what ``--status`` answers. A COMMIT that never came back is
        neither done nor not done.
        """
        out = {k: v for k, v in self.out.items() if k != "undo" or self.failure is None}
        if self.failure is None:
            outcome = "COMMITTED"
        elif self.unknown:
            outcome = "UNKNOWN"
        elif isinstance(self.failure, Refused):
            outcome = "REFUSED"
        else:
            outcome = "NOT_COMMITTED"
        out.update({
            "outcome": outcome,
            "mode": self.mode,
            "phases": {k: _RECEIPT_STATE[v] for k, v in self.phases.items()},
        })
        if self.failure is not None:
            if isinstance(self.failure, Refused):
                out["refusal"] = str(self.failure)
            out["error"] = f"{type(self.failure).__name__}: {self.failure}"
            out["readback"] = STATUS_COMMAND
            out["note"] = (
                "Not retried, not restored. A phase marked UNKNOWN sent its COMMIT and "
                "never heard back: its writes may or may not be durable. Read them back "
                "with the status command before any further step."
                if self.unknown else
                "Every phase marked committed was acknowledged; the phase marked "
                "not_committed stopped before its COMMIT was sent, so none of its "
                "writes are durable. Nothing was retried."
            )
        return out


class ApprovedGrade(NamedTuple):
    """A planned grade bound to the WHOLE row version it was approved on.

    The shared planner's :class:`~app.utils.kalshi_archive_grades.ArchiveGrade`
    fields, plus ``approved_before`` (``to_jsonb(row)::text``) — the version the
    digest covers and the backup must still find.
    """

    outcome_id: int
    ticker: str
    is_winner: bool
    status: Optional[str]
    result: Optional[str]
    approved_before: str


def _approved_before(g) -> str:
    before = getattr(g, "approved_before", None)
    if not before:
        raise Refused(f"outcome {g.outcome_id} carries no approved version; re-plan")
    return before


def load_archive_legs(path: Path = ARCHIVE_PATH, event_ticker: str = EVENT_TICKER) -> list[dict]:
    """The retained listing, held to the same proof the live primitive demands.

    The bytes must hash to the pinned value, the listing must be exhausted (an
    empty cursor), every leg must name the event, and no ticker may repeat.
    """
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != ARCHIVE_SHA256:
        raise Refused(f"archive bytes hash {digest}, expected {ARCHIVE_SHA256}")
    body = json.loads(raw)
    if body.get("cursor"):
        raise Refused("retained listing was not exhausted (non-empty cursor)")
    legs = body.get("markets")
    if not isinstance(legs, list) or not legs:
        raise Refused("retained listing holds no legs")
    seen: set = set()
    for leg in legs:
        if leg.get("event_ticker") != event_ticker:
            raise Refused(f"leg {leg.get('ticker')!r} names another event")
        if leg.get("ticker") in seen:
            raise Refused(f"ticker {leg.get('ticker')!r} repeats")
        seen.add(leg.get("ticker"))
    return legs


def approved_sha256(g) -> str:
    return hashlib.sha256(_approved_before(g).encode()).hexdigest()


def plan_digest(grades) -> str:
    """The plan's identity: the archive bytes plus every planned (id, verdict,
    approved version) — a leg that moves after review is a different plan."""
    body = ARCHIVE_SHA256 + "|" + ",".join(
        f"{g.outcome_id}:{int(g.is_winner)}:{approved_sha256(g)}"
        for g in sorted(grades, key=lambda g: g.outcome_id)
    )
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def refuse_unless_named_app(env) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app != REQUIRED_APP:
        raise Refused(f"HEROKU_APP_NAME={app!r}; writes run only on {REQUIRED_APP}")


@contextlib.asynccontextmanager
async def plan_session():
    """The plan's session: bounded per statement and per lock wait, and READ ONLY
    before any data is read. A timeout, lock refusal or cancel leaves by the
    wrapper's exception path, so nothing after it runs."""
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session(
        statement_timeout_ms=PLAN_STATEMENT_TIMEOUT_MS,
        lock_timeout_ms=PLAN_LOCK_TIMEOUT_MS,
    ) as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        yield session


async def build_plan(session, legs):
    from sqlalchemy import text

    from app.tasks.backfill_winners import _ARCHIVE_STORED_LEGS_SQL
    from app.utils.kalshi_archive_grades import plan_archive_grades, stored_legs

    rows = (await session.execute(
        text(_ARCHIVE_STORED_LEGS_SQL), {"event_ticker": EVENT_TICKER}
    )).all()
    grades, refused = plan_archive_grades(legs, stored_legs(rows))
    # Bind each planned leg to the whole row it was approved on. A leg graded
    # or removed between the two reads is not the plan's to approve.
    approved = dict((await session.execute(
        text(SQL["approved"]), {"ids": [g.outcome_id for g in grades]}
    )).all())
    moved = sorted(g.outcome_id for g in grades if g.outcome_id not in approved)
    if moved:
        raise Refused(f"legs {moved} changed while the plan was read; re-plan")
    return [
        ApprovedGrade(g.outcome_id, g.ticker, g.is_winner, g.status, g.result,
                      approved[g.outcome_id])
        for g in grades
    ], refused


async def unfrozen(session, grades, digest) -> list[int]:
    """Planned legs not frozen under ``digest`` at their approved version."""
    from sqlalchemy import text

    return [r[0] for r in (await session.execute(
        text(SQL["bak_unfrozen"]),
        {"ids": [g.outcome_id for g in grades],
         "images": [_approved_before(g) for g in grades], "digest": digest},
    )).all()]


async def backup(session, grades, digest) -> int:
    """Freeze the approved set: ids, verdicts, digest and each FULL before-image
    — only while each row still IS the version the plan was approved on.

    A leg that changed since the plan (any column) is refused and named: never
    adopted as a new baseline. The refusal leaves the write session by its
    exception path, so the session wrapper rolls back; re-plan and re-review.
    """
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    for g in grades:
        await session.execute(
            text(SQL["bak_copy"]),
            {"outcome_id": g.outcome_id, "planned": g.is_winner, "digest": digest,
             "approved_before": _approved_before(g)},
        )
    drifted = await unfrozen(session, grades, digest)
    if drifted:
        raise Refused(
            f"legs {drifted} changed since the plan was approved; nothing written "
            "— re-plan and re-review"
        )
    missing = (await session.execute(
        text(SQL["bak_missing"]),
        {"ids": [g.outcome_id for g in grades], "digest": digest},
    )).scalar_one()
    return int(missing)


async def apply(session, legs, digest) -> dict:
    """Write the FROZEN approved legs — never a re-plan — each by whole-row CAS.

    ``legs`` (the retained listing) re-confirms every frozen verdict: a frozen
    row whose venue verdict no longer matches is refused, not written.
    """
    import json as _json

    from sqlalchemy import text

    from app.utils import kalshi_market_status as kms
    from app.utils.settled_price import (
        SETTLED_NO_PRICE,
        SETTLED_YES_PRICE,
        settled_price_set_sql,
    )

    by_ticker = {leg["ticker"]: leg for leg in legs}
    frozen = (await session.execute(text(SQL["frozen"]), {"digest": digest})).all()
    tickers = dict((await session.execute(
        text("SELECT id, external_id FROM futures_outcomes "
             "WHERE id = ANY(CAST(:ids AS bigint[]))"),
        {"ids": [r[0] for r in frozen]},
    )).all())
    written: list[int] = []
    skipped: list[int] = []
    for outcome_id, planned in frozen:
        leg = by_ticker.get(tickers.get(outcome_id))
        verdict = kms.gradeable_winner(leg.get("status"), leg.get("result")) if leg else None
        if verdict is None or verdict != planned:
            raise Refused(f"outcome {outcome_id}: frozen verdict no longer matches the listing")
        sql = SQL["apply_one"].format(
            settled=settled_price_set_sql(
                SETTLED_YES_PRICE if planned else SETTLED_NO_PRICE, alias="fo"
            ),
            table=BACKUP_TABLE,
        )
        row = (await session.execute(
            text(sql), {"is_winner": planned, "outcome_id": outcome_id, "digest": digest}
        )).first()
        if row is None:
            skipped.append(outcome_id)
            continue
        after = row[0] if isinstance(row[0], str) else _json.dumps(row[0])
        await session.execute(
            text(SQL["mark_applied"]),
            {"after_row": after, "outcome_id": outcome_id, "digest": digest},
        )
        written.append(outcome_id)
    return {"written_ids": written, "skipped_changed_since_backup": skipped}


async def restore(session) -> list[int]:
    """The ids put back (see :func:`restore_report` for what was preserved)."""
    return (await restore_report(session))["restored"]


async def restore_report(session) -> dict:
    """Undo every row still holding exactly this repair's after-image; report the rest."""
    from sqlalchemy import text

    if not (await session.execute(text(SQL["bak_exists"]))).scalar_one():
        raise Refused(f"{BACKUP_TABLE} does not exist; nothing was applied")
    restored = [r[0] for r in (await session.execute(text(SQL["restore"]))).all()]
    if restored:
        await session.execute(text(SQL["close_restored"]), {"ids": restored})
    preserved = [r[0] for r in (await session.execute(text(SQL["close_lost"]))).all()]
    return {"restored": restored, "preserved_changed_since_apply": preserved}


async def status_report(session) -> dict:
    """Read-only: per digest, what the backup, apply and restore left durable.

    Resolves an UNKNOWN receipt without writing: a digest's frozen rows exist
    only if its backup committed; ``applied`` (with ``holds_after``) only if its
    apply committed; ``restored`` only if a restore committed. No backup table
    means no backup ever committed.
    """
    from sqlalchemy import text

    if not (await session.execute(text(SQL["bak_exists"]))).scalar_one():
        return {"backup_table": "absent", "digests": {}}
    digests: dict = {}
    for r in (await session.execute(text(SQL["status"]))).mappings().all():
        d = digests.setdefault(r["plan_digest"], {
            "frozen": 0, "applied": 0, "holds_after": 0, "holds_before": 0,
            "restored": 0, "ownership_lost": 0, "rows": [],
        })
        d["frozen"] += 1
        d["applied"] += bool(r["applied"])
        d["holds_after"] += bool(r["holds_after"])
        d["holds_before"] += bool(r["holds_before"])
        d["restored"] += r["restored_at"] is not None
        d["ownership_lost"] += r["ownership_lost_at"] is not None
        d["rows"].append({k: r[k] for k in (
            "outcome_id", "planned_is_winner", "applied", "row_exists", "holds_before",
            "holds_after", "backed_up_at", "applied_at", "restored_at", "ownership_lost_at",
        )})
    return {"backup_table": "present", "digests": digests}


async def run(args, env, progress: Optional[Progress] = None) -> dict:
    from app.tasks.base import get_task_session

    progress = progress if progress is not None else Progress()
    out = progress.out
    if args.status:
        async with get_task_session() as session:
            out.update(await status_report(session))
            await session.rollback()
        return out
    if args.restore:
        refuse_unless_named_app(env)
        progress.mode = "restore"
        # Every failure leaves the block by raising, so the wrapper rolls back
        # instead of sending its normal-exit COMMIT behind this one.
        async with get_task_session() as session:
            with progress.phase("restore"):
                out.update(await restore_report(session))
                await progress.commit(session, "restore")
        return out

    legs = load_archive_legs()
    async with plan_session() as session:
        grades, refused = await build_plan(session, legs)
        await session.rollback()
    digest = plan_digest(grades)
    out.update({
        "plan_digest": digest,
        "planned": [
            {"outcome_id": g.outcome_id, "ticker": g.ticker, "is_winner": g.is_winner,
             "venue_status": g.status, "venue_result": g.result,
             "approved_before_sha256": approved_sha256(g)}
            for g in grades
        ],
        "refused": {k: v for k, v in refused.items() if v},
    })
    if len(grades) != EXPECTED_PLAN:
        out["stop"] = (
            f"plan holds {len(grades)} legs, expected {EXPECTED_PLAN}: the stored "
            "legs moved since the retained read; do not apply this plan"
        )
        return out
    if not args.apply:
        return out

    refuse_unless_named_app(env)
    if not args.backup:
        raise Refused("--apply requires --backup (D51: the undo is written first)")
    if args.digest != digest:
        raise Refused(f"--digest {args.digest!r} does not match this plan ({digest})")
    progress.mode = "apply"
    # A refusal leaves the phase BEFORE anything rolls back, so the phase records
    # it first; the wrapper's rollback then runs outside every phase, and a
    # failure there is cleanup that can never replace the refusal or its exit 2.
    async with get_task_session() as session:
        with progress.phase("backup"):
            missing = await backup(session, grades, digest)
            if missing:
                raise Refused(f"{missing} planned legs have no backup row; nothing written")
            await progress.commit(session, "backup")
        with progress.phase("apply"):
            out["applied"] = await apply(session, legs, digest)
            await progress.commit(session, "apply")
        # Acknowledged: from here only the wrapper's exit remains, and nothing
        # it raises can change what the COMMIT above made durable.
        out["undo"] = UNDO_COMMAND
    return out


def _ended_abnormally(progress: Progress, exc: BaseException) -> int:
    """Print what the write session left durable, then exit or re-raise.

    ``exc`` is what reached ``main``: the phase's own failure, or a failure in
    the session wrapper's cleanup raised on top of it (a rollback, close or
    dispose on a dead connection), which proves nothing about any COMMIT.
    """
    if not progress.phases:  # no write phase began: nothing can be durable
        if isinstance(exc, Refused):
            print(json.dumps({"refused": str(exc)}))
            return 2
        raise exc
    failure = progress.failure
    print(json.dumps(progress.receipt(), indent=2, default=str))
    if failure is None or exc is not failure:
        after = (
            "after every COMMIT above was acknowledged" if failure is None
            else f"after the {type(failure).__name__} reported above"
        )
        print(
            f"note: the task session's cleanup raised {type(exc).__name__} {after}; "
            "it changes none of them",
            file=sys.stderr,
        )
    if not isinstance(exc, Exception):
        raise exc  # an interrupt or cancel keeps propagating as itself
    if failure is None:
        return 0
    if not isinstance(failure, Exception):
        raise failure  # a cancel on a phase keeps its type under a cleanup failure
    if progress.unknown:
        return 3
    if isinstance(failure, Refused):
        return 2
    raise failure


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true", help="write the undo table first")
    p.add_argument("--apply", action="store_true", help="write the planned legs")
    p.add_argument("--digest", default="", help="the plan digest printed by a plan run")
    p.add_argument("--restore", action="store_true", help="undo an apply")
    p.add_argument("--status", action="store_true",
                   help="read-only: what each phase left durable")
    args = p.parse_args(argv)
    if args.status and (args.backup or args.apply or args.restore):
        print(json.dumps({"refused": "--status is read-only; it takes no write flag"}))
        return 2
    progress = Progress()
    try:
        out = asyncio.run(run(args, os.environ, progress))
    except BaseException as exc:
        return _ended_abnormally(progress, exc)
    print(json.dumps(out, indent=2, default=str))
    return 1 if out.get("stop") else 0


if __name__ == "__main__":
    raise SystemExit(main())
