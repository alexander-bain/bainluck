"""THE FRONT DOOR STOPS OFFERING A QUESTION THAT IS ALREADY ANSWERED. #4914.

A market whose game has been played is not a market. It is an answer, printed at
100%, taking a dropdown slot from something the reader could still have an
opinion about.

MEASURED ON PRODUCTION, backend `9ed5a436`, 2026-09-11 ~01:55Z,
`GET /api/events/typeahead?q=swiatek` — row 7 of 7:

    {"type": "futures", "text": "Set 2 Winner: Swiatek vs Zheng",
     "market_id": 60299706, "market_tier": 1,
     "top_outcomes": [{"name": "No",  "probability": 1.0},
                      {"name": "Yes", "probability": null}]}

Swiatek-Zheng completed **2026-09-07 17:45:32Z** — four days before that read.
The market is `status='open'` with `resolution_date = 2026-09-13`, so both
filters the pool already had waved it through, and `market_tier = 1` put it at
the top of the futures ordering rather than the bottom.

At the same minute, on the same production database:

    markets the pool admits ..................... 50,576
      linked event `completed` .................     574   <- this ship
      linked event `closed` ....................       9   <- this ship
      linked event `live` ......................     200   <- MUST survive
      linked event `suspended` .................  11,077   <- NOT this ship
      linked event `voided` ....................     126   <- NOT this ship
      linked event `scheduled` .................   6,102
      no linked event at all ...................  32,483   <- MUST survive

WHY `status='open'` AND `resolution_date >= now` DID NOT CATCH IT. Both ask the
VENUE's question — "has the venue settled this yet?" — and the venue settles on
its own clock. `resolution_date` is a settlement DEADLINE, not a game clock: the
Swiatek market's is six days after the match, and the Patriots-Seahawks announcer
props #4914 was filed on carried an end-of-DAY `23:59Z`, which is why they were
offered for the whole evening after that game finished. The reader's question is
different and nothing was asking it: **is this still a thing I can have an
opinion about?**

WHAT THIS FILE DOES NOT CLAIM TO FIX. #4914's own filed specimen — the
Patriots-Seahawks announcer props — is NOT fixed by this change and cannot be.
Those 20 markets (`group_id = 'polymarket:979689'`) all carry
`event_id IS NULL`; the whole group is unattached, so there is no game state to
read. That is matching debt (#2693, D35) and is called out in the PR rather than
papered over here. This ship fixes the 583 markets whose game we CAN see, and
the tier-1 US Open specimen above is one of them.

THE DISCRIMINATOR IS THE GAME'S STATE, NOT THE PRICE — #4914 says so in those
words, and it is right. A lopsided price on a game not yet played is a real
market; the same number on a game already played is an answer. So the predicate
reads :data:`SETTLED_STATUSES` and nothing else.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, union
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import InvalidRequestError

from app.models import Event, FuturesMarket
from app.routes.events import _futures_game_already_played
from app.utils.event_completion import (
    EVENT_SUSPENDED,
    SETTLED_STATUSES,
)


def _sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _typeahead_arm_shape():
    """The shape `/typeahead` builds: the clause pushed into a UNION arm."""
    clause = _futures_game_already_played()
    return union(
        select(FuturesMarket.id).where(FuturesMarket.name.ilike("%x%"), clause),
        select(FuturesMarket.id).where(FuturesMarket.name.ilike("%y%"), clause),
    )


def _outer_query_joining_events_shape():
    """An enclosing query that ALSO joins `events` — the /search path shape."""
    return (
        select(FuturesMarket.id)
        .join(Event, Event.id == FuturesMarket.event_id)
        .where(_futures_game_already_played())
    )


# ---------------------------------------------------------------------------
# 1. The specimen is not vacuous
# ---------------------------------------------------------------------------


class TestTheSpecimenIsNotVacuous:
    """If these pass trivially, every assertion below is meaningless."""

    def test_settled_means_completed_and_closed_and_nothing_else(self):
        """The blast radius, pinned. Widening this set is a product decision —
        11,077 `suspended` markets sit one careless edit away."""
        assert set(SETTLED_STATUSES) == {"completed", "closed"}

    def test_a_live_game_is_not_settled(self):
        """200 markets. Suppressing these would empty the dropdown during the
        exact game a reader has the app open to watch."""
        assert "live" not in SETTLED_STATUSES

    def test_a_suspended_game_is_not_settled(self):
        """The largest bucket (11,077) and the one we deliberately do NOT touch:
        zero of them carry a `completed_at`, so we have not established the game
        was played. 19x this ship's blast radius on a guess."""
        assert EVENT_SUSPENDED not in SETTLED_STATUSES

    def test_a_voided_game_is_not_settled(self):
        """A cancelled game is a different defect from a played one."""
        assert "voided" not in SETTLED_STATUSES


# ---------------------------------------------------------------------------
# 2. The NULL trap — the spelling that guts recall
# ---------------------------------------------------------------------------


class TestTheNullTrap:
    """32,483 of the ~50.6K admitted markets carry `event_id IS NULL`.

    `NULL NOT IN (...)` is NULL, not TRUE, so the `~event_id.in_(...)` spelling
    silently drops every one of them — two thirds of the pool — while looking
    like a tightening. NOT EXISTS is correct on a NULL correlation by
    construction. These tests fail on the `IN` spelling.
    """

    def test_the_predicate_is_a_not_exists(self):
        sql = _sql(_typeahead_arm_shape())
        assert "NOT (EXISTS" in sql, sql

    def test_the_predicate_is_not_a_not_in(self):
        """The specific wrong spelling, refused by name."""
        sql = _sql(_typeahead_arm_shape())
        assert "NOT IN" not in sql.upper().replace("NOT (EXISTS", ""), sql

    def test_an_unattached_market_is_not_filtered_by_the_subquery(self):
        """A NULL `event_id` can never satisfy `events.id = futures_markets.
        event_id`, so NOT EXISTS is TRUE and the row survives. Asserted on the
        emitted correlation rather than on prose."""
        sql = _sql(_typeahead_arm_shape())
        assert "events.id = futures_markets.event_id" in sql, sql


# ---------------------------------------------------------------------------
# 3. Correlation — the crash this prevents
# ---------------------------------------------------------------------------


class TestCorrelation:
    def test_the_typeahead_union_arm_correlates_to_futures_markets(self):
        """The subquery selects only from `events`; the outer arm supplies the
        market row. A second `futures_markets` inside the subquery FROM would be
        an uncorrelated cartesian EXISTS — TRUE for every row the moment any one
        market anywhere links to a finished game, i.e. the whole pool suppressed.
        """
        sql = _sql(_typeahead_arm_shape())
        subquery = sql[sql.index("NOT (EXISTS") :]
        head = subquery[: subquery.index("WHERE")]
        assert "futures_markets" not in head, head

    def test_predicate_survives_an_outer_query_that_joins_events_4914(self):
        """🔴 THE REGRESSION THIS PINS IS A COMPILE-TIME CRASH, NOT A WRONG ROW.

        Drop `.correlate(FuturesMarket)` from the helper and this raises:

            InvalidRequestError: Select statement returned no FROM clauses due
            to auto-correlation; specify correlate(<tables>) to control
            correlation manually

        because an enclosing query that joins BOTH tables auto-correlates both
        and leaves the subquery nothing to select from. Measured both ways.
        """
        try:
            sql = _sql(_outer_query_joining_events_shape())
        except InvalidRequestError as exc:  # pragma: no cover - the red state
            # `raise`, not `pytest.fail`: CodeQL cannot see that `pytest.fail`
            # is NoReturn and flags `sql` below as possibly-unbound (1 error on
            # PR #5026). An explicit raise is terminating to any reader, human
            # or analyser, and reports the same thing.
            raise AssertionError(
                f"the predicate decorrelated inside a joined query: {exc}"
            ) from exc
        assert "NOT (EXISTS" in sql, sql
        assert "FROM events" in sql, sql

    def test_only_settled_statuses_reach_the_sql(self):
        sql = _sql(_typeahead_arm_shape())
        assert "'closed', 'completed'" in sql, sql
        for never in ("'live'", "'suspended'", "'voided'", "'scheduled'"):
            assert never not in sql, f"{never} must not be suppressed: {sql}"


# ---------------------------------------------------------------------------
# 4. Anti-drift — /search and /typeahead take ONE predicate
# ---------------------------------------------------------------------------


class TestBothSurfacesCarryIt:
    """`events.py`'s own `_build_league_ticker_match` comment records /search
    keeping a defect for THREE CYCLES after /typeahead's twin was fixed. The
    two pools are built in two places 1,300 lines apart; this is the only thing
    that notices when one of them loses the clause.
    """

    @pytest.mark.parametrize("pool", ["_futures_open_now", "_ta_open_now"])
    def test_the_pool_builder_calls_the_shared_helper(self, pool):
        import inspect

        from app.routes import events as events_module

        src = inspect.getsource(events_module)
        start = src.index(f"{pool} = (")
        body = src[start : src.index(")\n", start)]
        assert "_futures_game_already_played()" in body, (
            f"{pool} no longer filters out a played game's market (#4914):\n{body}"
        )

    def test_there_is_exactly_one_definition_of_the_predicate(self):
        """A second copy is how the drift starts."""
        import inspect

        from app.routes import events as events_module

        src = inspect.getsource(events_module)
        assert src.count("def _futures_game_already_played(") == 1
