"""#6546: a third of the marquee chart's payload is provenance no client reads.

native/190 walked the phone onto `bainluck://events/14638896` (Broncos at Chiefs,
FINAL) and found the win-probability chart a blank half-screen with a spinner for
~30 s. `GET /api/events/14638896/history` serves **2,691,217 B**, measured twice
from production on 2026-09-16.

The issue named `bookmaker_history` (612 KB) and `aggregate_line` (326 KB) as the
bulk. Neither is the largest key. Measured on the real payload:

    win_prob_history   1,803,666 B   67.0%      <- not in the issue's table
    bookmaker_history    611,732 B   22.7%
    aggregate_line       326,121 B   12.1%

and 909,121 B of that 1.8 MB — **33.8% of the whole response** — is the
`game_state` dict repeated on every point of every series:

    {"market_id": 25926038, "poll_type": "history_backfill",
     "market_name": "Denver vs Kansas City", "outcome_name": "Kansas City",
     "backfill_source": "kalshi_candlesticks", "yes_probability": 0.495}

324 B a point, 5,414 points, near-constant within a series. Across the two client
trees, **961** of the 32,580 `game_state` values on that specimen are readable by
any client and **31,619** are not.

So this projects each point's `game_state` down to the keys a client actually
reads, taken by grepping every access in both trees rather than by reasoning
about what the column is for (`_SERVED_GAME_STATE_KEYS` carries the census).
Nothing a reader sees moves: the same lines, the same markers, the same scores.

THE ORDER IS THE WHOLE RISK, and `test_a_settled_markets_series_is_still_withheld`
is the arm that holds it. `settled_chart.market_ids_in_series` reads
`game_state.market_id` off this same dict to decide which series may be drawn on
an event that has not kicked off (#1828/#5890). Project before that read and
`market_ids_in_series` returns an empty set, `withhold_settled_market_series`
short-circuits, and a settled market's price is drawn on an unstarted game — the
exact truth defect that pass exists to prevent, and one no size assertion would
notice. Hence the call sits after every server-side reader, and that arm fails if
it is ever moved up.

The unit arms take one key at a time on purpose: an allowlist asserted only in
bulk survives losing a member, and `inning`/`inning_half` (the MLB period arm)
appear in no snapshot of the last three days, so they are exactly the members a
bulk assertion would let fall out.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.events import (
    _SERVED_GAME_STATE_KEYS,
    _project_served_game_state,
    get_event_odds_history,
)
from app.utils.settled_chart import market_ids_in_series

from tests.test_history_window_stale_open_event import (  # noqa: E402
    _DispatchingSession,
    _Result,
)

UTC = timezone.utc

#: The production specimen, and the market behind its Kalshi series.
_SPECIMEN_ID = 14638896
_MARKET_ID = 25926038

#: Verbatim from the specimen's first Kalshi point, 2026-09-16.
_PRODUCTION_GAME_STATE = {
    "market_id": _MARKET_ID,
    "poll_type": "history_backfill",
    "market_name": "Denver vs Kansas City",
    "outcome_name": "Kansas City",
    "backfill_source": "kalshi_candlesticks",
    "yes_probability": 0.495,
}

#: Every other key the column holds, from a fleet-wide census of
#: `jsonb_object_keys(game_state)` over the last 3 days (2026-09-16):
#: 379,907 `market_id` … down to 2,127 `seconds_left`. None is read by a client.
_PROVENANCE_KEYS = [
    "market_id",
    "market_name",
    "outcome_name",
    "poll_type",
    "yes_probability",
    "yes_bid",
    "yes_ask",
    "backfill_source",
    "backfill",
    "backfilled",
    "pregame_spread",
    "mlb_game_pk",
    "seconds_left",
]

#: What each client reads. `time_source` is web's wall-clock stat-model
#: suppression; the rest are the score/period supplement and the MLB arm.
_READ_KEYS = {
    "period": "2nd Quarter",
    "clock": "07:41",
    "inning": 3,
    "inning_half": "top",
    "home_score": 21,
    "away_score": 10,
    "time_source": "espn",
}


def _point(game_state, ts="2026-09-15T00:17:12+00:00"):
    return {
        "timestamp": ts,
        "home_probability": 0.495,
        "away_probability": 0.505,
        "draw_probability": None,
        "game_state": game_state,
    }


# ---------------------------------------------------------------------------
# The projection itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key,value", sorted(_READ_KEYS.items()))
def test_every_key_a_client_reads_survives_on_its_own(key, value):
    """One arm per key: a bulk assertion survives losing a single member."""
    series = {"espn": [_point({key: value, "market_name": "Denver vs KC"})]}

    _project_served_game_state(series)

    assert series["espn"][0]["game_state"] == {key: value}


@pytest.mark.parametrize("key", _PROVENANCE_KEYS)
def test_every_provenance_key_is_dropped(key):
    series = {"kalshi": [_point({key: 1, "period": "1st Quarter"})]}

    _project_served_game_state(series)

    assert series["kalshi"][0]["game_state"] == {"period": "1st Quarter"}


def test_the_production_point_keeps_nothing_and_serves_none():
    """The specimen's own shape: all six keys are provenance, so the dict goes.

    `None` and not `{}` — a NULL `game_state` column is already served as `None`
    by this route, so an emptied projection meets the client in a shape it has
    always handled (`WinProbGameState?` on native, `if (!gs) continue` on web).
    """
    series = {"kalshi": [_point(dict(_PRODUCTION_GAME_STATE))]}

    _project_served_game_state(series)

    assert series["kalshi"][0]["game_state"] is None


def test_a_point_keeps_its_read_keys_and_loses_the_rest_together():
    series = {"kalshi": [_point({**_PRODUCTION_GAME_STATE, **_READ_KEYS})]}

    _project_served_game_state(series)

    assert series["kalshi"][0]["game_state"] == _READ_KEYS


def test_the_fixture_really_carries_what_the_projection_removes():
    """Not vacuous: the input must fail the assertion its output passes."""
    before = _point(dict(_PRODUCTION_GAME_STATE))

    assert set(before["game_state"]) & set(_PROVENANCE_KEYS), (
        "the fixture carries no provenance, so every arm above proves nothing"
    )
    assert not set(before["game_state"]) & _SERVED_GAME_STATE_KEYS


def test_a_null_game_state_is_still_null():
    series = {"kalshi": [_point(None)]}

    _project_served_game_state(series)

    assert series["kalshi"][0]["game_state"] is None


@pytest.mark.parametrize("weird", [[], ["market_id"], "kalshi", 7])
def test_a_non_dict_game_state_is_left_exactly_as_it_is(weird):
    """JSONB may hold a list or a string. No client parses one; neither do we."""
    series = {"kalshi": [_point(weird)]}

    _project_served_game_state(series)

    assert series["kalshi"][0]["game_state"] == weird


def test_the_stored_dict_is_never_mutated():
    """`game_state` comes straight off the ORM row (gotcha #4).

    The projection must build a new dict and assign it to the point. An
    implementation that popped keys in place would edit the session's own JSONB.
    """
    stored = dict(_PRODUCTION_GAME_STATE)
    stored["period"] = "1st Quarter"
    series = {"kalshi": [_point(stored)]}

    _project_served_game_state(series)

    assert stored == {**_PRODUCTION_GAME_STATE, "period": "1st Quarter"}, (
        "the projection edited the dict the ORM row is holding"
    )
    assert series["kalshi"][0]["game_state"] is not stored


def test_empty_and_missing_series_do_not_throw():
    """A chart with no points must not fail the page (this runs on every event)."""
    _project_served_game_state({})
    _project_served_game_state(None)
    _project_served_game_state({"kalshi": []})
    _project_served_game_state({"kalshi": None})


def test_the_projection_is_measurably_smaller_on_the_specimens_shape():
    """The size claim, with the unprojected shape as its own control."""
    import json

    series = {
        "kalshi": [
            _point(dict(_PRODUCTION_GAME_STATE)) for _ in range(3009)
        ]
    }
    before = len(json.dumps(series))

    _project_served_game_state(series)
    after = len(json.dumps(series))

    assert after < before * 0.45, (
        f"expected the provenance to dominate; {before} -> {after}"
    )


# ---------------------------------------------------------------------------
# Through the real route — where the ORDER is proved
# ---------------------------------------------------------------------------


class _MarketResult(_Result):
    """`settled_market_ids` reads `.scalars().unique().all()`."""

    def unique(self):
        return self


class _SettlementSession(_DispatchingSession):
    """The harness session, plus the `futures_markets` read the withhold does.

    The route reads that table three times — the withhold's `id IN (...)`, the
    event's own markets, and the backfill planner's `min(created_at)`. Only the
    first is answered with markets, because feeding a market row to the other
    two would have this fixture prove something about a different rail.
    """

    def __init__(self, event, win_prob_rows, markets):
        super().__init__(event, win_prob_rows)
        self.markets = markets
        self.market_reads = 0

    async def execute(self, statement, *a, **kw):
        sql = str(statement)
        if "futures_markets.id IN" in sql:
            self.market_reads += 1
            return _MarketResult(self.markets)
        if "futures_markets" in sql:
            return _MarketResult([])
        return await super().execute(statement, *a, **kw)


def _market(settled):
    return SimpleNamespace(
        id=_MARKET_ID,
        status="settled" if settled else "open",
        outcomes=[],
    )


def _unstarted_event(now):
    return SimpleNamespace(
        id=_SPECIMEN_ID,
        status="scheduled",
        commence_time=now + timedelta(hours=6),
        completed_at=None,
        home_team_name="Kansas City Chiefs",
        away_team_name="Denver Broncos",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="americanfootball_nfl"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.495}},
    )


def _kalshi_rows(now, count=40):
    """A Kalshi series drawn from `_MARKET_ID`, inside the 48-hour window."""
    return [
        SimpleNamespace(
            event_id=_SPECIMEN_ID,
            captured_at=now - timedelta(minutes=30 * (count - i)),
            source="kalshi",
            home_win_probability=0.50 + i * 0.001,
            away_win_probability=0.50 - i * 0.001,
            draw_probability=None,
            game_state=dict(_PRODUCTION_GAME_STATE),
        )
        for i in range(count)
    ]


async def _serve(event, rows, markets):
    session = _SettlementSession(event, rows, markets)
    payload = await get_event_odds_history(
        event_id=event.id, hours=48, response=MagicMock(headers={}), db=session
    )
    return payload, session


async def test_the_served_payload_carries_no_provenance():
    now = datetime.now(UTC)
    payload, _ = await _serve(
        _unstarted_event(now), _kalshi_rows(now), [_market(settled=False)]
    )

    served = payload["win_prob_history"]["kalshi"]
    assert served, "the fixture served no points, so this asserts nothing"
    for point in served:
        assert point["game_state"] is None, point["game_state"]


async def test_a_settled_markets_series_is_still_withheld():
    """THE ORDERING ARM. Move the projection earlier and this fails.

    `market_ids_in_series` reads `game_state.market_id`. Projected first, it
    finds nothing, the withhold short-circuits, and this settled market's price
    is drawn on a game that has not kicked off.
    """
    now = datetime.now(UTC)
    payload, session = await _serve(
        _unstarted_event(now), _kalshi_rows(now), [_market(settled=True)]
    )

    assert session.market_reads == 1, (
        "the withhold never asked about the market — the projection ran first"
    )
    assert "kalshi" not in payload["win_prob_history"], (
        "a settled market's series was drawn on an unstarted game"
    )


async def test_the_control_an_unsettled_market_is_still_drawn():
    """Without this, the arm above would pass on a route that drew nothing."""
    now = datetime.now(UTC)
    payload, session = await _serve(
        _unstarted_event(now), _kalshi_rows(now), [_market(settled=False)]
    )

    assert session.market_reads == 1
    assert len(payload["win_prob_history"]["kalshi"]) == 40


async def test_the_served_payload_can_no_longer_answer_the_withhold_question():
    """Why the order is load-bearing, stated as a fact about the output.

    The response no longer carries the market ids the server read to build it.
    That is the point — no client reads them — and it is also the reason this
    projection can only ever be the last thing that happens.
    """
    now = datetime.now(UTC)
    rows = _kalshi_rows(now)
    payload, _ = await _serve(
        _unstarted_event(now), rows, [_market(settled=False)]
    )

    assert market_ids_in_series(payload["win_prob_history"]) == set()
    assert market_ids_in_series(
        {"kalshi": [_point(dict(_PRODUCTION_GAME_STATE))]}
    ) == {_MARKET_ID}


async def test_a_period_bearing_point_keeps_its_period_through_the_route():
    """The read keys survive the whole route, not just the helper.

    `period` drives the chart's period markers and the score supplement, so a
    projection that dropped it would empty markers on every live game.

    On a LIVE event on purpose: #1828's cross-game filter drops a point bearing
    in-game state from outside the event's own window, so a scheduled fixture
    cannot carry a period at all and this arm would pass for the wrong reason.
    """
    now = datetime.now(UTC)
    event = _unstarted_event(now)
    event.commence_time = now - timedelta(hours=1)
    event.status = "live"
    rows = _kalshi_rows(now)
    rows[-1].game_state = {**_PRODUCTION_GAME_STATE, "period": "2nd Quarter",
                           "home_score": 21, "away_score": 10}

    payload, _ = await _serve(event, rows, [_market(settled=False)])

    assert payload["win_prob_history"]["kalshi"][-1]["game_state"] == {
        "period": "2nd Quarter",
        "home_score": 21,
        "away_score": 10,
    }
