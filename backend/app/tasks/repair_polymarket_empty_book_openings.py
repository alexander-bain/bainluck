"""#9083 — Polymarket openings promoted from an empty book leave the page and the curve.

## the defect, in one specimen

``/events/15319167`` led its props rail with "Turner's 1+ hits + runs + rbis was
marked 1% — and it hit". Outcome 236480965's ``opening_probability`` is 0.01,
promoted by ``backfill_winners`` Phase 0c-repair from a Polymarket snapshot of
**bid NULL / ask 1.00 / last 0.01**: nobody bidding, nobody offering below a
dollar, and one 1c trade. Its Under (236480966) is the same book from the other
token, stored at 0.99. Neither is a price.

``empty_polymarket_book_sql`` now keeps Phase 0c from promoting that shape. Like
``ece46743`` for Kalshi, that guard only reaches rows whose opening is still NULL,
so the rows already promoted need this rail. It is the Polymarket twin of
``repair_kalshi_empty_book_openings`` (#4745) and borrows that rail's decision
function and receipt shape instead of restating them.

## the bound, and the provenance clause that makes it safe

A row is in scope only when all of these hold:

    fm.source = 'polymarket' AND fm.status = 'resolved'
    fo.opening_source = 'first_snapshot'          -- Phase 0c wrote this value
    fo.opening_probability IS NOT NULL
    a snapshot of THIS outcome exists with
        captured_at = fo.opening_captured_at      -- PROVENANCE: the very
        probability = fo.opening_probability      -- snapshot the opening came
        and an empty Polymarket book              -- from, not just the earliest

This is stricter than #4745's clause (which matched the earliest snapshot by value)
because Phase 0c has written ``opening_captured_at`` from the same snapshot since
#7648. The only number this rail overwrites is one it can tie to a specific empty
book. A row with a NULL ``opening_captured_at`` is left alone, since nothing proves
where its opening came from.

## what is written

Per row, ``honest`` is the earliest snapshot that Phase 0c's SHIPPED filters
accept today: ``0 < p < 1``, neither venue's empty-book guard, captured at or
before ``resolution_date``. The same filters in the same order mean this rail's
result is a FIXED POINT of Phase 0c. A withdrawn row is NULL, Phase 0c examines it,
finds no honest snapshot, and leaves it NULL. A repriced row is non-null and
Phase 0c skips it.

    honest exists   -> opening_probability, opening_captured_at := honest's
    honest is NULL  -> opening_probability, opening_source, opening_captured_at := NULL
    calibration_probability := the same replacement, ONLY where it is a verbatim
        copy of the discredited opening; otherwise untouched

Nothing else is written: never ``is_winner`` or ``resolution_source`` (gotcha #21),
never ``last_updated`` (#2024). The rail holds no price rule of its own; both
guards are imported.

## D51 — backup and restore

``--apply`` copies every in-scope row's four columns into :data:`BAK_TABLE` in the
same transaction as the write, and refuses if the copy misses a planned id. Undo::

    curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
      "$BAINLUCK_API/api/admin/repairs/polymarket-empty-book-openings-restore?apply=true"

## paging — by markets EXAMINED, not rows found

861,411 resolved Polymarket markets on 2026-09-27, and the defect is sparse (49 of
1,016 legs on three days of MLB). A page capped on rows FOUND would have to walk
an unbounded number of clean markets to fill it. So ``limit`` counts markets
examined, keyset on ``fm.id``, and ``next_after_id`` is the last market examined.
Read ``scan_exhausted``, never a remaining count.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text

from app.tasks.repair_kalshi_empty_book_openings import _record, classify
from app.utils.kalshi_empty_book import lone_ask_on_empty_book_sql
from app.utils.polymarket_empty_book import empty_polymarket_book_sql

logger = logging.getLogger(__name__)

ISSUE = "#9083"

#: The D51 backup, house convention `bak_<issue>_<what>`.
BAK_TABLE = "bak_9083_pm_empty_book_openings"

#: Markets examined per call (about two outcomes each, one indexed EXISTS probe
#: per outcome, then a lateral only for the few that match).
DEFAULT_LIMIT = 5000
MAX_LIMIT = 20000

#: The market page, one rendering shared by the bound and the cursor.
_PAGE_SQL = """
    SELECT m.id FROM futures_markets m
    WHERE m.source = 'polymarket' AND m.status = 'resolved'
      AND m.id > :after_id
    ORDER BY m.id
    LIMIT :page_limit
"""

_PAGE_END_SQL = f"SELECT count(*), max(p.id) FROM ({_PAGE_SQL}) p"

#: The bound. One rendering for the plan, the backup and the apply, so the three
#: cannot disagree about which rows are in scope. The `honest` lateral carries
#: Phase 0c's filters in Phase 0c's order.
_BOUND_SQL = f"""
    SELECT fo.id AS outcome_id,
           fo.opening_probability AS before_opening,
           fo.opening_source AS before_opening_source,
           fo.opening_captured_at AS before_opening_captured_at,
           fo.calibration_probability AS before_calibration,
           fo.opening_probability AS bad_value,
           honest.probability AS honest_value,
           honest.captured_at AS honest_captured_at
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    LEFT JOIN LATERAL (
        SELECT fos.probability, fos.captured_at
        FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id
          AND fos.probability > 0 AND fos.probability < 1
          AND NOT {lone_ask_on_empty_book_sql("fos")}
          AND NOT {empty_polymarket_book_sql("fos")}
          AND (fm.resolution_date IS NULL
               OR fos.captured_at <= fm.resolution_date)
        ORDER BY fos.captured_at ASC
        LIMIT 1
    ) honest ON true
    WHERE fm.id IN ({_PAGE_SQL})
      AND fo.opening_source = 'first_snapshot'
      AND fo.opening_probability IS NOT NULL
      AND fo.opening_captured_at IS NOT NULL
      AND EXISTS (
          SELECT 1 FROM futures_odds_snapshots bad
          WHERE bad.outcome_id = fo.id
            AND bad.captured_at = fo.opening_captured_at
            AND bad.probability = fo.opening_probability
            AND {empty_polymarket_book_sql("bad")}
      )
    ORDER BY fo.id
"""

_BAK_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_TABLE} AS
    SELECT fo.id AS outcome_id,
           fo.opening_probability,
           fo.opening_source,
           fo.opening_captured_at,
           fo.calibration_probability,
           NOW() AS backed_up_at
    FROM futures_outcomes fo
    WHERE false
"""

_BAK_INDEX = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk ON {BAK_TABLE} (outcome_id)"
)

#: The FIRST backup is the one that predates this rail; never overwrite it.
_BAK_COPY = f"""
    INSERT INTO {BAK_TABLE} (outcome_id, opening_probability, opening_source,
                             opening_captured_at, calibration_probability,
                             backed_up_at)
    SELECT s.outcome_id, s.before_opening, s.before_opening_source,
           s.before_opening_captured_at, s.before_calibration, NOW()
    FROM ({_BOUND_SQL}) s
    ON CONFLICT (outcome_id) DO NOTHING
"""

_BAK_MISSING = f"""
    SELECT count(*) FROM ({_BOUND_SQL}) s
    WHERE NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.outcome_id = s.outcome_id)
"""

#: Re-derives the bound inside the UPDATE, so a row that moved between plan and
#: apply falls out instead of being rewritten from a stale reading. The SET reads
#: `fo.opening_probability`'s PRE-update value to decide whether the calibration
#: price was a copy of it.
_APPLY_SQL = f"""
    WITH scope AS ({_BOUND_SQL})
    UPDATE futures_outcomes fo
    SET opening_probability = s.honest_value,
        opening_captured_at = s.honest_captured_at,
        opening_source = CASE WHEN s.honest_value IS NULL
                              THEN NULL ELSE fo.opening_source END,
        calibration_probability = CASE
            WHEN fo.calibration_probability IS NOT NULL
                 AND fo.calibration_probability = fo.opening_probability
            THEN s.honest_value
            ELSE fo.calibration_probability
        END
    FROM scope s
    WHERE fo.id = s.outcome_id
      AND (s.honest_value IS NULL OR s.honest_value <> s.bad_value)
"""

_RESTORE_SQL = f"""
    UPDATE futures_outcomes fo
    SET opening_probability = b.opening_probability,
        opening_source = b.opening_source,
        opening_captured_at = b.opening_captured_at,
        calibration_probability = b.calibration_probability
    FROM {BAK_TABLE} b
    WHERE fo.id = b.outcome_id
      AND (fo.opening_probability IS DISTINCT FROM b.opening_probability
           OR fo.opening_source IS DISTINCT FROM b.opening_source
           OR fo.opening_captured_at IS DISTINCT FROM b.opening_captured_at
           OR fo.calibration_probability IS DISTINCT FROM b.calibration_probability)
"""

_RESTORE_PENDING = f"""
    SELECT count(*) FROM futures_outcomes fo
    JOIN {BAK_TABLE} b ON b.outcome_id = fo.id
    WHERE fo.opening_probability IS DISTINCT FROM b.opening_probability
       OR fo.opening_source IS DISTINCT FROM b.opening_source
       OR fo.opening_captured_at IS DISTINCT FROM b.opening_captured_at
       OR fo.calibration_probability IS DISTINCT FROM b.calibration_probability
"""

_BAK_EXISTS = f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"


def restore_command() -> str:
    """The one command that puts it back (D51). Printed by every apply."""
    return (
        'source ~/.claude/.env && curl -s -X POST -H '
        '"Authorization: Bearer $ADMIN_TOKEN" '
        '"$BAINLUCK_API/api/admin/repairs/polymarket-empty-book-openings-restore'
        '?apply=true"'
    )


async def repair(
    session,
    apply: bool = False,
    limit: Optional[int] = None,
    after_id: Optional[int] = None,
) -> dict[str, Any]:
    """Plan (and optionally apply) one page of the #9083 withdrawal.

    ``limit`` is markets EXAMINED; ``after_id`` is the last market id of the
    previous page.
    """
    page_limit = min(int(limit or DEFAULT_LIMIT), MAX_LIMIT)
    params = {"after_id": int(after_id or 0), "page_limit": page_limit}

    examined, page_end = (await session.execute(text(_PAGE_END_SQL), params)).one()
    rows = (await session.execute(text(_BOUND_SQL), params)).all()

    corrected: list[dict[str, Any]] = []
    withdrawn: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for row in rows:
        action, new_opening, refusal = classify(row)
        record = _record(row)
        if action == "refused":
            refused.append({**record, "reason": refusal})
        elif action == "withdraw":
            withdrawn.append(record)
        else:
            corrected.append({**record, "after_opening": new_opening})

    planned = corrected + withdrawn
    census = {
        "issue": ISSUE,
        "markets_examined": int(examined or 0),
        "in_scope": len(rows),
        "corrected": len(corrected),
        "withdrawn": len(withdrawn),
        "refused": len(refused),
        "leaves_the_curve": sum(1 for r in withdrawn if r["reader_visible"]),
        "repriced_visibly": sum(1 for r in corrected if r["reader_visible"]),
        "scan_exhausted": int(examined or 0) < page_limit,
        "next_after_id": page_end if page_end is not None else params["after_id"],
        "restore_command": restore_command(),
        "backup_table": BAK_TABLE,
        "samples": planned[:20],
        "refusals": refused[:20],
    }

    if not apply:
        census["terminal"] = "dry_run"
        census["changed"] = 0
        return census
    if not planned:
        census["terminal"] = "nothing_to_do"
        census["changed"] = 0
        return census

    # Backup and write in ONE transaction: either order across two transactions
    # leaves a crash window where the backup and the write disagree.
    await session.execute(text(_BAK_CREATE))
    await session.execute(text(_BAK_INDEX))
    await session.execute(text(_BAK_COPY), params)
    missing = (await session.execute(text(_BAK_MISSING), params)).scalar_one()
    if missing:
        await session.rollback()
        census["terminal"] = "refused_backup_incomplete"
        census["changed"] = 0
        census["backup_missing"] = int(missing)
        return census

    result = await session.execute(text(_APPLY_SQL), params)
    changed = result.rowcount or 0
    await session.commit()

    census["terminal"] = "changed"
    census["changed"] = changed
    logger.warning(
        "%s repair applied: %s outcomes (%s withdrawn, %s repriced). Backup in %s. "
        "D51 undo:\n%s",
        ISSUE, changed, len(withdrawn), len(corrected), BAK_TABLE, restore_command(),
    )
    return census


async def restore(session, apply: bool = False) -> dict[str, Any]:
    """Put every backed-up row back to the value it held before the repair."""
    exists = (await session.execute(text(_BAK_EXISTS))).scalar_one()
    if not exists:
        return {
            "issue": ISSUE,
            "terminal": "refused_no_backup",
            "backup_table": BAK_TABLE,
            "restored": 0,
        }

    pending = (await session.execute(text(_RESTORE_PENDING))).scalar_one()
    backed_up = (
        await session.execute(text(f"SELECT count(*) FROM {BAK_TABLE}"))
    ).scalar_one()
    census = {
        "issue": ISSUE,
        "backup_table": BAK_TABLE,
        "backed_up_rows": int(backed_up),
        "rows_differing_from_backup": int(pending),
    }
    if not apply:
        census["terminal"] = "dry_run"
        census["restored"] = 0
        return census

    result = await session.execute(text(_RESTORE_SQL))
    restored = result.rowcount or 0
    await session.commit()
    census["terminal"] = "restored"
    census["restored"] = restored
    logger.warning("%s restore: %s outcomes put back from %s", ISSUE, restored, BAK_TABLE)
    return census
