"""#6974 LAFC residual — the duplicate-club repair's apply, re-run and undo, against a real PostgreSQL.

The unit file drives the refusals with dicts. What the repair DOES is SQL:

* the Odds API "FC Cincinnati" mapping moved to FC Cincinnati BEFORE the fold,
  so ``_apply_merge`` does not hand it to LAFC (and the delete's CASCADE does not
  destroy it);
* the EPL and market-title mappings banked whole and deleted, while the real
  LAFC mapping rides the fold;
* ``team_merge._apply_merge`` with the Galaxy's names kept off LAFC's aliases;
* ``SELECT *`` backups and an undo that puts back ONLY what it banked;
* and the ship: the search route's own Teams filter and rank
  (``routes/events.py::_build_team_search_filter`` / ``_team_search_rank``)
  answer "lafc" with ONE club, and that club's row carries the upcoming game
  that only the duplicate named.

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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6974 LAFC "
            "fold apply/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_6974_lafc_pg", _SCRIPTS / "repair_6974_fold_lafc_duplicate_club.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

_GATE_SCHEMA = "fold_lafc_gate_6974"
MLS_KEY = "soccer_usa_mls"

MLS = 69742101
LAFC, LOS_ANGELES_FC, CINCY, GALAXY, VANCOUVER, SEATTLE = (
    69742001, 69742002, 69742003, 69742004, 69742005, 69742006,
)
EV_TWIN_ESPN, EV_TWIN_BOOK, EV_OCT11, EV_GALAXY = 69742201, 69742202, 69742203, 69742204
ENT_LAFC, ENT_DUP = 69742401, 69742402
MAP_CINCY, MAP_EPL, MAP_TITLE, MAP_KEEP, MAP_ESPN = (
    69742501, 69742502, 69742503, 69742504, 69742505,
)

CREST = "https://a.espncdn.com/i/teamlogos/soccer/500/18966.png"

FOLDS = (
    m.Fold(LOS_ANGELES_FC, "Los Angeles FC", LAFC, "LAFC", "18966", (1, 1, 0, 1, 4, 0, 0),
           ("Galaxy", "LA Galaxy", "LAFC"), drop_aliases=("Galaxy", "LA Galaxy")),
)
MAPPING_EDITS = (
    m.MappingEdit(MAP_CINCY, "odds_api", "FC Cincinnati", LOS_ANGELES_FC, CINCY, "FC Cincinnati"),
)
MAPPING_DELETES = (
    m.MappingRow(MAP_EPL, "kalshi", "Houston", "soccer_epl"),
    m.MappingRow(MAP_TITLE, "polymarket", "Los Angeles FC - Exact Score", MLS_KEY),
)
MAPPING_KEEPS = (m.MappingRow(MAP_KEEP, "kalshi", "Los Angeles FC", MLS_KEY),)


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _team(id_, name, slug, espn, abbr, aliases, record):
    return (
        f"({id_}, {MLS}, '{name}', '{slug}', "
        + ("NULL" if espn is None else f"'{espn}'")
        + ", "
        + ("NULL" if aliases is None else f"'{json.dumps(aliases)}'")
        + f", NULL, '{CREST}', '{CREST}', '#000000', '#c39e6d', "
        + ("NULL" if abbr is None else f"'{abbr}'")
        + f", '{record}', 'Los Angeles')"
    )


@pytest.fixture
async def gate(pg_session, monkeypatch):
    monkeypatch.setattr(m, "FOLDS", FOLDS)
    monkeypatch.setattr(m, "MAPPING_EDITS", MAPPING_EDITS)
    monkeypatch.setattr(m, "MAPPING_DELETES", MAPPING_DELETES)
    monkeypatch.setattr(m, "MAPPING_KEEPS", MAPPING_KEEPS)
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
        f"INSERT INTO sports (id, key, name, active) VALUES ({MLS}, '{MLS_KEY}', 'MLS', true)"
    ))
    teams = [
        # Production's shape: the club's row is named "LAFC" with the full name as
        # its alias; the duplicate is named in full, wears LAFC's ESPN id, crest and
        # abbreviation, and carries the Galaxy's names.
        _team(LAFC, "LAFC", "lafc", "18966", "LAFC", ["Los Angeles FC"], "11-8-9"),
        _team(LOS_ANGELES_FC, "Los Angeles FC", "los-angeles-fc", "18966", "LAFC",
              ["Galaxy", "LA Galaxy", "LAFC"], "11-8-8"),
        _team(CINCY, "FC Cincinnati", "fc-cincinnati", "18267", "CIN",
              ["Cincinnati", "FC Cincinnati"], "14-7-6"),
        _team(GALAXY, "LA Galaxy", "la-galaxy", "187", "LA", ["Galaxy"], "7-15-5"),
        _team(VANCOUVER, "Vancouver Whitecaps", "vancouver-whitecaps", "9727", "VAN",
              ["Whitecaps"], "16-6-5"),
        _team(SEATTLE, "Seattle Sounders FC", "seattle-sounders-fc", "9726", "SEA",
              ["Sounders"], "12-9-6"),
    ]
    await s.execute(text(
        "INSERT INTO teams (id, sport_id, name, slug, espn_id, alternate_names, logo_url, "
        "logo_url_small, logo_url_large, primary_color, secondary_color, abbreviation, "
        "current_record, location) VALUES " + ", ".join(teams)
    ))
    await s.execute(text(
        "INSERT INTO events (id, sport_id, home_team_name, away_team_name, commence_time, "
        "status, home_team_id, away_team_id) VALUES "
        # One game, two rows: ESPN's names the club, the sportsbook's the duplicate.
        f"({EV_TWIN_ESPN}, {MLS}, 'Seattle Sounders FC', 'LAFC', '2026-09-27 00:30+00', "
        f"'completed', {SEATTLE}, {LAFC}), "
        f"({EV_TWIN_BOOK}, {MLS}, 'Seattle Sounders FC', 'Los Angeles FC', '2026-09-27 00:30+00', "
        f"'completed', {SEATTLE}, {LOS_ANGELES_FC}), "
        # The game the club's page is missing: it names only the duplicate.
        f"({EV_OCT11}, {MLS}, 'Los Angeles FC', 'Vancouver Whitecaps', '2026-10-11 02:30+00', "
        f"'scheduled', {LOS_ANGELES_FC}, {VANCOUVER}), "
        f"({EV_GALAXY}, {MLS}, 'LA Galaxy', 'Vancouver Whitecaps', '2026-10-04 02:30+00', "
        f"'scheduled', {GALAXY}, {VANCOUVER})"
    ))
    await s.execute(text(
        "INSERT INTO entities (id, kind, canonical_name, source_team_id) VALUES "
        f"({ENT_LAFC}, 'team', 'LAFC', {LAFC}), "
        f"({ENT_DUP}, 'team', 'Los Angeles FC', {LOS_ANGELES_FC})"
    ))
    await s.execute(text(
        "INSERT INTO team_identity_mapping (id, team_id, source, source_id, source_name, sport_key) "
        "VALUES "
        f"({MAP_CINCY}, {LOS_ANGELES_FC}, 'odds_api', NULL, 'FC Cincinnati', '{MLS_KEY}'), "
        f"({MAP_EPL}, {LOS_ANGELES_FC}, 'kalshi', NULL, 'Houston', 'soccer_epl'), "
        f"({MAP_TITLE}, {LOS_ANGELES_FC}, 'polymarket', NULL, 'Los Angeles FC - Exact Score', "
        f"'{MLS_KEY}'), "
        f"({MAP_KEEP}, {LOS_ANGELES_FC}, 'kalshi', NULL, 'Los Angeles FC', '{MLS_KEY}'), "
        f"({MAP_ESPN}, {LAFC}, 'espn', '18966', 'LAFC', '{MLS_KEY}')"
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


async def _mappings_snapshot(s):
    rows = (await s.execute(text(
        "SELECT id, team_id, source, source_id, source_name, sport_key "
        "FROM team_identity_mapping ORDER BY id"
    ))).all()
    return [tuple(r) for r in rows]


async def _refs(s):
    one = lambda sql: _scalar(s, sql)  # noqa: E731
    return {
        "twin_espn": await one(f"SELECT away_team_id FROM events WHERE id = {EV_TWIN_ESPN}"),
        "twin_book": await one(f"SELECT away_team_id FROM events WHERE id = {EV_TWIN_BOOK}"),
        "oct11": await one(f"SELECT home_team_id FROM events WHERE id = {EV_OCT11}"),
        "ent_dup": await one(f"SELECT source_team_id FROM entities WHERE id = {ENT_DUP}"),
        "map_cincy": await one(f"SELECT team_id FROM team_identity_mapping WHERE id = {MAP_CINCY}"),
        "map_keep": await one(f"SELECT team_id FROM team_identity_mapping WHERE id = {MAP_KEEP}"),
    }


BEFORE_REFS = {
    "twin_espn": LAFC, "twin_book": LOS_ANGELES_FC, "oct11": LOS_ANGELES_FC,
    "ent_dup": LOS_ANGELES_FC, "map_cincy": LOS_ANGELES_FC, "map_keep": LOS_ANGELES_FC,
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


async def _club_games(s, team_id: int) -> set[int]:
    """The team page's id arm (``routes/teams.py``): home or away names the club."""
    res = await s.execute(
        text("SELECT id FROM events WHERE home_team_id = :t OR away_team_id = :t"), {"t": team_id}
    )
    return {r[0] for r in res}


async def test_before_the_repair_search_shows_two_lafc_cards(gate):
    # The control: the seeded shape reproduces production's defect.
    assert {LAFC, LOS_ANGELES_FC} <= set(await _search(gate, "lafc"))
    assert LOS_ANGELES_FC in await _search(gate, "galaxy")
    assert EV_OCT11 not in await _club_games(gate, LAFC)


async def test_dry_run_writes_nothing(gate):
    before = await _teams_snapshot(gate)
    maps = await _mappings_snapshot(gate)
    code, lines = await m.repair(gate, "dry")
    assert code == 0, lines
    assert await _teams_snapshot(gate) == before
    assert await _mappings_snapshot(gate) == maps
    assert await _refs(gate) == BEFORE_REFS
    assert await _scalar(gate, "SELECT to_regclass(:t)", t=m.BACKUP_TEAMS) is None


async def test_apply_repoints_deletes_folds_and_search_shows_one_lafc(gate):
    code, lines = await m.repair(gate, "apply")
    assert code == 0, lines

    assert await _scalar(gate, f"SELECT count(*) FROM teams WHERE id = {LOS_ANGELES_FC}") == 0
    assert await _refs(gate) == {
        "twin_espn": LAFC, "twin_book": LAFC, "oct11": LAFC,
        # LAFC already had an entity: the duplicate's goes NULL, never a second bridge.
        "ent_dup": None,
        # The Odds API's "FC Cincinnati" is FC Cincinnati — not LAFC, and not
        # cascaded away with the deleted row.
        "map_cincy": CINCY,
        "map_keep": LAFC,
    }
    for gone in (MAP_EPL, MAP_TITLE):
        assert await _scalar(gate, f"SELECT count(*) FROM team_identity_mapping WHERE id = {gone}") == 0
    banked = (await gate.execute(text(
        f"SELECT id, team_id, source_name FROM {m.BACKUP_MAPPINGS} ORDER BY id"
    ))).all()
    assert [tuple(r) for r in banked] == [
        (MAP_EPL, LOS_ANGELES_FC, "Houston"),
        (MAP_TITLE, LOS_ANGELES_FC, "Los Angeles FC - Exact Score"),
    ]
    aliases = await _scalar(gate, f"SELECT alternate_names FROM teams WHERE id = {LAFC}")
    assert {"Los Angeles FC", "LAFC"} == set(aliases)
    legacy = (await gate.execute(text(
        "SELECT source_id, team_id FROM team_identity_mapping WHERE source = 'legacy_slug'"
    ))).all()
    assert [tuple(r) for r in legacy] == [("los-angeles-fc", LAFC)]

    # THE SHIP: one LAFC card, whichever name the reader types, and the club's
    # page reaches the Oct 11 game. The Galaxy answers "galaxy" alone.
    assert await _search(gate, "lafc") == [LAFC]
    assert await _search(gate, "los angeles fc") == [LAFC]
    assert await _search(gate, "galaxy") == [GALAXY]
    assert {EV_TWIN_ESPN, EV_TWIN_BOOK, EV_OCT11} <= await _club_games(gate, LAFC)


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
    maps = await _mappings_snapshot(gate)
    code, _ = await m.repair(gate, "apply")
    assert code == 0
    code, lines = await m.repair(gate, "restore")
    assert code == 0, lines
    assert await _teams_snapshot(gate) == before
    assert await _mappings_snapshot(gate) == maps
    assert await _refs(gate) == BEFORE_REFS


async def test_restore_keeps_a_mapping_a_writer_re_registered_since(gate):
    code, _ = await m.repair(gate, "apply")
    assert code == 0
    # After the fold a resolver fuzzy-matches the title onto the club and
    # registers it again; the undo must not collide with (or clobber) that row.
    await gate.execute(text(
        "INSERT INTO team_identity_mapping (team_id, source, source_name, sport_key) VALUES "
        f"({LAFC}, 'polymarket', 'Los Angeles FC - Exact Score', '{MLS_KEY}')"
    ))
    await gate.commit()
    code, lines = await m.repair(gate, "restore")
    assert code == 0, lines
    titled = (await gate.execute(text(
        "SELECT team_id FROM team_identity_mapping "
        "WHERE source_name = 'Los Angeles FC - Exact Score'"
    ))).all()
    assert [r[0] for r in titled] == [LAFC]
    assert await _scalar(gate, f"SELECT team_id FROM team_identity_mapping WHERE id = {MAP_EPL}") == LOS_ANGELES_FC


async def test_restore_leaves_a_row_someone_moved_since(gate):
    code, _ = await m.repair(gate, "apply")
    assert code == 0
    await gate.execute(text(f"UPDATE events SET home_team_id = {GALAXY} WHERE id = {EV_OCT11}"))
    await gate.commit()
    code, _ = await m.repair(gate, "restore")
    assert code == 0
    refs = await _refs(gate)
    assert refs["oct11"] == GALAXY
    assert refs["twin_book"] == LOS_ANGELES_FC


async def test_a_moved_mapping_refuses_and_writes_nothing(gate):
    await gate.execute(text(
        f"UPDATE team_identity_mapping SET team_id = {LAFC} WHERE id = {MAP_TITLE}"
    ))
    await gate.commit()
    before = await _teams_snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 2
    assert "mapping" in lines[-1]
    assert await _teams_snapshot(gate) == before
    assert await _scalar(gate, "SELECT to_regclass(:t)", t=m.BACKUP_TEAMS) is None


async def test_a_new_mapping_on_the_duplicate_refuses_and_writes_nothing(gate):
    # A writer registered something between the read and the run: nothing may
    # ride the fold that was not read.
    await gate.execute(text(
        "INSERT INTO team_identity_mapping (team_id, source, source_name, sport_key) VALUES "
        f"({LOS_ANGELES_FC}, 'polymarket', 'Los Angeles FC - Total Corners', '{MLS_KEY}')"
    ))
    await gate.commit()
    before = await _teams_snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 2
    assert "population moved" in lines[-1] and "team_identity_mapping" in lines[-1]
    assert await _teams_snapshot(gate) == before


async def test_a_failure_mid_apply_rolls_back_everything(gate, monkeypatch):
    import app.utils.team_merge as tm

    async def boom(session, canonical, stub, sport_key):
        raise RuntimeError("boom in the fold")

    monkeypatch.setattr(tm, "_apply_merge", boom)
    before = await _teams_snapshot(gate)
    maps = await _mappings_snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 1
    assert "ROLLED BACK" in lines[-1]
    assert await _teams_snapshot(gate) == before
    # The repoint and the deletes ran before the fold; the rollback undoes them too.
    assert await _mappings_snapshot(gate) == maps
    assert await _refs(gate) == BEFORE_REFS
