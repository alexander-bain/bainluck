"""#5341 — the next NFL week publishes itself, end to end on a real server.

SHIP: the next authority-defined NFL week becomes a complete usable hub without
a per-week declaration or publication command; wrong or partial weeks stay
withheld and corrected hubs stay corrected. Pillars: MATCHING / DISCOVER / TRUTH.

Every test drives the MOUNTED path — `container_assembly.run_nfl_collection`
with the unchanged `NFL_2026` declaration, a schedule double for StatPal and a
clock — so the week is found, its row bootstrapped, assembled, decided on and
committed exactly as the hourly pass does it. Nothing calls the policy directly.

WHY A REAL DATABASE. The decision rides #9651's row lock, ledger and revision
column (created from the helper's own DDL, as every sibling gate does), and its
whole claim is about what is STORED: that a publish lands in the same commit
as the assembly that proved it, that a second pass adds no ledger row, that a
withdrawn hub or member stays withdrawn across a commit boundary, and that an
edge left behind by a game the authority moved is seen. A session double would
agree with whatever statement was built.
"""

from __future__ import annotations

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


def _at(m, d, h=17, minute=0):
    return datetime(2026, m, d, h, minute, tzinfo=timezone.utc)


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


def _week_7():
    """Three Week 7 games — a week no declaration, test or list names."""
    return [
        _fixture("s701", "Chiefs", "Raiders", _at(10, 23, 0, 15), W7),
        _fixture("s702", "Bills", "Jets", _at(10, 25), W7),
        _fixture("s703", "Eagles", "Giants", _at(10, 27, 0, 15), W7),
    ]


#: Week 7 is the only week with a kickoff inside [now - 2d, now + 9d].
WEEK_7_NOW = _at(10, 21, 12)
WEEK_7 = "nfl-2026-week-7"


class _Schedule:
    def __init__(self, fixtures=None, error=None):
        self.fixtures, self.error = fixtures, error

    async def get_schedule_fixtures(self, sport):
        assert sport == "nfl"
        if self.error is not None:
            raise self.error
        return list(self.fixtures)


@pytest.fixture
async def world(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Sport
    from app.services.database import Base
    from app.utils.container_corrections import UPGRADE_STATEMENTS

    monkeypatch.setenv(FLAG, "true")
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # The ledger references `containers`, so it goes first or drop_all wedges.
        await conn.execute(text("DROP TABLE IF EXISTS container_member_decisions"))
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        for statement in UPGRADE_STATEMENTS:
            await conn.execute(text(statement))

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        sport = Sport(key="americanfootball_nfl", name="NFL", active=True)
        session.add(sport)
        await session.commit()
        sport_id = sport.id

    yield Session, sport_id
    async with engine.begin() as conn:
        # Leave no FK onto `containers` behind: the next gate in the same job
        # runs a plain `drop_all`, which cannot drop `containers` past it.
        await conn.execute(text("DROP TABLE IF EXISTS container_member_decisions"))
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
    await engine.dispose()


async def _seed(Session, sport_id, games):
    """One event per ``(contest_id, home, away, kickoff)`` and one prop question
    on each. Returns ``{contest_id: event_id}``."""
    from app.models.models import Event, FuturesMarket

    ids = {}
    async with Session() as session:
        for cid, home, away, kickoff in games:
            event = Event(
                sport_id=sport_id,
                home_team_name=home,
                away_team_name=away,
                commence_time=kickoff,
                status="scheduled",
                statpal_fixture_id=cid,
            )
            session.add(event)
            await session.flush()
            session.add(
                FuturesMarket(
                    source="kalshi",
                    external_id=f"KXNFLPROP-{cid}-{event.id}",
                    sport_id=sport_id,
                    event_id=event.id,
                    name=f"{away} at {home}: total points over 44.5",
                    category="sports",
                    market_type="prop",
                    commence_time=kickoff,
                    status="open",
                )
            )
            ids[cid] = event.id
        await session.commit()
    return ids


def _games(fixtures):
    return [(f.fixture_id, f.home_team, f.away_team, f.start_time) for f in fixtures]


async def _pass(Session, fixtures, now, *, error=None):
    """One hourly pass's NFL half: its own session, committed per week."""
    from app.tasks import container_assembly as ca
    from app.utils.container_tournaments import NFL_2026

    async with Session() as session:
        runs = await ca.run_nfl_collection(
            session, NFL_2026, apply=True, now=now, service=_Schedule(fixtures, error)
        )
    return {r["slug"]: r for r in runs}


async def _hub(Session, slug):
    async with Session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT id, publication_state, membership_revision "
                    "FROM containers WHERE slug = :slug"
                ),
                {"slug": slug},
            )
        ).fetchone()
    return row


async def _ledger(Session, container_id):
    async with Session() as session:
        return (
            await session.execute(
                text(
                    "SELECT scope, action, actor, evidence, child_type, child_id "
                    "FROM container_corrections WHERE container_id = :cid ORDER BY id"
                ),
                {"cid": container_id},
            )
        ).fetchall()


async def _event_edges(Session, container_id):
    async with Session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT child_id FROM event_edges WHERE parent_type = 'container' "
                    "AND parent_id = :cid AND kind = 'contains' AND child_type = 'event'"
                ),
                {"cid": container_id},
            )
        ).fetchall()
    return {int(r[0]) for r in rows}


async def _read(Session, slug):
    from app.utils.container_corrections import read_published

    async with Session() as session:
        return await read_published(session, slug)


# --- the ship -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unseen_week_publishes_itself_under_its_stable_slug(world):
    from app.utils.container_nfl_publication import ACTOR, POLICY
    from app.utils.container_tournaments import DECLARED_COLLECTIONS, NFL_2026

    Session, sport_id = world
    fixtures = _week_7()
    events = await _seed(Session, sport_id, _games(fixtures))

    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    # The declaration is the season's, unchanged: no week was named anywhere.
    assert NFL_2026 in DECLARED_COLLECTIONS and not hasattr(NFL_2026, "week")
    assert list(runs) == [WEEK_7]
    run = runs[WEEK_7]
    assert run["terminal"] == "complete"
    assert run["publication"]["decision"] == "published"

    hub_id, state, revision = await _hub(Session, WEEK_7)
    assert state == "published"
    assert run["publication"]["revision"] == revision
    assert await _event_edges(Session, hub_id) == set(events.values())

    [row] = await _ledger(Session, hub_id)
    scope, action, actor, evidence, _, _ = row
    assert (scope, action, actor) == ("publication", "publish", ACTOR)
    assert evidence["policy"] == POLICY
    assert evidence["contest_ids"] == ["s701", "s702", "s703"]
    assert evidence["member_event_ids"] == sorted(events.values())

    read = await _read(Session, WEEK_7)
    assert read.state == "published"
    assert {m["id"] for m in read.members if m["type"] == "event"} == set(
        events.values()
    )


@pytest.mark.asyncio
async def test_preseason_and_regular_week_1_stay_two_hubs(world):
    Session, sport_id = world
    pre = _fixture("p101", "Lions", "Browns", _at(8, 7, 23), "Pre Season / Week 1")
    reg = _fixture("r101", "Ravens", "Bengals", _at(9, 13), "Regular Season / Week 1")
    events = await _seed(Session, sport_id, _games([pre, reg]))

    first = await _pass(Session, [pre, reg], _at(8, 6, 12))
    second = await _pass(Session, [pre, reg], _at(9, 11, 12))

    assert list(first) == ["nfl-2026-preseason-week-1"]
    assert list(second) == ["nfl-2026-week-1"]
    pre_hub = await _hub(Session, "nfl-2026-preseason-week-1")
    reg_hub = await _hub(Session, "nfl-2026-week-1")
    assert pre_hub[0] != reg_hub[0]
    assert (pre_hub[1], reg_hub[1]) == ("published", "published")
    assert await _event_edges(Session, pre_hub[0]) == {events["p101"]}
    assert await _event_edges(Session, reg_hub[0]) == {events["r101"]}


@pytest.mark.asyncio
async def test_a_rescheduled_game_stays_in_the_week_the_authority_files_it_under(world):
    Session, sport_id = world
    moved = _fixture("s703", "Eagles", "Giants", _at(10, 29, 23), W7)  # Week-8 dates
    fixtures = _week_7()[:2] + [moved, _fixture("s801", "Rams", "Seahawks", _at(10, 30), W8)]
    events = await _seed(Session, sport_id, _games(fixtures))

    runs = await _pass(Session, fixtures, _at(10, 28, 12))

    assert set(runs) == {WEEK_7, "nfl-2026-week-8"}
    week_7 = await _hub(Session, WEEK_7)
    week_8 = await _hub(Session, "nfl-2026-week-8")
    assert events["s703"] in await _event_edges(Session, week_7[0])
    assert await _event_edges(Session, week_8[0]) == {events["s801"]}
    assert (week_7[1], week_8[1]) == ("published", "published")


# --- wrong or partial weeks stay withheld --------------------------------------------


@pytest.mark.asyncio
async def test_a_week_missing_a_games_row_is_withheld_until_the_row_exists(world):
    Session, sport_id = world
    fixtures = _week_7()
    await _seed(Session, sport_id, _games(fixtures[:2]))

    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    run = runs[WEEK_7]
    assert run["terminal"] == "partial"
    assert run["publication"]["decision"] == "withheld"
    assert run["publication"]["reason"] == "contest_without_event_row"
    hub_id, state, _ = await _hub(Session, WEEK_7)
    assert state == "unpublished"
    assert await _ledger(Session, hub_id) == []
    # Members around the gap are kept; the claim is what is withheld.
    assert len(await _event_edges(Session, hub_id)) == 2

    await _seed(Session, sport_id, _games(fixtures[2:]))
    runs = await _pass(Session, fixtures, WEEK_7_NOW)
    assert runs[WEEK_7]["publication"]["decision"] == "published"


@pytest.mark.asyncio
async def test_two_rows_for_one_game_are_withheld(world):
    Session, sport_id = world
    fixtures = _week_7()
    await _seed(Session, sport_id, _games(fixtures))
    await _seed(Session, sport_id, _games(fixtures[1:2]))  # a second s702 row

    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    assert runs[WEEK_7]["publication"]["reason"] == "contest_with_duplicate_event_rows"
    assert (await _hub(Session, WEEK_7))[1] == "unpublished"


@pytest.mark.asyncio
async def test_an_unknown_season_publishes_nothing_and_creates_nothing(world):
    Session, sport_id = world
    fixtures = _week_7() + [
        _fixture("x1", "Bears", "Packers", datetime(2025, 10, 24, 17, tzinfo=timezone.utc), W7)
    ]
    await _seed(Session, sport_id, _games(fixtures))

    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    assert runs["nfl-2026"]["reason"] == "schedule_season_unknown"
    assert await _hub(Session, WEEK_7) is None


@pytest.mark.asyncio
async def test_a_game_the_authority_moved_away_leaves_an_edge_that_withholds(world, monkeypatch):
    Session, sport_id = world
    fixtures = _week_7()
    events = await _seed(Session, sport_id, _games(fixtures))
    monkeypatch.setenv(FLAG, "false")
    await _pass(Session, fixtures, WEEK_7_NOW)  # assembled, never published

    relabelled = fixtures[:2] + [
        _fixture("s703", "Eagles", "Giants", fixtures[2].start_time, W8)
    ]
    monkeypatch.setenv(FLAG, "true")
    runs = await _pass(Session, relabelled, WEEK_7_NOW)

    publication = runs[WEEK_7]["publication"]
    assert publication["decision"] == "withheld"
    assert publication["reason"] == "stored_members_differ"
    assert publication["difference"]["events_not_proved"] == [events["s703"]]
    assert (await _hub(Session, WEEK_7))[1] == "unpublished"


# --- idempotent, and corrected hubs stay corrected ---------------------------------


@pytest.mark.asyncio
async def test_a_second_pass_changes_nothing(world):
    Session, sport_id = world
    fixtures = _week_7()
    await _seed(Session, sport_id, _games(fixtures))

    await _pass(Session, fixtures, WEEK_7_NOW)
    before = await _hub(Session, WEEK_7)
    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    assert runs[WEEK_7]["publication"]["decision"] == "already_published"
    assert await _hub(Session, WEEK_7) == before
    assert len(await _ledger(Session, before[0])) == 1


@pytest.mark.asyncio
async def test_a_withdrawn_hub_is_never_republished(world):
    from app.utils.container_corrections import withdraw_publication

    Session, sport_id = world
    fixtures = _week_7()
    await _seed(Session, sport_id, _games(fixtures))
    await _pass(Session, fixtures, WEEK_7_NOW)
    hub_id = (await _hub(Session, WEEK_7))[0]
    async with Session() as session:
        await withdraw_publication(
            session, container_id=hub_id, reason="wrong edition", actor="alex"
        )
        await session.commit()

    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    assert runs[WEEK_7]["publication"]["decision"] == "withheld"
    assert runs[WEEK_7]["publication"]["reason"] == "publication_withdrawn"
    assert (await _hub(Session, WEEK_7))[1] == "withdrawn"
    assert [r[1] for r in await _ledger(Session, hub_id)] == ["publish", "withdraw"]
    assert (await _read(Session, WEEK_7)).state == "withdrawn"


@pytest.mark.asyncio
async def test_a_withdrawn_member_stays_out_and_a_hub_holding_one_waits_for_a_person(
    world, monkeypatch
):
    from app.utils.container_corrections import withdraw_member

    Session, sport_id = world
    fixtures = _week_7()
    events = await _seed(Session, sport_id, _games(fixtures))
    monkeypatch.setenv(FLAG, "false")
    await _pass(Session, fixtures, WEEK_7_NOW)
    hub_id = (await _hub(Session, WEEK_7))[0]
    async with Session() as session:
        await withdraw_member(
            session,
            container_id=hub_id,
            child_type="event",
            child_id=events["s702"],
            reason="not this week's game",
            actor="alex",
        )
        await session.commit()

    monkeypatch.setenv(FLAG, "true")
    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    assert events["s702"] not in await _event_edges(Session, hub_id)
    assert runs[WEEK_7]["publication"]["decision"] == "withheld"
    assert runs[WEEK_7]["publication"]["reason"] == "member_withdrawn"
    assert (await _hub(Session, WEEK_7))[1] == "unpublished"


@pytest.mark.asyncio
async def test_a_member_withdrawn_from_a_published_hub_is_not_resurrected(world):
    from app.utils.container_corrections import withdraw_member

    Session, sport_id = world
    fixtures = _week_7()
    events = await _seed(Session, sport_id, _games(fixtures))
    await _pass(Session, fixtures, WEEK_7_NOW)
    hub_id = (await _hub(Session, WEEK_7))[0]
    async with Session() as session:
        await withdraw_member(
            session,
            container_id=hub_id,
            child_type="event",
            child_id=events["s702"],
            reason="not this week's game",
            actor="alex",
        )
        await session.commit()

    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    assert events["s702"] not in await _event_edges(Session, hub_id)
    # A person's withdrawal is not drift: the published hub reads healthy.
    assert runs[WEEK_7]["publication"]["decision"] == "already_published"
    assert (await _hub(Session, WEEK_7))[1] == "published"
    assert [r[0] for r in await _ledger(Session, hub_id)] == ["publication", "member"]


@pytest.mark.asyncio
async def test_a_published_week_holding_a_game_the_authority_moved_says_so_and_changes_nothing(
    world,
):
    """Authority D1. Week 7 is published; the authority refiles s703 under Week 8.
    Week 8 publishes with it. Week 7 still holds its old edge — assembly never
    retires one — so it must read `retained: stored_members_differ`, never
    `already_published`, and must not write."""
    Session, sport_id = world
    fixtures = _week_7()
    s801 = _fixture("s801", "Rams", "Seahawks", _at(10, 30, 0, 15), W8)
    events = await _seed(Session, sport_id, _games(fixtures + [s801]))
    await _pass(Session, fixtures, WEEK_7_NOW)
    week_7_before = await _hub(Session, WEEK_7)
    assert week_7_before[1] == "published"

    refiled = fixtures[:2] + [
        _fixture("s703", "Eagles", "Giants", fixtures[2].start_time, W8),
        s801,
    ]
    runs = await _pass(Session, refiled, WEEK_7_NOW)

    publication = runs[WEEK_7]["publication"]
    assert publication["decision"] == "retained"
    assert publication["reason"] == "stored_members_differ"
    assert publication["difference"]["events_not_proved"] == [events["s703"]]
    assert await _hub(Session, WEEK_7) == week_7_before
    assert len(await _ledger(Session, week_7_before[0])) == 1

    assert runs["nfl-2026-week-8"]["publication"]["decision"] == "published"
    week_8 = await _hub(Session, "nfl-2026-week-8")
    assert await _event_edges(Session, week_8[0]) == {events["s703"], events["s801"]}


# --- our own rows say the schedule read is short (Authority D4) -----------------------


@pytest.mark.asyncio
async def test_a_stamped_game_in_the_week_that_the_read_omits_withholds(world):
    Session, sport_id = world
    fixtures = _week_7()
    await _seed(Session, sport_id, _games(fixtures))
    # Our row, stamped with a contest this read lists nowhere, at a Week 7 kickoff.
    await _seed(Session, sport_id, [("s799", "Cowboys", "Commanders", _at(10, 25, 20, 25))])

    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    assert runs[WEEK_7]["terminal"] == "complete"
    assert runs[WEEK_7]["publication"]["decision"] == "withheld"
    assert runs[WEEK_7]["publication"]["reason"] == "stamped_game_missing_from_schedule"
    assert (await _hub(Session, WEEK_7))[1] == "unpublished"


@pytest.mark.asyncio
async def test_unstamped_and_other_week_rows_in_the_span_stay_report_only(world):
    from app.models.models import Event

    Session, sport_id = world
    other_week = _fixture("s810", "Saints", "Falcons", _at(10, 25, 20, 25), W8)
    fixtures = _week_7() + [other_week]
    await _seed(Session, sport_id, _games(fixtures))
    async with Session() as session:  # a #2693 matching symptom: no contest id at all
        session.add(
            Event(
                sport_id=sport_id,
                home_team_name="Cardinals",
                away_team_name="Rams",
                commence_time=_at(10, 25),
                status="scheduled",
            )
        )
        await session.commit()

    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    assert runs[WEEK_7]["harvest"]["unidentified_in_span"] == 2
    assert runs[WEEK_7]["publication"]["decision"] == "published"


# --- a source outage keeps what readers already have ----------------------------------


@pytest.mark.asyncio
async def test_a_schedule_outage_keeps_the_published_hub(world):
    from app.services.statpal_api import StatPalUpstreamError

    Session, sport_id = world
    fixtures = _week_7()
    await _seed(Session, sport_id, _games(fixtures))
    await _pass(Session, fixtures, WEEK_7_NOW)
    before = await _hub(Session, WEEK_7)

    runs = await _pass(Session, fixtures, WEEK_7_NOW, error=StatPalUpstreamError("503"))

    assert runs["nfl-2026"]["terminal"] == "unavailable"
    assert runs["nfl-2026"]["reason"] == "schedule_unreadable"
    assert await _hub(Session, WEEK_7) == before
    assert len(await _ledger(Session, before[0])) == 1
    assert (await _read(Session, WEEK_7)).state == "published"


@pytest.mark.asyncio
async def test_a_published_week_that_reads_partial_is_retained_and_says_why(world):
    Session, sport_id = world
    fixtures = _week_7()
    await _seed(Session, sport_id, _games(fixtures))
    await _pass(Session, fixtures, WEEK_7_NOW)
    before = await _hub(Session, WEEK_7)
    extra = _fixture("s704", "Cowboys", "Commanders", _at(10, 26), W7)  # no row yet

    runs = await _pass(Session, fixtures + [extra], WEEK_7_NOW)

    assert runs[WEEK_7]["terminal"] == "partial"
    assert runs[WEEK_7]["publication"]["decision"] == "retained"
    assert runs[WEEK_7]["publication"]["reason"] == "contest_without_event_row"
    assert await _hub(Session, WEEK_7) == before


# --- dark by default -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_the_switch_off_a_complete_week_is_assembled_and_never_published(
    world, monkeypatch
):
    Session, sport_id = world
    fixtures = _week_7()
    await _seed(Session, sport_id, _games(fixtures))
    monkeypatch.delenv(FLAG, raising=False)

    runs = await _pass(Session, fixtures, WEEK_7_NOW)

    publication = runs[WEEK_7]["publication"]
    assert publication["decision"] == "disabled"
    assert publication["harvest_complete"] is True
    hub_id, state, _ = await _hub(Session, WEEK_7)
    assert state == "unpublished"
    assert await _ledger(Session, hub_id) == []
    assert (await _read(Session, WEEK_7)).state == "unpublished"
