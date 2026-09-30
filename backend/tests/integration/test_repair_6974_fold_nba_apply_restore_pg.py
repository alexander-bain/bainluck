"""#6974 NBA residual — the duplicate-club repair's apply, re-run and undo, against a real PostgreSQL.

The unit file drives the refusals with dicts. What the repair DOES is SQL:

* the Kalshi "Brooklyn" mapping moved to the Nets BEFORE the fold, so
  ``_apply_merge`` does not hand it to the Blazers (and the delete's CASCADE does
  not destroy it);
* a market-title mapping banked whole and deleted;
* legs that are another club's moved to that club, and a college leg unlinked,
  BEFORE the fold — so the fold carries only the duplicate's own club's legs;
* ``team_merge._apply_merge`` folding each duplicate's name into the club's aliases;
* ``SELECT *`` backups and an undo that puts back ONLY what it banked;
* and the ship: the #9617 league step (``team_linking._match_in_ticker_league``),
  given the teams as the table now holds them, refuses Kalshi's "Detroit" and
  "Portland" before the repair and binds each to the real club after it. The
  search route's own Teams filter answers "pistons" and "clippers" with ONE club.

Built narrow, in a private schema with the real foreign-key actions, so it runs
on the lane VM's Postgres 14 as well as in CI.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6974 NBA "
            "fold apply/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_6974_nba_pg", _SCRIPTS / "repair_6974_fold_nba_duplicate_clubs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

_GATE_SCHEMA = "fold_nba_gate_6974"
NBA_KEY, NHL_KEY = "basketball_nba", "icehockey_nhl"
NBA, NHL = 69743101, 69743102

(PISTONS, DETROIT, BLAZERS, PORTLAND, CLIPPERS, LAC, LAKERS, SPURS, NETS, KINGS, OKC) = (
    69743001, 69743002, 69743003, 69743004, 69743005, 69743006, 69743007, 69743008,
    69743009, 69743010, 69743011,
)
EV_DET, EV_POR = 69743201, 69743202
ENT_PISTONS, ENT_DET = 69743401, 69743402
MAP_BKN, MAP_TITLE, MAP_ESPN = 69743501, 69743502, 69743503
(LEG_DET_CLUB, LEG_HARRIS, LEG_MERCY, LEG_POR_CLUB, LEG_LAC_CLUB, LEG_LAL, LEG_KINGS) = (
    69743601, 69743602, 69743603, 69743604, 69743605, 69743606, 69743607,
)
# Kalshi's open 2027 title legs: unbound, because each city has two NBA rows.
OPEN_27 = {69743701: "Detroit", 69743702: "Portland", 69743703: "Los Angeles C",
           69743704: "Los Angeles L"}

FOLDS = (
    m.Fold(DETROIT, "Detroit", PISTONS, "Detroit Pistons", "8", (0, 1, 3, 1, 1, 0, 0),
           ("Detroit Pistons", "Pistons")),
    m.Fold(PORTLAND, "Portland", BLAZERS, "Portland Trail Blazers", "22", (1, 0, 1, 0, 1, 0, 0),
           ("Trail Blazers", "Portland Trail Blazers")),
    m.Fold(LAC, "Los Angeles C", CLIPPERS, "Los Angeles Clippers", "12", (0, 0, 3, 0, 0, 0, 0),
           ("Clippers", "LA Clippers")),
)
TARGETS = (
    m.Target(LAKERS, "Los Angeles Lakers", NBA_KEY),
    m.Target(KINGS, "Los Angeles Kings", NHL_KEY),
    m.Target(SPURS, "San Antonio Spurs", NBA_KEY),
    m.Target(NETS, "Brooklyn Nets", NBA_KEY),
)
MAPPING_EDITS = (m.MappingEdit(MAP_BKN, "kalshi", "Brooklyn", PORTLAND, NETS),)
MAPPING_DELETES = (m.MappingRow(MAP_TITLE, "kalshi", "Game 1: Orlando", DETROIT),)
LEG_EDITS = (
    m.LegEdit(LEG_HARRIS, "Tobias Harris", DETROIT, SPURS, "San Antonio Opening Game Starters"),
    m.LegEdit(LEG_MERCY, "Detroit", DETROIT, None, "Bellarmine vs Detroit"),
    m.LegEdit(LEG_LAL, "Los Angeles L", LAC, LAKERS, "Los Angeles C at Los Angeles L"),
    m.LegEdit(LEG_KINGS, "Los Angeles Kings", LAC, KINGS, "Series Winner: Vegas vs Colorado"),
)


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _team(id_, sport, name, slug, espn, abbr, aliases, record):
    crest = f"https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/{abbr.lower()}.png"
    return (
        f"({id_}, {sport}, '{name}', '{slug}', '{espn}', '{json.dumps(aliases)}', NULL, "
        f"'{crest}', '{crest}', '#000000', '#ffffff', '{abbr}', '{record}', NULL)"
    )


@pytest.fixture
async def gate(pg_session, monkeypatch):
    monkeypatch.setattr(m, "FOLDS", FOLDS)
    monkeypatch.setattr(m, "TARGETS", TARGETS)
    monkeypatch.setattr(m, "MAPPING_EDITS", MAPPING_EDITS)
    monkeypatch.setattr(m, "MAPPING_DELETES", MAPPING_DELETES)
    monkeypatch.setattr(m, "LEG_EDITS", LEG_EDITS)
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
        "INSERT INTO sports (id, key, name, active) VALUES "
        f"({NBA}, '{NBA_KEY}', 'NBA', true), ({NHL}, '{NHL_KEY}', 'NHL', true)"
    ))
    teams = [
        # Production's shape: each duplicate is named by its city (Kalshi's word),
        # wears the club's ESPN id, crest and abbreviation, and has the club's
        # full name as an alias.
        _team(PISTONS, NBA, "Detroit Pistons", "detroit-pistons", "8", "DET",
              ["Pistons", "Detroit"], "60-22"),
        _team(DETROIT, NBA, "Detroit", "detroit", "8", "DET",
              ["Detroit Pistons", "Pistons"], "60-22"),
        _team(BLAZERS, NBA, "Portland Trail Blazers", "portland-trail-blazers", "22", "POR",
              ["Trail Blazers", "Portland"], "42-40"),
        _team(PORTLAND, NBA, "Portland", "portland-nba", "22", "POR",
              ["Trail Blazers", "Portland Trail Blazers"], "36-37"),
        _team(CLIPPERS, NBA, "Los Angeles Clippers", "los-angeles-clippers", "12", "LAC",
              ["LA", "Clippers", "LA Clippers"], "42-40"),
        _team(LAC, NBA, "Los Angeles C", "los-angeles-c", "12", "LAC",
              ["Clippers", "LA Clippers"], "39-36"),
        _team(LAKERS, NBA, "Los Angeles Lakers", "los-angeles-lakers", "13", "LAL",
              ["Los Angeles", "Lakers"], "50-32"),
        _team(SPURS, NBA, "San Antonio Spurs", "san-antonio-spurs", "24", "SA",
              ["Spurs", "San Antonio"], "62-20"),
        _team(NETS, NBA, "Brooklyn Nets", "brooklyn-nets", "17", "BKN",
              ["Nets", "Brooklyn", "Brooklyn Nets"], "20-62"),
        _team(OKC, NBA, "Oklahoma City Thunder", "oklahoma-city-thunder", "25", "OKC",
              ["Thunder", "Oklahoma City"], "64-18"),
        _team(KINGS, NHL, "Los Angeles Kings", "los-angeles-kings", "8", "LA",
              ["Los Angeles Kings", "Kings", "Los Angeles"], "40-30-12"),
    ]
    await s.execute(text(
        "INSERT INTO teams (id, sport_id, name, slug, espn_id, alternate_names, logo_url, "
        "logo_url_small, logo_url_large, primary_color, secondary_color, abbreviation, "
        "current_record, location) VALUES " + ", ".join(teams)
    ))
    await s.execute(text(
        "INSERT INTO events (id, sport_id, home_team_name, away_team_name, commence_time, "
        "status, home_team_id, away_team_id) VALUES "
        f"({EV_DET}, {NBA}, 'Oklahoma City', 'Detroit', '2026-03-31 01:30+00', 'closed', "
        f"{OKC}, {DETROIT}), "
        f"({EV_POR}, {NBA}, 'Portland', 'Brooklyn', '2026-03-24 02:00+00', 'closed', "
        f"{PORTLAND}, {NETS})"
    ))
    legs = [
        (LEG_DET_CLUB, "Detroit", DETROIT),
        (LEG_HARRIS, "Tobias Harris", DETROIT),
        (LEG_MERCY, "Detroit", DETROIT),
        (LEG_POR_CLUB, "Portland", PORTLAND),
        (LEG_LAC_CLUB, "Los Angeles C", LAC),
        (LEG_LAL, "Los Angeles L", LAC),
        (LEG_KINGS, "Los Angeles Kings", LAC),
    ] + [(oid, name, None) for oid, name in OPEN_27.items()]
    await s.execute(text(
        "INSERT INTO futures_outcomes (id, market_id, external_id, name, team_id) VALUES "
        + ", ".join(
            f"({oid}, 1, 'x{oid}', '{name}', {'NULL' if tid is None else tid})"
            for oid, name, tid in legs
        )
    ))
    await s.execute(text(
        "INSERT INTO entities (id, kind, canonical_name, source_team_id) VALUES "
        f"({ENT_PISTONS}, 'team', 'Detroit Pistons', {PISTONS}), "
        f"({ENT_DET}, 'team', 'Detroit', {DETROIT})"
    ))
    await s.execute(text(
        "INSERT INTO team_identity_mapping (id, team_id, source, source_id, source_name, sport_key) "
        "VALUES "
        f"({MAP_BKN}, {PORTLAND}, 'kalshi', NULL, 'Brooklyn', '{NBA_KEY}'), "
        f"({MAP_TITLE}, {DETROIT}, 'kalshi', NULL, 'Game 1: Orlando', '{NBA_KEY}'), "
        f"({MAP_ESPN}, {PISTONS}, 'espn', '8', 'Detroit Pistons', '{NBA_KEY}')"
    ))
    await s.commit()
    yield s
    await s.rollback()
    await s.execute(text("SET search_path TO public"))
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.commit()


async def _scalar(s, sql, **params):
    return (await s.execute(text(sql), params)).scalar_one()


async def _snapshot(s):
    out = {}
    for table, order in (
        ("teams", "id"), ("team_identity_mapping", "id"), ("futures_outcomes", "id"),
        ("events", "id"), ("entities", "id"),
    ):
        rows = (await s.execute(text(f"SELECT * FROM {table} ORDER BY {order}"))).mappings().all()
        out[table] = [
            {k: v for k, v in r.items() if k not in ("created_at", "updated_at")} for r in rows
        ]
    return out


async def _team_of(s, outcome_id):
    return await _scalar(s, f"SELECT team_id FROM futures_outcomes WHERE id = {outcome_id}")


async def _league_step(s, name: str, ticker: str = "KXNBA-27"):
    """What the #9617 step binds a Kalshi outcome to, given the teams as stored."""
    from app.tasks.team_linking import _match_in_ticker_league

    rows = (await s.execute(text(
        "SELECT t.id, t.name, t.alternate_names, sp.key FROM teams t "
        "JOIN sports sp ON sp.id = t.sport_id"
    ))).all()
    teams = [
        {"id": r.id, "name": r.name, "alternate_names": r.alternate_names or [], "sport_key": r.key}
        for r in rows
    ]
    outcome = SimpleNamespace(
        name=name, market=SimpleNamespace(source="kalshi", external_id=ticker)
    )
    return _match_in_ticker_league(outcome, teams)


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


async def test_before_the_repair_kalshi_cities_bind_to_nothing(gate):
    # The control: the seeded shape reproduces production's refusal.
    for name in ("Detroit", "Portland"):
        assert await _league_step(gate, name) is None, name
    assert {PISTONS, DETROIT} <= set(await _search(gate, "pistons"))
    assert {CLIPPERS, LAC} <= set(await _search(gate, "clippers"))


async def test_dry_run_writes_nothing(gate):
    before = await _snapshot(gate)
    code, lines = await m.repair(gate, "dry")
    assert code == 0, lines
    assert await _snapshot(gate) == before
    assert await _scalar(gate, "SELECT to_regclass(:t)", t=m.BACKUP_TEAMS) is None


async def test_apply_corrects_folds_and_kalshi_binds_each_city_to_its_club(gate):
    code, lines = await m.repair(gate, "apply")
    assert code == 0, lines

    for gone in (DETROIT, PORTLAND, LAC):
        assert await _scalar(gate, f"SELECT count(*) FROM teams WHERE id = {gone}") == 0
    # The club's own legs rode the fold; the others went to their own club first.
    assert await _team_of(gate, LEG_DET_CLUB) == PISTONS
    assert await _team_of(gate, LEG_POR_CLUB) == BLAZERS
    assert await _team_of(gate, LEG_LAC_CLUB) == CLIPPERS
    assert await _team_of(gate, LEG_HARRIS) == SPURS
    assert await _team_of(gate, LEG_LAL) == LAKERS
    assert await _team_of(gate, LEG_KINGS) == KINGS
    assert await _team_of(gate, LEG_MERCY) is None
    assert await _scalar(gate, f"SELECT away_team_id FROM events WHERE id = {EV_DET}") == PISTONS
    assert await _scalar(gate, f"SELECT home_team_id FROM events WHERE id = {EV_POR}") == BLAZERS
    # The Pistons already had an entity: the duplicate's goes NULL, never a second bridge.
    assert await _scalar(gate, f"SELECT source_team_id FROM entities WHERE id = {ENT_DET}") is None
    # Kalshi's "Brooklyn" is the Nets — not the Blazers, and not cascaded away.
    assert await _scalar(gate, f"SELECT team_id FROM team_identity_mapping WHERE id = {MAP_BKN}") == NETS
    assert await _scalar(gate, f"SELECT count(*) FROM team_identity_mapping WHERE id = {MAP_TITLE}") == 0
    banked = (await gate.execute(text(
        f"SELECT id, team_id, source_name FROM {m.BACKUP_MAPPINGS}"
    ))).all()
    assert [tuple(r) for r in banked] == [(MAP_TITLE, DETROIT, "Game 1: Orlando")]
    aliases = await _scalar(gate, f"SELECT alternate_names FROM teams WHERE id = {CLIPPERS}")
    assert "Los Angeles C" in aliases
    legacy = (await gate.execute(text(
        "SELECT source_id, team_id FROM team_identity_mapping WHERE source = 'legacy_slug' "
        "ORDER BY source_id"
    ))).all()
    assert [tuple(r) for r in legacy] == [
        ("detroit", PISTONS), ("los-angeles-c", CLIPPERS), ("portland-nba", BLAZERS),
    ]

    # THE SHIP: the league step now binds each Kalshi city to the real club,
    # on the champion ticker and the conference tickers alike.
    assert await _league_step(gate, "Detroit") == PISTONS
    assert await _league_step(gate, "Detroit", "KXNBAEAST-27") == PISTONS
    assert await _league_step(gate, "Portland") == BLAZERS
    assert await _league_step(gate, "Portland", "KXNBAWEST-27") == BLAZERS
    # Said, not implied: normalize_name reads "Los Angeles C" and "Los Angeles L"
    # as "los angeles", which the Lakers answer to too. No fold changes that.
    assert await _league_step(gate, "Los Angeles C") is None
    assert await _league_step(gate, "Los Angeles L") is None
    assert await _search(gate, "pistons") == [PISTONS]
    assert await _search(gate, "clippers") == [CLIPPERS]


async def test_a_second_apply_is_a_no_op(gate):
    code, _ = await m.repair(gate, "apply")
    assert code == 0
    after = await _snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 0
    assert "already applied" in lines[0]
    assert await _snapshot(gate) == after


async def test_restore_puts_back_exactly_what_was_there(gate):
    before = await _snapshot(gate)
    code, _ = await m.repair(gate, "apply")
    assert code == 0
    code, lines = await m.repair(gate, "restore")
    assert code == 0, lines
    assert await _snapshot(gate) == before


async def test_restore_leaves_a_leg_the_linker_bound_since(gate):
    code, _ = await m.repair(gate, "apply")
    assert code == 0
    # After the fold the linker binds the unlinked college leg, and a writer moves
    # the Harris leg; the undo leaves both where they now are.
    await gate.execute(text(f"UPDATE futures_outcomes SET team_id = {OKC} WHERE id = {LEG_MERCY}"))
    await gate.execute(text(f"UPDATE futures_outcomes SET team_id = {OKC} WHERE id = {LEG_HARRIS}"))
    await gate.commit()
    code, _ = await m.repair(gate, "restore")
    assert code == 0
    assert await _team_of(gate, LEG_MERCY) == OKC
    assert await _team_of(gate, LEG_HARRIS) == OKC
    assert await _team_of(gate, LEG_LAL) == LAC
    assert await _team_of(gate, LEG_DET_CLUB) == DETROIT


async def test_a_moved_leg_refuses_and_writes_nothing(gate):
    await gate.execute(text(f"UPDATE futures_outcomes SET team_id = {PISTONS} WHERE id = {LEG_HARRIS}"))
    await gate.commit()
    before = await _snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 2
    assert f"leg {LEG_HARRIS}" in lines[-1]
    assert await _snapshot(gate) == before
    assert await _scalar(gate, "SELECT to_regclass(:t)", t=m.BACKUP_TEAMS) is None


async def test_a_new_leg_on_a_duplicate_refuses_and_writes_nothing(gate):
    # A writer linked a leg between the read and the run: nothing may ride the
    # fold that was not read.
    await gate.execute(text(
        "INSERT INTO futures_outcomes (id, market_id, external_id, name, team_id) VALUES "
        f"(69743699, 1, 'new', 'Cade Cunningham', {DETROIT})"
    ))
    await gate.commit()
    before = await _snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 2
    assert "population moved" in lines[-1] and "futures_outcomes" in lines[-1]
    assert await _snapshot(gate) == before


async def test_a_failure_mid_apply_rolls_back_everything(gate, monkeypatch):
    import app.utils.team_merge as tm

    calls = []
    real = tm._apply_merge

    async def boom_on_the_last(session, canonical, stub, sport_key):
        calls.append(stub.id)
        if len(calls) == len(FOLDS):
            raise RuntimeError("boom in the last fold")
        return await real(session, canonical, stub, sport_key)

    monkeypatch.setattr(tm, "_apply_merge", boom_on_the_last)
    before = await _snapshot(gate)
    code, lines = await m.repair(gate, "apply")
    assert code == 1
    assert "ROLLED BACK" in lines[-1]
    # The repoint, the delete, the leg edits and two whole folds ran first; the
    # rollback undoes all of them.
    assert await _snapshot(gate) == before
