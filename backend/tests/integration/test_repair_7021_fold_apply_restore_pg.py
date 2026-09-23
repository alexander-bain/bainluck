"""#7021 — the Cardinals fold's apply, re-run and undo, against a real PostgreSQL.

The unit file drives the refusals with dicts. Everything that decides what the
fold actually DOES is SQL, and a stub would be the thing deciding its answers:

* the repoint of every foreign key, followed by a DELETE whose own FK actions
  (``team_identity_mapping`` CASCADE, ``entities`` SET NULL) would silently
  destroy or orphan any reference the repoint missed;
* the fresher-board rule, a timestamp comparison with a NULL arm;
* the JSONB alias append and its ``@>`` idempotence guard;
* ``SELECT *`` backup and ``INSERT ... SELECT *`` restore of a whole team row;
* an undo that moves back ONLY the rows it banked.

The tables are built narrow, in a private schema, with the real foreign-key
actions, so this runs on the lane VM's Postgres 14 as well as in CI.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7021 "
            "fold apply/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_7021_pg", _SCRIPTS / "repair_7021_fold_spaceless_cardinals.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

_GATE_SCHEMA = "fold_cardinals_gate_7021"

DUP, CANON, OTHER = m.DUP_ID, m.CANON_ID, 70210003
MLB, PRESEASON = 70210101, 70210102
EV_HOME, EV_AWAY, EV_CANON, EV_OTHER = 70210201, 70210202, 70210203, 70210204
FO_DUP, FO_OTHER = 70210301, 70210302
ENT_DUP = 70210401

#: The seeded population, pinned the way the script pins production's.
SEEDED = {
    ("events", "home_team_id"): 1,
    ("events", "away_team_id"): 1,
    ("futures_outcomes", "team_id"): 1,
    ("entities", "source_team_id"): 1,
    ("user_favorites", "team_id"): 0,
    ("tournament_odds", "team_id"): 0,
    ("team_identity_mapping", "team_id"): 0,
}

DUP_BOARD = '{"wins": 76, "losses": 81, "div_rank": 4, "division": "Central"}'


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def gate(pg_session, monkeypatch):
    monkeypatch.setattr(m, "REPOINTS", dict(SEEDED))
    s = pg_session
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.execute(text(f"CREATE SCHEMA {_GATE_SCHEMA}"))
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    for ddl in (
        "CREATE TABLE sports (id int PRIMARY KEY, key varchar(50) NOT NULL, "
        "name varchar(100) NOT NULL, active boolean NOT NULL)",
        "CREATE TABLE teams (id int PRIMARY KEY, sport_id int NOT NULL REFERENCES sports(id), "
        "name varchar(200) NOT NULL, slug varchar(200) UNIQUE, espn_id varchar(50), "
        "alternate_names jsonb, standings_data jsonb, standings_updated_at timestamptz)",
        "CREATE TABLE events (id int PRIMARY KEY, sport_id int NOT NULL, "
        "home_team_name varchar(200) NOT NULL, away_team_name varchar(200) NOT NULL, "
        "commence_time timestamptz NOT NULL, status varchar(20) NOT NULL, "
        "home_team_id int REFERENCES teams(id), away_team_id int REFERENCES teams(id))",
        "CREATE TABLE futures_outcomes (id int PRIMARY KEY, market_id int NOT NULL, "
        "external_id varchar(200) NOT NULL, name varchar(300) NOT NULL, "
        "team_id int REFERENCES teams(id))",
        "CREATE TABLE entities (id int PRIMARY KEY, kind varchar(20) NOT NULL, "
        "canonical_name varchar(300) NOT NULL, "
        "source_team_id int REFERENCES teams(id) ON DELETE SET NULL)",
        "CREATE TABLE team_identity_mapping (id serial PRIMARY KEY, "
        "team_id int NOT NULL REFERENCES teams(id) ON DELETE CASCADE, "
        "source varchar(30) NOT NULL, source_id varchar(100), source_name varchar(200), "
        "sport_key varchar(50), created_at timestamptz NOT NULL DEFAULT now(), "
        "updated_at timestamptz NOT NULL DEFAULT now())",
        "CREATE TABLE user_favorites (id serial PRIMARY KEY, user_id int NOT NULL, "
        "team_id int NOT NULL REFERENCES teams(id))",
        "CREATE TABLE tournament_odds (id serial PRIMARY KEY, tournament_id int NOT NULL, "
        "team_id int NOT NULL REFERENCES teams(id))",
    ):
        await s.execute(text(ddl))
    await s.execute(
        text(
            "INSERT INTO sports (id, key, name, active) VALUES "
            f"({MLB}, 'baseball_mlb', 'MLB', true), "
            f"({PRESEASON}, 'baseball_mlb_preseason', 'MLB Preseason', true)"
        )
    )
    await s.execute(
        text(
            "INSERT INTO teams (id, sport_id, name, slug, espn_id, alternate_names, "
            "standings_data, standings_updated_at) VALUES "
            f"({DUP}, {MLB}, 'St.Louis Cardinals', 'stlouis-cardinals', '24', "
            f"'[\"Cardinals\", \"St. Louis Cardinals\"]', '{DUP_BOARD}', '2026-09-23 08:00:06+00'), "
            f"({CANON}, {MLB}, 'St. Louis Cardinals', 'st-louis-cardinals-mlb', '24', "
            "'[\"St. Louis\", \"Cardinals\"]', NULL, NULL), "
            f"({OTHER}, {MLB}, 'Pittsburgh Pirates', 'pittsburgh-pirates-mlb', '23', "
            "NULL, NULL, NULL)"
        )
    )
    await s.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, home_team_id, away_team_id) VALUES "
            f"({EV_HOME}, {MLB}, 'St.Louis Cardinals', 'Pittsburgh Pirates', "
            f"'2026-08-29 00:15+00', 'completed', {DUP}, {OTHER}), "
            f"({EV_AWAY}, {MLB}, 'Pittsburgh Pirates', 'St.Louis Cardinals', "
            f"'2026-08-30 18:15+00', 'closed', {OTHER}, {DUP}), "
            f"({EV_CANON}, {MLB}, 'Pittsburgh Pirates', 'St. Louis Cardinals', "
            f"'2026-09-23 22:40+00', 'live', {OTHER}, {CANON}), "
            f"({EV_OTHER}, {MLB}, 'Pittsburgh Pirates', 'Chicago Cubs', "
            f"'2026-09-23 22:40+00', 'live', {OTHER}, NULL)"
        )
    )
    await s.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, team_id) VALUES "
            f"({FO_DUP}, 1, 'fo-dup', 'St. Louis Cardinals', {DUP}), "
            f"({FO_OTHER}, 1, 'fo-other', 'Pittsburgh Pirates', {OTHER})"
        )
    )
    await s.execute(
        text(
            "INSERT INTO entities (id, kind, canonical_name, source_team_id) VALUES "
            f"({ENT_DUP}, 'team', 'St.Louis Cardinals', {DUP})"
        )
    )
    await s.commit()
    yield s
    await s.rollback()
    await s.execute(text("SET search_path TO public"))
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.commit()


async def _one(s, sql, **params):
    return (await s.execute(text(sql), params)).one()


async def _team_ref_state(s):
    return {
        "ev_home": (await _one(s, f"SELECT home_team_id FROM events WHERE id = {EV_HOME}"))[0],
        "ev_away": (await _one(s, f"SELECT away_team_id FROM events WHERE id = {EV_AWAY}"))[0],
        "ev_canon": (await _one(s, f"SELECT away_team_id FROM events WHERE id = {EV_CANON}"))[0],
        "fo_dup": (await _one(s, f"SELECT team_id FROM futures_outcomes WHERE id = {FO_DUP}"))[0],
        "fo_other": (await _one(s, f"SELECT team_id FROM futures_outcomes WHERE id = {FO_OTHER}"))[0],
        "entity": (await _one(s, f"SELECT source_team_id FROM entities WHERE id = {ENT_DUP}"))[0],
    }


async def _dup_exists(s):
    return (await _one(s, f"SELECT count(*) FROM teams WHERE id = {DUP}"))[0] == 1


async def test_dry_run_writes_nothing(gate):
    code, lines = await m.repair(gate, "dry")
    assert code == 0, lines
    assert await _dup_exists(gate)
    assert (await _team_ref_state(gate))["ev_home"] == DUP
    backup = (await _one(gate, "SELECT to_regclass(:t)", t=m.BACKUP_TEAMS))[0]
    assert backup is None


async def test_apply_folds_every_reference_and_deletes_the_duplicate(gate):
    code, lines = await m.repair(gate, "apply")
    assert code == 0, lines

    assert not await _dup_exists(gate)
    refs = await _team_ref_state(gate)
    assert refs == {
        "ev_home": CANON,
        "ev_away": CANON,
        "ev_canon": CANON,
        "fo_dup": CANON,
        "fo_other": OTHER,
        # Repointed, NOT nulled by the delete's SET NULL.
        "entity": CANON,
    }
    name, alts, board, stamp = await _one(
        gate,
        f"SELECT name, alternate_names, standings_data, standings_updated_at "
        f"FROM teams WHERE id = {CANON}",
    )
    assert name == "St. Louis Cardinals"
    assert alts == ["St. Louis", "Cardinals", "St.Louis Cardinals"]
    assert board["div_rank"] == 4 and stamp is not None
    legacy = (
        await gate.execute(
            text(
                "SELECT team_id, source_name, sport_key FROM team_identity_mapping "
                "WHERE source = 'legacy_slug' AND source_id = 'stlouis-cardinals'"
            )
        )
    ).all()
    assert [tuple(r) for r in legacy] == [(CANON, "St.Louis Cardinals", "baseball_mlb")]
    # The bystander is untouched.
    assert (await _one(gate, f"SELECT name FROM teams WHERE id = {OTHER}"))[0] == "Pittsburgh Pirates"


async def test_a_second_apply_is_a_no_op(gate):
    assert (await m.repair(gate, "apply"))[0] == 0
    code, lines = await m.repair(gate, "apply")
    assert code == 0 and "already applied" in lines[0]
    alts = (await _one(gate, f"SELECT alternate_names FROM teams WHERE id = {CANON}"))[0]
    assert alts.count("St.Louis Cardinals") == 1
    n = (
        await _one(
            gate,
            "SELECT count(*) FROM team_identity_mapping WHERE source = 'legacy_slug'",
        )
    )[0]
    assert n == 1


async def test_restore_undoes_the_fold_and_only_the_fold(gate):
    before = await _team_ref_state(gate)
    assert (await m.repair(gate, "apply"))[0] == 0

    # After the fold, somebody legitimately binds a NEW row to the real club.
    await gate.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, home_team_id, away_team_id) VALUES "
            f"(70210299, {MLB}, 'St. Louis Cardinals', 'Chicago Cubs', "
            f"'2026-09-26 18:15+00', 'scheduled', {CANON}, NULL)"
        )
    )
    await gate.commit()

    code, lines = await m.repair(gate, "restore")
    assert code == 0, lines
    assert await _dup_exists(gate)
    assert await _team_ref_state(gate) == before
    # The undo moved back what it banked — never the row bound after the fold.
    assert (await _one(gate, "SELECT home_team_id FROM events WHERE id = 70210299"))[0] == CANON

    alts, board, stamp = await _one(
        gate,
        f"SELECT alternate_names, standings_data, standings_updated_at FROM teams WHERE id = {CANON}",
    )
    assert alts == ["St. Louis", "Cardinals"]
    assert board is None and stamp is None
    dup_name, dup_board = await _one(
        gate, f"SELECT name, standings_data FROM teams WHERE id = {DUP}"
    )
    assert dup_name == "St.Louis Cardinals" and dup_board["div_rank"] == 4
    n = (
        await _one(
            gate,
            "SELECT count(*) FROM team_identity_mapping WHERE source = 'legacy_slug'",
        )
    )[0]
    assert n == 0


async def test_a_moved_population_refuses_and_writes_nothing(gate):
    await gate.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, home_team_id, away_team_id) VALUES "
            f"(70210298, {MLB}, 'St.Louis Cardinals', 'Chicago Cubs', "
            f"'2026-09-27 18:15+00', 'scheduled', {DUP}, NULL)"
        )
    )
    await gate.commit()
    code, lines = await m.repair(gate, "apply")
    assert code == 2 and "population moved" in lines[-1]
    assert await _dup_exists(gate)
    assert (await _team_ref_state(gate))["ev_home"] == DUP


async def test_a_fresher_board_on_the_real_club_is_kept(gate):
    await gate.execute(
        text(
            f"UPDATE teams SET standings_data = '{{\"div_rank\": 3}}', "
            f"standings_updated_at = '2026-09-24 08:00+00' WHERE id = {CANON}"
        )
    )
    await gate.commit()
    assert (await m.repair(gate, "apply"))[0] == 0
    board = (await _one(gate, f"SELECT standings_data FROM teams WHERE id = {CANON}"))[0]
    assert board == {"div_rank": 3}
