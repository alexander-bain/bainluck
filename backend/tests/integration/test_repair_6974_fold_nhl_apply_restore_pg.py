"""#6974 NHL residual — the duplicate-club repair's apply, re-run and undo, against a real PostgreSQL.

The unit file drives the refusals with dicts. What the repair DOES is SQL:

* the Kalshi "Columbus" mapping moved to the Blue Jackets BEFORE the fold, so
  ``_apply_merge`` does not hand it to the Islanders (and the delete's CASCADE
  does not destroy it);
* ``team_merge._apply_merge`` per fold, with the bare city "New York" kept off
  the Islanders' aliases;
* the strip of the "New Jersey" row's borrowed Islanders identity;
* ``SELECT *`` backup and an undo that moves back ONLY what it banked;
* and the ship: the search route's own Teams filter and rank
  (``routes/events.py::_build_team_search_filter`` / ``_team_search_rank``)
  lead "rangers" and "islanders" with the real club.

Built narrow, in a private schema with the real foreign-key actions, so it runs
on the lane VM's Postgres 14 as well as in CI.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import select, text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6974 NHL "
            "fold apply/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_6974_nhl_pg", _SCRIPTS / "repair_6974_fold_nhl_duplicate_clubs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

_GATE_SCHEMA = "fold_nhl_gate_6974"

NHL = 69741101
RANGERS, ISLANDERS, BLUE_JACKETS, DEVILS = 69741001, 69741002, 69741003, 69741004
NEW_YORK_R, NEW_YORK_I, NEW_JERSEY = 69741011, 69741012, 69741013
EV_R_HOME, EV_R_AWAY, EV_I_HOME, EV_REAL = 69741201, 69741202, 69741203, 69741204
FO_R_TEAM, FO_R_PLAYER = 69741301, 69741302
ENT_RANGERS, ENT_R, ENT_I = 69741401, 69741402, 69741403
MAP_COLUMBUS, MAP_I_NAME = 69741501, 69741502

NYR = "https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/nyr.png"
NYI = "https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/nyi.png"

FOLDS = (
    m.Fold(NEW_YORK_R, "New York R", RANGERS, "New York Rangers", "13", (1, 1, 2, 1, 0, 0, 0),
           ("Rangers", "New York Rangers")),
    m.Fold(NEW_YORK_I, "New York I", ISLANDERS, "New York Islanders", "12", (1, 0, 0, 1, 1, 0, 0),
           ("New York Islanders", "Islanders", "New York"), drop_aliases=("New York",)),
)
STRIPS = (m.Strip(NEW_JERSEY, "New Jersey", "12", NYI, ("New York Islanders", "Islanders")),)
MAPPING_EDITS = (
    m.MappingEdit(MAP_COLUMBUS, "kalshi", "Columbus", NEW_YORK_I, BLUE_JACKETS, "Columbus Blue Jackets"),
)


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _team(id_, name, slug, espn, abbr, aliases, crest, record):
    return (
        f"({id_}, {NHL}, '{name}', '{slug}', "
        + ("NULL" if espn is None else f"'{espn}'")
        + ", "
        + ("NULL" if aliases is None else f"'{json.dumps(aliases)}'")
        + f", NULL, '{crest}', '{crest}', '#0056ae', '#e51937', "
        + ("NULL" if abbr is None else f"'{abbr}'")
        + f", '{record}', 'New York')"
    )


@pytest.fixture
async def gate(pg_session, monkeypatch):
    monkeypatch.setattr(m, "FOLDS", FOLDS)
    monkeypatch.setattr(m, "STRIPS", STRIPS)
    monkeypatch.setattr(m, "MAPPING_EDITS", MAPPING_EDITS)
    s = pg_session
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.execute(text(f"CREATE SCHEMA {_GATE_SCHEMA}"))
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    for ddl in (
        "CREATE TABLE sports (id int PRIMARY KEY, key varchar(50) NOT NULL, "
        "name varchar(100) NOT NULL, active boolean NOT NULL)",
        "CREATE TABLE teams (id int PRIMARY KEY, sport_id int NOT NULL REFERENCES sports(id), "
        "name varchar(200) NOT NULL, slug varchar(200) UNIQUE, espn_id varchar(50), "
        "alternate_names jsonb, logo_url text, logo_url_small varchar(512), "
        "logo_url_large varchar(512), primary_color varchar(7), secondary_color varchar(7), "
        "abbreviation varchar(20), current_record varchar(20), location varchar(200))",
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
        "source varchar(30) NOT NULL, source_id varchar(200), source_name varchar(300), "
        "sport_key varchar(50), created_at timestamptz NOT NULL DEFAULT now(), "
        "updated_at timestamptz NOT NULL DEFAULT now())",
        "CREATE UNIQUE INDEX uq_tim_source_id ON team_identity_mapping "
        "(source, source_id, sport_key) WHERE source_id IS NOT NULL",
        "CREATE UNIQUE INDEX uq_tim_source_name ON team_identity_mapping "
        "(source, source_name, sport_key) WHERE source_name IS NOT NULL",
        "CREATE TABLE user_favorites (id serial PRIMARY KEY, user_id int NOT NULL, "
        "team_id int NOT NULL REFERENCES teams(id), relation_type varchar(20) NOT NULL, "
        "UNIQUE (user_id, team_id, relation_type))",
        "CREATE TABLE tournament_odds (id serial PRIMARY KEY, "
        "team_id int NOT NULL REFERENCES teams(id))",
    ):
        await s.execute(text(ddl))
    await s.execute(text(
        f"INSERT INTO sports (id, key, name, active) VALUES ({NHL}, 'icehockey_nhl', 'NHL', true)"
    ))
    teams = [
        # Production's shape: the real clubs carry only their nickname as an
        # alias, the duplicates carry the full name too — which is why search
        # ranked the duplicates first.
        _team(RANGERS, "New York Rangers", "new-york-rangers", "13", "NYR", ["Rangers"], NYR, "1-2-0"),
        _team(ISLANDERS, "New York Islanders", "new-york-islanders", "12", "NYI",
              ["Islanders"], NYI, "1-1-0"),
        _team(BLUE_JACKETS, "Columbus Blue Jackets", "columbus-blue-jackets", "29", "CBJ",
              ["Blue Jackets"], NYI, "0-2-0"),
        _team(DEVILS, "New Jersey Devils", "new-jersey-devils", "11", "NJ", ["Devils"], NYI, "2-0-0"),
        _team(NEW_YORK_R, "New York R", "new-york-r", "13", "NYR",
              ["Rangers", "New York Rangers"], NYR, "28-33-8"),
        _team(NEW_YORK_I, "New York I", "new-york-i", "12", "NYI",
              ["New York Islanders", "Islanders", "New York"], NYI, "39-26-5"),
        _team(NEW_JERSEY, "New Jersey", "new-jersey", "12", "NYI",
              ["New York Islanders", "Islanders"], NYI, "42-27-5"),
    ]
    await s.execute(text(
        "INSERT INTO teams (id, sport_id, name, slug, espn_id, alternate_names, logo_url, "
        "logo_url_small, logo_url_large, primary_color, secondary_color, abbreviation, "
        "current_record, location) VALUES " + ", ".join(teams)
    ))
    await s.execute(text(
        "INSERT INTO events (id, sport_id, home_team_name, away_team_name, commence_time, "
        "status, home_team_id, away_team_id) VALUES "
        f"({EV_R_HOME}, {NHL}, 'New York R', 'Winnipeg', '2026-03-22 16:00+00', 'closed', "
        f"{NEW_YORK_R}, NULL), "
        f"({EV_R_AWAY}, {NHL}, 'New Jersey', 'New York R', '2026-03-31 23:00+00', 'closed', "
        f"{NEW_JERSEY}, {NEW_YORK_R}), "
        f"({EV_I_HOME}, {NHL}, 'New York I', 'Columbus', '2026-03-22 23:00+00', 'closed', "
        f"{NEW_YORK_I}, NULL), "
        f"({EV_REAL}, {NHL}, 'New York Rangers', 'New Jersey Devils', '2026-10-08 23:00+00', "
        f"'scheduled', {RANGERS}, {DEVILS})"
    ))
    await s.execute(text(
        "INSERT INTO futures_outcomes (id, market_id, external_id, name, team_id) VALUES "
        f"({FO_R_TEAM}, 8, 'nyr', 'New York Rangers', {NEW_YORK_R}), "
        f"({FO_R_PLAYER}, 9, 'fox', 'Adam Fox', {NEW_YORK_R})"
    ))
    # The Rangers already have an entity, so New York R's goes NULL on the delete;
    # the Islanders have none, so New York I's is repointed.
    await s.execute(text(
        "INSERT INTO entities (id, kind, canonical_name, source_team_id) VALUES "
        f"({ENT_RANGERS}, 'team', 'New York Rangers', {RANGERS}), "
        f"({ENT_R}, 'team', 'New York R', {NEW_YORK_R}), "
        f"({ENT_I}, 'team', 'New York I', {NEW_YORK_I})"
    ))
    await s.execute(text(
        "INSERT INTO team_identity_mapping (id, team_id, source, source_name, sport_key) VALUES "
        f"({MAP_COLUMBUS}, {NEW_YORK_I}, 'kalshi', 'Columbus', 'icehockey_nhl'), "
        f"({MAP_I_NAME}, {ISLANDERS}, 'kalshi', 'New York I', 'icehockey_nhl')"
    ))
    await s.commit()
    yield s
    await s.rollback()
    await s.execute(text("SET search_path TO public"))
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.commit()


async def _scalar(s, sql, **params):
    return (await s.execute(text(sql), params)).scalar_one()


async def _teams_snapshot(s):
    rows = (await s.execute(text("SELECT * FROM teams ORDER BY id"))).mappings().all()
    return [dict(r) for r in rows]


async def _refs(s):
    one = lambda sql: _scalar(s, sql)  # noqa: E731
    return {
        "ev_r_home": await one(f"SELECT home_team_id FROM events WHERE id = {EV_R_HOME}"),
        "ev_r_away": await one(f"SELECT away_team_id FROM events WHERE id = {EV_R_AWAY}"),
        "ev_r_away_home": await one(f"SELECT home_team_id FROM events WHERE id = {EV_R_AWAY}"),
        "ev_i_home": await one(f"SELECT home_team_id FROM events WHERE id = {EV_I_HOME}"),
        "fo_team": await one(f"SELECT team_id FROM futures_outcomes WHERE id = {FO_R_TEAM}"),
        "fo_player": await one(f"SELECT team_id FROM futures_outcomes WHERE id = {FO_R_PLAYER}"),
        "ent_r": await one(f"SELECT source_team_id FROM entities WHERE id = {ENT_R}"),
        "ent_i": await one(f"SELECT source_team_id FROM entities WHERE id = {ENT_I}"),
        "map_columbus": await one(f"SELECT team_id FROM team_identity_mapping WHERE id = {MAP_COLUMBUS}"),
    }


BEFORE_REFS = {
    "ev_r_home": NEW_YORK_R, "ev_r_away": NEW_YORK_R, "ev_r_away_home": NEW_JERSEY,
    "ev_i_home": NEW_YORK_I, "fo_team": NEW_YORK_R, "fo_player": NEW_YORK_R,
    "ent_r": NEW_YORK_R, "ent_i": NEW_YORK_I, "map_columbus": NEW_YORK_I,
}


async def _search(s, q: str) -> list[int]:
    """The ids the search route's own Teams filter and rank return, in order."""
    from app.models.models import Team
    from app.routes.events import _build_team_search_filter, _team_search_rank

    res = await s.execute(
        select(Team.id)
        .where(_build_team_search_filter(q))
        .order_by(_team_search_rank(q).desc(), Team.name)
    )
    return [r[0] for r in res]


async def test_before_the_repair_search_leads_with_the_duplicates(gate):
    # The control: the seeded shape reproduces production's defect.
    assert (await _search(gate, "rangers"))[0] == NEW_YORK_R
    islanders = await _search(gate, "islanders")
    assert islanders[0] != ISLANDERS
    assert {NEW_YORK_I, NEW_JERSEY} <= set(islanders)


async def test_dry_run_writes_nothing(gate):
    before = await _teams_snapshot(gate)
    code, lines = await m.repair(gate, "dry")
    assert code == 0, lines
    assert await _teams_snapshot(gate) == before
    assert await _refs(gate) == BEFORE_REFS
    assert await _scalar(gate, "SELECT to_regclass(:t)", t=m.BACKUP_TEAMS) is None


async def test_apply_folds_strips_repoints_and_search_leads_with_the_club(gate):
    code, lines = await m.repair(gate, "apply")
    assert code == 0, lines

    for dup in (NEW_YORK_R, NEW_YORK_I):
        assert await _scalar(gate, f"SELECT count(*) FROM teams WHERE id = {dup}") == 0
    assert await _refs(gate) == {
        "ev_r_home": RANGERS, "ev_r_away": RANGERS,
        # The stripped row keeps its own references — nothing repoints it.
        "ev_r_away_home": NEW_JERSEY,
        "ev_i_home": ISLANDERS, "fo_team": RANGERS, "fo_player": RANGERS,
        "ent_r": None, "ent_i": ISLANDERS,
        # Kalshi's "Columbus" is the Blue Jackets — not the Islanders, and not
        # cascaded away with the deleted row.
        "map_columbus": BLUE_JACKETS,
    }
    rangers = await _scalar(gate, f"SELECT alternate_names FROM teams WHERE id = {RANGERS}")
    assert {"Rangers", "New York R", "New York Rangers"} == set(rangers)
    islanders = await _scalar(gate, f"SELECT alternate_names FROM teams WHERE id = {ISLANDERS}")
    assert {"Islanders", "New York I", "New York Islanders"} == set(islanders)
    assert "New York" not in islanders
    legacy = (await gate.execute(text(
        "SELECT source_id, team_id FROM team_identity_mapping "
        "WHERE source = 'legacy_slug' ORDER BY source_id"
    ))).all()
    assert [tuple(r) for r in legacy] == [("new-york-i", ISLANDERS), ("new-york-r", RANGERS)]
    nj = (await gate.execute(text(f"SELECT * FROM teams WHERE id = {NEW_JERSEY}"))).mappings().one()
    assert nj["name"] == "New Jersey"
    for c in ("espn_id", "alternate_names", "logo_url_small", "abbreviation", "current_record", "location"):
        assert nj[c] is None, c

    # THE SHIP: the search route's own filter and rank lead with the real club,
    # and no duplicate or borrowed-identity row answers either query.
    assert await _search(gate, "rangers") == [RANGERS]
    assert await _search(gate, "islanders") == [ISLANDERS]


async def test_a_second_apply_is_a_no_op(gate):
    code, _ = await m.repair(gate, "apply")
    assert code == 0
    after = await _teams_snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 0
    assert "already applied" in lines[0]
    assert await _teams_snapshot(gate) == after


async def test_restore_puts_back_exactly_what_was_there(gate):
    before = await _teams_snapshot(gate)
    code, _ = await m.repair(gate, "apply")
    assert code == 0
    code, lines = await m.repair(gate, "restore")
    assert code == 0, lines
    assert await _teams_snapshot(gate) == before
    assert await _refs(gate) == BEFORE_REFS
    assert await _scalar(
        gate, "SELECT count(*) FROM team_identity_mapping WHERE source = 'legacy_slug'"
    ) == 0


async def test_restore_leaves_a_row_someone_moved_since(gate):
    code, _ = await m.repair(gate, "apply")
    assert code == 0
    await gate.execute(text(f"UPDATE futures_outcomes SET team_id = {DEVILS} WHERE id = {FO_R_PLAYER}"))
    await gate.commit()
    code, _ = await m.repair(gate, "restore")
    assert code == 0
    refs = await _refs(gate)
    assert refs["fo_player"] == DEVILS
    assert refs["fo_team"] == NEW_YORK_R


async def test_a_moved_mapping_refuses_and_writes_nothing(gate):
    await gate.execute(text(
        f"UPDATE team_identity_mapping SET team_id = {BLUE_JACKETS} WHERE id = {MAP_COLUMBUS}"
    ))
    await gate.commit()
    before = await _teams_snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 2
    assert "mapping" in lines[-1]
    assert await _teams_snapshot(gate) == before
    assert await _scalar(gate, "SELECT to_regclass(:t)", t=m.BACKUP_TEAMS) is None


async def test_a_moved_count_refuses_and_writes_nothing(gate):
    await gate.execute(text(
        "INSERT INTO futures_outcomes (id, market_id, external_id, name, team_id) VALUES "
        f"(69741399, 1, 'x', 'Igor Shesterkin', {NEW_YORK_R})"
    ))
    await gate.commit()
    before = await _teams_snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 2
    assert "population moved" in lines[-1] and str(NEW_YORK_R) in lines[-1]
    assert await _teams_snapshot(gate) == before


async def test_a_failure_mid_apply_rolls_back_everything(gate, monkeypatch):
    import app.utils.team_merge as tm

    real = tm._apply_merge
    calls = {"n": 0}

    async def flaky(session, canonical, stub, sport_key):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom on the second fold")
        return await real(session, canonical, stub, sport_key)

    monkeypatch.setattr(tm, "_apply_merge", flaky)
    before = await _teams_snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 1
    assert "ROLLED BACK" in lines[-1]
    assert await _teams_snapshot(gate) == before
    assert await _refs(gate) == BEFORE_REFS
