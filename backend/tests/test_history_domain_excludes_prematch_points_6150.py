"""live/228 (#6150): the served chart domain excluded 100% of the served points.

Measured on production 2026-09-14 13:01Z, three independent `scheduled` events
whose matches were 20–30 minutes away:

    event 15312285  commence 13:30  domain 13:30 -> 14:00   0 of 287 points inside
    event 15312299  commence 13:30  domain 13:30 -> 14:00   0 of 241 points inside
    event 15312301  commence 13:20  domain 13:20 -> 13:50   0 of 206 points inside

Every point was pre-match drift lying in the 14 hours BEFORE the domain opened.

The mechanism is two defects stacked, and the second hides the first:

  1. `_domain_start` is `commence_time` (in the future) while `_domain_end` is
     `now` — so on a not-yet-started event the domain is INVERTED at birth.
  2. The `MIN_LIVE_DOMAIN_SECONDS` floor then ASSIGNED
     `_domain_end = _domain_start + 30min`. On an inverted domain that is a
     narrowing, and it rewrites the inversion into a well-formed 30-minute
     window sitting entirely in the future.

Because step 2 always repairs the ordering, `end >= start` — the contract the
existing integration test asserts (`test_route_events_seeded.py`) — held on
every one of these rows. A domain can satisfy every stated invariant and still
contain none of its own data, so these tests assert CONTAINMENT, which is the
property the field exists to have.

The FIX is step 1 alone: widen the start to the earliest point actually served,
the same repair the two cohorts above it already make. The floor is deliberately
left exactly as it was. Two "defensive" edits were written here first and both
were deleted after mutation testing proved them unkillable:
`max(_domain_end, _domain_start + 30min)` is provably identical to the plain
assignment inside a branch already guarded by `_domain_end - _domain_start <
30min`; and widening the END cannot fire either, because `_domain_end` is `now`
on every unfinished event and no snapshot is captured in the future. Code no
test can kill is a false reassurance, not a safety net.

`is_live: not is_finished` is the third defect and the one the issue named: a
`scheduled` event is not live. The two siblings in `events.py`
(`_extend_win_prob_history_to_live_edge`, `_pin_blend_edge`) already carried the
`status == "live"` conjunct; the time domain was the unconverted call site.

These tests drive the REAL route function against the stubbed session the
stale-open module already built, rather than re-deriving the domain — a
replicated domain is one that can agree with the test and disagree with
production.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from tests.test_history_window_stale_open_event import _history  # noqa: E402

UTC = timezone.utc

#: The production specimen this module was measured on.
_SPECIMEN_ID = 15312285


def _snapshot(when, home_prob):
    return SimpleNamespace(
        event_id=_SPECIMEN_ID,
        captured_at=when,
        source="kalshi",
        home_win_probability=home_prob,
        away_win_probability=round(1.0 - home_prob, 4),
        draw_probability=None,
        game_state={"market_name": "Nikles vs Cerny"},
    )


def _prematch_event(now, *, minutes_to_start=30, status="scheduled"):
    """The specimen: a match that has NOT started, carrying pre-match drift."""
    return SimpleNamespace(
        id=_SPECIMEN_ID,
        status=status,
        commence_time=now + timedelta(minutes=minutes_to_start),
        completed_at=None,
        home_team_name="Nikles",
        away_team_name="Cerny",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="tennis_atp"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.99}},
    )


def _prematch_drift(now, *, hours=14, n=40):
    """`n` points of pre-match movement ending just before `now`."""
    start = now - timedelta(hours=hours)
    step = timedelta(hours=hours) / n
    return [_snapshot(start + step * i, round(0.58 + i * 0.008, 4)) for i in range(n)]


def _served_timestamps(payload):
    out = []
    for pts in payload["win_prob_history"].values():
        out.extend(datetime.fromisoformat(p["timestamp"]) for p in pts)
    out.extend(datetime.fromisoformat(p["timestamp"]) for p in payload["history"])
    return out


# ---------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------


async def test_the_domain_of_a_scheduled_event_contains_its_own_points():
    """The whole bug in one assertion: 0 of N inside is what shipped."""
    now = datetime.now(UTC)
    event = _prematch_event(now)
    rows = _prematch_drift(now)

    payload, _ = await _history(event, rows, hours=48)

    td = payload["time_domain"]
    start = datetime.fromisoformat(td["start"])
    end = datetime.fromisoformat(td["end"])
    served = _served_timestamps(payload)

    assert served, "the rig served no points, so containment would be vacuous"
    outside = [t for t in served if not (start <= t <= end)]
    assert not outside, (
        f"{len(outside)} of {len(served)} served points fall outside the served "
        f"domain {start} -> {end}"
    )


async def test_the_domain_of_a_scheduled_event_is_not_a_window_in_the_future():
    """The production signature: an axis that opens at a kickoff yet to happen."""
    now = datetime.now(UTC)
    event = _prematch_event(now)

    payload, _ = await _history(event, _prematch_drift(now), hours=48)

    start = datetime.fromisoformat(payload["time_domain"]["start"])
    assert start <= now, "the axis opens in the future"
    assert (
        start < event.commence_time
    ), "the axis is still anchored on a commence_time that lies after the data"


async def test_a_scheduled_event_is_not_reported_live():
    now = datetime.now(UTC)
    event = _prematch_event(now)

    payload, _ = await _history(event, _prematch_drift(now), hours=48)

    assert payload["time_domain"]["is_live"] is False


# ---------------------------------------------------------------------------
# Controls — the three cohorts this change must not touch
# ---------------------------------------------------------------------------


async def test_a_live_game_is_still_live_and_still_floored():
    """#240's original case. A young live game must keep its readable span."""
    now = datetime.now(UTC)
    event = _prematch_event(now, minutes_to_start=-5, status="live")
    # Four minutes of data on a game five minutes old: the sliver #240 exists for.
    rows = [_snapshot(now - timedelta(minutes=m), 0.60) for m in range(4, 0, -1)]

    payload, _ = await _history(event, rows, hours=48)

    td = payload["time_domain"]
    start = datetime.fromisoformat(td["start"])
    end = datetime.fromisoformat(td["end"])
    assert td["is_live"] is True
    assert (end - start).total_seconds() >= td[
        "min_window_seconds"
    ], "the minimum-width floor stopped applying to a young live game"


async def test_a_long_live_game_is_not_narrowed_to_the_floor():
    """The floor is a MINIMUM, so its width test has to be a real test.

    Drop the `< MIN_LIVE_DOMAIN_SECONDS` condition and this three-hour game gets
    cut back to a half-hour axis. That is the mutant this kills — not the shape
    of the assignment inside the branch, which the module docstring explains is
    unkillable by construction.
    """
    now = datetime.now(UTC)
    event = _prematch_event(now, minutes_to_start=-180, status="live")
    rows = _prematch_drift(now, hours=3, n=30)

    payload, _ = await _history(event, rows, hours=48)

    td = payload["time_domain"]
    start = datetime.fromisoformat(td["start"])
    end = datetime.fromisoformat(td["end"])
    assert (end - start).total_seconds() > td[
        "min_window_seconds"
    ], "a three-hour live game was narrowed to the 30-minute floor"
    assert max(_served_timestamps(payload)) <= end


async def test_a_live_game_keeps_its_axis_anchored_at_kickoff():
    """The widen is deliberately pre-match ONLY, and the asymmetry is the point.

    #240 anchors a live axis at `commence_time` so the chart reads as the game
    rather than as the week before it — the page's own "Since Start" view. So a
    live game carrying pre-match drift must NOT have its axis dragged back to
    that drift, even though those points are served. Drop the `not
    _is_live_now` conjunct from the widen and this is what breaks.
    """
    now = datetime.now(UTC)
    event = _prematch_event(now, minutes_to_start=-60, status="live")
    # Two hours of drift before a kickoff that was an hour ago, plus live play.
    rows = _prematch_drift(now, hours=3, n=30)

    payload, _ = await _history(event, rows, hours=48)

    start = datetime.fromisoformat(payload["time_domain"]["start"])
    assert (
        start == event.commence_time
    ), "a live game's axis was dragged back off kickoff to its pre-match drift"
    assert (
        min(_served_timestamps(payload)) < start
    ), "control is vacuous: no point actually precedes kickoff here"


async def test_a_finished_event_is_untouched():
    now = datetime.now(UTC)
    event = _prematch_event(now, minutes_to_start=-240, status="completed")
    event.completed_at = now - timedelta(minutes=30)
    event.home_score = 2
    event.away_score = 1
    rows = _prematch_drift(now, hours=4, n=30)

    payload, _ = await _history(event, rows, hours=48)

    td = payload["time_domain"]
    assert td["is_live"] is False
    start = datetime.fromisoformat(td["start"])
    end = datetime.fromisoformat(td["end"])
    assert end >= start


async def test_a_scheduled_event_with_no_points_still_serves_a_sane_domain():
    """The widen has nothing to widen to; it must not crash or invert."""
    now = datetime.now(UTC)
    event = _prematch_event(now)

    payload, _ = await _history(event, [], hours=48)

    td = payload["time_domain"]
    if td is None:
        return  # no data and no anchor is an honest absence
    start = datetime.fromisoformat(td["start"])
    end = datetime.fromisoformat(td["end"])
    assert end >= start, "an empty scheduled event served an inverted domain"
    assert td["is_live"] is False


# ---------------------------------------------------------------------------
# The rig itself
# ---------------------------------------------------------------------------


async def test_the_rig_actually_serves_the_points_it_builds():
    """Without this, every containment assertion above could pass on zero points."""
    now = datetime.now(UTC)
    rows = _prematch_drift(now)
    payload, _ = await _history(_prematch_event(now), rows, hours=48)

    assert len(payload["win_prob_history"].get("kalshi", [])) == len(rows)
