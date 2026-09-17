"""#6619 — un-say the half-market verdicts we wrote from the full-time score.

THE SIBLING ARM OF #4923, FOR THE VENUE THAT HAS NO TICKER. #4923 repaired the
rows whose Kalshi ticker series carried a period token. This repairs the rows
where the period was invisible to that classifier: Polymarket's `external_id`
is a bare integer (market 60040627 carries `'977353'`), so `_ticker_period`
found no series, answered `None`, and every caller graded a HALF market against
the WHOLE GAME's score. The segment marker sat unread in `futures_markets.name`.

WHAT A READER SEES TODAY. `/futures/60040627` — *Deportivo Alavés vs. Valencia
CF - Halftime Result*:

    Valencia CF  WON        "Markets gave this just 0%."
    Settled — Valencia CF won.
    Valencia CF      · Won  · 100% Settled   (opened 21%)
    Draw             · Lost                  (opened 45%)   <- the priced favourite
    Deportivo Alavés · Lost                  (opened 32%)

The match finished **0–1 at full time**. Nothing we hold says who led at half.
Note that the damage is not only the crown: `Draw`, the outcome the market
itself opened most likely at 45%, is printed `Lost` on the same missing
evidence. This repair clears the negative legs too, for that reason.

THE PRODUCER IS FIXED IN PR #6621 (`_market_period` = ticker first, then name),
AND THIS SCRIPT CANNOT RUN BEFORE THAT DEPLOYS. That is not a warning in a
docstring — it is enforced, and for free. `_market_period` and `_name_period`
are imported below to DECIDE the cohort, and they exist only in the fixed
producer, so on an unpatched dyno this file raises ImportError at startup and
writes nothing. #4923 had to ask a human to sequence this ("THIS SCRIPT MUST NOT
RUN BEFORE THAT DEPLOYS"); here the ordering is structural, because the beat
would otherwise re-write within six hours exactly what was cleared.

THE COHORT IS DECIDED BY THE REAL CLASSIFIER, NOT BY A REGEX MIRRORED INTO SQL.
This is the one deliberate departure from #4923's shape and it is the most
important line in the file. #4923 re-expressed `_PERIOD_SERIES_RE` as POSIX ARE
and the mirror drifted: a day-of-month ran into a club code
(`KXMLSSPREAD-26APR22HOUSD` → `22H`), and **70 correct verdicts across 12
markets were deleted** on production before anyone noticed — the harder bug,
because a false positive here silently destroys a right answer instead of
printing a wrong one. So SQL below does no classification at all. It runs a
prefilter that is a PROVABLE SUPERSET, and Python then asks the producer's own
functions. There is one definition of "which period is this market about" and
this script does not own a copy of it.

    prefilter : resolution_source = 'game_score' AND name ILIKE '%half%'
    decision  : _ticker_period(ticker) is None AND _name_period(name) is not None

The prefilter is a superset by construction: every alternative in
`_NAME_PERIOD_RE` (`half[ -]?time`, `(1st|first)\\s+half`, `(2nd|second)\\s+half`)
contains the literal substring "half", and both tests are case-insensitive. So
a row the decision would accept can never be one the prefilter dropped. Pinned
by `test_repair_6619_half_verdicts.py`, which re-derives the containment from
the live regex rather than trusting this paragraph.

`_ticker_period(ticker) is None` IS THE DISJOINTNESS GUARANTEE. A row whose
ticker classifies went through the INTENDED path — `_get_halftime_score` for a
first half, `_period_scores` for a second — and may well be right; it is #4923's
and #5052's business and this script must never touch it. Measured on production
2026-09-17: of the 8,991 half-named `game_score` outcomes on non-Polymarket
ids, the 12 series families they live in (`KXNBA1HSPREAD`, `KXNBA2HWINNER`, …)
**all classify**, so the two cohorts are not merely intended to be disjoint —
they are measured disjoint, and this script's scope is empty outside Polymarket.

THE COHORT, measured on production 2026-09-17 ~01:35Z:

    first half  (1h)    120 markets    356 outcomes    118 crowned
    second half (2h)     90 markets    258 outcomes     87 crowned
    -------------------------------------------------------------
    total               210 markets    614 outcomes    205 crowned

All 210 names are accepted by `_NAME_PERIOD_RE` — the prefilter's residue on the
live population is **0 markets**, so the superset is, here, an equality.

THE POPULATION GROWS UNTIL #6621 DEPLOYS. The cert measured 203 markets at
2026-09-16 20:55Z; it read 210 fifteen hours later, because the beat is still
writing this defect every six hours. That is why the sanity floor below is a
LOWER bound and why `explain_small_plan` asks the manifest which of "drained" or
"broken predicate" happened, rather than treating any small plan as suspicious.

WHAT THIS CLEARS, AND WHY IT COMPUTES NOTHING. It sets `is_winner` and
`resolution_source` to NULL — the ungraded state, which every surface already
renders honestly (`_settled_grade_fields` gates on `resolution_source`, so the
row keeps its label and its price and simply stops claiming a result). It does
NOT compute the right answer, and on this cohort it could not: **0 of the 130
events hold a period linescore and 0 hold a single `scoring_plays` row**
(measured 2026-09-17, all 130). There is no half score to grade against for any
row in scope, so every one of the 614 verdicts is unfounded and none is
recoverable. Gotcha #21 says a bulk `is_winner` reset needs an immediate
re-resolve source; the source here is the VENUE — `game_score` is not in
`OVERWRITABLE_WINNER_SOURCES_SQL` and the candidate scan drops any market
already holding one, so clearing is precisely what lets Polymarket's own
settlement land on these rows. Clearing is what makes that possible; guessing is
what made this issue.

THE READER CONSEQUENCE, STATED PLAINLY. 210 settled half markets stop naming a
winner. A reader who today sees "Settled — Valencia CF won" will see the three
outcomes with their prices and no verdict, until the venue settles them. That is
the intended outcome and it is the #4923 ruling applied unchanged: a wrong
verdict is replaced by no verdict first. Withdrawing 205 crowns we cannot
justify is the ship, not a cost of it.

D51(b) — `--apply` REFUSES until `--backup` has copied every in-scope row, and
the undo is one command:

    python3 scripts/restore_6619_half_verdicts_from_the_full_time_score.py --apply

    python3 scripts/repair_6619_half_verdicts_from_the_full_time_score.py            # preview
    python3 scripts/repair_6619_half_verdicts_from_the_full_time_score.py --backup   # copy + reconcile
    python3 scripts/repair_6619_half_verdicts_from_the_full_time_score.py --apply --limit 10   # canary
    python3 scripts/repair_6619_half_verdicts_from_the_full_time_score.py --apply    # the rest

Heroku one-off (gotcha #48 — a non-detached run returns empty stdout that reads
like success; PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):

    heroku run:detached -a bainluck \\
      "python3 scripts/repair_6619_half_verdicts_from_the_full_time_score.py --backup"
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# THE IMPORT IS THE DEPLOY GATE, and it is deliberately at module scope so the
# refusal happens before argparse, before any session, before any write. These
# names exist only in the fixed producer (PR #6621). On a dyno still running the
# code that CAUSED this defect, the script cannot start — which is the correct
# behaviour, because the beat would re-write the cleared rows inside six hours.
from app.tasks.backfill_winners import (  # noqa: E402
    _name_period,
    _ticker_period,
)

BAK_TABLE = "bak_6619_futures_outcomes"
#: What the repair DID, as opposed to what the rows WERE (the CERT-2439 lesson,
#: inherited from #4586 via #4923 rather than re-learned): a full-row backup
#: records where a row CAME FROM and cannot record that this script is what
#: moved it. Without it a restore can only ask "does the live row differ from
#: its backup?", which is also true of a row the VENUE has settled since — and
#: the undo would then revert Polymarket's newer, correct verdict back to our
#: invented one.
MANIFEST_TABLE = "bak_6619_repair_manifest"

#: The sanity floor, as a LOWER bound on a population that is still GROWING.
#: 614 in-scope outcomes were measured at 2026-09-17 01:35Z, up from the cert's
#: 203 markets fifteen hours earlier, because the producer is unfixed in
#: production until #6621 deploys. 500 leaves room for the venue settling some
#: rows out of scope on its own (which removes them legitimately) while still
#: catching a predicate that has stopped matching. A plan below it is not
#: overridden by a flag — `explain_small_plan` asks the manifest which of the
#: two causes it is.
SANITY_FLOOR = 500

#: THE PREFILTER, AND IT CLASSIFIES NOTHING. Both conjuncts are chosen to be a
#: provable superset of the Python decision applied in `in_scope` below:
#:
#:   * `resolution_source = 'game_score'` — the only value this repair clears,
#:     and the same value the forward write's compare-and-swap requires.
#:   * `name ILIKE '%half%'` — every alternative in `_NAME_PERIOD_RE` contains
#:     the literal "half" (`half[ -]?time`, `(1st|first)\s+half`,
#:     `(2nd|second)\s+half`), and both matches are case-insensitive.
#:
#: Widening a prefilter is always safe here (the Python decision re-filters);
#: NARROWING it silently shrinks the cohort, which is why the containment has a
#: test that derives it from the regex rather than reading this comment.
_PREFILTER = """
    fo.resolution_source = 'game_score'
    AND fm.name ILIKE '%half%'
"""

#: One row per candidate outcome, with enough of the market for `in_scope` to
#: decide and for a person to read the printed plan without this docstring.
_CANDIDATE_SQL = f"""
SELECT fo.id                AS outcome_id,
       fo.name              AS outcome_name,
       fo.is_winner         AS is_winner,
       fm.id                AS market_id,
       fm.external_id       AS ticker,
       fm.name              AS market_name
  FROM futures_outcomes fo
  JOIN futures_markets fm ON fm.id = fo.market_id
 WHERE {_PREFILTER}
 ORDER BY fo.id
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
    # been backed up — which is every database on the documented preview-only
    # first run (#4669). A missing table still yields an empty reconciliation,
    # and `backup_is_exact({})` is False, so `--apply` still refuses (gotcha #53).
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    "man_exists": f"SELECT to_regclass('{MANIFEST_TABLE}') IS NOT NULL",
    "man_count": f"SELECT count(*) FROM {MANIFEST_TABLE}",
    # THE FORWARD WRITE, a compare-and-swap on the value this repair exists to
    # remove. If anything re-graded the row between the plan and the write — the
    # venue's own settlement is exactly what we WANT to arrive — the statement
    # no-ops instead of overwriting a fresher, better verdict with a NULL.
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


def in_scope(ticker, market_name) -> str | None:
    """The period this row is wrongly graded for, or ``None`` if out of scope.

    THE WHOLE COHORT DECISION, and it delegates both halves of it to the
    producer's own classifier so there is exactly one definition in the repo.

      * ``_ticker_period(...) is None`` — the disjointness guarantee. A ticker
        that classifies went through the intended period path and may hold a
        CORRECT verdict; #4923 owns those and this script must not touch one.
      * ``_name_period(...) is not None`` — the market's name binds it to a half,
        which is the signal the old producer could not see.

    Returns the period (``"1h"``/``"2h"``) rather than a bool so the printed
    census can be split the way the issue reports it, without a second
    classification pass that could disagree with this one.
    """
    if _ticker_period(ticker) is not None:
        return None
    return _name_period(market_name)


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
        f"an expected {SANITY_FLOOR}+ are accounted for. Either the prefilter "
        f"stopped matching or the classifier changed under it. Do NOT lower the "
        f"floor; find the rows."
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


def census(rows) -> dict:
    """In-scope rows split by period, for a plan that can be diffed with the issue."""
    out: dict = {}
    for r, period in rows:
        b = out.setdefault(period, {"outcomes": 0, "markets": set(), "crowned": 0})
        b["outcomes"] += 1
        b["markets"].add(r.market_id)
        b["crowned"] += 1 if r.is_winner else 0
    return out


async def run(args) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        candidates = (await s.execute(text(_CANDIDATE_SQL))).all()

        # THE DECISION, in Python, by the producer's own functions. Rows the
        # prefilter caught but the classifier refuses are REPORTED, not dropped
        # silently: a growing residue here is the early warning that the
        # prefilter and the regex have drifted apart.
        scoped = [(r, p) for r in candidates if (p := in_scope(r.ticker, r.market_name))]
        residue = len(candidates) - len(scoped)
        applied_before = await manifest_count(s)

        print("=== #6619 half-verdict repair ===")
        print(f"prefilter candidates           : {len(candidates)}")
        print(f"refused by the real classifier : {residue} "
              f"(ticker already classifies, or the name is not a half)")
        print(f"IN SCOPE                       : {len(scoped)}")
        print()
        print(f"{'period':>8} {'outcomes':>9} {'markets':>8} {'crowned':>8}")
        for period, b in sorted(census(scoped).items()):
            print(f"{period:>8} {b['outcomes']:>9} {len(b['markets']):>8} "
                  f"{b['crowned']:>8}")
        print(f"{'TOTAL':>8} {len(scoped):>9}")
        print(f"already applied in {MANIFEST_TABLE}: {applied_before}")

        print("\nfirst 10 rows:")
        for r, period in scoped[:10]:
            print(f"  {r.outcome_id:>10} {period} win={str(r.is_winner):>5} "
                  f"{(r.market_name or '')[:46]:<46} | {(r.outcome_name or '')[:28]}")

        if not scoped:
            if applied_before:
                print(f"\nNothing in scope and {applied_before} rows applied — "
                      f"idempotent no-op, the cohort is drained.")
            else:
                print("\nNothing in scope and nothing ever applied — that is not a "
                      "drained backlog, it is a predicate that matches nothing. STOP.")
            return

        small = explain_small_plan(len(scoped), applied_before)
        if small:
            print(f"\n⚠️  plan is below the sanity floor of {SANITY_FLOOR}.")
            print(f"    {small}")
            if small.startswith("PREDICATE BROKE"):
                print("\n❌ REFUSING — see above.")
                return

        outcome_ids = [int(r.outcome_id) for r, _ in scoped]

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
            print("\nPREVIEW — no writes. Pass --backup to copy, then --apply to "
                  "clear. Undo: "
                  "restore_6619_half_verdicts_from_the_full_time_score.py --apply")
            return

        if not clean:
            print(f"\n❌ REFUSING TO APPLY — the backup is not exact. Run --backup "
                  f"first; {BAK_TABLE} must hold every in-scope row.")
            return

        doable = scoped[: args.limit] if args.limit else scoped
        print(f"\n=== applying {len(doable)} of {len(scoped)} ===")

        # Same transaction as the writes it describes, so a rolled-back clear
        # cannot leave a manifest row telling the restore to put a verdict back
        # on a row this script never touched.
        await s.execute(text(SQL["man_create"]))

        now = datetime.now(timezone.utc)
        cleared, declined = 0, 0
        for r, _ in doable:
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
        print(f"Undo: restore_6619_half_verdicts_from_the_full_time_score.py --apply "
              f"(restores only these {cleared}, and only while they are still "
              f"ungraded).")

        after = (await s.execute(text(_CANDIDATE_SQL))).all()
        still = sum(1 for r in after if in_scope(r.ticker, r.market_name))
        print(f"POST-REPAIR: {still} outcomes still carry a half `game_score` "
              f"verdict (target: 0 after a full run).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help=f"copy in-scope futures_outcomes rows into {BAK_TABLE}")
    p.add_argument("--apply", action="store_true",
                   help="clear the verdicts (refuses unless the backup reconciles)")
    p.add_argument("--limit", type=int, default=0,
                   help="the canary: apply only the first N clears (0 = all)")
    asyncio.run(run(p.parse_args()))
