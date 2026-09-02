"""live/035 item 1b: backfilled history is worthless if the window clips it on read.

`GET /api/events/{id}/history?hours=N` windows a non-finished event at
`now - N`. That is a FOCUS device for an upcoming or in-progress game. Applied
to the cohort this queue exists for, it is a chord across a dead event.

The specimen, measured on production 2026-09-02:

    events.id 15300759   status 'scheduled'   commence_time 2026-08-30 00:00 UTC
    the match actually played 2026-09-01 23:00 .. 2026-09-02 01:43
    Kalshi price history spans 2026-08-27 17:17 .. 2026-09-02 01:43

`commence_time` is a Kalshi ticker-derived midnight stand-in (gotcha #14) and is
wrong by two days, so it can bound nothing. The web page asks for `hours=48`,
which would clip four of the five days of drift the backfill just recovered.

These tests drive the REAL route function against a stubbed session rather than
re-implementing its windowing, because a replicated window is a window that can
agree with the test and disagree with production.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.events import (
    _event_started_long_ago_unsettled,
    get_event_odds_history,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------


def _ev(commence_offset_hours, **kw):
    now = datetime.now(UTC)
    return SimpleNamespace(
        commence_time=(
            None
            if commence_offset_hours is None
            else now + timedelta(hours=commence_offset_hours)
        ),
        **kw,
    )


def test_a_match_that_started_days_ago_and_never_settled_is_served_whole():
    now = datetime.now(UTC)
    assert _event_started_long_ago_unsettled(_ev(-72), now, hours=48) is True


def test_a_game_in_progress_is_still_windowed():
    """Control. The window is right for a live game and must not be lifted."""
    now = datetime.now(UTC)
    assert _event_started_long_ago_unsettled(_ev(-2), now, hours=48) is False


def test_an_upcoming_game_is_still_windowed():
    now = datetime.now(UTC)
    assert _event_started_long_ago_unsettled(_ev(+6), now, hours=48) is False


def test_an_event_with_no_commence_time_is_never_convicted():
    now = datetime.now(UTC)
    assert _event_started_long_ago_unsettled(_ev(None), now, hours=48) is False


def test_the_predicate_follows_the_REQUESTED_window_not_a_constant():
    """`hours` is a caller parameter; a hard-coded 24 would misjudge `hours=168`."""
    now = datetime.now(UTC)
    event = _ev(-72)
    assert _event_started_long_ago_unsettled(event, now, hours=48) is True
    assert _event_started_long_ago_unsettled(event, now, hours=168) is False


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _DispatchingSession:
    """Answers each query by the table it reads, HONOURING its time bounds.

    A stub that ignored the WHERE clause would return every row under both arms,
    so the windowed control would pass against a route that had stopped
    windowing entirely — the guard would be vacuous in the direction that
    matters. Instead the compiled bind parameters are read back and applied, so
    "no datetime bound was compiled" is what makes the unwindowed arm differ.
    """

    def __init__(self, event, win_prob_rows):
        self.event = event
        self.win_prob_rows = win_prob_rows
        self.win_prob_time_bounds: list[datetime] = []

    async def execute(self, statement, *_a, **_kw):
        sql = str(statement)
        if "FROM events" in sql:
            return _Result([self.event])
        if "win_prob_snapshots" in sql:
            bounds = _datetime_params(statement)
            self.win_prob_time_bounds = bounds
            if not bounds:
                return _Result(self.win_prob_rows)
            cutoff = min(bounds)
            return _Result(
                [r for r in self.win_prob_rows if r.captured_at >= cutoff]
            )
        return _Result([])


def _datetime_params(statement) -> list[datetime]:
    try:
        params = statement.compile().params
    except Exception:  # pragma: no cover — a stub must never mask the route
        return []
    return [v for v in params.values() if isinstance(v, datetime)]


def _snapshot(when, home_prob):
    return SimpleNamespace(
        captured_at=when,
        source="kalshi",
        home_win_probability=home_prob,
        away_win_probability=round(1.0 - home_prob, 4),
        draw_probability=None,
        game_state={
            "market_name": "Vallejo vs Monfils",
            "poll_type": "history_backfill",
            "backfill_source": "kalshi_candlesticks",
        },
    )


def _specimen_event(now):
    return SimpleNamespace(
        id=15300759,
        status="scheduled",
        commence_time=now - timedelta(days=3),
        completed_at=None,
        home_team_name="Vallejo",
        away_team_name="Monfils",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="tennis_atp_us_open"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.01}},
    )


def _backfilled_curve(now):
    """Five days of drift ending in a settlement — the shape the backfill draws."""
    start = now - timedelta(days=5, hours=12)
    rows = []
    for step in range(120):
        rows.append(
            _snapshot(start + timedelta(hours=step), round(0.50 - step * 0.004, 4))
        )
    rows.append(_snapshot(now - timedelta(hours=3), 0.0))
    return rows


async def _history(event, rows, hours):
    session = _DispatchingSession(event, rows)
    payload = await get_event_odds_history(
        event_id=event.id, hours=hours, response=MagicMock(headers={}), db=session
    )
    return payload, session


async def test_the_whole_recovered_curve_is_served_not_the_last_48_hours():
    now = datetime.now(UTC)
    event = _specimen_event(now)
    rows = _backfilled_curve(now)

    payload, session = await _history(event, rows, hours=48)
    served = payload["win_prob_history"]["kalshi"]

    assert session.win_prob_time_bounds == [], (
        "the win-prob query still compiled a time bound on a stale-open event"
    )

    assert len(served) == len(rows), (
        "the backfilled pre-match drift was clipped by the 48-hour window"
    )
    earliest = datetime.fromisoformat(served[0]["timestamp"])
    assert earliest < now - timedelta(hours=48)
    assert served[-1]["home_probability"] == 0.0, "the settlement must survive too"


async def test_a_live_game_is_still_windowed():
    """The control that keeps this change narrow.

    Same route, same rows, an event that started an hour ago: the window must
    still apply, or every live page starts serving days of stale points.
    """
    now = datetime.now(UTC)
    event = _specimen_event(now)
    event.commence_time = now - timedelta(hours=1)
    event.status = "live"
    rows = _backfilled_curve(now)

    payload, session = await _history(event, rows, hours=48)
    served = payload["win_prob_history"].get("kalshi", [])

    assert session.win_prob_time_bounds, "a live game must still compile a cutoff"
    assert len(served) < len(rows), "a live game must keep its focused window"


async def test_the_time_domain_contains_the_data_it_is_the_domain_of():
    """#240's axis must not open AFTER the first point on this cohort.

    `commence_time` is the wrong field here, so an axis anchored on it would
    hide the drift the backfill just recovered.
    """
    now = datetime.now(UTC)
    event = _specimen_event(now)
    rows = _backfilled_curve(now)

    payload, _session = await _history(event, rows, hours=48)
    domain_start = datetime.fromisoformat(payload["time_domain"]["start"])
    earliest = datetime.fromisoformat(
        payload["win_prob_history"]["kalshi"][0]["timestamp"]
    )

    assert domain_start <= earliest
    assert domain_start < event.commence_time


async def test_a_stale_open_event_is_cached_like_a_finished_one():
    """It is a dead event; re-deriving it per request buys nothing."""
    now = datetime.now(UTC)
    event = _specimen_event(now)
    response = MagicMock(headers={})
    session = _DispatchingSession(event, _backfilled_curve(now))

    await get_event_odds_history(
        event_id=event.id, hours=48, response=response, db=session
    )

    assert "max-age=3600" in response.headers.get("Cache-Control", "")
