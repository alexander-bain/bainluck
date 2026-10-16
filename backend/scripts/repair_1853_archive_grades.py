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

THE DECISION IS SHARED. :func:`app.utils.kalshi_archive_grades.plan_archive_grades`
decides which legs may be written, for this script and for the grader's dormant
archive arm alike, and the write is the grader's own ``_grade_from_archive``:
one CAS per leg on "still no grade and no source".

MODES (attended; nothing here runs on a schedule):

    # 1. plan (read-only): prints the plan and its digest
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_1853_archive_grades.py
    # 2. apply: backup first, then the planned legs only — the digest must match
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_1853_archive_grades.py --backup --apply --digest <D>
    # 3. undo: puts back every leg still exactly as the apply wrote it
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_1853_archive_grades.py --restore

``--backup`` / ``--apply`` / ``--restore`` refuse unless ``HEROKU_APP_NAME`` is
``bainluck-heavy``. The backup table is runtime DDL created only by an attended
invocation (notice 47(c)): never by a deploy.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

EVENT_TICKER = "KXUECLSCORE-26JUL30LEVIFK"
ARCHIVE_PATH = Path(__file__).parent / "data" / "1853-KXUECLSCORE-26JUL30LEVIFK-archive.json"
ARCHIVE_SHA256 = "80b3540db0c39dd2894207625eee742a8033eec59725e0c82158accc1217c543"
#: The plan the retained bytes and the 2026-10-15 stored read prove. A plan of a
#: different size means the stored legs moved; the script stops and says so.
EXPECTED_PLAN = 22
REQUIRED_APP = "bainluck-heavy"
BACKUP_TABLE = "backup_1853_archive_grades"

SQL = {
    "bak_create": f"""
        CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
            outcome_id bigint PRIMARY KEY,
            resolution_source varchar(30),
            is_winner boolean,
            current_probability numeric(7,6),
            current_american_odds integer,
            price_changed_at timestamptz,
            last_updated timestamptz,
            planned_is_winner boolean NOT NULL,
            plan_digest text NOT NULL,
            backed_up_at timestamptz NOT NULL DEFAULT NOW(),
            applied boolean NOT NULL DEFAULT false
        )
    """,
    "mark_applied": f"""
        UPDATE {BACKUP_TABLE} SET applied = true
        WHERE outcome_id = ANY(CAST(:ids AS bigint[])) AND plan_digest = :digest
    """,
    "bak_copy": f"""
        INSERT INTO {BACKUP_TABLE} (
            outcome_id, resolution_source, is_winner, current_probability,
            current_american_odds, price_changed_at, last_updated,
            planned_is_winner, plan_digest)
        SELECT fo.id, fo.resolution_source, fo.is_winner, fo.current_probability,
            fo.current_american_odds, fo.price_changed_at, fo.last_updated,
            :planned, :digest
        FROM futures_outcomes fo
        WHERE fo.id = :outcome_id
          AND fo.resolution_source IS NULL AND fo.is_winner IS NULL
        ON CONFLICT (outcome_id) DO NOTHING
    """,
    "bak_missing": f"""
        SELECT COUNT(*) FROM unnest(CAST(:ids AS bigint[])) AS t(id)
        WHERE NOT EXISTS (
            SELECT 1 FROM {BACKUP_TABLE} b
            WHERE b.outcome_id = t.id AND b.plan_digest = :digest)
    """,
    "bak_exists": f"SELECT to_regclass('{BACKUP_TABLE}') IS NOT NULL",
    # Undo only what the apply wrote and nobody has touched since.
    "restore": f"""
        UPDATE futures_outcomes fo
        SET resolution_source = b.resolution_source,
            is_winner = b.is_winner,
            current_probability = b.current_probability,
            current_american_odds = b.current_american_odds,
            price_changed_at = b.price_changed_at,
            last_updated = NOW()
        FROM {BACKUP_TABLE} b
        WHERE fo.id = b.outcome_id
          AND b.applied
          AND fo.resolution_source = 'api_settlement'
          AND fo.is_winner = b.planned_is_winner
          AND fo.current_probability = CASE WHEN b.planned_is_winner THEN 1.0 ELSE 0.0 END
        RETURNING fo.id
    """,
    "restore_count": f"SELECT COUNT(*) FROM {BACKUP_TABLE}",
}


class Refused(RuntimeError):
    pass


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


def plan_digest(grades) -> str:
    """The plan's identity: the archive bytes plus every planned (id, verdict)."""
    body = ARCHIVE_SHA256 + "|" + ",".join(
        f"{g.outcome_id}:{int(g.is_winner)}" for g in sorted(grades, key=lambda g: g.outcome_id)
    )
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def refuse_unless_named_app(env) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app != REQUIRED_APP:
        raise Refused(f"HEROKU_APP_NAME={app!r}; writes run only on {REQUIRED_APP}")


async def build_plan(session, legs):
    from sqlalchemy import text

    from app.tasks.backfill_winners import _ARCHIVE_STORED_LEGS_SQL
    from app.utils.kalshi_archive_grades import plan_archive_grades, stored_legs

    rows = (await session.execute(
        text(_ARCHIVE_STORED_LEGS_SQL), {"event_ticker": EVENT_TICKER}
    )).all()
    return plan_archive_grades(legs, stored_legs(rows))


async def backup(session, grades, digest) -> int:
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    for g in grades:
        await session.execute(
            text(SQL["bak_copy"]),
            {"outcome_id": g.outcome_id, "planned": g.is_winner, "digest": digest},
        )
    missing = (await session.execute(
        text(SQL["bak_missing"]),
        {"ids": [g.outcome_id for g in grades], "digest": digest},
    )).scalar_one()
    return int(missing)


async def apply(session, legs, digest) -> dict:
    """The grader's own archive write, then the backup rows it actually wrote
    are marked — so an undo can never revert a leg somebody else graded."""
    from sqlalchemy import text

    from app.tasks.backfill_winners import _grade_from_archive

    stats: dict = {"archive_graded": 0, "archive_refused": {}, "winners_set": 0,
                   "losers_set": 0, "expiring_graded": 0}
    written = await _grade_from_archive(
        session, EVENT_TICKER, legs, stats, dry_run=False, expiring=False
    )
    await session.execute(text(SQL["mark_applied"]), {"ids": written, "digest": digest})
    stats["written_ids"] = written
    return stats


async def restore(session) -> list[int]:
    from sqlalchemy import text

    if not (await session.execute(text(SQL["bak_exists"]))).scalar_one():
        raise Refused(f"{BACKUP_TABLE} does not exist; nothing was applied")
    return [r[0] for r in (await session.execute(text(SQL["restore"]))).all()]


async def run(args, env) -> dict:
    from app.tasks.base import get_task_session

    out: dict = {"event_ticker": EVENT_TICKER, "archive_sha256": ARCHIVE_SHA256}
    if args.restore:
        refuse_unless_named_app(env)
        async with get_task_session() as session:
            restored = await restore(session)
            await session.commit()
        out["restored"] = restored
        return out

    legs = load_archive_legs()
    async with get_task_session() as session:
        grades, refused = await build_plan(session, legs)
        await session.rollback()
    digest = plan_digest(grades)
    out.update({
        "plan_digest": digest,
        "planned": [
            {"outcome_id": g.outcome_id, "ticker": g.ticker, "is_winner": g.is_winner,
             "venue_status": g.status, "venue_result": g.result}
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
    async with get_task_session() as session:
        missing = await backup(session, grades, digest)
        if missing:
            await session.rollback()
            raise Refused(f"{missing} planned legs have no backup row; nothing written")
        await session.commit()
        out["applied"] = await apply(session, legs, digest)
        await session.commit()
    out["undo"] = (
        f"heroku run:detached -a {REQUIRED_APP} -- python3 "
        "scripts/repair_1853_archive_grades.py --restore"
    )
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true", help="write the undo table first")
    p.add_argument("--apply", action="store_true", help="write the planned legs")
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
