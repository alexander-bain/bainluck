"""#3613's selector, executed against real Postgres — the half a fake session cannot reach.

`tests/test_polymarket_dark_linked_market_gets_a_price_3613.py` drives the whole
pass, but its recording session ANSWERS the selector instead of running it. So
every claim that file makes about *which* markets get picked is a claim about
SQL nothing has executed: `make_interval(hours => :lookback_hours)`, the
`NOT EXISTS` anti-join, the `NOT LIKE '0x%'` exclusion and the `ORDER BY` are all
unproved there. A raw-SQL typo in a beat task is invisible until the beat runs in
production and logs an error nobody reads.

This file is the twin of `test_linked_game_price_chain_real_postgres.py` for the
Polymarket side, and it is deliberately small: the population, then one write.

**Five rows, four of which must NOT be selected**, each excluded for a different
reason, because a selector that returns the right answer for one reason and the
wrong answer for three is indistinguishable from a correct one when the fixture
only holds the specimen:

    picked   the specimen — open, linked, 13.4 days out, ZERO legs
    skipped  has a leg already          (the anti-join)
    skipped  keyed by condition_id      (`/events?id=` cannot address it)
    skipped  20 days out                (outside the measured 14-day bound)
    skipped  resolved                   (`status = 'open'`)

The 13.4-day specimen is the point of the horizon, not an arbitrary date: the
Kalshi twin stops at 7 days, and #3602 is the issue that closed because of it.

There is no local Postgres in the agent sandbox (`initdb` dies on `shmget`), so
CI is the environment that runs this — the `search-recall` job.
"""

from __future__ import annotations

import json
import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the dark-Polymarket selector "
            "against real Postgres (CI job `search-recall` provides one)"
        ),
    ),
]

UTC = timezone.utc

#: The production specimen (2026-09-06): Gamma event id, and its moneyline leg.
SPECIMEN_EXTERNAL_ID = "972409"
SPECIMEN_TITLE = "UFC 331: Ozzy Diaz vs. Ryan Gandra (Middleweight, Early Prelims)"
MONEYLINE_CID = "0xf5200af34f486ef08072a3759b351021d4895123ed6a6ab338fbc5458147a365"
MONEYLINE_PRICE, MONEYLINE_BID, MONEYLINE_ASK = 0.295, 0.21, 0.38


@pytest.fixture
async def pg_session():
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


async def _seed(session):
    """The five rows. Returns `{label: market_id}`."""
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    sport = Sport(key="mma_mixed_martial_arts", name="MMA", group="Fighting")
    session.add(sport)
    await session.flush()

    def _event(days):
        e = Event(
            sport_id=sport.id,
            home_team_name="Gandra",
            away_team_name="Diaz",
            commence_time=datetime.now(UTC) + timedelta(days=days),
            status="scheduled",
        )
        session.add(e)
        return e

    near, far = _event(13.4), _event(20)
    await session.flush()

    def _market(external_id, event, status="open"):
        m = FuturesMarket(
            source="polymarket",
            external_id=external_id,
            name=SPECIMEN_TITLE,
            category="championship",
            market_tier=5,
            status=status,
            event_id=event.id,
            # Copied from the specimen's own production row (`futures_markets`
            # 60280227, read 2026-09-06): `llm_sport_category='mma'`,
            # `sport_id=29` — the same sport the event carries. Both are
            # load-bearing on the READ side and neither was here at first, which
            # is why `test_after_the_pass_...` failed in CI on a green ship:
            # `_build_related_futures`' game-prop pass requires
            # `sport_id == event.sport_id` OR (`sport_id IS NULL` AND
            # `llm_sport_category == 'mma'`), and a NULL satisfies neither arm.
            # A fixture thinner than production does not prove a smaller thing —
            # it proves a different one.
            llm_sport_category="mma",
            sport_id=sport.id,
        )
        session.add(m)
        return m

    ids = {
        "specimen": _market(SPECIMEN_EXTERNAL_ID, near),
        "already_has_a_leg": _market("111111", near),
        "condition_id_keyed": _market("0xdeadbeef", near),
        "beyond_the_horizon": _market("222222", far),
        "resolved": _market("333333", near, status="resolved"),
    }
    await session.flush()

    session.add(
        FuturesOutcome(
            market_id=ids["already_has_a_leg"].id,
            external_id="0xalready",
            name="Somebody",
            current_probability=0.5,
            rank=1,
        )
    )
    await session.commit()
    out = {k: m.id for k, m in ids.items()}
    # The event the specimen hangs on, so a test can ask what a READER of that
    # page would be served rather than only what the table holds.
    out["_near_event_id"] = near.id
    return out


def _specimen_service():
    """The venue, answering with the specimen's one real book.

    The nineteen phantom sub-markets are left out here on purpose: which rows
    the pass REFUSES is proved in `test_polymarket_dark_linked_market_gets_a_
    price_3613.py`, and repeating it would make this file's failures ambiguous.
    """
    from app.services.polymarket_api import PolymarketEvent, PolymarketMarket

    venue = PolymarketEvent(
        id=SPECIMEN_EXTERNAL_ID,
        title=SPECIMEN_TITLE,
        active=True,
        neg_risk=False,
        markets=[
            PolymarketMarket(
                condition_id=MONEYLINE_CID,
                question=SPECIMEN_TITLE,
                outcomes=["Ozzy Diaz", "Ryan Gandra"],
                outcome_prices=[MONEYLINE_PRICE, 0.705],
                best_bid=MONEYLINE_BID,
                best_ask=MONEYLINE_ASK,
                active=True,
            ),
        ],
    )

    class _Service:
        async def get_events_by_ids(self, event_ids):
            return [{"id": i} for i in event_ids]

        def _parse_event(self, raw):
            return venue if raw["id"] == SPECIMEN_EXTERNAL_ID else None

        async def close(self):
            return None

    return _Service()


def _session_cm_for(session):
    """`get_task_session` replacement that hands the pass the test's session."""

    @asynccontextmanager
    async def _cm():
        yield session

    return _cm


async def _select(session):
    """Execute the shipping selector, with the shipping bound values."""
    from app.tasks.polymarket import (
        LINKED_POLY_BOOK_HORIZON_DAYS,
        LINKED_POLY_BOOK_LOOKBACK_HOURS,
        _LINKED_POLY_BOOKS_SQL,
        _LINKED_POLY_MAX_MARKETS,
    )

    rows = (
        await session.execute(
            _LINKED_POLY_BOOKS_SQL,
            {
                "lookback_hours": LINKED_POLY_BOOK_LOOKBACK_HOURS,
                "horizon_days": LINKED_POLY_BOOK_HORIZON_DAYS,
                "max_markets": _LINKED_POLY_MAX_MARKETS,
            },
        )
    ).fetchall()
    return rows


class TestTheSelectorAgainstRealPostgres:
    async def test_it_picks_the_specimen_and_nothing_else(self, pg_session):
        ids = await _seed(pg_session)
        rows = await _select(pg_session)
        assert [r.id for r in rows] == [ids["specimen"]], (
            "the five-row fixture excludes four rows for four different reasons; "
            "any other answer means one of those clauses is not doing its job"
        )

    async def test_the_row_carries_what_the_pass_reads_off_it(self, pg_session):
        """The pass reads `.id`, `.external_id`, `.name` and `.event_id`. A
        column renamed out of the SELECT is an AttributeError at beat time."""
        await _seed(pg_session)
        (row,) = await _select(pg_session)
        assert str(row.external_id) == SPECIMEN_EXTERNAL_ID
        assert row.name == SPECIMEN_TITLE
        assert row.event_id is not None

    async def test_a_started_but_unflipped_event_is_still_selected(self, pg_session):
        """The lookback, executed. A game whose row never flipped to `live`
        must not drop out of the population an hour after kick-off — those are
        the rows most likely to be looked at."""
        ids = await _seed(pg_session)
        await pg_session.execute(
            text(
                "UPDATE events SET commence_time = NOW() - INTERVAL '2 hours' "
                "WHERE id = (SELECT event_id FROM futures_markets WHERE id = :m)"
            ),
            {"m": ids["specimen"]},
        )
        await pg_session.commit()
        assert [r.id for r in await _select(pg_session)] == [ids["specimen"]]

    async def test_seven_hours_after_kickoff_it_drops_out(self, pg_session):
        """...and the lookback is a bound, not an open door."""
        ids = await _seed(pg_session)
        await pg_session.execute(
            text(
                "UPDATE events SET commence_time = NOW() - INTERVAL '7 hours' "
                "WHERE id = (SELECT event_id FROM futures_markets WHERE id = :m)"
            ),
            {"m": ids["specimen"]},
        )
        await pg_session.commit()
        assert await _select(pg_session) == []

    async def test_a_live_event_is_in_scope_whatever_its_clock_says(self, pg_session):
        ids = await _seed(pg_session)
        await pg_session.execute(
            text(
                "UPDATE events SET status = 'live', "
                "       commence_time = NOW() - INTERVAL '3 days' "
                "WHERE id = (SELECT event_id FROM futures_markets WHERE id = :m)"
            ),
            {"m": ids["specimen"]},
        )
        await pg_session.commit()
        assert [r.id for r in await _select(pg_session)] == [ids["specimen"]]


class TestThePassWritesToRealPostgres:
    async def test_the_dark_market_ends_the_pass_holding_the_venues_price(
        self, pg_session
    ):
        """End to end on real rows: the selector picks it, the writer fills it.

        Only the network is stubbed. The ON CONFLICT clause, the explicit NULL
        `is_winner` against a column that DEFAULTS TO FALSE (CAL-P1004R — the
        trap a fake session cannot show you, because only Postgres applies the
        default), and the snapshot's foreign key are all exercised for real.
        """
        from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
        from app.tasks import polymarket as poly

        ids = await _seed(pg_session)

        venue = PolymarketEvent(
            id=SPECIMEN_EXTERNAL_ID,
            title=SPECIMEN_TITLE,
            active=True,
            neg_risk=False,
            markets=[
                PolymarketMarket(
                    condition_id=MONEYLINE_CID,
                    question=SPECIMEN_TITLE,
                    outcomes=["Ozzy Diaz", "Ryan Gandra"],
                    outcome_prices=[MONEYLINE_PRICE, 0.705],
                    best_bid=MONEYLINE_BID,
                    best_ask=MONEYLINE_ASK,
                    active=True,
                ),
            ],
        )

        class _Service:
            async def get_events_by_ids(self, event_ids):
                return [{"id": i} for i in event_ids]

            def _parse_event(self, raw):
                return venue if raw["id"] == SPECIMEN_EXTERNAL_ID else None

            async def close(self):
                return None

        @asynccontextmanager
        async def _session_cm():
            yield pg_session

        with ExitStack() as es:
            es.enter_context(patch("app.tasks.polymarket.get_task_session", _session_cm))
            es.enter_context(
                patch(
                    "app.services.polymarket_api.PolymarketAPIService",
                    lambda *a, **k: _Service(),
                )
            )
            stats = await poly._refresh_linked_polymarket_books()

        assert stats["outcomes_created"] == 1, stats
        assert stats["snapshots_written"] == 1, stats

        row = (
            await pg_session.execute(
                text(
                    "SELECT external_id, current_probability, current_yes_bid, "
                    "       is_winner, resolution_source "
                    "  FROM futures_outcomes WHERE market_id = :m"
                ),
                {"m": ids["specimen"]},
            )
        ).one()
        assert row.external_id == MONEYLINE_CID
        assert float(row.current_probability) == pytest.approx(MONEYLINE_PRICE)
        assert float(row.current_yes_bid) == pytest.approx(MONEYLINE_BID)
        assert row.is_winner is None, (
            "the column DEFAULTS TO FALSE, so a stored False here would be an "
            "affirmative graded loss on a fight nobody has watched (CAL-P1004R)"
        )
        assert row.resolution_source is None

        snap = (
            await pg_session.execute(
                text(
                    "SELECT s.bookmaker, s.probability FROM futures_odds_snapshots s "
                    "  JOIN futures_outcomes o ON o.id = s.outcome_id "
                    " WHERE o.market_id = :m"
                ),
                {"m": ids["specimen"]},
            )
        ).one()
        assert snap.bookmaker == "polymarket"
        assert float(snap.probability) == pytest.approx(MONEYLINE_PRICE)

    async def test_running_it_twice_writes_nothing_the_second_time(self, pg_session):
        """Idempotence, on the real unique index rather than on a promise. The
        pass selects markets with no legs, so the second run must not even see
        it — and if a race put it back in scope, ON CONFLICT DO NOTHING is what
        stops a duplicate snapshot landing on someone else's leg."""
        from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
        from app.tasks import polymarket as poly

        ids = await _seed(pg_session)
        venue = PolymarketEvent(
            id=SPECIMEN_EXTERNAL_ID,
            title=SPECIMEN_TITLE,
            active=True,
            neg_risk=False,
            markets=[
                PolymarketMarket(
                    condition_id=MONEYLINE_CID,
                    question=SPECIMEN_TITLE,
                    outcomes=["Ozzy Diaz", "Ryan Gandra"],
                    outcome_prices=[MONEYLINE_PRICE, 0.705],
                    best_bid=MONEYLINE_BID,
                    best_ask=MONEYLINE_ASK,
                    active=True,
                ),
            ],
        )

        class _Service:
            async def get_events_by_ids(self, event_ids):
                return [{"id": i} for i in event_ids]

            def _parse_event(self, raw):
                return venue if raw["id"] == SPECIMEN_EXTERNAL_ID else None

            async def close(self):
                return None

        @asynccontextmanager
        async def _session_cm():
            yield pg_session

        with ExitStack() as es:
            es.enter_context(patch("app.tasks.polymarket.get_task_session", _session_cm))
            es.enter_context(
                patch(
                    "app.services.polymarket_api.PolymarketAPIService",
                    lambda *a, **k: _Service(),
                )
            )
            first = await poly._refresh_linked_polymarket_books()
            second = await poly._refresh_linked_polymarket_books()

        assert first["outcomes_created"] == 1
        assert second["terminal"] == "no_dark_linked_markets_in_window"
        legs = (
            await pg_session.execute(
                text("SELECT COUNT(*) FROM futures_outcomes WHERE market_id = :m"),
                {"m": ids["specimen"]},
            )
        ).scalar()
        assert legs == 1


class TestTheReaderCanActuallySeeIt:
    """CERT-2103's finding, answered on the path that really renders.

    The BLOCK was right that the backend pass alone proves nothing a reader can
    see, and it named `gameMarkets.other` and its `>= 3` gates as the thing to
    fix. Measured afterwards, that is the wrong door, twice over:

    1. **A fight moneyline is deliberately excluded from that section.**
       `findWinProbMarkets` in `lib/otherMarketGroups.ts` classifies any market
       whose rows sum to ~1.0 as a win-probability market and withholds it,
       because the hero owns that question. Ozzy Diaz 0.295 + Ryan Gandra 0.705
       is exactly 1.000. Forcing it into "Additional Markets" would put a
       moneyline under a junk-drawer heading and duplicate the hero — the
       opposite of *"the blend is the product"*.
    2. **These rows already reach the reader by another route.** Measured on the
       working sibling `/events/15190803` (same card, legs present, screenshot
       2026-09-06): its fight markets render under **Bigger Picture -> GAME
       PROPS**, served by `/related-futures`, and its `other` section renders
       nothing at all — all five of its rows are win-prob shaped and withheld.

    `/related-futures` builds `home_team_futures` by iterating **outcome rows**,
    so a parent market with zero legs contributes nothing and is structurally
    invisible. That is the whole bug, and writing the legs is the whole fix.
    Measured the same day: the dark event returned `home_team_futures: 0`,
    `away_team_futures: 0`, `series_markets: 0` — an empty page — while the
    sibling returned 4.

    So this is the one-row display regression the BLOCK asked for, pointed at
    the door the row actually comes through. It fails if the ship is invisible.
    """

    async def _related(self, session, event_id):
        from app.routes.events import _build_related_futures

        resp, _status, _ids, _cacheable = await _build_related_futures(
            event_id, session, debug=False
        )
        return resp

    def _all_rows(self, resp):
        return (resp.get("home_team_futures") or []) + (
            resp.get("away_team_futures") or []
        )

    async def test_before_the_pass_the_page_has_nothing_to_show(self, pg_session):
        """The state a user actually hit: a linked market, and a blank page.

        This is the guard's own control. Without it, a test that finds the row
        AFTER the pass cannot tell a fix from a fixture that was always green.
        """
        ids = await _seed(pg_session)
        resp = await self._related(pg_session, ids["_near_event_id"])

        rows = self._all_rows(resp)
        assert not any(
            r.get("market_id") == ids["specimen"] for r in rows
        ), "the legless specimen must be invisible — that is the bug"
        # NOT a substring test on the payload. The four sibling markets in the
        # fixture carry the same title, so the fighter's name legitimately
        # appears in another row's `market_name` while his price does not exist
        # anywhere. What the reader is missing is a PRICED ROW, and that is what
        # this asserts — a `json.dumps(resp)` check would fail here for a reason
        # that has nothing to do with the ship.
        assert not any(
            "Ozzy Diaz" in (r.get("outcome_name") or "") for r in rows
        ), "no leg exists yet, so no priced row for this fighter can be served"

    async def test_after_the_pass_the_venues_price_is_on_the_page(self, pg_session):
        """The ship, as a reader meets it: the fight, priced, in the payload
        that draws Bigger Picture -> GAME PROPS."""
        from app.tasks import polymarket as poly

        ids = await _seed(pg_session)

        with ExitStack() as es:
            es.enter_context(patch("app.tasks.polymarket.get_task_session", _session_cm_for(pg_session)))
            es.enter_context(
                patch(
                    "app.services.polymarket_api.PolymarketAPIService",
                    lambda *a, **k: _specimen_service(),
                )
            )
            stats = await poly._refresh_linked_polymarket_books()
        assert stats["outcomes_created"] == 1, stats

        resp = await self._related(pg_session, ids["_near_event_id"])
        rows = self._all_rows(resp)

        mine = [r for r in rows if r.get("market_id") == ids["specimen"]]
        assert mine, (
            "the specimen must now be surfaced — related-futures groups by "
            "OUTCOME rows, so writing the leg is exactly what makes it visible"
        )

        blob = json.dumps(mine)
        assert "Ozzy Diaz" in blob, "the fighter the price is about must be named"

        # `home_team_futures`/`away_team_futures` are FLAT rows — one per
        # OUTCOME, carrying `outcome_name` and `probability` at the top level.
        # Only `series_markets` nests an `outcomes` list, and this market is not
        # one. Reading the wrong shape is how the first version of this arm
        # would have failed even once the row was surfaced.
        # The SERVED label, which is not the stored one and is not the venue's.
        # Two hops, both of them production behaviour this arm exists to pin:
        # `_parent_outcome_data` yields a single-market event ONE leg named
        # "Yes" (the venue's own convention for a two-sided moneyline), and
        # `_build_related_futures` then relabels a "Yes" on a matchup-named
        # market to "<first side> Win". The working sibling reads exactly the
        # same way on production today — "UFC 331: Gable Steveson Win". Asserted
        # as an equality on the whole string, because "the fighter's name
        # appears somewhere" is satisfied by the market_name on every row here.
        priced = [
            r for r in mine
            if (r.get("outcome_name") or "") == "UFC 331: Ozzy Diaz Win"
        ]
        assert priced, f"no Ozzy Diaz row in {blob}"
        assert priced[0]["probability"] == pytest.approx(MONEYLINE_PRICE), (
            "the number on the page must be the number the venue is quoting — "
            "29.5%, not a normalised or invented one"
        )
        # CERT-2111: being in the payload is not being on the page.
        # `categorizeFutures()` buckets on this field and has NO bucket for
        # `championship`, which is what the fixture is seeded with and what the
        # specimen's production row carries. The round trip is what proves the
        # pass's label correction survives to the reader — a unit test can only
        # show the UPDATE was emitted.
        assert priced[0]["display_category"] == "game_prop", (
            f"the row is served as {priced[0]['display_category']!r}; the web "
            "categorizer drops everything it has no bucket for, and it has none "
            "for 'championship'. The fixture seeds 'championship' exactly as "
            "production does, so this asserts the pass relabelled it."
        )
