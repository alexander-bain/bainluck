"""#2351: the team-total repair against a real PostgreSQL — plan, pinned apply,
drift refusal, backup and restore.

Runs on a disposable database on the local CI service, never production. The
tables are the minimal columns the rail reads and writes; the SQL under test is
the module's own.
"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.tasks.repair_team_total_game_score as rt

URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not URL, reason="SEARCH_TEST_DATABASE_URL required for real-PG #2351 repair gate"
    ),
]

_LINES = (1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5)

#: event id -> (status, home, away, home runs, away runs)
EVENTS = {
    42: ("completed", "Cincinnati Reds", "St. Louis Cardinals", 3, 5),
    14788069: ("completed", "New York Yankees", "Tampa Bay Rays", 2, 0),
    # The doubleheader shape: a wrong stored score the venue contradicts.
    77: ("completed", "Boston Red Sox", "Tampa Bay Rays", 9, 8),
    88: ("in_progress", "Chicago Cubs", "Milwaukee Brewers", 1, 0),
}
CIN_MARKET, NYY_MARKET, BOS_MARKET, LIVE_MARKET = 7, 53667298, 900, 901
CONTROL_TOTAL, CONTROL_LOOKALIKE, WITNESS_TOTAL, BOS_WITNESS = 910, 911, 912, 913


def _rows():
    markets = [
        (CIN_MARKET, "KXMLBTEAMTOTAL-26JUN052015CINSTL", "Cincinnati vs St. Louis: Team Total", 42),
        (NYY_MARKET, "KXMLBTEAMTOTAL-26SEP22TBNYY", "Tampa Bay vs New York Y: Team Total", 14788069),
        (BOS_MARKET, "KXMLBTEAMTOTAL-26AUG01TBBOS", "Tampa Bay vs Boston: Team Total", 77),
        (LIVE_MARKET, "KXMLBTEAMTOTAL-26OCT12MILCHC", "Milwaukee vs Chicago C: Team Total", 88),
        # Never in scope: a game total, and a family that only shares a prefix.
        (CONTROL_TOTAL, "KXMLBTOTAL-26JUN052015CINSTL", "Total runs", 42),
        (CONTROL_LOOKALIKE, "KXMLBTEAMTOTALX-26JUN052015CINSTL", "Lookalike", 42),
        # Venue witnesses.
        (WITNESS_TOTAL, "KXMLBTOTAL-26SEP22TBNYY", "Total runs", 14788069),
        (BOS_WITNESS, "KXMLBTOTAL-26AUG01TBBOS", "Total runs", 77),
    ]
    outcomes = []
    oid = 1000
    for line in _LINES:
        for team in ("Cincinnati", "St. Louis"):
            oid += 1
            outcomes.append((oid, CIN_MARKET, f"{team} over {line} runs scored", True, "game_score"))
    for oid_, name in zip(range(201010270, 201010277), [
        "Tampa Bay over 2.5 runs scored", "Tampa Bay over 3.5 runs scored",
        "Tampa Bay over 4.5 runs scored", "Tampa Bay over 6.5 runs scored",
        "New York Y over 2.5 runs scored", "New York Y over 3.5 runs scored",
        "New York Y over 6.5 runs scored",
    ]):
        outcomes.append((oid_, NYY_MARKET, name, True, "game_score"))
    outcomes += [
        (2001, BOS_MARKET, "Boston over 7.5 runs scored", False, "game_score"),
        (2002, LIVE_MARKET, "Chicago C over 4.5 runs scored", True, "game_score"),
        (2003, CONTROL_TOTAL, "Over 9.5 runs scored", True, "game_score"),
        (2004, CONTROL_LOOKALIKE, "Cincinnati over 7.5 runs scored", True, "game_score"),
        (2005, WITNESS_TOTAL, "Over 6.5 runs scored", False, "api_settlement"),
        # 9 + 8 = 17 says Over 9.5 won; the venue says it lost. Score untrusted.
        (2006, BOS_WITNESS, "Over 9.5 runs scored", False, "api_settlement"),
    ]
    return markets, outcomes


@pytest.fixture(scope="session")
def isolated_database():
    url = make_url(URL)
    assert url.host in ("localhost", "127.0.0.1"), "gate may only use local PostgreSQL"
    database = "team_total_2351_" + uuid4().hex
    admin = create_engine(url.set(drivername="postgresql+psycopg2"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{database}"'))
    try:
        yield url.set(database=database)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
async def db(isolated_database):
    engine = create_async_engine(isolated_database)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        for t in (rt.BAK_TABLE, "futures_outcomes", "futures_markets", "events"):
            await s.execute(text(f"DROP TABLE IF EXISTS {t}"))
        await s.execute(text(
            "CREATE TABLE events (id BIGINT PRIMARY KEY, status TEXT, home_team_name TEXT,"
            " away_team_name TEXT, home_score INT, away_score INT,"
            " commence_time TIMESTAMPTZ, completed_at TIMESTAMPTZ, score_source TEXT)"))
        await s.execute(text(
            "CREATE TABLE futures_markets (id BIGINT PRIMARY KEY, source TEXT,"
            " external_id TEXT, name TEXT, event_id BIGINT,"
            " UNIQUE (source, external_id))"))
        await s.execute(text(
            "CREATE TABLE futures_outcomes (id BIGINT PRIMARY KEY, market_id BIGINT,"
            " name TEXT, is_winner BOOLEAN, resolution_source TEXT,"
            " last_updated TIMESTAMPTZ DEFAULT '2026-01-01T00:00:00Z')"))
        for eid, (status, home, away, hs, as_) in EVENTS.items():
            await s.execute(text(
                "INSERT INTO events (id, status, home_team_name, away_team_name, home_score, away_score)"
                " VALUES (:i,:s,:h,:a,:hs,:as_)"),
                dict(i=eid, s=status, h=home, a=away, hs=hs, as_=as_))
        markets, outcomes = _rows()
        for mid, ext, name, eid in markets:
            await s.execute(text(
                "INSERT INTO futures_markets VALUES (:i,'kalshi',:x,:n,:e)"),
                dict(i=mid, x=ext, n=name, e=eid))
        for oid, mid, name, won, src in outcomes:
            await s.execute(text(
                "INSERT INTO futures_outcomes (id, market_id, name, is_winner, resolution_source)"
                " VALUES (:i,:m,:n,:w,:s)"), dict(i=oid, m=mid, n=name, w=won, s=src))
        await s.commit()
    yield maker
    await engine.dispose()


async def _state(maker):
    async with maker() as s:
        rows = (await s.execute(text(
            "SELECT id, is_winner, resolution_source, last_updated FROM futures_outcomes"))).all()
    return {r.id: (r.is_winner, r.resolution_source, r.last_updated) for r in rows}


def _expected_cin():
    out = {}
    oid = 1000
    for line in _LINES:
        for team, runs in (("Cincinnati", 3), ("St. Louis", 5)):
            oid += 1
            out[oid] = runs > line
    return out


async def _run(maker, fn, **kw):
    async with maker() as s:
        return await fn(s, **kw)


async def test_dry_run_plans_only_contradicted_legs_and_writes_nothing(db):
    before = await _state(db)
    plan = await _run(db, rt.repair)
    assert plan["terminal"] == "dry_run" and plan["exhausted"] is True
    cin_wrong = {k for k, v in _expected_cin().items() if v is False}
    nyy = set(range(201010270, 201010277))
    assert plan["legs_contradicted"] == len(cin_wrong) + len(nyy) == 15
    assert plan["market_skips"] == {"score_contradicted_by_venue": 1, "event_not_final": 1}
    assert plan["markets_with_venue_witness"] == 1  # NYY: concordant total leg
    assert await _state(db) == before


async def test_apply_needs_the_reviewed_hash_and_then_writes_exactly_the_plan(db):
    before = await _state(db)
    plan = await _run(db, rt.repair)

    refused = await _run(db, rt.repair, apply=True)
    assert refused["terminal"] == "refused_no_plan_hash"
    stale = await _run(db, rt.repair, apply=True, plan_hash="0" * 32)
    assert stale["terminal"] == "refused_plan_drift" and stale["legs_written"] == 0
    assert await _state(db) == before

    out = await _run(db, rt.repair, apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "applied"
    assert out["legs_written"] == 15 and out["drift_refused"] == 0
    after = await _state(db)

    expected = {**{k: v for k, v in _expected_cin().items()},
                **{k: False for k in range(201010270, 201010277)}}
    for oid, won in expected.items():
        assert after[oid][0] is won and after[oid][1] == "game_score", oid
    changed = {oid for oid in after if after[oid] != before[oid]}
    assert changed == {k for k, v in expected.items() if before[k][0] != v}
    # Correct siblings, untrusted score, live game, other families: untouched.
    for oid in (2001, 2002, 2003, 2004, 2005, 2006):
        assert after[oid] == before[oid]

    again = await _run(db, rt.repair)
    assert again["legs_contradicted"] == 0, "the repair is a fixed point"
    async with db() as s:
        n = (await s.execute(text(f"SELECT count(*) FROM {rt.BAK_TABLE}"))).scalar_one()
    assert n == 15


async def test_pinned_ids_narrow_the_plan_and_the_apply(db):
    pin = "201010270,201010276"
    plan = await _run(db, rt.repair, only_ids=pin)
    assert plan["legs_contradicted"] == 2
    whole = await _run(db, rt.repair)
    assert plan["plan_hash"] != whole["plan_hash"]
    out = await _run(db, rt.repair, apply=True, only_ids=pin, plan_hash=plan["plan_hash"])
    assert out["legs_written"] == 2
    after = await _state(db)
    assert after[201010270][0] is False and after[201010276][0] is False
    assert after[201010271][0] is True, "an unpinned leg is not written"


async def test_a_leg_that_moves_between_plan_and_write_is_refused_and_unbacked(db, monkeypatch):
    plan = await _run(db, rt.repair)
    real = rt._plan_page

    async def plan_then_venue_grades(*a, **k):
        result = await real(*a, **k)
        async with db() as other:  # another writer lands after the plan is read
            await other.execute(text(
                "UPDATE futures_outcomes SET is_winner = false,"
                " resolution_source = 'api_settlement' WHERE id = 201010276"))
            await other.execute(text(
                "UPDATE events SET home_score = 4 WHERE id = 42"))
            await other.commit()
        return result

    monkeypatch.setattr(rt, "_plan_page", plan_then_venue_grades)
    out = await _run(db, rt.repair, apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "applied"
    # 1 NYY leg moved; every CIN leg's score moved. Only six NYY legs land.
    assert out["legs_written"] == 6 and out["drift_refused"] == 9
    after = await _state(db)
    assert after[201010276][1] == "api_settlement"
    async with db() as s:
        backed = {r[0] for r in (await s.execute(text(
            f"SELECT outcome_id FROM {rt.BAK_TABLE}"))).all()}
    assert backed == set(range(201010270, 201010276)), "a refused leg leaves no backup row"


async def test_restore_puts_back_only_what_this_rail_wrote(db):
    before = await _state(db)
    assert (await _run(db, rt.restore))["terminal"] == "refused_no_backup"
    plan = await _run(db, rt.repair)
    await _run(db, rt.repair, apply=True, plan_hash=plan["plan_hash"])

    async with db() as other:  # the venue grades one repaired leg afterwards
        await other.execute(text(
            "UPDATE futures_outcomes SET resolution_source = 'api_settlement'"
            " WHERE id = 201010270"))
        await other.commit()

    dry = await _run(db, rt.restore)
    assert dry["terminal"] == "dry_run"
    assert dry["backed_up_rows"] == 15 and dry["restorable"] == 14 and dry["diverged"] == 1
    assert dry["restored"] == 0

    done = await _run(db, rt.restore, apply=True)
    assert done["restored"] == 14
    after = await _state(db)
    for oid, (won, src, _) in before.items():
        if oid == 201010270:
            assert src == "game_score" and after[oid][1] == "api_settlement"
            continue
        assert (after[oid][0], after[oid][1]) == (won, src), oid

    again = await _run(db, rt.restore)
    assert again["restorable"] == 0 and again["already_at_prior"] == 14


async def test_a_moved_prior_is_drift_even_when_a_backup_row_already_exists(db, monkeypatch):
    """Apply, restore, re-apply: the backup rows survive the restore, so the
    backup copy no longer guards the write and only the prior compare-and-set
    can see a leg another `game_score` writer re-graded after the plan."""
    plan = await _run(db, rt.repair)
    await _run(db, rt.repair, apply=True, plan_hash=plan["plan_hash"])
    await _run(db, rt.restore, apply=True)
    replan = await _run(db, rt.repair)
    assert replan["plan_hash"] == plan["plan_hash"]
    real = rt._plan_page

    async def plan_then_regrade(*a, **k):
        result = await real(*a, **k)
        async with db() as other:
            await other.execute(text(
                "UPDATE futures_outcomes SET is_winner = false WHERE id = 201010271"))
            await other.commit()
        return result

    monkeypatch.setattr(rt, "_plan_page", plan_then_regrade)
    out = await _run(db, rt.repair, apply=True, plan_hash=replan["plan_hash"])
    assert out["legs_written"] == 14 and out["drift_refused"] == 1
    async with db() as s:
        kept = (await s.execute(text(
            f"SELECT prior_is_winner FROM {rt.BAK_TABLE} WHERE outcome_id = 201010271"
        ))).scalar_one()
    assert kept is True, "the first backup, from before the rail, is never overwritten"


async def test_restore_never_undoes_a_later_write_that_restates_the_same_verdict(db):
    """Root's restore hole: a later writer re-states the rail's own boolean and
    source (here, a resolver touching `last_updated`). Same values, newer write
    — the restore must count it as diverged and leave it, never revert it."""
    plan = await _run(db, rt.repair)
    await _run(db, rt.repair, apply=True, plan_hash=plan["plan_hash"])
    before_restore = await _state(db)
    async with db() as other:
        await other.execute(text(
            "UPDATE futures_outcomes SET is_winner = false, resolution_source = 'game_score',"
            " last_updated = NOW() WHERE id = 201010272"))
        await other.commit()
    dry = await _run(db, rt.restore)
    assert dry["restorable"] == 14 and dry["diverged"] == 1
    await _run(db, rt.restore, apply=True)
    after = await _state(db)
    assert after[201010272][:2] == (False, "game_score"), "the later write stands"
    assert after[201010272][2] != before_restore[201010272][2]
    assert after[201010273][:2] == (True, "game_score"), "an untouched leg is restored"


@pytest.mark.parametrize("event_sql", [
    "UPDATE events SET status = 'in_progress' WHERE id = 14788069",
    "UPDATE events SET commence_time = '2026-09-22T23:05:00Z',"
    " completed_at = '2026-09-22T20:00:00Z' WHERE id = 14788069",
])
async def test_an_event_that_stops_being_a_valid_final_after_the_plan_gets_no_write(
    db, monkeypatch, event_sql
):
    """Root's apply hole: the planner refuses a non-final event and a completion
    before the start; the write must re-ask both, not just score and clubs."""
    plan = await _run(db, rt.repair)
    real = rt._plan_page

    async def plan_then_event_changes(*a, **k):
        result = await real(*a, **k)
        async with db() as other:
            await other.execute(text(event_sql))
            await other.commit()
        return result

    monkeypatch.setattr(rt, "_plan_page", plan_then_event_changes)
    out = await _run(db, rt.repair, apply=True, plan_hash=plan["plan_hash"])
    assert out["legs_written"] == 8 and out["drift_refused"] == 7  # CIN lands, NYY refused
    after = await _state(db)
    assert all(after[oid][0] is True for oid in range(201010270, 201010277))
    async with db() as s:
        backed = {r[0] for r in (await s.execute(text(
            f"SELECT outcome_id FROM {rt.BAK_TABLE}"))).all()}
    assert not backed & set(range(201010270, 201010277)), "no backup row for a refused leg"
