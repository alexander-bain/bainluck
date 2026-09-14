"""#6051 — the "gone quiet" mark fired on a price that moved 100 seconds ago.

## the defect

`/api/events/{id}/game-markets` publishes an `observed_at` per priced leg, and
`components/event/PriceAgeMark` draws NOTHING unless that stamp is already
stale. So the field is not decoration: a stamp that is too old does not
misprint an age, it MANUFACTURES a "this price has gone quiet" warning over a
card whose prices are moving every minute — the one thing the mark exists to
say.

Measured on production 2026-09-14 03:37Z, event 15311956 (Chunichi Dragons @
Hanshin Tigers, upcoming): every Kalshi leg served
`observed_at = 2026-09-13T22:28:27Z`, 5.15 h before the read, while the same
rows' `price_changed_at` read 03:35:49Z / 03:34:12Z / 03:26:16Z. The snapshot
series had stopped; the prices had not. Fleet-wide on ±1-day events, legs whose
price provably moved after their newest snapshot: polymarket 1,123 of 6,366
(mean gap 13.8 h), kalshi 3,067 of 14,035 (mean 2.05 h).

## what is pinned here, and why each one has a mutant

The rule is `observed_at = max(newest snapshot, price_changed_at)` under three
refusals. Every arm below is a way the rule could be written to look right and
be wrong:

* the floor must **win** when the price moved after the snapshot (the ship);
* it must **never lose the newer snapshot** — a floor that simply replaced the
  answer would make a freshly-snapshotted row read as old as its last MOVE,
  which is the same lie pointing the other way;
* a **graded** row is refused, because `backfill_winners` stamps
  `price_changed_at` in the statement that crowns a leg 1.0/0.0 — that is our
  certainty, not a venue reading;
* an **unpriced** row is refused, because `datagolf` stamps the clearing of a
  withdrawn leg, and there is then no price for an age to be about;
* the mapping **gains no keys**: `routes/tournaments.py` reads membership as
  evidence of a priced observation, and this fix does not get to redefine that
  word underneath it.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.latest_observation import (
    load_latest_observed_at,
    price_movement_floor,
)

NOW = datetime(2026, 9, 14, 3, 37, 0, tzinfo=timezone.utc)
#: The production specimen's own two stamps, to the minute.
SNAPSHOT_AT = datetime(2026, 9, 13, 22, 28, 27, tzinfo=timezone.utc)
PRICE_MOVED_AT = datetime(2026, 9, 14, 3, 35, 49, tzinfo=timezone.utc)


class _Rows:
    """What `session.execute(...)` returns: an object with `.all()`."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Row:
    """A result row addressed by attribute.

    Unset columns read as `None` rather than raising, for the reason
    `test_latest_observation_lat_p147.py` gives at length: this SELECT is
    shared, and a strict double turns "a sibling branch added a column" into a
    red test in a file with no opinion about it. Every column this file asserts
    on is set explicitly and checked by value.
    """

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return None


class _Session:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, statement, params=None):
        return _Rows(self._rows)


def _leg(**overrides):
    """A priced, ungraded leg whose snapshot is old — the defect's own shape."""
    row = {
        "id": 227688721,
        "observed_at": SNAPSHOT_AT,
        "price_changed_at": PRICE_MOVED_AT,
        "resolution_source": None,
        "current_probability": 0.6,
    }
    row.update(overrides)
    return _Row(**row)


class TestThePureRule:
    def test_a_moved_price_on_a_priced_ungraded_leg_is_an_observation(self):
        assert (
            price_movement_floor(PRICE_MOVED_AT, None, 0.6) == PRICE_MOVED_AT
        )

    def test_a_graded_leg_is_refused_because_the_stamp_may_be_our_own_crown(self):
        """`backfill_winners` writes `price_changed_at` beside
        `resolution_source='api_settlement'` when it sets a leg to 1.0/0.0."""
        assert price_movement_floor(PRICE_MOVED_AT, "api_settlement", 1.0) is None

    def test_any_grader_counts_not_only_the_one_that_wrote_the_specimen(self):
        for source in ("api_settlement", "game_score", "manual", "espn"):
            assert price_movement_floor(PRICE_MOVED_AT, source, 0.6) is None

    def test_an_unpriced_leg_is_refused_so_a_withdrawal_is_not_an_observation(self):
        """`datagolf` clears a withdrawn leg's price and stamps the change."""
        assert price_movement_floor(PRICE_MOVED_AT, None, None) is None

    def test_a_zero_price_is_a_price_and_is_not_read_as_absent(self):
        """0.0 is falsy. A leg quoted at zero still has a number on the page,
        so the refusal is keyed on `is None` and this pins it."""
        assert price_movement_floor(PRICE_MOVED_AT, None, 0.0) == PRICE_MOVED_AT

    def test_a_row_no_write_ever_moved_has_no_floor(self):
        assert price_movement_floor(None, None, 0.6) is None

    def test_a_naive_stamp_is_read_as_utc_rather_than_compared_and_raised(self):
        naive = PRICE_MOVED_AT.replace(tzinfo=None)
        assert price_movement_floor(naive, None, 0.6) == PRICE_MOVED_AT


@pytest.mark.asyncio
class TestTheLoaderServesTheHonestStamp:
    async def test_the_specimen_stops_being_five_hours_old(self):
        """The ship: event 15311956's moneyline, exactly as production held it."""
        out = await load_latest_observed_at(_Session([_leg()]), [227688721])

        assert out[227688721] == PRICE_MOVED_AT
        assert (NOW - out[227688721]) < timedelta(minutes=30), (
            "the served age must fall under SOURCE_STALE_AFTER_MS, which is what "
            "makes PriceAgeMark stop drawing a warning over a moving price"
        )

    async def test_a_fresher_snapshot_is_never_dragged_back_to_the_last_move(self):
        """The same lie pointing the other way, and the reason this is a max.

        A leg whose price is STABLE is snapshotted every poll while
        `price_changed_at` stays at its last move — hours or days back. A floor
        that replaced the answer instead of raising it would report that old
        move as the observation and call a just-confirmed price stale.
        """
        just_polled = NOW - timedelta(minutes=2)
        stable_since = NOW - timedelta(days=3)

        out = await load_latest_observed_at(
            _Session(
                [_leg(observed_at=just_polled, price_changed_at=stable_since)]
            ),
            [227688721],
        )

        assert out[227688721] == just_polled

    async def test_an_untouched_row_is_served_verbatim(self):
        """Not merely equal: the same object, so a row this rule does not touch
        cannot acquire a re-formatted spelling of a stamp it already carried."""
        row = _leg(price_changed_at=None)

        out = await load_latest_observed_at(_Session([row]), [227688721])

        assert out[227688721] is row.observed_at

    async def test_a_graded_leg_keeps_its_snapshot_stamp_through_the_loader(self):
        out = await load_latest_observed_at(
            _Session([_leg(resolution_source="api_settlement", current_probability=1.0)]),
            [227688721],
        )

        assert out[227688721] == SNAPSHOT_AT

    async def test_a_leg_with_no_snapshot_gains_no_key_however_hard_its_price_moved(
        self,
    ):
        """`routes/tournaments.py` reads membership as evidence of a priced
        observation. The floor may make an answer newer; it may not invent one."""
        out = await load_latest_observed_at(
            _Session([_leg(observed_at=None)]), [227688721]
        )

        assert out == {}

    async def test_an_empty_id_list_still_asks_the_database_nothing(self):
        class _Explode:
            async def execute(self, statement, params=None):  # pragma: no cover
                raise AssertionError("no statement may be issued for zero ids")

        assert await load_latest_observed_at(_Explode(), []) == {}

    async def test_the_rule_is_applied_per_row_and_not_to_the_batch(self):
        """One card's legs share a poll batch but not a settlement state, and a
        rule accidentally written over the batch (a single `max`, an `any`)
        would hand one row's answer to its neighbour."""
        moved = _leg(id=1)
        graded = _leg(id=2, resolution_source="game_score", current_probability=1.0)
        stable = _leg(id=3, observed_at=NOW - timedelta(minutes=1))

        out = await load_latest_observed_at(_Session([moved, graded, stable]), [1, 2, 3])

        assert out == {
            1: PRICE_MOVED_AT,
            2: SNAPSHOT_AT,
            3: NOW - timedelta(minutes=1),
        }


@pytest.mark.asyncio
class TestTheStatementStillAsksForWhatTheRuleNeeds:
    async def test_the_three_columns_ride_the_select_that_was_already_there(self):
        """A pure rule nobody feeds is a rule that does nothing.

        The floor is only reachable if the loader SELECTs the columns it reads,
        and it must keep doing so in ONE statement — the round trip this module
        exists to avoid is the whole of LAT-P147.
        """
        captured: list[object] = []

        class _Recording:
            async def execute(self, statement, params=None):
                captured.append(statement)
                return _Rows([])

        await load_latest_observed_at(_Recording(), [1, 2, 3])

        assert len(captured) == 1, "the floor must not cost a second round trip"
        rendered = str(captured[0]).lower()
        for column in ("price_changed_at", "resolution_source", "current_probability"):
            assert column in rendered, f"the loader never asks for {column}"


@pytest.mark.asyncio
class TestTheFloorCannotFiveHundredThePage:
    """The stamps are not always the type the model promises, and a freshness
    display may not be the thing that discovers it.

    `latest_observation`'s own docstring refuses to raise over a timezone; the
    first cut of this floor read `.tzinfo` off whatever it was handed and so
    raised `AttributeError` on the ISO STRINGS that
    `test_latest_observation_lat_p147` passes in. That is a 500 on
    `/api/events/{id}/game-markets`, for a grey four-character age mark.
    """

    async def test_an_iso_string_snapshot_is_compared_rather_than_crashed_on(self):
        out = await load_latest_observed_at(
            _Session([_leg(observed_at=SNAPSHOT_AT.isoformat())]), [227688721]
        )

        assert out[227688721] == PRICE_MOVED_AT

    async def test_an_unparseable_stamp_serves_verbatim_and_does_not_raise(self):
        row = _leg(observed_at="whenever")

        out = await load_latest_observed_at(_Session([row]), [227688721])

        assert out[227688721] == "whenever", (
            "an undatable stamp must travel untouched — the floor cannot prove "
            "it is newer than something it cannot read"
        )

    async def test_an_unparseable_price_stamp_is_not_a_floor(self):
        out = await load_latest_observed_at(
            _Session([_leg(price_changed_at="whenever")]), [227688721]
        )

        assert out[227688721] == SNAPSHOT_AT
