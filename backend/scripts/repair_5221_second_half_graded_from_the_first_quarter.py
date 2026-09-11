"""#5221 + #5236 — un-say the 1H and 2H verdicts we computed off the FIRST QUARTER.

WHAT A READER SEES TODAY. `KXNBA2HWINNER-26FEB19BOSGSW` says **Boston won the
second half**. Boston scored 47 after the interval; Golden State scored 59.
`KXNBA2HWINNER-26MAR18PORIND` credits Portland with a second half Indiana won
57–48. On the totals it is worse: **126 of 153** `KXNBA2HTOTAL` legs are served
the wrong verdict, because a 2H total computed over three quarters clears almost
every line. And on the FIRST halves, which are four times the population, an NBA
1H total is graded on Q1's points against a line written for two quarters, so
roughly half the ladder flips.

WHERE THEY CAME FROM, and it is ONE helper with TWO callers.
`_get_halftime_score`'s box-score fallback returned `home_period_scores[0]`
behind a `len(...) >= 2` guard whose comment assumed the linescore held HALVES.
On a quarter-scored sport `[0]` is Q1. `_period_scores` hands that number
straight back for `1h` and subtracts it from the final for `2h`, so the same
mistake reads as "the first quarter" on one path and "three quarters" on the
other. #5052 wired the 2H caller in on 2026-09-11 and it graded that population
in one 55-minute window (13:01Z–13:56Z); the 1H caller has been there far
longer, which is why it is the bigger half. The producer is fixed in the commit
this script ships with, and **THIS SCRIPT MUST NOT RUN BEFORE THAT DEPLOYS** —
the beat runs every six hours and would re-write exactly what this clears.

THE COHORT, re-measured on production 2026-09-11 ~14:4xZ by running THIS
script's own filter over every candidate row, series by series:

    series             candidates   clear   spare  refuse
    KXNBA1HSPREAD           2,209     356   1,849       4
    KXNBA1HTOTAL            1,867     821   1,046       0
    KXNCAAMB1HSPREAD          889       0     879      10
    KXNCAAMB1HTOTAL           801       0     801       0
    KXNBA1HWINNER             609     132     477       0
    KXNBA2HWINNER             608      80     520       8
    KXNCAAMB1HWINNER          318       0     318       0
    KXNBA2HSPREAD             158      27     131       0
    KXNBA2HTOTAL              153     126      27       0
    KXNFL1HSPREAD             105       0       5     100
    KXNCAAF2HSPREAD            94      15      79       0
    KXNCAAF1HSPREAD            72       1      31      40
    -------------------------------------------------------
    total                   7,883   1,558   6,163     162
      of which 2H (#5221)   1,013     248     757       8
      of which 1H (#5236)   6,870   1,310   5,406     154

The 2H numbers are IDENTICAL to the ones the 2H-only version of this filter
measured (248 clearable, 8 refused) — widening the scan to `[12]H` moved no 2H
row, which is the regression evidence for folding the two cohorts into one
script. `KXNBA1HWINNER`'s 132 reproduces #5236's independently-recomputed 132
exactly. Candidate counts have GROWN since #5236 was filed (its table read 6,100
1H candidates against 6,870 here) because the beat keeps grading while the
producer fix waits to deploy; the clearable set is what this repair is sized on.

THE CONTROL, which is why "51.6% of NBA 1H totals are wrong" is a measurement
and not a number. `basketball_ncaab` plays HALVES, so `[0]` genuinely is the
first half there and `_first_half_period_count` returns 1. Its 2,008 rows —
graded by the same filter, in the same run, off the same code — yield **zero**
clears. The sport split is doing the work.

Every clearable row sits on a quarter-scored sport, every one fell through to
the box score because the event holds no first-half `scoring_plays` row, and the
buggy formula reproduces its stored value exactly.

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
the half" in this codebase and this script is not a second one. #4923's repair
could not compute the right answer; this one deliberately does not.

**It does not clear a row it agrees with.** 6,163 of the 7,883 were computed
from the wrong number and happen to land on the right verdict — a spread leg
whose line the wrong score clears anyway, a winner the leading team won either
way. Clearing those would un-say 6,163 correct results for up to six hours to
fix 1,558 — a net regression for a reader. They are reported and left alone.

**And it refuses 162 rows rather than quietly skipping them**, because a
refusal count is where a second defect goes to hide. The 100 `KXNFL1HSPREAD`
rows refused for a missing linescore carry a `game_score` grade that this bug
cannot have written and that no reading of the score explains (#5243); the 40
`KXNCAAF1HSPREAD` rows are #5237, whose events hold linescores like
`[10, 0, 0, 0]`. Both were found by reading the refusal buckets, not the clears.

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
producer fix deploys, correctly-graded period rows carry `game_score` too and
are structurally identical to these — so a purely structural cohort would start
eating correct verdicts, and a date bound would be a guess about release timing.
"The constant-1 reading explains what is stored, and the sport's own half does
not" is decidable from the row alone, is true of exactly the rows this bug
wrote, and stops being true the moment the row is re-graded. It needs no clock.

IT IS ALSO WHY THE TWO-HALF SPORTS NEED NO EXCLUSION LIST. The bug was
`_first_half_period_count` having been the constant 1, so on `basketball_ncaab`
and `soccer_*` — where the true count IS 1 — the buggy and correct readings are
the same numbers and no row can satisfy "buggy explains it, correct does not".
NCAAB's 1,998 correctly-graded 1H rows are spared by the arithmetic itself,
which is a property a reviewer can check rather than a list someone must
maintain. The measured control run agrees: 0 clears in 2,008 NCAAB rows.

THE RESIDUE, STATED RATHER THAN QUIETLY DROPPED — all 162 of it, grouped by the
reason the filter gave, because a refusal reported only as a count is where the
next defect hides. Every one of the five buckets below was found by reading that
grouping, and all five are now issues:

    100  KXNFL1HSPREAD, linescore missing        -> #5243 (six events hold NO
         or unreadable                              box score at all; no reading
                                                    of the score explains any of
                                                    the 105 verdicts)
     40  KXNCAAF1HSPREAD, the bug does not       -> #5237, and NOT a linescore
         explain the stored verdict                 problem: both events'
                                                    linescores sum exactly to
                                                    their finals. SHSUTROY's
                                                    first half was 14-14 and
                                                    legs claim Troy won it by
                                                    over 3.5, 20.5 and 23.5.
     10  KXNCAAMB1HSPREAD, no pure grader        -> #5248. A leg will not parse
         for this market shape                      for `_spread_outcome_is_
                                                    winner`, so the market is
                                                    left whole -- but BOTH
                                                    teams are stored winning
                                                    the same 1H, which UVA led
                                                    41-25 while Virginia Tech
                                                    is also winning it by over
                                                    3.5, 6.5 and 9.5. 3 wrong.
      8  KXNBA2HWINNER, no pure grader           -> #5234 (the 2-leg winner
         for this market shape                      shape)
      4  KXNBA1HSPREAD, the bug does not         -> #5248: on the one market,
         explain the stored verdict                 KXNBA1HSPREAD-26MAR24NOPNYK
                                                    both teams are stored
                                                    winning the same 1H, which
                                                    New York took 66-60. 6 of
                                                    its 11 legs are wrong.

#5234 is the shape worth naming here because it is a gap in the CODE rather than
in the data: four `KXNBA2HWINNER` markets carry TWO legs ("Minnesota wins 2nd
half" / "Utah wins 2nd half"), and the producer grades that shape inline in
`_resolve_kalshi_spread_total_from_scores` rather than through a pure function —
a third copy of the side-picker #2352 consolidated twice already. There is
nothing to import, so all 8 outcomes are REFUSED. Two of them are wrong
(`KXNBA2HWINNER-26MAR18PORIND`). Repairing them needs that branch extracted
first; filed rather than guessed.

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

#: The sanity floor. 1,558 clearable outcomes were measured at ~16:0xZ across
#: both cohorts (248 on 2H, 1,310 on 1H). The population can only GROW until the
#: producer fix deploys and is frozen after it — a graded `game_score` row is
#: never re-graded (`OVERWRITABLE_WINNER_SOURCES_SQL`), which is the same
#: property that makes clearing the repair mechanism — so a plan far below this
#: is a broken filter or a completed run. Those two causes need a DISCRIMINATOR
#: rather than an override flag; `explain_small_plan` asks the manifest which
#: one happened. Set at ~80% of the measurement, as the 2H-only floor of 200
#: against 248 was.
SANITY_FLOOR = 1250

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
#:
#: #5236 widened `2H` to `[12]H`, and this scan is now deliberately LOOSER than
#: the rows `classify` will look at: which period a ticker binds to is decided
#: in Python by the producer's own `_ticker_period`, not by this regex. Two
#: readings of "is this a period market" is exactly the drift `_ticker_period`
#: was extracted to end (#4923); a SQL regex that had to agree with a Python
#: one across two files would be a third.
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
   AND {_SERIES} ~* '(^|[^H])[12]H'
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
    # Spelled `len(value) == 0` rather than the idiomatic `or not value`: that
    # exact two-line form is the replacement literal of
    # `season_market_discovery_mutations:M9`, so writing it here makes the
    # mutation-residue sweep report this file as a mutant someone left behind
    # (`tests/test_mutation_guard.py`, Pass B). Same semantics, no collision —
    # please do not "simplify" it back.
    if not isinstance(value, list) or len(value) == 0:
        return None
    if any(not isinstance(x, int) or isinstance(x, bool) for x in value):
        return None
    return value


def correct_period_score(period, n, periods, final):
    """The score `period` is worth, read the way the fixed producer reads it.

    `n` is `_first_half_period_count`'s answer for the sport. A first half is
    the first `n` entries; a second half is everything else, overtime included
    — the same reading `_period_scores` gives, because a repair that computed a
    different "2H" than the loop re-grading these rows would be measuring a
    population production does not have.
    """
    if len(periods) < n:
        return None
    first = sum(periods[:n])
    if period == "1h":
        return first
    if period == "2h":
        if final is None:
            return None
        return final - first
    return None


def buggy_period_score(period, periods, final):
    """What the PRE-#5221 `_get_halftime_score` produced, reproduced exactly.

    The old branch was `if len(h_periods) >= 2 ...: return h_periods[0], ...`,
    so the bug is not "an off-by-one in the arithmetic" — it is
    `_first_half_period_count` having been the constant 1. Which is why this
    takes no `n`, and why on a two-half sport it agrees with
    `correct_period_score` exactly: there was nothing to get wrong.

    The `>= 2` is part of the reproduction rather than decoration. A one-entry
    linescore made the old code refuse, so admitting one here would let the
    admission test claim the bug wrote a row it never touched.
    """
    if len(periods) < 2:
        return None
    if period == "1h":
        return periods[0]
    if period == "2h":
        if final is None:
            return None
        return final - periods[0]
    return None


def _refuse(legs, reason):
    """Stamp a whole market REFUSED with why, so a run reports its own residue.

    A refusal that is only a count is a place defects go to be buried: the four
    `KXNCAAF1HSPREAD` markets this filter spares are #5237, and they were only
    ever visible because the reason was printed beside them.
    """
    out = []
    for leg in legs:
        leg["refuse_reason"] = reason
        out.append(leg)
    return out


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
    re-graded — so this script cannot eat a correctly-graded period row after
    the producer fix deploys, and needs no date bound to promise it.

    #5236: it is also what keeps the two-half sports out. On `basketball_ncaab`
    and `soccer_*`, `_first_half_period_count` is 1 and the bug's constant was
    1, so `correct` and `buggy` are the SAME verdicts and no row can satisfy
    "buggy explains it and correct does not". The 1,981 correct NCAAB rows in
    the 1H cohort are spared by arithmetic, not by an exclusion list somebody
    has to remember to maintain.
    """
    from app.tasks.backfill_winners import (
        _first_half_period_count,
        _ticker_period,
    )

    first = legs[0]
    # WHICH PERIOD, asked of the producer's own classifier. `_PLAN_SQL`'s regex
    # is a candidate net; this is the authority, so a widening there cannot
    # quietly change what gets graded here.
    period = _ticker_period(first["ticker"])
    if period not in ("1h", "2h"):
        return [], [], _refuse(
            legs, f"_ticker_period says {period!r}, not a half this repair reads")

    n = _first_half_period_count(first["sport_key"])
    if n is None:
        return [], [], _refuse(
            legs, f"sport {first['sport_key']!r} has no half we may invent")

    home = linescore(first["home_periods"])
    away = linescore(first["away_periods"])
    if home is None or away is None:
        return [], [], _refuse(legs, "linescore missing or cannot be summed")

    correct_pts = (correct_period_score(period, n, home, first["final_home"]),
                   correct_period_score(period, n, away, first["final_away"]))
    buggy_pts = (buggy_period_score(period, home, first["final_home"]),
                 buggy_period_score(period, away, first["final_away"]))
    if None in correct_pts or None in buggy_pts:
        return [], [], _refuse(
            legs, f"the {period.upper()} score cannot be reconstructed from this row")

    correct = market_verdicts(first["ticker"], legs, *correct_pts)
    buggy = market_verdicts(first["ticker"], legs, *buggy_pts)
    if correct is None or buggy is None:
        return [], [], _refuse(legs, "no pure grader for this market shape")

    clear, spare, refuse = [], [], []
    for leg in legs:
        oid = leg["outcome_id"]
        stored = leg["stored_is_winner"]
        if buggy.get(oid) != stored:
            # This row does not carry what the constant-1 reading produces, so
            # whatever is wrong with it is not the defect this repair was
            # measured on. It is reported under its own heading because that is
            # where #5237 came from.
            refuse.append(_refuse([leg], "the bug does not explain the stored "
                                         "verdict — a DIFFERENT defect")[0])
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

        print(f"=== #5221 + #5236 period re-grade: {len(candidates)} candidates ===")
        print(f"  the linescore REFUTES the stored verdict, will clear : {len(clear)}")
        print(f"  computed wrong, lands right, LEFT ALONE              : {len(spare)}")
        print(f"  the filter would be guessing, REFUSED                : {len(refuse)}")
        print(f"  already applied in {MANIFEST_TABLE}: {applied_before}")

        print("\nby series (candidates / clear / spare / refuse):")
        buckets = collections.OrderedDict()
        for name, legs in (("clear", clear), ("spare", spare), ("refuse", refuse)):
            for leg in legs:
                series = (leg["ticker"] or "").split("-", 1)[0]
                buckets.setdefault(series, collections.Counter())[name] += 1
        for series in sorted(buckets, key=lambda s: -sum(buckets[s].values())):
            b = buckets[series]
            print(f"  {series:<22} {sum(b.values()):>5} | {b['clear']:>5} "
                  f"{b['spare']:>5} {b['refuse']:>5}")

        print("\nfirst 10 to clear:")
        for leg in clear[:10]:
            print(f"  {leg['outcome_id']:>10} served={str(leg['stored_is_winner']):>5} "
                  f"{(leg['ticker'] or '')[:34]:<34} | {(leg['outcome_name'] or '')[:34]}")

        if refuse:
            # BY REASON, because a refusal count is where a second defect hides.
            # #5237 is four KXNCAAF1HSPREAD markets that only became visible as
            # a line under "the bug does not explain the stored verdict".
            by_reason = collections.Counter(
                leg.get("refuse_reason", "unstated") for leg in refuse)
            print(f"\nREFUSED ({len(refuse)}) — reported, not guessed at:")
            for reason, n in by_reason.most_common():
                print(f"  {n:>5}  {reason}")
                sample = [leg for leg in refuse
                          if leg.get("refuse_reason", "unstated") == reason][:3]
                for leg in sample:
                    print(f"         {leg['outcome_id']:>9} "
                          f"{(leg['ticker'] or '')[:34]:<34} "
                          f"| {(leg['outcome_name'] or '')[:30]}")

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
        print(f"POST-REPAIR: {len(after_clear)} outcomes still carry a 1H/2H "
              f"verdict the linescore refutes (target: 0 after a full run).")


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
