"""#5789 — the #5621 repair's population names what is WRONG with a row.

WHAT WENT WRONG, TWICE, IN OPPOSITE DIRECTIONS
==============================================

`repair_5621_phantom_ffpts_events.py` retires phantom NFL fantasy-points
events — rows the `kxnflffpts` series minted as basketball, which render in
search as a second, fake copy of a real game. Its population was every event
carrying a `kxnflffpts` Kalshi market:

    JOIN futures_markets f ON f.event_id = e.id
    WHERE f.source = 'kalshi' AND lower(f.external_id) LIKE 'kxnflffpts%'

That is an ATTACHMENT question asked about an IDENTITY problem, and the
matcher moves attachments every fifteen minutes. Measured on production:

    2026-09-12        16 rows = 16 phantoms          (script measured "correct")
    2026-09-13 00:00Z 16 rows =  4 phantoms + 12 REAL anchored NFL games
    2026-09-13 03:45Z  2 rows =  2 phantoms          (14 phantoms gone silent)

OVER-REACH first. Twelve Week 2 props were linked to the games they belong to,
so the predicate began selecting the GAMES. `--apply` would have run
`UPDATE events SET status = 'voided'` over the whole Sunday slate, on the
Sunday, an hour before kickoff; every rail is an allowlist over live statuses,
so all twelve would have left the site. Both safety gates passed it:

* `orphans` — the LATERAL had no `e2.id <> ph.id`, so each real game matched
  **itself** (same names, delta 0). `real_id == id`, orphans 0. A gate a row
  can satisfy by pointing at itself is not a gate.
* `MAX_EXPECTED_POPULATION = 60` — 16 is comfortably under it.

UNDER-REACH second, and it is the half that survives fixing the first. The
props of fourteen PHANTOMS were moved off them onto the real games, so those
rows — still `basketball_other`, still anchorless, still rendering as fake
games — silently left the population. A repair fixed only for over-reach would
have run clean, reported success, and cleaned two of sixteen.

THE POPULATION NOW
==================

Four properties the row HAS, none of which another writer can take away:

    sported `basketball_other`      + anchorless (no espn_id, no external_id,
    no team ids) + `commence_time_source LIKE 'kalshi%'` + BOTH team names are
    NFL clubs                                                 -> 16 rows

The club test is what cuts 4,158 anchorless Kalshi-minted basketball rows to
16, and it is why the counterpart LATERAL is still a REAL gate rather than a
tautology: the population is defined WITHOUT it, so a phantom whose real game
is missing or outside ±36h shows up as an orphan and refuses the run.
Measured: 16 rows, 16 distinct counterparts, 0 orphans, 0 self-matches.

WHY THIS NEEDS A REAL SERVER
============================

The whole defect is one SQL predicate over `LATERAL`, `interval`, `extract`
and a correlated `ORDER BY`. No mock session has a query planner, and a test
asserting about the SQL *text* would have passed on both broken versions —
their text was perfectly reasonable. The only witness is a PostgreSQL that
executes it over the rows production actually held.

The corpus is those rows, verbatim: 33 events, 14 markets and 32 clubs, with
ids, names, `espn_id`s, kickoffs and tickers read from production at
2026-09-13 03:45Z, plus one DECOY — a genuine anchorless Kalshi-minted
basketball fixture that must never be retired.

`ORIGINAL_POPULATION_SQL` is the predicate as it SHIPPED, frozen. It is the
only copy left, it is a control rather than a description, and its whole
content is the defect (standing notice 50): two tests run it and assert the
over-reach and the under-reach respectively, on real data rather than on a
strawman.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import pathlib

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #5621 population "
        "gate (CI's search-recall job provides it)"
    ),
)

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1].parent / "scripts"

NFL = "americanfootball_nfl"
OTHER = "basketball_other"

#: The twelve REAL Week 2 games whose `kxnflffpts` props are correctly linked.
#: These are the rows the broken predicate would have voided.
REAL_WITH_TICKER = [
    (14637256, "New York Giants", "Dallas Cowboys", "401872930",
     "2026-09-14 00:20:00+00", 60779928, "KXNFLFFPTS-26SEP13DALNYG"),
    (14638896, "Kansas City Chiefs", "Denver Broncos", "401872931",
     "2026-09-15 00:15:00+00", 60816234, "KXNFLFFPTS-26SEP14DENKC"),
    (14780141, "Houston Texans", "Buffalo Bills", "401872660",
     "2026-09-13 17:00:00+00", 60780328, "KXNFLFFPTS-26SEP13BUFHOU"),
    (14780142, "Carolina Panthers", "Chicago Bears", "401872661",
     "2026-09-13 17:00:00+00", 60780327, "KXNFLFFPTS-26SEP13CHICAR"),
    (14780143, "Cincinnati Bengals", "Tampa Bay Buccaneers", "401872925",
     "2026-09-13 17:00:00+00", 60780323, "KXNFLFFPTS-26SEP13TBCIN"),
    (14780144, "Jacksonville Jaguars", "Cleveland Browns", "401872922",
     "2026-09-13 17:00:00+00", 60780326, "KXNFLFFPTS-26SEP13CLEJAC"),
    (14780145, "Detroit Lions", "New Orleans Saints", "401872923",
     "2026-09-13 17:00:00+00", 60780325, "KXNFLFFPTS-26SEP13NODET"),
    (14780146, "Tennessee Titans", "New York Jets", "401872924",
     "2026-09-13 17:00:00+00", 60780324, "KXNFLFFPTS-26SEP13NYJTEN"),
    (14780147, "Los Angeles Chargers", "Arizona Cardinals", "401872926",
     "2026-09-13 20:25:00+00", 60780089, "KXNFLFFPTS-26SEP13ARILAC"),
    (14780148, "Minnesota Vikings", "Green Bay Packers", "401872927",
     "2026-09-13 20:25:00+00", 60780088, "KXNFLFFPTS-26SEP13GBMIN"),
    (14780149, "Las Vegas Raiders", "Miami Dolphins", "401872928",
     "2026-09-13 20:25:00+00", 60780087, "KXNFLFFPTS-26SEP13MIALV"),
    (14780150, "Philadelphia Eagles", "Washington Commanders", "401872929",
     "2026-09-13 20:25:00+00", 60780086, "KXNFLFFPTS-26SEP13WASPHI"),
]

#: The two phantoms that STILL carry their `kxnflffpts` market. These are the
#: only ones an attachment-based predicate can still see — see
#: `PHANTOMS_UNATTACHED` for the fourteen it lost.
PHANTOMS = [
    (15305028, "New England", "Seattle", "2026-09-10 03:20:00+00",
     "suspended", 60617788, "KXNFLFFPTS-26SEP09NESEA"),
    (15305029, "San Francisco", "Los Angeles R", "2026-09-10 00:00:00+00",
     "scheduled", 60617215, "KXNFLFFPTS-26SEP10SFLAR"),
]

#: The other fourteen phantoms, IDENTICAL in every way that matters — sported
#: `basketball_other`, no `espn_id`, no `external_id`, no team ids, minted by a
#: Kalshi occurrence, abbreviated club names in the reversed orientation, the
#: Kalshi CLOSE rather than kickoff — except that the matcher has since moved
#: their `kxnflffpts` prop onto the real game, so they now carry NO market at
#: all. They are still wrong, still `scheduled`, and still render in search as
#: fake OTHER BASKETBALL games.
#:
#: The predicate that shipped could not see a single one of them. Read at
#: 2026-09-13 03:45Z on production; 15305030/31 were still attached at 02:31Z
#: and had gone silent by 03:45Z, which is how the under-reach was found.
PHANTOMS_UNATTACHED = [
    (15305030, "Atlanta", "Pittsburgh", "2026-09-13 20:00:00+00", "scheduled"),
    (15305031, "Baltimore", "Indianapolis", "2026-09-13 20:00:00+00", "scheduled"),
    (15305032, "Buffalo", "Houston", "2026-09-13 00:00:00+00", "scheduled"),
    (15305033, "Chicago", "Carolina", "2026-09-13 20:00:00+00", "scheduled"),
    (15305034, "Cleveland", "Jacksonville", "2026-09-13 20:00:00+00", "scheduled"),
    (15305035, "New Orleans", "Detroit", "2026-09-13 20:00:00+00", "scheduled"),
    (15305036, "New York J", "Tennessee", "2026-09-13 20:00:00+00", "scheduled"),
    (15305037, "Tampa Bay", "Cincinnati", "2026-09-13 20:00:00+00", "scheduled"),
    (15305038, "Arizona", "Los Angeles C", "2026-09-13 23:25:00+00", "scheduled"),
    (15305039, "Green Bay", "Minnesota", "2026-09-13 00:00:00+00", "scheduled"),
    (15305040, "Miami", "Las Vegas", "2026-09-13 23:25:00+00", "scheduled"),
    (15305041, "Washington", "Philadelphia", "2026-09-13 23:25:00+00", "scheduled"),
    (15305042, "Dallas", "New York G", "2026-09-14 03:20:00+00", "scheduled"),
    (15305046, "Denver", "Kansas City", "2026-09-15 03:15:00+00", "scheduled"),
]

#: A genuine anchorless Kalshi-minted `basketball_other` fixture that is NOT an
#: NFL club pair. It satisfies every clause of the new population EXCEPT the
#: team-name test, and it is what stops that test from being decoration: the
#: predicate without it selects 4,158 rows on production, and this row is the
#: one the gate can prove gets swept up. It must never be retired.
DECOY = (15305099, "Zalgiris", "Maccabi Tel Aviv", "2026-09-13 18:00:00+00",
         "scheduled")

#: The four real games the phantoms above are shadows OF. They carry no
#: `kxnflffpts` market, so they are only ever reachable as counterparts.
COUNTERPARTS = [
    (14780138, "Seattle Seahawks", "New England Patriots", "401872656",
     "2026-09-10 00:20:00+00", "completed"),
    (14632820, "Los Angeles Rams", "San Francisco 49ers", "401872657",
     "2026-09-11 00:35:00+00", "completed"),
    (14780139, "Pittsburgh Steelers", "Atlanta Falcons", "401872658",
     "2026-09-13 17:00:00+00", "scheduled"),
    (14780140, "Indianapolis Colts", "Baltimore Ravens", "401872659",
     "2026-09-13 17:00:00+00", "scheduled"),
]

#: phantom id -> the counterpart the repair must find for it. Sixteen rows,
#: sixteen DISTINCT counterparts — read off production 2026-09-13 03:45Z. The
#: distinctness is the safety proof: no phantom is paired with a game another
#: phantom is also standing in for, and none is paired with itself.
EXPECTED_PAIRING = {
    15305028: 14780138,
    15305029: 14632820,
    15305030: 14780139,
    15305031: 14780140,
    15305032: 14780141,
    15305033: 14780142,
    15305034: 14780144,
    15305035: 14780145,
    15305036: 14780146,
    15305037: 14780143,
    15305038: 14780147,
    15305039: 14780148,
    15305040: 14780149,
    15305041: 14780150,
    15305042: 14637256,
    15305046: 14638896,
}

PHANTOM_IDS = sorted(
    [p[0] for p in PHANTOMS] + [p[0] for p in PHANTOMS_UNATTACHED]
)
ATTACHED_PHANTOM_IDS = sorted(p[0] for p in PHANTOMS)
REAL_TICKER_IDS = sorted(r[0] for r in REAL_WITH_TICKER)

#: Every club name that appears on a real NFL event here, which is what the
#: `nfl_club` CTE reads out of `teams`. Derived from the corpus rather than
#: retyped, so a seed edit cannot leave the club list quietly behind.
NFL_CLUB_NAMES = sorted(
    {r[1] for r in REAL_WITH_TICKER}
    | {r[2] for r in REAL_WITH_TICKER}
    | {c[1] for c in COUNTERPARTS}
    | {c[2] for c in COUNTERPARTS}
)


def _repair():
    name = "repair_5621_phantom_ffpts_events"
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The exact clause text the fix relies on. Held here so a mutant is produced by
# DELETING what the script really contains, never by pasting a second copy of
# the query that could drift into agreeing with itself.
SPORT_CLAUSE = "s.key = :phantom_sport"
SELF_CLAUSE = "AND e2.id <> ph.id"
#: The four "this row was never anchored to anything" clauses. Each one of them
#: independently excludes every real game in the corpus, which is the point of
#: `test_no_single_deletion_lets_a_real_game_back_in`.
ANCHOR_CLAUSES = [
    "AND e.espn_id IS NULL",
    "AND e.external_id IS NULL",
    "AND e.home_team_id IS NULL",
    "AND e.away_team_id IS NULL",
    "AND e.commence_time_source LIKE 'kalshi%'",
]
CLUB_CLAUSE_HOME = (
    "AND EXISTS (SELECT 1 FROM nfl_club c\n"
    "                    WHERE c.name LIKE lower(e.home_team_name) || '%')"
)
CLUB_CLAUSE_AWAY = (
    "AND EXISTS (SELECT 1 FROM nfl_club c\n"
    "                    WHERE c.name LIKE lower(e.away_team_name) || '%')"
)

#: The predicate AS IT SHIPPED, frozen. This is the only copy left — the script
#: no longer contains it — so it is held verbatim rather than derived, and it is
#: a CONTROL, not a description of current behaviour: its whole content is the
#: defect (standing notice 50). Snapshotted 2026-09-13 while both failure modes
#: were live on production. DO NOT "update" it to match the script; it is
#: retired with this gate.
ORIGINAL_POPULATION_SQL = """
WITH ph AS (
    SELECT e.id,
           e.status,
           e.commence_time,
           e.home_team_name AS h,
           e.away_team_name AS a,
           s.key            AS sport_key,
           f.id             AS market_id,
           f.external_id    AS ticker,
           f.llm_sport_category
      FROM events e
      JOIN sports s          ON s.id = e.sport_id
      JOIN futures_markets f ON f.event_id = e.id
     WHERE f.source = 'kalshi'
       AND lower(f.external_id) LIKE :prefix || '%'
)
SELECT ph.*, r.id AS real_id, r.espn_id, r.commence_time AS real_ct
  FROM ph
  LEFT JOIN LATERAL (
        SELECT e2.id, e2.espn_id, e2.commence_time
          FROM events e2
          JOIN sports s2 ON s2.id = e2.sport_id
         WHERE s2.key = :target_sport
           AND e2.espn_id IS NOT NULL
           AND (
                 (lower(e2.home_team_name) LIKE lower(ph.a) || '%'
                  AND lower(e2.away_team_name) LIKE lower(ph.h) || '%')
              OR (lower(e2.home_team_name) LIKE lower(ph.h) || '%'
                  AND lower(e2.away_team_name) LIKE lower(ph.a) || '%')
               )
           AND e2.commence_time BETWEEN ph.commence_time - interval '36 hours'
                                    AND ph.commence_time + interval '36 hours'
         ORDER BY abs(extract(epoch FROM (e2.commence_time - ph.commence_time)))
         LIMIT 1
  ) r ON true
 ORDER BY ph.commence_time
"""


def _without(sql: str, clause: str) -> str:
    """Delete `clause` from `sql`, refusing to return an unchanged string.

    An unmatched patch is the classic vacuous mutant: the "broken" variant is
    the fixed query, it passes, and the test reports that the clause is not
    load-bearing. Reworded the clause? This raises instead of lying.
    """
    if clause not in sql:
        raise AssertionError(
            f"the clause {clause!r} is no longer present in _POPULATION_SQL, so "
            "this mutant would have run the UNMODIFIED query and passed "
            "vacuously. Re-derive the mutant against the current text."
        )
    return sql.replace(clause, "", 1)


def _replace(sql: str, clause: str, with_: str) -> str:
    """`_without` for a clause that cannot simply be deleted.

    `WHERE s.key = :phantom_sport` is the first predicate in its WHERE, so
    deleting it leaves `WHERE AND ...` and the mutant dies of a syntax error —
    which would "pass" a red-expecting test for entirely the wrong reason.
    Neutralising it to TRUE runs the same query with that one restriction
    lifted, which is the thing actually under test.
    """
    if clause not in sql:
        raise AssertionError(
            f"the clause {clause!r} is no longer present in _POPULATION_SQL, so "
            "this mutant would have run the UNMODIFIED query and passed "
            "vacuously. Re-derive the mutant against the current text."
        )
    return sql.replace(clause, with_, 1)


def _closure(*roots):
    """The tables these three need, and nothing else.

    `Base.metadata.create_all()` emits DDL for every model, and one unrelated
    table carries `NULLS NOT DISTINCT` — PostgreSQL 15+ only. Building the whole
    schema would mean this gate's ability to run at all depended on a clause no
    part of it uses, and the failure would read as "the #5621 gate is broken"
    rather than "the server is old". The closure is the tables actually joined
    here plus whatever their foreign keys require.
    """
    seen: dict = {}
    pending = list(roots)
    while pending:
        table = pending.pop()
        if table.key in seen:
            continue
        seen[table.key] = table
        for fk in table.foreign_keys:
            pending.append(fk.column.table)
    return list(seen.values())


@pytest.fixture
async def pg_engine():
    """Function-scoped: `pytest.ini` leaves the fixture loop scope unset."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, FuturesMarket, Sport, Team
    from app.services.database import Base

    # `Team` is reachable from `Event` via the `home_team_id` FK, but this gate
    # now READS `teams` directly (the `nfl_club` CTE), so it is named as a root
    # rather than left to arrive by accident — drop that FK and the closure
    # would silently stop building the table this file depends on.
    tables = _closure(
        Sport.__table__, Event.__table__, FuturesMarket.__table__, Team.__table__
    )
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=tables, checkfirst=True
            )
        )
    yield engine
    await engine.dispose()


async def _seed(conn):
    """Production's 33 events, 14 markets and 32 clubs, verbatim, in one txn."""
    await conn.execute(
        text("DELETE FROM futures_markets WHERE lower(external_id) LIKE 'kxnflffpts%'")
    )
    await conn.execute(
        text("DELETE FROM events WHERE id = ANY(:ids)"),
        {
            "ids": REAL_TICKER_IDS
            + PHANTOM_IDS
            + [c[0] for c in COUNTERPARTS]
            + [DECOY[0]]
        },
    )
    for key, name in ((NFL, "NFL"), (OTHER, "Other Basketball")):
        await conn.execute(
            text(
                "INSERT INTO sports (key, name, active) VALUES (:k, :n, true) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"k": key, "n": name},
        )
    sport = {}
    for key in (NFL, OTHER):
        sport[key] = (
            await conn.execute(
                text("SELECT id FROM sports WHERE key = :k"), {"k": key}
            )
        ).scalar()

    # The `nfl_club` CTE reads club names out of `teams`; without these rows
    # the two team-name clauses match nothing and the population is empty,
    # which would make every ship assertion below pass for the wrong reason.
    # `test_the_seed_can_tell_the_right_answer_from_the_wrong_one` is what
    # notices if this ever stops being seeded.
    await conn.execute(
        text("DELETE FROM teams WHERE sport_id = :sid"), {"sid": sport[NFL]}
    )
    for club in NFL_CLUB_NAMES:
        await conn.execute(
            text("INSERT INTO teams (sport_id, name) VALUES (:sid, :n)"),
            {"sid": sport[NFL], "n": club},
        )

    ins_event = text(
        "INSERT INTO events "
        "(id, sport_id, home_team_name, away_team_name, espn_id, "
        " commence_time, status, commence_time_source) "
        "VALUES (:id, :sid, :h, :a, :espn, :ct, :st, :cts)"
    )
    ins_market = text(
        "INSERT INTO futures_markets "
        "(id, source, external_id, name, category, llm_sport_category, "
        " sport_id, event_id, mutually_exclusive, status) "
        "VALUES (:id, 'kalshi', :ext, :nm, 'prop', :cat, :sid, :eid, "
        "        true, 'open')"
    )

    # Real games carry a provider anchor and a non-Kalshi commence_time_source;
    # phantoms carry neither. That asymmetry IS the population predicate, so it
    # has to be in the seed rather than assumed.
    for eid, h, a, espn, ct, mid, ticker in REAL_WITH_TICKER:
        await conn.execute(ins_event, {
            "id": eid, "sid": sport[NFL], "h": h, "a": a, "espn": espn,
            "ct": dt.datetime.fromisoformat(ct), "st": "scheduled",
            "cts": "odds_api",
        })
        await conn.execute(ins_market, {
            "id": mid, "ext": ticker, "nm": f"{a} fantasy points",
            "cat": "prop", "sid": sport[NFL], "eid": eid,
        })
    for eid, h, a, espn, ct, st in COUNTERPARTS:
        await conn.execute(ins_event, {
            "id": eid, "sid": sport[NFL], "h": h, "a": a, "espn": espn,
            "ct": dt.datetime.fromisoformat(ct), "st": st,
            "cts": "odds_api",
        })
    for eid, h, a, ct, st, mid, ticker in PHANTOMS:
        await conn.execute(ins_event, {
            "id": eid, "sid": sport[OTHER], "h": h, "a": a, "espn": None,
            "ct": dt.datetime.fromisoformat(ct), "st": st,
            "cts": "kalshi_occurrence",
        })
        await conn.execute(ins_market, {
            "id": mid, "ext": ticker, "nm": f"{a} fantasy points",
            "cat": "prop", "sid": sport[OTHER], "eid": eid,
        })
    # The fourteen with NO market — the ones the shipped predicate lost.
    for eid, h, a, ct, st in PHANTOMS_UNATTACHED:
        await conn.execute(ins_event, {
            "id": eid, "sid": sport[OTHER], "h": h, "a": a, "espn": None,
            "ct": dt.datetime.fromisoformat(ct), "st": st,
            "cts": "kalshi_occurrence",
        })
    eid, h, a, ct, st = DECOY
    await conn.execute(ins_event, {
        "id": eid, "sid": sport[OTHER], "h": h, "a": a, "espn": None,
        "ct": dt.datetime.fromisoformat(ct), "st": st,
        "cts": "kalshi_occurrence",
    })


async def _population(conn, sql):
    rows = (
        await conn.execute(
            text(sql),
            {
                "prefix": "kxnflffpts",
                "target_sport": NFL,
                "phantom_sport": OTHER,
            },
        )
    ).all()
    return [
        {"id": r.id, "real_id": r.real_id, "sport_key": r.sport_key}
        for r in rows
    ]


def test_the_seed_can_tell_the_right_answer_from_the_wrong_one():
    """A property of the corpus, so the Postgres gates cannot go vacuous.

    Not gated on a server. The corpus has to contain, simultaneously, the two
    shapes the two failure modes need: real anchored NFL games that wear the
    ticker (or the over-reach has nothing to over-reach onto) and phantoms that
    wear NO ticker (or the under-reach is invisible). If either set empties,
    assertions below would pass on a broken predicate.
    """
    assert len(REAL_WITH_TICKER) == 12
    assert len(PHANTOMS) == 2, "the attached phantoms — the over-reach corpus"
    assert len(PHANTOMS_UNATTACHED) == 14, "the under-reach corpus"
    assert len(PHANTOM_IDS) == 16
    assert all(r[3] for r in REAL_WITH_TICKER), "real games must carry espn_id"
    assert set(EXPECTED_PAIRING) == set(PHANTOM_IDS)
    assert len(set(EXPECTED_PAIRING.values())) == 16, (
        "sixteen phantoms must pair with sixteen DISTINCT real games — a "
        "shared counterpart would mean one of them is not a shadow of it"
    )
    assert not set(EXPECTED_PAIRING) & set(EXPECTED_PAIRING.values()), (
        "no phantom may be its own counterpart, or the pairing proves nothing"
    )
    assert len(NFL_CLUB_NAMES) == 32, "every club the corpus names"
    assert DECOY[0] not in set(PHANTOM_IDS)


def test_every_load_bearing_clause_is_present_in_the_shipped_query():
    """Cheap, and it runs where Postgres does not.

    The mutants below delete these strings; if a refactor renames one this
    fails here with the reason, rather than silently downgrading the gates.
    """
    sql = _repair()._POPULATION_SQL
    for clause in (SPORT_CLAUSE, SELF_CLAUSE, CLUB_CLAUSE_HOME, CLUB_CLAUSE_AWAY):
        assert clause in sql, clause


def test_the_population_no_longer_depends_on_an_attached_market():
    """The under-reach, as a property of the SQL rather than of a server.

    The market join must be LEFT. An inner join is what lost fourteen rows, and
    it is a one-word edit away from coming back.
    """
    sql = _repair()._POPULATION_SQL
    assert "LEFT JOIN futures_markets f" in sql
    assert "JOIN futures_markets f ON f.event_id = e.id\n     WHERE" not in sql


@needs_postgres
async def test_the_population_is_the_sixteen_phantoms_and_nothing_else(pg_engine):
    """THE SHIP. All sixteen fake games are in scope; nothing else is.

    Twelve real ticket-bearing games, four real counterparts and one genuine
    basketball fixture are all in the corpus and none of them is selected.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, _repair()._POPULATION_SQL)

    assert sorted(r["id"] for r in rows) == PHANTOM_IDS
    assert {r["sport_key"] for r in rows} == {OTHER}


@needs_postgres
async def test_the_fourteen_with_no_market_are_in_scope(pg_engine):
    """RED ON THE UNDER-REACH, stated on its own so it cannot be lost.

    These rows carry no `kxnflffpts` market at all. Under the predicate that
    shipped they were unreachable; they are the fourteen fake games a reader
    would still have found in search after a clean, successful repair run.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, _repair()._POPULATION_SQL)

    selected = {r["id"] for r in rows}
    assert {p[0] for p in PHANTOMS_UNATTACHED} <= selected
    assert {p[0] for p in PHANTOMS} <= selected


@needs_postgres
async def test_every_phantom_still_finds_its_real_counterpart(pg_engine):
    """The fix must not buy reach by weakening the safety proof.

    Zero orphans, and each phantom pairs with the game production pairs it
    with — reversed orientation, Kalshi close time, up to 24.6h apart.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, _repair()._POPULATION_SQL)

    assert [r for r in rows if r["real_id"] is None] == []
    assert {r["id"]: r["real_id"] for r in rows} == EXPECTED_PAIRING
    assert len({r["real_id"] for r in rows}) == 16


@needs_postgres
async def test_no_row_can_be_its_own_counterpart(pg_engine):
    """The self-match is what made `orphans == 0` a lie."""
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, _repair()._POPULATION_SQL)

    assert [r for r in rows if r["real_id"] == r["id"]] == []


@needs_postgres
async def test_the_shipped_predicate_still_reproduces_the_over_reach(pg_engine):
    """RED ON THE DEFECT AS IT SHIPPED, run from the frozen control.

    `ORIGINAL_POPULATION_SQL` is the query that was live on production, and on
    production's own rows it returns sixteen — but only two of them are
    phantoms. Twelve are the real Week 2 slate, every one self-matched, so the
    orphan refusal reported a clean zero and `--apply` would have voided them.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, ORIGINAL_POPULATION_SQL)

    assert len(rows) == 14
    scooped = sorted(r["id"] for r in rows if r["id"] in set(REAL_TICKER_IDS))
    assert scooped == REAL_TICKER_IDS, "the twelve real games were in scope"
    assert sorted(r["id"] for r in rows if r["real_id"] == r["id"]) == (
        REAL_TICKER_IDS
    ), "and each answered the safety gate with itself"
    assert [r for r in rows if r["real_id"] is None] == [], (
        "the orphan gate reported no orphans on the form that shipped — that "
        "is precisely why it did not stop the apply"
    )


@needs_postgres
async def test_the_shipped_predicate_still_reproduces_the_under_reach(pg_engine):
    """The same frozen control, read for what it MISSES.

    Fourteen of the sixteen phantoms are simply absent from it. Fixing only the
    over-reach would have left a repair that runs clean and cleans two.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, ORIGINAL_POPULATION_SQL)

    selected = {r["id"] for r in rows}
    missed = sorted(set(PHANTOM_IDS) - selected)
    assert missed == sorted(p[0] for p in PHANTOMS_UNATTACHED)
    assert len(missed) == 14
    assert sorted(set(PHANTOM_IDS) & selected) == ATTACHED_PHANTOM_IDS


@needs_postgres
async def test_no_single_deletion_lets_a_real_game_back_in(pg_engine):
    """THE SAFETY PROPERTY, stated over every clause rather than one.

    The over-reach cannot return through any single edit. Six clauses are
    lifted one at a time — the sport test and each of the four anchor tests and
    the provenance test — and in every case the population still contains no
    NFL-sported row and none of the twelve real ticket-bearing games.

    This is deliberately stronger than "clause X is load-bearing", and it is
    also HONEST about something the first draft of this file got wrong: the
    sport clause is *not* individually what keeps the real games out. Each of
    the anchorless clauses does it too, because a real game has an `espn_id`,
    an `external_id`, team ids and an `odds_api` commence-time source. That is
    defence in depth and it should be recorded as such, not overclaimed.
    """
    sql = _repair()._POPULATION_SQL
    real = set(REAL_TICKER_IDS) | {c[0] for c in COUNTERPARTS}
    mutants = [(SPORT_CLAUSE, _replace(sql, SPORT_CLAUSE, "TRUE"))]
    mutants += [(c, _without(sql, c)) for c in ANCHOR_CLAUSES]

    async with pg_engine.begin() as conn:
        await _seed(conn)
        for clause, mutant in mutants:
            rows = await _population(conn, mutant)
            assert {r["sport_key"] for r in rows} == {OTHER}, clause
            assert not {r["id"] for r in rows} & real, (
                f"lifting {clause!r} let a real anchored game into a "
                "population whose apply sets status='voided'"
            )


@needs_postgres
async def test_the_self_clause_is_the_backstop_for_a_lost_sport_test(pg_engine):
    """Why `e2.id <> ph.id` stays even though it can no longer fire.

    While the population is restricted to `basketball_other` a row CANNOT be
    its own counterpart: the LATERAL only looks at NFL-sported rows. So the
    self clause is unreachable today, and the honest way to keep it is to show
    what it does when the clauses above it are gone — which is exactly the
    state the script shipped in.

    Strip the population back to the club test alone and the twelve real games
    return. WITH the self clause they land as orphans and `--apply` refuses;
    WITHOUT it they answer the safety gate with themselves, orphans reads a
    clean zero, and the Week 2 slate is retired.
    """
    sql = _repair()._POPULATION_SQL
    stripped = _replace(sql, SPORT_CLAUSE, "TRUE")
    for clause in ANCHOR_CLAUSES:
        stripped = _without(stripped, clause)
    no_self = _without(stripped, SELF_CLAUSE)

    async with pg_engine.begin() as conn:
        await _seed(conn)
        with_self = await _population(conn, stripped)
        without_self = await _population(conn, no_self)

    orphaned = {r["id"] for r in with_self if r["real_id"] is None}
    assert set(REAL_TICKER_IDS) <= orphaned, (
        "with the self clause present a real game has no counterpart but "
        "itself, so it must orphan and refuse the run"
    )
    selfmatched = {r["id"] for r in without_self if r["real_id"] == r["id"]}
    assert set(REAL_TICKER_IDS) <= selfmatched, (
        "and without it, it answers the safety gate with itself — orphans "
        "reads zero and the apply proceeds"
    )
    assert not [r for r in without_self if r["real_id"] is None], (
        "that is the clean-zero orphan count that did not stop the apply"
    )


@needs_postgres
async def test_the_club_clauses_are_what_stop_this_being_a_sweep(pg_engine):
    """The decoy is the whole point of the team-name test.

    A genuine anchorless Kalshi-minted basketball fixture satisfies every other
    clause. On production, dropping these two takes the population from 16 to
    4,158 — here it takes in Zalgiris–Maccabi, which must never be retired.
    """
    sql = _repair()._POPULATION_SQL
    swept = _without(_without(sql, CLUB_CLAUSE_HOME), CLUB_CLAUSE_AWAY)
    async with pg_engine.begin() as conn:
        await _seed(conn)
        tight = await _population(conn, sql)
        loose = await _population(conn, swept)

    assert DECOY[0] not in {r["id"] for r in tight}
    assert DECOY[0] in {r["id"] for r in loose}, (
        "without the club clauses a real basketball fixture enters a "
        "population whose apply sets status='voided'"
    )
