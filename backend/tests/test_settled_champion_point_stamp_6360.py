"""The synthesized settlement point stops being stamped with the clock (#6360).

`_apply_settled_winner_freeze` draws a graded champion's line up to 1.0 by
synthesizing a terminal chart point (#1177). Its timestamp was
`min(resolution_date, now)`, and `resolution_date` is a SCHEDULE that Kalshi
routinely leaves in the FUTURE for a settled market (gotcha #14) — so the clamp
returned `now` and the champion's dot sat at the moment of the request, moving
on every read. Measured on production 2026-09-15 on `/api/futures/58675941`
(Vuelta a España 2026, settled 14 September): the point came back at
`11:32:56Z`, then at `11:33:24Z` 28 seconds later.

The ladder that replaces it lives in `app/utils/settlement_stamp.py`; these
tests pin each of its four arms, the two refusals that keep a future or
non-datetime witness out, and — the controls — that the 593,549 markets sitting
on a past `resolution_date` and every existing freeze behaviour are untouched.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.routes.futures import _apply_settled_winner_freeze
from app.utils.settlement_stamp import (
    BASIS_CLOCK,
    BASIS_LAST_OBSERVATION,
    BASIS_RESOLUTION_DATE,
    BASIS_SETTLED_AT,
    as_past_utc,
    last_charted_timestamp,
    settled_point_timestamp,
)

# A fixed clock. Every anchor below is an offset FROM it and nothing branches on
# the real time (gotcha #44).
NOW = datetime(2026, 9, 15, 11, 33, 24, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    """``datetime`` with ``now()`` pinned to :data:`NOW`.

    Subclassed rather than mocked so ``isinstance`` and the other constructors
    (``fromisoformat``) keep working for the module under patch. Mirrors the
    existing idiom in ``test_seasonal_sport_guess_honest_empty.py``.
    """

    @classmethod
    def now(cls, tz=None):  # noqa: D102 - stdlib signature
        return NOW if tz is None else NOW.astimezone(tz)


def _outcome(oid, name, prob=0.5, is_winner=False):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.current_probability = prob
    o.is_winner = is_winner
    return o


def _market(outcomes, resolution_date=None, settled_at=None):
    m = MagicMock()
    m.id = 58675941
    m.name = "Vuelta a Espana 2026: Winner"
    m.market_metadata = None
    m.resolution_date = resolution_date
    m.settled_at = settled_at
    m.outcomes = outcomes
    return m


def _series(oid, name, points):
    return {
        "outcome_id": oid,
        "name": name,
        "history": [
            {"timestamp": ts.isoformat(), "probability": p,
             "american_odds": None, "bookmaker": "consensus"}
            for ts, p in points
        ],
        "eliminated": False,
        "eliminated_at": None,
    }


def _stamp_of(entry):
    return datetime.fromisoformat(entry["history"][-1]["timestamp"])


class TestTheLadder:
    """`settled_point_timestamp` — one test per arm, asserting the BASIS too."""

    def test_a_past_resolution_date_still_wins_and_that_is_the_unchanged_arm(self):
        rd = NOW - timedelta(days=3)
        ts, basis = settled_point_timestamp(
            resolution_date=rd,
            last_observed=NOW - timedelta(hours=1),
            settled_at=NOW - timedelta(hours=2),
            now=NOW,
        )
        assert (ts, basis) == (rd, BASIS_RESOLUTION_DATE)

    def test_a_future_resolution_date_is_skipped_for_the_last_real_observation(self):
        """The Vuelta shape: rd is six days out, so the schedule is no witness."""
        observed = NOW - timedelta(days=1, hours=6)
        ts, basis = settled_point_timestamp(
            resolution_date=NOW + timedelta(days=6),
            last_observed=observed,
            settled_at=NOW - timedelta(hours=22),
            now=NOW,
        )
        assert (ts, basis) == (observed, BASIS_LAST_OBSERVATION)

    def test_settled_at_answers_only_when_there_is_no_schedule_and_no_chart(self):
        settled = NOW - timedelta(days=30)
        ts, basis = settled_point_timestamp(
            resolution_date=None, last_observed=None, settled_at=settled, now=NOW
        )
        assert (ts, basis) == (settled, BASIS_SETTLED_AT)

    def test_the_clock_is_reached_only_when_the_row_holds_no_evidence_at_all(self):
        ts, basis = settled_point_timestamp(
            resolution_date=None, last_observed=None, settled_at=None, now=NOW
        )
        assert (ts, basis) == (NOW, BASIS_CLOCK)

    def test_a_future_settled_at_is_refused_rather_than_clamped(self):
        """Clamping a future witness into the present is the whole defect."""
        ts, basis = settled_point_timestamp(
            resolution_date=NOW + timedelta(days=6),
            last_observed=None,
            settled_at=NOW + timedelta(minutes=5),
            now=NOW,
        )
        assert (ts, basis) == (NOW, BASIS_CLOCK)


class TestWitnessCoercion:
    def test_a_naive_datetime_is_read_as_utc_rather_than_dropped(self):
        naive = (NOW - timedelta(hours=4)).replace(tzinfo=None)
        assert as_past_utc(naive, NOW) == NOW - timedelta(hours=4)

    def test_a_non_datetime_witness_is_refused(self):
        """ORM rows and test doubles both reach here; a MagicMock is not a time."""
        assert as_past_utc(MagicMock(), NOW) is None
        assert as_past_utc("2026-09-14T11:31:56Z", NOW) is None
        assert as_past_utc(None, NOW) is None

    def test_a_witness_exactly_at_now_is_accepted(self):
        assert as_past_utc(NOW, NOW) == NOW


class TestLastChartedTimestamp:
    def test_it_is_the_max_across_every_series(self):
        oh = {
            1: _series(1, "A", [(NOW - timedelta(days=5), 0.2), (NOW - timedelta(days=2), 0.3)]),
            2: _series(2, "B", [(NOW - timedelta(days=4), 0.1), (NOW - timedelta(days=1), 0.4)]),
        }
        assert last_charted_timestamp(oh) == NOW - timedelta(days=1)

    def test_empty_and_malformed_series_are_skipped_not_raised_on(self):
        oh = {
            1: _series(1, "A", []),
            2: {"outcome_id": 2, "name": "B",
                "history": [{"timestamp": "not-a-time", "probability": 0.5}]},
            3: _series(3, "C", [(NOW - timedelta(days=9), 0.7)]),
        }
        assert last_charted_timestamp(oh) == NOW - timedelta(days=9)

    def test_no_chart_at_all_is_none(self):
        assert last_charted_timestamp({}) is None
        assert last_charted_timestamp(None) is None


class TestTheFreezeOnTheSpecimenShape:
    """End-to-end on the Vuelta's shape: settled market, future `resolution_date`.

    🪤 #7611 — THIS CLASS IS THE ONE THAT READS A CLOCK THE SUITE DOES NOT OWN.
    Every class above calls the ladder directly and injects ``now=NOW``, so the
    module comment about gotcha #44 held for them. This one goes through
    ``_apply_settled_winner_freeze``, which takes no ``now`` and reads
    ``datetime.now(timezone.utc)`` itself (``routes/futures.py``) — so the
    specimen's ``resolution_date`` was "future" only against the FROZEN ``NOW``,
    while the code compared it to the WALL clock. ``NOW + 5d10h`` is
    2026-09-20 21:33:24Z; at that instant the wall clock caught up, the
    "future" date became past, the ladder correctly took its
    ``BASIS_RESOLUTION_DATE`` arm, and master went red for every lane with one
    test and no diff. Freezing the route's clock is what makes the word
    "future" in this docstring true at any wall time, and it is why the offsets
    below can stay small and readable instead of being inflated to buy years.
    """

    @pytest.fixture(autouse=True)
    def _freeze_the_route_clock(self, monkeypatch):
        """Pin the clock ``_apply_settled_winner_freeze`` reads to ``NOW``."""
        monkeypatch.setattr("app.routes.futures.datetime", _FrozenDatetime)

    def _vuelta(self):
        champ = _outcome(229691385, "Other", prob=1.0, is_winner=True)
        rider = _outcome(229691386, "Tadej Pogacar", prob=0.0)
        market = _market(
            [champ, rider],
            resolution_date=NOW + timedelta(days=5, hours=10),   # 2026-09-20
            settled_at=NOW - timedelta(hours=24),                # 2026-09-14
        )
        # The champion carries NO charted snapshots — the synthesize branch.
        oh = {
            rider.id: _series(rider.id, "Tadej Pogacar", [
                (NOW - timedelta(days=38), 0.25),
                (NOW - timedelta(days=1, hours=6, minutes=42), 0.0),
            ]),
        }
        return market, oh, champ, rider

    def test_the_champions_dot_lands_on_the_data_not_on_the_clock(self):
        market, oh, champ, _rider = self._vuelta()
        _apply_settled_winner_freeze(market, oh, {champ.id: "Other"})
        assert _stamp_of(oh[champ.id]) == NOW - timedelta(days=1, hours=6, minutes=42)
        assert oh[champ.id]["history"][-1]["probability"] == 1.0
        assert oh[champ.id]["history"][-1]["bookmaker"] == "settlement"

    def test_two_reads_a_second_apart_produce_the_same_timestamp(self):
        """The reader-visible property: the dot does not move between requests."""
        first_market, first_oh, champ, _ = self._vuelta()
        _apply_settled_winner_freeze(first_market, first_oh, {champ.id: "Other"})
        second_market, second_oh, champ2, _ = self._vuelta()
        _apply_settled_winner_freeze(second_market, second_oh, {champ2.id: "Other"})
        assert _stamp_of(first_oh[champ.id]) == _stamp_of(second_oh[champ2.id])

    def test_the_dot_never_precedes_the_field_it_resolves(self):
        market, oh, champ, rider = self._vuelta()
        _apply_settled_winner_freeze(market, oh, {champ.id: "Other"})
        assert _stamp_of(oh[champ.id]) >= _stamp_of(oh[rider.id])

    def test_the_route_clock_is_frozen_so_this_class_cannot_drift_again(self):
        """🪤 #7611 — the strawman for the fixture above.

        ``monkeypatch.setattr`` takes the target as a STRING, so it fails silent
        in exactly one direction that matters: if ``routes/futures.py`` ever
        stops doing ``from datetime import datetime`` (an ``import datetime``
        and a ``datetime.datetime.now`` would do it), the patch lands on a name
        nothing reads, the class quietly goes back on the wall clock, and the
        assertions above pass or fail on the date the suite is run. That is the
        #7611 failure mode returning by a different door, so it is asserted
        rather than assumed.
        """
        from app.routes import futures as futures_module

        assert futures_module.datetime.now(timezone.utc) == NOW
        assert futures_module.datetime.now() == NOW

    def test_a_charted_champion_on_a_future_schedule_lands_beside_its_own_last_point(self):
        """The other branch of the same defect: the champion HAS snapshots.

        `min(resolution_date, now)` sent this one to the clock too, appending a
        1.0 point hours or days right of the line it was supposed to finish.
        """
        champ = _outcome(1, "Spain", prob=0.587, is_winner=True)
        last_real = NOW - timedelta(days=2, hours=5)
        market = _market([champ], resolution_date=NOW + timedelta(days=6))
        oh = {1: _series(1, "Spain", [(NOW - timedelta(days=9), 0.55), (last_real, 0.587)])}
        _apply_settled_winner_freeze(market, oh, {1: "Spain"})
        assert _stamp_of(oh[1]) == last_real + timedelta(seconds=1)

    def test_an_empty_chart_falls_all_the_way_to_settled_at(self):
        """The 1,275-market arm: no schedule, no snapshots anywhere, one witness.

        A mutation that stops the route passing `settled_at` survives every other
        test in this file, because this is the only shape where that argument is
        the one that answers.
        """
        champ = _outcome(1, "Other", prob=1.0, is_winner=True)
        settled = NOW - timedelta(days=11)
        market = _market([champ], resolution_date=None, settled_at=settled)
        oh: dict = {}
        _apply_settled_winner_freeze(market, oh, {1: "Other"})
        assert _stamp_of(oh[1]) == settled

    def test_a_second_pass_over_the_same_chart_is_idempotent(self):
        """A synthesized point must never become the witness for the next one."""
        market, oh, champ, _ = self._vuelta()
        _apply_settled_winner_freeze(market, oh, {champ.id: "Other"})
        first = _stamp_of(oh[champ.id])
        _apply_settled_winner_freeze(market, oh, {champ.id: "Other"})
        assert _stamp_of(oh[champ.id]) == first
        assert len(oh[champ.id]["history"]) == 1


class TestControlsThatMustHoldBothSidesOfThisChange:
    def test_a_past_resolution_date_market_is_stamped_exactly_where_it_was(self):
        """The 593,549-market arm. If this moves, the ship widened."""
        champ = _outcome(1, "Spain", prob=0.587, is_winner=True)
        rd = NOW - timedelta(days=2)
        market = _market([champ], resolution_date=rd, settled_at=NOW - timedelta(days=1))
        oh = {1: _series(1, "Spain", [(NOW - timedelta(days=4), 0.55)])}
        _apply_settled_winner_freeze(market, oh, {1: "Spain"})
        assert _stamp_of(oh[1]) == rd

    def test_a_terminal_point_still_never_precedes_the_champions_own_last_point(self):
        champ = _outcome(1, "Spain", prob=0.587, is_winner=True)
        last_real = NOW - timedelta(hours=3)
        market = _market([champ], resolution_date=NOW - timedelta(days=9))
        oh = {1: _series(1, "Spain", [(last_real, 0.587)])}
        _apply_settled_winner_freeze(market, oh, {1: "Spain"})
        assert _stamp_of(oh[1]) == last_real + timedelta(seconds=1)

    def test_a_line_that_already_converged_gets_no_second_point(self):
        champ = _outcome(1, "Spain", prob=1.0, is_winner=True)
        market = _market([champ], resolution_date=NOW + timedelta(days=6))
        oh = {1: _series(1, "Spain", [(NOW - timedelta(days=2), 0.9995)])}
        _apply_settled_winner_freeze(market, oh, {1: "Spain"})
        assert len(oh[1]["history"]) == 1

    def test_non_champion_lines_terminate_at_their_own_last_value(self):
        champ = _outcome(1, "Spain", prob=0.587, is_winner=True)
        other = _outcome(2, "France", prob=0.30)
        market = _market([champ, other], resolution_date=NOW + timedelta(days=6))
        oh = {
            1: _series(1, "Spain", [(NOW - timedelta(days=2), 0.55)]),
            2: _series(2, "France", [(NOW - timedelta(days=2), 0.30)]),
        }
        _apply_settled_winner_freeze(market, oh, {1: "Spain", 2: "France"})
        assert oh[2]["history"][-1]["probability"] == 0.30
        assert len(oh[2]["history"]) == 1

    def test_co_winners_are_still_a_no_op(self):
        a = _outcome(1, "A", is_winner=True)
        b = _outcome(2, "B", is_winner=True)
        market = _market([a, b], resolution_date=NOW + timedelta(days=6))
        oh = {1: _series(1, "A", [(NOW - timedelta(days=2), 0.5)])}
        _apply_settled_winner_freeze(market, oh, {1: "A", 2: "B"})
        assert len(oh[1]["history"]) == 1

    def test_a_single_non_champion_view_is_still_not_injected_into(self):
        champ = _outcome(1, "Spain", is_winner=True)
        other = _outcome(2, "France", prob=0.30)
        market = _market([champ, other], resolution_date=NOW + timedelta(days=6))
        oh = {2: _series(2, "France", [(NOW - timedelta(days=2), 0.30)])}
        _apply_settled_winner_freeze(market, oh, {1: "Spain", 2: "France"}, outcome_id_filter=2)
        assert 1 not in oh
