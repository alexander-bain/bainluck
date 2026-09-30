"""Place the Phoenix's Polymarket-born NBL rows in ``basketball_nbl``. #8100.

THE SHIP
--------

Friday's Perth Wildcats v S.E. Melbourne Phoenix (2026-10-02 11:30Z) shows once
on search and the NBL page, carrying Polymarket's price. Today it is two cards:
``15319245`` (Polymarket-born, ``basketball_other``, Polymarket's price) and
``15320512`` (Odds API, ``basketball_nbl``, sportsbooks only).

WHY A ONE-OFF WRITE AS WELL AS THE CODE
---------------------------------------

The code half (``app/utils/venue_club_spellings.py``) teaches placement that
Polymarket's "South East Melbourne Phoenix" is teams 2919, so the NEXT Phoenix
row is minted in ``basketball_nbl`` like the other nine clubs' rows, and teaches
the fold's squash the same spelling, so the anchored-claim kickoff pass joins
the pair (six minutes apart) the way it joins Tasmania v Melbourne today.
Placement runs only at create. The rows already minted into the catch-all stay
there, and the kickoff pass is same-league, so without this write they stay two
cards.

This moves ``sport_id`` only, from ``basketball_other`` to ``basketball_nbl``.
That is the value placement would have written at create had it known the
spelling. Nothing is absorbed, deleted or renamed (ruling 048 untouched): both
rows stay, and the serve-time fold decides the card.

WHICH ROWS
----------

Selected by predicate, and the dry run prints the list. Every clause must hold:

  * ``basketball_other``, ``status = 'scheduled'``, kickoff in the future;
  * an id-less Polymarket venue mint: ``commence_time_source =
    'polymarket_venue'`` and no ``external_id`` / ``espn_id`` /
    ``statpal_fixture_id``;
  * one side is, exactly, a venue spelling in ``VENUE_CLUB_SPELLINGS`` whose
    stored club is an NBL team, and the other side is, exactly, an NBL team's
    stored name.

Read on 2026-09-30 14:3xZ: ``15319245`` (Perth v Phoenix, 10-02) and
``15319859`` (Phoenix v Illawarra, 10-04).

THE BACKUP AND THE UNDO
-----------------------

``--apply`` banks each row's ``sport_id`` in ``backup_8100_phoenix_placement``
first and refuses to write unless every planned row is banked with the value it
still holds. ``--restore`` writes the banked ``sport_id`` back, only for rows
still on ``basketball_nbl``. ``CREATE TABLE IF NOT EXISTS`` is runtime DDL
behind a person's invocation on a named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_8100_phoenix_rows_in_the_catchall.py            # dry run
    heroku run:detached -a bainluck -- python3 scripts/repair_8100_phoenix_rows_in_the_catchall.py --apply    # backup + write
    heroku run:detached -a bainluck -- python3 scripts/repair_8100_phoenix_rows_in_the_catchall.py --restore  # undo

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.utils.venue_club_spellings import VENUE_CLUB_SPELLINGS  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})
BACKUP_TABLE = "backup_8100_phoenix_placement"
CATCHALL = "basketball_other"
LEAGUE = "basketball_nbl"
VENUE_COMMENCE_SOURCE = "polymarket_venue"


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def eligible(home: str | None, away: str | None, league_teams: set[str]) -> bool:
    """One side a venue spelling of an NBL club, the other an NBL club. Exact."""
    venue_names = {
        venue for venue, ours in VENUE_CLUB_SPELLINGS.items() if ours in league_teams
    }
    return (home in venue_names and away in league_teams) or (
        away in venue_names and home in league_teams
    )


async def _sport_ids(session) -> dict[str, int]:
    rows = await session.execute(
        text("SELECT key, id FROM sports WHERE key IN (:catchall, :league)"),
        {"catchall": CATCHALL, "league": LEAGUE},
    )
    ids = {r.key: int(r.id) for r in rows}
    if set(ids) != {CATCHALL, LEAGUE}:
        raise Refused(f"sports rows missing: have {sorted(ids)}")
    return ids


async def _league_teams(session, league_id: int) -> set[str]:
    rows = await session.execute(
        text("SELECT name FROM teams WHERE sport_id = :sid"), {"sid": league_id}
    )
    return {r.name for r in rows if r.name}


async def _candidates(session, ids: dict[str, int]) -> list[dict]:
    rows = await session.execute(
        text(
            "SELECT id, home_team_name, away_team_name, commence_time "
            "FROM events WHERE sport_id = :catchall AND status = 'scheduled' "
            "AND commence_time > now() "
            "AND commence_time_source = :venue_source "
            "AND external_id IS NULL AND espn_id IS NULL AND statpal_fixture_id IS NULL "
            "ORDER BY id"
        ),
        {"catchall": ids[CATCHALL], "venue_source": VENUE_COMMENCE_SOURCE},
    )
    league_teams = await _league_teams(session, ids[LEAGUE])
    return [
        {
            "event_id": int(r.id),
            "home": r.home_team_name,
            "away": r.away_team_name,
            "commence_time": r.commence_time.isoformat(),
        }
        for r in rows
        if eligible(r.home_team_name, r.away_team_name, league_teams)
    ]


async def _backup(session, event_ids: list[int], catchall_id: int) -> int:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " event_id integer PRIMARY KEY,"
            " sport_id_before integer NOT NULL,"
            " taken_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.execute(
        text(
            f"INSERT INTO {BACKUP_TABLE} (event_id, sport_id_before) "
            "SELECT id, sport_id FROM events WHERE id = ANY(:ids) "
            "ON CONFLICT (event_id) DO NOTHING"
        ),
        {"ids": event_ids},
    )
    await session.commit()
    banked = await session.execute(
        text(
            f"SELECT count(*) FROM {BACKUP_TABLE} "
            "WHERE event_id = ANY(:ids) AND sport_id_before = :catchall"
        ),
        {"ids": event_ids, "catchall": catchall_id},
    )
    return int(banked.scalar_one())


async def _banked(session) -> list[tuple[int, int]]:
    exists = await session.execute(text("SELECT to_regclass(:t)"), {"t": BACKUP_TABLE})
    if exists.scalar_one() is None:
        return []
    rows = await session.execute(
        text(f"SELECT event_id, sport_id_before FROM {BACKUP_TABLE} ORDER BY event_id")
    )
    return [(int(r.event_id), int(r.sport_id_before)) for r in rows]


async def _where_now(session, event_ids: list[int]) -> dict[str, str]:
    if not event_ids:
        return {}
    rows = await session.execute(
        text(
            "SELECT e.id, s.key FROM events e JOIN sports s ON s.id = e.sport_id "
            "WHERE e.id = ANY(:ids)"
        ),
        {"ids": event_ids},
    )
    return {str(r.id): r.key for r in rows}


async def run(session, *, apply: bool, restore: bool) -> dict:
    ids = await _sport_ids(session)
    written = 0
    if restore:
        banked = await _banked(session)
        planned = [{"event_id": e, "to_sport_id": s} for e, s in banked]
        for event_id, sport_id_before in banked:
            result = await session.execute(
                text(
                    "UPDATE events SET sport_id = :before "
                    "WHERE id = :id AND sport_id = :league"
                ),
                {"before": sport_id_before, "id": event_id, "league": ids[LEAGUE]},
            )
            written += result.rowcount
        await session.commit()
        touched = [e for e, _ in banked]
    else:
        planned = await _candidates(session, ids)
        touched = [c["event_id"] for c in planned]
        if apply and planned:
            banked = await _backup(session, touched, ids[CATCHALL])
            if banked < len(touched):
                raise Refused(
                    f"backup holds {banked} of {len(touched)} rows at "
                    f"{CATCHALL}; refusing to write"
                )
            for event_id in touched:
                result = await session.execute(
                    text(
                        "UPDATE events SET sport_id = :league "
                        "WHERE id = :id AND sport_id = :catchall AND status = 'scheduled'"
                    ),
                    {"league": ids[LEAGUE], "id": event_id, "catchall": ids[CATCHALL]},
                )
                if result.rowcount != 1:
                    await session.rollback()
                    raise Refused(
                        f"row {event_id} changed under the run; rolled back, nothing written"
                    )
                written += 1
            await session.commit()
    # Read back from disk rather than trusting rowcount (gotcha #53).
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "planned": planned,
        "written": written,
        "now": await _where_now(session, touched),
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    try:
        refuse_unless_production(dict(os.environ))
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        try:
            out = await run(session, apply=args.apply, restore=args.restore)
        except Refused as exc:
            await session.rollback()
            print(f"REFUSED: {exc}")
            return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if out["mode"] == "apply":
        print(
            "UNDO: heroku run:detached -a bainluck -- "
            "python3 scripts/repair_8100_phoenix_rows_in_the_catchall.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
