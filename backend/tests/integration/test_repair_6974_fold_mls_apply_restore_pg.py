"""#6974 — the MLS duplicate-club repair's apply, re-run and undo, against a real PostgreSQL.

The unit file drives the refusals with dicts. Everything that decides what the
repair actually DOES is SQL, and a stub would be the thing deciding its answers:

* ``team_merge._apply_merge`` per fold, followed by a DELETE whose own FK
  actions (``team_identity_mapping`` CASCADE, ``entities`` SET NULL) would
  silently destroy or orphan any reference the repoint missed;
* two duplicates folding into ONE club, whose aliases must union, not overwrite;
* the strip's ``SET col = NULL`` over the identity columns, and the alias edits;
* ``SELECT *`` backup and ``INSERT ... SELECT *`` restore of whole team rows,
  and an undo that moves back ONLY the rows it banked;
* and the thing the ship is: after the apply, the serve path's own name lookup
  (``routes/events.py::_dedupe_team_name_lookup``) paints each fixture's club
  from the club's row.

Built narrow, in a private schema, with the real foreign-key actions, so this
runs on the lane VM's Postgres 14 as well as in CI.
"""

import importlib.util
import json
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6974 "
            "fold apply/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_6974_pg", _SCRIPTS / "repair_6974_fold_mls_duplicate_clubs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

_GATE_SCHEMA = "fold_mls_gate_6974"

MLS = 69740101
# The clubs.
# Ids ordered as production's are: the lookup's last tie-break is the row id,
# and Inter Miami (2324) outranks Atlanta United (30), so MIAMI > ATLANTA here.
SOUNDERS, RSL, ATLANTA, MIAMI, TIMBERS = 69740001, 69740002, 69740003, 69740004, 69740005
# The duplicates: two fold into the Sounders, one into RSL.
SEATTLE, SEATTLE_FC, SALT_LAKE = 69740011, 69740012, 69740013
# A reserve club wearing the Timbers' identity.
TIMBERS_2 = 69740021
EV_SEA_RSL, EV_SEA_HOME, EV_OTHER = 69740201, 69740202, 69740203
FO_SALT_LAKE = 69740301
ENT_SOUNDERS, ENT_SEATTLE, ENT_SALT_LAKE = 69740401, 69740402, 69740403
MAP_SEATTLE, MAP_RSL_DUP = 69740501, 69740502

SEA_CREST = "https://a.espncdn.com/i/teamlogos/soccer/500/9726.png"
RSL_CREST = "https://a.espncdn.com/i/teamlogos/soccer/500/4771.png"
POR_CREST = "https://a.espncdn.com/i/teamlogos/soccer/500/9723.png"

FOLDS = (
    m.Fold(SEATTLE, "Seattle", SOUNDERS, "Seattle Sounders FC", "9726", (0, 1, 0, 1, 1, 0, 0)),
    m.Fold(SEATTLE_FC, "Seattle FC", SOUNDERS, "Seattle Sounders FC", "9726", (1, 0, 0, 0, 0, 0, 0)),
    m.Fold(SALT_LAKE, "Salt Lake", RSL, "Real Salt Lake", "4771", (1, 0, 1, 1, 1, 0, 0)),
)
STRIPS = (
    m.Strip(TIMBERS_2, "Portland Timbers 2", "9723", POR_CREST, ("Portland", "Portland Timbers")),
)
ALIAS_EDITS = (
    m.AliasEdit(MIAMI, "Inter Miami CF", ("Atlanta United FC", "Miami"), ("Miami",)),
)


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _team(id_, name, slug, espn, aliases, crest, record, color="#000000"):
    return (
        f"({id_}, {MLS}, '{name}', '{slug}', "
        + ("NULL" if espn is None else f"'{espn}'")
        + ", "
        + ("NULL" if aliases is None else f"'{json.dumps(aliases)}'")
        + f", '{crest}', '{crest}', '{crest}', '{color}', '#ffffff', 'ABC', '{record}', '{name}')"
    )


@pytest.fixture
async def gate(pg_session, monkeypatch):
    monkeypatch.setattr(m, "FOLDS", FOLDS)
    monkeypatch.setattr(m, "STRIPS", STRIPS)
    monkeypatch.setattr(m, "ALIAS_EDITS", ALIAS_EDITS)
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
        "abbreviation varchar(20), current_record varchar(20), location varchar(200), "
        "standings_data jsonb, standings_updated_at timestamptz)",
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
        # Production's two partial unique indexes — `_apply_merge`'s legacy-slug
        # INSERT is what they would abort.
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
            "INSERT INTO sports (id, key, name, active) VALUES "
            f"({MLS}, 'soccer_usa_mls', 'MLS', true)"
        ))
    teams = [
        _team(SOUNDERS, "Seattle Sounders FC", "seattle-sounders-fc", "9726",
              ["Seattle", "Sounders"], SEA_CREST, "7-8-9"),
        _team(RSL, "Real Salt Lake", "real-salt-lake", "4771", ["Salt Lake"], RSL_CREST, "8-5-12"),
        _team(MIAMI, "Inter Miami CF", "inter-miami-cf", "20232",
              ["Atlanta United FC", "Miami"], "https://x/20232.png", "12-10-4"),
        _team(ATLANTA, "Atlanta United FC", "atlanta-united-fc", "18418",
              ["Atlanta"], "https://x/18418.png", "7-5-14"),
        _team(TIMBERS, "Portland Timbers", "portland-timbers", "9723",
              ["Portland"], POR_CREST, "9-5-12"),
        # The duplicates each carry the club's full name as an alias — the reason
        # the name lookup has two same-league answers and picks them.
        _team(SEATTLE, "Seattle", "seattle-mls", "9726",
              ["Seattle Sounders FC", "Sounders"], SEA_CREST, "1-0-1"),
        _team(SEATTLE_FC, "Seattle FC", "seattle-fc", "9726",
              ["Seattle Sounders FC"], SEA_CREST, "0-1-0"),
        _team(SALT_LAKE, "Salt Lake", "salt-lake", "4771", ["Real Salt Lake"], RSL_CREST, "3-1-1"),
        _team(TIMBERS_2, "Portland Timbers 2", "portland-timbers-2-mls", "9723",
              ["Portland", "Portland Timbers"], POR_CREST, "4-2-8"),
    ]
    await s.execute(
        text(
            "INSERT INTO teams (id, sport_id, name, slug, espn_id, alternate_names, logo_url, "
            "logo_url_small, logo_url_large, primary_color, secondary_color, abbreviation, "
            "current_record, location) VALUES " + ", ".join(teams)
        )
    )
    await s.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, commence_time, "
            "status, home_team_id, away_team_id) VALUES "
            f"({EV_SEA_RSL}, {MLS}, 'Salt Lake', 'Seattle', '2026-03-01 00:30+00', 'closed', "
            f"{SALT_LAKE}, {SEATTLE}), "
            f"({EV_SEA_HOME}, {MLS}, 'Seattle FC', 'Atlanta United FC', '2026-03-08 00:30+00', "
            f"'closed', {SEATTLE_FC}, {ATLANTA}), "
            f"({EV_OTHER}, {MLS}, 'Seattle Sounders FC', 'Real Salt Lake', '2026-09-24 01:30+00', "
            f"'scheduled', {SOUNDERS}, {RSL})"
        )
    )
    await s.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, team_id) VALUES "
            f"({FO_SALT_LAKE}, 1, 'fo-salt-lake', 'Salt Lake', {SALT_LAKE})"
        )
    )
    # The Sounders already have an entity, so Seattle's goes NULL on the delete;
    # RSL has none, so Salt Lake's is repointed.
    await s.execute(
        text(
            "INSERT INTO entities (id, kind, canonical_name, source_team_id) VALUES "
            f"({ENT_SOUNDERS}, 'team', 'Seattle Sounders FC', {SOUNDERS}), "
            f"({ENT_SEATTLE}, 'team', 'Seattle', {SEATTLE}), "
            f"({ENT_SALT_LAKE}, 'team', 'Salt Lake', {SALT_LAKE})"
        )
    )
    await s.execute(
        text(
            "INSERT INTO team_identity_mapping (id, team_id, source, source_name, sport_key) VALUES "
            f"({MAP_SEATTLE}, {SEATTLE}, 'odds_api', 'Seattle Sounders FC', 'soccer_usa_mls'), "
            f"({MAP_RSL_DUP}, {SALT_LAKE}, 'odds_api', 'Real Salt Lake', 'soccer_usa_mls')"
        )
    )
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
    return {
        "ev_home": await _scalar(s, f"SELECT home_team_id FROM events WHERE id = {EV_SEA_RSL}"),
        "ev_away": await _scalar(s, f"SELECT away_team_id FROM events WHERE id = {EV_SEA_RSL}"),
        "ev_sea_fc": await _scalar(s, f"SELECT home_team_id FROM events WHERE id = {EV_SEA_HOME}"),
        "ev_other": await _scalar(s, f"SELECT home_team_id FROM events WHERE id = {EV_OTHER}"),
        "fo": await _scalar(s, f"SELECT team_id FROM futures_outcomes WHERE id = {FO_SALT_LAKE}"),
        "ent_seattle": await _scalar(s, f"SELECT source_team_id FROM entities WHERE id = {ENT_SEATTLE}"),
        "ent_salt": await _scalar(s, f"SELECT source_team_id FROM entities WHERE id = {ENT_SALT_LAKE}"),
        "map_seattle": await _scalar(s, f"SELECT team_id FROM team_identity_mapping WHERE id = {MAP_SEATTLE}"),
        "map_rsl": await _scalar(s, f"SELECT team_id FROM team_identity_mapping WHERE id = {MAP_RSL_DUP}"),
    }


BEFORE_REFS = {
    "ev_home": SALT_LAKE, "ev_away": SEATTLE, "ev_sea_fc": SEATTLE_FC, "ev_other": SOUNDERS,
    "fo": SALT_LAKE, "ent_seattle": SEATTLE, "ent_salt": SALT_LAKE,
    "map_seattle": SEATTLE, "map_rsl": SALT_LAKE,
}


async def _painted(s) -> dict[str, int | None]:
    """Which row the serve path's own name lookup paints for each fixture name."""
    from types import SimpleNamespace

    from app.routes.events import _dedupe_team_name_lookup, _team_for_event

    rows = (
        await s.execute(
            text(
                "SELECT t.*, sp.key AS sport_key FROM teams t JOIN sports sp ON sp.id = t.sport_id "
                "WHERE t.primary_color IS NOT NULL OR t.logo_url_small IS NOT NULL"
            )
        )
    ).mappings().all()
    snaps = [
        SimpleNamespace(**{**dict(r), "alternate_names": tuple(r["alternate_names"] or ())})
        for r in rows
    ]
    lookup = _dedupe_team_name_lookup(snaps)
    return {
        name: getattr(_team_for_event(lookup, name, "soccer_usa_mls"), "id", None)
        for name in ("Seattle Sounders FC", "Real Salt Lake", "Atlanta United FC", "Portland Timbers")
    }


async def test_before_the_repair_the_lookup_paints_the_duplicates(gate):
    # The control: the seeded shape reproduces production's defect, so the
    # after-assertion below cannot pass on a fixture that never had it.
    painted = await _painted(gate)
    assert painted["Seattle Sounders FC"] in (SEATTLE, SEATTLE_FC)
    assert painted["Real Salt Lake"] == SALT_LAKE
    assert painted["Atlanta United FC"] == MIAMI
    assert painted["Portland Timbers"] == TIMBERS_2


async def test_dry_run_writes_nothing(gate):
    before = await _teams_snapshot(gate)
    code, lines = await m.repair(gate, "dry")
    assert code == 0, lines
    assert await _teams_snapshot(gate) == before
    assert await _refs(gate) == BEFORE_REFS
    assert await _scalar(gate, "SELECT to_regclass(:t)", t=m.BACKUP_TEAMS) is None


async def test_apply_folds_strips_and_paints_every_club_from_its_own_row(gate):
    code, lines = await m.repair(gate, "apply")
    assert code == 0, lines

    for dup in (SEATTLE, SEATTLE_FC, SALT_LAKE):
        assert await _scalar(gate, f"SELECT count(*) FROM teams WHERE id = {dup}") == 0
    assert await _refs(gate) == {
        "ev_home": RSL, "ev_away": SOUNDERS, "ev_sea_fc": SOUNDERS, "ev_other": SOUNDERS,
        "fo": RSL,
        # One entity per team: the Sounders already had one, so Seattle's went
        # NULL on the delete; RSL had none, so Salt Lake's was repointed.
        "ent_seattle": None, "ent_salt": RSL,
        "map_seattle": SOUNDERS, "map_rsl": RSL,
    }
    # Two duplicates into one club: aliases UNION.
    sounders = await _scalar(gate, f"SELECT alternate_names FROM teams WHERE id = {SOUNDERS}")
    assert {"Seattle", "Sounders", "Seattle FC"} <= set(sounders)
    # The old URLs open the club.
    legacy = (
        await gate.execute(
            text(
                "SELECT source_id, team_id FROM team_identity_mapping "
                "WHERE source = 'legacy_slug' ORDER BY source_id"
            )
        )
    ).all()
    assert [tuple(r) for r in legacy] == [
        ("salt-lake", RSL), ("seattle-fc", SOUNDERS), ("seattle-mls", SOUNDERS)
    ]
    # The reserve club keeps its name and loses the first team's identity.
    t2 = (await gate.execute(text(f"SELECT * FROM teams WHERE id = {TIMBERS_2}"))).mappings().one()
    assert t2["name"] == "Portland Timbers 2"
    assert all(t2[c] is None for c in m.STRIP_FIELDS)
    # Named, not read off STRIP_FIELDS: a field dropped from that tuple must fail here.
    for c in ("espn_id", "alternate_names", "logo_url_small", "abbreviation", "current_record", "location"):
        assert t2[c] is None, c
    miami = await _scalar(gate, f"SELECT alternate_names FROM teams WHERE id = {MIAMI}")
    assert miami == ["Miami"]

    # THE SHIP: every fixture name now paints the club's own row.
    assert await _painted(gate) == {
        "Seattle Sounders FC": SOUNDERS,
        "Real Salt Lake": RSL,
        "Atlanta United FC": ATLANTA,
        "Portland Timbers": TIMBERS,
    }


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
    # After the fold, another writer rebinds the away side to a third club.
    await gate.execute(text(f"UPDATE events SET away_team_id = {ATLANTA} WHERE id = {EV_SEA_RSL}"))
    await gate.commit()
    code, _ = await m.repair(gate, "restore")
    assert code == 0
    refs = await _refs(gate)
    assert refs["ev_away"] == ATLANTA
    assert refs["ev_home"] == SALT_LAKE


async def test_a_moved_count_refuses_and_writes_nothing(gate):
    await gate.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, team_id) VALUES "
            f"(69740399, 1, 'fo-seattle', 'Seattle', {SEATTLE})"
        )
    )
    await gate.commit()
    before = await _teams_snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 2
    assert "population moved" in lines[-1] and str(SEATTLE) in lines[-1]
    assert await _teams_snapshot(gate) == before
    assert await _scalar(gate, "SELECT to_regclass(:t)", t=m.BACKUP_TEAMS) is None


async def test_an_existing_legacy_slug_refuses_before_the_insert_can_abort(gate):
    await gate.execute(
        text(
            "INSERT INTO team_identity_mapping (team_id, source, source_id, source_name, "
            "sport_key) VALUES "
            f"({RSL}, 'legacy_slug', 'salt-lake', 'Salt Lake', 'soccer_usa_mls')"
        )
    )
    await gate.commit()
    code, lines = await m.repair(gate, "apply")
    assert code == 2
    assert "legacy slug already mapped" in lines[-1]
    assert await _scalar(gate, f"SELECT count(*) FROM teams WHERE id = {SALT_LAKE}") == 1


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
