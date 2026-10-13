"""#1541 — a championship the provider WITHDREW stops reading as live, and is never called final.

WHAT A READER SEES TODAY. ``https://bainluck.com/futures/10`` (390px, 2026-10-12
14:08Z): *FIFA World Cup Winner*, no settled language, "No current prices", and a
"Games This Week" strip of MLS fixtures — for a tournament Spain won on
2026-07-19. The row is ``odds_api``, ``status='open'``, last written
2026-07-19 20:38Z; The Odds API stopped listing its sport key after the final, so
the poller stopped visiting it, and nothing else ever owns an odds_api futures row.

WHAT IT MUST NOT BECOME (review of PR #10938): a listing gap plus quote silence
proves the market is unavailable, not that the tournament ended — a FUTURE
championship the provider drops for eight days meets the same evidence. So the
transition is ``status='withdrawn'`` (never ``resolved``, never ``settled_at``),
and the 2027 board below proves it end to end, through the served detail payload.

The round trip is the REAL ``_poll_futures_odds`` (and, for the crowner arms, the
REAL ``_backfill_from_current_probability``) against REAL Postgres, with two
seams: the venue (stubbed listing + payload) and the connection. Every arm
asserts on the rows THIS file seeded, never on whole-table counts — the CI
database is shared with the steps before it.
"""

from __future__ import annotations

import json
import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres provider-closed "
            "championship round trip (CI job `database-integration` provides one)"
        ),
    ),
]

# Keys shaped like the provider's, unique to this file so cleanup is scoped.
DEAD = "soccer_t1541_world_cup_winner"          # the specimen: closed, unquoted since the final
LIVE = "golf_t1541_masters_tournament_winner"   # control: listed and priced this poll
RECENT = "basketball_t1541_championship_winner"  # control: unlisted, quoted 2 days ago
QUIET_LISTED = "icehockey_t1541_stanley_cup_winner"  # guard: listed, nothing quoted for weeks
GRADED_KEY = "americanfootball_t1541_super_bowl_winner"  # guard: unlisted + quiet, but already graded
FUTURE = "basketball_t1541_nba_championship_winner"  # THE COUNTEREXAMPLE: 2027 Finals ahead, unlisted + quiet 8 days
CROWN_KEYS = ("t1541_crown_retired_a", "t1541_crown_retired_b", "t1541_crown_control_a", "t1541_crown_control_b")
ALL_KEYS = (DEAD, LIVE, RECENT, QUIET_LISTED, GRADED_KEY, FUTURE) + CROWN_KEYS

#: The 2027 board's provider identity, shaped like production market 2's
#: (read 2026-10-12): the decisive game is eight months away.
FUTURE_IDENTITY = {"scope": "current_quotes_only", "event_id": "t1541-nba-2027",
                   "sport_key": FUTURE, "commence_time": "2027-06-19T00:40:00+00:00"}

FINAL_DAY_AGO = 85  # 2026-07-19 → 2026-10-12


def _book(names_probs, *, event_id=None, commence=None, sport_key=None):
    return SimpleNamespace(
        bookmaker="draftkings",
        market_name="Test Winner",
        event_id=event_id,
        event_commence_time=commence,
        sport_key=sport_key,
        outcomes=[
            SimpleNamespace(name=n, probability=p, american_odds=int(100 / p - 100) if p < 0.5 else -int(100 * p / (1 - p)))
            for n, p in names_probs
        ],
    )


#: Sentinel: store SQL NULL — what production's Core ``pg_insert`` leaves when it
#: omits the column. A plain ``None`` through the ORM stores JSON ``null``
#: instead (the JSONB type's ``none_as_null`` is False), a different value.
SQL_NULL = object()


async def _seed_market(session, key, *, status="open", touched, legs, metadata=SQL_NULL, external_id=None):
    from sqlalchemy import null

    from app.models.models import FuturesMarket, FuturesOutcome

    if metadata is SQL_NULL:
        metadata = null()

    market = FuturesMarket(
        source="odds_api",
        external_id=external_id or key,
        sport_id=None,
        name=f"Test {key}",
        category="championship",
        mutually_exclusive=True,
        status=status,
        market_metadata=metadata,
        updated_at=touched,
    )
    session.add(market)
    await session.flush()
    for name, prob, seen in legs:
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=name,
                name=name,
                current_probability=prob,
                opening_probability=prob,
                last_updated=seen,
                # Production's stored shape for an ungraded leg: the column
                # default False, resolution_source NULL (CAL-P1004R).
                is_winner=False,
                resolution_source=None,
            )
        )
    await session.commit()
    return market.id


async def _seed_the_board(session):
    now = datetime.now(timezone.utc)
    final = now - timedelta(days=FINAL_DAY_AGO)
    ids = {}
    # JSON ``null`` metadata on the specimen on purpose: ``COALESCE`` keeps it and
    # ``null || {...}`` is an array, which this round trip caught in the first
    # cut of the retirement. Every other row carries production's SQL NULL.
    ids[DEAD] = await _seed_market(
        session, DEAD, touched=final + timedelta(minutes=8), metadata=None,
        legs=[("Spain", 0.587142, final), ("Argentina", 0.412858, final), ("England", 0.0, final - timedelta(days=3))],
    )
    ids[LIVE] = await _seed_market(
        session, LIVE, touched=now - timedelta(hours=4),
        legs=[("Scottie Scheffler", 0.13, now - timedelta(hours=4)), ("Rory McIlroy", 0.07, now - timedelta(hours=4))],
    )
    two_days = now - timedelta(days=2)
    ids[RECENT] = await _seed_market(
        session, RECENT, touched=two_days,
        legs=[("Thunder", 0.6, two_days), ("Pacers", 0.4, two_days)],
    )
    ids[QUIET_LISTED] = await _seed_market(
        session, QUIET_LISTED, touched=final,
        legs=[("Panthers", 0.55, final), ("Oilers", 0.45, final)],
    )
    ids[GRADED_KEY] = await _seed_market(
        session, GRADED_KEY, touched=final,
        legs=[("Eagles", 0.99, final), ("Chiefs", 0.01, final)],
    )
    # A venue already put a verdict on one leg: resolving the board under a
    # no-winner reason would contradict it.
    await session.execute(
        text("UPDATE futures_outcomes SET is_winner = true, resolution_source = 'api_settlement' "
             "WHERE market_id = :i AND name = 'Eagles'"),
        {"i": ids[GRADED_KEY]},
    )
    eight_days = now - timedelta(days=8)
    ids[FUTURE] = await _seed_market(
        session, FUTURE, touched=eight_days, metadata={"odds_api_current_event": FUTURE_IDENTITY},
        legs=[("Thunder", 0.31, eight_days), ("Nuggets", 0.12, eight_days), ("Celtics", 0.09, eight_days)],
    )
    await session.commit()
    return ids


async def _served_detail(session, market_id):
    """What `/api/futures/{id}` formats for this row: the REAL formatter over the
    REAL row and its legs, as the route loads them."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket
    from app.routes.futures import _format_market_detail

    session.expire_all()
    market = (await session.execute(
        select(FuturesMarket).options(selectinload(FuturesMarket.outcomes),
                                      selectinload(FuturesMarket.sport))
        .where(FuturesMarket.id == market_id)
    )).scalar_one()
    return _format_market_detail(market, None, set())


async def _run_poll(session, *, listed, responses):
    """The REAL task. ``responses`` maps sport key -> list of parsed books."""
    service = SimpleNamespace(
        get_sports_with_outrights=AsyncMock(return_value=[{"key": k} for k in listed]),
        get_futures_odds=AsyncMock(side_effect=lambda sport_key, regions="us": sport_key),
        _parse_futures=lambda response, sport_key: responses.get(sport_key, []),
        last_requests_used=1,
        last_requests_remaining=None,
        close=AsyncMock(),
    )

    @asynccontextmanager
    async def _session_cm():
        yield session

    with ExitStack() as es:
        es.enter_context(patch("app.tasks.futures.OddsAPIService", return_value=service))
        es.enter_context(patch("app.tasks.futures.get_task_session", _session_cm))
        es.enter_context(patch("app.tasks.redis_state.check_quota_guard", return_value=(True, "test")))
        from app.tasks.futures import _poll_futures_odds

        stats = await _poll_futures_odds()
    assert stats["errors"] == [], f"the poll reported errors: {stats['errors']}"
    await session.commit()
    return stats


async def _market(session, market_id):
    row = (await session.execute(
        text("SELECT status, external_id, market_metadata, settled_at FROM futures_markets WHERE id = :i"),
        {"i": market_id},
    )).one()
    meta = row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}")
    return {"status": row[0], "external_id": row[1], "meta": meta, "settled_at": row[3]}


async def _legs(session, market_id):
    rows = (await session.execute(
        text("SELECT name, current_probability, is_winner, resolution_source FROM futures_outcomes WHERE market_id = :i"),
        {"i": market_id},
    )).fetchall()
    return {r[0]: {"prob": None if r[1] is None else float(r[1]), "won": r[2], "source": r[3]} for r in rows}


async def _ids_on_key(session, key):
    rows = (await session.execute(
        text("SELECT id, status FROM futures_markets WHERE source = 'odds_api' AND external_id = :k"), {"k": key},
    )).fetchall()
    return [(r[0], r[1]) for r in rows]


def _fk_closure(metadata, *names):
    want, seen = list(names), set()
    while want:
        name = want.pop()
        if name in seen:
            continue
        seen.add(name)
        for fk in metadata.tables[name].foreign_keys:
            want.append(fk.column.table.name)
    return [metadata.tables[n] for n in seen]


# Scoped by key PREFIX-or-retired-suffix so a retired row is cleaned too. The
# pattern is a bind parameter, never inline text (gotcha #45).
_CLEAN = (
    """DELETE FROM futures_odds_snapshots s USING futures_outcomes o, futures_markets m
        WHERE s.outcome_id = o.id AND o.market_id = m.id AND m.external_id LIKE :p""",
    """DELETE FROM futures_outcomes o USING futures_markets m
        WHERE o.market_id = m.id AND m.external_id LIKE :p""",
    "DELETE FROM futures_markets WHERE external_id LIKE :p",
)


@pytest.fixture
async def pg_session():
    """Create what is missing, delete only this file's rows — never drop (see #5869's rig)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401
    from app.services.database import Base

    tables = _fk_closure(Base.metadata, "sports", "futures_markets", "futures_outcomes", "futures_odds_snapshots")
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        for stmt in _CLEAN:
            await conn.execute(text(stmt), {"p": "%t1541%"})
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


LISTING = [LIVE, QUIET_LISTED]


def _responses():
    return {LIVE: [_book([("Scottie Scheffler", 0.14), ("Rory McIlroy", 0.08)])]}


class TestTheWithdrawnChampionshipStopsBeingLive:
    async def test_the_specimen_is_withdrawn_not_settled(self, pg_session):
        ids = await _seed_the_board(pg_session)
        stats = await _run_poll(pg_session, listed=LISTING, responses=_responses())

        assert ids[DEAD] in stats["provider_delisted_retired"], stats
        got = await _market(pg_session, ids[DEAD])
        assert got["status"] == "withdrawn"
        assert got["settled_at"] is None
        assert "resolution_gate" not in got["meta"]
        record = got["meta"]["odds_api_retirement"]
        assert record["rolling_key"] == DEAD
        assert record["reason"] == "provider_stopped_listing"

    async def test_the_rolling_key_is_released(self, pg_session):
        ids = await _seed_the_board(pg_session)
        await _run_poll(pg_session, listed=LISTING, responses=_responses())

        got = await _market(pg_session, ids[DEAD])
        final_day = (datetime.now(timezone.utc) - timedelta(days=FINAL_DAY_AGO)).date().isoformat()
        assert got["external_id"] == f"{DEAD}:retired:{final_day}"
        assert await _ids_on_key(pg_session, DEAD) == []

    async def test_no_leg_is_graded_and_no_price_is_touched(self, pg_session):
        """The provider never said who won. Nobody is crowned, nobody marked Lost."""
        ids = await _seed_the_board(pg_session)
        await _run_poll(pg_session, listed=LISTING, responses=_responses())

        legs = await _legs(pg_session, ids[DEAD])
        assert {n: leg["source"] for n, leg in legs.items()} == {"Spain": None, "Argentina": None, "England": None}
        assert legs["Spain"]["prob"] == pytest.approx(0.587142)
        assert legs["Argentina"]["prob"] == pytest.approx(0.412858)
        assert all(leg["won"] is False for leg in legs.values())


class TestAFutureChampionshipIsNeverCalledFinal:
    """THE REVIEW COUNTEREXAMPLE. Same evidence as market 10, competition ahead."""

    async def test_it_is_withdrawn_never_resolved(self, pg_session):
        ids = await _seed_the_board(pg_session)
        stats = await _run_poll(pg_session, listed=LISTING, responses=_responses())

        assert ids[FUTURE] in stats["provider_delisted_retired"], stats
        got = await _market(pg_session, ids[FUTURE])
        assert got["status"] == "withdrawn" and got["status"] != "resolved"
        assert got["settled_at"] is None
        assert "resolution_gate" not in got["meta"]
        legs = await _legs(pg_session, ids[FUTURE])
        assert {leg["source"] for leg in legs.values()} == {None}
        assert all(leg["won"] is False for leg in legs.values())

    async def test_the_served_detail_is_unavailable_not_final(self, pg_session):
        """The reader seam: status `withdrawn` (the page's "Final Results" and
        settled hero key on `resolved` only), every price withheld, rows kept."""
        ids = await _seed_the_board(pg_session)
        await _run_poll(pg_session, listed=LISTING, responses=_responses())

        detail = await _served_detail(pg_session, ids[FUTURE])
        assert detail["status"] == "withdrawn"
        assert {o["name"] for o in detail["outcomes"]} == {"Thunder", "Nuggets", "Celtics"}
        assert {o["probability"] for o in detail["outcomes"]} == {None}
        assert detail["prices_withheld"] == 3

    async def test_the_live_control_is_served_with_prices(self, pg_session):
        """Anti-vacuity for the arm above, same poll, same formatter."""
        ids = await _seed_the_board(pg_session)
        await _run_poll(pg_session, listed=LISTING, responses=_responses())

        detail = await _served_detail(pg_session, ids[LIVE])
        assert detail["status"] == "open"
        assert any(o["probability"] is not None for o in detail["outcomes"])


class TestHealthyAndFutureTournamentsStayOpen:
    async def test_a_listed_live_field_is_untouched(self, pg_session):
        ids = await _seed_the_board(pg_session)
        stats = await _run_poll(pg_session, listed=LISTING, responses=_responses())

        got = await _market(pg_session, ids[LIVE])
        assert got["status"] == "open" and got["external_id"] == LIVE
        assert "resolution_gate" not in got["meta"]
        assert ids[LIVE] not in stats["provider_delisted_retired"]
        # Re-priced by THIS poll (the aggregator de-vigs: 0.14 / (0.14 + 0.08)).
        assert (await _legs(pg_session, ids[LIVE]))["Scottie Scheffler"]["prob"] == pytest.approx(0.14 / 0.22, abs=0.001)

    async def test_an_unlisted_board_quoted_two_days_ago_waits(self, pg_session):
        ids = await _seed_the_board(pg_session)
        stats = await _run_poll(pg_session, listed=LISTING, responses=_responses())

        got = await _market(pg_session, ids[RECENT])
        assert got["status"] == "open" and got["external_id"] == RECENT
        assert ids[RECENT] not in stats["provider_delisted_retired"]

    async def test_a_listed_board_with_nothing_quoted_is_flagged_not_closed(self, pg_session):
        """The stale-unsettled guard: the case nothing closes is reported, not guessed."""
        ids = await _seed_the_board(pg_session)
        stats = await _run_poll(pg_session, listed=LISTING, responses=_responses())

        got = await _market(pg_session, ids[QUIET_LISTED])
        assert got["status"] == "open" and got["external_id"] == QUIET_LISTED
        flagged = {f["id"]: f["verdict"] for f in stats["stale_unsettled"]}
        assert flagged.get(ids[QUIET_LISTED]) == "stale_listed", stats["stale_unsettled"]

    async def test_a_board_that_already_carries_a_verdict_is_flagged_not_closed(self, pg_session):
        ids = await _seed_the_board(pg_session)
        stats = await _run_poll(pg_session, listed=LISTING, responses=_responses())

        got = await _market(pg_session, ids[GRADED_KEY])
        assert got["status"] == "open" and got["external_id"] == GRADED_KEY
        assert "resolution_gate" not in got["meta"]
        flagged = {f["id"]: f["verdict"] for f in stats["stale_unsettled"]}
        assert flagged.get(ids[GRADED_KEY]) == "graded", stats["stale_unsettled"]

    async def test_a_listing_that_cannot_testify_retires_nothing(self, pg_session):
        """An empty listing is a response shape, not a closure (gotcha #53)."""
        ids = await _seed_the_board(pg_session)
        stats = await _run_poll(pg_session, listed=[], responses={})

        assert stats["provider_delisted_pass"] == "skipped_listing_cannot_testify"
        assert (await _market(pg_session, ids[DEAD]))["status"] == "open"


class TestTheNextEditionGetsItsOwnRow:
    async def test_a_relisted_key_with_a_new_edition_does_not_overwrite_the_finished_one(self, pg_session):
        ids = await _seed_the_board(pg_session)
        await _run_poll(pg_session, listed=LISTING, responses=_responses())

        nxt = {**_responses(), DEAD: [_book([("Spain", 0.18), ("France", 0.16)],
                                            event_id="wc2030", commence="2030-06-08T18:00:00Z", sport_key=DEAD)]}
        stats = await _run_poll(pg_session, listed=LISTING + [DEAD], responses=nxt)

        on_key = await _ids_on_key(pg_session, DEAD)
        assert len(on_key) == 1 and on_key[0][0] != ids[DEAD] and on_key[0][1] == "open"
        finished = await _market(pg_session, ids[DEAD])
        assert finished["status"] == "withdrawn"
        assert (await _legs(pg_session, ids[DEAD]))["Spain"]["prob"] == pytest.approx(0.587142)
        assert ids[DEAD] not in stats.get("provider_delisted_reopened", [])

    async def test_the_same_provider_edition_reopens_its_own_row(self, pg_session):
        """A false retirement (provider paused, then resumed the SAME event) is undone."""
        now = datetime.now(timezone.utc)
        final = now - timedelta(days=FINAL_DAY_AGO)
        identity = {"event_id": "same-edition", "commence_time": "2026-06-11T19:00:00+00:00",
                    "sport_key": DEAD, "polled_at": final.isoformat(), "scope": "current_quotes_only"}
        dead = await _seed_market(
            pg_session, DEAD, touched=final, metadata={"odds_api_current_event": identity},
            legs=[("Spain", 0.55, final), ("Argentina", 0.45, final)],
        )
        await _run_poll(pg_session, listed=LISTING, responses=_responses())
        assert (await _market(pg_session, dead))["status"] == "withdrawn"

        resumed = {**_responses(), DEAD: [_book([("Spain", 0.6), ("Argentina", 0.4)],
                                                event_id="same-edition", commence="2026-06-11T19:00:00Z", sport_key=DEAD)]}
        stats = await _run_poll(pg_session, listed=LISTING + [DEAD], responses=resumed)

        assert dead in stats.get("provider_delisted_reopened", []), stats
        got = await _market(pg_session, dead)
        assert got["status"] == "open" and got["external_id"] == DEAD and got["settled_at"] is None
        assert got["meta"]["odds_api_retirement"]["reopened_at"]
        assert await _ids_on_key(pg_session, DEAD) == [(dead, "open")]
        assert (await _legs(pg_session, dead))["Spain"]["prob"] == pytest.approx(0.6, abs=0.02)


class TestPriceCrownersLeaveAWithdrawnBoardUngraded:
    """``clean_resolution`` (all legs >=0.95/<=0.05) and ``all_losers`` (max <=0.10)
    run over every RESOLVED market. A withdrawn board's last quote is not a result,
    and its status keeps it out of both; the controls — same shapes, resolved —
    prove both passes ran in this very call."""

    async def test_neither_crowner_grades_a_withdrawn_board(self, pg_session):
        from app.utils.odds_api_retirement import (
            WITHDRAWN_STATUS,
            retired_external_id,
            retirement_metadata,
        )

        now = datetime.now(timezone.utc)
        old = now - timedelta(days=40)
        clean_shape = [("A", 0.04, old), ("B", 0.03, old)]   # Pass 1 shape (and Pass 4)
        losers_shape = [("A", 0.08, old), ("B", 0.06, old)]  # Pass 4 only

        def withdrawn_meta(key):
            return retirement_metadata(rolling_key=key, last_observed_at=old, checked_at=now)

        ra, rb, ca, cb = CROWN_KEYS
        ids = {
            "ra": await _seed_market(pg_session, ra, status=WITHDRAWN_STATUS, touched=old, legs=clean_shape,
                                     metadata=withdrawn_meta(ra), external_id=retired_external_id(ra, old)),
            "rb": await _seed_market(pg_session, rb, status=WITHDRAWN_STATUS, touched=old, legs=losers_shape,
                                     metadata=withdrawn_meta(rb), external_id=retired_external_id(rb, old)),
            "ca": await _seed_market(pg_session, ca, status="resolved", touched=old, legs=clean_shape),
            "cb": await _seed_market(pg_session, cb, status="resolved", touched=old, legs=losers_shape),
        }

        @asynccontextmanager
        async def _session_cm():
            yield pg_session

        import importlib

        backfill = importlib.import_module("app.tasks.backfill_winners")
        with patch.object(backfill, "get_task_session", _session_cm):
            stats = await backfill._backfill_from_current_probability()
        assert stats["errors"] == [], stats["errors"]

        for control in ("ca", "cb"):
            sources = {leg["source"] for leg in (await _legs(pg_session, ids[control])).values()}
            assert None not in sources, f"control {control} was not graded, so the pass never ran: {sources}"
        for withdrawn in ("ra", "rb"):
            legs = await _legs(pg_session, ids[withdrawn])
            assert {leg["source"] for leg in legs.values()} == {None}, (
                f"withdrawn board {withdrawn} was price-graded {legs} — a provider-withdrawn "
                "board's last quote is not a result"
            )
