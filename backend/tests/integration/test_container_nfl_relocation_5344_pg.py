"""#5344 — a game the authority moves to another week moves hubs, on a real server.

SHIP: when the authoritative schedule moves a game to another week, the next
complete automatic pass moves it and its markets to the correct hub; old links
stay truthful and human withdrawals are not revived. Pillars: MATCHING /
DISCOVER / TRUTH.

Contract: `artifacts/containers-1.0.4-20261011/AUTHORITY-5344-CONTRACT-RETURN.md`
(P1–P10) and policy A (`5344-CORRECTION-POLICY-DECISION.md`): the barrier is the
database clock taken BEFORE the fetch; an older-started read changes nothing; an
identical equal-barrier repeat is a no-op and a conflicting one changes nothing.

Every test drives the MOUNTED path — `container_assembly.run_nfl_collection`
with the unchanged declaration, a schedule double standing in for StatPal's
receipted read and a clock — and reads back what is STORED. The races are real
sessions on a real server: a read parked inside its fetch while another pass
commits, and a person's withdrawal holding its row lock while the pass waits.
A session double cannot show either; it would agree with whatever statement was
built.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "needs a real PostgreSQL: set SEARCH_TEST_DATABASE_URL (the "
        "search-recall CI job does)"
    ),
)

FLAG = "CONTAINER_NFL_AUTO_PUBLISH_ENABLED"
W7 = "Regular Season / Week 7"
W8 = "Regular Season / Week 8"
W12 = "Regular Season / Week 12"
WEEK_7 = "nfl-2026-week-7"
WEEK_8 = "nfl-2026-week-8"
WEEK_12 = "nfl-2026-week-12"

#: Weeks 7 and 8 both hold a kickoff inside [now - 2d, now + 9d]; Week 12 does not.
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def _at(m, d, h=17, minute=0, year=2026):
    return datetime(year, m, d, h, minute, tzinfo=timezone.utc)


def _fixture(cid, home, away, kickoff, round_info):
    from app.services.statpal_api import StatPalFixture

    return StatPalFixture(
        fixture_id=cid,
        home_team=home,
        away_team=away,
        home_team_id=f"h-{cid}",
        away_team_id=f"a-{cid}",
        start_time=kickoff,
        status="scheduled",
        round_info=round_info,
    )


def _schedule(s703_round=W7, *, extra=()):
    """Weeks 7 and 8 as the authority files them; s703's week is the variable."""
    return [
        _fixture("s701", "Chiefs", "Raiders", _at(10, 23, 0, 15), W7),
        _fixture("s702", "Bills", "Jets", _at(10, 25), W7),
        _fixture("s703", "Eagles", "Giants", _at(10, 27, 0, 15), s703_round),
        _fixture("s801", "Rams", "Seahawks", _at(10, 29, 0, 15), W8),
        *extra,
    ]


class _Schedule:
    """StatPal's receipted NFL read (`get_nfl_schedule_read`, #5344 M1)."""

    def __init__(self, fixtures=None, *, error=None, skipped=(), duplicates=(),
                 gate=None, entered=None):
        self.fixtures, self.error = fixtures, error
        self.skipped, self.duplicates = list(skipped), list(duplicates)
        self.gate, self.entered = gate, entered

    async def get_nfl_schedule_read(self):
        from app.services.statpal_api import StatPalNflScheduleRead

        if self.entered is not None:
            self.entered.set()
        if self.gate is not None:
            await self.gate.wait()  # parked inside the fetch, holding nothing
        if self.error is not None:
            raise self.error
        return StatPalNflScheduleRead(
            fixtures=list(self.fixtures),
            skipped=self.skipped,
            unidentified=[],
            duplicates=self.duplicates,
            rows_seen=len(self.fixtures) + len(self.skipped),
        )


@pytest.fixture
async def world(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Sport
    from app.services.database import Base
    from app.utils.container_corrections import UPGRADE_STATEMENTS
    from app.utils.theme_definitions import UPGRADE_STATEMENTS as DECISION_STATEMENTS

    monkeypatch.setenv(FLAG, "true")
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS container_member_decisions"))
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        for statement in UPGRADE_STATEMENTS:
            await conn.execute(text(statement))
        # The decisions table the theme pass already writes in production
        # (#9935): the barrier lives in its evidence, no new schema.
        for statement in DECISION_STATEMENTS:
            await conn.execute(text(statement))

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        sport = Sport(key="americanfootball_nfl", name="NFL", active=True)
        session.add(sport)
        await session.commit()
        sport_id = sport.id

    yield Session, sport_id
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS container_member_decisions"))
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
    await engine.dispose()


async def _seed(Session, sport_id, fixtures):
    """One event per contest and one prop question on each.
    Returns ``({contest_id: event_id}, {contest_id: market_id})``."""
    from app.models.models import Event, FuturesMarket

    events, markets = {}, {}
    async with Session() as session:
        for f in fixtures:
            event = Event(
                sport_id=sport_id,
                home_team_name=f.home_team,
                away_team_name=f.away_team,
                commence_time=f.start_time,
                status="scheduled",
                statpal_fixture_id=f.fixture_id,
            )
            session.add(event)
            await session.flush()
            market = FuturesMarket(
                source="kalshi",
                external_id=f"KXNFLPROP-{f.fixture_id}-{event.id}",
                sport_id=sport_id,
                event_id=event.id,
                name=f"{f.away_team} at {f.home_team}: total points over 44.5",
                category="sports",
                market_type="prop",
                commence_time=f.start_time,
                status="open",
            )
            session.add(market)
            await session.flush()
            events[f.fixture_id], markets[f.fixture_id] = event.id, market.id
        await session.commit()
    return events, markets


async def _pass(Session, fixtures=None, *, now=NOW, declaration=None, **schedule):
    """One hourly pass's NFL half: its own session, committed per week."""
    from app.tasks import container_assembly as ca
    from app.utils.container_tournaments import NFL_2026

    service = schedule.pop("service", None) or _Schedule(fixtures, **schedule)
    async with Session() as session:
        runs = await ca.run_nfl_collection(
            session, declaration or NFL_2026, apply=True, now=now, service=service
        )
    return {r["slug"]: r for r in runs}


async def _hub(Session, slug):
    async with Session() as session:
        return (
            await session.execute(
                text(
                    "SELECT id, publication_state, membership_revision "
                    "FROM containers WHERE slug = :slug"
                ),
                {"slug": slug},
            )
        ).fetchone()


async def _members(Session, slug):
    async with Session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT ee.child_type, ee.child_id FROM event_edges ee "
                    "JOIN containers c ON c.id = ee.parent_id "
                    "WHERE ee.parent_type = 'container' AND ee.kind = 'contains' "
                    "  AND c.slug = :slug"
                ),
                {"slug": slug},
            )
        ).fetchall()
    return {(r[0], int(r[1])) for r in rows}


async def _decisions(Session, slug):
    async with Session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT d.child_type, d.child_id, d.outcome, d.reason, d.evidence "
                    "FROM container_member_decisions d JOIN containers c "
                    "  ON c.id = d.container_id WHERE c.slug = :slug ORDER BY d.child_id"
                ),
                {"slug": slug},
            )
        ).fetchall()
    return [tuple(r) for r in rows]


async def _edge_versions(Session):
    """Every edge's row version: unchanged ``xmin`` ⇔ the row was not rewritten."""
    async with Session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT parent_id, child_type, child_id, xmin::text FROM event_edges "
                    "WHERE parent_type = 'container'"
                )
            )
        ).fetchall()
    return {(int(r[0]), r[1], int(r[2])): r[3] for r in rows}


async def _ledger(Session, slug):
    async with Session() as session:
        return [
            tuple(r)
            for r in (
                await session.execute(
                    text(
                        "SELECT l.scope, l.action, l.child_type, l.child_id, l.actor "
                        "FROM container_corrections l JOIN containers c "
                        "  ON c.id = l.container_id WHERE c.slug = :slug ORDER BY l.id"
                    ),
                    {"slug": slug},
                )
            ).fetchall()
        ]


def _game(events, markets, cid):
    return {("event", events[cid]), ("market", markets[cid])}


async def _withdraw(session, slug, event_id):
    from app.utils.container_corrections import withdraw_member

    container_id = (
        await session.execute(text("SELECT id FROM containers WHERE slug = :s"), {"s": slug})
    ).scalar_one()
    return await withdraw_member(
        session,
        container_id=container_id,
        child_type="event",
        child_id=event_id,
        reason="not this week's game",
        actor="alex",
    )


async def _wait_for_lock_waiter(Session, timeout=15.0):
    """Until some backend is waiting on a row lock — the pass, parked on ours."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        async with Session() as probe:
            waiting = (
                await probe.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE wait_event_type = 'Lock' AND datname = current_database()"
                    )
                )
            ).scalar()
        if waiting:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the pass never waited on the withdrawal's lock")


async def _published_weeks_7_and_8(Session, sport_id, *, dest_first=False, extra=()):
    """Weeks 7 and 8 assembled and published, s703 in Week 7. ``dest_first``
    creates Week 8's row first, so it has the LOWER id (the other lock order)."""
    fixtures = _schedule(extra=extra)
    events, markets = await _seed(Session, sport_id, fixtures)
    if dest_first:
        async with Session() as session:
            await session.execute(
                text(
                    "INSERT INTO containers (kind, name, slug) "
                    "VALUES ('season', 'NFL 2026 · Week 8', :slug)"
                ),
                {"slug": WEEK_8},
            )
            await session.commit()
    runs = await _pass(Session, fixtures)
    assert runs[WEEK_7]["publication"]["decision"] == "published"
    assert runs[WEEK_8]["publication"]["decision"] == "published"
    w7, w8 = await _hub(Session, WEEK_7), await _hub(Session, WEEK_8)
    assert (w8[0] < w7[0]) is dest_first
    assert _game(events, markets, "s703") <= await _members(Session, WEEK_7)
    return events, markets


# --- P1 / P2: the move, and the unchanged repeat --------------------------------


@pytest.mark.asyncio
async def test_p1_a_relabelled_game_leaves_week_7_and_arrives_in_week_8_atomically(world):
    from app.utils.container_nfl import DECISION_RELOCATED, RELOCATION_RULE_VERSION
    from app.utils.container_read_cache import container_read_cache_key

    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    s703 = _game(events, markets, "s703")
    _, _, w7_rev = await _hub(Session, WEEK_7)
    _, _, w8_rev = await _hub(Session, WEEK_8)

    runs = await _pass(Session, _schedule(W8))

    # The destination ran first, so Week 7 is judged after the move.
    assert list(runs) == [WEEK_8, WEEK_7]
    relocation = runs[WEEK_8]["relocation"]
    assert relocation["state"] == "applied" and relocation["complete"] is True
    [moved] = relocation["moved"]
    assert moved["event_id"] == events["s703"]
    assert moved["from_slugs"] == [WEEK_7] and moved["to_slug"] == WEEK_8
    assert moved["markets_removed"] == 1

    assert not (s703 & await _members(Session, WEEK_7))
    assert s703 <= await _members(Session, WEEK_8)
    _, w7_state, w7_after = await _hub(Session, WEEK_7)
    _, w8_state, w8_after = await _hub(Session, WEEK_8)
    assert (w7_after, w8_after) == (w7_rev + 1, w8_rev + 1)
    assert (w7_state, w8_state) == ("published", "published")
    assert container_read_cache_key(WEEK_7, w7_rev, True) != container_read_cache_key(
        WEEK_7, w7_after, True
    )
    # Week 7, re-read after the move, is exactly its remaining games again.
    assert runs[WEEK_7]["publication"]["decision"] == "already_published"

    [(ct, cid, outcome, reason, evidence)] = await _decisions(Session, WEEK_7)
    assert (ct, cid, outcome, reason) == ("event", events["s703"], "excluded", DECISION_RELOCATED)
    assert evidence["rule"] == RELOCATION_RULE_VERSION
    assert evidence["to_slug"] == WEEK_8 and evidence["from_slugs"] == [WEEK_7]
    assert evidence["contest_id"] == "s703" and evidence["round"] == W8
    [(_, _, outcome, reason, dest_evidence)] = await _decisions(Session, WEEK_8)
    assert (outcome, reason) == ("admitted", DECISION_RELOCATED)
    assert dest_evidence["barrier"] == evidence["barrier"] == relocation["barrier"]
    # A move is never a person's veto: no ledger row anywhere.
    assert [r for r in await _ledger(Session, WEEK_7) if r[0] == "member"] == []


@pytest.mark.asyncio
async def test_p2_the_same_snapshot_again_writes_no_edge_and_bumps_no_revision(world):
    Session, sport_id = world
    await _published_weeks_7_and_8(Session, sport_id)
    await _pass(Session, _schedule(W8))
    before = await _edge_versions(Session)
    hubs = [await _hub(Session, WEEK_7), await _hub(Session, WEEK_8)]
    decisions = [await _decisions(Session, WEEK_7), await _decisions(Session, WEEK_8)]

    runs = await _pass(Session, _schedule(W8))

    for slug in (WEEK_7, WEEK_8):
        assert runs[slug]["assembly"]["edges_written"] == 0
        assert runs[slug]["relocation"]["moved"] == []
        assert runs[slug]["relocation"]["decisions_written"] == 0
        assert runs[slug]["publication"]["decision"] == "already_published"
    assert await _edge_versions(Session) == before
    assert [await _hub(Session, WEEK_7), await _hub(Session, WEEK_8)] == hubs
    assert [await _decisions(Session, WEEK_7), await _decisions(Session, WEEK_8)] == decisions


# --- P3 + policy A: an older-started read never undoes a newer one -------------


@pytest.mark.asyncio
@pytest.mark.parametrize("dest_first", [False, True], ids=["w7-lower-id", "w8-lower-id"])
async def test_p3_an_old_read_parked_in_its_fetch_changes_nothing_after_a_new_move(
    world, dest_first
):
    """Old allocates its barrier, then parks inside the fetch; New starts later,
    reads s703 in Week 8 and commits the move; Old is released holding the old
    schedule. Old must write nothing and bump nothing — in both lock orders."""
    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id, dest_first=dest_first)
    s703 = _game(events, markets, "s703")

    gate, entered = asyncio.Event(), asyncio.Event()
    old = asyncio.create_task(
        _pass(Session, service=_Schedule(_schedule(W7), gate=gate, entered=entered))
    )
    await entered.wait()  # Old's barrier is taken; it holds no transaction now
    new_runs = await _pass(Session, _schedule(W8))
    assert new_runs[WEEK_8]["relocation"]["moved"]
    after_new = (await _hub(Session, WEEK_7), await _hub(Session, WEEK_8))
    edges_after_new = await _edge_versions(Session)
    decisions_after_new = (await _decisions(Session, WEEK_7), await _decisions(Session, WEEK_8))

    gate.set()
    old_runs = await old

    for slug in (WEEK_7, WEEK_8):
        run = old_runs[slug]
        assert (run["terminal"], run["reason"]) == ("partial", "stale_snapshot")
        assert run["relocation"]["state"] == "stale_snapshot"
        assert "assembly" not in run
        assert run["publication"]["decision"] == "not_evaluated"
    assert old_runs[WEEK_7]["relocation"]["barrier"] < new_runs[WEEK_8]["relocation"]["barrier"]
    assert (await _hub(Session, WEEK_7), await _hub(Session, WEEK_8)) == after_new
    assert await _edge_versions(Session) == edges_after_new
    assert (await _decisions(Session, WEEK_7), await _decisions(Session, WEEK_8)) == (
        decisions_after_new
    )
    assert not (s703 & await _members(Session, WEEK_7))
    assert s703 <= await _members(Session, WEEK_8)


@pytest.mark.asyncio
@pytest.mark.parametrize("dest_first", [False, True], ids=["w7-lower-id", "w8-lower-id"])
async def test_p3_the_opposite_commit_order_applies_both_in_order(world, dest_first):
    """Old starts first and commits first; New starts later and commits after.
    Both are admitted in order and s703 ends in Week 8."""
    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id, dest_first=dest_first)
    s703 = _game(events, markets, "s703")

    old_entered, old_gate = asyncio.Event(), asyncio.Event()
    new_entered, new_gate = asyncio.Event(), asyncio.Event()
    old = asyncio.create_task(
        _pass(Session, service=_Schedule(_schedule(W7), gate=old_gate, entered=old_entered))
    )
    await old_entered.wait()
    new = asyncio.create_task(
        _pass(Session, service=_Schedule(_schedule(W8), gate=new_gate, entered=new_entered))
    )
    await new_entered.wait()
    old_gate.set()
    old_runs = await old
    new_gate.set()
    new_runs = await new

    assert all(r["terminal"] != "partial" or r["reason"] != "stale_snapshot"
               for r in old_runs.values())
    assert old_runs[WEEK_7]["relocation"]["barrier"] < new_runs[WEEK_8]["relocation"]["barrier"]
    assert new_runs[WEEK_8]["relocation"]["moved"][0]["event_id"] == events["s703"]
    assert not (s703 & await _members(Session, WEEK_7))
    assert s703 <= await _members(Session, WEEK_8)


# --- equal barriers -------------------------------------------------------------


@pytest.fixture
def fixed_barrier(monkeypatch):
    """Pin the pass's barrier: two reads taken at the same database instant."""
    import app.tasks.container_nfl_assembly as nfl

    value = {"at": datetime(2026, 10, 21, 12, 0, 0, 123456, tzinfo=timezone.utc)}

    async def pinned(session):
        await session.rollback()
        return value["at"]

    monkeypatch.setattr(nfl, "read_admission_barrier", pinned)
    return value


@pytest.mark.asyncio
async def test_an_identical_equal_barrier_repeat_is_a_no_op(world, fixed_barrier):
    Session, sport_id = world
    await _published_weeks_7_and_8(Session, sport_id)
    first = await _pass(Session, _schedule(W8))
    assert first[WEEK_8]["relocation"]["moved"]
    before = await _edge_versions(Session)
    hubs = [await _hub(Session, WEEK_7), await _hub(Session, WEEK_8)]
    decisions = [await _decisions(Session, WEEK_7), await _decisions(Session, WEEK_8)]

    again = await _pass(Session, _schedule(W8))

    for slug in (WEEK_7, WEEK_8):
        assert again[slug]["relocation"]["state"] == "applied"
        assert again[slug]["relocation"]["moved"] == []
        assert again[slug]["assembly"]["edges_written"] == 0
    assert await _edge_versions(Session) == before
    assert [await _hub(Session, WEEK_7), await _hub(Session, WEEK_8)] == hubs
    assert [await _decisions(Session, WEEK_7), await _decisions(Session, WEEK_8)] == decisions


@pytest.mark.asyncio
async def test_a_conflicting_equal_barrier_read_changes_nothing_anywhere(
    world, fixed_barrier
):
    """Same instant, different answer: s703 back in Week 7 AND a new Week 8 game.
    Neither read is newer, so neither the move back NOR the unrelated addition
    may land, and no revision moves."""
    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    await _pass(Session, _schedule(W8))
    s802 = _fixture("s802", "Packers", "Bears", _at(10, 30, 0, 15), W8)
    new_events, new_markets = await _seed(Session, sport_id, [s802])
    before = await _edge_versions(Session)
    hubs = [await _hub(Session, WEEK_7), await _hub(Session, WEEK_8)]
    decisions = [await _decisions(Session, WEEK_7), await _decisions(Session, WEEK_8)]

    runs = await _pass(Session, _schedule(W7, extra=[s802]))

    for slug in (WEEK_7, WEEK_8):
        assert (runs[slug]["terminal"], runs[slug]["reason"]) == (
            "partial", "conflicting_equal_barrier"
        )
        assert "assembly" not in runs[slug]
    assert await _edge_versions(Session) == before
    assert [await _hub(Session, WEEK_7), await _hub(Session, WEEK_8)] == hubs
    assert [await _decisions(Session, WEEK_7), await _decisions(Session, WEEK_8)] == decisions
    assert ("event", new_events["s802"]) not in await _members(Session, WEEK_8)
    assert _game(events, markets, "s703") <= await _members(Session, WEEK_8)


# --- P4: a person's withdrawal binds, before, during and after ------------------


@pytest.mark.asyncio
async def test_p4_withdrawn_from_the_destination_before_it_never_arrives_and_still_leaves(world):
    from app.utils.container_corrections import withdrawn_members
    from app.utils.container_nfl import DECISION_RELOCATED_WITHDRAWN

    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    async with Session() as session:
        await _withdraw(session, WEEK_8, events["s703"])
        await session.commit()
    ledger = await _ledger(Session, WEEK_8)

    runs = await _pass(Session, _schedule(W8))

    s703 = _game(events, markets, "s703")
    assert not (s703 & await _members(Session, WEEK_7))
    assert ("event", events["s703"]) not in await _members(Session, WEEK_8)
    assert runs[WEEK_8]["relocation"]["destination_withdrawn"] == [events["s703"]]
    [(_, _, outcome, reason, _)] = await _decisions(Session, WEEK_8)
    assert (outcome, reason) == ("withheld", DECISION_RELOCATED_WITHDRAWN)
    assert await _ledger(Session, WEEK_8) == ledger
    w8_id = (await _hub(Session, WEEK_8))[0]
    async with Session() as session:
        assert await withdrawn_members(session, w8_id) == {("event", events["s703"])}


@pytest.mark.asyncio
async def test_p4_withdrawn_from_the_old_week_before_never_returns_there(world):
    """Withdrawn from Week 7; the authority moves it to Week 8 (it arrives);
    then a newer read files it back under Week 7 — it does not return there, and
    Week 8 still loses it, because the authority says it is not Week 8's."""
    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    async with Session() as session:
        await _withdraw(session, WEEK_7, events["s703"])
        await session.commit()
    ledger = await _ledger(Session, WEEK_7)
    s703 = _game(events, markets, "s703")

    moving = await _pass(Session, _schedule(W8))
    assert s703 <= await _members(Session, WEEK_8)
    # The person withdrew the game, not its question; the question leaves too.
    assert not (s703 & await _members(Session, WEEK_7))
    assert moving[WEEK_8]["relocation"]["moved"][0]["markets_removed"] == 1

    runs = await _pass(Session, _schedule(W7))

    assert ("event", events["s703"]) not in await _members(Session, WEEK_7)
    assert not (s703 & await _members(Session, WEEK_8))
    assert runs[WEEK_7]["relocation"]["destination_withdrawn"] == [events["s703"]]
    assert await _ledger(Session, WEEK_7) == ledger


@pytest.mark.asyncio
@pytest.mark.parametrize("dest_first", [False, True], ids=["w7-lower-id", "w8-lower-id"])
@pytest.mark.parametrize("withdrawn_from", [WEEK_8, WEEK_7])
async def test_p4_a_withdrawal_holding_its_lock_during_the_move_is_honoured(
    world, dest_first, withdrawn_from
):
    """The person's correction holds its week's row lock, uncommitted, while the
    pass reaches for the same week; the pass waits, then reads the withdrawal.
    No deadlock in either id order, and the ledger row stands."""
    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id, dest_first=dest_first)
    s703 = _game(events, markets, "s703")

    async with Session() as person:
        await _withdraw(person, withdrawn_from, events["s703"])
        moving = asyncio.create_task(_pass(Session, _schedule(W8)))
        await _wait_for_lock_waiter(Session)
        assert not moving.done()
        await person.commit()
    runs = await asyncio.wait_for(moving, timeout=30)

    assert not (s703 & await _members(Session, WEEK_7))
    w8 = await _members(Session, WEEK_8)
    if withdrawn_from == WEEK_8:
        assert ("event", events["s703"]) not in w8
        assert runs[WEEK_8]["relocation"]["destination_withdrawn"] == [events["s703"]]
    else:
        # The game had left Week 7 by the person's hand; its question leaves
        # with the move, and the game arrives in Week 8.
        assert s703 <= w8
        [moved] = runs[WEEK_8]["relocation"]["moved"]
        assert moved["from_slugs"] == [WEEK_7] and moved["markets_removed"] == 1
    [(scope, action, ct, cid, actor)] = [
        r for r in await _ledger(Session, withdrawn_from) if r[0] == "member"
    ]
    assert (scope, action, ct, cid, actor) == ("member", "withdraw", "event", events["s703"], "alex")


@pytest.mark.asyncio
async def test_p4_withdrawn_from_the_destination_after_the_move_stays_out(world):
    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    await _pass(Session, _schedule(W8))
    async with Session() as session:
        await _withdraw(session, WEEK_8, events["s703"])
        await session.commit()
    ledger = await _ledger(Session, WEEK_8)

    await _pass(Session, _schedule(W8))

    assert ("event", events["s703"]) not in await _members(Session, WEEK_8)
    assert not (_game(events, markets, "s703") & await _members(Session, WEEK_7))
    assert await _ledger(Session, WEEK_8) == ledger


# --- P5: a later newer read can bring it back ----------------------------------


@pytest.mark.asyncio
async def test_p5_a_newer_read_filing_it_back_under_week_7_returns_it(world):
    from app.utils.container_nfl import DECISION_RELOCATED

    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    s703 = _game(events, markets, "s703")
    await _pass(Session, _schedule(W8))

    runs = await _pass(Session, _schedule(W7))

    assert runs[WEEK_7]["relocation"]["moved"][0]["from_slugs"] == [WEEK_8]
    assert s703 <= await _members(Session, WEEK_7)
    assert not (s703 & await _members(Session, WEEK_8))
    [(_, _, outcome, reason, _)] = await _decisions(Session, WEEK_7)
    assert (outcome, reason) == ("admitted", DECISION_RELOCATED)
    [(_, _, outcome, reason, _)] = await _decisions(Session, WEEK_8)
    assert (outcome, reason) == ("excluded", DECISION_RELOCATED)


# --- P6: another writer's edge holds --------------------------------------------


@pytest.mark.asyncio
async def test_p6_a_foreign_source_edge_on_the_game_is_kept(world):
    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    w7_id, _, w7_rev = await _hub(Session, WEEK_7)
    async with Session() as session:
        await session.execute(
            text(
                "UPDATE event_edges SET source = 'venue_grouping' WHERE parent_id = :cid "
                "AND child_type = 'event' AND child_id = :eid"
            ),
            {"cid": w7_id, "eid": events["s703"]},
        )
        await session.commit()

    runs = await _pass(Session, _schedule(W8))

    [held] = runs[WEEK_8]["relocation"]["foreign_source_holds"]
    assert held == {"event_id": events["s703"], "container": WEEK_7, "sources": ["venue_grouping"]}
    assert ("event", events["s703"]) in await _members(Session, WEEK_7)
    assert ("event", events["s703"]) in await _members(Session, WEEK_8)
    assert await _decisions(Session, WEEK_7) == []


# --- P7: a failure mid-move leaves both weeks as they were -----------------------


@pytest.mark.asyncio
async def test_p7_a_failure_after_the_old_week_lost_it_rolls_the_whole_move_back(
    world, monkeypatch
):
    import app.tasks.container_nfl_assembly as nfl

    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    hubs = [await _hub(Session, WEEK_7), await _hub(Session, WEEK_8)]
    members = [await _members(Session, WEEK_7), await _members(Session, WEEK_8)]

    async def boom(*args, **kwargs):
        raise RuntimeError("destination write failed")

    monkeypatch.setattr(nfl, "assemble_container", boom)
    runs = await _pass(Session, _schedule(W8))

    assert runs[WEEK_8]["terminal"] == "failed"
    assert [await _hub(Session, WEEK_7), await _hub(Session, WEEK_8)] == hubs
    assert [await _members(Session, WEEK_7), await _members(Session, WEEK_8)] == members
    assert await _decisions(Session, WEEK_7) == await _decisions(Session, WEEK_8) == []


# --- P8: a read that cannot vouch never removes ---------------------------------


def _skipped_receipt():
    from app.services.statpal_api import StatPalScheduleReceipt

    return StatPalScheduleReceipt(
        reason="missing_team", path="scores/tournament/stage[1]/week[7]/matches/match[9]",
        stage="Regular Season", week="Week 7", contest_id="s799", detail="no home team",
    )


def _duplicate(cid, rounds):
    from app.services.statpal_api import StatPalScheduleDuplicate

    return StatPalScheduleDuplicate(contest_id=cid, paths=("a", "b"), rounds=tuple(rounds))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "parse_skipped",
        "unreadable",
        "season_mismatch",
        "absent_from_schedule",
        "week_7_empty",
        "duplicate_rows",
        "conflicting_identity",
        "two_rows_of_ours",
        "capped_markets",
    ],
)
async def test_p8_a_read_that_cannot_vouch_never_removes_the_game(world, monkeypatch, case):
    from app.services.statpal_api import StatPalUpstreamError
    from app.utils.container_tournaments import NflSeasonDeclaration

    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    s703 = _game(events, markets, "s703")
    w7_before = await _hub(Session, WEEK_7)
    kwargs: dict = {}
    moved = _schedule(W8)
    if case == "parse_skipped":
        kwargs["skipped"] = [_skipped_receipt()]
    elif case == "unreadable":
        kwargs["error"] = StatPalUpstreamError("503")
    elif case == "season_mismatch":
        kwargs["declaration"] = NflSeasonDeclaration(season=2025)
    elif case == "absent_from_schedule":
        moved = [f for f in _schedule() if f.fixture_id != "s703"]
    elif case == "week_7_empty":
        moved = [f for f in _schedule() if f.fixture_id == "s801"]
    elif case == "duplicate_rows":
        kwargs["duplicates"] = [_duplicate("s703", [W8, W8])]
    elif case == "conflicting_identity":
        moved = _schedule(W8) + [_fixture("s703", "Eagles", "Giants", _at(10, 27, 0, 15), W7)]
    elif case == "two_rows_of_ours":
        await _seed(Session, sport_id, [_fixture("s703", "Eagles", "Giants", _at(10, 27, 0, 15), W8)])
    elif case == "capped_markets":
        import app.tasks.container_nfl_assembly as nfl

        original = nfl.gather_nfl_week_candidates

        async def capped(session, fixtures, target, *, limit=None, only_contests=None):
            return await original(session, fixtures, target, limit=1, only_contests=only_contests)

        monkeypatch.setattr(nfl, "gather_nfl_week_candidates", capped)

    runs = await _pass(Session, moved, **kwargs)

    assert s703 <= await _members(Session, WEEK_7), runs
    assert await _hub(Session, WEEK_7) == w7_before
    assert await _decisions(Session, WEEK_7) == []
    if case in ("duplicate_rows", "capped_markets"):
        # #10908 D1 unchanged: the week still holding a game it cannot prove says so.
        week_8 = runs[WEEK_8]["relocation"]
        assert week_8["moved"] == []
        assert runs[WEEK_7]["publication"]["reason"] in (
            "stored_members_differ", "market_read_truncated",
        )


# --- a destination outside the window ------------------------------------------


@pytest.mark.asyncio
async def test_a_game_moved_to_a_week_outside_the_window_still_moves_in_one_run(world):
    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    s703 = _game(events, markets, "s703")

    # Moved AND re-dated: Week 12's only kickoff is a month out of the window.
    moved = [f for f in _schedule() if f.fixture_id != "s703"] + [
        _fixture("s703", "Eagles", "Giants", _at(11, 23, 0, 15), W12)
    ]
    runs = await _pass(Session, moved)

    assert list(runs)[0] == WEEK_12
    run = runs[WEEK_12]
    assert (run["terminal"], run["reason"]) == ("partial", "relocation_only")
    assert run["relocation"]["only_contests"] == ["s703"]
    assert run["publication"] == {"decision": "not_evaluated", "reason": "relocation_only"}
    assert await _members(Session, WEEK_12) == s703
    assert not (s703 & await _members(Session, WEEK_7))
    _, state, _ = await _hub(Session, WEEK_12)
    assert state == "unpublished"  # not for readers until its own window proves it


# --- P9: a held-out edition, no source edit --------------------------------------


@pytest.mark.asyncio
async def test_p9_a_2027_preseason_game_moves_with_no_code_naming_it(world):
    from app.utils.container_tournaments import NflSeasonDeclaration

    Session, sport_id = world
    pre2, pre3 = "Pre Season / Week 2", "Pre Season / Week 3"

    def schedule(p2003_round):
        return [
            _fixture("p2001", "Colts", "Lions", _at(8, 12, 23, year=2027), pre2),
            _fixture("p2003", "Titans", "Saints", _at(8, 13, 23, year=2027), p2003_round),
            _fixture("p3001", "Broncos", "Cardinals", _at(8, 19, 0, year=2027), pre3),
            # The season is read off its regular-season kickoffs; outside the window.
            _fixture("r0101", "Ravens", "Steelers", _at(9, 10, 0, year=2027), "Regular Season / Week 1"),
        ]

    events, markets = await _seed(Session, sport_id, schedule(pre2))
    declaration = NflSeasonDeclaration(season=2027)
    now = _at(8, 11, 12, year=2027)
    first = await _pass(Session, schedule(pre2), now=now, declaration=declaration)
    assert set(first) == {"nfl-2027-preseason-week-2", "nfl-2027-preseason-week-3"}

    runs = await _pass(Session, schedule(pre3), now=now, declaration=declaration)

    moved = runs["nfl-2027-preseason-week-3"]["relocation"]["moved"]
    assert [m["event_id"] for m in moved] == [events["p2003"]]
    game = _game(events, markets, "p2003")
    assert not (game & await _members(Session, "nfl-2027-preseason-week-2"))
    assert game <= await _members(Session, "nfl-2027-preseason-week-3")


# --- a read that cannot vouch never brings a moved game back --------------------


@pytest.mark.asyncio
async def test_an_incomplete_newer_read_does_not_pull_a_moved_game_back(world):
    """After the move, a NEWER read files s703 under Week 7 again but dropped a
    row. It is newer, so it is admitted — but it cannot move anything, so Week 7
    withholds the game it lost by a move instead of holding it twice."""
    Session, sport_id = world
    events, markets = await _published_weeks_7_and_8(Session, sport_id)
    s703 = _game(events, markets, "s703")
    await _pass(Session, _schedule(W8))
    w7_before = await _hub(Session, WEEK_7)

    runs = await _pass(Session, _schedule(W7), skipped=[_skipped_receipt()])

    week_7 = runs[WEEK_7]["relocation"]
    assert (week_7["state"], week_7["reason"]) == ("inactive", "schedule_parse_incomplete")
    assert week_7["withheld_relocated_away"] == [events["s703"]]
    assert not (s703 & await _members(Session, WEEK_7))
    assert s703 <= await _members(Session, WEEK_8)
    assert await _hub(Session, WEEK_7) == w7_before
