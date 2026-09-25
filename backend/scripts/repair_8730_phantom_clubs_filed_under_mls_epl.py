"""#8730 — clubs that were never MLS or EPL stop being filed under MLS and EPL.

WHAT THE READER SAW

`bainluck.com/search?q=united` (2026-09-25, 390px) listed **Akwa United — MLS**
and **Cambrian United — MLS** between Minnesota United and Atlanta United. Akwa
United is Nigerian and Cambrian United is Welsh. `q=fulham` was worse: its one
team card was a crestless "Fulham" with no record, the MLS row, and the real
Fulham (EPL, ESPN id 370, a record) was not on the page at all.

THE CAUSE (measured on production, not inferred)

StatPal soccer ingest in February–March 2026 wrote world-soccer fixtures under
`soccer_usa_mls` and `soccer_epl` — 1,912 and 1,920 events that carry
`commence_time_source='statpal'` and NO provider id of any kind (`external_id`,
`espn_id`, `statpal_fixture_id` all NULL), every one now `closed`. Specimens:
event 6608439 "Akwa United v First Bank" and 6608825 "Cambrian United v Trethomas
Bluebirds", both in one transaction (`created_at` 2026-02-28 04:15:00.097441).
The clubs those fixtures named were minted as `teams` rows in the same wrong
league. The producer stopped long ago: zero such MLS rows since April.

The team rows are what a reader sees — search's teams card, typeahead, and
`/api/teams/<slug>` (which served Akwa United with `sport_name: "MLS"`). And the
wrong league is worse than a wrong label, because `soccer_usa_mls`/`soccer_epl`
are MARQUEE keys in search's tie-break (`_team_marquee_rank`), so these rows
sorted ahead of real clubs of the same name and won the same-name collapse.

THE POPULATION — every clause is read off the row, none off a name

A team is moved only when ALL of these hold (`phantom_refusal` is the rule, and
the SQL below only fetches a superset for it to judge):

  1. its league is `soccer_usa_mls` or `soccer_epl`;
  2. it carries no provider identity: `espn_id`, `statpal_team_id`, `external_id`
     all NULL (a real MLS/EPL club is ESPN-anchored by the ESPN sync);
  3. nothing maintains it: `current_record` and `standings_data` both NULL;
  4. it plays at least one event, and EVERY event it plays is an anonymous
     StatPal row as defined above — so a club that has ever appeared in an
     id-anchored fixture is never touched, whatever its name.

Measured 2026-09-25 23:30Z: 641 MLS + 160 EPL = 801 teams, 0 carrying a record,
standings, a favourite, or a slug that collides under the target league. Names
confirm the class rather than define it: Akwa United, Sporting Lagos, Feyenoord,
Osasuna, Brighton, Fulham, Tottenham under MLS; Corinthians, Toluca, Philadelphia
Union, New York City under EPL.

WHERE THEY GO, AND WHY THERE

`soccer_other` — the catch-all a fixture lands in when ingest cannot place its
league (`_sport_key_names_no_league`). That is the only league claim we can back:
we hold no evidence of which league Akwa United plays in, and a guess would be
this defect again. It also resolves the collisions without folding anything:
`soccer_other` is not a marquee key, so wherever a real club shares the name
(Fulham, Osasuna, Philadelphia Union) the real row now sorts first and survives
the same-name collapse. Folding those duplicates into their real clubs is a
different, heavier repair (FKs across events, futures legs, identity mappings);
it is not this one.

WHAT THIS DELIBERATELY DOES NOT TOUCH

- The anonymous events themselves. They are `closed`, unscored and unserved, and
  they span six more league keys than the two the reader saw; moving them is a
  separate decision. Their team FKs are unchanged, so nothing is unbound.
- `slug`. Some carry a league suffix (`fulham-mls`); a slug is a URL, and
  renaming 801 of them breaks links for no reader-visible gain.
- `entities` and `team_identity_mapping` rows that mirror these teams. They are
  matching-registry inputs, not reader surfaces; moving them changes what the
  matcher can attach, which is lane-reviewed work of its own.

RUNBOOK (D51: backup first, one-command undo)

    heroku run:detached -a bainluck -- python3 scripts/repair_8730_phantom_clubs_filed_under_mls_epl.py
    heroku run:detached -a bainluck -- python3 scripts/repair_8730_phantom_clubs_filed_under_mls_epl.py --backup --apply
    undo: heroku run:detached -a bainluck -- python3 scripts/restore_8730_phantom_clubs_filed_under_mls_epl.py --apply

`heroku run` without `:detached` fails silently in the sandbox (gotcha #48) —
verify by re-reading the rows about sixty seconds later, never by trusting an
empty stdout.

PLAN-BOUND: `--backup` banks the population as it stands; `--apply` writes ONLY
banked teams, re-judges each one against `phantom_refusal` at write time, and
writes compare-and-set on the banked `sport_id`. A team that gained an ESPN id,
a record, or an anchored fixture between the bank and the write is skipped and
counted, never moved.

Writes refuse anywhere but ``bainluck``. Team rows are read by web routes on the
main app; no task in ``HEAVY_TASKS`` is involved (notice 48 owes no heavy line).

`CREATE TABLE IF NOT EXISTS backup_8730_team_league` is runtime DDL behind
`--backup`, invoked by a person, on a named app — notice 47(c): the invocation is
the attended step, so this is NOT migration-class. Its column types are derived
from `teams` by `CREATE TABLE AS SELECT ... WHERE false`, never hand-typed
(#6215's backup was unrunnable for a week over one hand-typed column).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: The app whose web dyno serves the team rows. See the header on notice 48.
PRODUCER_APP = "bainluck"

BACKUP_TABLE = "backup_8730_team_league"

#: The two leagues the defect filed clubs under, and the one they move to, as
#: spelled in `sports.key`. Ids are LOOKED UP at run time: a name that does not
#: resolve is a loud refusal, an id is right until the day it is not.
SOURCE_LEAGUES = ("soccer_usa_mls", "soccer_epl")
TARGET_LEAGUE = "soccer_other"

#: Refusal reasons. Strings, so the plan output says which clause declined a row.
NOT_A_SOURCE_LEAGUE = "not_a_source_league"
HAS_PROVIDER_ID = "has_provider_id"
MAINTAINED = "maintained"
NO_EVENTS = "no_events"
PLAYS_AN_ANCHORED_EVENT = "plays_an_anchored_event"


def phantom_refusal(team: dict, source_sport_ids: set) -> str | None:
    """Why *team* must NOT be moved, or None when every clause holds. Pure.

    *team* carries the row's own columns plus two counts over the events it
    plays: ``n_events`` and ``n_anonymous`` (events with no provider id of any
    kind, timed by StatPal). The clauses are checked in the header's order and
    the FIRST failing one is named, so a declined row always says why.
    """
    if team.get("sport_id") not in source_sport_ids:
        return NOT_A_SOURCE_LEAGUE
    if any(team.get(k) is not None for k in ("espn_id", "statpal_team_id", "external_id")):
        return HAS_PROVIDER_ID
    if team.get("current_record") is not None or team.get("has_standings"):
        return MAINTAINED
    n_events = int(team.get("n_events") or 0)
    if n_events == 0:
        return NO_EVENTS
    if int(team.get("n_anonymous") or 0) != n_events:
        return PLAYS_AN_ANCHORED_EVENT
    return None


def wrong_app_refusal(args) -> str | None:
    """Refuse a write from anywhere but the producer app.

    THE UNDO IMPORTS THIS, so a restore — a production write in the opposite
    direction — earns the identical gate. ``getattr`` because the undo's parser
    defines no ``--backup``. UNSET refuses too: unset means a laptop pointed at
    the production database with whatever happens to be checked out.
    """
    if not (getattr(args, "apply", False) or getattr(args, "backup", False)):
        return None
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. "
        f"Re-run with `heroku run:detached -a {PRODUCER_APP}`."
    )


#: The SUPERSET `phantom_refusal` judges: every provider-id-less team in the two
#: leagues (or, on the apply path, exactly the banked ids), with its event counts.
#: The events are read through two index-backed joins (`home_team_id`,
#: `away_team_id`) and UNION ALL — an `OR` over the two FKs timed out at 10 s on
#: production. A self-matchup counts twice on both sides, so the counts agree.
_CANDIDATE_SQL = """
WITH base AS (
    SELECT t.id, t.name, t.sport_id, t.espn_id, t.statpal_team_id,
           t.external_id, t.current_record,
           (t.standings_data IS NOT NULL) AS has_standings
      FROM teams t
     WHERE {where}
), ev AS (
    SELECT b.id AS team_id,
           (e.external_id IS NULL AND e.espn_id IS NULL
            AND e.statpal_fixture_id IS NULL
            AND e.commence_time_source = 'statpal') AS anonymous
      FROM base b JOIN events e ON e.home_team_id = b.id
    UNION ALL
    SELECT b.id,
           (e.external_id IS NULL AND e.espn_id IS NULL
            AND e.statpal_fixture_id IS NULL
            AND e.commence_time_source = 'statpal')
      FROM base b JOIN events e ON e.away_team_id = b.id
)
SELECT b.*,
       count(ev.team_id) AS n_events,
       count(ev.team_id) FILTER (WHERE ev.anonymous) AS n_anonymous
  FROM base b LEFT JOIN ev ON ev.team_id = b.id
 GROUP BY b.id, b.name, b.sport_id, b.espn_id, b.statpal_team_id,
          b.external_id, b.current_record, b.has_standings
 ORDER BY b.id
"""

_SURVEY_WHERE = (
    "t.sport_id = ANY(:source_ids) AND t.espn_id IS NULL "
    "AND t.statpal_team_id IS NULL AND t.external_id IS NULL"
)
_BANKED_WHERE = f"t.id IN (SELECT team_id FROM {BACKUP_TABLE})"


async def league_ids(s) -> dict:
    from sqlalchemy import text

    keys = (*SOURCE_LEAGUES, TARGET_LEAGUE)
    rows = (
        await s.execute(
            text("SELECT key, id FROM sports WHERE key = ANY(:keys)"),
            {"keys": list(keys)},
        )
    ).all()
    return {k: i for k, i in rows}


async def ensure_bank(s) -> None:
    """Create the backup table and its key. Idempotent.

    Both league columns mirror `teams.sport_id` and take its type from it, and
    `name` mirrors `teams.name`, so nothing here is hand-typed.
    """
    from sqlalchemy import text

    await s.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS "
            "SELECT id AS team_id, name, "
            " sport_id AS sport_id_before, sport_id AS sport_id_after, "
            " now() AS taken_at "
            "FROM teams WHERE false"
        )
    )
    await s.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {BACKUP_TABLE}_pk "
            f"ON {BACKUP_TABLE} (team_id)"
        )
    )


async def run(args) -> int:  # noqa: C901 - a runbook, read top to bottom
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        ids = await league_ids(s)
        missing = [k for k in (*SOURCE_LEAGUES, TARGET_LEAGUE) if k not in ids]
        if missing:
            print(f"REFUSING: league key(s) {missing} do not resolve in `sports`.")
            return 2
        source_ids = {ids[k] for k in SOURCE_LEAGUES}
        target_id = ids[TARGET_LEAGUE]
        name_of = {v: k for k, v in ids.items()}

        rows = (
            await s.execute(
                text(_CANDIDATE_SQL.format(where=_SURVEY_WHERE)),
                {"source_ids": sorted(source_ids)},
            )
        ).mappings().all()
        plan, declined = [], {}
        for r in rows:
            why = phantom_refusal(dict(r), source_ids)
            if why is None:
                plan.append(dict(r))
            else:
                declined[why] = declined.get(why, 0) + 1

        by_league: dict = {}
        for r in plan:
            by_league.setdefault(name_of[r["sport_id"]], []).append(r)
        print(f"surveyed {len(rows)} provider-id-less teams in {list(SOURCE_LEAGUES)}")
        for league, members in sorted(by_league.items()):
            sample = ", ".join(m["name"] for m in members[:12])
            print(f"  move {league} -> {TARGET_LEAGUE}: {len(members)}  e.g. {sample}")
        print(f"  declined by clause: {declined or 'none'}")

        if args.backup:
            await ensure_bank(s)
            for r in plan:
                await s.execute(
                    text(
                        f"INSERT INTO {BACKUP_TABLE} "
                        "(team_id, name, sport_id_before, sport_id_after, taken_at) "
                        "VALUES (:id, :name, :before, :after, now()) "
                        "ON CONFLICT (team_id) DO NOTHING"
                    ),
                    {"id": r["id"], "name": r["name"],
                     "before": r["sport_id"], "after": target_id},
                )
            await s.commit()
            banked = (
                await s.execute(text(f"SELECT count(*) FROM {BACKUP_TABLE}"))
            ).scalar_one()
            print(f"{BACKUP_TABLE}: {banked} rows banked")

        if not args.apply:
            print("plan only. Re-run with --backup --apply.")
            return 0

        exists = (
            await s.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": BACKUP_TABLE})
        ).scalar_one()
        if not exists:
            print("REFUSING: no bank. --apply writes only banked teams; run --backup first.")
            return 2
        bank = (
            await s.execute(
                text(f"SELECT team_id, sport_id_before, sport_id_after FROM {BACKUP_TABLE}")
            )
        ).all()
        if not bank:
            print("REFUSING: the bank is empty, so there is no approved population to write.")
            return 2

        # Re-judge every banked team on its LIVE row, not on the survey above:
        # the bank is the approval, and the rule still has to hold at write time.
        live = {
            r["id"]: dict(r)
            for r in (
                await s.execute(text(_CANDIDATE_SQL.format(where=_BANKED_WHERE)))
            ).mappings().all()
        }
        moved = already = skipped = 0
        for team_id, before, after in bank:
            row = live.get(team_id)
            if row is None:
                skipped += 1
                continue
            if row["sport_id"] == after:
                already += 1
                continue
            if row["sport_id"] != before or phantom_refusal(row, {before}) is not None:
                skipped += 1
                continue
            result = await s.execute(
                text(
                    "UPDATE teams SET sport_id = :after "
                    "WHERE id = :id AND sport_id = :before"
                ),
                {"id": team_id, "before": before, "after": after},
            )
            moved += result.rowcount
        await s.commit()

        # Read back rather than trusting rowcount (gotcha #53).
        carrying = (
            await s.execute(
                text(
                    f"SELECT count(*) FROM {BACKUP_TABLE} b JOIN teams t "
                    "ON t.id = b.team_id AND t.sport_id = b.sport_id_after"
                )
            )
        ).scalar_one()
        print(
            f"moved {moved}; already moved {already}; skipped {skipped} "
            f"(changed since the bank); banked teams now in {TARGET_LEAGUE}: "
            f"{carrying}/{len(bank)}"
        )
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="bank the population")
    p.add_argument("--apply", action="store_true", help="write the repair")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
