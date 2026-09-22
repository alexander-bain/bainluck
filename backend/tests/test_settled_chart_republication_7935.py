"""A settled chart stops saw-toothing between its price and its grade (#7935).

`https://bainluck.com/futures/61010898` — "BMW PGA Championship - Make the Cut",
`resolved`, hero reads "Ludvig Aberg WON". Under it, the Probability Trend chart
swung between **84% and 0% forty times** across the four days AFTER the cut had
already eliminated Tommy Fleetwood. It is the settled page's headline graphic
and it was not readable as a journey.

Measured on the SERVED payload 2026-09-22, no sampling — `/api/futures/{id}/history`
for all 13 `Make the Cut` markets:

    markets affected                7 of 13   (the diagnosis on #7935 named 3)
    charted lines repaired        440
    stale points dropped       15,038   = 10.9% of every point the family charts
    `eliminated` flags recovered    0 -> 6

The cause is producer-side and is lane1b's #7947: two tasks write
`bookmaker="datagolf_model"` for one outcome — an hourly poll republishing
PRE-TOURNAMENT predictions, and a 90-second in-play beat writing the real board.
That fix stops the next tournament. It rewrites no stored row, so every board
already written stays broken for its reader; this is that half, and the two are
independent (neither blocks the other).

🔴 THE TESTS THAT MATTER MOST HERE ARE THE CONTROLS. The obvious rule — "on a
settled market, drop points that disagree with the grade" — is wrong, and
`TestTheJourneysThisMustNeverTouch` is why: a longshot priced at ~0, trading up
through a real journey and finally losing has its FIRST point already at the
graded value, so that rule erases every honest observation it ever had. The
anchor is the symptom instead: a republication RETURNS to the grade once per
producer cycle, tens of times; a journey crosses it once. Measured across 74
settled markets / 565 lines, the return count is bimodal — 51 lines return 0
times, 514 return 7+, and not one returns between 1 and 6.

Nothing here writes (gotcha #21) and no assertion reads a clock (gotcha #44).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.futures import (
    _at_grade,
    _detect_elimination,
    _drop_post_decision_republication,
    _settled_graded_values,
    get_futures_history,
)

BASE = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)

# Tommy Fleetwood's two real families, to the digit, off the served payload.
STALE_PRICE = 0.8383
GRADED_LOSS = 0.0


def _pt(minutes, prob, bookmaker="consensus"):
    return {
        "timestamp": (BASE + timedelta(minutes=minutes)).isoformat(),
        "probability": prob,
        "american_odds": None,
        "bookmaker": bookmaker,
    }


# The instant the cut decides the line, in `_sawtooth`'s fixture: three lead-in
# points at 30-minute spacing, so the decision lands at minute 90. Named because
# two assertions must compare against it rather than against the output.
DECISION_AT = (BASE + timedelta(minutes=90)).isoformat()


def _sawtooth(grade, stale, *, cycles=8, lead_in=(0.25, 0.51, 0.7)):
    """The real shape: a genuine climb, the decision, then the producer's echo.

    One cycle is the pair #7935 measured — the stale republication, then the
    graded value ~50 s later — repeated every ~90 minutes.
    """
    history = [_pt(i * 30, p) for i, p in enumerate(lead_in)]
    t = len(lead_in) * 30
    history.append(_pt(t, grade))  # the decision itself
    for c in range(cycles):
        history.append(_pt(t + 90 * (c + 1), stale))
        history.append(_pt(t + 90 * (c + 1) + 1, grade))
    return history


def _returns_to_grade(history, grade):
    """How many times the line comes BACK to its graded value."""
    first = next((i for i, p in enumerate(history) if _at_grade(p["probability"], grade)), None)
    if first is None:
        return 0
    n, prev = 0, True
    for p in history[first + 1:]:
        at = _at_grade(p["probability"], grade)
        if at and not prev:
            n += 1
        prev = at
    return n


class TestTheDefectItself:
    """The specimen, and what a reader gets instead."""

    def test_the_specimen_really_does_saw_tooth(self):
        """THE RIG CONTROL. Every assertion below is about removing something;
        this one proves the thing was there. A fixture that never carried the
        defect would let every other test in this class pass vacuously."""
        history = _sawtooth(GRADED_LOSS, STALE_PRICE)
        assert _returns_to_grade(history, GRADED_LOSS) == 8
        assert sum(1 for p in history if p["probability"] == STALE_PRICE) == 8

    def test_a_missed_cut_line_loses_its_echo_and_keeps_its_journey(self):
        history = _sawtooth(GRADED_LOSS, STALE_PRICE)
        out = _drop_post_decision_republication(history, GRADED_LOSS)

        assert [p["probability"] for p in out if p["probability"] == STALE_PRICE] == []
        # The climb TO the cut is the part worth reading, and it is untouched.
        assert [p["probability"] for p in out[:3]] == [0.25, 0.51, 0.7]
        # The decision itself is KEPT, and it is the drop to the cut — the one
        # point on the line that shows the reader when it happened. Pinned by
        # its own timestamp, not read back off the result.
        assert out[3]["probability"] == GRADED_LOSS
        assert out[3]["timestamp"] == DECISION_AT
        # What remains is monotone to the result: one value after the decision.
        assert {p["probability"] for p in out[3:]} == {GRADED_LOSS}

    def test_a_made_cut_line_is_the_same_defect_and_the_same_repair(self):
        """72 of the 74 charted BMW PGA lines are graded WINNERS alternating
        between their pre-cut price and 1.0 — the same echo, mirrored."""
        history = _sawtooth(1.0, 0.2503)
        out = _drop_post_decision_republication(history, 1.0)
        assert {p["probability"] for p in out[3:]} == {1.0}
        assert 0.2503 not in [p["probability"] for p in out]

    def test_the_line_still_ends_at_its_grade(self):
        """#7927's guarantee — a settled line ends at its result — survives, and
        now does so on a REAL observation rather than a synthesized point."""
        for grade, stale in ((GRADED_LOSS, STALE_PRICE), (1.0, 0.2503)):
            out = _drop_post_decision_republication(_sawtooth(grade, stale), grade)
            assert out[-1]["probability"] == grade
            assert out[-1]["bookmaker"] == "consensus"

    def test_a_de_vigged_near_miss_does_not_survive_as_a_spike(self):
        """The grade-side family lands at 0.9989 on 18 of the 74 real lines (the
        de-vig squeeze). Those are dropped with the echo rather than left behind
        as the only non-1.0 points on a flat line — at chart scale they are the
        same pixel, and keeping them would reintroduce the saw-tooth in miniature."""
        history = _sawtooth(1.0, 0.2503)
        history.insert(-1, _pt(2000, 0.9989))
        out = _drop_post_decision_republication(history, 1.0)
        assert {p["probability"] for p in out[3:]} == {1.0}


class TestTheJourneysThisMustNeverTouch:
    """The controls. Erasing a reader's real observations is far worse than the
    defect, so each of these is a line that LOOKS gradeable and must survive."""

    def test_a_longshot_that_starts_at_zero_and_trades_up_keeps_everything(self):
        """THE CASE THAT KILLS THE OBVIOUS RULE. First point already at the
        graded value, a real journey away from it, and a real loss at the end —
        "drop what disagrees with the grade" erases the entire line."""
        history = [
            _pt(0, 0.0), _pt(60, 0.12), _pt(120, 0.31),
            _pt(180, 0.44), _pt(240, 0.19), _pt(300, 0.0),
        ]
        out = _drop_post_decision_republication(history, 0.0)
        assert out is history  # same object: the response is byte-for-byte unchanged
        assert [p["probability"] for p in out] == [0.0, 0.12, 0.31, 0.44, 0.19, 0.0]

    def test_a_line_that_never_reaches_its_grade_is_untouched(self):
        """95 of 175 outcomes in the measured sample. Nothing was decided
        in-window, so there is no anchor and nothing to compact."""
        history = [_pt(i * 60, p) for i, p in enumerate((0.3, 0.42, 0.55, 0.61))]
        assert _drop_post_decision_republication(history, 1.0) is history

    @pytest.mark.parametrize("returns", [1, 2])
    def test_a_line_that_crosses_its_grade_a_couple_of_times_is_untouched(self, returns):
        """The empty band, asserted from below. Real lines return 0 times;
        echoes return 7+. Anything a human could mistake for a journey stays."""
        history = [_pt(0, 0.4), _pt(30, 1.0)]
        for c in range(returns):
            history.append(_pt(60 + c * 60, 0.72))
            history.append(_pt(90 + c * 60, 1.0))
        assert _returns_to_grade(history, 1.0) == returns
        assert _drop_post_decision_republication(history, 1.0) is history

    def test_the_threshold_is_where_the_measurement_put_it(self):
        """Three returns is the first count treated as an echo — pinned so a
        later edit cannot drift it into the populated part of the distribution
        without this failing."""
        history = [_pt(0, 0.4), _pt(30, 1.0)]
        for c in range(3):
            history.append(_pt(60 + c * 60, 0.72))
            history.append(_pt(90 + c * 60, 1.0))
        out = _drop_post_decision_republication(history, 1.0)
        assert out is not history
        assert 0.72 not in [p["probability"] for p in out]


class TestWhichOutcomesAreEvenGraded:
    """`_settled_graded_values` — and it deliberately reuses #7927's keys rather
    than forming a second opinion about what a grade is."""

    def _o(self, oid, *, is_winner=False, source=None):
        o = MagicMock()
        o.id = oid
        o.is_winner = is_winner
        o.resolution_source = source
        return o

    def _m(self, outcomes, *, mutually_exclusive=False):
        m = MagicMock()
        m.outcomes = outcomes
        m.mutually_exclusive = mutually_exclusive
        return m

    def test_a_graded_winner_and_an_evidenced_loser_are_graded(self):
        graded = _settled_graded_values(self._m([
            self._o(1, is_winner=True, source="leaderboard"),
            self._o(2, is_winner=False, source="leaderboard"),
        ]))
        assert graded == {1: 1.0, 2: 0.0}

    def test_an_ungraded_row_is_not_graded(self):
        assert _settled_graded_values(self._m([self._o(1, is_winner=False, source=None)])) == {}

    def test_an_unmeasured_is_winner_is_not_graded(self):
        """`None` is unknown truth, not a loss — the nullable column's whole
        point. Fails closed (#7927's `_is_evidenced_loss`)."""
        assert _settled_graded_values(self._m([self._o(1, is_winner=None, source="leaderboard")])) == {}

    def test_a_bare_mock_attribute_is_not_a_grade(self):
        """A MagicMock auto-attribute is truthy. Strict `is True` is what stops a
        test double licensing the removal of a reader's points."""
        o = MagicMock()
        o.id = 1
        o.resolution_source = "leaderboard"
        assert _settled_graded_values(self._m([o])) == {}

    @pytest.mark.parametrize("source", ["settlement_sync", "clean_resolution", "ungradeable_result"])
    def test_a_price_derived_or_retracted_grade_is_not_a_loss(self, source):
        """#7927's discriminator, inherited whole: a price-derived "loss" is
        arithmetic on the very line being drawn, and `ungradeable_result` is a
        RETRACTION — it sat on the US Open champion at 0.995 (#6012)."""
        assert _settled_graded_values(self._m([self._o(1, is_winner=False, source=source)])) == {}

    def test_a_mutex_field_with_two_winners_grades_nothing(self):
        """A grading CONTRADICTION must not decide which observations were real.
        Same no-op, same reason, as the winner freeze."""
        graded = _settled_graded_values(self._m([
            self._o(1, is_winner=True, source="leaderboard"),
            self._o(2, is_winner=True, source="leaderboard"),
        ], mutually_exclusive=True))
        assert graded == {}

    def test_co_winners_on_an_independent_field_are_normal(self):
        """73 golfers make the cut (#7921). On an independent field that is the
        answer, not an ambiguity."""
        graded = _settled_graded_values(self._m([
            self._o(1, is_winner=True, source="leaderboard"),
            self._o(2, is_winner=True, source="leaderboard"),
        ], mutually_exclusive=False))
        assert graded == {1: 1.0, 2: 1.0}


class TestTheEliminationFlagReadsTheRepairedLine:
    """Ordering, not decoration: the flag is inferred from the TAIL, so on a
    saw-toothing board it read `false` for golfers who had already missed the
    cut — and `eliminated` is what draws a line in the chart's grey."""

    def test_a_saw_toothing_loser_reads_as_not_eliminated(self):
        assert _detect_elimination(_sawtooth(GRADED_LOSS, STALE_PRICE))["eliminated"] is False

    def test_and_reads_as_eliminated_once_the_echo_is_gone(self):
        out = _drop_post_decision_republication(_sawtooth(GRADED_LOSS, STALE_PRICE), GRADED_LOSS)
        elim = _detect_elimination(out)
        assert elim["eliminated"] is True
        # At the cut, not at the last echo 12 hours later — and taken from the
        # FIXTURE's known instant. Reading it back off `out` would let a change
        # that discards the decision point keep passing (it did; a mutant that
        # dropped it survived until this assertion was pinned).
        assert elim["eliminated_at"] == DECISION_AT


def _snapshot(outcome_id, captured_at, prob):
    s = MagicMock()
    s.outcome_id = outcome_id
    s.captured_at = captured_at
    s.probability = prob
    s.bookmaker = "datagolf_model"
    s.american_odds = None
    return s


def _outcome(oid, name, *, is_winner=False, resolution_source=None, prob=0.5):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.is_winner = is_winner
    o.resolution_source = resolution_source
    o.current_probability = prob
    o.last_updated = None
    o.external_id = None
    return o


class TestTheEndpointServesIt:
    """End-to-end through `/api/futures/{id}/history` — the payload #7935 read.

    The unit tests above cannot stand in for this: they call the helper with a
    grade in hand, which proves the rule works, not that the ROUTE still applies
    it, still applies it before the elimination flag, and still counts what it
    draws.
    """

    def _board(self):
        """Two graded lines on an independent field, each alternating between a
        stale price and its grade — Fleetwood and Aberg, in miniature."""
        now = datetime.now(timezone.utc)
        winner = _outcome(100, "Ludvig Aberg", is_winner=True,
                          resolution_source="leaderboard", prob=0.84)
        loser = _outcome(200, "Tommy Fleetwood", is_winner=False,
                         resolution_source="leaderboard", prob=0.8383)
        market = MagicMock()
        market.id = 61010898
        market.name = "BMW PGA Championship - Make the Cut"
        market.outcomes = [winner, loser]
        market.mutually_exclusive = False
        market.resolution_date = now - timedelta(hours=2)
        market.settled_at = now - timedelta(hours=2)
        market.market_metadata = None

        snaps = []
        start = now - timedelta(days=4)
        for i in range(3):  # the honest climb, before the cut
            ts = start + timedelta(hours=i)
            snaps.append(_snapshot(100, ts, 0.60 + 0.08 * i))
            snaps.append(_snapshot(200, ts, 0.55 + 0.09 * i))
        cut = start + timedelta(hours=4)
        snaps.append(_snapshot(100, cut, 1.0))
        snaps.append(_snapshot(200, cut, 0.0))
        for c in range(9):  # the producer's echo, every ~90 minutes
            t = cut + timedelta(minutes=90 * (c + 1))
            snaps.append(_snapshot(100, t, 0.8403))
            snaps.append(_snapshot(200, t, 0.8383))
            snaps.append(_snapshot(100, t + timedelta(seconds=50), 1.0))
            snaps.append(_snapshot(200, t + timedelta(seconds=50), 0.0))
        return market, snaps

    async def _serve(self, market, snaps):
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = market
                return result
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = snaps
            result.scalars.return_value = scalars_mock
            return result

        db = AsyncMock()
        db.execute = mock_execute
        return await get_futures_history(
            market_id=61010898, hours=8760, top_n=8, outcome_id=None, db=db
        )

    @pytest.mark.asyncio
    async def test_the_route_would_serve_the_saw_tooth_without_this(self, monkeypatch):
        """THE BEFORE, through the real route. Disabling only the threshold
        leaves every other line of the endpoint in place, so this is the served
        payload as a reader got it — and it is what the next test's assertions
        would otherwise be passing against vacuously."""
        monkeypatch.setattr("app.routes.futures._GRADE_RETURN_MIN", 10_000)
        result = await self._serve(*self._board())
        by_name = {o["name"]: o for o in result["outcomes"]}
        fleetwood = by_name["Tommy Fleetwood"]["history"]
        assert _returns_to_grade(fleetwood, 0.0) >= 7
        assert max(p["probability"] for p in fleetwood[4:]) > 0.5
        assert by_name["Tommy Fleetwood"]["eliminated"] is False

    @pytest.mark.asyncio
    async def test_the_served_board_is_one_readable_journey(self):
        result = await self._serve(*self._board())
        by_name = {o["name"]: o for o in result["outcomes"]}

        fleetwood = by_name["Tommy Fleetwood"]["history"]
        aberg = by_name["Ludvig Aberg"]["history"]
        # No return to the grade at all: the alternation is gone, not reduced.
        assert _returns_to_grade(fleetwood, 0.0) == 0
        assert _returns_to_grade(aberg, 1.0) == 0
        # Both still end at their result (#7927 composes rather than conflicts).
        assert fleetwood[-1]["probability"] == 0.0
        assert aberg[-1]["probability"] == 1.0
        # And the climb before the cut is still drawn — this is a compaction,
        # not a truncation to the settled value.
        assert len(fleetwood) > 3
        assert max(p["probability"] for p in fleetwood[:3]) > 0.3

    @pytest.mark.asyncio
    async def test_the_served_flag_marks_the_eliminated_golfer(self):
        result = await self._serve(*self._board())
        by_name = {o["name"]: o for o in result["outcomes"]}
        assert by_name["Tommy Fleetwood"]["eliminated"] is True
        assert by_name["Ludvig Aberg"]["eliminated"] is False

    @pytest.mark.asyncio
    async def test_the_point_count_promises_only_what_is_drawn(self, monkeypatch):
        """`total_data_points` feeds the chart's own sparse empty-state, so a
        dropped point may not be counted (gotcha #53: an absence and a fact must
        not share a shape)."""
        before = await self._serve(*self._board())
        drawn = sum(len(o["history"]) for o in before["outcomes"])
        assert before["total_data_points"] == drawn

        monkeypatch.setattr("app.routes.futures._GRADE_RETURN_MIN", 10_000)
        uncompacted = await self._serve(*self._board())
        assert uncompacted["total_data_points"] > before["total_data_points"]
