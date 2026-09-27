"""#5576 — the venue-named-competition repair's apply, re-run and undo, against a real PostgreSQL.

The unit file drives the refusal rule with dicts. What the repair DOES is SQL:

* the population read — the pinned rows, their linked markets' venue listing
  (a Polymarket slug and a Kalshi ticker), the clubs through the matcher's own
  ``leagues_by_side_for_matchup``, and the same-day counterpart read;
* the banked pre-image and the ``sport_id`` move guarded on the value read;
* a re-run that finds nothing left to place;
* an undo that moves back ONLY rows still where the repair put them;
* and the ship, read the way a card reads its competition: the row's
  ``sports.key`` through its ``sport_id``.

Built narrow, in a private schema, so it runs on the lane VM's Postgres 14 as
well as in CI.
"""

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #5576 "
            "venue-placement apply/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_5576_pg", _SCRIPTS / "repair_5576_venue_named_competition.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

_GATE_SCHEMA = "venue_placement_gate_5576"
UNL = "soccer_uefa_nations_league"
NOW = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)

OTHER, NATIONS, WORLD_CUP, SEGUNDA = 55760001, 55760002, 55760003, 55760004
PORTUGAL, NORWAY, ISRAEL, CZECH = 55760101, 55760102, 55760103, 55760104
ENGLAND, EIBAR = 55760105, 55760106

# Pinned and qualifying.
EV_POR_NOR = 55760201  # two competitions shared; Polymarket `unl-` slug
EV_IRL_ISR = 55760202  # one side unresolvable; Kalshi KXUEFANLGAME only
# Pinned, but must be skipped.
EV_CZE_ENG = 55760203  # the league already holds "Czech Republic" v England
EV_TAGGED = 55760204  # the drain has tagged it duplicate-of since measurement
EV_PLAYED = 55760205  # kicked off before the run
# Not pinned: qualifies by the rule, must not be touched.
EV_UNPINNED = 55760206
# The league's own rows.
EV_ESPN_CZE = 55760301

PLACEMENTS = (
    (EV_POR_NOR, UNL),
    (EV_IRL_ISR, UNL),
    (EV_CZE_ENG, UNL),
    (EV_TAGGED, UNL),
    (EV_PLAYED, UNL),
)


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _event(id_, sport, home, away, when, source, tags='[]'):
    return (
        f"({id_}, {sport}, '{home}', '{away}', TIMESTAMPTZ '{when}+00', "
        f"'scheduled', '{source}', '{tags}')"
    )


def _market(id_, event_id, source, external_id, meta):
    return (
        f"({id_}, '{source}', '{external_id}', 'market {id_}', 'sports', true, "
        f"'open', {event_id}, '{json.dumps(meta)}')"
    )


@pytest.fixture
async def gate(pg_session, monkeypatch):
    monkeypatch.setattr(m, "PLACEMENTS", PLACEMENTS)
    s = pg_session
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.execute(text(f"CREATE SCHEMA {_GATE_SCHEMA}"))
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    for ddl in (
        "CREATE TABLE sports (id int PRIMARY KEY, key varchar(50) NOT NULL UNIQUE, "
        "name varchar(100) NOT NULL, active boolean NOT NULL)",
        "CREATE TABLE teams (id int PRIMARY KEY, sport_id int NOT NULL REFERENCES sports(id), "
        "name varchar(200) NOT NULL, alternate_names jsonb)",
        "CREATE TABLE team_identity_mapping (id int PRIMARY KEY, "
        "team_id int NOT NULL REFERENCES teams(id), source varchar(30) NOT NULL, "
        "source_name varchar(300), sport_key varchar(50))",
        "CREATE TABLE events (id int PRIMARY KEY, sport_id int NOT NULL REFERENCES sports(id), "
        "home_team_name varchar(200) NOT NULL, away_team_name varchar(200) NOT NULL, "
        "commence_time timestamptz NOT NULL, status varchar(20) NOT NULL, "
        "commence_time_source varchar(40), event_tags jsonb DEFAULT '[]')",
        "CREATE TABLE futures_markets (id int PRIMARY KEY, source varchar(20) NOT NULL, "
        "external_id varchar(200) NOT NULL, name varchar(500) NOT NULL, "
        "category varchar(50) NOT NULL, mutually_exclusive boolean NOT NULL, "
        "status varchar(20) NOT NULL, event_id int REFERENCES events(id), "
        "market_metadata jsonb)",
    ):
        await s.execute(text(ddl))
    await s.execute(
        text(
            "INSERT INTO sports (id, key, name, active) VALUES "
            f"({OTHER}, 'soccer_other', 'Other Soccer', true), "
            f"({NATIONS}, '{UNL}', 'UEFA Nations League', true), "
            f"({WORLD_CUP}, 'soccer_fifa_world_cup', 'FIFA World Cup', true), "
            f"({SEGUNDA}, 'soccer_spain_segunda_division', 'Segunda', true)"
        )
    )
    await s.execute(
        text(
            "INSERT INTO teams (id, sport_id, name, alternate_names) VALUES "
            f"({PORTUGAL}, {NATIONS}, 'Portugal', NULL), "
            f"({PORTUGAL + 50}, {WORLD_CUP}, 'Portugal', NULL), "
            f"({NORWAY}, {NATIONS}, 'Norway', NULL), "
            f"({NORWAY + 50}, {WORLD_CUP}, 'Norway', NULL), "
            f"({ISRAEL}, {NATIONS}, 'Israel', NULL), "
            f"({CZECH}, {NATIONS}, 'Czech Republic', '[\"Czechia\"]'), "
            f"({ENGLAND}, {NATIONS}, 'England', NULL), "
            f"({EIBAR}, {SEGUNDA}, 'SD Eibar', NULL)"
        )
    )
    await s.execute(
        text(
            "INSERT INTO team_identity_mapping (id, team_id, source, source_name, "
            "sport_key) VALUES "
            f"(55760401, {ISRAEL}, 'kalshi', 'Israel', '{UNL}')"
        )
    )
    await s.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, commence_time_source, event_tags) VALUES "
            + ", ".join(
                [
                    _event(EV_POR_NOR, OTHER, "Portugal", "Norway",
                           "2026-10-04 18:45", "polymarket_venue"),
                    _event(EV_IRL_ISR, OTHER, "Republic of Ireland", "Israel",
                           "2026-10-04 18:45", "polymarket_venue"),
                    _event(EV_CZE_ENG, OTHER, "Czechia", "England",
                           "2026-09-29 18:45", "polymarket_venue"),
                    _event(EV_TAGGED, OTHER, "Norway", "Israel",
                           "2026-10-05 18:45", "polymarket_venue",
                           '["provenance:duplicate-of:55760301"]'),
                    _event(EV_PLAYED, OTHER, "Israel", "Portugal",
                           "2026-09-27 05:00", "polymarket_venue"),
                    _event(EV_UNPINNED, OTHER, "England", "Norway",
                           "2026-10-06 18:45", "polymarket_venue"),
                    _event(EV_ESPN_CZE, NATIONS, "Czech Republic", "England",
                           "2026-09-29 18:45", "espn"),
                ]
            )
        )
    )
    unl = {"polymarket_event_slug": "unl-x-y-2026-10-04"}
    await s.execute(
        text(
            "INSERT INTO futures_markets (id, source, external_id, name, category, "
            "mutually_exclusive, status, event_id, market_metadata) VALUES "
            + ", ".join(
                [
                    _market(55760501, EV_POR_NOR, "polymarket", "1057948", unl),
                    _market(55760502, EV_POR_NOR, "kalshi",
                            "KXUEFANLGAME-26OCT04PORNOR-POR", {}),
                    _market(55760503, EV_IRL_ISR, "kalshi",
                            "KXUEFANLGAME-26OCT04IRLISR-ISR", {}),
                    _market(55760504, EV_IRL_ISR, "polymarket", "1057999",
                            {"polymarket_event_id": "1"}),
                    _market(55760505, EV_CZE_ENG, "polymarket", "1052000", unl),
                    _market(55760506, EV_TAGGED, "polymarket", "1052001", unl),
                    _market(55760507, EV_PLAYED, "polymarket", "1052002", unl),
                    _market(55760508, EV_UNPINNED, "polymarket", "1052003", unl),
                ]
            )
        )
    )
    await s.commit()
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    yield s
    await s.rollback()
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.commit()


async def _league_of(s, event_id):
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    res = await s.execute(
        text(
            "SELECT s.key FROM events e JOIN sports s ON s.id = e.sport_id "
            "WHERE e.id = :id"
        ),
        {"id": event_id},
    )
    return res.scalar_one()


async def _backup_rows(s):
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    res = await s.execute(
        text(f"SELECT event_id, from_sport_id, to_sport_id FROM {m.BACKUP} ORDER BY 1")
    )
    return [tuple(r) for r in res]


async def test_the_dry_run_names_every_row_and_writes_nothing(gate):
    code, lines = await m.repair(gate, "dry", NOW)
    text_out = "\n".join(lines)
    assert code == 0
    assert f"place {EV_POR_NOR} -> {UNL}" in text_out
    assert f"place {EV_IRL_ISR} -> {UNL}" in text_out
    assert f"skip {EV_CZE_ENG}" in text_out and "#8818" in text_out
    assert f"skip {EV_TAGGED}" in text_out and "duplicate-of" in text_out
    assert f"skip {EV_PLAYED}" in text_out and "kicked off" in text_out
    assert "Would place 2, skip 3" in text_out
    for event_id in (EV_POR_NOR, EV_IRL_ISR, EV_UNPINNED):
        assert await _league_of(gate, event_id) == "soccer_other"


async def test_apply_places_the_qualifying_pins_and_nothing_else(gate):
    code, lines = await m.repair(gate, "apply", NOW)
    assert code == 0, lines
    # The ship: both Nations League games read the Nations League.
    assert await _league_of(gate, EV_POR_NOR) == UNL
    assert await _league_of(gate, EV_IRL_ISR) == UNL
    # Every skip stayed exactly where it was.
    for event_id in (EV_CZE_ENG, EV_TAGGED, EV_PLAYED):
        assert await _league_of(gate, event_id) == "soccer_other"
    # A row the rule WOULD place, but nobody pinned, is not touched.
    assert await _league_of(gate, EV_UNPINNED) == "soccer_other"
    assert await _league_of(gate, EV_ESPN_CZE) == UNL
    assert await _backup_rows(gate) == [
        (EV_POR_NOR, OTHER, NATIONS),
        (EV_IRL_ISR, OTHER, NATIONS),
    ]


async def test_a_re_run_places_nothing_and_keeps_the_first_pre_image(gate):
    assert (await m.repair(gate, "apply", NOW))[0] == 0
    code, lines = await m.repair(gate, "apply", NOW)
    assert code == 0
    assert "nothing to place" in "\n".join(lines)
    assert await _backup_rows(gate) == [
        (EV_POR_NOR, OTHER, NATIONS),
        (EV_IRL_ISR, OTHER, NATIONS),
    ]


async def test_restore_moves_back_only_rows_still_where_the_repair_put_them(gate):
    assert (await m.repair(gate, "apply", NOW))[0] == 0
    # Somebody moves one placed row on after the repair; the undo leaves it.
    await gate.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    await gate.execute(
        text("UPDATE events SET sport_id = :wc WHERE id = :id"),
        {"wc": WORLD_CUP, "id": EV_IRL_ISR},
    )
    await gate.commit()
    await gate.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    code, lines = await m.repair(gate, "restore", NOW)
    assert code == 0
    assert "restored 1 event(s)" in "\n".join(lines)
    assert await _league_of(gate, EV_POR_NOR) == "soccer_other"
    assert await _league_of(gate, EV_IRL_ISR) == "soccer_fifa_world_cup"
    assert await _league_of(gate, EV_ESPN_CZE) == UNL


async def test_restore_before_any_apply_is_a_no_op(gate):
    code, lines = await m.repair(gate, "restore", NOW)
    assert code == 0
    assert "restored 0 event(s)" in "\n".join(lines)


async def test_a_missing_league_row_refuses_and_writes_nothing(gate, monkeypatch):
    monkeypatch.setattr(
        m, "PLACEMENTS", PLACEMENTS + ((EV_UNPINNED, "soccer_nowhere_league"),)
    )
    code, lines = await m.repair(gate, "apply", NOW)
    assert code == 2
    assert "no sports row" in "\n".join(lines)
    assert await _league_of(gate, EV_POR_NOR) == "soccer_other"
