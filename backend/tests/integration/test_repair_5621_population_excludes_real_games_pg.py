"""#5789 — the #5621 repair stops selecting the games it was matching against.

WHAT WENT WRONG, AND WHY NEITHER REFUSAL SAW IT
===============================================

`repair_5621_phantom_ffpts_events.py` retires phantom NFL fantasy-points
events. Its population was every event carrying a `kxnflffpts` Kalshi market:

    JOIN futures_markets f ON f.event_id = e.id
    WHERE f.source = 'kalshi' AND lower(f.external_id) LIKE 'kxnflffpts%'

On 2026-09-12 that was exactly the 16 phantoms, so the script was measured
correct and staged as an attended `DO` for Alex. By 2026-09-13 00:00Z it was a
different set: **4 phantoms and 12 REAL anchored NFL games**, because the
matcher had linked twelve of those props to the games they belong to. The
predicate asked what a row had ATTACHED, not what was WRONG with it, and being
correctly linked is not a reason to be retired.

Both safety gates then passed it:

* `orphans` — a phantom with no real counterpart aborts the run. The LATERAL
  had no `e2.id <> ph.id`, so each real game matched **itself** (same names,
  same kickoff, delta 0). `real_id == id`, orphans 0.
* `MAX_EXPECTED_POPULATION = 60` — 16 is comfortably under it.

`--apply` would then have run `UPDATE events SET status = 'voided'` over all
sixteen ids and cleared `event_id` on their markets: the whole Week 2 Sunday
slate retired on the Sunday, an hour before kickoff. Every rail is an allowlist
over live statuses, so all twelve games would have vanished from the site.

THE TWO CLAUSES, AND WHY BOTH ARE HERE
======================================

Either one alone averts the disaster, and they fail in different directions,
which is why the fix ships both and this file grades them separately:

``AND NOT (s.key = :target_sport AND e.espn_id IS NOT NULL)``
    Names the phantom property, so the twelve are never in scope. Correct
    outcome: population 4, the repair still does its job.
``AND e2.id <> ph.id``
    A row may not be its own counterpart. On its own it does not shrink the
    population — it turns the twelve into ORPHANS, and the orphan refusal then
    stops the run. Wrong outcome, safe outcome: the repair is blocked rather
    than destructive.

WHY THIS NEEDS A REAL SERVER
============================

The whole defect is one SQL predicate over `LATERAL`, `interval`, `extract` and
a correlated `ORDER BY`. No mock session has a query planner, and a test that
asserted about the SQL *text* would have passed on the broken version — the
broken version's text was perfectly reasonable. The only witness is a
PostgreSQL that executes it over the rows production actually held.

The corpus is those rows, verbatim: ids, club names, `espn_id`s, kickoffs and
tickers read from production at 2026-09-13 00:00Z. Delete either clause and
this file goes red on real data rather than on a strawman — which is the point
of `test_the_old_predicate_still_reproduces_the_defect_on_this_corpus`, the one
test here that runs the BROKEN form and asserts it destroys the slate.
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

#: The four phantoms: `basketball_other`, no `espn_id`, abbreviated club names
#: in the reversed orientation, and the Kalshi CLOSE rather than kickoff.
PHANTOMS = [
    (15305028, "New England", "Seattle", "2026-09-10 03:20:00+00",
     "suspended", 60617788, "KXNFLFFPTS-26SEP09NESEA"),
    (15305029, "San Francisco", "Los Angeles R", "2026-09-10 00:00:00+00",
     "scheduled", 60617215, "KXNFLFFPTS-26SEP10SFLAR"),
    (15305030, "Atlanta", "Pittsburgh", "2026-09-13 20:00:00+00",
     "scheduled", 60780330, "KXNFLFFPTS-26SEP13ATLPIT"),
    (15305031, "Baltimore", "Indianapolis", "2026-09-13 20:00:00+00",
     "scheduled", 60780329, "KXNFLFFPTS-26SEP13BALIND"),
]

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

#: phantom id -> the counterpart the repair must find for it.
EXPECTED_PAIRING = {
    15305028: 14780138,
    15305029: 14632820,
    15305030: 14780139,
    15305031: 14780140,
}

PHANTOM_IDS = sorted(p[0] for p in PHANTOMS)
REAL_TICKER_IDS = sorted(r[0] for r in REAL_WITH_TICKER)


def _repair():
    name = "repair_5621_phantom_ffpts_events"
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The exact clause text the fix added. Held here so a mutant is produced by
# DELETING what the script really contains, never by pasting a second copy of
# the query that could drift into agreeing with itself.
SCOPE_CLAUSE = "AND NOT (s.key = :target_sport AND e.espn_id IS NOT NULL)"
SELF_CLAUSE = "AND e2.id <> ph.id"


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
    from app.models.models import Event, FuturesMarket, Sport
    from app.services.database import Base

    tables = _closure(Sport.__table__, Event.__table__, FuturesMarket.__table__)
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
    """Production's 20 events and 16 markets, verbatim, in one transaction."""
    await conn.execute(
        text("DELETE FROM futures_markets WHERE lower(external_id) LIKE 'kxnflffpts%'")
    )
    await conn.execute(
        text("DELETE FROM events WHERE id = ANY(:ids)"),
        {
            "ids": REAL_TICKER_IDS
            + PHANTOM_IDS
            + [c[0] for c in COUNTERPARTS]
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

    ins_event = text(
        "INSERT INTO events "
        "(id, sport_id, home_team_name, away_team_name, espn_id, "
        " commence_time, status) "
        "VALUES (:id, :sid, :h, :a, :espn, :ct, :st)"
    )
    ins_market = text(
        "INSERT INTO futures_markets "
        "(id, source, external_id, name, category, llm_sport_category, "
        " sport_id, event_id, mutually_exclusive, status) "
        "VALUES (:id, 'kalshi', :ext, :nm, 'prop', :cat, :sid, :eid, "
        "        true, 'open')"
    )

    for eid, h, a, espn, ct, mid, ticker in REAL_WITH_TICKER:
        await conn.execute(ins_event, {
            "id": eid, "sid": sport[NFL], "h": h, "a": a, "espn": espn,
            "ct": dt.datetime.fromisoformat(ct), "st": "scheduled",
        })
        await conn.execute(ins_market, {
            "id": mid, "ext": ticker, "nm": f"{a} fantasy points",
            "cat": "prop", "sid": sport[NFL], "eid": eid,
        })
    for eid, h, a, espn, ct, st in COUNTERPARTS:
        await conn.execute(ins_event, {
            "id": eid, "sid": sport[NFL], "h": h, "a": a, "espn": espn,
            "ct": dt.datetime.fromisoformat(ct), "st": st,
        })
    for eid, h, a, ct, st, mid, ticker in PHANTOMS:
        await conn.execute(ins_event, {
            "id": eid, "sid": sport[OTHER], "h": h, "a": a, "espn": None,
            "ct": dt.datetime.fromisoformat(ct), "st": st,
        })
        await conn.execute(ins_market, {
            "id": mid, "ext": ticker, "nm": f"{a} fantasy points",
            "cat": "prop", "sid": sport[OTHER], "eid": eid,
        })


async def _population(conn, sql):
    rows = (
        await conn.execute(
            text(sql),
            {"prefix": "kxnflffpts", "target_sport": NFL},
        )
    ).all()
    return [
        {"id": r.id, "real_id": r.real_id, "sport_key": r.sport_key}
        for r in rows
    ]


def test_the_seed_can_tell_the_right_answer_from_the_wrong_one():
    """A property of the corpus, so the Postgres gates cannot go vacuous.

    Not gated on a server. If the seed ever stopped containing real anchored
    NFL games that wear the ticker, every assertion below would pass on the
    broken predicate too — the defect needs those twelve rows to exist.
    """
    assert len(REAL_WITH_TICKER) == 12
    assert len(PHANTOMS) == 4
    assert all(r[3] for r in REAL_WITH_TICKER), "real games must carry espn_id"
    assert set(EXPECTED_PAIRING) == set(PHANTOM_IDS)
    assert not set(EXPECTED_PAIRING.values()) & set(REAL_TICKER_IDS), (
        "a phantom must pair with a counterpart that is NOT itself in the "
        "ticker-bearing set, or the pairing assertion proves nothing"
    )


def test_both_clauses_are_present_in_the_shipped_query():
    """Cheap, and it runs where Postgres does not.

    The mutants below delete these two strings; if a refactor renames them this
    fails here with the reason, rather than silently downgrading the gates.
    """
    sql = _repair()._POPULATION_SQL
    assert SCOPE_CLAUSE in sql
    assert SELF_CLAUSE in sql


@needs_postgres
async def test_the_population_is_the_four_phantoms_and_nothing_else(pg_engine):
    """THE SHIP. Twelve real games are out of scope; the four phantoms are in."""
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, _repair()._POPULATION_SQL)

    assert sorted(r["id"] for r in rows) == PHANTOM_IDS
    assert {r["sport_key"] for r in rows} == {OTHER}


@needs_postgres
async def test_every_phantom_still_finds_its_real_counterpart(pg_engine):
    """The fix must not buy safety by breaking the repair.

    Zero orphans, and each phantom pairs with the game production pairs it
    with — reversed orientation, Kalshi close time, up to 24.6h apart.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, _repair()._POPULATION_SQL)

    assert [r for r in rows if r["real_id"] is None] == []
    assert {r["id"]: r["real_id"] for r in rows} == EXPECTED_PAIRING


@needs_postgres
async def test_no_row_can_be_its_own_counterpart(pg_engine):
    """The self-match is what made `orphans == 0` a lie."""
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, _repair()._POPULATION_SQL)

    assert [r for r in rows if r["real_id"] == r["id"]] == []


@needs_postgres
async def test_the_old_predicate_still_reproduces_the_defect_on_this_corpus(
    pg_engine,
):
    """RED ON THE DEFECT. Delete both clauses and the slate is back in scope.

    This is the test that makes the other three mean something: it runs the
    form that shipped, on production's own rows, and asserts the disaster —
    sixteen rows, twelve of them real games, every one of them self-matched so
    the orphan refusal reports a clean zero.
    """
    broken = _without(
        _without(_repair()._POPULATION_SQL, SCOPE_CLAUSE), SELF_CLAUSE
    )
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, broken)

    assert len(rows) == 16
    scooped = sorted(r["id"] for r in rows if r["id"] in set(REAL_TICKER_IDS))
    assert scooped == REAL_TICKER_IDS
    assert sorted(r["id"] for r in rows if r["real_id"] == r["id"]) == (
        REAL_TICKER_IDS
    )
    assert [r for r in rows if r["real_id"] is None] == [], (
        "the orphan gate reported no orphans on the broken form — that is "
        "precisely why it did not stop the apply"
    )


@needs_postgres
async def test_the_scope_clause_alone_is_enough(pg_engine):
    """Each clause is graded on its own, because they fail differently.

    Scope clause only: the right answer. Four phantoms, all paired.
    """
    only_scope = _without(_repair()._POPULATION_SQL, SELF_CLAUSE)
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, only_scope)

    assert sorted(r["id"] for r in rows) == PHANTOM_IDS
    assert [r for r in rows if r["real_id"] is None] == []


@needs_postgres
async def test_the_self_clause_alone_fails_safe_rather_than_correct(pg_engine):
    """Self clause only: the twelve stay in scope but become ORPHANS.

    That is the wrong population and the right outcome — `--apply` refuses on
    `orphans > 0` instead of voting twelve real games out of existence. Asserted
    so nobody later removes it believing the scope clause made it redundant:
    it is the backstop for a phantom the scope clause cannot recognise.
    """
    only_self = _without(_repair()._POPULATION_SQL, SCOPE_CLAUSE)
    async with pg_engine.begin() as conn:
        await _seed(conn)
        rows = await _population(conn, only_self)

    assert len(rows) == 16
    orphans = sorted(r["id"] for r in rows if r["real_id"] is None)
    assert orphans == REAL_TICKER_IDS
