"""Both live Kalshi poll branches feed `_kalshi_commence_time` into the upsert.

`KALSHI-GAME-COMMENCE-WIRING-GUARD` — the nonblocking follow-up CERT-2026 named
by name (#3433, lane1b/055):

    add an AST or driver-level assertion that both active single- and
    multi-market poll paths call `_kalshi_commence_time` and feed its result to
    the upsert.

## the gap this closes

#3433 taught the poll to store a game's `occurrence_datetime` — when the thing
actually happens — instead of `close_time`, which for a game market is a
multi-day settlement backstop (measured at the venue 2026-09-06: NFL +3d, MLB
+4d, UFC and tennis +14d). A UFC fight on Sep 8 was dated Sep 22, and a user
searching the fighter saw "Sep 22 7:00 PM".

The repair is one helper consumed at two call sites — the single-market branch
and the multi-market branch of `_poll_kalshi_markets`. Every test shipped with
it (`test_kalshi_game_commence_from_occurrence.py`) calls `_kalshi_commence_time`
DIRECTLY. So the helper is thoroughly proved and its WIRING is not proved at
all: revert either call site to `close_time`, or drop `commence_time` from
`update_set`, and all 13 of those assertions stay green while the production
defect returns in full.

## why the sentinel arms, and not just value equality

Asserting "the stored value equals the occurrence" is necessary but not
sufficient: a call site that computed the occurrence ITSELF, without calling the
helper, would satisfy it, and so would one that read `markets[0].occurrence_
datetime` directly — losing the `is_game` scope and the `occ <= close` bound
that make the helper safe on outrights.

So the two `..._feeds_the_helpers_result_to_the_upsert` arms patch
`_kalshi_commence_time` to return a value NOTHING in the fixture carries
(`SENTINEL`, 2031) and require that value to come back out of the server. That
is the wiring claim stated directly: whatever the helper returns is what the row
gets. Each of those arms also asserts WHICH branch ran, by reading the call's
own arguments — one market for the single-market branch, all three for the
multi-market branch — because a single mock satisfied twice proves one wire
twice, not two wires.

## why a real server

`commence_time` is written in TWO halves of one statement — `upsert_values` (the
INSERT arm) and `update_set` (the `on_conflict_do_update` arm) — and the second
one runs on every beat after the first. A statement-shape assertion reads the
values the caller passed and therefore agrees with the caller by construction;
only a round trip distinguishes "the poll built a dict" from "the row holds the
right instant". `test_the_conflict_arm_carries_the_helpers_result_too` is the
arm that covers the half a first-insert-only test cannot reach.

There is no local Postgres in the agent sandbox (`initdb` fails on `shmget`), so
**CI is the environment that runs this** — the `search-recall` job, alongside
`test_gap_create_grade_real_postgres.py`, whose three-seam rig this reuses.

## the control that keeps it honest

`test_a_non_game_outright_keeps_its_close_time` drives an event whose occurrence
is EARLIER than its close and requires the close to win, because the helper is
deliberately scoped to game tickers: `occurrence_datetime` is populated on
outrights too, where it means something else. Without that arm this file would
pass just as well against "always prefer the occurrence", which is a different
and wrong repair.

The fixture's own premises are asserted at import (`KICKOFF < CLOSE`, the
sentinel matching neither): if a later edit collapses them, these arms would
pass without discriminating anything, which is the failure mode a guard cannot
report about itself.

## deliberately NOT covered here

`_create_settled_market` (the gap-create backfill) is a THIRD commence writer and
still computes `min(close_times)` — the pre-#3433 shape. It is out of this
guard's named scope (the follow-up says "both active poll branches") and its harm
is much smaller, because a settled market's close_time has already collapsed to
its real settlement instant. Filed against #3433 rather than widened into a
test-only diff.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from app.services.kalshi_api import KalshiEvent, KalshiMarket

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres Kalshi "
            "commence-wiring round trip (CI job `search-recall` provides one)"
        ),
    ),
]

# An NFL game and its settlement backstop, at the venue's measured +3d drift.
KICKOFF = datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc)
CLOSE = KICKOFF + timedelta(days=3)

# A value nothing in any fixture carries, so a row holding it can only have got
# it from the helper's return.
SENTINEL = datetime(2031, 3, 3, 3, 3, 3, tzinfo=timezone.utc)

# Fixture premises, asserted where they are stated. Each arm below discriminates
# only because these hold; a later edit that collapses them would leave the arms
# green and meaningless.
assert KICKOFF < CLOSE, "the occurrence must differ from the close, or nothing is proved"
assert SENTINEL not in (KICKOFF, CLOSE), "the sentinel must match no fixture value"


@pytest.fixture
async def pg_session():
    """Real Postgres with the real schema.

    Function-scoped, following `test_gap_create_grade_real_postgres.py`:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that created its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


def _market(event_ticker, suffix, name, price, *, occurrence, close=CLOSE):
    """One priced Kalshi market.

    The book is tight and two-sided so `_kalshi_yes_probability` takes the
    midpoint rather than returning None — an unpriced leg is skipped before the
    upsert, and the round trip would have nothing to read.
    """
    return KalshiMarket(
        ticker=f"{event_ticker}-{suffix}",
        event_ticker=event_ticker,
        title=name,
        yes_sub_title=name,
        status="active",
        close_time=close,
        occurrence_datetime=occurrence,
        yes_bid=price - 0.01,
        yes_ask=price + 0.01,
        last_price=price,
        volume=1500,
    )


def _single_market_game(event_ticker="KXNFLGAME-26SEP13BUFNYJ", *, occurrence=KICKOFF):
    """A game event with exactly one market — the `len(event.markets) == 1` branch."""
    return KalshiEvent(
        event_ticker=event_ticker,
        title="Bills at Jets",
        category="Football",
        mutually_exclusive=True,
        markets=[_market(event_ticker, "BUF", "Bills", 0.62, occurrence=occurrence)],
    )


def _multi_market_game(event_ticker="KXNFLGAME-26SEP13KCDEN"):
    """A game event with three markets — the `else` branch.

    The occurrences are staggered so the arm reading the stored value is also
    asserting the helper's "earliest start across the event" rule, not merely
    that some occurrence was used.
    """
    return KalshiEvent(
        event_ticker=event_ticker,
        title="Chiefs at Broncos",
        category="Football",
        mutually_exclusive=True,
        markets=[
            _market(
                event_ticker, "KC", "Chiefs", 0.62,
                occurrence=KICKOFF + timedelta(minutes=20),
            ),
            # The earliest, deliberately not first in the list.
            _market(event_ticker, "DEN", "Broncos", 0.51, occurrence=KICKOFF),
            _market(
                event_ticker, "TIE", "Tie", 0.20,
                occurrence=KICKOFF + timedelta(minutes=10),
            ),
        ],
    )


async def _run_poll(session, events, *, commence_patch=None):
    """Run the REAL `_poll_kalshi_markets` against this Postgres session.

    Three seams, all of them the task's own boundaries rather than anything
    inside the write path:

    * `KalshiAPIService` — the network. `get_all_events` returns `events`.
    * `get_task_session` — the connection. Yields OUR session and does not close
      it, so the assertions can read the same server afterwards. The poll
      re-enters this CM in its post-loop fixups; re-yielding one session is
      correct for that.
    * `get_redis_client` — raised, so `_phase_rc` is None and every phase
      marker/cursor/discovery-cache branch takes its own no-op path. It also
      makes `_golf_commence_fix_enabled()` return False, so the golf fix-up
      stays a dry run and cannot rewrite what we are about to read.

    The hockey and tennis post-loop fix-ups DO run, and are why every fixture
    here is football: they are scoped by `llm_sport_category` in SQL and match
    zero of these rows.

    `commence_patch`, when given, replaces `_kalshi_commence_time` for the run
    and is returned so the caller can read which branch called it with what.
    """
    service = MagicMock()
    service.get_all_events = AsyncMock(return_value=events)
    service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm():
        yield session

    stack = [
        patch("app.services.kalshi_api.KalshiAPIService", return_value=service),
        patch("app.tasks.kalshi.get_task_session", _session_cm),
        patch(
            "app.tasks.redis_state.get_redis_client",
            side_effect=RuntimeError("no Redis in this gate — take the None branch"),
        ),
        patch.dict(os.environ, {"KALSHI_API_KEY": "test-key"}),
    ]
    if commence_patch is not None:
        stack.append(
            patch("app.tasks.kalshi._kalshi_commence_time", commence_patch)
        )

    from contextlib import ExitStack

    with ExitStack() as es:
        for cm in stack:
            es.enter_context(cm)
        from app.tasks.kalshi import _poll_kalshi_markets

        stats = await _poll_kalshi_markets()

    # The poll swallows per-event and top-level failures into `stats["errors"]`
    # (it must: one bad event may not wipe a whole ingest). Unasserted, a gate
    # driving it would read a silently-skipped event as a passing round trip —
    # gotcha #53's class.
    assert stats["errors"] == [], f"the poll reported errors: {stats['errors']}"
    assert stats["events_processed"] == len(events), (
        f"the poll processed {stats['events_processed']}/{len(events)} events — "
        "the fixture never reached the upsert loop, so nothing below is a round "
        f"trip. stats: {stats}"
    )
    await session.commit()
    return stats


async def _stored_commence(session, external_id):
    """Read the instant back out of the SERVER, not the ORM identity map."""
    return (
        await session.execute(
            text(
                "SELECT commence_time FROM futures_markets "
                "WHERE source = 'kalshi' AND external_id = :t"
            ),
            {"t": external_id},
        )
    ).scalar_one()


def _utc(dt):
    """Postgres may hand back a naive datetime depending on the column type."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# The value the two branches actually store.
# --------------------------------------------------------------------------


async def test_single_market_game_stores_the_occurrence_not_the_close(pg_session):
    """The `len(event.markets) == 1` branch, end to end."""
    event = _single_market_game()
    await _run_poll(pg_session, [event])

    stored = _utc(await _stored_commence(pg_session, event.event_ticker))
    assert stored == KICKOFF, (
        f"the single-market branch stored {stored}, expected the occurrence "
        f"{KICKOFF}. Stored {CLOSE} means the branch is back on the settlement "
        "backstop and #3433's defect has returned for every single-market game."
    )


async def test_multi_market_game_stores_the_earliest_occurrence(pg_session):
    """The `else` branch, end to end, including the earliest-across-markets rule."""
    event = _multi_market_game()
    await _run_poll(pg_session, [event])

    stored = _utc(await _stored_commence(pg_session, event.event_ticker))
    assert stored == KICKOFF, (
        f"the multi-market branch stored {stored}, expected the earliest "
        f"occurrence {KICKOFF}. Stored {CLOSE} means the branch is back on the "
        "settlement backstop; a later occurrence means it stopped taking the min."
    )


# --------------------------------------------------------------------------
# The wiring claim itself: the helper's RETURN is what the row gets.
# --------------------------------------------------------------------------


async def test_single_market_branch_feeds_the_helpers_result_to_the_upsert(pg_session):
    spy = MagicMock(return_value=SENTINEL)
    event = _single_market_game()
    await _run_poll(pg_session, [event], commence_patch=spy)

    stored = _utc(await _stored_commence(pg_session, event.event_ticker))
    assert stored == SENTINEL, (
        f"the single-market branch stored {stored}, not the helper's return "
        f"{SENTINEL} — `_kalshi_commence_time` is being called and its result "
        "discarded, or the branch no longer calls it at all."
    )

    # Which branch ran: the single-market call passes exactly one market.
    assert spy.call_count == 1, f"expected one helper call, got {spy.call_count}"
    markets, kwargs = spy.call_args.args[0], spy.call_args.kwargs
    assert len(markets) == 1, (
        f"the single-market branch passed {len(markets)} markets — this arm is "
        "no longer exercising the `len(event.markets) == 1` path"
    )
    assert kwargs.get("is_game") is True, (
        "the single-market branch called the helper with is_game="
        f"{kwargs.get('is_game')!r} for a KXNFLGAME ticker — the game scope that "
        "keeps outrights from being re-timed has been lost"
    )


async def test_multi_market_branch_feeds_the_helpers_result_to_the_upsert(pg_session):
    spy = MagicMock(return_value=SENTINEL)
    event = _multi_market_game()
    await _run_poll(pg_session, [event], commence_patch=spy)

    stored = _utc(await _stored_commence(pg_session, event.event_ticker))
    assert stored == SENTINEL, (
        f"the multi-market branch stored {stored}, not the helper's return "
        f"{SENTINEL} — `_kalshi_commence_time` is being called and its result "
        "discarded, or the branch no longer calls it at all."
    )

    assert spy.call_count == 1, f"expected one helper call, got {spy.call_count}"
    markets, kwargs = spy.call_args.args[0], spy.call_args.kwargs
    assert len(markets) == 3, (
        f"the multi-market branch passed {len(markets)} markets, expected all 3 "
        "— it must hand the helper the whole event, or the earliest-start rule "
        "is computed over the wrong set"
    )
    assert kwargs.get("is_game") is True


# --------------------------------------------------------------------------
# The conflict arm — the half of the upsert that runs on every later beat.
# --------------------------------------------------------------------------


async def test_the_conflict_arm_carries_the_helpers_result_too(pg_session):
    """Re-poll the same event with a moved occurrence; the row must follow.

    `on_conflict_do_update` fires on every beat after the first, so for a market
    that lives for days this arm is the one that runs essentially always.
    Dropping `commence_time` from `update_set` alone would leave the two arms
    above green and freeze every game at whatever its first beat happened to see.
    """
    ticker = "KXNFLGAME-26SEP13REPOLL"
    await _run_poll(pg_session, [_single_market_game(ticker)])
    assert _utc(await _stored_commence(pg_session, ticker)) == KICKOFF

    moved = KICKOFF + timedelta(hours=3, minutes=15)  # a real NFL window slip
    await _run_poll(pg_session, [_single_market_game(ticker, occurrence=moved)])

    stored = _utc(await _stored_commence(pg_session, ticker))
    assert stored == moved, (
        f"after a re-poll the row still reads {stored}, expected the moved "
        f"occurrence {moved} — the conflict arm is not carrying commence_time, "
        "so a rescheduled game keeps its first-seen date forever"
    )


# --------------------------------------------------------------------------
# The control: the helper is scoped to games on purpose.
# --------------------------------------------------------------------------


async def test_a_non_game_outright_keeps_its_close_time(pg_session):
    """An outright whose occurrence is EARLIER than its close still stores close.

    `occurrence_datetime` is populated on outrights too, where it means
    something else, so preferring it everywhere would re-time markets that were
    never broken. Without this arm the file passes just as well against "always
    use the occurrence" — a different repair from the one #3433 shipped.
    """
    ticker = "KXECONGDP-26SEP"
    event = KalshiEvent(
        event_ticker=ticker,
        title="US GDP growth above 3% in Q3",
        category="Economics",
        mutually_exclusive=True,
        markets=[_market(ticker, "YES", "Above 3%", 0.44, occurrence=KICKOFF)],
    )
    await _run_poll(pg_session, [event])

    stored = _utc(await _stored_commence(pg_session, ticker))
    assert stored == CLOSE, (
        f"a non-game outright stored {stored}, expected its close {CLOSE} — the "
        "is_game scope has been dropped and every outright is now being re-timed "
        "onto a field that does not mean kick-off for them"
    )


# --------------------------------------------------------------------------
# #3532: the SECOND writer. Every fixture above is football precisely because
# the post-loop fix-ups skip it — which left the one sport where two writers
# both fire untested, and they disagreed.
# --------------------------------------------------------------------------


# The venue's own values for KXWTADOUBLES-26SEP07SINTOWHUNKRA, read 2026-09-06:
# a 2:00 PM EDT match against the +14d tennis settlement backstop.
_TENNIS_OCCURRENCE = datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc)
_TENNIS_CLOSE = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)
_ITF_TICKER_MIDNIGHT = datetime(2026, 9, 6, tzinfo=timezone.utc)
_DOUBLES_TICKER_MIDNIGHT = datetime(2026, 9, 7, tzinfo=timezone.utc)

assert _TENNIS_OCCURRENCE != _DOUBLES_TICKER_MIDNIGHT, (
    "the venue hour must differ from the ticker midnight, or the Event arm "
    "below cannot tell a repair from a no-op"
)


async def test_the_tennis_fixup_keeps_the_venue_start_but_still_repairs_a_close(
    pg_session,
):
    """Both tennis writers, one poll, on a real server.

    The subject and the control run TOGETHER, and that is the point. Asserting
    only the subject would pass just as well if the fix-up never selected the
    row at all — `tennis_commence_fixed == 0` reads the same whether the value
    was deliberately kept or never looked at. The ITF control is a row the main
    loop CANNOT date (KXITFMATCH is absent from KALSHI_TICKER_TO_DISPLAY_LABEL,
    so `is_game` is False and it stores the close), so a non-zero count is proof
    the fix-up ran, selected tennis, and wrote — in the same run in which it
    left the doubles row alone.
    """
    doubles = "KXWTADOUBLES-26SEP07SINTOWHUNKRA"
    itf = "KXITFMATCH-26SEP06AHRNEC"
    events = [
        KalshiEvent(
            event_ticker=doubles,
            title="Siniakova/Townsend vs Hunter/Krawczyk",
            category="Sports",
            mutually_exclusive=True,
            markets=[
                _market(
                    doubles, "SINTOW", "Siniakova/Townsend", 0.83,
                    occurrence=_TENNIS_OCCURRENCE, close=_TENNIS_CLOSE,
                ),
                _market(
                    doubles, "HUNKRA", "Hunter/Krawczyk", 0.17,
                    occurrence=_TENNIS_OCCURRENCE, close=_TENNIS_CLOSE,
                ),
            ],
        ),
        KalshiEvent(
            event_ticker=itf,
            title="Ahrens vs Necker",
            category="Sports",
            mutually_exclusive=True,
            markets=[
                _market(
                    itf, "AHR", "Ahrens", 0.55,
                    occurrence=None, close=_TENNIS_CLOSE,
                ),
            ],
        ),
    ]

    stats = await _run_poll(pg_session, events)

    assert stats.get("tennis_commence_fixed") == 1, (
        "the tennis fix-up wrote "
        f"{stats.get('tennis_commence_fixed')} rows, expected exactly 1 (the ITF "
        "control). 0 means it never selected these rows, so the subject below "
        "proves nothing; 2 means it also rewrote the doubles row"
    )

    stored = _utc(await _stored_commence(pg_session, doubles))
    assert stored == _TENNIS_OCCURRENCE, (
        f"the doubles market stored {stored}, expected the venue's "
        f"{_TENNIS_OCCURRENCE}. The main loop reads occurrence_datetime for this "
        "series and the post-loop tennis fix-up then re-dated it to the ticker's "
        f"midnight ({_ITF_TICKER_MIDNIGHT.replace(day=7)}) — which Eastern renders "
        "as 8:00 PM the previous evening, the wrong hour AND the wrong day (#3532)"
    )

    repaired = _utc(await _stored_commence(pg_session, itf))
    assert repaired == _ITF_TICKER_MIDNIGHT, (
        f"the ITF control stored {repaired}, expected the ticker date "
        f"{_ITF_TICKER_MIDNIGHT}. #3532 must not switch the fix-up off: 140 open "
        "ITF markets at the venue have no route to their occurrence and the "
        "ticker date is the only thing standing between them and a +14d close"
    )


# --------------------------------------------------------------------------
# CERT-2070: the market row is not the ship. `GET /api/events/{id}` serialises
# `event.commence_time`, and the page header and "Starts in" countdown read
# that field — so the market can hold 18:00Z while the page renders midnight.
# --------------------------------------------------------------------------


async def _seed_event(session, *, event_id, external_id, commence, ticker):
    """One tennis Event and the open Kalshi market linked to it.

    The market is already at the venue occurrence: that is the steady state
    after the main loop runs, and it is the state in which the Event is the
    only thing still wrong.
    """
    from app.models.models import Event, FuturesMarket, Sport

    sport = (
        await session.execute(text("SELECT id FROM sports WHERE key = 'tennis_wta'"))
    ).scalar_one_or_none()
    if sport is None:
        s = Sport(key="tennis_wta", name="WTA")
        session.add(s)
        await session.flush()
        sport = s.id

    session.add(
        Event(
            id=event_id,
            external_id=external_id,
            sport_id=sport,
            home_team_name="Siniakova / Townsend",
            away_team_name="Hunter / Krawczyk",
            commence_time=commence,
            status="scheduled",
        )
    )
    await session.flush()
    session.add(
        FuturesMarket(
            source="kalshi",
            external_id=ticker,
            name="Siniakova / Townsend vs Hunter / Krawczyk",
            category="championship",
            llm_sport_category="tennis",
            status="open",
            event_id=event_id,
            commence_time=_TENNIS_OCCURRENCE,
            resolution_date=_TENNIS_CLOSE,
        )
    )
    await session.commit()


async def _event_commence(session, event_id):
    return (
        await session.execute(
            text("SELECT commence_time FROM events WHERE id = :i"), {"i": event_id}
        )
    ).scalar_one()


async def _route_commence(session, event_id):
    """What `GET /api/events/{id}` actually serialises, off this same server."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.routes.events import _event_detail_cache
    from app.services.database import get_db

    # The route memoises by event id in-process; a hit would answer from a
    # payload built before the repair ran and the arm would prove nothing.
    _event_detail_cache.clear()

    async def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/events/{event_id}")
        assert resp.status_code == 200, f"route returned {resp.status_code}"
        return datetime.fromisoformat(resp.json()["commence_time"])
    finally:
        app.dependency_overrides.pop(get_db, None)
        _event_detail_cache.clear()


async def test_the_event_the_page_reads_gets_the_venue_hour(pg_session):
    """CERT-2070's named repair, through the real path and the real route.

    Three Events, one pass. `/events/15305555` is the specimen from the issue.
    Both controls exist because provenance and value are independent guards and
    a single control cannot show that either one is doing work.
    """
    await _seed_event(
        pg_session,
        event_id=15305555,
        external_id="pm_kalshi_KXWTADOUBLES-26SEP07SINTOWHUNKRA",
        commence=_DOUBLES_TICKER_MIDNIGHT,
        ticker="KXWTADOUBLES-26SEP07SINTOWHUNKRA",
    )
    # Control A — provenance. An ESPN row sitting on the very same midnight.
    # Only the `pm_kalshi_` guard stands between it and a rewrite.
    await _seed_event(
        pg_session,
        event_id=15305556,
        external_id="espn_401745231",
        commence=_DOUBLES_TICKER_MIDNIGHT,
        ticker="KXWTAMATCH-26SEP07OSARYB",
    )
    # Control B — the block's named control: an authoritative non-midnight start.
    authoritative = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)
    await _seed_event(
        pg_session,
        event_id=15305557,
        external_id="espn_401745232",
        commence=authoritative,
        ticker="KXWTAMATCH-26SEP07JOVGAU",
    )

    from app.tasks import kalshi as kalshi_task

    @asynccontextmanager
    async def _session_cm():
        yield pg_session

    with patch.object(kalshi_task, "get_task_session", _session_cm):
        result = await kalshi_task._fix_tennis_commence_times()

    assert result["events"] == 1, (
        f"the repair moved {result['events']} events, expected exactly 1. 0 means "
        "the Event pass never ran and the page is still wrong; >1 means a control "
        f"was overwritten. full result: {result}"
    )

    stored = _utc(await _event_commence(pg_session, 15305555))
    assert stored == _TENNIS_OCCURRENCE, (
        f"events.commence_time is {stored}, expected {_TENNIS_OCCURRENCE}. This is "
        "the field the page reads — the market row being right does not move it"
    )

    served = await _route_commence(pg_session, 15305555)
    assert _utc(served) == _TENNIS_OCCURRENCE, (
        f"GET /api/events/15305555 served {served}, expected {_TENNIS_OCCURRENCE}. "
        "The stored value is right but the payload is not, so the header and the "
        "'Starts in' countdown still render 8:00 PM the previous evening"
    )

    same_midnight = _utc(await _event_commence(pg_session, 15305556))
    assert same_midnight == _DOUBLES_TICKER_MIDNIGHT, (
        f"an ESPN event was re-timed to {same_midnight}. Provenance, not the "
        "value, is what makes the specimen eligible — an authoritative start is "
        "never overwritten from a Kalshi ticker even when it sits on the midnight"
    )

    untouched = _utc(await _event_commence(pg_session, 15305557))
    assert untouched == authoritative, (
        f"an authoritative non-midnight event moved to {untouched}"
    )
