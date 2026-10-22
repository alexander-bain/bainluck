"""Every served settlement point says which witness placed it (#10955 Step 1).

`/api/futures/{id}/history` ends a graded leg's line with a synthesized
`bookmaker: "settlement"` point (the winner arm, #1177/#7921, and the loser arm,
#7927). Its timestamp comes from the #6360 ladder in
`app/utils/settlement_stamp.py`, and the ladder already knows which of its four
witnesses answered — `resolution_date`, `last_observation`, `settled_at` or
`clock` — but the route threw that away and served a bare instant. On
`/futures/199045` (AL Champion, future `resolution_date`) a graded loser's 0%
was stamped at a still-trading sibling's newest trade, and no reader could tell
that instant from an observed result time (Authority's 2026-10-22 contract
read: neither web nor native distinguishes the point at all).

Step 1 is ADDITIVE ONLY: the point now carries `settlement_basis`, the raw
witness name. No timestamp, value or other key moves, and this file does not
claim the marker stopped moving — on the 199045 shape it still sits at the
board's last trade. Readers keyed on the basis are Step 2; placement is Step 3.

The four binds this file guards (Live's clearance, 2026-10-22 05:32Z):

* B1 — name the witness ACTUALLY used. A point nudged to one second after the
  leg's own last real point serves `last_observation`, whatever the ladder said.
* B2 — only the four existing constants, served raw.
* B3 — a bare `settle_ts` with no basis and no nudge appends NO key (698's exact
  dict equality is the standing control). With no `settle_ts` the arm reads the
  pair itself and a lone basis is ignored.
* B4 — placement untouched.

Fixture pattern: `tests/test_settled_loser_freeze_7927.py` and the prepared
#11158 candidate's route rig (MagicMock rows, a mocked `db.execute`, the real
`get_futures_history`). Every helper-level stamp is an argument; route anchors
are offsets from the import instant and never branch on the clock (gotcha #44).
"""

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import futures as futures_routes
from app.routes.futures import (
    _apply_settled_loser_freeze,
    _apply_settled_winner_freeze,
    _freeze_one_winner_line,
    _settled_chart_stamp,
    get_futures_history,
)
from app.utils.settlement_stamp import (
    BASIS_CLOCK,
    BASIS_LAST_OBSERVATION,
    BASIS_RESOLUTION_DATE,
    BASIS_SETTLED_AT,
)

FOUR_BASES = {BASIS_RESOLUTION_DATE, BASIS_LAST_OBSERVATION, BASIS_SETTLED_AT, BASIS_CLOCK}
# The keys a settlement point carried before Step 1, and still carries when the
# caller named no witness (B3).
BARE_KEYS = {"timestamp", "probability", "american_odds", "bookmaker"}

SECOND = timedelta(seconds=1)
# Helper-level instants are only ever ARGUMENTS, so they cannot age out.
SETTLE = datetime(2026, 9, 21, 18, 0, 0, tzinfo=timezone.utc)
EARLIER = SETTLE - timedelta(days=2)
LATER = SETTLE + timedelta(days=2)

# Route-level anchors: offsets from the import instant (the route reads the
# real clock for the ladder's `now`).
NOW = datetime.now(timezone.utc)
A_LAST = NOW - timedelta(days=26)      # the graded leg's own last observation
B_LAST = NOW - timedelta(days=1)       # the still-trading siblings' newest
B_LATER = NOW - timedelta(hours=6)     # ...and a newer one, on the next read
DEADLINE = NOW + timedelta(days=40)    # a future schedule: the ladder skips it


def _outcome(oid, name, *, is_winner=False, resolution_source=None, prob=0.5):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.is_winner = is_winner
    o.resolution_source = resolution_source
    o.current_probability = prob
    o.last_updated = None
    return o


def _market(outcomes, *, mutually_exclusive=True, resolution_date=None,
            settled_at=None, status="open", market_id=199045):
    m = MagicMock()
    m.id = market_id
    m.name = "MLB: 2026 American League Champion"
    m.outcomes = outcomes
    m.resolution_date = resolution_date
    m.settled_at = settled_at
    m.status = status
    # Set explicitly (#7921): a bare MagicMock attribute is truthy.
    m.mutually_exclusive = mutually_exclusive
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


def _snapshot(outcome_id, captured_at, prob):
    s = MagicMock()
    s.outcome_id = outcome_id
    s.captured_at = captured_at
    s.probability = prob
    s.bookmaker = "test"
    return s


def _stamp(point):
    return datetime.fromisoformat(point["timestamp"])


def _settlement_points(result):
    return [
        (o["name"], p)
        for o in result["outcomes"]
        for p in o["history"]
        if p.get("bookmaker") == "settlement"
    ]


async def _serve(market, snaps):
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
        market_id=market.id, hours=8760, top_n=8, outcome_id=None, db=db
    )


def _board_snapshots(*, siblings_last=B_LAST):
    """The 199045 shape in miniature: A's series ends at `A_LAST`, the
    siblings' runs on to `siblings_last`. Shared instants keep the route's
    per-instant de-vig sane."""
    snaps = []
    for ts in [A_LAST - timedelta(days=d) for d in range(6, 0, -1)] + [A_LAST]:
        snaps.append(_snapshot(1, ts, 0.004))
        snaps.append(_snapshot(2, ts, 0.616))
        snaps.append(_snapshot(3, ts, 0.380))
    for ts in [siblings_last - timedelta(days=d) for d in range(10, 0, -1)] + [siblings_last]:
        snaps.append(_snapshot(2, ts, 0.620))
        snaps.append(_snapshot(3, ts, 0.380))
    return snaps


def _open_board(**market_kwargs):
    a = _outcome(1, "Detroit Tigers", resolution_source="leaderboard", prob=0.004)
    b = _outcome(2, "Cleveland Guardians", resolution_source=None, prob=0.620)
    c = _outcome(3, "Tampa Bay Rays", resolution_source=None, prob=0.380)
    kwargs = {"resolution_date": DEADLINE}
    kwargs.update(market_kwargs)
    return _market([a, b, c], **kwargs)


def _settled_board(**market_kwargs):
    """Winner with real points + graded loser + ungraded third line. The third
    line shares the winner's instants so the winner's de-vigged value stays
    under 0.999 and its arm actually fires."""
    winner = _outcome(2, "Cleveland Guardians", is_winner=True,
                      resolution_source="leaderboard", prob=0.55)
    loser = _outcome(1, "Detroit Tigers", resolution_source="leaderboard", prob=0.50)
    ungraded = _outcome(3, "Tampa Bay Rays", resolution_source=None, prob=0.45)
    return _market([winner, loser, ungraded], **market_kwargs)


def _settled_board_snapshots(last_real):
    """The winner (and the ungraded line) end ON `last_real`; the loser ends
    four hours earlier. On the last-observation rung the winner is nudged to
    `last_real + 1s` and the loser is not."""
    snaps = []
    for i in range(30):
        ts = last_real - timedelta(hours=i * 2)
        snaps.append(_snapshot(2, ts, 0.55))
        snaps.append(_snapshot(3, ts, 0.45))
    for i in range(30):
        snaps.append(_snapshot(1, last_real - timedelta(hours=4 + i * 2), 0.50))
    return snaps


class TestTheRouteServesTheWitness:
    """The four bases and both arms, through the real `/history` route."""

    @pytest.mark.asyncio
    async def test_a_past_schedule_is_served_as_resolution_date_on_both_arms(self):
        rd = NOW - timedelta(days=10)
        market = _settled_board(resolution_date=rd, status="resolved")
        result = await _serve(market, _settled_board_snapshots(rd - timedelta(days=2)))
        by_name = {o["name"]: o for o in result["outcomes"]}
        w_end = by_name["Cleveland Guardians"]["history"][-1]
        l_end = by_name["Detroit Tigers"]["history"][-1]
        assert (w_end["bookmaker"], l_end["bookmaker"]) == ("settlement", "settlement")
        assert (w_end["probability"], l_end["probability"]) == (1.0, 0.0)
        assert w_end["settlement_basis"] == BASIS_RESOLUTION_DATE
        assert l_end["settlement_basis"] == BASIS_RESOLUTION_DATE
        # B4: the schedule arm's placement, as it was.
        assert _stamp(w_end) == _stamp(l_end) == rd

    @pytest.mark.asyncio
    async def test_the_199045_shape_serves_last_observation_on_the_graded_loser(self):
        result = await _serve(_open_board(), _board_snapshots())
        by_name = {o["name"]: o for o in result["outcomes"]}
        a_end = by_name["Detroit Tigers"]["history"][-1]
        assert a_end["bookmaker"] == "settlement"
        assert a_end["probability"] == 0.0
        assert a_end["settlement_basis"] == BASIS_LAST_OBSERVATION
        # The open siblings carry no settlement point and no basis.
        for name in ("Cleveland Guardians", "Tampa Bay Rays"):
            assert not any(
                p.get("bookmaker") == "settlement" or "settlement_basis" in p
                for p in by_name[name]["history"]
            )

    @pytest.mark.asyncio
    async def test_on_a_last_observation_board_the_nudged_winner_and_the_loser_both_say_so(self):
        """Loser: the ladder's rung, not nudged. Winner: nudged past its own
        last point, so B1 makes it `last_observation` whatever the ladder said
        — here the two agree, and the placement is exactly 7927's."""
        last_real = NOW - timedelta(hours=12)
        market = _settled_board(resolution_date=None, settled_at=None)
        result = await _serve(market, _settled_board_snapshots(last_real))
        by_name = {o["name"]: o for o in result["outcomes"]}
        w_end = by_name["Cleveland Guardians"]["history"][-1]
        l_end = by_name["Detroit Tigers"]["history"][-1]
        assert w_end["settlement_basis"] == BASIS_LAST_OBSERVATION
        assert l_end["settlement_basis"] == BASIS_LAST_OBSERVATION
        assert _stamp(l_end) == last_real
        assert _stamp(w_end) == last_real + SECOND

    @pytest.mark.asyncio
    async def test_an_empty_chart_serves_settled_at_on_the_synthesized_winner(self):
        settled_at = NOW - timedelta(days=3)
        winner = _outcome(2, "Cleveland Guardians", is_winner=True,
                          resolution_source="leaderboard", prob=0.62)
        market = _market([winner], resolution_date=DEADLINE, settled_at=settled_at,
                         status="resolved")
        result = await _serve(market, [])
        points = _settlement_points(result)
        assert len(points) == 1
        name, point = points[0]
        assert name == "Cleveland Guardians"
        assert point["probability"] == 1.0
        assert point["settlement_basis"] == BASIS_SETTLED_AT
        assert _stamp(point) == settled_at  # #6331 one-point winner, unchanged

    @pytest.mark.asyncio
    async def test_no_witness_at_all_serves_clock_on_the_synthesized_winner(self):
        winner = _outcome(2, "Cleveland Guardians", is_winner=True,
                          resolution_source="leaderboard", prob=0.62)
        market = _market([winner], resolution_date=None, settled_at=None, status="resolved")
        result = await _serve(market, [])
        points = _settlement_points(result)
        assert len(points) == 1
        assert points[0][1]["settlement_basis"] == BASIS_CLOCK

    @pytest.mark.asyncio
    async def test_every_served_settlement_point_carries_one_of_the_four_constants(self):
        """B2 + "production passes the pair": no served settlement point is
        missing a basis, and none carries a fifth value."""
        shapes = [
            (_open_board(), _board_snapshots()),
            (_settled_board(resolution_date=NOW - timedelta(days=10), status="resolved"),
             _settled_board_snapshots(NOW - timedelta(days=12))),
            (_settled_board(resolution_date=None, settled_at=None),
             _settled_board_snapshots(NOW - timedelta(hours=12))),
        ]
        seen = 0
        for market, snaps in shapes:
            for _name, point in _settlement_points(await _serve(market, snaps)):
                seen += 1
                assert point.get("settlement_basis") in FOUR_BASES, point
        assert seen == 5  # 1 + 2 + 2 — the shapes really produced settlement points

    @pytest.mark.asyncio
    async def test_g_c_sibling_trades_between_two_reads_leave_the_basis_unchanged(self):
        """G-c. Two reads of the 199045 shape with the siblings trading in
        between. The BASIS is the same on both reads. This deliberately says
        nothing about the marker's timestamp: on this shape it still sits at
        the board's last trade in Step 1, and moving it is Step 3's job."""
        first = await _serve(_open_board(), _board_snapshots())
        second = await _serve(_open_board(), _board_snapshots(siblings_last=B_LATER))
        a_first = {o["name"]: o for o in first["outcomes"]}["Detroit Tigers"]["history"][-1]
        a_second = {o["name"]: o for o in second["outcomes"]}["Detroit Tigers"]["history"][-1]
        assert a_first["bookmaker"] == a_second["bookmaker"] == "settlement"
        assert a_first["settlement_basis"] == a_second["settlement_basis"] == BASIS_LAST_OBSERVATION
        # Non-vacuity: the board really did move between the reads.
        b_first = {o["name"]: o for o in first["outcomes"]}["Cleveland Guardians"]["history"][-1]
        b_second = {o["name"]: o for o in second["outcomes"]}["Cleveland Guardians"]["history"][-1]
        assert _stamp(b_first) == B_LAST
        assert _stamp(b_second) == B_LATER

    @pytest.mark.asyncio
    async def test_the_route_reads_the_pair_exactly_once_before_either_arm(self, monkeypatch):
        """Single read + non-self-reference, now on the pair: the route reads
        `_settled_chart_stamp_basis` once and hands both arms the result, so
        neither arm re-reads the ladder off a chart the other has appended to."""
        calls = []
        real = futures_routes._settled_chart_stamp_basis

        def counting(market, outcome_history):
            calls.append(sum(
                1 for e in outcome_history.values()
                for p in e.get("history") or []
                if p.get("bookmaker") == "settlement"
            ))
            return real(market, outcome_history)

        monkeypatch.setattr(futures_routes, "_settled_chart_stamp_basis", counting)
        market = _settled_board(resolution_date=None, settled_at=None)
        result = await _serve(market, _settled_board_snapshots(NOW - timedelta(hours=12)))
        assert len(_settlement_points(result)) == 2  # both arms fired
        assert calls == [0]  # once, and before any settlement point existed


class TestTheArmsHelperLevel:
    """The binds on the arms themselves, with the stamp as an argument."""

    def _loser_board(self, own_last):
        loser = _outcome(1, "Tommy Fleetwood", resolution_source="leaderboard")
        market = _market([loser], mutually_exclusive=False)
        oh = {1: _series(1, "Tommy Fleetwood", [(own_last - timedelta(days=1), 0.84), (own_last, 0.84)])}
        return market, oh

    def _winner_board(self, own_last):
        winner = _outcome(1, "Ludvig Aberg", is_winner=True, resolution_source="leaderboard")
        market = _market([winner], mutually_exclusive=True)
        oh = {1: _series(1, "Ludvig Aberg", [(own_last - timedelta(days=1), 0.6), (own_last, 0.6)])}
        return market, oh

    # --- G-a / B3: a bare settle_ts names no witness ---------------------------

    def test_g_a_bare_settle_ts_not_nudged_loser_point_has_exactly_the_old_keys(self):
        market, oh = self._loser_board(EARLIER)
        _apply_settled_loser_freeze(market, oh, SETTLE)
        end = oh[1]["history"][-1]
        assert end["bookmaker"] == "settlement"
        assert set(end) == BARE_KEYS
        assert _stamp(end) == SETTLE

    def test_g_a_bare_settle_ts_not_nudged_winner_point_has_exactly_the_old_keys(self):
        market, oh = self._winner_board(EARLIER)
        _apply_settled_winner_freeze(market, oh, {1: "Ludvig Aberg"}, settle_ts=SETTLE)
        end = oh[1]["history"][-1]
        assert end["bookmaker"] == "settlement"
        assert set(end) == BARE_KEYS

    def test_g_a_bare_settle_ts_synthesized_winner_has_exactly_the_old_keys(self):
        winner = _outcome(1, "Ludvig Aberg", is_winner=True, resolution_source="leaderboard")
        market = _market([winner], mutually_exclusive=True)
        oh = {}
        _apply_settled_winner_freeze(market, oh, {1: "Ludvig Aberg"}, settle_ts=SETTLE)
        assert [set(p) for p in oh[1]["history"]] == [BARE_KEYS]

    def test_a_nudged_point_under_a_bare_settle_ts_serves_last_observation(self):
        """The nudge is itself the witness (B1), so even a caller that named no
        basis gets `last_observation` on a point the nudge placed."""
        market, oh = self._loser_board(LATER)
        _apply_settled_loser_freeze(market, oh, SETTLE)
        assert oh[1]["history"][-1]["settlement_basis"] == BASIS_LAST_OBSERVATION
        market, oh = self._winner_board(LATER)
        _apply_settled_winner_freeze(market, oh, {1: "Ludvig Aberg"}, settle_ts=SETTLE)
        assert oh[1]["history"][-1]["settlement_basis"] == BASIS_LAST_OBSERVATION

    # --- G-b / B1: the nudge outranks the ladder's word -------------------------

    def test_g_b_a_past_schedule_point_moved_by_the_nudge_serves_last_observation_loser(self):
        market, oh = self._loser_board(LATER)
        _apply_settled_loser_freeze(market, oh, SETTLE, settle_basis=BASIS_RESOLUTION_DATE)
        end = oh[1]["history"][-1]
        assert end["settlement_basis"] == BASIS_LAST_OBSERVATION
        assert end["settlement_basis"] != BASIS_RESOLUTION_DATE
        assert _stamp(end) == LATER + SECOND  # B4: the nudge's placement, as it was

    def test_g_b_a_past_schedule_point_moved_by_the_nudge_serves_last_observation_winner(self):
        market, oh = self._winner_board(LATER)
        _apply_settled_winner_freeze(
            market, oh, {1: "Ludvig Aberg"},
            settle_ts=SETTLE, settle_basis=BASIS_RESOLUTION_DATE,
        )
        end = oh[1]["history"][-1]
        assert end["settlement_basis"] == BASIS_LAST_OBSERVATION
        assert _stamp(end) == LATER + SECOND

    def test_a_point_that_is_not_nudged_serves_the_basis_it_was_handed(self):
        for basis in sorted(FOUR_BASES):
            market, oh = self._loser_board(EARLIER)
            _apply_settled_loser_freeze(market, oh, SETTLE, settle_basis=basis)
            assert oh[1]["history"][-1]["settlement_basis"] == basis
            assert _stamp(oh[1]["history"][-1]) == SETTLE
            market, oh = self._winner_board(EARLIER)
            _apply_settled_winner_freeze(
                market, oh, {1: "Ludvig Aberg"}, settle_ts=SETTLE, settle_basis=basis
            )
            assert oh[1]["history"][-1]["settlement_basis"] == basis

    def test_the_synthesized_winner_is_never_nudged_and_serves_the_ladder_basis(self):
        winner = _outcome(1, "Ludvig Aberg", is_winner=True, resolution_source="leaderboard")
        market = _market([winner], mutually_exclusive=True)
        oh = {}
        _apply_settled_winner_freeze(
            market, oh, {1: "Ludvig Aberg"}, settle_ts=SETTLE, settle_basis=BASIS_CLOCK
        )
        assert len(oh[1]["history"]) == 1
        assert oh[1]["history"][0]["settlement_basis"] == BASIS_CLOCK
        assert _stamp(oh[1]["history"][0]) == SETTLE

    # --- B3: with no settle_ts the arm reads the pair; a lone basis is ignored --

    def test_with_no_settle_ts_each_arm_reads_the_pair_and_ignores_a_lone_basis(self):
        past_rd = datetime.now(timezone.utc) - timedelta(days=30)
        loser = _outcome(1, "Tommy Fleetwood", resolution_source="leaderboard")
        market = _market([loser], mutually_exclusive=False, resolution_date=past_rd)
        oh = {1: _series(1, "Tommy Fleetwood", [(past_rd - timedelta(days=2), 0.84)])}
        _apply_settled_loser_freeze(market, oh, None, settle_basis=BASIS_CLOCK)
        assert oh[1]["history"][-1]["settlement_basis"] == BASIS_RESOLUTION_DATE

        winner = _outcome(1, "Ludvig Aberg", is_winner=True, resolution_source="leaderboard")
        market = _market([winner], mutually_exclusive=True, resolution_date=past_rd)
        oh = {1: _series(1, "Ludvig Aberg", [(past_rd - timedelta(days=2), 0.6)])}
        _apply_settled_winner_freeze(market, oh, {1: "Ludvig Aberg"}, settle_basis=BASIS_CLOCK)
        assert oh[1]["history"][-1]["settlement_basis"] == BASIS_RESOLUTION_DATE

    def test_with_no_settle_ts_and_no_basis_each_arm_still_serves_one(self):
        past_rd = datetime.now(timezone.utc) - timedelta(days=30)
        loser = _outcome(1, "Tommy Fleetwood", resolution_source="leaderboard")
        market = _market([loser], mutually_exclusive=False, resolution_date=past_rd)
        oh = {1: _series(1, "Tommy Fleetwood", [(past_rd - timedelta(days=2), 0.84)])}
        _apply_settled_loser_freeze(market, oh, None)
        assert oh[1]["history"][-1]["settlement_basis"] == BASIS_RESOLUTION_DATE

        winner = _outcome(1, "Ludvig Aberg", is_winner=True, resolution_source="leaderboard")
        market = _market([winner], mutually_exclusive=True, resolution_date=past_rd)
        oh = {}
        _apply_settled_winner_freeze(market, oh, {1: "Ludvig Aberg"})
        assert oh[1]["history"][0]["settlement_basis"] == BASIS_RESOLUTION_DATE

    # --- interface compatibility --------------------------------------------------

    def test_the_stamp_keeps_its_datetime_return_and_matches_the_pair(self):
        rd = datetime.now(timezone.utc) - timedelta(days=30)
        market = _market([], resolution_date=rd)
        oh = {1: _series(1, "x", [(rd - timedelta(days=2), 0.5)])}
        stamp = _settled_chart_stamp(market, oh)
        assert isinstance(stamp, datetime)
        assert futures_routes._settled_chart_stamp_basis(market, oh) == (stamp, BASIS_RESOLUTION_DATE)

    def test_settle_basis_is_keyword_only_on_every_freeze_helper(self):
        for fn in (_apply_settled_winner_freeze, _apply_settled_loser_freeze, _freeze_one_winner_line):
            param = inspect.signature(fn).parameters["settle_basis"]
            assert param.kind is inspect.Parameter.KEYWORD_ONLY, fn.__name__
            assert param.default is None, fn.__name__

    def test_the_positional_winner_line_call_still_works(self):
        """`test_repair_11315` calls `_freeze_one_winner_line` positionally."""
        winner = _outcome(1, "Ludvig Aberg", is_winner=True)
        oh = {1: _series(1, "Ludvig Aberg", [(EARLIER, 0.6)])}
        _freeze_one_winner_line(winner, oh, {1: "Ludvig Aberg"}, SETTLE, allow_synthesis=True)
        assert set(oh[1]["history"][-1]) == BARE_KEYS
