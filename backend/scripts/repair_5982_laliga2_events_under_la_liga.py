"""#5982 — move the Kalshi-born LaLiga 2 rows off La Liga's page.

------------------------------------------------------------------------------
WHAT A READER SEES
------------------------------------------------------------------------------
`https://bainluck.com/sports/soccer_spain_la_liga`, 2026-09-13. The *Live &
Paused* rail carries six fixtures presented as if they were in progress, each
reading "No result reported": Córdoba v Almería, Granada v Albacete, Girona v
Castellón, Cádiz v Las Palmas, Andorra v Real Sociedad B, Gijón v Eldense.

Not one of them is a La Liga fixture. All six are Segunda División, and we
already hold every one of them under `soccer_spain_segunda_division`, minted
from the schedule, with a score.

------------------------------------------------------------------------------
THE CAUSE IS FIXED IN CODE; THIS IS THE ROWS THAT CAUSE ALREADY WROTE
------------------------------------------------------------------------------
`get_sport_key_from_ticker` answered `soccer_spain_la_liga` for every
`KXLALIGA2*` ticker, because the futures map's eight-character `kxlaliga` entry
matched first. `_find_matching_event` scopes candidates by that key, so the real
Segunda fixture was never a candidate and the market minted a TWIN of it on the
top-flight page. The commit this script ships with registers the five LaLiga 2
series and makes the resolver prefer the longest prefix, so no new row can be
born this way.

That fixes the future and nothing else. 21 rows are already written.

**The producer is `match_prediction_markets`, which is in `HEAVY_TASKS`.** Until
`bainluck-heavy` carries the map fix (standing notice 48) the producer can still
mint these, so running this repair before that release will see the population
refill. Step 0 of the runbook is therefore a heavy-release check, not a
courtesy.

------------------------------------------------------------------------------
WHY REPOINTING `sport_id` IS THE WHOLE REPAIR — MEASURED, NOT ASSUMED
------------------------------------------------------------------------------
The obvious worry about moving 21 rows into Segunda is that Segunda's page then
carries 21 duplicates instead of La Liga carrying six. It does not, and the
reason is that #5964's `fold_twin_events` is already deployed and already asks
exactly the right question — it simply never got to ask it, because its
candidate bucket is `(sport_id, UTC date)` and these rows sat under a different
`sport_id` from their twins.

The two halves of the clock line up once they share a bucket. Kalshi stores an
expected expiration three hours after the whistle (#5905), and
`recover_kalshi_occurrence_starts` already corrects that at serve time, on this
very path, before the fold keys anything:

    ghost (served)                              real Segunda (served)        drift
    15307878 Andorra v R Sociedad B  09-12 12:00  15305059 Andorra CF …  12:00   0m
    15307871 Cadiz v Las Palmas      09-12 14:15  15305140 Cádiz CF …    14:15   0m
    15307865 Girona v Castellon      09-12 16:30  15305185 Girona FC …   16:30   0m
    15307866 Granada v Albacete      09-12 16:30  15305290 Granada CF …  16:29   1m
    15307859 Cordoba v Almeria       09-12 19:00  15305486 Córdoba …     19:01   1m
    15308739 Gijon v Eldense         09-13 12:00  15305858 Sporting …    12:01   1m
    15308732 Valladolid v Oviedo     09-13 14:15  15305920 R Valladolid  14:17   2m
    15308726 Mallorca v Sabadell     09-13 16:30  15306010 Mallorca …    16:30   0m
    15308585 Tenerife v Leganes      09-13 19:00  15306137 Tenerife …    19:00   0m
    15308951 Celta Fortuna v Eibar   09-14 18:30  15306978 Celta …       18:30   0m

Every one inside `SOCCER_KICKOFF_DRIFT` (5 min). Driving the SHIPPED
`fold_twin_events` over the real production rows, with the ghosts' `sport_id`
repointed and nothing else changed (`artifacts-lane1-294/drive_fold_5982.py`):

    BEFORE   in=54  served=53  folded=1    ghosts dropped: 1
    AFTER    in=54  served=42  folded=12   ghosts dropped: 12
    NON-ghost rows dropped, both runs: 0

So the repair does not move six bad cards from one page to another. It removes
them from La Liga's page and folds eleven of them INTO the real fixture on
Segunda's, unioning their Kalshi prices onto the row that already has the score.
Nothing is deleted; acceptance 3 of #5982 ("they should reach their own
competition, not a bin") is the mechanism, not a hope.

The five that do not fold (15297767, 15297992, 15298352, 15299083, 15303019) are
the older rows stamped `00:00:00` — a midnight placeholder rather than a Kalshi
expiration, so the recovery has nothing to subtract and they have no twin to
meet. They are outside every rail's window and invisible to a reader. They are
still repointed, because they are still Segunda fixtures and La Liga is still
the wrong page for them; they are simply not the part a reader notices.

------------------------------------------------------------------------------
SCOPE — AND THE MUCH LARGER THING THIS DELIBERATELY IS NOT
------------------------------------------------------------------------------
The tempting general predicate is "every event whose linked Kalshi tickers
resolve to a competition that is not the event's own". Measured on production
2026-09-13 20:4xZ, that selects **16,098 events across 83 (current → resolved)
pairs**, overwhelmingly `*_other` catch-all keys assigned by
`auto_create_sport_key_from_category` when the LLM guessed a sport and the
ticker names another (6,246 rows of `baseball_other` that `KXITFMATCH` calls
ITF tennis, and so on). That is a real and separate question about the
catch-all fallback, with its own owners and its own blast radius. It is not
#5982 and nothing here touches it.

This script repairs one pair: `soccer_spain_la_liga` → `soccer_spain_segunda_
division`, for rows whose Kalshi evidence is LaLiga 2 and nothing else.

Three fences, all necessary:

  * `external_id IS NULL AND espn_id IS NULL`. A row a schedule provider
    reported is a row that provider assigned to a competition, and Kalshi's
    ticker is not evidence against it. All 21 satisfy this, so the fence costs
    nothing today and is the honest bound.
  * **No mixed evidence.** An event holding ANY Kalshi market outside the LaLiga
    2 series is refused, not repointed. A row that both a La Liga market and a
    Segunda market claim is an identity question, not a relabelling, and
    guessing it is how a correct fix becomes a new defect. Zero rows are mixed
    today; the refusal is there for the row that is not.
  * The series list is DERIVED from `KALSHI_FUTURES_TICKER_TO_SPORT_KEY`, never
    re-spelled here. A script that hardcodes the map it is repairing against is
    one edit away from disagreeing with it.

------------------------------------------------------------------------------
RUNBOOK
------------------------------------------------------------------------------
    0.  heroku releases -a bainluck-heavy      # must carry the map fix first
    1.  heroku run:detached -a bainluck-heavy -- \
            python3 scripts/repair_5982_laliga2_events_under_la_liga.py --dry-run
    2.  heroku run:detached -a bainluck-heavy -- \
            python3 scripts/repair_5982_laliga2_events_under_la_liga.py --backup
    3.  heroku run:detached -a bainluck-heavy -- \
            python3 scripts/repair_5982_laliga2_events_under_la_liga.py --apply

Undo, one command:

        heroku run:detached -a bainluck-heavy -- \
            python3 scripts/restore_5982_laliga2_events_under_la_liga.py --apply

Steps 2 and 3 are not advice: `--backup` and `--apply` refuse unless
`HEROKU_APP_NAME` is `bainluck-heavy`. `--apply` additionally refuses until the
backup holds a row for every event it is about to move.

`CREATE TABLE IF NOT EXISTS backup_5982_event_sports` is runtime DDL that
executes only when a person invokes `--backup` on that named app — standing
notice 47(c), NOT migration-class. The invocation is the attended step.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: The app whose code can put the defect back. `match_prediction_markets` mints
#: these rows and is in `HEAVY_TASKS`, so since the heavy split that is
#: `bainluck-heavy` — released separately from the web app and routinely behind
#: it (standing notice 48). Repairing from the web app would race a producer
#: still running the unfixed map.
PRODUCER_APP = "bainluck-heavy"

#: The competition the rows are wrongly on, and the one they belong to. Spelled
#: as sport KEYS rather than ids: an id is a fact about one database.
WRONG_SPORT_KEY = "soccer_spain_la_liga"
RIGHT_SPORT_KEY = "soccer_spain_segunda_division"

BACKUP_TABLE = "backup_5982_event_sports"


def segunda_series() -> list[str]:
    """The Kalshi series prefixes that name LaLiga 2, read off the shipped map.

    Derived, never re-spelled. This script exists because a ticker resolved to
    the wrong competition; hardcoding a second opinion about which tickers those
    are would reproduce the original failure in a new place.
    """
    from app.utils.sport_keys import KALSHI_FUTURES_TICKER_TO_SPORT_KEY

    return sorted(
        prefix
        for prefix, key in KALSHI_FUTURES_TICKER_TO_SPORT_KEY.items()
        if key == RIGHT_SPORT_KEY
    )


#: Events currently on the wrong competition whose Kalshi evidence is LaLiga 2
#: and ONLY LaLiga 2. The `HAVING` is two-sided on purpose — see the mixed
#: evidence fence in the module docstring.
_POPULATION_SQL = """
    SELECT e.id,
           e.status,
           e.commence_time,
           e.home_team_name,
           e.away_team_name,
           e.sport_id AS current_sport_id,
           count(fm.id) AS kalshi_markets
      FROM events e
      JOIN sports s ON s.id = e.sport_id
      JOIN futures_markets fm ON fm.event_id = e.id AND fm.source = 'kalshi'
     WHERE s.key = :wrong_key
       AND e.external_id IS NULL
       AND e.espn_id IS NULL
  GROUP BY e.id, e.status, e.commence_time, e.home_team_name,
           e.away_team_name, e.sport_id
    HAVING count(*) FILTER (
             WHERE lower(split_part(fm.external_id, '-', 1)) = ANY(:series)
           ) > 0
       AND count(*) FILTER (
             WHERE lower(split_part(fm.external_id, '-', 1)) <> ALL(:series)
           ) = 0
  ORDER BY e.commence_time
"""

#: Rows that hold BOTH kinds of Kalshi market. Reported, never moved — the
#: refusal the docstring describes, made visible rather than silent.
_MIXED_SQL = """
    SELECT e.id,
           e.home_team_name,
           e.away_team_name,
           string_agg(DISTINCT split_part(fm.external_id, '-', 1), ',') AS series
      FROM events e
      JOIN sports s ON s.id = e.sport_id
      JOIN futures_markets fm ON fm.event_id = e.id AND fm.source = 'kalshi'
     WHERE s.key = :wrong_key
  GROUP BY e.id, e.home_team_name, e.away_team_name
    HAVING count(*) FILTER (
             WHERE lower(split_part(fm.external_id, '-', 1)) = ANY(:series)
           ) > 0
       AND count(*) FILTER (
             WHERE lower(split_part(fm.external_id, '-', 1)) <> ALL(:series)
           ) > 0
"""


def wrong_app_refusal(args) -> str | None:
    """Refuse a write from anywhere but the producer app.

    THE UNDO IMPORTS THIS. A restore is a production write in the opposite
    direction and earns the identical gate — and it is the write most likely to
    be typed in a hurry by someone who has just decided the repair went wrong.

    `getattr`, because the undo's parser has no `--backup`: one refusal serving
    two programs must not raise on reading a flag only one of them defines.

    UNSET refuses too, rather than falling through. Unset means a laptop pointed
    at the production database with whatever happens to be checked out, which is
    precisely the case this gate exists to stop.
    """
    if not (getattr(args, "apply", False) or getattr(args, "backup", False)):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. "
        "`match_prediction_markets` — the task that mints these rows off the "
        "shadowed ticker prefix — is in HEAVY_TASKS, so the code that can put "
        f"the defect back is what is deployed to '{PRODUCER_APP}', an app "
        "released separately from the web app and routinely behind it "
        f"(standing notice 48). Re-run with `heroku run:detached -a {PRODUCER_APP}`."
    )


async def run(args) -> int:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    series = segunda_series()
    if not series:
        print(
            "REFUSING: no series in KALSHI_FUTURES_TICKER_TO_SPORT_KEY resolve to "
            f"{RIGHT_SPORT_KEY!r}. Either the map fix is not deployed here or it "
            "was reverted; without it this script has no population and moving "
            "rows would be guesswork."
        )
        return 2

    params = {"wrong_key": WRONG_SPORT_KEY, "series": series}

    async with get_task_session() as s:
        right_sport_id = (
            await s.execute(
                text("SELECT id FROM sports WHERE key = :k"),
                {"k": RIGHT_SPORT_KEY},
            )
        ).scalar()
        if right_sport_id is None:
            print(
                f"REFUSING: no `sports` row for {RIGHT_SPORT_KEY!r}. The repair "
                "must not create a competition; a missing row means this "
                "database is not the one the population was measured on."
            )
            return 2

        rows = (await s.execute(text(_POPULATION_SQL), params)).all()
        mixed = (await s.execute(text(_MIXED_SQL), params)).all()

        print(f"=== #5982 LaLiga 2 rows on {WRONG_SPORT_KEY} ===")
        print(f"series read off the shipped map: {', '.join(series)}")
        print(f"target sport_id for {RIGHT_SPORT_KEY}: {right_sport_id}")
        print()

        if mixed:
            print(
                f"REFUSED (mixed evidence) — {len(mixed)} row(s) hold both LaLiga 2 "
                "and non-LaLiga 2 Kalshi markets. Not moved; an identity question, "
                "not a relabelling:"
            )
            for m in mixed:
                print(f"  {m.id}  {m.home_team_name} v {m.away_team_name}  [{m.series}]")
            print()

        if not rows:
            print("Nothing to repair — population is 0 (idempotent no-op).")
            return 0

        print(f"{len(rows)} event(s) in scope:")
        for r in rows:
            print(
                f"  {r.id}  {r.commence_time:%Y-%m-%d %H:%MZ}  {r.status:<10} "
                f"{r.home_team_name} v {r.away_team_name}  "
                f"({r.kalshi_markets} kalshi market(s))"
            )
        print()

        ids = [r.id for r in rows]

        if args.backup:
            await s.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
                    "  event_id BIGINT PRIMARY KEY,"
                    "  sport_id INTEGER NOT NULL,"
                    "  captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
                    "  restored_at TIMESTAMPTZ"
                    ")"
                )
            )
            # DO UPDATE, not DO NOTHING: a second `--backup` after the population
            # drifted must refresh the recorded sport_id rather than keep a stale
            # one. `restored_at` is reset because a re-backed-up row is live again.
            await s.execute(
                text(
                    f"INSERT INTO {BACKUP_TABLE} (event_id, sport_id) "
                    "SELECT id, sport_id FROM events WHERE id = ANY(:ids) "
                    "ON CONFLICT (event_id) DO UPDATE "
                    "  SET sport_id = EXCLUDED.sport_id, "
                    "      captured_at = now(), restored_at = NULL"
                ),
                {"ids": ids},
            )
            await s.commit()
            print(f"BACKUP: {len(ids)} row(s) recorded in {BACKUP_TABLE}.")
            return 0

        backup_exists = (
            await s.execute(
                text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL")
            )
        ).scalar()

        if not args.apply:
            print(
                f"DRY RUN — nothing written. Backup table "
                f"{'exists' if backup_exists else 'DOES NOT EXIST YET'}. "
                "Re-run with --backup, then --apply."
            )
            return 0

        if not backup_exists:
            print(
                f"REFUSING --apply: {BACKUP_TABLE} does not exist. Run --backup "
                "first; an undo nobody can run is not an undo."
            )
            return 2

        unbacked = (
            await s.execute(
                text(
                    "SELECT count(*) FROM unnest(CAST(:ids AS BIGINT[])) AS t(id) "
                    f"WHERE NOT EXISTS (SELECT 1 FROM {BACKUP_TABLE} b "
                    "                   WHERE b.event_id = t.id "
                    "                     AND b.restored_at IS NULL)"
                ),
                {"ids": ids},
            )
        ).scalar()
        if unbacked:
            print(
                f"REFUSING --apply: {unbacked} of {len(ids)} in-scope row(s) have "
                f"no live backup. The population moved since --backup ran. "
                "Re-run --backup."
            )
            return 2

        result = await s.execute(
            text(
                "UPDATE events SET sport_id = :right_id "
                " WHERE id = ANY(:ids) AND sport_id <> :right_id"
            ),
            {"right_id": right_sport_id, "ids": ids},
        )
        await s.commit()
        print(
            f"APPLIED: {result.rowcount} event(s) moved "
            f"{WRONG_SPORT_KEY} -> {RIGHT_SPORT_KEY}."
        )
        print(
            "Undo: python3 scripts/restore_5982_laliga2_events_under_la_liga.py --apply"
        )
        return 0


def main():
    p = argparse.ArgumentParser(
        description="#5982 move Kalshi-born LaLiga 2 events off La Liga"
    )
    p.add_argument("--backup", action="store_true", help="record current sport_id")
    p.add_argument("--apply", action="store_true", help="write the repair")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the population and write nothing (the default)",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)) or 0)


if __name__ == "__main__":
    main()
