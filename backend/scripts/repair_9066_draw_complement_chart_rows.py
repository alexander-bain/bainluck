"""#9066 — a soccer chart stops drawing the away side's price as the home line.

THE SHIP. ``/events/15316107`` (Croatia v England, Oct 3), phone and desktop,
measured on production 2026-09-27 ~08:00Z: the Win Probability chart draws the
Kalshi line as a square wave between ~23% and ~80% Croatia ("Odds flipped (24)")
while Croatia's own Kalshi price is 0.25. The same defect, without the square
wave, sits on 96 more fixtures: Montenegro v Latvia (Oct 2) draws Montenegro's
price as Latvia's line, Brunei v Johor Darul Ta'zim drew Brunei at 61% while
Brunei's own leg read 0.05.

------------------------------------------------------------------------------
WHY THESE ROWS ARE PROVABLY NOT THE HOME TEAM'S PROBABILITY
------------------------------------------------------------------------------

A Kalshi soccer game is ONE market with three legs — home, Tie, away
(``KXUEFANLGAME-26OCT03CROENG-CRO/-TIE/-ENG``). Every row pinned here was written
off the AWAY leg (``game_state.outcome_name``), and each stores either
``1 - P(away)`` — which on a 3-way field is P(home) + P(draw), not P(home) — or
``P(away)`` itself (9,414 of 9,414 rows are one of those two shapes, measured).
Neither is the home team's number.

The live writers stopped producing these on 2026-09-26 ~21:28Z, when #8814's
draw clause (``away_leg_complement_is_not_home``) went live; the chart backfill
kept producing them until #9066's code half gives it the same clause. Neither
fix can see a row already stored. Classification is the production predicate:
each group below passed ``away_leg_complement_is_not_home`` over its market's
real outcomes and the event's own team names, and this script re-asks it at
apply time.

ROUND 2. Heavy ran v104 (no code half) until 12:56Z, and its backfill kept
writing away-leg rows after round 1's census: 20 more on Hungary v Georgia
(so run.8781 refused that group, 117 > 97) and 1,432 on LA Galaxy v Colorado
(#9130's page, whose dashed Kalshi line still started Galaxy at 70.5%).
``ROUND_2`` pins those two groups. Re-running is safe: groups run.8781 already
cleared read "already repaired" and are skipped. Both rounds bank into the
same table, so the one-command undo restores both.

------------------------------------------------------------------------------
ONE TABLE, BECAUSE THE PAGE READS ONE
------------------------------------------------------------------------------

The chart's Kalshi line is ``win_prob_history.kalshi`` from
``GET /api/events/{id}/history``, read out of ``win_prob_snapshots``; the chart's
blended line (``aggregate_line``) is computed from that same series at serve
time. The hero reads ``events.win_probability_sources``, which #8814's live
writer already keeps honest. Deleting the rows corrects both chart lines. The
backfill refills a thinned Kalshi line from the HOME leg on its next pass.

------------------------------------------------------------------------------
HOW TO RUN IT (D51(b): backup first, one-command restore)
------------------------------------------------------------------------------

Dry run (default, writes nothing, prints the plan):

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/repair_9066_draw_complement_chart_rows.py

Apply:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/repair_9066_draw_complement_chart_rows.py --apply

The undo is one command:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/restore_9066_draw_complement_chart_rows.py --apply

Runtime DDL (``CREATE TABLE IF NOT EXISTS backup_*``), attended invocation only,
refuses to run anywhere but ``bainluck-heavy`` — notice 47(c), not migration
class. Nothing here runs on merge or on release.

Gotcha #48: ``heroku run`` without ``:detached`` fails silently in the sandbox —
use ``run:detached`` and verify the side effect afterwards with the verify query
this script prints.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.tasks.base import get_task_session  # noqa: E402
from app.utils.live_blend import away_leg_complement_is_not_home  # noqa: E402

#: Only this app may run it — notice 47(c).
PRODUCER_APP = "bainluck-heavy"

BACKUP_TABLE = "backup_9066_draw_complement_chart_rows"

#: Rows captured at or after this instant are never touched: the census that
#: banked the counts below read everything before it.
CUTOFF = "2026-09-27 08:00:00+00"

#: How close a stored home number must sit to ``yes`` or ``1 - yes`` to be the
#: away leg's reading (Numeric(5, 4) storage rounds to 0.0001).
SHAPE_TOLERANCE = 0.0005

#: ``(event_id, market_id, away_leg_name, banked_row_count)``, measured
#: 2026-09-27 ~08:10Z over every event carrying a Kalshi ``KX*GAME-`` market
#: with a Tie/Draw leg (4,073 events). Applied as run.8781, 13:33:52Z.
ROUND_1: tuple[tuple[int, int, str, int], ...] = (
    (14655755, 7042354, "Western Michigan", 1),  # 2026-05-13 18:35Z closed    Penn State v Michigan
    (14657756, 2954990, "Minnesota", 3),  # 2026-05-13 18:35Z closed    Ferris State v Minnesota State
    (14657756, 3974481, "Minnesota", 1),  # 2026-05-13 18:35Z closed    Ferris State v Minnesota State
    (14659546, 1860186, "New Hampshire", 2),  # 2026-05-13 18:35Z closed    Providence v New Hampshire
    (14659546, 2076114, "New Hampshire", 1),  # 2026-05-13 18:35Z closed    Providence v New Hampshire
    (14662430, 422437, "Cornell", 2),  # 2026-05-13 18:50Z closed    Princeton v Cornell
    (14678160, 3129783, "Minnesota Duluth", 1),  # 2026-05-13 20:50Z closed    Penn State v Minnesota Duluth
    (14969920, 55687938, "Kansas City", 1),  # 2026-07-17 00:30Z completed St. Louis City SC v Sporting Kansas City
    (15175836, 56944741, "Colorado", 1),  # 2026-07-26 00:30Z completed St. Louis City SC v Colorado Rapids
    (15195469, 58729086, "Wolfsburg", 11),  # 2026-08-16 11:30Z completed Hannover 96 v VfL Wolfsburg
    (15186684, 58728864, "San Jose", 1),  # 2026-08-20 02:30Z completed LA Galaxy v San Jose Earthquakes
    (15290690, 59173207, "Dallas", 602),  # 2026-08-30 23:00Z closed    St. Louis City SC v FC Dallas
    (15297461, 59700892, "U de Concepcion", 113),  # 2026-09-02 00:00Z scheduled Coquimbo v U de Concepcion
    (15293968, 59701100, "Kyoto Sanga", 88),  # 2026-09-02 10:03Z completed Yokohama F Marinos v Kyoto Purple Sanga
    (15297309, 59700822, "Al Qadsiah", 526),  # 2026-09-03 00:00Z scheduled Diriyah Club v Al Qadsiah
    (15297330, 59700832, "Djurgarden", 466),  # 2026-09-03 00:00Z scheduled Mjallby v Djurgarden
    (15297396, 59700824, "Beitar Jerusalem", 283),  # 2026-09-03 00:00Z scheduled Hapoel Tel Aviv v Beitar Jerusalem
    (15297439, 59700766, "Dorados", 384),  # 2026-09-03 00:00Z scheduled Tepatitlan v Dorados
    (15303027, 59700752, "Adhyaksa", 298),  # 2026-09-04 00:00Z scheduled Arema FC v Adhyaksa
    (15297358, 59700727, "Johor Darul Ta'zim", 1658),  # 2026-09-04 15:15Z scheduled Brunei DPMM v Johor Darul Ta'zim
    (15291070, 59700427, "New England", 312),  # 2026-09-06 01:30Z completed LA Galaxy v New England Revolution
    (15307925, 60490178, "Telstar", 4),  # 2026-09-09 20:45Z voided    Enschede v Telstar
    (15298466, 59700261, "Miami", 1),  # 2026-09-10 00:30Z completed Chicago Fire v Inter Miami CF
    (15307824, 60489439, "Flamengo", 1),  # 2026-09-11 03:30Z voided    Ind. del Valle v Flamengo
    (15307914, 60489309, "Liepaja", 1),  # 2026-09-11 17:00Z voided    Ogre United v Liepaja
    (15304748, 60489225, "Anderlecht", 1),  # 2026-09-11 18:46Z completed KV Mechelen v Anderlecht
    (15307911, 60489285, "Kladno", 1),  # 2026-09-11 19:00Z voided    FC Silon Taborsko v Kladno
    (15307881, 60489070, "Lion City Sailors", 12),  # 2026-09-12 14:30Z voided    Hougang United v Lion City Sailors
    (15308759, 60616553, "Metropolitanos", 18),  # 2026-09-12 23:00Z voided    Academia Anzoategui FC v Metropolitanos
    (15308758, 60616541, "Tachira", 1),  # 2026-09-13 00:00Z voided    Est. Merida v Tachira
    (15307855, 60488610, "Llaneros", 1),  # 2026-09-13 00:05Z voided    Internacional de Bogota v Llaneros
    (15301219, 60488432, "Minnesota", 1252),  # 2026-09-13 00:30Z completed St. Louis City SC v Minnesota United FC
    (15309426, 60672924, "Trinidense", 2),  # 2026-09-13 00:30Z voided    CD Recoleta v Trinidense
    (15307847, 60488506, "Loudoun United FC", 1),  # 2026-09-13 02:00Z voided    Pittsburgh v Loudoun United FC
    (15307845, 60488504, "Ind. Medellin", 1),  # 2026-09-13 02:10Z voided    Boyaca Chico v Ind. Medellin
    (15301228, 60482352, "Seattle", 720),  # 2026-09-13 02:30Z completed LA Galaxy v Seattle Sounders FC
    (15308755, 60616464, "Bay FC", 1),  # 2026-09-13 03:00Z voided    Seattle Reign v Bay FC
    (15307682, 60482360, "Detroit City FC", 1),  # 2026-09-13 05:00Z voided    Sacramento Republic v Detroit City FC
    (15308746, 60616423, "Chelsea", 1),  # 2026-09-13 14:00Z voided    Manchester United v Chelsea
    (15308738, 60616401, "Rayong FC", 1),  # 2026-09-13 15:00Z voided    Chonburi v Rayong FC
    (15308736, 60616394, "Brighton and Hove", 1),  # 2026-09-13 16:00Z voided    Birmingham City WFC v Brighton and Hove
    (15308733, 60616382, "Crystal Palace", 1),  # 2026-09-13 16:45Z voided    Arsenal v Crystal Palace
    (15307093, 60609098, "Basaksehir", 1),  # 2026-09-13 17:00Z completed Amed SK v Basaksehir
    (15307687, 60482274, "Feyenoord", 1),  # 2026-09-13 17:45Z voided    Zwolle v Feyenoord
    (15308729, 60616365, "Ajax", 1),  # 2026-09-13 17:45Z voided    Heerenveen v Ajax
    (15308731, 60616367, "Eindhoven", 1),  # 2026-09-13 17:45Z voided    Alkmaar v Eindhoven
    (15308578, 60609092, "Manchester City", 1),  # 2026-09-13 20:30Z voided    Aston Villa v Manchester City
    (15304473, 60481982, "Philadelphia", 1),  # 2026-09-14 01:00Z completed San Diego FC v Philadelphia Union
    (15307094, 60636858, "Fenerbahce", 1),  # 2026-09-14 17:00Z completed Gazişehir Gaziantep v Fenerbahce
    (15307041, 60481916, "Estoril", 3),  # 2026-09-14 19:45Z completed Braga v Estoril
    (15310508, 60779807, "Orense", 1),  # 2026-09-15 03:00Z suspended Uni Catolica v Orense
    (15307695, 60481857, "Newcastle", 1),  # 2026-09-15 14:00Z suspended Kashima v Newcastle
    (15310504, 60779754, "Salernitana", 1),  # 2026-09-15 22:00Z suspended Barletta v Salernitana
    (15305845, 60481782, "Sevilla", 2),  # 2026-09-16 17:00Z completed Deportivo La Coruña v Sevilla
    (15307677, 60481778, "Jagiellonia", 1),  # 2026-09-16 22:00Z suspended Olympiacos v Jagiellonia
    (15308583, 60608969, "Sporting Jax", 1),  # 2026-09-17 01:00Z suspended Hartford Athletic v Sporting Jax
    (15298552, 60481745, "Lech Poznan", 1),  # 2026-09-17 19:00Z completed Crystal Palace v Lech Poznań
    (15307672, 60481746, "Ferencvarosi", 1),  # 2026-09-17 22:00Z suspended Celtic v Ferencvarosi
    (15307694, 60481705, "Vallecano", 1),  # 2026-09-19 12:00Z suspended Osasuna v Vallecano
    (15306037, 60481701, "Mainz", 1054),  # 2026-09-19 13:30Z completed Borussia Monchengladbach v FSV Mainz 05
    (15315400, 61508514, "Boyaca Chico", 1),  # 2026-09-19 23:00Z suspended Millonarios v Boyaca Chico
    (15311392, 60481456, "Toronto", 1053),  # 2026-09-20 00:30Z completed St. Louis City SC v Toronto FC
    (15312183, 61497857, "Paju Frontier", 3),  # 2026-09-20 10:00Z suspended Gimhae FC v Paju Frontier FC
    (15315207, 61497752, "CONG AN", 1),  # 2026-09-20 15:00Z suspended Truong Tuoi Dong Nai v CONG AN
    (15312373, 61496891, "Radomiak Radom", 1),  # 2026-09-20 18:15Z completed Lech Poznań v Radomiak Radom
    (15315096, 61496179, "Hammarby Talang", 1),  # 2026-09-21 20:00Z suspended Arlanda v Hammarby Talang
    (15315093, 61496161, "Lumezzane", 1),  # 2026-09-21 21:30Z suspended Dolomiti Bellunesi v Lumezzane
    (15315085, 61495946, "Cali", 1),  # 2026-09-23 04:00Z suspended Independ. Santa Fe v Cali
    (15315045, 60636771, "Congo Republic", 1),  # 2026-09-24 16:00Z suspended Namibia v Congo Republic
    (15315079, 61495837, "Louisville City", 3),  # 2026-09-25 23:00Z suspended Hartford Athletic v Louisville City
    (15311770, 61495803, "Blackpool", 3),  # 2026-09-26 14:00Z suspended Notts County FC v Blackpool FC
    (15313656, 61495789, "CD Ceuta 6 de Junio", 11),  # 2026-09-26 16:00Z suspended UB Lebrijana v CD Ceuta 6 de Junio
    (15315075, 61495809, "Eritrea", 8),  # 2026-09-26 16:00Z suspended Kenya v Eritrea
    (15315072, 61495675, "Atletico Melilla CF", 5),  # 2026-09-26 21:00Z suspended Unico Atletico Pinatarense v Atletico Melilla CF
    (15312621, 62399356, "Dominican Republic", 3),  # 2026-09-28 01:00Z scheduled Trinidad and Tobago v Dominican Republic
    (15312629, 61485137, "America", 1),  # 2026-09-28 03:10Z scheduled Club Necaxa v CF América
    (15314918, 61485122, "Burkina Faso", 1),  # 2026-09-28 19:00Z scheduled Central African Republic v Burkina Faso
    (15314924, 61485120, "Congo DR", 12),  # 2026-09-28 19:00Z scheduled Zimbabwe v Congo DR
    (15314933, 61485121, "Sierra Leone", 2),  # 2026-09-28 19:00Z scheduled Equatorial Guinea v Sierra Leone
    (15313075, 62399095, "El Salvador", 2),  # 2026-09-29 02:00Z scheduled Guatemala v El Salvador
    (15314930, 61485102, "Senegal", 1),  # 2026-09-29 16:00Z scheduled Ethiopia v Senegal
    (15314942, 61485103, "Algeria", 13),  # 2026-09-29 16:00Z scheduled Burundi v Algeria
    (15314919, 61485096, "Nigeria", 2),  # 2026-09-29 19:00Z scheduled Guinea-Bissau v Nigeria
    (15314929, 61485097, "Rwanda", 2),  # 2026-09-29 19:00Z scheduled Cape Verde v Rwanda
    (15314915, 61485088, "Ivory Coast", 1),  # 2026-09-29 22:00Z scheduled Somalia v Ivory Coast
    (15314926, 61485091, "Cameroon", 2),  # 2026-09-29 22:00Z scheduled Congo Republic v Cameroon
    (15314928, 61485089, "Mali", 1),  # 2026-09-29 22:00Z scheduled Liberia v Mali
    (15314936, 61485074, "South Africa", 1),  # 2026-09-30 19:00Z scheduled Eritrea v South Africa
    (15319008, 62398906, "Las Vegas Lights", 1),  # 2026-10-01 02:00Z scheduled Sacramento Republic v Las Vegas Lights
    (15319011, 62398920, "Sporting Jax", 2),  # 2026-10-01 02:00Z scheduled Miami v Sporting Jax
    (15319010, 62398914, "Indy Eleven", 2),  # 2026-10-01 02:30Z scheduled Rhode Island FC v Indy Eleven
    (15314898, 62398799, "Montenegro", 133),  # 2026-10-02 16:00Z scheduled Latvia v Montenegro
    (15314891, 62398778, "Georgia", 97),  # 2026-10-02 18:45Z scheduled Hungary v Georgia
    (15314892, 62398781, "Sweden", 1),  # 2026-10-02 18:45Z scheduled Bosnia and Herzegovina v Sweden
    (15314897, 62398779, "Slovakia", 1),  # 2026-10-02 18:45Z scheduled Faroe Islands v Slovakia
    (15316107, 62398724, "England", 185),  # 2026-10-03 16:00Z scheduled Croatia v England
    (15316103, 62384018, "Scotland", 1),  # 2026-10-03 18:45Z scheduled North Macedonia v Scotland
    (15317811, 62383856, "Spain", 1),  # 2026-10-06 18:45Z scheduled Croatia v Spain
    (15316568, 62455759, "Columbus", 1),  # 2026-10-10 23:30Z scheduled Orlando City SC v Columbus Crew SC
)

#: Re-census 2026-09-27 ~14:30Z of the rows the chart backfill wrote AFTER
#: round 1's census, on heavy v104, before heavy v105 (12:56Z) carried #9066's
#: code half (9abb549612). Same population rule, same predicate; every
#: draw-bearing Kalshi group with an away-leg row above round 1's highest
#: banked id (13842066) is here, and none has a row written since v105.
#: A round-2 entry REPLACES the round-1 entry for its key.
ROUND_2: tuple[tuple[int, int, str, int], ...] = (
    (15314891, 62398778, "Georgia", 117),  # round 1 banked 97, so run.8781 skipped it; v104 added 20 (ids 13969614-13969633)
    (15314006, 61485166, "Colorado", 1432),  # 2026-09-27 02:30Z completed LA Galaxy v Colorado Rapids (#9130), ids 13969977-13971408
)

EXPECTED: tuple[tuple[int, int, str, int], ...] = tuple(
    {(e, m, leg): (e, m, leg, c) for e, m, leg, c in ROUND_1 + ROUND_2}.values()
)
EXPECTED_KEYS = {(e, m, leg) for e, m, leg, _ in EXPECTED}


def wrong_app_refusal() -> str | None:
    """Return a refusal string when not running on :data:`PRODUCER_APP`."""
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to run on HEROKU_APP_NAME={app!r}: this repair writes "
        f"production rows and runs only on {PRODUCER_APP!r}"
    )


def row_shape_is_away_reading(row: dict) -> bool:
    """True when the stored home number is ``yes`` or ``1 - yes`` of the away leg."""
    home = row.get("home_win_probability")
    yes = row.get("yes_probability")
    if home is None or yes is None:
        return False
    home, yes = float(home), float(yes)
    return (
        abs(home - (1.0 - yes)) <= SHAPE_TOLERANCE
        or abs(home - yes) <= SHAPE_TOLERANCE
    )


def group_is_deletable(
    key: tuple[int, int, str],
    banked_count: int,
    event: dict | None,
    outcome_names: list[str],
    rows: list[dict],
) -> str | None:
    """Return None when every row of this group may be deleted, else why not.

    PURE and per-group. Each refusal is a reason the rows might now be a real
    home reading, or that something is still writing them.
    """
    event_id, _market_id, leg = key
    if key not in EXPECTED_KEYS:
        return "not in the pinned population"
    if event is None:
        return f"event {event_id} no longer exists"
    if not rows:
        return "already repaired"
    if len(rows) > banked_count:
        return (
            f"{len(rows)} rows, banked {banked_count} — something wrote more "
            f"away-leg rows since the census; find the writer before deleting"
        )
    outcomes = [SimpleNamespace(name=name) for name in outcome_names]
    leg_rows = [o for o in outcomes if o.name == leg]
    if len(leg_rows) != 1:
        return f"market no longer carries exactly one {leg!r} leg"
    if not away_leg_complement_is_not_home(
        outcomes,
        leg_rows[0],
        False,
        event["home_team_name"],
        event["away_team_name"],
    ):
        return (
            f"{leg!r} is no longer the away leg of a draw-bearing field for "
            f"{event['home_team_name']} v {event['away_team_name']}"
        )
    off_shape = [r["id"] for r in rows if not row_shape_is_away_reading(r)]
    if off_shape:
        return (
            f"{len(off_shape)} row(s) are not an away-leg reading "
            f"(first: {off_shape[0]})"
        )
    return None


async def _load(session) -> tuple[dict, dict, dict]:
    event_ids = sorted({e for e, _, _, _ in EXPECTED})
    market_ids = sorted({m for _, m, _, _ in EXPECTED})
    ev_result = await session.execute(
        text("""
            SELECT id, home_team_name, away_team_name, commence_time, status
              FROM events WHERE id = ANY(:ids)
        """),
        {"ids": event_ids},
    )
    events = {r["id"]: dict(r) for r in ev_result.mappings()}

    oc_result = await session.execute(
        text("SELECT market_id, name FROM futures_outcomes WHERE market_id = ANY(:ids)"),
        {"ids": market_ids},
    )
    outcomes: dict[int, list[str]] = {}
    for r in oc_result.mappings():
        outcomes.setdefault(r["market_id"], []).append(r["name"])

    snap_result = await session.execute(
        text(f"""
            SELECT id, event_id,
                   (game_state->>'market_id')::bigint AS market_id,
                   game_state->>'outcome_name' AS leg,
                   home_win_probability,
                   (game_state->>'yes_probability')::numeric AS yes_probability
              FROM win_prob_snapshots
             WHERE source = 'kalshi'
               AND event_id = ANY(:ids)
               AND captured_at < '{CUTOFF}'
        """),
        {"ids": event_ids},
    )
    rows: dict[tuple[int, int, str], list[dict]] = {}
    for r in snap_result.mappings():
        key = (r["event_id"], r["market_id"], r["leg"])
        if key in EXPECTED_KEYS:
            rows.setdefault(key, []).append(dict(r))
    return events, outcomes, rows


async def bank_pre_image(session, ids: list[int]) -> None:
    """Bank whole rows, ORIGINAL ids included, before the first DELETE."""
    await session.execute(
        text(f"""
            CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (
                snapshot_id          BIGINT PRIMARY KEY,
                event_id             BIGINT NOT NULL,
                source               VARCHAR(30) NOT NULL,
                captured_at          TIMESTAMPTZ,
                home_win_probability NUMERIC(5, 4),
                away_win_probability NUMERIC(5, 4),
                draw_probability     NUMERIC(5, 4),
                game_state           JSONB,
                reading_count        INTEGER,
                valid_until          TIMESTAMPTZ,
                banked_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    )
    # ON CONFLICT DO NOTHING: the FIRST pre-image is the true one.
    await session.execute(
        text(f"""
            INSERT INTO {BACKUP_TABLE}
                (snapshot_id, event_id, source, captured_at,
                 home_win_probability, away_win_probability, draw_probability,
                 game_state, reading_count, valid_until)
            SELECT id, event_id, source, captured_at,
                   home_win_probability, away_win_probability, draw_probability,
                   game_state, reading_count, valid_until
              FROM win_prob_snapshots WHERE id = ANY(:ids)
            ON CONFLICT (snapshot_id) DO NOTHING
        """),
        {"ids": ids},
    )


async def run(apply: bool) -> int:
    if apply:
        refusal = wrong_app_refusal()
        if refusal:
            print(f"REFUSED: {refusal}")
            return 2

    async with get_task_session() as session:
        events, outcomes, rows = await _load(session)

        deletable: list[tuple[tuple[int, int, str], list[dict]]] = []
        skipped: list[tuple[tuple[int, int, str], str]] = []
        for event_id, market_id, leg, banked in EXPECTED:
            key = (event_id, market_id, leg)
            group = rows.get(key, [])
            why = group_is_deletable(
                key, banked, events.get(event_id), outcomes.get(market_id, []), group
            )
            if why is None:
                deletable.append((key, group))
            else:
                skipped.append((key, why))

        ids = sorted(r["id"] for _, group in deletable for r in group)
        print(f"#9066 — {'APPLY' if apply else 'DRY RUN'}")
        print(f"  pinned groups       : {len(EXPECTED)}")
        print(f"  pinned rows (banked): {sum(c for *_, c in EXPECTED)}")
        print(f"  deletable groups    : {len(deletable)}")
        print(f"  deletable rows      : {len(ids)}")
        print(f"  skipped groups      : {len(skipped)}")
        for (event_id, market_id, leg), group in deletable:
            ev = events[event_id]
            print(
                f"    {event_id}  {ev['commence_time']:%Y-%m-%d %H:%M}Z  "
                f"{ev['home_team_name']} v {ev['away_team_name']}  "
                f"leg={leg!r} market={market_id}  {len(group)} rows -> DELETE"
            )
        for (event_id, market_id, leg), why in skipped:
            print(f"    SKIP {event_id} market={market_id} leg={leg!r}: {why}")

        if not apply:
            print("\ndry run — nothing written. Re-run with --apply.")
            return 0
        if not ids:
            print("\nnothing to write.")
            return 0

        await bank_pre_image(session, ids)
        banked = (
            await session.execute(
                text(f"SELECT count(*) FROM {BACKUP_TABLE} WHERE snapshot_id = ANY(:ids)"),
                {"ids": ids},
            )
        ).scalar()
        if banked != len(ids):
            await session.rollback()
            print(f"REFUSED: banked {banked} of {len(ids)} rows — nothing deleted")
            return 1

        deleted = 0
        for key, group in deletable:
            event_id, market_id, leg = key
            # Re-assert the pin in the WHERE clause, so a row changed between
            # the SELECT and here is not deleted on a stale read.
            result = await session.execute(
                text(f"""
                    DELETE FROM win_prob_snapshots
                     WHERE id = ANY(:ids)
                       AND source = 'kalshi'
                       AND event_id = :eid
                       AND game_state->>'market_id' = :mid
                       AND game_state->>'outcome_name' = :leg
                       AND captured_at < '{CUTOFF}'
                """),
                {
                    "ids": [r["id"] for r in group],
                    "eid": event_id,
                    "mid": str(market_id),
                    "leg": leg,
                },
            )
            deleted += result.rowcount or 0

        await session.commit()

        drift = len(ids) - deleted
        print(f"\n  pre-image banked in : {BACKUP_TABLE} ({banked} rows)")
        print(f"  rows deleted        : {deleted}")
        print(f"  concurrent_drift    : {drift}")
        print(
            f"\nverify: SELECT count(*) FROM win_prob_snapshots s "
            f"JOIN {BACKUP_TABLE} b ON b.snapshot_id = s.id;  -- expect 0"
        )
        print(
            "undo: python3 scripts/restore_9066_draw_complement_chart_rows.py --apply"
        )
        return 0 if drift == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
