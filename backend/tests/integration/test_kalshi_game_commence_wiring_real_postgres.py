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
