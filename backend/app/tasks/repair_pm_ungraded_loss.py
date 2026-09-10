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

## THE PAGE IS FROZEN, AND THE WRITE CANNOT OUTRUN ITS OWN BACKUP

This rail runs attended, for many pages, over a population a SCHEDULED writer is
also touching: ``backfill_winners`` every six hours, ``pm-never-graded`` when an
operator runs it. Both grade **one leg per statement and commit per leg**
(``repair_pm_never_graded.py:1364-1382``), so a market is not graded atomically —
it passes through a state where one leg carries a verdict and its siblings do
not. The application session runs READ COMMITTED and does not raise it
(``database.py:132-147``), so every statement here takes a FRESH snapshot.

The first cut of this rail re-ran ``_BOUND_SQL`` — a ``LIMIT``ed, therefore
MOVING, scope — four separate times: to plan, to back up, to check the backup,
and again inside the ``UPDATE``. CERT-2524 blocked it, correctly. If a grader
commits between two of those statements, the graded market's legs leave the
bound, the ``LIMIT`` admits the next rows down the id order, and the ``UPDATE``
changes rows **no backup ever covered** — so the one-command D51 undo silently
stops being complete. That is the promise this module makes in its own docstring
above, and it was not being kept.

Three things now hold it, and each answers one half of the failure:

1. **The page is frozen in Python, once.** ``_BOUND_SQL`` is the only ``LIMIT``ed
   read and it runs EXACTLY ONCE per call. Every statement after it is keyed on
   ``fo.id = ANY(:page_ids)`` — a literal list of integers. A scope that is a
   value cannot move; a scope that is a query re-run under a new snapshot can.
2. **The write is joined to the durable backup.** ``_APPLY_SQL`` reads
   ``FROM {BAK_TABLE} b WHERE b.outcome_id = fo.id``. An unbacked row is not
   merely *checked for* — it is unreachable by the ``UPDATE``, because there is
   no row to join it to. The counting gate stays as the loud, named refusal
   (gotcha #53), but the join is what makes the invariant structural.
3. **The market gate is re-validated under a lock the graders block on.**
   Immediately before the write, ``_LOCK_SQL`` takes ``FOR UPDATE`` on **every
   leg of every market in the page** — not just the page's own legs, because the
   sibling a grader crowns may sit on the other side of a page boundary. Any
   grader mid-flight blocks there and lands before we look; any grader arriving
   after blocks until we commit. The ``UPDATE``'s snapshot is therefore taken
   after every racing grade is visible, and its ``NOT EXISTS`` excludes the
   market. This is the "atomically revalidate against concurrent outcome
   writers" half; the lock is bounded by ``LOCK_TIMEOUT_MS`` so a busy row makes
   the rail REFUSE BY NAME rather than hold an admin request open.

**A backup row is only kept for a leg the write actually changed.** Backing up is
one statement and the revalidation is a later one, so a grade landing in between
leaves rows copied that the ``UPDATE`` then correctly declines to touch. Those
rows are pruned inside the same transaction (``_BAK_PRUNE``). Left behind, they
would arm the undo to push ``false`` back over a verdict the grader had
meanwhile written — the backup would be a loaded gun pointed at real data.

**The restore only puts back a verdict still nobody else has written.**
``_RESTORE_SQL`` carries ``AND fo.resolution_source IS NULL``. Without it, an
undo run days after the apply would overwrite whatever ``pm-never-graded``
crowned in the meantime — the same hazard CERT-2516 recorded against #4745's
rail as ``4745-RESTORE-PRESERVES-POST-REPAIR-REPRICING``. A graded leg is not
ours to put back, and a restore that skips it is the honest one.

**What is still not covered, stated rather than implied:** a grader that INSERTS
a brand-new already-graded leg onto a resolved market between the lock and the
commit. ``FOR UPDATE`` locks rows, so it cannot lock a row that does not exist
yet. No writer in this repository does that — every grade is an ``UPDATE`` of a
leg the ingest created with the market — and the residue is self-healing anyway:
``pm-never-graded``'s compare-and-set (``resolution_source IS NULL AND is_winner
IS NOT TRUE``) still matches a withdrawn leg, so its next pass grades it.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import BigInteger, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY

logger = logging.getLogger(__name__)

ISSUE = "#4788"

#: The D51 backup. `bak_<issue>_<what>` is the house convention.
BAK_TABLE = "bak_4788_ungraded_loss"

#: Rows per call. One anti-join over `futures_outcomes` by `market_id` (indexed);
#: measured ~0.5s for 11k rows on production, so a page of 5,000 sits well inside
#: the request budget with the backup copy in the same transaction.
DEFAULT_LIMIT = 5000
MAX_LIMIT = 20000

#: How long the pre-write lock will wait for a grader that is mid-commit on one
#: of these legs. A grade is a single-row UPDATE that commits immediately, so a
#: real wait is milliseconds; anything approaching this bound means something is
#: holding rows open and the honest answer is to refuse the page and say so,
#: not to keep an attended admin request hanging.
LOCK_TIMEOUT_MS = 15000

#: Postgres `lock_not_available` — what `SET LOCAL lock_timeout` raises. Matched
#: on SQLSTATE rather than on message text, which is localised.
_LOCK_TIMEOUT_SQLSTATE = "55P03"

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

#: The SAME leg-and-market test as `_BOUND_SQL`, keyed on a FROZEN list of ids
#: instead of a moving `LIMIT`. Every statement after the plan read uses this, so
#: the backup, the gate and the write cannot disagree about which rows are in
#: scope — and cannot silently acquire rows the plan never saw.
_ELIGIBLE_BY_ID = f"""
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fo.id = ANY(:page_ids)
      AND fm.source = 'polymarket'
      AND fm.status = 'resolved'
      AND fo.is_winner = false
      AND fo.resolution_source IS NULL
      AND {_MARKET_HAS_NO_GRADE}
"""

#: Never overwrite an existing backup row. A leg may legitimately be withdrawn,
#: restored and withdrawn again; the FIRST backup is the one that predates this
#: rail, and re-copying after an apply would back up the withdrawn value and make
#: the undo a no-op. `RETURNING` names the rows THIS call inserted, which is what
#: `_BAK_PRUNE` needs to avoid deleting an earlier page's backup.
_BAK_COPY = f"""
    INSERT INTO {BAK_TABLE} (outcome_id, market_id, is_winner, backed_up_at)
    SELECT fo.id, fo.market_id, fo.is_winner, NOW()
    {_ELIGIBLE_BY_ID}
    ON CONFLICT (outcome_id) DO NOTHING
    RETURNING outcome_id
"""

#: The D51 gate. Counts in-scope rows with NO backup row — a COUNT over the bound
#: rather than a comparison of two totals, because two totals can agree while
#: naming different rows. The `_APPLY_SQL` join makes an unbacked write
#: impossible; this makes it LOUD instead of merely absent.
_BAK_MISSING = f"""
    SELECT count(*) FROM (SELECT fo.id AS outcome_id {_ELIGIBLE_BY_ID}) s
    WHERE NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.outcome_id = s.outcome_id)
"""

#: Take a row lock on EVERY leg of every market this page touches — the page's
#: own legs and their siblings alike. A grader crowning a winner one leg at a
#: time either lands before this (and the write's `NOT EXISTS` then excludes the
#: market) or blocks until this transaction commits. Without the siblings, a
#: market split across a page boundary leaves the grader an unlocked leg to write
#: while this rail withdraws the rest.
_LOCK_SQL = """
    SELECT fo.id
    FROM futures_outcomes fo
    WHERE fo.market_id = ANY(:market_ids)
    ORDER BY fo.id
    FOR UPDATE
"""

#: The write. Keyed on the frozen page, JOINED to the durable backup — an
#: unbacked row has nothing to join to and cannot be reached — and re-testing the
#: market gate in its own snapshot, which the lock above has just made current.
_APPLY_SQL = f"""
    UPDATE futures_outcomes fo
    SET is_winner = NULL
    FROM {BAK_TABLE} b
    WHERE b.outcome_id = fo.id
      AND fo.id = ANY(:page_ids)
      AND EXISTS (
          SELECT 1
          FROM futures_markets fm
          WHERE fm.id = fo.market_id
            AND fm.source = 'polymarket'
            AND fm.status = 'resolved'
      )
      AND fo.is_winner = false
      AND fo.resolution_source IS NULL
      AND {_MARKET_HAS_NO_GRADE}
    RETURNING fo.id
"""

#: Drop the backup rows THIS call wrote for legs it then declined to change —
#: a market someone graded between the copy and the write. A backup row for a row
#: we did not touch is not harmless: the undo would push our remembered `false`
#: over the verdict the grader wrote.
_BAK_PRUNE = f"""
    DELETE FROM {BAK_TABLE} WHERE outcome_id = ANY(:page_ids)
"""

#: The undo, as ONE statement. `IS DISTINCT FROM` makes it idempotent and makes
#: its rowcount mean "rows actually put back" rather than "rows visited".
#:
#: `resolution_source IS NULL` is the half that makes a LATE undo safe. Every
#: backed-up leg was source-less when we withdrew it; if one carries a source
#: now, something graded it in the meantime and the verdict is no longer ours to
#: overwrite. Restoring it would re-fabricate exactly the `Lost` this rail
#: exists to remove — on a market that has since been graded honestly.
_RESTORE_SQL = f"""
    UPDATE futures_outcomes fo
    SET is_winner = b.is_winner
    FROM {BAK_TABLE} b
    WHERE fo.id = b.outcome_id
      AND fo.resolution_source IS NULL
      AND fo.is_winner IS DISTINCT FROM b.is_winner
"""

_RESTORE_PENDING = f"""
    SELECT count(*) FROM futures_outcomes fo
    JOIN {BAK_TABLE} b ON b.outcome_id = fo.id
    WHERE fo.resolution_source IS NULL
      AND fo.is_winner IS DISTINCT FROM b.is_winner
"""

#: Backed-up legs something else has graded since. Reported by the restore so a
#: skip is a NUMBER an operator can see, never a silent shortfall between
#: `backed_up_rows` and `restored` (gotcha #53).
_RESTORE_SKIPPED = f"""
    SELECT count(*) FROM futures_outcomes fo
    JOIN {BAK_TABLE} b ON b.outcome_id = fo.id
    WHERE fo.resolution_source IS NOT NULL
"""


def _ids(sql: str, *names: str):
    """A statement whose `= ANY(:name)` binds take a Python list of ids.

    asyncpg needs the array type spelled out; without it the bind arrives as a
    scalar and the statement matches nothing — which on a repair rail reads as
    "there was no work", the exact ambiguity gotcha #53 is about.
    """
    return text(sql).bindparams(
        *[bindparam(name, type_=ARRAY(BigInteger)) for name in names]
    )

_BAK_EXISTS = f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"


def restore_command() -> str:
    """The one command that puts it back (D51). Printed by every apply."""
    return (
        'source ~/.claude/.env && curl -s -X POST -H '
        '"Authorization: Bearer $ADMIN_TOKEN" '
        '"$BAINLUCK_API/api/admin/repairs/pm-ungraded-loss-restore?apply=true"'
    )


def _sqlstate(exc: BaseException) -> Optional[str]:
    """The Postgres SQLSTATE behind a driver error, wrapper or not.

    SQLAlchemy wraps the asyncpg exception in a `DBAPIError` and hangs the
    original off `.orig`, so the code is one attribute deeper than it looks.
    Walking both means the caller never has to know which layer raised.
    """
    for candidate in (exc, getattr(exc, "orig", None)):
        state = getattr(candidate, "sqlstate", None) or getattr(
            candidate, "pgcode", None
        )
        if state:
            return str(state)
    return None


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
    _between_backup_and_update=None,
) -> dict[str, Any]:
    """Plan (and optionally apply) one page of the #4788 withdrawal.

    Returns a payload complete enough to BE the receipt: every in-scope leg, the
    market it hangs off, and the last price whose contradiction of the printed
    `Lost` is the reason a reader notices.

    ``_between_backup_and_update`` is a test seam and nothing else: an awaitable
    called once, after the backup and before the lock, so a second Postgres
    session can commit a grade INTO the window this rail used to lose rows in.
    Production never passes it. A race that can only be described in a comment
    is a race nobody re-checks after the next refactor.
    """
    page_limit = min(int(limit or DEFAULT_LIMIT), MAX_LIMIT)
    params = {"after_id": int(after_id or 0), "page_limit": page_limit}

    # The ONLY LIMITed read in this function. Everything downstream is keyed on
    # the ids it returns, so the scope is a value from here on, not a query.
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

    # The frozen page. A list of integers cannot be re-derived under a newer
    # snapshot, which is the whole of CERT-2524's finding.
    page_ids = [r["outcome_id"] for r in planned]
    market_ids = sorted({r["market_id"] for r in planned})
    id_params = {"page_ids": page_ids, "market_ids": market_ids}

    # Backup and write in ONE transaction. Copying on its own connection could
    # only happen before or after the update, and both orders are a lie waiting
    # for a crash: before, the backup claims rows that may roll back; after, a
    # durable write may have no undo.
    await session.execute(text(_BAK_CREATE))
    await session.execute(text(_BAK_INDEX))
    inserted = {
        row[0]
        for row in (
            await session.execute(_ids(_BAK_COPY, "page_ids"), id_params)
        ).all()
    }

    missing = (
        await session.execute(_ids(_BAK_MISSING, "page_ids"), id_params)
    ).scalar_one()
    if missing:
        await session.rollback()
        census["terminal"] = "refused_backup_incomplete"
        census["changed"] = 0
        census["backup_missing"] = int(missing)
        return census

    if _between_backup_and_update is not None:
        await _between_backup_and_update()

    # Freeze the graders out, then look again. Order matters and is the repair:
    # the lock makes every racing grade either already-visible or not-yet-begun,
    # so `_APPLY_SQL`'s market gate is evaluated against a settled world.
    try:
        await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_MS}ms'"))
        await session.execute(_ids(_LOCK_SQL, "market_ids"), id_params)
    except Exception as exc:  # noqa: BLE001 — re-raised unless it is the timeout
        if _sqlstate(exc) != _LOCK_TIMEOUT_SQLSTATE:
            raise
        await session.rollback()
        census["terminal"] = "refused_lock_timeout"
        census["changed"] = 0
        census["lock_timeout_ms"] = LOCK_TIMEOUT_MS
        return census

    changed_ids = [
        row[0]
        for row in (
            await session.execute(_ids(_APPLY_SQL, "page_ids"), id_params)
        ).all()
    ]
    changed = len(changed_ids)

    # A row we copied but then declined to change belongs to a market someone
    # graded inside the window above. Its backup row must go, or the undo would
    # push our remembered `false` over their verdict.
    stale_backup = sorted(inserted - set(changed_ids))
    if stale_backup:
        await session.execute(
            _ids(_BAK_PRUNE, "page_ids"), {"page_ids": stale_backup}
        )

    await session.commit()

    census["terminal"] = "changed"
    census["changed"] = changed
    # Non-zero means a grader landed mid-page. Not an error — the gate working —
    # but a silent one would look identical to a page that simply had less work.
    census["conceded_to_a_grader"] = len(stale_backup)
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
    skipped = (await session.execute(text(_RESTORE_SKIPPED))).scalar_one()

    census = {
        "issue": ISSUE,
        "backup_table": BAK_TABLE,
        "backed_up_rows": int(backed_up),
        "rows_differing_from_backup": int(pending),
        # Legs something graded since the withdrawal. The undo leaves them
        # alone; saying so by number is the difference between a deliberate
        # skip and an undo that quietly did less than it claimed.
        "skipped_now_graded": int(skipped),
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
