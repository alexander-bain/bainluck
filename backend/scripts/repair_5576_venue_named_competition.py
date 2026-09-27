"""#5576 — Nations League games stop reading "Other Soccer": the venue names their competition.

THE SHIP. ``/search?q=portugal`` at 390px on 2026-09-27 shows Norway v Portugal
(09-27) and Denmark v Portugal (10-01) under UEFA NATIONS LEAGUE with flags, and
Portugal v Norway (10-04) under OTHER SOCCER with "P" and "N" letter tiles and
its own "Other Soccer" chip. Wales v Denmark, Italy v Türkiye and Croatia v
England read the same. After this runs, every Nations League game from 09-28 to
10-06 that is still on the catch-all reads UEFA NATIONS LEAGUE, like its round.

WHY THE ROWS ARE THERE. A Polymarket game market has no ticker, so it is minted
on ``soccer_other`` and the clubs' placer relabels it. For these rows the clubs
could not: 45 were refused by #6392's season guard (minted ~13 days out, before
any schedule-born fixture sat within 3 days of the kickoff), 9 share two
competitions (Portugal and Norway are World Cup sides too), 6 carry a name
``teams`` does not ("Republic of Ireland"). The refusal is PERMANENT for a
linked row (CERT-3120): rescans read only unlinked markets.

PREVENTION SHIPS WITH THIS FILE. ``venue_placed_league`` in
``app/tasks/prediction_market_matching.py`` places a new row where its venue
lists the fixture — a Polymarket ``unl-`` slug, a Kalshi ``KXUEFANLGAME`` ticker
— when a side plays in that league. This script applies THAT rule, through the
same helpers, to the rows minted before it.

THE POPULATION, measured on production 2026-09-27 ~05:45Z. Every upcoming,
untagged ``soccer_other`` row (563) read against its linked markets:

    473  no venue league (an unmapped code, a friendly, no slug stamp yet)
     12  the venue names a league no side of ours plays in — left alone
     78  the venue names one league, a side plays in it, not Odds-API covered
      9  of those already have their OWN row in that league on the same day,
         sharing a side name — "Czech Republic" v England beside "Czechia" v
         England, "Turkey" v Italy beside "Türkiye" v Italy, "Bosnia &
         Herzegovina", "Las Palmas" beside "UD Las Palmas". Left alone: that is
         two rows for one game (#8818), the drain's job, and a relabel would put
         the second card on the league page itself.
     69  PLACED below — 46 Nations League, 23 across 12 other leagues (Brazil
         Série B 6, Chinese Super League 3, Brasileirão 3, …), the same defect.

Every pinned row is RE-QUALIFIED at apply time by the same rule — still on the
catch-all, still upcoming and scheduled, untagged, market-born, the venue still
names exactly the pinned league, a side still plays in it, still no
counterpart. Anything that no longer qualifies is skipped and named, so the
population can only shrink between measurement and run, never grow.

THE WRITE. ``events.sport_id`` only, one row at a time, each guarded on the
value it was read with. The pre-image is banked first (first pre-image wins),
and ``--restore`` moves back only rows still where this put them.

Runs only on ``bainluck-heavy`` (notice 47(c): runtime DDL, attended invocation):

    python3 scripts/repair_5576_venue_named_competition.py            # dry run
    python3 scripts/repair_5576_venue_named_competition.py --apply    # bank, place
    python3 scripts/repair_5576_venue_named_competition.py --restore  # undo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCER_APP = "bainluck-heavy"
CATCH_ALL = "soccer_other"
BACKUP = "backup_5576_venue_placement"
DUPLICATE_TAG = "duplicate-of:"

#: How far either side of the kickoff a same-league row sharing a side counts as
#: this game's own row. A club plays once a day; the measured counterparts all
#: sit at the same minute.
COUNTERPART_WINDOW = timedelta(hours=24)

#: (event id, the league its venue names), measured 2026-09-27 ~05:45Z.
PLACEMENTS: tuple[tuple[int, str], ...] = (
    # soccer_argentina_primera_division (1)
    (15318337, "soccer_argentina_primera_division"),
    # soccer_brazil_campeonato (3)
    (15318374, "soccer_brazil_campeonato"),
    (15318379, "soccer_brazil_campeonato"),
    (15318383, "soccer_brazil_campeonato"),
    # soccer_brazil_serie_b (6)
    (15312168, "soccer_brazil_serie_b"),
    (15313130, "soccer_brazil_serie_b"),
    (15318375, "soccer_brazil_serie_b"),
    (15318377, "soccer_brazil_serie_b"),
    (15318380, "soccer_brazil_serie_b"),
    (15318900, "soccer_brazil_serie_b"),
    # soccer_china_superleague (3)
    (15318930, "soccer_china_superleague"),
    (15318931, "soccer_china_superleague"),
    (15319545, "soccer_china_superleague"),
    # soccer_epl (1)
    (15319677, "soccer_epl"),
    # soccer_germany_bundesliga (1)
    (15319675, "soccer_germany_bundesliga"),
    # soccer_italy_serie_a (1)
    (15319590, "soccer_italy_serie_a"),
    # soccer_japan_j_league (1)
    (15319549, "soccer_japan_j_league"),
    # soccer_korea_kleague1 (2)
    (15319539, "soccer_korea_kleague1"),
    (15319540, "soccer_korea_kleague1"),
    # soccer_mexico_ligamx (1)
    (15319204, "soccer_mexico_ligamx"),
    # soccer_russia_premier_league (1)
    (15318873, "soccer_russia_premier_league"),
    # soccer_spain_segunda_division (2)
    (15312461, "soccer_spain_segunda_division"),
    (15312465, "soccer_spain_segunda_division"),
    # soccer_uefa_nations_league (46)
    (15313490, "soccer_uefa_nations_league"),
    (15313492, "soccer_uefa_nations_league"),
    (15313493, "soccer_uefa_nations_league"),
    (15313498, "soccer_uefa_nations_league"),
    (15314506, "soccer_uefa_nations_league"),
    (15314507, "soccer_uefa_nations_league"),
    (15314890, "soccer_uefa_nations_league"),
    (15314892, "soccer_uefa_nations_league"),
    (15314893, "soccer_uefa_nations_league"),
    (15314894, "soccer_uefa_nations_league"),
    (15314896, "soccer_uefa_nations_league"),
    (15314897, "soccer_uefa_nations_league"),
    (15316103, "soccer_uefa_nations_league"),
    (15316104, "soccer_uefa_nations_league"),
    (15316105, "soccer_uefa_nations_league"),
    (15316106, "soccer_uefa_nations_league"),
    (15316107, "soccer_uefa_nations_league"),
    (15316108, "soccer_uefa_nations_league"),
    (15316109, "soccer_uefa_nations_league"),
    (15316110, "soccer_uefa_nations_league"),
    (15316635, "soccer_uefa_nations_league"),
    (15316636, "soccer_uefa_nations_league"),
    (15316637, "soccer_uefa_nations_league"),
    (15316638, "soccer_uefa_nations_league"),
    (15316639, "soccer_uefa_nations_league"),
    (15316640, "soccer_uefa_nations_league"),
    (15316641, "soccer_uefa_nations_league"),
    (15316642, "soccer_uefa_nations_league"),
    (15317243, "soccer_uefa_nations_league"),
    (15317244, "soccer_uefa_nations_league"),
    (15317245, "soccer_uefa_nations_league"),
    (15317246, "soccer_uefa_nations_league"),
    (15317247, "soccer_uefa_nations_league"),
    (15317248, "soccer_uefa_nations_league"),
    (15317249, "soccer_uefa_nations_league"),
    (15317250, "soccer_uefa_nations_league"),
    (15317805, "soccer_uefa_nations_league"),
    (15317806, "soccer_uefa_nations_league"),
    (15317807, "soccer_uefa_nations_league"),
    (15317808, "soccer_uefa_nations_league"),
    (15317809, "soccer_uefa_nations_league"),
    (15317810, "soccer_uefa_nations_league"),
    (15317811, "soccer_uefa_nations_league"),
    (15317812, "soccer_uefa_nations_league"),
    (15317813, "soccer_uefa_nations_league"),
    (15317814, "soccer_uefa_nations_league"),
)


def wrong_app_refusal() -> str | None:
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to run on HEROKU_APP_NAME={app!r}: this repair writes "
        f"production rows and runs only on {PRODUCER_APP!r}"
    )


def squash(name: str | None) -> str:
    """A club name folded for EQUALITY only: accents, case and punctuation off.

    ``Córdoba CF`` and ``Cordoba CF`` are one string here; ``Córdoba`` is not.
    That is deliberate — this answers "is this the same side", and a looser
    rule would find counterparts for rows that have none.
    """
    plain = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", plain.lower())


def has_counterpart(home: str, away: str, rows) -> bool:
    """Any ``(home, away)`` in ``rows`` shares a side with this fixture."""
    mine = {squash(home), squash(away)} - {""}
    return any({squash(h), squash(a)} & mine for h, a in rows)


def _tags(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        value = json.loads(value)
    return list(value) if isinstance(value, list) else []


def refusal(
    league: str,
    event: dict | None,
    venue_leagues: set[str],
    sides: list[set[str]] | None,
    counterparts: list[tuple[str, str]],
    now: datetime,
) -> str | None:
    """Why this pinned row must NOT be placed now, or None to place it.

    The create path's rule (``venue_placed_league``) plus the population
    bounds the measurement was taken with. Pure, so it is driven directly.
    """
    from app.tasks.prediction_market_matching import (
        MARKET_BORN_COMMENCE_SOURCES,
        _sport_key_is_odds_api_covered,
    )

    if event is None:
        return "gone"
    if event["sport_key"] != CATCH_ALL:
        return f"now on {event['sport_key']!r}, not the catch-all"
    if event["status"] != "scheduled":
        return f"status {event['status']!r}"
    if event["commence_time"] <= now:
        return "kicked off"
    if any(DUPLICATE_TAG in str(t) for t in _tags(event["tags"])):
        return "tagged duplicate-of — the drain has it"
    if event["commence_time_source"] not in MARKET_BORN_COMMENCE_SOURCES:
        return f"not market-born ({event['commence_time_source']!r})"
    if venue_leagues != {league}:
        return f"the venue now names {sorted(venue_leagues)!r}"
    if _sport_key_is_odds_api_covered(league):
        return "an Odds-API-covered league"
    if sides is None or league not in (sides[0] | sides[1]):
        return f"no side plays in {league}"
    if counterparts:
        return f"{league} already has its own row for this game (#8818)"
    return None


async def _read_events(session) -> dict[int, dict]:
    res = await session.execute(
        text(
            "SELECT e.id, e.sport_id, s.key AS sport_key, e.home_team_name, "
            "e.away_team_name, e.commence_time, e.status, e.commence_time_source, "
            "CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS tags "
            "FROM events e JOIN sports s ON s.id = e.sport_id "
            "WHERE e.id = ANY(:ids)"
        ),
        {"ids": [event_id for event_id, _ in PLACEMENTS]},
    )
    return {r.id: dict(r._mapping) for r in res}


async def _venue_leagues(session) -> dict[int, set[str]]:
    from app.utils.venue_competition import venue_named_league

    res = await session.execute(
        text(
            "SELECT event_id, source, external_id, market_metadata "
            "FROM futures_markets WHERE event_id = ANY(:ids)"
        ),
        {"ids": [event_id for event_id, _ in PLACEMENTS]},
    )
    named: dict[int, set[str]] = {}
    for r in res:
        meta = r.market_metadata
        if isinstance(meta, str):
            meta = json.loads(meta)
        league = venue_named_league(r.source, r.external_id, meta)
        if league:
            named.setdefault(r.event_id, set()).add(league)
    return named


async def _sport_ids(session) -> dict[str, int]:
    res = await session.execute(
        text("SELECT id, key FROM sports WHERE key = ANY(:keys)"),
        {"keys": sorted({league for _, league in PLACEMENTS})},
    )
    return {r.key: r.id for r in res}


async def _counterparts(session, league: str, event: dict) -> list[tuple[str, str]]:
    res = await session.execute(
        text(
            "SELECT e.home_team_name, e.away_team_name FROM events e "
            "JOIN sports s ON s.id = e.sport_id WHERE s.key = :league "
            "AND e.commence_time BETWEEN :lo AND :hi"
        ),
        {
            "league": league,
            "lo": event["commence_time"] - COUNTERPART_WINDOW,
            "hi": event["commence_time"] + COUNTERPART_WINDOW,
        },
    )
    rows = [(r.home_team_name, r.away_team_name) for r in res]
    home, away = event["home_team_name"], event["away_team_name"]
    return [row for row in rows if has_counterpart(home, away, [row])]


async def plan(session, now: datetime) -> tuple[list[tuple[int, str]], list[str]]:
    """The pinned rows that still qualify, and a line per row that does not."""
    from app.tasks.prediction_market_matching import leagues_by_side_for_matchup

    events = await _read_events(session)
    venues = await _venue_leagues(session)
    place: list[tuple[int, str]] = []
    skipped: list[str] = []
    for event_id, league in PLACEMENTS:
        event = events.get(event_id)
        sides = counterparts = None
        if event is not None and event["sport_key"] == CATCH_ALL:
            sides = await leagues_by_side_for_matchup(
                session, event["home_team_name"], event["away_team_name"], CATCH_ALL
            )
            counterparts = await _counterparts(session, league, event)
        why = refusal(
            league, event, venues.get(event_id, set()), sides, counterparts or [], now
        )
        if why:
            skipped.append(f"  skip {event_id} ({league}): {why}")
        else:
            place.append((event_id, league))
    return place, skipped


async def _apply(session, place, events, sport_ids) -> list[str]:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP} (event_id bigint PRIMARY KEY, "
            "from_sport_id bigint NOT NULL, to_sport_id bigint NOT NULL, "
            "league text NOT NULL, banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    out = []
    for event_id, league in place:
        event = events[event_id]
        params = {
            "id": event_id,
            "frm": event["sport_id"],
            "to": sport_ids[league],
            "league": league,
        }
        # First pre-image wins: a re-run never overwrites what was banked.
        await session.execute(
            text(
                f"INSERT INTO {BACKUP} (event_id, from_sport_id, to_sport_id, league) "
                "VALUES (:id, :frm, :to, :league) ON CONFLICT (event_id) DO NOTHING"
            ),
            params,
        )
        res = await session.execute(
            text("UPDATE events SET sport_id = :to WHERE id = :id AND sport_id = :frm"),
            {"id": event_id, "frm": event["sport_id"], "to": sport_ids[league]},
        )
        if res.rowcount != 1:
            raise RuntimeError(f"event {event_id} touched {res.rowcount} rows")
        out.append(
            f"  placed {event_id} {event['home_team_name']} v "
            f"{event['away_team_name']} {event['commence_time']:%m-%d %H:%M}Z -> {league}"
        )
    return out


async def _landed(session, place, sport_ids) -> str | None:
    res = await session.execute(
        text("SELECT id, sport_id FROM events WHERE id = ANY(:ids)"),
        {"ids": [event_id for event_id, _ in place]},
    )
    now_on = {r.id: r.sport_id for r in res}
    for event_id, league in place:
        if now_on.get(event_id) != sport_ids[league]:
            return f"event {event_id} is on sport {now_on.get(event_id)}, expected {league}"
    return None


async def _backup_exists(session) -> bool:
    res = await session.execute(text("SELECT to_regclass(:t)"), {"t": BACKUP})
    return res.scalar_one() is not None


async def _restore(session) -> int:
    if not await _backup_exists(session):
        return 0
    # Only rows still where the repair put them: a row somebody has since moved
    # elsewhere is theirs.
    res = await session.execute(
        text(
            f"UPDATE events e SET sport_id = b.from_sport_id FROM {BACKUP} b "
            "WHERE e.id = b.event_id AND e.sport_id = b.to_sport_id"
        )
    )
    return res.rowcount


async def repair(session, mode: str, now: datetime | None = None) -> tuple[int, list[str]]:
    """``mode`` is ``dry``, ``apply`` or ``restore``. Returns (exit code, lines).

    Commits only on a clean apply or restore; every refusal writes nothing.
    """
    out: list[str] = []
    if mode == "restore":
        restored = await _restore(session)
        await session.commit()
        out.append(f"  restored {restored} event(s) to the catch-all")
        return 0, out

    now = now or datetime.now(timezone.utc)
    sport_ids = await _sport_ids(session)
    missing = sorted({league for _, league in PLACEMENTS} - set(sport_ids))
    if missing:
        out.append(f"REFUSED: no sports row for {missing!r}")
        return 2, out
    place, skipped = await plan(session, now)
    out.extend(skipped)
    for event_id, league in place:
        out.append(f"  place {event_id} -> {league}")
    if not place:
        out.append(f"\nnothing to place ({len(skipped)} skipped).")
        return 0, out
    if mode != "apply":
        out.append(
            f"\ndry run — nothing written. Would place {len(place)}, "
            f"skip {len(skipped)}."
        )
        return 0, out

    events = await _read_events(session)
    try:
        out.extend(await _apply(session, place, events, sport_ids))
    except Exception as exc:  # one transaction: any failure undoes all of it
        await session.rollback()
        out.append(f"ROLLED BACK: {exc}")
        return 1, out
    stray = await _landed(session, place, sport_ids)
    if stray:
        await session.rollback()
        out.append(f"ROLLED BACK: {stray}")
        return 1, out
    await session.commit()
    out.append(f"\n  applied: {len(place)} placed, {len(skipped)} skipped (banked in {BACKUP})")
    out.append("undo: python3 scripts/repair_5576_venue_named_competition.py --restore")
    return 0, out


async def run(mode: str) -> int:
    refused = wrong_app_refusal()
    if refused:
        print(f"REFUSED: {refused}")
        return 2
    from app.tasks.base import get_task_session

    print(f"#5576 venue-named competition — {mode.upper()}")
    async with get_task_session() as session:
        code, lines = await repair(session, mode)
    for line in lines:
        print(line)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="bank, place (default: dry run)")
    group.add_argument("--restore", action="store_true", help="undo from the banked rows")
    args = parser.parse_args()
    mode = "restore" if args.restore else ("apply" if args.apply else "dry")
    return asyncio.run(run(mode))


if __name__ == "__main__":
    raise SystemExit(main())
