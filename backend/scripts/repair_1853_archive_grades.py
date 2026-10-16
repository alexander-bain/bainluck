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

#: THE OWNERSHIP CONTRACT (CERT-4149 + Root's three counterexamples, 2026-10-16).
#:
#: * The approved set is FROZEN at backup: the plan's ids, verdicts and digest,
#:   and each row's FULL before-image (``to_jsonb`` of the whole row). Apply
#:   reads that set back and never re-plans, so a row that becomes ungraded
#:   after the review (Root: control 220314801 retracted) is not written.
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
        ON CONFLICT (outcome_id) DO NOTHING
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
    """Freeze the approved set: ids, verdicts, digest and each FULL before-image."""
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


async def run(args, env) -> dict:
    from app.tasks.base import get_task_session

    out: dict = {"event_ticker": EVENT_TICKER, "archive_sha256": ARCHIVE_SHA256}
    if args.restore:
        refuse_unless_named_app(env)
        async with get_task_session() as session:
            out.update(await restore_report(session))
            await session.commit()
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
