"""#4745 (CAL-P1086) — the openings promoted from a lone ask leave the published curve.

## the defect, in one specimen

*Mitch Marner: 3+ points* stored a Kalshi book of **bid 0.00 / ask 0.98 / no
trade** and we published **0.98**. Nobody would pay a cent for YES; somebody
left an offer at 98c; the accuracy page called it a 98% chance. *Drew Doughty:
1+ goals* is the same book and the same 0.98.

``_kalshi_yes_probability`` (``app/tasks/kalshi.py``) has refused to WRITE that
shape since ``52eee9b6``, 2026-07-13 (Queue #182): an ask-only book is trusted
only to :data:`~app.utils.kalshi_empty_book.ASK_ONLY_TRUSTED_MAX`, and above it
the poller stores nothing. ``ece46743`` put the same rule on the PROMOTION —
``backfill_winners`` Phase 0c-repair, which copies a resolved outcome's earliest
snapshot into ``opening_probability`` and never looked at the book that snapshot
recorded.

Both of those are guards. Neither removes a row that was already promoted, and
CERT-2508 BLOCKed ``ece46743`` on exactly that: the bad openings are non-null,
so a guard keyed on ``opening_probability IS NULL`` cannot reach them. This rail
is the reach.

## THE MEASUREMENT CORRECTED THE FILING, TWICE, AND BOTH CORRECTIONS MATTER

Measured on production 2026-09-10 14:5xZ, 1-in-20 systematic sample on ``fo.id``
(the unsampled form times out; the sample examines 1,756 legs in ~5s).

**Correction 1 — the curve does not read ``opening_probability`` for half of
them.** The curve price is ``COALESCE(calibration_probability,
opening_probability)`` — a coalesce, not an exclusion (gotcha #144 / ruling
103) — so a row carrying its own ``calibration_probability`` never shows its
opening to a reader at all:

    arm                                     legs   curve price   opening   won
    a. calibration NULL, curve reads open    475      0.9805      0.9805    8.4%
    b. calibration is a COPY of the opening  373      0.8069      0.8069   19.0%
    c. calibration is independent            908      0.3921      0.9710   18.9%

Arms a+b are what a reader sees: **848 sampled ≈ 16,960 legs, published at a
mean 0.904, realised 13.1%.** Arm c's opening is just as false, and is repaired
here for the same reason — but it is not what the page publishes, and the ship
does not claim it.

**Correction 2 — inside the published arms it is almost all withdrawal, not
repricing.** CAL-P1086's own directive said "half get a real price, half are
removed". That 50/50 is the split of the WHOLE cohort, and its correctable half
is almost entirely arm c — rows whose repair a reader cannot see. Within arms
a+b:

    action                                   legs   ×20      mean published   won
    withdrawn (no honest snapshot ever)       778   ~15,560      0.919        12.6%
    repriced to a real price                   70    ~1,400      0.938        18.6%

So the ship is a **withdrawal**: ~15,600 predictions the page publishes at ~0.92
average, which came true ~13% of the time, are removed because no price ever
existed for them at any point in their history. Baseball (363/848) and hockey
(356/848) are 85% of it.

## the asymmetry that makes refusing the ask side safe

Earliest snapshot per leg, 1-in-211 sample of ALL resolved Kalshi legs, so the
false-positive rate is measured on the known-good population and not only on
the suspect one:

    book shape at capture          legs   mean stored   actually won
    lone ASK, zero bid, no trade    659      0.369          6.2%
    lone BID, ask at 1.00           189      0.949         93.7%
    tight book                      872      0.341         33.3%

A lone **bid** is a price somebody will pay and grades almost perfectly; it is
deliberately untouched. A lone **ask** on a book nobody bids into grades as a
near-total loss. Only the ask side is refused, and the predicate is the shipped
one — :func:`~app.utils.kalshi_empty_book.lone_ask_on_empty_book_sql`, imported,
never restated.

## WHY A ONE-OFF RAIL AND NOT A RE-DERIVING PHASE 0c

The alternative on the table was to make Phase 0c re-derive every
``opening_source = 'first_snapshot'`` row instead of only filling NULLs, so the
correction would be structural. Measured, it is the worse of the two:

* **It does not fit in the budget.** 261,976 rows carry that source
  (production, 2026-09-10). Re-deriving means running the guarded
  ``captured_at ASC LIMIT 1`` lateral over all of them every six hours, inside
  ``backfill_winners`` — a task with ``soft_time_limit=840`` that CAL-P1080
  measured stopping early at 757.8s with ``partial_budget_guard`` /
  ``stopped_before: bookmaker_closing``. A phase that cannot finish is a
  correction that arrives for an arbitrary prefix of the population.
* **It buys nothing, because this rail's result is ALREADY a fixed point of the
  live Phase 0c.** A corrected row is non-null, so the ``IS NULL`` key skips it.
  A withdrawn row is null, so Phase 0c does examine it — and its guarded lateral
  finds no honest snapshot (that is the definition of withdrawn), yields no row,
  and the ``CROSS JOIN LATERAL`` drops the outcome. Nothing is re-promoted.
  ``test_phase_0c_does_not_re_promote_a_withdrawn_row`` runs the real Phase 0c
  SQL against a real Postgres immediately after the repair and asserts it.
* **It widens a scheduled task's terminal behaviour over the whole
  population**, where this is bounded, backed up and reversible.

Trap 1 in the directive — "null a row and Phase 0c re-promotes it within one
cycle" — is true only while the guard is *absent*. It is the reason this rail
must not run before ``ece46743`` is live, and the reason it is safe once it is.

## the bound, and the provenance clause that makes it safe

A row is in scope only when all of these hold:

    fm.status = 'resolved'
    fo.opening_source = 'first_snapshot'      -- Phase 0c wrote this value
    fo.opening_probability IS NOT NULL
    the EARLIEST snapshot with 0 < probability < 1 is a lone ask on an empty
        Kalshi book
    fo.opening_probability = that snapshot's probability   -- PROVENANCE

The last clause is the safety argument. Without it the rail would rewrite any
row that merely *has* a bad earliest snapshot; with it, the only number this
rail ever overwrites is one it can prove came from the discredited book. On
production the clause costs nothing today — 1,756 of 1,756 sampled rows satisfy
it — which is a measurement recorded here, not an assumption, and exactly why it
must stay: the day it stops being free is the day it starts protecting a row.

## what is written, and what is never touched

Per row, with ``honest`` = the earliest snapshot the SHIPPED guard accepts:

    honest exists   -> opening_probability := honest, opening_source unchanged
    honest is NULL  -> opening_probability := NULL, opening_source := NULL
    calibration_probability := the same replacement, but ONLY where it is a
        verbatim copy of the discredited opening (arm b); otherwise untouched

Never ``is_winner`` or ``resolution_source`` — this rail has no opinion about
truth, only about price (gotcha #21). Never ``last_updated`` — the poller's
touch-stamp is read elsewhere as liveness (#2024). It holds no price rule of its
own: there is no numeric threshold in this module, and
``test_the_rail_holds_no_price_rule_of_its_own`` fails if one appears.

:data:`REASON_REPLACEMENT_EQUALS_STORED` is a real refusal, not a defensive one:
9 of 1,756 sampled legs have a later honest snapshot whose probability equals
the lone ask's. Writing those changes nothing, so they are refused by name
rather than counted as repaired.

## D51 — backup and restore

``--apply`` copies every in-scope row's three columns into
:data:`BAK_TABLE` **in the same transaction as the write**, and refuses if the
copy does not cover every planned id (gotcha #53: a reconciliation that ran on
no rows is not a clean one). The undo is ONE statement, on the same rail with
the same auth::

    curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
      "$BAINLUCK_API/api/admin/repairs/kalshi-empty-book-openings-restore?apply=true"

It puts back exactly what was stored at backup time. That is what an undo is,
and it is why this rail is not a maintenance job: run it after something else
has legitimately repriced one of these rows and it reclaims that row too.

## paging

The population is ~35,000 rows through two laterals; the whole of it does not
fit in one request (the published-population chain alone times out at ~18s on
the admin rail). ``limit`` + ``after_id`` walk it keyset-wise in ``fo.id``
order. A page that repairs its rows removes them from its own bound, so read
``scan_exhausted`` — "this page found no more rows" — and never a remaining
count.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text

from app.utils.kalshi_empty_book import lone_ask_on_empty_book_sql

logger = logging.getLogger(__name__)

ISSUE = "#4745"

#: The D51 backup. `bak_<issue>_<what>` is the house convention — 24 such tables
#: are live on production (`bak_2871_events`, `bak_4586_futures_markets`, …).
BAK_TABLE = "bak_4745_empty_book_openings"

#: Rows per call. Two correlated laterals per row over `futures_odds_snapshots`;
#: 1,756 rows measured at ~5s, so a page of 2,000 sits inside the request budget
#: with room for the backup copy in the same transaction.
DEFAULT_LIMIT = 2000
MAX_LIMIT = 5000

#: Named refusals, so a reader of the payload never has to infer one.
REASON_REPLACEMENT_EQUALS_STORED = "replacement_equals_stored"

_GUARD_ON_EARLIEST = lone_ask_on_empty_book_sql("bad")
_GUARD_ON_CANDIDATE = lone_ask_on_empty_book_sql("fos")

#: The bound. ONE rendering, used by the plan, the backup and the apply alike,
#: so the three cannot drift into disagreeing about which rows are in scope.
_BOUND_SQL = f"""
    SELECT fo.id AS outcome_id,
           fo.opening_probability AS before_opening,
           fo.opening_source AS before_opening_source,
           fo.calibration_probability AS before_calibration,
           bad.probability AS bad_value,
           honest.probability AS honest_value
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    CROSS JOIN LATERAL (
        SELECT fos.probability, fos.bookmaker, fos.yes_bid, fos.yes_ask, fos.last_price
        FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id
          AND fos.probability > 0 AND fos.probability < 1
        ORDER BY fos.captured_at ASC
        LIMIT 1
    ) bad
    LEFT JOIN LATERAL (
        SELECT fos.probability
        FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id
          AND fos.probability > 0 AND fos.probability < 1
          AND NOT {_GUARD_ON_CANDIDATE}
        ORDER BY fos.captured_at ASC
        LIMIT 1
    ) honest ON true
    WHERE fm.status = 'resolved'
      AND fo.opening_source = 'first_snapshot'
      AND fo.opening_probability IS NOT NULL
      AND {_GUARD_ON_EARLIEST}
      AND fo.opening_probability = bad.probability
      AND fo.id > :after_id
    ORDER BY fo.id
    LIMIT :page_limit
"""

#: `CREATE TABLE ... AS SELECT ... WHERE false` rather than a spelled-out DDL:
#: the backup inherits `futures_outcomes`' own column types, so a restore can
#: never lose precision to a hand-written `NUMERIC(7,6)` that drifts from the
#: column it mirrors.
_BAK_CREATE = f"""
    CREATE TABLE IF NOT EXISTS {BAK_TABLE} AS
    SELECT fo.id AS outcome_id,
           fo.opening_probability,
           fo.opening_source,
           fo.calibration_probability,
           NOW() AS backed_up_at
    FROM futures_outcomes fo
    WHERE false
"""

_BAK_INDEX = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk ON {BAK_TABLE} (outcome_id)"
)

#: Never overwrite an existing backup row. A leg may legitimately be repaired,
#: restored and repaired again; the FIRST backup is the one that predates this
#: rail, and re-copying after an apply would back up the repaired value and make
#: the undo a no-op.
_BAK_COPY = f"""
    INSERT INTO {BAK_TABLE} (outcome_id, opening_probability, opening_source,
                             calibration_probability, backed_up_at)
    SELECT s.outcome_id, s.before_opening, s.before_opening_source,
           s.before_calibration, NOW()
    FROM ({_BOUND_SQL}) s
    ON CONFLICT (outcome_id) DO NOTHING
"""

#: The D51 gate. Counts in-scope rows with NO backup row — and it is a COUNT
#: over the bound rather than a comparison of two totals, because two totals can
#: agree while naming different rows.
_BAK_MISSING = f"""
    SELECT count(*) FROM ({_BOUND_SQL}) s
    WHERE NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.outcome_id = s.outcome_id)
"""

#: The write. Re-derives the bound INSIDE the UPDATE rather than trusting the
#: ids the plan produced (the `repair_golf_round_closing_line` lesson): plan and
#: apply may be seconds apart, and a row the pipeline touched in between must
#: not be rewritten from a stale reading. A row that has moved simply falls out
#: of the bound.
#:
#: `fo.opening_probability` inside the SET reads the row's PRE-UPDATE value —
#: that is what makes "calibration was a verbatim copy of the discredited
#: opening" testable in the same statement that replaces the opening.
_APPLY_SQL = f"""
    WITH scope AS ({_BOUND_SQL})
    UPDATE futures_outcomes fo
    SET opening_probability = s.honest_value,
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

#: The undo, as ONE statement. `IS DISTINCT FROM` makes it idempotent and makes
#: its rowcount mean "rows actually put back" rather than "rows visited".
_RESTORE_SQL = f"""
    UPDATE futures_outcomes fo
    SET opening_probability = b.opening_probability,
        opening_source = b.opening_source,
        calibration_probability = b.calibration_probability
    FROM {BAK_TABLE} b
    WHERE fo.id = b.outcome_id
      AND (fo.opening_probability IS DISTINCT FROM b.opening_probability
           OR fo.opening_source IS DISTINCT FROM b.opening_source
           OR fo.calibration_probability IS DISTINCT FROM b.calibration_probability)
"""

_RESTORE_PENDING = f"""
    SELECT count(*) FROM futures_outcomes fo
    JOIN {BAK_TABLE} b ON b.outcome_id = fo.id
    WHERE fo.opening_probability IS DISTINCT FROM b.opening_probability
       OR fo.opening_source IS DISTINCT FROM b.opening_source
       OR fo.calibration_probability IS DISTINCT FROM b.calibration_probability
"""

_BAK_EXISTS = f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"


def restore_command() -> str:
    """The one command that puts it back (D51). Printed by every apply."""
    return (
        'source ~/.claude/.env && curl -s -X POST -H '
        '"Authorization: Bearer $ADMIN_TOKEN" '
        '"$BAINLUCK_API/api/admin/repairs/kalshi-empty-book-openings-restore'
        '?apply=true"'
    )


def classify(row: Any) -> tuple[str, Optional[float], Optional[str]]:
    """``(action, new_opening, refusal)`` for one bound row.

    Split out of the SQL so the decision can be read, tested and mutated
    without a database — the SQL and this function are asserted to agree on
    every arm by the real-Postgres gate.
    """
    honest = None if row.honest_value is None else float(row.honest_value)
    bad = None if row.bad_value is None else float(row.bad_value)
    if honest is not None and bad is not None and honest == bad:
        # A later snapshot carried a real book at the same number. Writing it
        # changes nothing; counting it as repaired would overstate the ship.
        return "refused", None, REASON_REPLACEMENT_EQUALS_STORED
    if honest is None:
        return "withdraw", None, None
    return "correct", honest, None


def _record(row: Any) -> dict[str, Any]:
    before_open = None if row.before_opening is None else float(row.before_opening)
    before_cal = (
        None if row.before_calibration is None else float(row.before_calibration)
    )
    return {
        "outcome_id": row.outcome_id,
        "before_opening": before_open,
        "before_calibration": before_cal,
        # What a reader is shown today: COALESCE(calibration, opening).
        "published_now": before_open if before_cal is None else before_cal,
        # True only for the arms where the curve reads the discredited number.
        "reader_visible": before_cal is None or before_cal == before_open,
        "bad_value": None if row.bad_value is None else float(row.bad_value),
    }


async def repair(
    session,
    apply: bool = False,
    limit: Optional[int] = None,
    after_id: Optional[int] = None,
) -> dict[str, Any]:
    """Plan (and optionally apply) one page of the #4745 withdrawal.

    Returns a payload complete enough to BE the receipt: every in-scope row with
    what is published for it today, what replaces it, and — for the rows nothing
    replaces — that they leave the curve.
    """
    page_limit = min(int(limit or DEFAULT_LIMIT), MAX_LIMIT)
    params = {"after_id": int(after_id or 0), "page_limit": page_limit}

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
    # The half of the ship a reader can see: rows where the curve price IS the
    # discredited number, and no replacement exists to take its place.
    leaves_the_curve = [r for r in withdrawn if r["reader_visible"]]
    repriced_visibly = [r for r in corrected if r["reader_visible"]]

    census = {
        "issue": ISSUE,
        "examined": len(rows),
        "corrected": len(corrected),
        "withdrawn": len(withdrawn),
        "refused": len(refused),
        "leaves_the_curve": len(leaves_the_curve),
        "repriced_visibly": len(repriced_visibly),
        # A page that repairs its rows removes them from its own bound, so an
        # empty page is the end of the walk and a remaining count is fiction.
        "scan_exhausted": len(rows) < page_limit,
        "next_after_id": rows[-1].outcome_id if rows else after_id,
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
        "%s repair applied: %s outcomes — %s withdrawn (%s of them leave the "
        "published curve), %s repriced. Backup in %s. D51 undo:\n%s",
        ISSUE, changed, len(withdrawn), len(leaves_the_curve),
        len(corrected), BAK_TABLE, restore_command(),
    )
    return census


async def restore(session, apply: bool = False) -> dict[str, Any]:
    """Put every backed-up row back to the value it held before the repair."""
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
    logger.warning("%s restore: %s outcomes put back from %s", ISSUE, restored, BAK_TABLE)
    return census
