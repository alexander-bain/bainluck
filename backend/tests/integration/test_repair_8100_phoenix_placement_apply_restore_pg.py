"""#8100 — the Phoenix placement repair's select, backup, apply, readback and undo, against a real PostgreSQL.

CERT-3876's follow-up ``8100-REPAIR-RUN-PG-GUARD``. The ship: Friday's Perth
Wildcats v S.E. Melbourne Phoenix shows once, carrying Polymarket's price,
because the Polymarket-born row moves from ``basketball_other`` into
``basketball_nbl`` beside the sportsbook row and the kickoff fold joins them.

The unit file checks ``eligible()`` with strings. What the repair DOES is SQL,
so this drives ``run()`` end to end on a real server:

* the candidate read — every clause of the predicate, each with a row that
  fails only that clause;
* the banked pre-image, and the refusal when the bank does not hold the value
  a planned row still has;
* the guarded write and the readback from disk;
* a row changing under the run: rolled back, nothing written;
* a re-run that finds nothing, and an undo that puts back ONLY rows still
  where the repair put them.

Built narrow, in a private schema, so it runs on the lane VM's Postgres 14 as
well as in CI.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8100 "
            "Phoenix placement apply/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_8100_pg", _SCRIPTS / "repair_8100_phoenix_rows_in_the_catchall.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

_GATE_SCHEMA = "phoenix_placement_gate_8100"

NBL, OTHER, WNBA = 81000001, 81000002, 81000003

PHOENIX = "S.E. Melbourne Phoenix"  # teams 2919, the Odds API's spelling
VENUE_PHOENIX = "South East Melbourne Phoenix"  # Polymarket's
assert m.VENUE_CLUB_SPELLINGS[VENUE_PHOENIX] == PHOENIX

# Qualifying: the two rows production held on 2026-09-30.
EV_PERTH = 81000201  # Perth Wildcats v South East Melbourne Phoenix (15319245)
EV_ILLAWARRA = 81000202  # South East Melbourne Phoenix v Illawarra Hawks (15319859)
# Each fails exactly one clause.
EV_ANCHORED = 81000203  # carries an espn_id
EV_PAST = 81000204  # kickoff already gone
EV_LIVE = 81000205  # status is not 'scheduled'
EV_ODDS_SOURCE = 81000206  # not a Polymarket venue mint
EV_NOT_NBL = 81000207  # the other side is not an NBL club
EV_OUR_SPELLING = 81000208  # neither side is a venue spelling
# The sportsbook twin, already in the league. Never touched.
EV_SPORTSBOOK = 81000209

QUALIFYING = (EV_PERTH, EV_ILLAWARRA)
UNTOUCHED = (
    EV_ANCHORED,
    EV_PAST,
    EV_LIVE,
    EV_ODDS_SOURCE,
    EV_NOT_NBL,
    EV_OUR_SPELLING,
    EV_SPORTSBOOK,
)


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Every pooled connection lands in the private schema, so the script's
    # commits never hand it a connection that reads ``public``.
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": _GATE_SCHEMA}}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _event(id_, sport, home, away, *, kickoff="now() + interval '2 days'",
           status="scheduled", source="polymarket_venue", espn_id=None,
           external_id=None):
    def lit(v):
        return "NULL" if v is None else "'" + v.replace("'", "''") + "'"

    return (
        f"({id_}, {sport}, {lit(home)}, {lit(away)}, {kickoff}, {lit(status)}, "
        f"{lit(source)}, {lit(external_id)}, {lit(espn_id)}, NULL)"
    )


@pytest.fixture
async def gate(pg_session):
    s = pg_session
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.execute(text(f"CREATE SCHEMA {_GATE_SCHEMA}"))
    for ddl in (
        "CREATE TABLE sports (id int PRIMARY KEY, key varchar(50) NOT NULL UNIQUE, "
        "name varchar(100) NOT NULL, active boolean NOT NULL)",
        "CREATE TABLE teams (id int PRIMARY KEY, name varchar(200) NOT NULL, "
        "sport_id int NOT NULL REFERENCES sports(id))",
        "CREATE TABLE events (id int PRIMARY KEY, sport_id int NOT NULL REFERENCES sports(id), "
        "home_team_name varchar(200) NOT NULL, away_team_name varchar(200) NOT NULL, "
        "commence_time timestamptz NOT NULL, status varchar(20) NOT NULL, "
        "commence_time_source varchar(50), external_id varchar(200), "
        "espn_id varchar(50), statpal_fixture_id varchar(50))",
    ):
        await s.execute(text(ddl))
    await s.execute(
        text(
            "INSERT INTO sports (id, key, name, active) VALUES "
            f"({NBL}, 'basketball_nbl', 'NBL', true), "
            f"({OTHER}, 'basketball_other', 'basketball_other', true), "
            f"({WNBA}, 'basketball_wnba', 'WNBA', true)"
        )
    )
    await s.execute(
        text(
            "INSERT INTO teams (id, name, sport_id) VALUES "
            f"(81000101, '{PHOENIX}', {NBL}), "
            f"(81000102, 'Perth Wildcats', {NBL}), "
            f"(81000103, 'Illawarra Hawks', {NBL}), "
            f"(81000104, 'Seattle Storm', {WNBA})"
        )
    )
    await s.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, commence_time_source, external_id, espn_id, "
            "statpal_fixture_id) VALUES "
            + ", ".join(
                [
                    _event(EV_PERTH, OTHER, "Perth Wildcats", VENUE_PHOENIX),
                    _event(EV_ILLAWARRA, OTHER, VENUE_PHOENIX, "Illawarra Hawks",
                           kickoff="now() + interval '4 days'"),
                    _event(EV_ANCHORED, OTHER, "Perth Wildcats", VENUE_PHOENIX,
                           espn_id="401700001"),
                    _event(EV_PAST, OTHER, "Perth Wildcats", VENUE_PHOENIX,
                           kickoff="now() - interval '1 hour'"),
                    _event(EV_LIVE, OTHER, "Perth Wildcats", VENUE_PHOENIX,
                           status="live"),
                    _event(EV_ODDS_SOURCE, OTHER, "Perth Wildcats", VENUE_PHOENIX,
                           source="odds_api"),
                    _event(EV_NOT_NBL, OTHER, VENUE_PHOENIX, "Seattle Storm"),
                    _event(EV_OUR_SPELLING, OTHER, "Perth Wildcats", PHOENIX),
                    _event(EV_SPORTSBOOK, NBL, "Perth Wildcats", PHOENIX,
                           source="odds_api", external_id="oa-8100"),
                ]
            )
        )
    )
    await s.commit()
    yield s
    await s.rollback()
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.commit()


async def _league(s, event_id):
    res = await s.execute(
        text("SELECT s.key FROM events e JOIN sports s ON s.id = e.sport_id WHERE e.id = :id"),
        {"id": event_id},
    )
    return res.scalar_one()


async def _backup_rows(s):
    exists = await s.execute(text("SELECT to_regclass(:t)"), {"t": m.BACKUP_TABLE})
    if exists.scalar_one() is None:
        return None
    res = await s.execute(
        text(f"SELECT event_id, sport_id_before FROM {m.BACKUP_TABLE} ORDER BY 1")
    )
    return [tuple(r) for r in res]


async def _all_leagues(s):
    return {e: await _league(s, e) for e in QUALIFYING + UNTOUCHED}


BEFORE = {
    **{e: "basketball_other" for e in QUALIFYING + UNTOUCHED},
    EV_SPORTSBOOK: "basketball_nbl",
}


async def test_the_dry_run_plans_exactly_the_two_phoenix_rows_and_writes_nothing(gate):
    out = await m.run(gate, apply=False, restore=False)
    assert out["mode"] == "dry-run"
    assert [p["event_id"] for p in out["planned"]] == list(QUALIFYING)
    assert out["planned"][0]["away"] == VENUE_PHOENIX
    assert out["written"] == 0
    assert await _all_leagues(gate) == BEFORE
    # A dry run banks nothing either: the table is created only on --apply.
    assert await _backup_rows(gate) is None


async def test_apply_banks_first_then_moves_only_the_planned_rows(gate):
    out = await m.run(gate, apply=True, restore=False)
    assert out["written"] == 2
    # The readback is from disk, keyed the way the script prints it.
    assert out["now"] == {str(e): "basketball_nbl" for e in QUALIFYING}
    assert await _backup_rows(gate) == [(EV_PERTH, OTHER), (EV_ILLAWARRA, OTHER)]
    # The ship: the Polymarket row now sits in the sportsbook row's league,
    # which is what lets the same-league kickoff fold make them one card.
    assert await _league(gate, EV_PERTH) == await _league(gate, EV_SPORTSBOOK)
    after = await _all_leagues(gate)
    for event_id in UNTOUCHED:
        assert after[event_id] == BEFORE[event_id], event_id


async def test_a_re_run_finds_nothing_and_keeps_the_first_pre_image(gate):
    await m.run(gate, apply=True, restore=False)
    out = await m.run(gate, apply=True, restore=False)
    assert out["planned"] == []
    assert out["written"] == 0
    assert await _backup_rows(gate) == [(EV_PERTH, OTHER), (EV_ILLAWARRA, OTHER)]


async def test_a_row_that_changes_under_the_run_rolls_back_every_write(gate, monkeypatch):
    real_backup = m._backup

    async def backup_then_the_game_goes_live(session, event_ids, catchall_id):
        banked = await real_backup(session, event_ids, catchall_id)
        # Between the bank and the writes, the second row tips off.
        await session.execute(
            text("UPDATE events SET status = 'live' WHERE id = :id"), {"id": EV_ILLAWARRA}
        )
        await session.commit()
        return banked

    monkeypatch.setattr(m, "_backup", backup_then_the_game_goes_live)
    with pytest.raises(m.Refused, match=f"row {EV_ILLAWARRA} changed under the run"):
        await m.run(gate, apply=True, restore=False)
    # EV_PERTH's UPDATE ran first and succeeded; the rollback took it back.
    assert await _league(gate, EV_PERTH) == "basketball_other"
    assert await _league(gate, EV_ILLAWARRA) == "basketball_other"


async def test_a_bank_that_does_not_hold_the_current_value_refuses_before_any_write(gate):
    # A stale bank row from some earlier run says Perth came from the league.
    # ON CONFLICT DO NOTHING keeps it, so the bank no longer proves the undo.
    # Banked through the script's own DDL, then drifted.
    await m._backup(gate, [EV_PERTH], OTHER)
    await gate.execute(
        text(f"UPDATE {m.BACKUP_TABLE} SET sport_id_before = :nbl WHERE event_id = :e"),
        {"nbl": NBL, "e": EV_PERTH},
    )
    await gate.commit()
    with pytest.raises(m.Refused, match="backup holds 1 of 2 rows"):
        await m.run(gate, apply=True, restore=False)
    assert await _all_leagues(gate) == BEFORE


async def test_restore_puts_back_only_rows_still_where_the_repair_put_them(gate):
    await m.run(gate, apply=True, restore=False)
    # Somebody moves one row on after the repair; the undo leaves it there.
    await gate.execute(
        text("UPDATE events SET sport_id = :wnba WHERE id = :id"),
        {"wnba": WNBA, "id": EV_ILLAWARRA},
    )
    await gate.commit()
    out = await m.run(gate, apply=False, restore=True)
    assert out["mode"] == "restore"
    assert out["written"] == 1
    assert out["now"] == {str(EV_PERTH): "basketball_other", str(EV_ILLAWARRA): "basketball_wnba"}
    assert await _league(gate, EV_SPORTSBOOK) == "basketball_nbl"


async def test_restore_before_any_apply_is_a_no_op(gate):
    out = await m.run(gate, apply=False, restore=True)
    assert out["planned"] == []
    assert out["written"] == 0
    assert await _all_leagues(gate) == BEFORE


async def test_a_missing_league_row_refuses_and_writes_nothing(gate):
    await gate.execute(text("UPDATE sports SET key = 'renamed' WHERE id = :id"), {"id": NBL})
    await gate.commit()
    with pytest.raises(m.Refused, match="sports rows missing"):
        await m.run(gate, apply=True, restore=False)
    assert await _backup_rows(gate) is None
    assert await _league(gate, EV_PERTH) == "basketball_other"
