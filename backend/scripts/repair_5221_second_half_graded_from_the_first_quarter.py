"""#5221 — un-say the 2H verdicts we computed as "final minus the FIRST QUARTER".

WHAT A READER SEES TODAY. `KXNBA2HWINNER-26FEB19BOSGSW` says **Boston won the
second half**. Boston scored 47 after the interval; Golden State scored 59.
`KXNBA2HWINNER-26MAR18PORIND` credits Portland with a second half Indiana won
57–48. On the totals it is worse: **126 of 153** `KXNBA2HTOTAL` legs are served
the wrong verdict, because a 2H total computed over three quarters clears almost
every line.

WHERE THEY CAME FROM. `_get_halftime_score`'s box-score fallback returned
`home_period_scores[0]` behind a `len(...) >= 2` guard whose comment assumed the
linescore held HALVES. On a quarter-scored sport `[0]` is Q1, so "second half"
was `final - Q1` — three quarters of scoring. #5052 wired that helper into the
refusing loop on 2026-09-11 and it graded the whole population in one 55-minute
window (13:01Z-13:56Z). The producer is fixed in the commit this script ships
with, and **THIS SCRIPT MUST NOT RUN BEFORE THAT DEPLOYS** — the beat runs every
six hours and would re-write exactly what this clears.

THE COHORT, measured on production 2026-09-11 14:1xZ:

    KXNBA2HWINNER    608 outcomes  204 markets     80 wrong  (+2 refused, below)
    KXNBA2HTOTAL     153            17            126 wrong
    KXNBA2HSPREAD    158            15             27 wrong
    KXNCAAF2HSPREAD   73             4             15 wrong
    ----------------------------------------------------------------
    total            992           240            248 clearable / 250 wrong

Every one of the 992 sits on a quarter-scored sport (`basketball_nba`,
`americanfootball_ncaaf`), every one fell through to the box score because the
event holds no first-half `scoring_plays` row, and **the buggy formula
reproduces all 992 stored values exactly**. Not one row in this population came
from anywhere else. `basketball_ncaab` — which plays halves and for which `[0]`
was right — does not appear at all.

WHAT THIS DOES, AND THE TWO THINGS IT REFUSES TO DO.

It sets `is_winner` and `resolution_source` to NULL on the rows the linescore
REFUTES: the ungraded state, which every surface already renders honestly
(`_settled_grade_fields` gates on `resolution_source`, so the row simply stops
claiming a result). The fixed producer re-grades them on its next pass — that is
gotcha #21's required immediate re-resolve source, and it is why this ships
behind the producer fix rather than beside it.

**It does not compute the replacement.** The verdicts printed here are a FILTER,
never a write. Every value that lands back on a row is written by
`_resolve_kalshi_spread_total_from_scores`, so there is one reading of "who won
the second half" in this codebase and this script is not a second one. #4923's
repair could not compute the right answer; this one deliberately does not.

**It does not clear a row it agrees with.** 742 of the 992 were computed from
the wrong number and happen to land on the right verdict. Clearing those would
un-say 742 correct results for up to six hours to fix 248 — a net regression for
a reader. They are reported and left alone.

WHY THE FILTER IMPORTS AND NEVER MIRRORS. The verdict each row SHOULD carry is
asked of the producer's own graders — `_decide_three_way_winner`,
`_spread_outcome_is_winner`, `_total_outcome_is_winner`, `_first_half_period_count`
— and not re-implemented here. A mirror measures a different population than the
one production wrote: `_decide_three_way_winner` tokenises with a bare
`.lower().split()`, and a "better" copy using `normalize_team_name` grades four
markets this one refuses. That drift IS the #4923 lesson, and #5023 is what it
costs.

THE ADMISSION TEST, which is what makes this safe to run at any time. A row is
only clearable when the BUGGY formula also reproduces its stored value. Once the
producer fix deploys, correctly-graded 2H rows carry `game_score` too and are
structurally identical to these — so a purely structural cohort would start
eating correct verdicts, and a date bound would be a guess about release
timing. "Final minus Q1 explains what is stored, and final minus the half does
not" is decidable from the row alone, is true of exactly the rows this bug
wrote, and stops being true the moment the row is re-graded. It needs no clock.

THE RESIDUE, STATED RATHER THAN QUIETLY DROPPED. Four `KXNBA2HWINNER` markets
carry TWO legs ("Minnesota wins 2nd half" / "Utah wins 2nd half"), and the
producer grades that shape inline in `_resolve_kalshi_spread_total_from_scores`
rather than through a pure function — a third copy of the side-picker #2352
consolidated twice already. There is nothing to import, so all 8 outcomes are
REFUSED and reported. Two of them are wrong (`KXNBA2HWINNER-26MAR18PORIND`).
Repairing them needs that branch extracted first; filed rather than guessed.

D51(b) — `--apply` REFUSES until `--backup` has copied every clearable row, and
the undo is one command:

    python3 scripts/restore_5221_second_half_graded_from_the_first_quarter.py --apply

    python3 scripts/repair_5221_second_half_graded_from_the_first_quarter.py            # plan only
    python3 scripts/repair_5221_second_half_graded_from_the_first_quarter.py --backup   # copy + reconcile
    python3 scripts/repair_5221_second_half_graded_from_the_first_quarter.py --apply --limit 10
    python3 scripts/repair_5221_second_half_graded_from_the_first_quarter.py --apply

Heroku one-off (gotcha #48 — a non-detached run returns empty stdout that reads
like success; PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):

    heroku run:detached -a bainluck \\
      "python3 scripts/repair_5221_second_half_graded_from_the_first_quarter.py --backup"
"""
import argparse
import asyncio
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_5221_futures_outcomes"
#: What the repair DID, as opposed to what the rows WERE (the CERT-2439 lesson,
#: inherited from #4923). A full-row backup records where a row CAME FROM and
#: cannot record that this script is what moved it; without the manifest a
#: restore can only ask "does the live row differ from its backup?", which is
#: also true of a row the producer has legitimately re-graded since.
MANIFEST_TABLE = "bak_5221_repair_manifest"

#: The sanity floor. 248 clearable outcomes were measured at 14:1xZ against a
#: static population — the producer fix stops any more being written, and
#: nothing else writes this shape. A plan far below this is a broken filter or a
#: completed run, and those two causes need a DISCRIMINATOR rather than an
#: override flag; `explain_small_plan` asks the manifest which one happened.
SANITY_FLOOR = 200

#: THE SERIES FAMILY, AND NOTHING ELSE (#5023, learned the expensive way on this
#: table). A Kalshi ticker is `<series>-<date><club><club>`, and a day-of-month
#: runs straight into a club code, so `2H` appears inside dates:
#: `KXMLSSPREAD-26APR22HOUSD` is day 22 + HOUston, a whole-game spread. Matching
#: the period grammar against the whole `external_id` cleared 70 correct
#: verdicts on 2026-09-11. Match the part before the first dash, as
#: `_ticker_period` always has.
#:
#: `(^|[^H])` is the head-to-head carve-out: `KXEPLH2H` is a whole-game market
#: that contains the characters "2H". Postgres has no lookbehind, so it is
#: written as "a character that is not H, or the start of the string".
_SERIES = "split_part(fm.external_id, '-', 1)"

#: The FIRST-HALF period labels `_get_halftime_score` looks for in
#: `scoring_plays` before it falls through to the box score. An event that has
#: one of these rows never reached the buggy branch at all, so it is not in
#: scope — this is the structural half of "did this row take the broken path".
_FIRST_HALF_PLAY_PERIODS = (
    "'q1','q2','1q','2q','1st','2nd','1st half','first half','1h'"
)

#: The candidate scan. Deliberately WIDER than the rows this will clear: the
#: arithmetic filter in `classify` narrows it, and a candidate the filter spares
#: is reported rather than absent, so a run prints what it decided and not just
#: what it did.
_PLAN_SQL = f"""
SELECT fo.id                AS outcome_id,
       fo.name              AS outcome_name,
       fo.is_winner         AS stored_is_winner,
       fm.id                AS market_id,
       fm.external_id       AS ticker,
       e.home_team_name     AS home_team_name,
       e.away_team_name     AS away_team_name,
       e.home_score         AS final_home,
       e.away_score         AS final_away,
       e.box_score_data -> 'home_period_scores' AS home_periods,
       e.box_score_data -> 'away_period_scores' AS away_periods,
       COALESCE(s.key, '')  AS sport_key
  FROM futures_outcomes fo
  JOIN futures_markets fm ON fm.id = fo.market_id
  JOIN events e           ON e.id = fm.event_id
  LEFT JOIN sports s      ON s.id = e.sport_id
 WHERE fo.resolution_source = 'game_score'
   AND {_SERIES} ~* '(^|[^H])2H'
   AND NOT EXISTS (SELECT 1 FROM scoring_plays sp
                    WHERE sp.event_id = e.id
                      AND LOWER(sp.period) IN ({_FIRST_HALF_PLAY_PERIODS}))
 ORDER BY fo.market_id, fo.id
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
    # run. A missing table still yields an empty reconciliation, and
    # `backup_is_exact({})` is False, so `--apply` still refuses (gotcha #53).
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    "man_exists": f"SELECT to_regclass('{MANIFEST_TABLE}') IS NOT NULL",
    "man_count": f"SELECT count(*) FROM {MANIFEST_TABLE}",
    # THE FORWARD WRITE, and it is a compare-and-swap on the value this repair
    # exists to remove. If anything re-graded the row between the plan and the
    # write — the fixed producer, or Kalshi's own settlement, both of which are
    # what we WANT to arrive — the statement no-ops instead of overwriting a
    # fresher, better verdict with a NULL.
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


def linescore(value):
    """Coerce a linescore to a list of ints, or None if it cannot be summed.

    JSONB arrives as a real list through the ORM and as a Python-repr STRING
    through the admin `db-query` rail (gotcha #40), and a malformed linescore
    (nulls, strings, an empty array) must refuse rather than raise inside a
    grading loop.
    """
    if isinstance(value, str):
        import ast

        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return None
    if not isinstance(value, list) or not value:
        return None
    if any(not isinstance(x, int) or isinstance(x, bool) for x in value):
        return None
    return value


def market_verdicts(ticker, legs, home_pts, away_pts):
    """{outcome_id: bool} the PRODUCER would write for this period score.

    Every branch delegates to a grader that already exists in
    `backfill_winners`; this function chooses which one, and computes nothing.
    Returns None when the producer's own graders refuse — a market we cannot
    ask about is left alone, never guessed at.
    """
    from app.tasks.backfill_winners import (
        _decide_three_way_winner,
        _spread_outcome_is_winner,
        _total_outcome_is_winner,
    )

    series = (ticker or "").split("-", 1)[0].upper()
    if series.endswith("WINNER"):
        # The 2-leg shape is graded inline in the resolver, so there is no pure
        # function to ask and nothing this script may honestly do with it.
        if len(legs) != 3:
            return None
        decided = _decide_three_way_winner(
            [leg["outcome_name"] for leg in legs],
            legs[0]["home_team_name"], legs[0]["away_team_name"],
            home_pts, away_pts,
        )
        if decided is None:
            return None
        return {legs[i]["outcome_id"]: decided[i] for i in range(3)}

    out = {}
    for leg in legs:
        if series.endswith("SPREAD"):
            won = _spread_outcome_is_winner(
                leg["outcome_name"], leg["home_team_name"],
                leg["away_team_name"], home_pts, away_pts,
            )
        elif series.endswith("TOTAL"):
            won = _total_outcome_is_winner(
                leg["outcome_name"], home_pts, away_pts)
        else:
            return None
        # ALL-OR-NOTHING across the market, for the same reason the producer
        # writes that way (CERT-499): a leg we cannot read leaves the market's
        # arithmetic unproven, and clearing its siblings on a partial reading is
        # how a repair invents a population.
        if won is None:
            return None
        out[leg["outcome_id"]] = won
    return out


def classify(legs):
    """Split one market's legs into clear / spare / refuse.

    THE ADMISSION TEST is the second condition and it carries the safety: a row
    is only clearable when the BUGGY formula reproduces what is stored AND the
    correct one does not. That is true of exactly the rows this bug wrote, is
    decidable from the row alone, and stops being true the moment the row is
    re-graded — so this script cannot eat a correctly-graded 2H row after the
    producer fix deploys, and needs no date bound to promise it.
    """
    from app.tasks.backfill_winners import _first_half_period_count

    first = legs[0]
    n = _first_half_period_count(first["sport_key"])
    home = linescore(first["home_periods"])
    away = linescore(first["away_periods"])
    if (n is None or home is None or away is None
            or len(home) < n or len(away) < n
            or first["final_home"] is None or first["final_away"] is None):
        return [], [], list(legs)

    correct = market_verdicts(first["ticker"], legs,
                              first["final_home"] - sum(home[:n]),
                              first["final_away"] - sum(away[:n]))
    buggy = market_verdicts(first["ticker"], legs,
                            first["final_home"] - home[0],
                            first["final_away"] - away[0])
    if correct is None or buggy is None:
        return [], [], list(legs)

    clear, spare, refuse = [], [], []
    for leg in legs:
        oid = leg["outcome_id"]
        stored = leg["stored_is_winner"]
        if buggy.get(oid) != stored:
            # This row does not carry what final-minus-Q1 produces, so whatever
            # is wrong with it is not the defect this repair was measured on.
            refuse.append(leg)
        elif correct.get(oid) == stored:
            spare.append(leg)
        else:
            clear.append(leg)
    return clear, spare, refuse


def backup_is_exact(recon) -> bool:
    """The D51 gate: every clearable row has a backup row, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo (gotcha #53).
    """
    return bool(recon) and all(n == 0 for n in recon.values())


def explain_small_plan(plan_count: int, manifest_rows: int) -> str:
    """Why is the plan below the floor — a broken filter, or a done job?

    A sanity floor that names two causes needs a DISCRIMINATOR, not an override
    flag: `--allow-small` would let the broken-filter case through wearing the
    completed-run case's clothes. The manifest is the discriminator, because
    only a successful forward write puts a row in it.
    """
    if plan_count >= SANITY_FLOOR:
        return ""
    if manifest_rows + plan_count >= SANITY_FLOOR:
        return (
            f"ALREADY APPLIED — {manifest_rows} rows are in {MANIFEST_TABLE} and "
            f"{plan_count} remain clearable; together they clear the floor of "
            f"{SANITY_FLOOR}. This is a drained backlog, not a broken filter."
        )
    return (
        f"FILTER BROKE — only {plan_count} rows are clearable and "
        f"{manifest_rows} were ever applied, so {plan_count + manifest_rows} of "
        f"an expected {SANITY_FLOOR}+ are accounted for. Either the cohort SQL "
        f"stopped matching or a grader changed its mind. Do NOT lower the "
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


def plan(rows):
    """Group the candidate scan by market and classify each one."""
    by_market = collections.OrderedDict()
    for row in rows:
        leg = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        by_market.setdefault(leg["market_id"], []).append(leg)

    clear, spare, refuse = [], [], []
    for legs in by_market.values():
        c, s, r = classify(legs)
        clear.extend(c)
        spare.extend(s)
        refuse.extend(r)
    return clear, spare, refuse


async def run(args) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        candidates = (await s.execute(text(_PLAN_SQL))).all()
        clear, spare, refuse = plan(candidates)
        applied_before = await manifest_count(s)

        print(f"=== #5221 second-half re-grade: {len(candidates)} candidates ===")
        print(f"  the linescore REFUTES the stored verdict, will clear : {len(clear)}")
        print(f"  computed wrong, lands right, LEFT ALONE              : {len(spare)}")
        print(f"  no pure grader / unreadable linescore, REFUSED       : {len(refuse)}")
        print(f"  already applied in {MANIFEST_TABLE}: {applied_before}")

        per_series = collections.Counter(
            (leg["ticker"] or "").split("-", 1)[0] for leg in clear)
        if per_series:
            print("\nclearable by series:")
            for series, n in per_series.most_common():
                print(f"  {series:<24} {n:>5}")

        print("\nfirst 10 to clear:")
        for leg in clear[:10]:
            print(f"  {leg['outcome_id']:>10} served={str(leg['stored_is_winner']):>5} "
                  f"{(leg['ticker'] or '')[:34]:<34} | {(leg['outcome_name'] or '')[:34]}")
        if refuse:
            print(f"\nREFUSED ({len(refuse)}) — reported, not guessed at:")
            for leg in refuse[:10]:
                print(f"  {leg['outcome_id']:>10} {(leg['ticker'] or '')[:34]:<34} "
                      f"| {(leg['outcome_name'] or '')[:34]}")

        if not clear:
            if applied_before:
                print(f"\nNothing clearable and {applied_before} rows applied — "
                      f"idempotent no-op, the cohort is drained.")
            else:
                print("\nNothing clearable and nothing ever applied — that is not a "
                      "drained backlog, it is a filter that matches nothing. STOP.")
            return

        small = explain_small_plan(len(clear), applied_before)
        if small:
            print(f"\n⚠️  plan is below the sanity floor of {SANITY_FLOOR}.")
            print(f"    {small}")
            if small.startswith("FILTER BROKE"):
                print("\n❌ REFUSING — see above.")
                return

        outcome_ids = [int(leg["outcome_id"]) for leg in clear]

        if args.backup:
            print(f"\n=== backup: copying {len(outcome_ids)} futures_outcomes rows "
                  f"into {BAK_TABLE} ===")
            await backup(s, outcome_ids)

        if await _table_exists(s, "bak_exists"):
            recon = await reconcile_backup(s, outcome_ids)
            print("\n=== backup reconciliation (clearable rows with no backup row) ===")
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
                  "restore_5221_second_half_graded_from_the_first_quarter.py --apply")
            return

        if not clean:
            print(f"\n❌ REFUSING TO APPLY — the backup is not exact. Run --backup "
                  f"first; {BAK_TABLE} must hold every clearable row.")
            return

        doable = clear[: args.limit] if args.limit else clear
        print(f"\n=== applying {len(doable)} of {len(clear)} ===")

        # Same transaction as the writes it describes, so a rolled-back clear
        # cannot leave a manifest row telling the restore to put a verdict back
        # on a row this script never touched.
        await s.execute(text(SQL["man_create"]))

        now = datetime.now(timezone.utc)
        cleared, declined = 0, 0
        for leg in doable:
            res = await s.execute(text(SQL["clear"]),
                                  {"oid": int(leg["outcome_id"])})
            if (res.rowcount or 0) == 0:
                # The CAS declined: the row was re-graded between the plan and
                # the write, which is the outcome this repair is trying to make
                # possible. Report it, never force it, and write NO manifest row.
                declined += 1
                continue
            await s.execute(text(SQL["man_record"]), {
                "oid": int(leg["outcome_id"]),
                "mid": int(leg["market_id"]),
                "now": now,
            })
            cleared += 1

        await s.commit()
        print(f"\nCOMMITTED: cleared {cleared} outcomes, {declined} declined by the "
              f"compare-and-swap (re-graded since the plan — that is the good case).")
        print(f"Undo: restore_5221_second_half_graded_from_the_first_quarter.py "
              f"--apply (restores only these {cleared}, and only while they are "
              f"still ungraded).")

        after_clear, _, _ = plan((await s.execute(text(_PLAN_SQL))).all())
        print(f"POST-REPAIR: {len(after_clear)} outcomes still carry a 2H verdict "
              f"the linescore refutes (target: 0 after a full run).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help=f"copy clearable futures_outcomes rows into {BAK_TABLE}")
    p.add_argument("--apply", action="store_true",
                   help="clear the refuted verdicts (refuses unless the backup "
                        "reconciles)")
    p.add_argument("--limit", type=int, default=0,
                   help="apply only the first N clears (0 = all)")
    asyncio.run(run(p.parse_args()))
