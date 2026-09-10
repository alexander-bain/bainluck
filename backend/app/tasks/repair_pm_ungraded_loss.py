"""#4788 (CAL-P1088) — a Polymarket leg nobody graded stops printing a red **Lost**.

## the defect, in one specimen

*Tesla (TSLA) closes above ___ on September 9?* resolved on 2026-09-09. Its
five rungs — $340, $350, $360, $370, $380 — every one of them prints red
**Lost · 0% · Settled** under a heading that reads *Final Results*. Our own last
recorded price had $340 at **96%**. A ladder where every rung lost is not a
result; it is a column default being read as a verdict.

``FuturesOutcome.is_winner`` is ``boolean NULL DEFAULT false`` with a
Python-side ``default=False`` beside it (``models.py:942``). **NULL means
"nobody graded this"; ``false`` is an affirmative graded LOSS.** A writer that
merely OMITS the column therefore declares the leg a loser. That is CAL-P1004R,
and ``OutcomeRow.tsx`` renders it on a resolved market as ``Lost``.

## the population, re-measured — the filing was a 56× understatement

#4788 filed **10,337 legs / 3,308 resolved markets**, bounded by
``fo.id >= 225095972`` and correctly labelled *a lower bound on the post-fix
cohort, not a total for all time*. Measured on production 2026-09-10 17:0xZ,
that bound is doing almost all of the work. Whole population, resolved
Polymarket markets, classified at the MARKET level:

    market shape                       markets    legs
    no winner, no graded leg           277,519   574,832   <- this rail
    a winner crowned, legs badged          854     1,789   <- NOT touched
    no winner, some leg badged             118       304   <- NOT touched

277,519 of the **661,290** resolved Polymarket markets — 42% — print at least
one *Lost* that no grader ever wrote. Within the id-bounded slice the filing
used, the same classification is 3,504 of 3,527 markets, so the shape is not an
artefact of age.

The middle row is the reason this rail is gated at the market and not at the
leg. On a market whose winner IS crowned, a ``false`` leg genuinely lost — it is
merely un-badged — and nulling it would manufacture the opposite defect. The
``kalshi_fabricated_loss`` docstring records the same lesson from the other
direction: a per-market repair there would have corrupted 150 true rows to fix
2. Here the market is the SAFETY gate and the leg is the unit of write.

## THE CURVE IS NOT AFFECTED, AND THAT IS WHY THIS IS A RENDER-TRUTH SHIP

This repository's canonical grade predicate is
``calibration_graded_share.GRADED_PREDICATE = "fo.resolution_source IS NOT
NULL"``, and ``precompute_calibration``'s truth-eligibility allowlist
(``CALIBRATION_TRUTH_ELIGIBLE_SOURCES``) keeps every source-less row out of
``ranked_outcomes``. The module says so in its own words: *"The real 'nobody
graded this' shape is ``is_winner = false, resolution_source = NULL`` … it is
the truth-eligibility allowlist — not any rung here — that keeps it out of the
curve."* So not one of these 574,832 legs reaches ``/api/calibration``.

The ship is therefore entirely the reader's screen, and it is claimed as
nothing more.

## WHY WITHDRAWAL, AND NOT A SECOND VENUE-GRADING RAIL

The cohort is not unowned. ``pm-never-graded`` (CAL-P065, #1912) selects it with
an identical market-level predicate::

    HAVING bool_or(fo.is_winner) IS NOT TRUE
       AND bool_and(fo.resolution_source IS NULL)

(#4788's body distinguishes itself from #1912 on the grounds that #1912 is
``is_winner IS NULL``. That distinction does not hold: #1912's own registry
entry describes *"their ``is_winner=false`` is the COLUMN DEFAULT"*. Same rows.)

That rail asks the CLOB venue per market and CROWNS a winner — the honest
long-run fix, and the only one permitted to decide who won (gotcha #21). It is
capped at ``APPLY_MARKET_CAP = 40`` markets per call, attended-only, with no
beat. Against 277,519 markets that is **6,938 attended calls**. It cannot reach
the reader on any horizon, and its own docstring names that hazard: *"promising
a drain rate against an unsized population is how the CLOB rail ended up
scheduled at 1,200 checks/day against a five-figure backlog."*

So this rail does not grade. It **withdraws a verdict we never made** — a fact
about our own row, not a claim about the venue, so notice 26 does not bite and
no venue call is required to establish it. Grading remains #1912's, unimpeded:

* ``pm-never-graded``'s cohort still selects a withdrawn market. ``bool_or`` over
  all-NULL yields NULL, and ``NULL IS NOT TRUE`` is true.
* Its compare-and-set (``resolution_source IS NULL AND is_winner IS NOT TRUE``)
  still matches a NULL leg.

Both are asserted against a real Postgres by
``test_pm_never_graded_still_selects_a_withdrawn_market``, because they are the
properties that make withdrawal safe rather than merely appealing.

## the one interaction this creates, named rather than hidden

``repair_pm_never_graded._revert_written_legs`` restores
``bool(leg.expected_is_winner)``, and the planner hardcodes
``expected_is_winner=False`` (``repair_pm_never_graded.py:1149``) on the premise
— true before this rail — that every cohort leg reads ``false``. After a
withdrawal that premise is stale, so a halt-and-revert would write ``false``
back onto legs it had graded.

It is **self-healing and bounded**: the revert is scoped to
``resolution_source = 'clob_never_graded'``, so a reverted leg lands back on
``false`` + NULL source, which is this rail's own bound, and the next pass
withdraws it again. It is recorded here, and filed, rather than fixed in
passing: that rail is #1912's, separately certified, and the fix needs
``_load_outcomes`` to carry ``is_winner`` so the plan can record the tri-state.

## what is written, and what is never touched

Per row, exactly one column::

    is_winner := NULL          -- withdraw a verdict nobody made

Never ``resolution_source`` — it is already NULL and is the cohort's key. Never
a price: this rail has no opinion about what the market thought, only about
whether we graded it. Never ``last_updated`` — that touch-stamp is read
elsewhere as poller liveness (#2024). It crowns nobody, so it holds no
truth rule of its own, and
``test_the_rail_crowns_nobody`` fails if a ``= true`` ever appears in its SQL.

## D51 — backup and restore

``--apply`` copies every in-scope row into :data:`BAK_TABLE` **in the same
transaction as the write**, and refuses if the copy does not cover every planned
id (gotcha #53: a reconciliation that ran on no rows is not a clean one). The
undo is ONE statement, on the same rail with the same auth::

    curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
      "$BAINLUCK_API/api/admin/repairs/pm-ungraded-loss-restore?apply=true"

## paging

574,832 rows do not fit in one request. ``limit`` + ``after_id`` walk the bound
keyset-wise in ``fo.id`` order. A withdrawn row leaves its own bound
(``is_winner = false`` no longer matches NULL), so read ``scan_exhausted`` —
"this page found no more rows" — and never a remaining count.

A page boundary that splits a market is harmless: the market-level gate asks
whether any leg carries a GRADE, and a half-withdrawn market still carries none,
so the remaining legs stay in scope on the next page.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

ISSUE = "#4788"

#: The D51 backup. `bak_<issue>_<what>` is the house convention.
BAK_TABLE = "bak_4788_ungraded_loss"

#: Rows per call. One anti-join over `futures_outcomes` by `market_id` (indexed);
#: measured ~0.5s for 11k rows on production, so a page of 5,000 sits well inside
#: the request budget with the backup copy in the same transaction.
DEFAULT_LIMIT = 5000
MAX_LIMIT = 20000

#: A leg our own last recorded price puts at or above this is one where the red
#: `Lost` contradicts the number printed beside it. Reported, never acted on —
#: the price does not decide the grade (gotcha #21), it only measures how loud
#: the defect is.
CONTRADICTION_PRICE = 0.9

#: The MARKET-level safety gate: no leg on this market carries a grade of any
#: kind. Written as an anti-join rather than the `HAVING bool_or(...)` form
#: `pm-never-graded` uses, because this rail pages by leg id and a HAVING would
#: force a full group-by of the population per page. The two are asserted
#: equivalent against a real Postgres.
_MARKET_HAS_NO_GRADE = """
    NOT EXISTS (
        SELECT 1 FROM futures_outcomes g
        WHERE g.market_id = fo.market_id
          AND (g.resolution_source IS NOT NULL OR g.is_winner IS TRUE)
    )
"""

#: The bound. ONE rendering, used by the plan, the backup and the apply alike,
#: so the three cannot drift into disagreeing about which rows are in scope.
_BOUND_SQL = f"""
    SELECT fo.id AS outcome_id,
           fo.market_id AS market_id,
           fo.is_winner AS before_is_winner,
           fo.current_probability AS last_price
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.source = 'polymarket'
      AND fm.status = 'resolved'
      AND fo.is_winner = false
      AND fo.resolution_source IS NULL
      AND {_MARKET_HAS_NO_GRADE}
      AND fo.id > :after_id
    ORDER BY fo.id
    LIMIT :page_limit
"""

#: `CREATE TABLE ... AS SELECT ... WHERE false` rather than a spelled-out DDL:
#: the backup inherits `futures_outcomes`' own column types, so a restore can
#: never lose a value to a hand-written type that drifts from the column it
#: mirrors.
_BAK_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_TABLE} AS
    SELECT fo.id AS outcome_id,
           fo.market_id,
           fo.is_winner,
           NOW() AS backed_up_at
    FROM futures_outcomes fo
    WHERE false
"""

_BAK_INDEX = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk ON {BAK_TABLE} (outcome_id)"
)

#: Never overwrite an existing backup row. A leg may legitimately be withdrawn,
#: restored and withdrawn again; the FIRST backup is the one that predates this
#: rail, and re-copying after an apply would back up the withdrawn value and make
#: the undo a no-op.
_BAK_COPY = f"""
    INSERT INTO {BAK_TABLE} (outcome_id, market_id, is_winner, backed_up_at)
    SELECT s.outcome_id, s.market_id, s.before_is_winner, NOW()
    FROM ({_BOUND_SQL}) s
    ON CONFLICT (outcome_id) DO NOTHING
"""

#: The D51 gate. Counts in-scope rows with NO backup row — a COUNT over the bound
#: rather than a comparison of two totals, because two totals can agree while
#: naming different rows.
_BAK_MISSING = f"""
    SELECT count(*) FROM ({_BOUND_SQL}) s
    WHERE NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.outcome_id = s.outcome_id)
"""

#: The write. Re-derives the bound INSIDE the UPDATE rather than trusting the ids
#: the plan produced: plan and apply may be seconds apart, and a market something
#: else graded in between must fall out of scope rather than be withdrawn from a
#: stale reading.
_APPLY_SQL = f"""
    WITH scope AS ({_BOUND_SQL})
    UPDATE futures_outcomes fo
    SET is_winner = NULL
    FROM scope s
    WHERE fo.id = s.outcome_id
"""

#: The undo, as ONE statement. `IS DISTINCT FROM` makes it idempotent and makes
#: its rowcount mean "rows actually put back" rather than "rows visited".
_RESTORE_SQL = f"""
    UPDATE futures_outcomes fo
    SET is_winner = b.is_winner
    FROM {BAK_TABLE} b
    WHERE fo.id = b.outcome_id
      AND fo.is_winner IS DISTINCT FROM b.is_winner
"""

_RESTORE_PENDING = f"""
    SELECT count(*) FROM futures_outcomes fo
    JOIN {BAK_TABLE} b ON b.outcome_id = fo.id
    WHERE fo.is_winner IS DISTINCT FROM b.is_winner
"""

_BAK_EXISTS = f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"


def restore_command() -> str:
    """The one command that puts it back (D51). Printed by every apply."""
    return (
        'source ~/.claude/.env && curl -s -X POST -H '
        '"Authorization: Bearer $ADMIN_TOKEN" '
        '"$BAINLUCK_API/api/admin/repairs/pm-ungraded-loss-restore?apply=true"'
    )


def _record(row: Any) -> dict[str, Any]:
    price = None if row.last_price is None else float(row.last_price)
    return {
        "outcome_id": row.outcome_id,
        "market_id": row.market_id,
        # What the row says today, and what a resolved market renders as `Lost`.
        "before_is_winner": row.before_is_winner,
        "last_price": price,
        # The sharpest half: our own last number contradicts the red `Lost`.
        "price_contradicts": price is not None and price >= CONTRADICTION_PRICE,
    }


async def repair(
    session,
    apply: bool = False,
    limit: Optional[int] = None,
    after_id: Optional[int] = None,
) -> dict[str, Any]:
    """Plan (and optionally apply) one page of the #4788 withdrawal.

    Returns a payload complete enough to BE the receipt: every in-scope leg, the
    market it hangs off, and the last price whose contradiction of the printed
    `Lost` is the reason a reader notices.
    """
    page_limit = min(int(limit or DEFAULT_LIMIT), MAX_LIMIT)
    params = {"after_id": int(after_id or 0), "page_limit": page_limit}

    rows = (await session.execute(text(_BOUND_SQL), params)).all()
    planned = [_record(row) for row in rows]
    contradicted = [r for r in planned if r["price_contradicts"]]

    census = {
        "issue": ISSUE,
        "examined": len(rows),
        "planned": len(planned),
        "markets": len({r["market_id"] for r in planned}),
        "price_contradicted": len(contradicted),
        # A withdrawn row leaves its own bound, so an under-full page is the end
        # of the walk and a remaining count is fiction.
        "scan_exhausted": len(rows) < page_limit,
        "next_after_id": rows[-1].outcome_id if rows else after_id,
        "restore_command": restore_command(),
        "backup_table": BAK_TABLE,
        "samples": planned[:20],
    }

    if not apply:
        census["terminal"] = "dry_run"
        census["changed"] = 0
        return census

    if not planned:
        census["terminal"] = "nothing_to_do"
        census["changed"] = 0
        return census

    # Backup and write in ONE transaction. Copying on its own connection could
    # only happen before or after the update, and both orders are a lie waiting
    # for a crash: before, the backup claims rows that may roll back; after, a
    # durable write may have no undo.
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
        "%s withdrawal applied: %s legs across %s markets stop printing Lost "
        "(%s of them contradicted by our own last price). Backup in %s. "
        "D51 undo:\n%s",
        ISSUE, changed, census["markets"], len(contradicted), BAK_TABLE,
        restore_command(),
    )
    return census


async def restore(session, apply: bool = False) -> dict[str, Any]:
    """Put every backed-up leg back to the verdict it carried before the repair."""
    exists = (await session.execute(text(_BAK_EXISTS))).scalar_one()
    if not exists:
        # "I found no backup table" is not "there is nothing to restore"
        # (gotcha #53) — it is a refusal that names itself.
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
    logger.warning("%s restore: %s legs put back from %s", ISSUE, restored, BAK_TABLE)
    return census
