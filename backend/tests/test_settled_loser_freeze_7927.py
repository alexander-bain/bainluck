"""The graded-LOSER arm of the settled chart freeze (#7927).

`https://bainluck.com/futures/61010898` — "BMW PGA Championship - Make the Cut",
`status: resolved`. Tommy Fleetwood and Jon Rahm both MISSED the cut, and both
chart lines ended at **84%** as the chart's final, permanent word, while the
same page's Final Results table printed the opposite verdict beside them.
Measured on the served payload 2026-09-22, all 163 outcomes, no sampling:

    is_winner   resolution_source      count
    true        leaderboard              72
    false       leaderboard              66   <- the class this arm ends at 0.0
    false       did_not_play             19   <- deliberately NOT swept
    false       withdrew                  6   <- deliberately NOT swept

This is the mirror of #7921 (the graded-WINNER arm, same function, same call
site) and it is the harder half, because `is_winner=False` is ALSO the column
default: on its own it cannot tell a graded NO from a row nobody ever graded.
So every test below is really a test of the DISCRIMINATOR — the set of
`resolution_source` values whose loss is established independently of the
market's own price — and the ones that matter most are the controls that must
stay untouched. Sweeping them would be far worse than the defect: stamping 0.0
on `ungradeable_result` would have drawn the US Open champion's line to zero
(#6012), and sweeping the price-derived sources would zero whole fields off
arithmetic on the very line being drawn.

Nothing here writes (gotcha #21) and nothing here reads a clock: the stamp is an
argument, so these are pure-value tests (gotcha #44).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.futures import (
    _apply_settled_loser_freeze,
    _apply_settled_winner_freeze,
    _settled_chart_stamp,
    get_futures_history,
)

# A fixed instant, and it is only ever used as an ARGUMENT — nothing in this
# module compares it against the real clock, so it cannot age out (#7611).
SETTLE = datetime(2026, 9, 21, 18, 0, 0, tzinfo=timezone.utc)
EARLIER = SETTLE - timedelta(days=2)


def _outcome(oid, name, *, is_winner=False, resolution_source=None, prob=0.5):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.is_winner = is_winner
    o.resolution_source = resolution_source
    # Real values, because the endpoint sorts the field on them and MagicMocks
    # are not orderable.
    o.current_probability = prob
    o.last_updated = None
    return o


def _market(outcomes, *, mutually_exclusive=False, resolution_date=None, settled_at=None):
    m = MagicMock()
    m.id = 61010898
    m.name = "BMW PGA Championship - Make the Cut"
    m.outcomes = outcomes
    m.resolution_date = resolution_date
    m.settled_at = settled_at
    # Set explicitly for the same reason #7921 set it: a bare MagicMock
    # auto-creates a TRUTHY attribute, which would send a test down the "we do
    # not know" arm while reading as though it had proven the other one.
    m.mutually_exclusive = mutually_exclusive
    return m


def _series(oid, name, points):
    """points = list of (datetime, probability), ascending like the builder's."""
    return {
        "outcome_id": oid,
        "name": name,
        "history": [
            {
                "timestamp": ts.isoformat(),
                "probability": p,
                "american_odds": None,
                "bookmaker": "consensus",
            }
            for ts, p in points
        ],
        "eliminated": False,
        "eliminated_at": None,
    }


def _last(entry):
    return entry["history"][-1]


class TestTheDefectItself:
    """Fleetwood and Rahm: graded `leaderboard` losers whose lines ended at 84%."""

    def test_a_graded_losers_line_ends_at_zero(self):
        fleetwood = _outcome(229405816, "Tommy Fleetwood", resolution_source="leaderboard")
        rahm = _outcome(229035437, "Jon Rahm", resolution_source="leaderboard")
        market = _market([fleetwood, rahm])
        oh = {
            229405816: _series(229405816, "Tommy Fleetwood", [(EARLIER, 0.8383)]),
            229035437: _series(229035437, "Jon Rahm", [(EARLIER, 0.8347)]),
        }

        _apply_settled_loser_freeze(market, oh, SETTLE)

        assert _last(oh[229405816])["probability"] == 0.0
        assert _last(oh[229035437])["probability"] == 0.0
        # Provenance a reader (and the next probe) can tell from a poll.
        assert _last(oh[229405816])["bookmaker"] == "settlement"
        # The journey is kept — the terminal point is APPENDED, never a rewrite.
        assert len(oh[229405816]["history"]) == 2
        assert oh[229405816]["history"][0]["probability"] == 0.8383

    def test_the_terminal_point_is_stamped_at_settlement_not_at_the_last_price(self):
        loser = _outcome(1, "Tommy Fleetwood", resolution_source="leaderboard")
        oh = {1: _series(1, "Tommy Fleetwood", [(EARLIER, 0.8383)])}

        _apply_settled_loser_freeze(_market([loser]), oh, SETTLE)

        assert _last(oh[1])["timestamp"] == SETTLE.isoformat()

    def test_the_terminal_point_never_lands_before_the_lines_own_last_point(self):
        """A settlement stamp older than the data is nudged, never drawn backwards.

        The #6360 ladder can answer with a `resolution_date` that precedes the
        last observation; a point drawn to the LEFT of the line's own end is a
        journey that runs backwards.
        """
        loser = _outcome(1, "Tommy Fleetwood", resolution_source="leaderboard")
        oh = {1: _series(1, "Tommy Fleetwood", [(SETTLE + timedelta(hours=3), 0.8383)])}

        _apply_settled_loser_freeze(_market([loser]), oh, SETTLE)

        assert _last(oh[1])["probability"] == 0.0
        assert datetime.fromisoformat(_last(oh[1])["timestamp"]) == SETTLE + timedelta(
            hours=3, seconds=1
        )

    def test_a_line_that_already_ended_at_zero_gains_no_second_point(self):
        loser = _outcome(1, "Marcus Kinhult", resolution_source="leaderboard")
        oh = {1: _series(1, "Marcus Kinhult", [(EARLIER, 0.0)])}

        _apply_settled_loser_freeze(_market([loser]), oh, SETTLE)

        assert len(oh[1]["history"]) == 1


class TestTheControlsThatMustStayUntouched:
    """The half that matters more. Each case is `is_winner=False` and must NOT move.

    `is_winner=False` is the column DEFAULT, so a freeze keyed on it alone would
    publish "this did not happen" about questions still open, about retractions,
    and about grades derived from the very price the chart draws.
    """

    def test_an_ungraded_row_is_untouched(self):
        """`resolution_source IS NULL` — nobody graded this. #4788's render rule
        already refuses to print a verdict here; so does the chart."""
        ungraded = _outcome(1, "105+ wins", resolution_source=None)
        oh = {1: _series(1, "105+ wins", [(EARLIER, 0.06)])}

        _apply_settled_loser_freeze(_market([ungraded]), oh, SETTLE)

        assert _last(oh[1])["probability"] == 0.06
        assert len(oh[1]["history"]) == 1

    def test_a_null_is_winner_is_untouched(self):
        """NULL is UNKNOWN truth, not a loss — the column is nullable on purpose."""
        never_graded = _outcome(1, "Someone", resolution_source="leaderboard")
        never_graded.is_winner = None
        oh = {1: _series(1, "Someone", [(EARLIER, 0.42)])}

        _apply_settled_loser_freeze(_market([never_graded]), oh, SETTLE)

        assert _last(oh[1])["probability"] == 0.42

    def test_an_ungradeable_result_retraction_is_untouched(self):
        """THE EXPENSIVE ONE. `ungradeable_result` is a RETRACTION (CAL-P056),
        the state of a leg whose stored loss the venue never declared.

        Alexander Zverev sat at `is_winner=false / ungradeable_result` while
        priced at 0.995 as the US Open champion (#6012). A key of
        `resolution_source IS NOT NULL` would have drawn the tournament
        winner's line down to zero.
        """
        zverev = _outcome(1, "Alexander Zverev", resolution_source="ungradeable_result")
        oh = {1: _series(1, "Alexander Zverev", [(EARLIER, 0.995)])}

        _apply_settled_loser_freeze(_market([zverev]), oh, SETTLE)

        assert _last(oh[1])["probability"] == 0.995
        assert len(oh[1]["history"]) == 1

    @pytest.mark.parametrize("source", ["settlement_sync", "clean_resolution"])
    def test_a_price_derived_grade_is_untouched(self, source):
        """Both set `is_winner = price >= 0.95`, so on a wide field EVERY other
        leg is a 'loser' by arithmetic on the line being drawn. Grading a chart
        from its own last point is circular."""
        leg = _outcome(1, "A 40% leg", resolution_source=source)
        oh = {1: _series(1, "A 40% leg", [(EARLIER, 0.40)])}

        _apply_settled_loser_freeze(_market([leg]), oh, SETTLE)

        assert _last(oh[1])["probability"] == 0.40

    @pytest.mark.parametrize("source", ["pass2_guess", "multi_max_prob", "pass3_threshold"])
    def test_a_guess_family_grade_is_untouched(self, source):
        """#754's poison class asserts a loss with no cited authority at all."""
        leg = _outcome(1, "A guessed leg", resolution_source=source)
        oh = {1: _series(1, "A guessed leg", [(EARLIER, 0.31)])}

        _apply_settled_loser_freeze(_market([leg]), oh, SETTLE)

        assert _last(oh[1])["probability"] == 0.31

    @pytest.mark.parametrize("source", ["did_not_play", "withdrew"])
    def test_non_participation_is_untouched_and_that_is_a_decision(self, source):
        """A withdrawal is not a contest lost (#7927's explicit scope call).

        19 `did_not_play` and 6 `withdrew` legs sit on the BMW PGA market beside
        the 66 real losses. The reader's line should stop where the golfer
        stopped rather than be carried to a zero that claims he was beaten.
        Pinned here so a later widening of the source set cannot sweep them in
        silently.
        """
        absent = _outcome(1, "A golfer who never teed off", resolution_source=source)
        oh = {1: _series(1, "A golfer who never teed off", [(EARLIER, 0.55)])}

        _apply_settled_loser_freeze(_market([absent]), oh, SETTLE)

        assert _last(oh[1])["probability"] == 0.55
        assert len(oh[1]["history"]) == 1

    def test_a_graded_winner_is_untouched_by_the_loser_arm(self):
        winner = _outcome(1, "Ludvig Aberg", is_winner=True, resolution_source="leaderboard")
        oh = {1: _series(1, "Ludvig Aberg", [(EARLIER, 0.8403)])}

        _apply_settled_loser_freeze(_market([winner]), oh, SETTLE)

        assert _last(oh[1])["probability"] == 0.8403

    def test_a_loser_the_chart_never_drew_gets_no_series(self):
        """No synthesis. On the BMW PGA market only 2 of the 66 graded losers are
        drawn; conjuring the other 64 would add flat zeros to a 74-line chart."""
        drawn = _outcome(1, "Tommy Fleetwood", resolution_source="leaderboard")
        undrawn = _outcome(2, "Someone with no snapshots", resolution_source="leaderboard")
        oh = {1: _series(1, "Tommy Fleetwood", [(EARLIER, 0.8383)])}

        _apply_settled_loser_freeze(_market([drawn, undrawn]), oh, SETTLE)

        assert _last(oh[1])["probability"] == 0.0
        assert 2 not in oh
        assert len(oh) == 1

    def test_a_filtered_view_only_gets_the_outcome_it_asked_for(self):
        a = _outcome(1, "Tommy Fleetwood", resolution_source="leaderboard")
        b = _outcome(2, "Jon Rahm", resolution_source="leaderboard")
        oh = {
            1: _series(1, "Tommy Fleetwood", [(EARLIER, 0.8383)]),
            2: _series(2, "Jon Rahm", [(EARLIER, 0.8347)]),
        }

        _apply_settled_loser_freeze(_market([a, b]), oh, SETTLE, outcome_id_filter=2)

        assert _last(oh[2])["probability"] == 0.0
        assert _last(oh[1])["probability"] == 0.8383


class TestTheTwoArmsShareOneStamp:
    """#6360's self-evidence trap, now that two arms write to one chart.

    The ladder's second witness is the chart's LAST REAL POINT. An arm that read
    it after the other had appended would take a synthesized point as evidence —
    the defect #6360 closed, rebuilt by the act of adding a second arm.
    """

    def test_winner_and_loser_resolve_at_the_same_instant(self):
        winner = _outcome(1, "Ludvig Aberg", is_winner=True, resolution_source="leaderboard")
        loser = _outcome(2, "Tommy Fleetwood", resolution_source="leaderboard")
        market = _market([winner, loser])
        oh = {
            1: _series(1, "Ludvig Aberg", [(EARLIER, 0.8403)]),
            2: _series(2, "Tommy Fleetwood", [(EARLIER, 0.8383)]),
        }

        stamp = _settled_chart_stamp(market, oh)
        _apply_settled_winner_freeze(market, oh, {1: "Ludvig Aberg"}, settle_ts=stamp)
        _apply_settled_loser_freeze(market, oh, stamp)

        assert _last(oh[1])["probability"] == 1.0
        assert _last(oh[2])["probability"] == 0.0
        assert _last(oh[1])["timestamp"] == _last(oh[2])["timestamp"]

    def test_the_shared_read_is_what_prevents_the_drift(self):
        """The discriminator for the clause above: without it the stamps DIVERGE.

        Re-reading the ladder after the winner arm has appended returns a
        DIFFERENT instant, because the synthesized point is now the chart's last
        point. This test fails if `_settled_chart_stamp` ever stops depending on
        the chart's contents — i.e. it also guards that the assertion above is
        not trivially true.
        """
        winner = _outcome(1, "Ludvig Aberg", is_winner=True, resolution_source="leaderboard")
        market = _market([winner])
        oh = {1: _series(1, "Ludvig Aberg", [(EARLIER, 0.8403)])}

        before = _settled_chart_stamp(market, oh)
        _apply_settled_winner_freeze(market, oh, {1: "Ludvig Aberg"}, settle_ts=before)
        after = _settled_chart_stamp(market, oh)

        assert after != before, (
            "the ladder no longer reads the chart's last point, so sharing one "
            "stamp between the two arms proves nothing — see #6360"
        )

    def test_the_winner_arm_still_reads_its_own_stamp_when_none_is_passed(self):
        """Every existing caller passes no stamp; that path must be unchanged."""
        winner = _outcome(1, "Ludvig Aberg", is_winner=True, resolution_source="leaderboard")
        market = _market([winner], resolution_date=SETTLE)
        oh = {1: _series(1, "Ludvig Aberg", [(EARLIER, 0.8403)])}

        _apply_settled_winner_freeze(market, oh, {1: "Ludvig Aberg"})

        assert _last(oh[1])["probability"] == 1.0
        assert _last(oh[1])["timestamp"] == SETTLE.isoformat()


class TestTheEndpointServesIt:
    """End-to-end through `/api/futures/{id}/history`, the payload #7927 measured."""

    @pytest.mark.asyncio
    async def test_a_missed_cut_is_served_ending_at_zero(self):
        now = datetime.now(timezone.utc)
        winner = _outcome(100, "Ludvig Aberg", is_winner=True, resolution_source="leaderboard")
        loser = _outcome(200, "Tommy Fleetwood", resolution_source="leaderboard")
        ungraded = _outcome(300, "Nobody graded me", resolution_source=None)
        market = _market([winner, loser, ungraded], resolution_date=now - timedelta(hours=6))

        snaps = []
        for i in range(30):
            ts = now - timedelta(hours=12 + i * 2)
            snaps.append(_snapshot(100, ts, 0.84))
            snaps.append(_snapshot(200, ts, 0.8383))
            snaps.append(_snapshot(300, ts, 0.06))

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

        # outcome_id=None mirrors what FastAPI injects when the param is absent.
        result = await get_futures_history(
            market_id=61010898, hours=8760, top_n=8, outcome_id=None, db=db
        )
        by_name = {o["name"]: o for o in result["outcomes"]}
        assert by_name["Tommy Fleetwood"]["history"][-1]["probability"] == 0.0
        assert by_name["Ludvig Aberg"]["history"][-1]["probability"] == 1.0
        # The ungraded rung still ends on its own last OBSERVED point — no
        # settlement point was appended to it. (Its value is the endpoint's
        # de-vigged consensus, not the raw 0.06 seeded above, which is why the
        # assertion is about provenance rather than the number.)
        ungraded_last = by_name["Nobody graded me"]["history"][-1]
        assert ungraded_last["bookmaker"] == "consensus"
        assert ungraded_last["probability"] not in (0.0, 1.0)

    @pytest.mark.asyncio
    async def test_the_route_reads_the_stamp_ladder_before_either_arm_writes(self):
        """THE CALL-SITE GUARD, and the unit tests above cannot stand in for it.

        They pass one stamp into both arms by hand, so they prove the arms USE a
        shared stamp — not that the route still HANDS them one. Let the route
        pass `None` and the loser arm re-reads the #6360 ladder after the winner
        arm has already appended, taking a SYNTHESIZED point as its evidence.

        The specimen is built so that distinction is visible. No past
        `resolution_date` and no `settled_at`, so the ladder falls to its
        last-observation rung; the winner's own line ends ON the chart's last
        real point, so its terminal point is nudged to T+1s; the loser's line
        ends four hours earlier, so it is not nudged. Sharing the ladder read
        therefore lands the loser at T and the winner at T+1s, while a re-read
        would land BOTH at T+1s.
        """
        now = datetime.now(timezone.utc)
        last_real = now - timedelta(hours=12)
        winner = _outcome(100, "Ludvig Aberg", is_winner=True,
                          resolution_source="leaderboard", prob=0.55)
        loser = _outcome(200, "Tommy Fleetwood", resolution_source="leaderboard", prob=0.50)
        # A third line sharing the winner's timestamps, so the de-vig at those
        # instants leaves the winner under 0.999 and its arm actually fires.
        ungraded = _outcome(300, "Nobody graded me", resolution_source=None, prob=0.45)
        market = _market([winner, loser, ungraded], resolution_date=None, settled_at=None)

        snaps = []
        for i in range(30):
            ts = last_real - timedelta(hours=i * 2)
            snaps.append(_snapshot(100, ts, 0.55))
            snaps.append(_snapshot(300, ts, 0.45))
        for i in range(30):
            snaps.append(_snapshot(200, last_real - timedelta(hours=4 + i * 2), 0.50))

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

        result = await get_futures_history(
            market_id=61010898, hours=8760, top_n=8, outcome_id=None, db=db
        )
        by_name = {o["name"]: o for o in result["outcomes"]}
        loser_end = by_name["Tommy Fleetwood"]["history"][-1]
        winner_end = by_name["Ludvig Aberg"]["history"][-1]
        assert loser_end["probability"] == 0.0
        assert winner_end["probability"] == 1.0
        # The loser resolves on the chart's last REAL observation…
        assert datetime.fromisoformat(loser_end["timestamp"]) == last_real
        # …which is strictly before the winner's nudged point. Equal stamps here
        # would mean the ladder was read twice. See #6360.
        assert datetime.fromisoformat(loser_end["timestamp"]) < datetime.fromisoformat(
            winner_end["timestamp"]
        )


def _snapshot(outcome_id, captured_at, prob):
    s = MagicMock()
    s.outcome_id = outcome_id
    s.captured_at = captured_at
    s.probability = prob
    s.bookmaker = "test"
    return s
