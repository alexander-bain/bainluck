"""A Kalshi leg the venue lists is never left with zero outcome rows (#3518).

## the defect

`_poll_kalshi_markets` computes a probability per venue market and, when
`_kalshi_yes_probability` returns None — wide/one-sided book, no trade — used to
`continue` before writing anything at all. No row, not even an unpriced one.

That is only survivable if something comes back later. Nothing does, and this is
measured rather than assumed (2026-09-06, `/api/admin/kalshi/scan-report`):

* the main scan reaches **no existing event on any beat** — verdict `frozen` on
  24 of the last 24 runs, `unreached_existing == events_existing` (12,396 of
  12,396 on the latest), `wraps: 0`, and the loop deadline fires while still
  inside the NEW events (2,768 processed of 6,934 new). `_partition_new_events_
  first` + `_LOOP_DEADLINE_S` behaving exactly as `kalshi.py` predicts in prose;
* `futures_price_refresh` (#2199) — built for that very freeze — states in its
  own docstring that it "deliberately does NOT create markets, **create
  outcomes**, categorise, re-tier, group, or touch `event_id`";
* `_poll_live_prediction_market_prices` looks up `outcome_lookup[(market.id,
  ticker)]` and can only UPDATE a row that already exists.

So the skip is permanent. Production held **240 open, correctly-linked Kalshi
markets with zero outcome rows**, 81 of them across 63 FUTURE events, rendering
"No price yet" while the venue traded them — 57,000 contracts on one FCS
football game whose row had not been touched since 2026-08-19.

## what changed, and the claim these arms make

Recording that an outcome EXISTS is not the same claim as fabricating its price,
and the file already treats "outcome row with `current_probability = NULL`" as a
legitimate state — the null-out block writes exactly that whenever a
previously-priced market goes quiet. The poll now writes that state at BIRTH as
well as on the way down.

## why a real server, and why these particular arms

A statement-shape assertion reads back the values the caller passed and so
agrees with the caller by construction. Only a round trip distinguishes "the
poll built a dict" from "the row is in the table".

Three things can each silently undo this while a naive "a row appeared" test
stays green, so each has its own arm:

* **`is_winner` defaults to an affirmative LOSS.** The column is `boolean NULL
  DEFAULT false`, so an INSERT that merely OMITS it stores False — CAL-P1004R,
  the defect the *priced* insert in this same loop was already repaired for. A
  placeholder is the least-graded row in the system and must be born UNKNOWN.
  `test_the_placeholder_is_born_ungraded` is that arm, and it fails on an
  omission, not just on an explicit `False`.
* **The name could be computed independently.** `_kalshi_outcome_name` was
  hoisted out of the first pass so the unpriced branch could reach it. An arm
  patches it to return a string no fixture carries and requires that string back
  out of the server, so the claim is "whatever the helper returns is what the
  row gets" rather than "some plausible name appeared".
* **It must only ever ADD.** `on_conflict_do_nothing`, not `do_update`: an
  existing row's price is the null-out block's business, which protects settled
  and graded rows (gotcha #21). The re-poll arms drive the same event twice.

There is no local Postgres in the agent sandbox (`initdb` fails on `shmget`), so
**CI is the environment that runs this** — the `search-recall` job, reusing the
three-seam rig of `test_kalshi_game_commence_wiring_real_postgres.py`.

Every fixture is FOOTBALL on purpose: the post-loop golf/hockey/tennis fix-ups
run inside the same task and are scoped by `llm_sport_category` in SQL, so a
fixture in one of those sports could have its row rewritten under the assertion.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from app.services.kalshi_api import KalshiEvent, KalshiMarket
from app.tasks.kalshi import _kalshi_yes_probability

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres unpriced-"
            "outcome round trip (CI job `search-recall` provides one)"
        ),
    ),
]

KICKOFF = datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc)
CLOSE = KICKOFF + timedelta(days=3)

#: A name nothing in any fixture carries, so a row holding it can only have got
#: it from `_kalshi_outcome_name`'s return value.
NAME_SENTINEL = "Zzyzx Sentinel 2031"


def _unpriced_market(event_ticker, suffix, name):
    """A leg the venue LISTS but whose book cannot be read this pass.

    All three price inputs are absent, which is the state Kalshi returns for a
    market listed before its book opens. The premise is asserted below rather
    than assumed: if a later edit to `_kalshi_yes_probability` starts returning a
    number here, every arm in this file would be testing the priced path while
    still claiming to test the unpriced one.
    """
    return KalshiMarket(
        ticker=f"{event_ticker}-{suffix}",
        event_ticker=event_ticker,
        title=name,
        yes_sub_title=name,
        status="active",
        close_time=CLOSE,
        occurrence_datetime=KICKOFF,
        yes_bid=None,
        yes_ask=None,
        last_price=None,
        volume=0,
    )


def _priced_market(event_ticker, suffix, name, price):
    """A leg with a tight two-sided book — `_kalshi_yes_probability` takes the midpoint."""
    return KalshiMarket(
        ticker=f"{event_ticker}-{suffix}",
        event_ticker=event_ticker,
        title=name,
        yes_sub_title=name,
        status="active",
        close_time=CLOSE,
        occurrence_datetime=KICKOFF,
        yes_bid=price - 0.01,
        yes_ask=price + 0.01,
        last_price=price,
        volume=1500,
    )


# The fixture premises, asserted where they are stated (gotcha: a guard whose
# fixture drifts stops discriminating while staying green).
assert (
    _kalshi_yes_probability(None, None, None) is None
), "an all-absent book must be UNPRICED, or this file tests the priced path"
assert (
    _kalshi_yes_probability(0.61, 0.63, 0.62) is not None
), "the control leg must be PRICED, or the no-regression arm proves nothing"


def _event(event_ticker, markets, title="Bills at Jets"):
    return KalshiEvent(
        event_ticker=event_ticker,
        title=title,
        category="Football",
        mutually_exclusive=True,
        markets=markets,
    )


def _all_unpriced_event(event_ticker="KXNFLGAME-26SEP13BUFNYJ"):
    """Both legs unreadable — the #3518 population exactly (`market_count: 2`, zero rows)."""
    return _event(
        event_ticker,
        [
            _unpriced_market(event_ticker, "BUF", "Bills"),
            _unpriced_market(event_ticker, "NYJ", "Jets"),
        ],
    )


def _mixed_event(event_ticker="KXNFLGAME-26SEP13KCDEN"):
    """One readable leg, one not — the half-ingested shape behind the 153 one-outcome rows."""
    return _event(
        event_ticker,
        [
            _priced_market(event_ticker, "KC", "Chiefs", 0.62),
            _unpriced_market(event_ticker, "DEN", "Broncos"),
        ],
        title="Chiefs at Broncos",
    )


async def _run_poll(session, events, *, name_patch=None):
    """Run the REAL `_poll_kalshi_markets` against this Postgres session.

    Three seams, all of them the task's own boundaries — see
    `test_kalshi_game_commence_wiring_real_postgres.py`, whose rig this reuses:
    the network (`KalshiAPIService`), the connection (`get_task_session`, which
    yields OUR session and does not close it), and Redis (raised, so every phase
    marker / cursor / discovery-cache branch takes its no-op path and the golf
    fix-up stays a dry run).
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
    if name_patch is not None:
        stack.append(patch("app.tasks.kalshi._kalshi_outcome_name", name_patch))

    from contextlib import ExitStack

    with ExitStack() as es:
        for cm in stack:
            es.enter_context(cm)
        from app.tasks.kalshi import _poll_kalshi_markets

        stats = await _poll_kalshi_markets()

    # The poll swallows per-event and top-level failures into `stats["errors"]`
    # (it must: one bad event may not wipe a whole ingest). Unasserted, a gate
    # driving it would read a silently-skipped event as a passing round trip.
    assert stats["errors"] == [], f"the poll reported errors: {stats['errors']}"
    assert stats["events_processed"] == len(events), (
        f"the poll processed {stats['events_processed']}/{len(events)} events — "
        f"the fixture never reached the upsert loop. stats: {stats}"
    )
    await session.commit()
    return stats


async def _outcomes(session, event_ticker):
    """Read the rows back out of the SERVER, keyed by ticker."""
    rows = await session.execute(
        text(
            "SELECT o.external_id, o.name, o.current_probability, o.is_winner, o.rank "
            "FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
            "WHERE m.source = 'kalshi' AND m.external_id = :t ORDER BY o.rank"
        ),
        {"t": event_ticker},
    )
    return {
        r[0]: {"name": r[1], "prob": r[2], "is_winner": r[3], "rank": r[4]}
        for r in rows.fetchall()
    }


@pytest.fixture
async def pg_session():
    """Real Postgres with the real schema.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the loop that created
    its engine.
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


class TestTheVenuesLegIsRecorded:
    """The ship: a leg the venue lists is never left with zero rows."""

    async def test_an_all_unpriced_event_still_gets_a_row_per_leg(self, pg_session):
        ev = _all_unpriced_event()
        stats = await _run_poll(pg_session, [ev])

        got = await _outcomes(pg_session, ev.event_ticker)
        assert set(got) == {f"{ev.event_ticker}-BUF", f"{ev.event_ticker}-NYJ"}, (
            "the venue listed two legs and the market must not hold zero outcome "
            f"rows — this is #3518's exact population. got: {got}"
        )
        assert stats["unpriced_outcomes_recorded"] == 2, (
            "the dedicated counter must report the write; a zero here with rows "
            "present would mean some other path created them"
        )

    async def test_the_recorded_row_carries_no_fabricated_price(self, pg_session):
        ev = _all_unpriced_event()
        await _run_poll(pg_session, [ev])

        for ticker, row in (await _outcomes(pg_session, ev.event_ticker)).items():
            assert row["prob"] is None, (
                f"{ticker} holds {row['prob']} — recording that an outcome EXISTS "
                "must never fabricate its PRICE, which is the whole reason the "
                "original `continue` was defensible"
            )

    async def test_the_placeholder_is_born_ungraded(self, pg_session):
        """CAL-P1004R's trap, on the new write site.

        `is_winner` is `boolean NULL DEFAULT false`. An INSERT that omits the
        column stores False — an affirmative graded LOSS on a leg the venue has
        not called — and that False then sits on a row `resolution_authority`
        protects from correction. NULL is UNKNOWN; False is a claim.
        """
        ev = _all_unpriced_event()
        await _run_poll(pg_session, [ev])

        for ticker, row in (await _outcomes(pg_session, ev.event_ticker)).items():
            assert row["is_winner"] is None, (
                f"{ticker} was born is_winner={row['is_winner']!r}. The placeholder "
                "must pass is_winner=None EXPLICITLY — omitting it lets the "
                "server_default write an affirmative loss (CAL-P1004R)."
            )

    async def test_the_name_is_the_helpers_return_value(self, pg_session):
        """The wiring claim, stated directly.

        A name that merely looks right could have been computed at the call site,
        which is how the hoist could be silently unwired. Patch the helper to
        return a string no fixture carries and require it back out of the server.
        """
        ev = _all_unpriced_event()
        await _run_poll(pg_session, [ev], name_patch=lambda *a, **k: NAME_SENTINEL)

        got = await _outcomes(pg_session, ev.event_ticker)
        assert got, "no rows written, so the sentinel proves nothing"
        for ticker, row in got.items():
            assert row["name"] == NAME_SENTINEL, (
                f"{ticker} stored name={row['name']!r}, not the helper's return "
                "value — the unpriced branch is not wired to `_kalshi_outcome_name`"
            )


class TestTheHealthyPathIsUntouched:
    """The controls. 1,059 markets price correctly today and must keep doing so."""

    async def test_a_priced_leg_keeps_its_price(self, pg_session):
        ev = _mixed_event()
        await _run_poll(pg_session, [ev])

        got = await _outcomes(pg_session, ev.event_ticker)
        priced = got[f"{ev.event_ticker}-KC"]
        assert priced["prob"] is not None and 0.61 < float(priced["prob"]) < 0.63, (
            f"the readable leg lost its price: {priced}"
        )

    async def test_both_legs_are_present_and_the_priced_one_outranks(self, pg_session):
        """The 153 one-outcome markets are this shape, and the missing side is
        what let the live poller's count-based fallback write one side's price
        onto the other. Both sides present is what kills that for this class."""
        ev = _mixed_event()
        await _run_poll(pg_session, [ev])

        got = await _outcomes(pg_session, ev.event_ticker)
        assert set(got) == {f"{ev.event_ticker}-KC", f"{ev.event_ticker}-DEN"}, got
        assert got[f"{ev.event_ticker}-DEN"]["prob"] is None
        assert (
            got[f"{ev.event_ticker}-KC"]["rank"] < got[f"{ev.event_ticker}-DEN"]["rank"]
        ), "an unpriced leg must never outrank a priced one on a rank-sorted page"

    async def test_a_fully_priced_event_records_no_placeholders(self, pg_session):
        """The counter must not fire on the steady state, or it cannot testify."""
        t = "KXNFLGAME-26SEP13SEASF"
        ev = _event(
            t,
            [_priced_market(t, "SEA", "Seahawks", 0.55),
             _priced_market(t, "SF", "49ers", 0.45)],
            title="Seahawks at 49ers",
        )
        stats = await _run_poll(pg_session, [ev])
        assert stats["unpriced_outcomes_recorded"] == 0, (
            "no leg was unreadable, so the placeholder write had nothing to do"
        )


class TestTheWriteOnlyEverAdds:
    """`on_conflict_do_nothing`: an existing row belongs to the null-out block."""

    async def test_a_second_poll_does_not_duplicate_or_error(self, pg_session):
        ev = _all_unpriced_event()
        await _run_poll(pg_session, [ev])
        await _run_poll(pg_session, [ev])

        got = await _outcomes(pg_session, ev.event_ticker)
        assert len(got) == 2, (
            f"re-polling the same event duplicated rows: {got}. The unique index "
            "on (market_id, external_id) plus do_nothing must make this idempotent."
        )

    async def test_a_price_that_arrives_later_is_not_clobbered_back_to_null(
        self, pg_session
    ):
        """The healing direction — the entire point of writing the row.

        Poll once with the book shut, then again with it open. The placeholder
        must accept the real price, which is the round trip proving these rows
        are reachable rather than merely present.
        """
        t = "KXNFLGAME-26SEP13BUFNYJ"
        await _run_poll(pg_session, [_event(t, [_unpriced_market(t, "BUF", "Bills")])])
        assert (await _outcomes(pg_session, t))[f"{t}-BUF"]["prob"] is None

        await _run_poll(
            pg_session, [_event(t, [_priced_market(t, "BUF", "Bills", 0.62)])]
        )
        row = (await _outcomes(pg_session, t))[f"{t}-BUF"]
        assert row["prob"] is not None and 0.61 < float(row["prob"]) < 0.63, (
            f"the placeholder did not accept the price that arrived later: {row}"
        )
