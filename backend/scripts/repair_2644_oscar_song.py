"""#2644 — the decided 2026 Best Original Song question stops appearing Open, reversibly.

PILLAR: TRUTH. SHIP: the decided 2026 Best Original Song question stops
appearing Open with a December resolution date, through an exact-id reversible
lifecycle correction.

THE ONE ROW. ``futures_markets`` 109548, source ``kalshi``, external_id
``KXOSCARSONG-26``. The venue's live event read names the event and returns no
legs; its exhausted archive listing holds all 16 legs finalized (15 no, 1 yes:
Golden), whose rules name Best Music (Original Song) at the 98th Academy
Awards. #2722's archive walk (merged, inactive) settles exactly this shape —
the 006 replay — but the walk keeps no before-image, and #2722's attended rail
is frozen to nine OTHER ids. This is that rail's second channel: its own
member, its own retained evidence and manifest hash, its own digest and its own
backup table. Neither channel's restore can touch the other's rows.

THE WRITE IS THE WALK'S. The plan runs the merged ``run_backfill``
(``archive_only``) over the row as stored, the venue answered ONLY from the
retained bytes, its writes recorded instead of made — the nine-row rail's
``build_plan``, unchanged. Backup, the whole-row compare-and-set apply and the
after-image restore are that rail's too, pointed at this channel's table. So
the lifecycle, CAS and undo are the certified code, not a copy. On top, this
channel freezes what review saw (006):

* the retained authority is the exact event: every leg names
  ``KXOSCARSONG-26``, the listing is exhausted, all 16 legs are finalized with a
  15/1 result, every rule names the award and the 98th edition, and the live
  event answer names the ticker with no legs;
* the walk's write must BE the reviewed transition — status resolved,
  resolution_date 2026-03-16T02:11:07Z (the last terminal close), the December
  31 legal expiration kept in ``expiration_time`` — or the plan stops;
* a void the walk would record stops the plan (a void is not this repair).

Status, dates and ``settled_at`` only: no grade, price, snapshot or metadata.
``settled_at`` is when OUR row flipped (``COALESCE(settled_at, NOW())``), never
the venue's March settlement stamp.

MODES (attended; nothing here runs on a schedule, the beat's ``archive_walk``
stays False, and the default is a read-only plan with no DDL and no write):

    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_2644_oscar_song.py
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_2644_oscar_song.py --backup --apply --digest <D>
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_2644_oscar_song.py --restore
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_2644_oscar_song.py --status

Writes refuse unless ``HEROKU_APP_NAME`` is ``bainluck-heavy``; the backup table
is runtime DDL created only by an attended ``--backup`` (notice 47(c)).

EVERY SESSION IS BOUNDED (#4482): plan, backup/apply, restore and status each
open ``get_task_session`` with ``STATEMENT_TIMEOUT_MS`` / ``LOCK_TIMEOUT_MS``,
which ride the startup packet and so survive every commit and reconnect. A
budget that fires refuses by phase; nothing retries and nothing restores on
its own. A COMMIT that does not return is neither: its outcome is UNKNOWN, the
run says so and stops, and ``--status`` is the readback.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import repair_2722_archived_nine as rail  # noqa: E402

#: The one reviewed row: (futures_markets.id, external_id).
MEMBERS: tuple[tuple[int, str], ...] = ((109548, "KXOSCARSONG-26"),)
TICKER = MEMBERS[0][1]
EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kalshi_2644_oscar_song"
MANIFEST_SHA256 = "836611e27df0c76afbb47dc25f5515da9ee24d893ad29bc113c0ef7fc32e4640"
BACKUP_TABLE = "backup_2644_oscar_song"
REQUIRED_APP = rail.REQUIRED_APP
STATEMENT_TIMEOUT_MS = rail.STATEMENT_TIMEOUT_MS
LOCK_TIMEOUT_MS = rail.LOCK_TIMEOUT_MS
#: The reviewed transition (006): what the walk's write must be, value for value.
REVIEWED_WRITE = {
    "market_id": 109548,
    "ticker": "KXOSCARSONG-26",
    "resolution_date": "2026-03-16T02:11:07+00:00",
    "expiration_time": "2026-12-31T15:00:00+00:00",
    "venue_settled": True,
}
#: The retained archive's reviewed shape.
ARCHIVE_LEGS = 16
ARCHIVE_RESULTS = {"no": 15, "yes": 1}
RULE_PHRASES = ("Best Music (Original Song)", "98th Academy Awards")

Refused = rail.Refused

STATUS_SQL = f"""
    SELECT b.market_id, b.plan_digest, b.applied, b.backed_up_at, b.applied_at,
           b.restored_at, b.ownership_lost_at,
           to_jsonb(fm) = b.before_row AS row_is_before_image,
           b.after_row IS NOT NULL AND to_jsonb(fm) = b.after_row AS row_is_after_image,
           fm.status, fm.resolution_date, fm.expiration_time, fm.settled_at, fm.updated_at
    FROM {BACKUP_TABLE} b JOIN futures_markets fm ON fm.id = b.market_id
    ORDER BY b.market_id
"""


class Unknown(RuntimeError):
    """A commit whose acknowledgement never came back: it may or may not be durable."""


def verify_authority(event_body: dict, archive_body: dict) -> None:
    """The retained bytes are the exact, complete, terminal Oscars event."""
    event = event_body.get("event") or {}
    if event.get("event_ticker") != TICKER or event.get("series_ticker") != "KXOSCARSONG":
        raise Refused("the retained live event answer is not KXOSCARSONG-26")
    if event_body.get("markets") != []:
        raise Refused("the retained live event answer lists legs")
    legs = archive_body.get("markets")
    if not isinstance(legs, list) or not legs or archive_body.get("cursor"):
        raise Refused("the retained archive listing is empty or not exhausted")
    if any(leg.get("event_ticker") != TICKER for leg in legs):
        raise Refused("a retained archive leg names another event")
    if len({leg.get("ticker") for leg in legs}) != len(legs) or len(legs) != ARCHIVE_LEGS:
        raise Refused(f"the retained archive does not hold {ARCHIVE_LEGS} distinct legs")
    if any(leg.get("status") != "finalized" for leg in legs):
        raise Refused("a retained archive leg is not finalized")
    results = {r: sum(leg.get("result") == r for leg in legs) for r in ARCHIVE_RESULTS}
    if results != ARCHIVE_RESULTS or sum(results.values()) != len(legs):
        raise Refused(f"the retained archive results are not {ARCHIVE_RESULTS}")
    if any(not all(p in (leg.get("rules_primary") or "") for p in RULE_PHRASES) for leg in legs):
        raise Refused("a retained archive leg's rules do not name the award and edition")


def load_evidence(directory: Path = EVIDENCE_DIR) -> dict:
    """``ticker -> {"live": bytes, "archive": bytes}``: the rail's own loader under
    this channel's manifest, then the identity answer and the authority check."""
    out = rail.load_evidence(directory, manifest_sha256=MANIFEST_SHA256, members=MEMBERS)
    raw = (directory / "manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise Refused("evidence manifest changed while it was read")
    entry = json.loads(raw)["identity"]
    body = (directory / entry["file"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != entry["sha256"]:
        raise Refused(f"evidence file {entry['file']} does not match its manifest hash")
    verify_authority(json.loads(body), json.loads(out[TICKER]["archive"]))
    return out


async def build_plan(session, evidence, *, now: datetime) -> dict:
    """The rail's plan over this one member, held to the reviewed transition."""
    plan = await rail.build_plan(session, evidence, now=now, members=MEMBERS)
    stop = []
    if plan["stop_not_settled_from_archive"]:
        stop.append("the walk would not settle the row from its retained archive listing")
    if plan["voids_reported_not_written"]:
        stop.append("the walk would record a void, which this lifecycle repair never writes")
    for entry in plan["planned"] + plan["no_op"]:
        if rail._values(entry) != REVIEWED_WRITE:
            stop.append(f"the walk's write {rail._values(entry)} is not the reviewed transition")
    plan["stop"] = stop
    return plan


def plan_digest(planned: list[dict]) -> str:
    return rail.plan_digest(planned, manifest_sha256=MANIFEST_SHA256)


#: What is certain when each commit fails to return.
_UNKNOWN_AFTER = {
    "backup-commit": "the backup's durability is UNKNOWN; futures_markets was not written "
                     "(the apply had not started)",
    "apply-commit": "the apply's durability is UNKNOWN; the backup is committed",
    "restore-commit": "the restore's durability is UNKNOWN",
}


def _unknown(phase: str, exc: BaseException) -> Unknown:
    return Unknown(
        f"the {phase} did not return ({type(exc).__name__}); {_UNKNOWN_AFTER[phase]}. "
        "Not retried, not restored — read it back with --status before any further step"
    )


async def status() -> dict:
    """Read-only readback of this channel's backup rows against the live row."""
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session(
        statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
    ) as session:
        exists = (await session.execute(text(rail.channel_sql(BACKUP_TABLE)["bak_exists"]))).scalar_one()
        rows = (await session.execute(text(STATUS_SQL))).mappings().all() if exists else []
        await session.rollback()
    return {
        "backup_table": BACKUP_TABLE if exists else "absent",
        "rows": [{k: rail._iso(v) if isinstance(v, datetime) else v for k, v in r.items()} for r in rows],
    }


async def run(args, env) -> dict:
    from sqlalchemy.exc import DBAPIError

    from app.tasks.base import get_task_session

    out: dict = {"manifest_sha256": MANIFEST_SHA256, "backup_table": BACKUP_TABLE}
    if args.status:
        out.update(await status())
        return out
    if args.restore:
        rail.refuse_unless_named_app(env)
        phase = "restore"
        try:
            async with get_task_session(
                statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
            ) as session:
                out.update(await rail.restore_report(session, table=BACKUP_TABLE))
                phase = "restore-commit"
                await session.commit()
                phase = "done"
        except Exception as exc:
            if phase == "restore-commit":
                raise _unknown(phase, exc) from exc
            if phase == "restore" and isinstance(exc, DBAPIError):
                raise rail._stopped(
                    "restore", exc, "no row was restored and no marker closed") from exc
            raise  # "done": the restore is durable; never report it as rolled back
        return out

    evidence = load_evidence()
    try:
        async with get_task_session(
            statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
        ) as session:
            plan = await build_plan(session, evidence, now=datetime.now(timezone.utc))
    except DBAPIError as exc:
        raise rail._stopped("plan", exc, "nothing was read into a plan and nothing written") from exc
    stop = plan.pop("stop")
    digest = plan_digest(plan["planned"])
    out.update(plan, plan_digest=digest)
    # One row: the whole approved version is printed, and its hash.
    out["planned"] = [
        {**rail._values(p), "approved_before": json.loads(p["approved_before"]),
         "approved_before_sha256": hashlib.sha256(p["approved_before"].encode()).hexdigest()}
        for p in plan["planned"]
    ]
    if stop:
        out["stop"] = "; ".join(stop) + " — do not apply this plan"
        return out
    if not args.apply:
        return out
    rail.refuse_unless_named_app(env)
    if not args.backup:
        raise Refused("--apply requires --backup (D51: the undo is written first)")
    if args.digest != digest:
        raise Refused(f"--digest {args.digest!r} does not match this plan ({digest})")
    if not plan["planned"]:
        out["applied"] = {"written_ids": [], "skipped_changed_since_backup": []}
        return out
    phase = "backup"
    try:
        async with get_task_session(
            statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
        ) as session:
            drifted = await rail.backup(session, plan["planned"], digest, table=BACKUP_TABLE)
            if drifted:
                await session.rollback()
                raise Refused(
                    f"rows changed since the plan was approved: {drifted}; nothing written "
                    "— re-plan and re-review"
                )
            phase = "backup-commit"
            await session.commit()
            phase = "apply"
            out["applied"] = await rail.apply(session, digest, table=BACKUP_TABLE)
            phase = "apply-commit"
            await session.commit()
            phase = "done"
    except Exception as exc:
        if phase in _UNKNOWN_AFTER:
            raise _unknown(phase, exc) from exc
        if phase == "backup" and isinstance(exc, DBAPIError):
            raise rail._stopped("backup", exc, "nothing was backed up or written") from exc
        if phase == "apply" and isinstance(exc, DBAPIError):
            raise rail._stopped(
                "apply", exc,
                f"the row was not written; the backup for plan {digest} stays committed "
                "and unapplied, so there is nothing to restore",
            ) from exc
        raise  # "done": the apply is durable; never report it as rolled back
    out["undo"] = (
        f"heroku run:detached -a {REQUIRED_APP} -- python3 "
        "scripts/repair_2644_oscar_song.py --restore"
    )
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true", help="freeze the plan and its before-image")
    p.add_argument("--apply", action="store_true", help="write the frozen plan")
    p.add_argument("--digest", default="", help="the plan digest printed by a plan run")
    p.add_argument("--restore", action="store_true", help="undo an apply")
    p.add_argument("--status", action="store_true", help="read back this channel's backup rows")
    args = p.parse_args(argv)
    try:
        out = asyncio.run(run(args, os.environ))
    except Unknown as exc:
        print(json.dumps({"outcome": "UNKNOWN", "unknown": str(exc)}))
        return 3
    except Refused as exc:
        print(json.dumps({"refused": str(exc)}))
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 1 if out.get("stop") else 0


if __name__ == "__main__":
    raise SystemExit(main())
