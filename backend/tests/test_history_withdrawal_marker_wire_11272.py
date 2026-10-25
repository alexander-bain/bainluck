"""#11272: a genuine source withdrawal reaches the history wire; nothing else does.

The Polymarket writer records a removed source as a NULL win-prob row whose
`game_state` is `{"live_source_withdrawal": true}`. The history route reads that
row and decides, from the stored row alone, whether the point is a withdrawal
(`_explicit_source_withdrawal`) — the aggregate line already ends the source
there. But `_project_served_game_state` (#6546) runs last and keeps only the
census keys, so the marker was stripped and the final response served the
withdrawal as `game_state: null`, indistinguishable from an ordinary NULL
reading. The web chart's strict check (a null point whose marker is boolean
`true`) could therefore never fire against the real response.

What these arms hold, all on the FINAL projected response of the real route:

  * a stored NULL row marked boolean `true` serves `{"live_source_withdrawal": true}`
    at its own stored timestamp, with no price;
  * an ordinary NULL, a string "true", a `false`, an empty dict, and a marker on a
    PRICED row all serve exactly what they served before (`null`);
  * the live-edge extension, which copies the last row's `game_state` dict onto a
    synthetic point at `now`, does NOT carry the marker — a key passthrough would
    serve a second withdrawal at an instant nobody observed;
  * the internal `_explicit_source_withdrawal` flag never reaches the wire;
  * provenance stays stripped on the marked point.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.events import _SERVED_GAME_STATE_KEYS, _project_served_game_state

from tests.test_event_history_game_state_projection_6546 import (
    _MARKET_ID,
    _PRODUCTION_GAME_STATE,
    _kalshi_rows,
    _market,
    _serve,
    _unstarted_event,
)

UTC = timezone.utc
MARKER = "live_source_withdrawal"


def _point(home, game_state, *, internal=None, ts="2026-10-19T11:41:55+00:00"):
    point = {
        "timestamp": ts,
        "home_probability": home,
        "away_probability": None if home is None else 1 - home,
        "draw_probability": None,
        "game_state": game_state,
    }
    if internal is not None:
        point["_explicit_source_withdrawal"] = internal
    return point


# ---------------------------------------------------------------------------
# The projection helper
# ---------------------------------------------------------------------------


def test_the_marker_is_not_a_census_key():
    """It must never pass through by key — only by the route's classification."""
    assert MARKER not in _SERVED_GAME_STATE_KEYS


def test_a_classified_withdrawal_serves_the_marker():
    point = _point(None, {MARKER: True}, internal=True)
    _project_served_game_state({"polymarket": [point]})
    assert point["game_state"] == {MARKER: True}
    assert point["game_state"][MARKER] is True
    assert "_explicit_source_withdrawal" not in point


def test_a_classified_withdrawal_keeps_read_keys_and_drops_provenance():
    state = {MARKER: True, **_PRODUCTION_GAME_STATE, "period": "Q3"}
    point = _point(None, state, internal=True)
    _project_served_game_state({"polymarket": [point]})
    assert point["game_state"] == {MARKER: True, "period": "Q3"}


def test_a_copied_marker_without_the_classification_is_not_served():
    """The live-edge extension shares the row's dict but not the flag."""
    point = _point(None, {MARKER: True})
    _project_served_game_state({"polymarket": [point]})
    assert point["game_state"] is None


@pytest.mark.parametrize(
    "state",
    [None, {}, {MARKER: "true"}, {MARKER: False}, {MARKER: 1}],
    ids=["null", "empty", "string-true", "false", "int-1"],
)
def test_an_unclassified_null_serves_what_it_always_did(state):
    point = _point(None, None if state is None else dict(state), internal=False)
    _project_served_game_state({"polymarket": [point]})
    assert point["game_state"] is None
    assert "_explicit_source_withdrawal" not in point


def test_a_priced_point_never_serves_the_marker_even_if_flagged():
    point = _point(0.78, {MARKER: True}, internal=True)
    _project_served_game_state({"polymarket": [point]})
    assert point["game_state"] is None


@pytest.mark.parametrize("state", [None, "x", [1], {MARKER: True}])
def test_the_internal_flag_is_removed_from_every_point(state):
    point = _point(None, state, internal=True)
    _project_served_game_state({"polymarket": [point]})
    assert "_explicit_source_withdrawal" not in point


def test_the_stored_dict_is_never_mutated():
    stored = {MARKER: True, **_PRODUCTION_GAME_STATE}
    snapshot = dict(stored)
    point = _point(None, stored, internal=True)
    _project_served_game_state({"polymarket": [point]})
    assert stored == snapshot
    assert point["game_state"] is not stored


# ---------------------------------------------------------------------------
# Through the real route — the FINAL projected response
# ---------------------------------------------------------------------------


def _live_event(now):
    event = _unstarted_event(now)
    event.commence_time = now - timedelta(hours=1)
    event.status = "live"
    return event


def _rows_ending_in(now, *, home, game_state, ago=timedelta(minutes=5)):
    """A priced Kalshi series whose last stored row is the specimen row."""
    rows = _kalshi_rows(now, count=10)
    for row in rows:
        row.captured_at = now - ago - timedelta(minutes=10 * (len(rows) - rows.index(row)))
    rows.append(
        SimpleNamespace(
            event_id=rows[0].event_id,
            captured_at=now - ago,
            source="kalshi",
            home_win_probability=home,
            away_win_probability=None if home is None else 1 - home,
            draw_probability=None,
            game_state=game_state,
        )
    )
    return rows


async def _served_series(now, *, home, game_state):
    rows = _rows_ending_in(now, home=home, game_state=game_state)
    payload, _ = await _serve(_live_event(now), rows, [_market(settled=False)])
    return payload["win_prob_history"]["kalshi"], rows[-1]


def _no_internal_key(points):
    leaked = [p for p in points if "_explicit_source_withdrawal" in p]
    assert not leaked, leaked


async def test_route_a_marked_withdrawal_reaches_the_final_response():
    now = datetime.now(UTC)
    served, stored = await _served_series(
        now, home=None, game_state={MARKER: True, "market_id": _MARKET_ID}
    )
    marked = [p for p in served if (p.get("game_state") or {}).get(MARKER) is True]
    assert len(marked) == 1, served[-3:]
    point = marked[0]
    assert point["home_probability"] is None
    assert point["game_state"] == {MARKER: True}
    assert point["timestamp"] == stored.captured_at.isoformat()
    assert not point.get("live_edge")
    _no_internal_key(served)


async def test_route_the_live_edge_copy_does_not_carry_the_marker():
    """The decisive counterexample against a key passthrough.

    The withdrawal row is 5 minutes old on a live game, so the live-edge
    extension appends a synthetic point at `now` built from that row, sharing
    its `game_state` dict. Without a live-edge point this arm proves nothing.
    """
    now = datetime.now(UTC)
    served, _ = await _served_series(now, home=None, game_state={MARKER: True})
    edge = [p for p in served if p.get("live_edge")]
    assert edge, "no live-edge point was appended, so this arm is vacuous"
    for p in edge:
        assert p["game_state"] is None, p


@pytest.mark.parametrize(
    "game_state",
    [None, {}, {MARKER: "true"}, {MARKER: False}, {"market_id": _MARKET_ID}],
    ids=["null", "empty", "string-true", "false", "provenance-only"],
)
async def test_route_an_ordinary_null_serves_null_as_before(game_state):
    now = datetime.now(UTC)
    served, stored = await _served_series(now, home=None, game_state=game_state)
    last_stored = [p for p in served if p["timestamp"] == stored.captured_at.isoformat()]
    assert len(last_stored) == 1, served[-3:]
    assert last_stored[0]["home_probability"] is None
    assert last_stored[0]["game_state"] is None
    assert not any((p.get("game_state") or {}).get(MARKER) for p in served)
    _no_internal_key(served)


async def test_route_a_marker_on_a_priced_row_is_not_a_withdrawal():
    now = datetime.now(UTC)
    served, stored = await _served_series(now, home=0.78, game_state={MARKER: True})
    point = [p for p in served if p["timestamp"] == stored.captured_at.isoformat()]
    assert len(point) == 1
    assert point[0]["home_probability"] == pytest.approx(0.78)
    assert point[0]["game_state"] is None
    _no_internal_key(served)
