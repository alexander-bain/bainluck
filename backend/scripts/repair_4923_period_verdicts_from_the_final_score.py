"""#4923 — un-say the period verdicts we wrote from the whole game's score.

WHAT A READER SEES TODAY. `/futures/60489789` — *Chicago Fire vs Miami: First
Half BTTS* — says **"Yes ✅ WON"**, *"Markets gave this just 1%"* and *"Settled —
Yes won."* The first half finished **1–0**. `/futures/60489769` says **"Over 1.5
2H goals scored — Won · 100% Settled"** about a second half with **one goal**.

Both are proved false by Kalshi's OWN grades of sibling markets on the same
event (15298466, final 1–1): `1st Half Correct Score → Chicago Fire wins 1H 1-0`
(`api_settlement`) and `First Half Total → Over 1.5 1H goals` **LOST**
(`clean_resolution`) pin the first half at 1–0, leaving the second half 0–1.

WHERE THEY CAME FROM. Two fallback resolvers in `backfill_winners` grade from
`events.home_score`/`away_score` when Kalshi has purged its settlement data, and
both answered period-bounded questions with the full-time number: the BTTS
branch `continue`d above the `_non_ml` guard, and `is_1h = "1h" in ticker_lower`
knew exactly one period. Both are fixed at the producer (PR #4944, CERT-2554)
and **THIS SCRIPT MUST NOT RUN BEFORE THAT DEPLOYS** — the beat runs every six
hours and would simply re-write what this clears.

WHAT THIS DOES, AND THE ONE THING IT REFUSES TO DO. It sets `is_winner` and
`resolution_source` to NULL on the cohort: the ungraded state, which every
surface already renders honestly (`_settled_grade_fields` gates on
`resolution_source`, so the row simply stops claiming a result). It does NOT
compute the right answer. For 0 of the 49 half-BTTS events do we hold
`box_score_data->home_period_scores`, so for most of this cohort there is no
half score to grade against — and gotcha #21 is the rule that a bulk `is_winner`
reset needs an immediate re-resolve source. The source here is the VENUE: with
`game_score` gone the market re-enters the candidate scan (whose HAVING excludes
any market already holding a non-overwritable winner), so Kalshi's own
settlement can land on it. Clearing is what makes that possible; guessing is
what made this issue.

Correct 2H grading — final minus halftime — is a separate follow-up. A wrong
verdict is replaced by no verdict first.

THE COHORT, measured on production 2026-09-10 22:30Z:

    second half                1,278 outcomes   291 markets   769 affirmative
    quarters                     321             39           271
    MLB first-N-inning windows   160             54            53
    half BTTS                     50             50            46
    ----------------------------------------------------------------------
    total                      1,809            434         1,139

1H spread/total rows are deliberately OUT of scope: those went through
`_get_halftime_score`, which reconstructs a real first-half score, and may be
right. Only 1H **BTTS** is in, because that branch never consulted a half score
at all.

D51(b) — `--apply` REFUSES until `--backup` has copied every in-scope row, and
the undo is one command:

    python3 scripts/restore_4923_period_verdicts_from_the_final_score.py --apply

    python3 scripts/repair_4923_period_verdicts_from_the_final_score.py            # plan only
    python3 scripts/repair_4923_period_verdicts_from_the_final_score.py --backup   # copy + reconcile
    python3 scripts/repair_4923_period_verdicts_from_the_final_score.py --apply --limit 10
    python3 scripts/repair_4923_period_verdicts_from_the_final_score.py --apply

Heroku one-off (gotcha #48 — a non-detached run returns empty stdout that reads
like success; PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):

    heroku run:detached -a bainluck \\
      "python3 scripts/repair_4923_period_verdicts_from_the_final_score.py --backup"
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_4923_futures_outcomes"
#: What the repair DID, as opposed to what the rows WERE (the CERT-2439 lesson,
#: earned by #4586's restore): a full-row backup records where a row CAME FROM
#: and cannot record that this script is what moved it. Without that, a restore
#: can only ask "does the live row differ from its backup?", which is also true
#: of a row the VENUE has legitimately graded since — and it would then revert
#: the venue's newer, correct verdict back to our invented one.
MANIFEST_TABLE = "bak_4923_repair_manifest"

#: The sanity floor. 1,809 in-scope outcomes were measured at 22:30Z and the
#: population is static once PR #4944 deploys, so a plan far below this is a
#: broken predicate — or a completed run. Those two causes need a
#: DISCRIMINATOR, not an override flag, which is what `explain_small_plan`
#: below is: it asks the manifest which one happened.
SANITY_FLOOR = 1500

#: THE SERIES FAMILY, AND NOTHING ELSE (#5023). A Kalshi ticker is
#: `<series>-<date><club><club>`, and the grammar below may only ever be matched
#: against the part before the first dash. `_ticker_period`
#: (`app/tasks/backfill_winners.py`) has always done this —
#: `series = ticker.split("-", 1)[0].lower()` — and its docstring names the
#: hazard outright: 282 event-linked markets carry an accidental `1h` in the
#: suffix, because `KXWTAMATCH-26JUL11HODCHA` is Hodzic vs Chan on the 11th.
#:
#: THE FIRST VERSION OF THIS FILE MATCHED THE WHOLE `external_id` AND THE
#: SUFFIX BIT BACK, on production, on the run this script was written for. A
#: day-of-month runs straight into a club code, so `2H` and `1Q` appear inside
#: dates:
#:
#:     KXMLSSPREAD-26APR**22H**OUSD        day 22 + HOUston   whole-game spread
#:     KXMLSBTTS-26MAY**02H**OUCOL         day 02 + HOUston   whole-game BTTS
#:     KXNCAAMBTOTAL-26FEB**22H**CBUCK     day 22 + Holy Cross
#:     KXNCAAMBSPREAD-26MAR**01Q**UINCAN   day 01 + QUINnipiac
#:
#: 70 correct verdicts across 12 markets were cleared that way — 57 whole-game
#: and 13 halftime-derived first halves. A false positive here does not print a
#: wrong answer, it silently deletes a right one, which is the harder bug to
#: notice and the reason `_ticker_period` was careful. Mirroring a Python
#: classifier into SQL means mirroring what it matches ON, not just its regex.
_SERIES = "split_part(fm.external_id, '-', 1)"

# THE COHORT. Every alternative names a PERIOD the final score cannot answer,
# and each is the POSIX-ARE form of one alternative in `_ticker_period`'s regex
# — the same four grammars measured over all 899 event-linked Kalshi series.
#
# `(^|[^H])` is the head-to-head carve-out. `KXEPLH2H` and `KXEPLH2HFINISH` are
# whole-game markets that contain the characters "2H"; a repair that clears them
# would delete verdicts that are correct. Python expresses this as a lookbehind;
# Postgres has none, so the carve-out is written as "a character that is not H,
# or the start of the string". Case-insensitive `~*` makes `[^H]` exclude both
# cases.
#
# The F-family is anchored to the END of the series (`$`, where the whole-ticker
# form needed the dash that begins the date suffix), because `F5` is otherwise a
# substring of college-football families (`KXNCAAF3QSPREAD` is NCAAF's third
# quarter — in scope, but via `[1-4]Q`).
_COHORT = f"""
    fo.resolution_source = 'game_score'
    AND (   {_SERIES} ~* '(^|[^H])[12]H[A-Z]*BTTS'
         OR {_SERIES} ~* '(^|[^H])2H'
         OR {_SERIES} ~* '[1-4]Q'
         OR {_SERIES} ~* 'F[357](SPREAD|TOTAL)?$' )
"""

#: One row per in-scope outcome, with enough of the market to make the printed
#: plan readable by a person who has not read this docstring.
_PLAN_SQL = f"""
SELECT fo.id                AS outcome_id,
       fo.name              AS outcome_name,
       fo.is_winner         AS is_winner,
       fm.id                AS market_id,
       fm.external_id       AS ticker,
       fm.name              AS market_name
  FROM futures_outcomes fo
  JOIN futures_markets fm ON fm.id = fo.market_id
 WHERE {_COHORT}
 ORDER BY fo.id
"""

#: The same population, split the way the issue reports it, so a run prints a
#: table that can be compared with the filed numbers rather than one total.
_CENSUS_SQL = f"""
SELECT CASE
         WHEN {_SERIES} ~* '(^|[^H])[12]H[A-Z]*BTTS' THEN 'half_btts'
         WHEN {_SERIES} ~* '(^|[^H])2H'              THEN 'second_half'
         WHEN {_SERIES} ~* '[1-4]Q'                  THEN 'quarter'
         ELSE 'mlb_window'
       END                                     AS cohort,
       count(*)                                AS outcomes,
       count(DISTINCT fm.id)                   AS markets,
       sum(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS affirmative
  FROM futures_outcomes fo
  JOIN futures_markets fm ON fm.id = fo.market_id
 WHERE {_COHORT}
 GROUP BY 1
 ORDER BY 2 DESC
"""

SQL = {
    # LIKE copies columns and types but NOT the foreign keys — a backup that
    # cascaded with its source would be no backup at all.
    "bak_create": f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} "
                  f"(LIKE futures_outcomes INCLUDING DEFAULTS)",
    "bak_index": f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk "
                 f"ON {BAK_TABLE} (id)",
    "bak_copy": f"INSERT INTO {BAK_TABLE} SELECT s.* FROM futures_outcomes s "
                f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    "bak_missing": f"SELECT count(*) FROM futures_outcomes s "
                   f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                   f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    # Asked BEFORE `bak_missing`, never instead: that statement names the backup
    # table in a subquery and raises UndefinedTable on a database that has never
    # been backed up — which is every database on the documented plan-only first
    # run (#4669). A missing table still yields an empty reconciliation, and
    # `backup_is_exact({})` is False, so `--apply` still refuses (gotcha #53).
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    "man_exists": f"SELECT to_regclass('{MANIFEST_TABLE}') IS NOT NULL",
    "man_count": f"SELECT count(*) FROM {MANIFEST_TABLE}",
    # THE FORWARD WRITE, and it is a compare-and-swap on the value this repair
    # exists to remove. If anything re-graded the row between the plan and the
    # write — the venue's own settlement is exactly what we WANT to arrive — the
    # statement no-ops instead of overwriting a fresher, better verdict with a
    # NULL.
    #
    # `last_updated` is deliberately NOT stamped. It is the PRICE clock three
    # surfaces read as "when did somebody last look at this number"
    # (LIVE-077-TOUCH-STAMP-PROVENANCE-GUARD / CERT-1936), and this script reads
    # no venue price. The guard's `settled` class would permit the stamp; a
    # permission is not a reason.
    "clear": "UPDATE futures_outcomes "
             "SET is_winner = NULL, resolution_source = NULL "
             "WHERE id = :oid AND resolution_source = 'game_score'",
    "man_create": f"CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} ("
                  f"  outcome_id  integer PRIMARY KEY,"
                  f"  market_id   integer NOT NULL,"
                  f"  applied_at  timestamptz NOT NULL DEFAULT NOW())",
    # A row can legitimately be cleared, restored and cleared again, so the
    # later row REPLACES the earlier one; `DO NOTHING` would leave the restore
    # reasoning about a move that is two states stale.
    "man_record": f"INSERT INTO {MANIFEST_TABLE} (outcome_id, market_id, applied_at) "
                  f"VALUES (:oid, :mid, :now) "
                  f"ON CONFLICT (outcome_id) DO UPDATE SET "
                  f"  market_id = EXCLUDED.market_id,"
                  f"  applied_at = EXCLUDED.applied_at",
}


def backup_is_exact(recon) -> bool:
    """The D51 gate: every in-scope row has a backup row, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo (gotcha #53).
    """
    return bool(recon) and all(n == 0 for n in recon.values())


def explain_small_plan(plan_count: int, manifest_rows: int) -> str:
    """Why is the plan below the floor — a broken predicate, or a done job?

    A sanity floor that names two causes needs a DISCRIMINATOR, not an override
    flag: `--allow-small` would let the broken-predicate case through wearing
    the completed-run case's clothes. The manifest is the discriminator, because
    only a successful forward write puts a row in it.
    """
    if plan_count >= SANITY_FLOOR:
        return ""
    if manifest_rows + plan_count >= SANITY_FLOOR:
        return (
            f"ALREADY APPLIED — {manifest_rows} rows are in {MANIFEST_TABLE} and "
            f"{plan_count} remain in scope; together they clear the floor of "
            f"{SANITY_FLOOR}. This is a drained backlog, not a broken predicate."
        )
    return (
        f"PREDICATE BROKE — only {plan_count} rows are in scope and "
        f"{manifest_rows} were ever applied, so {plan_count + manifest_rows} of "
        f"an expected {SANITY_FLOOR}+ are accounted for. Something in the cohort "
        f"regexes stopped matching. Do NOT widen the floor; find the rows."
    )


async def backup(session, outcome_ids):
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    await session.execute(text(SQL["bak_index"]))
    await session.execute(text(SQL["bak_copy"]), {"ids": outcome_ids})
    await session.commit()


async def _table_exists(session, key) -> bool:
    from sqlalchemy import text

    return bool((await session.execute(text(SQL[key]))).scalar_one())


async def manifest_count(session) -> int:
    from sqlalchemy import text

    if not await _table_exists(session, "man_exists"):
        return 0
    return int((await session.execute(text(SQL["man_count"]))).scalar_one())


async def reconcile_backup(session, outcome_ids) -> dict:
    from sqlalchemy import text

    missing = (
        await session.execute(text(SQL["bak_missing"]), {"ids": outcome_ids})
    ).scalar_one()
    return {"futures_outcomes": int(missing)}


async def run(args) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        rows = (await s.execute(text(_PLAN_SQL))).all()
        census = (await s.execute(text(_CENSUS_SQL))).all()
        applied_before = await manifest_count(s)

        print(f"=== #4923 period-verdict repair: {len(rows)} outcomes in scope ===")
        print(f"{'cohort':>14} {'outcomes':>9} {'markets':>8} {'affirmative':>12}")
        for c in census:
            print(f"{c.cohort:>14} {c.outcomes:>9} {c.markets:>8} {c.affirmative:>12}")
        print(f"{'TOTAL':>14} {len(rows):>9}")
        print(f"already applied in {MANIFEST_TABLE}: {applied_before}")

        print("\nfirst 10 rows:")
        for r in rows[:10]:
            print(f"  {r.outcome_id:>10} win={str(r.is_winner):>5} "
                  f"{(r.ticker or '')[:34]:<34} | {(r.outcome_name or '')[:40]}")

        if not rows:
            if applied_before:
                print(f"\nNothing in scope and {applied_before} rows applied — "
                      f"idempotent no-op, the cohort is drained.")
            else:
                print("\nNothing in scope and nothing ever applied — that is not a "
                      "drained backlog, it is a predicate that matches nothing. STOP.")
            return

        small = explain_small_plan(len(rows), applied_before)
        if small:
            print(f"\n⚠️  plan is below the sanity floor of {SANITY_FLOOR}.")
            print(f"    {small}")
            if small.startswith("PREDICATE BROKE"):
                print("\n❌ REFUSING — see above.")
                return

        outcome_ids = [int(r.outcome_id) for r in rows]

        if args.backup:
            print(f"\n=== backup: copying {len(outcome_ids)} futures_outcomes rows "
                  f"into {BAK_TABLE} ===")
            await backup(s, outcome_ids)

        if await _table_exists(s, "bak_exists"):
            recon = await reconcile_backup(s, outcome_ids)
            print("\n=== backup reconciliation (in-scope rows with no backup row) ===")
            for tbl, n in recon.items():
                print(f"  {tbl}: {n}")
        else:
            recon = {}
            print(f"\n=== backup reconciliation: {BAK_TABLE} does not exist yet ===")
            print("  nothing has been backed up, so there is nothing to reconcile.")
        clean = backup_is_exact(recon)

        if not args.apply:
            print("\nDRY-RUN — no writes. Pass --backup to copy, then --apply to "
                  "clear. Undo: "
                  "restore_4923_period_verdicts_from_the_final_score.py --apply")
            return

        if not clean:
            print(f"\n❌ REFUSING TO APPLY — the backup is not exact. Run --backup "
                  f"first; {BAK_TABLE} must hold every in-scope row.")
            return

        doable = rows[: args.limit] if args.limit else rows
        print(f"\n=== applying {len(doable)} of {len(rows)} ===")

        # Same transaction as the writes it describes, so a rolled-back clear
        # cannot leave a manifest row telling the restore to put a verdict back
        # on a row this script never touched.
        await s.execute(text(SQL["man_create"]))

        now = datetime.now(timezone.utc)
        cleared, declined = 0, 0
        for r in doable:
            res = await s.execute(text(SQL["clear"]), {"oid": int(r.outcome_id)})
            if (res.rowcount or 0) == 0:
                # The CAS declined: the row was re-graded between the plan and
                # the write, which is the outcome this repair is trying to make
                # possible. Report it, never force it, and write NO manifest row.
                declined += 1
                continue
            await s.execute(text(SQL["man_record"]), {
                "oid": int(r.outcome_id),
                "mid": int(r.market_id),
                "now": now,
            })
            cleared += 1

        await s.commit()
        print(f"\nCOMMITTED: cleared {cleared} outcomes, {declined} declined by the "
              f"compare-and-swap (re-graded since the plan — that is the good case).")
        print(f"Undo: restore_4923_period_verdicts_from_the_final_score.py --apply "
              f"(restores only these {cleared}, and only while they are still "
              f"ungraded).")

        after = (await s.execute(text(_PLAN_SQL))).all()
        print(f"POST-REPAIR: {len(after)} outcomes still carry a period "
              f"`game_score` verdict (target: 0 after a full run).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help=f"copy in-scope futures_outcomes rows into {BAK_TABLE}")
    p.add_argument("--apply", action="store_true",
                   help="clear the verdicts (refuses unless the backup reconciles)")
    p.add_argument("--limit", type=int, default=0,
                   help="apply only the first N clears (0 = all)")
    asyncio.run(run(p.parse_args()))
