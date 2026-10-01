"""#1833 (END side) — a finished game's chart ends where play ended, not where we wrote the result.

Seen on production (ux 2026-09-30, native 2026-10-01), ``/events/15292394``,
Real Madrid 77–78 Dubai, EuroLeague:

    tip-off            16:00Z
    last real reading  17:52Z   (sportsbook line + every source stop here)
    completed_at       21:23:09Z (when the result was WRITTEN)

``/history`` stamped the settlement point (1.0, ``bookmaker_count`` 0) at
``completed_at``, and the only score capture — the completion write — sat at
21:23:09 too, so "Since Start" read 9:00 AM → 2:24 PM with a lone result dot
3.5 h to the right of the line. Web draws its x-axis from the served points
(score history included), so both points must move or the web chart does not.

The rule: when ``completed_at`` lies past kickoff + the sport's longest game
(`SPORT_MAX_DURATIONS`), the result is stamped at the last real reading + 1 min
— the rule the route already used when ``completed_at`` was null. A prompt
``completed_at`` is untouched (control below).

The rig executes ``get_event_odds_history`` itself on the 8951 session shape.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routes.events import _observed_play_end, get_event_odds_history
from tests.test_history_window_stale_open_event import _Result
from tests.test_settled_fight_chart_ends_on_result_8951 import _book, _kalshi
from tests.test_settled_fight_chart_ends_on_result_8951 import _Session as _Session8951

UTC = timezone.utc
EVENT_ID = 15314294  # the 8951 helpers stamp rows with this id


def _tip():
    """Eight hours ago, to the minute. Offset first, truncate second (gotcha #44)."""
    return (datetime.now(UTC) - timedelta(hours=8)).replace(second=0, microsecond=0)


#: The specimen's last real reading, 112 minutes after tip (16:00Z → 17:52Z).
LAST_READING = timedelta(minutes=112)
#: The specimen's result write, 5h23m09s after tip (16:00Z → 21:23:09Z).
LATE_WRITE = timedelta(hours=5, minutes=23, seconds=9)


def _event(k, completed_after):
    return SimpleNamespace(
        id=EVENT_ID,
        status="completed",
        commence_time=k,
        completed_at=k + completed_after,
        home_team_name="Dubai Basketball",
        away_team_name="Real Madrid",
        home_score=78,
        away_score=77,
        sport=SimpleNamespace(key="basketball_euroleague"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.99}},
    )


def _books(k):
    """Two books quoting through the game, the last at the specimen's 17:52Z."""
    rows = []
    for i, minutes in enumerate(range(-30, 113, 2)):
        when = k + timedelta(minutes=minutes)
        rows.append(_book("draftkings", when, when + timedelta(minutes=2), 0.5752, 2 * i + 1))
        rows.append(_book("fanduel", when, when + timedelta(minutes=2), 0.5752, 2 * i + 2))
    return rows


def _kalshi_rows(k):
    return [_kalshi(k + timedelta(minutes=m, seconds=40), 0.6) for m in range(0, 112, 4)]


class _Session(_Session8951):
    """The 8951 session plus the score table, which it does not answer."""

    def __init__(self, event, books, kalshi, scores):
        super().__init__(event, books, kalshi, [])
        self.scores = scores

    async def execute(self, statement, *a, **kw):
        if "score_snapshots" in str(statement):
            return _Result(self.scores)
        return await super().execute(statement, *a, **kw)


def _score(event, when, home, away):
    return SimpleNamespace(event_id=event.id, captured_at=when, home_score=home, away_score=away)


def _serve(event, scores=None):
    k = event.commence_time
    if scores is None:
        # The specimen's only score capture: the completion write, 62 ms after it.
        scores = [_score(event, event.completed_at + timedelta(milliseconds=62), 78, 77)]
    session = _Session(event, _books(k), _kalshi_rows(k), scores)
    return asyncio.run(
        get_event_odds_history(
            event_id=EVENT_ID, hours=24, response=MagicMock(headers={}), db=session
        )
    )


def _ts(value):
    return datetime.fromisoformat(value)


def _every_served_stamp(payload):
    series = [payload["history"], payload["espn_history"], payload["aggregate_line"],
              payload["score_history"], *payload["win_prob_history"].values()]
    return [_ts(p["timestamp"]) for s in series for p in s]


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_the_specimens_result_lands_where_play_ended():
    k = _tip()
    payload = _serve(_event(k, LATE_WRITE))
    play_end = k + LAST_READING + timedelta(minutes=1)  # 17:53Z

    assert payload["history"][-1]["bookmaker_count"] == 0, "the result point is served"
    assert payload["history"][-1]["home_probability"] == 1.0
    assert _ts(payload["history"][-1]["timestamp"]) == play_end, (
        "the settlement point still sits at the result write, "
        f"{payload['history'][-1]['timestamp']}"
    )
    assert _ts(payload["win_prob_history"]["kalshi"][-1]["timestamp"]) == play_end
    assert payload["aggregate_line"] and _ts(payload["aggregate_line"][-1]["timestamp"]) == play_end


def test_the_final_score_dot_ends_with_the_line():
    """Web reads score_history into its x-axis; a 21:23 score dot keeps the 3 h gap."""
    k = _tip()
    payload = _serve(_event(k, LATE_WRITE))

    final = payload["score_history"][-1]
    assert (final["home_score"], final["away_score"]) == (78, 77), "the score itself is unchanged"
    assert final["timestamp"] == payload["history"][-1]["timestamp"]


def test_the_axis_ends_where_the_chart_ends_and_holds_every_point():
    k = _tip()
    payload = _serve(_event(k, LATE_WRITE))
    end = _ts(payload["time_domain"]["end"])

    assert end == k + LAST_READING + timedelta(minutes=1)
    assert max(_every_served_stamp(payload)) <= end
    assert _ts(payload["time_domain"]["start"]) == k


def test_an_in_game_score_capture_counts_as_a_reading():
    """A live score seen after the last price is evidence play was still going."""
    k = _tip()
    event = _event(k, LATE_WRITE)
    scores = [
        _score(event, k + timedelta(minutes=125), 76, 77),
        _score(event, event.completed_at + timedelta(milliseconds=62), 78, 77),
    ]
    payload = _serve(event, scores)
    play_end = k + timedelta(minutes=126)

    assert _ts(payload["history"][-1]["timestamp"]) == play_end
    assert [_ts(p["timestamp"]) for p in payload["score_history"]] == [
        k + timedelta(minutes=125), play_end,
    ]


# ---------------------------------------------------------------------------
# Controls — what must not move
# ---------------------------------------------------------------------------


def test_a_prompt_result_write_keeps_its_timestamp():
    """completed_at 2h10m after tip is inside a basketball game's 3.5 h: it may be
    the finish, and readings that stopped early must not cut the chart short.
    The BEFORE behaviour, on the same rows."""
    k = _tip()
    prompt = timedelta(hours=2, minutes=10)
    payload = _serve(_event(k, prompt))
    completed = k + prompt

    assert _ts(payload["history"][-1]["timestamp"]) == completed
    assert _ts(payload["score_history"][-1]["timestamp"]) == completed + timedelta(milliseconds=62)
    assert _ts(payload["time_domain"]["end"]) == completed + timedelta(minutes=30)


def test_the_rig_reproduces_the_defect_without_the_gate():
    """Strawman: had the sport allowed a 6 h game, the specimen is the old payload.

    If this ever reads 17:53 the rig stopped reproducing #1833 and the headline
    test would pass for a reason that is not this fix.
    """
    import app.tasks.odds_polling as odds_polling

    original = odds_polling.get_max_duration_for_sport
    odds_polling.get_max_duration_for_sport = lambda _key: 6.0
    try:
        k = _tip()
        payload = _serve(_event(k, LATE_WRITE))
    finally:
        odds_polling.get_max_duration_for_sport = original

    late = (k + LATE_WRITE).replace(second=0)
    assert _ts(payload["history"][-1]["timestamp"]) == late
    assert _ts(payload["time_domain"]["end"]) == k + LATE_WRITE + timedelta(minutes=30)


# ---------------------------------------------------------------------------
# The helper's edges
# ---------------------------------------------------------------------------


def _pts(*stamps):
    return [{"timestamp": s.isoformat()} for s in stamps]


def test_helper_keeps_completed_at_when_no_reading_follows_kickoff():
    k = datetime(2026, 9, 24, 16, 0, tzinfo=UTC)
    assert _observed_play_end(
        k + LATE_WRITE, k, 3.5, (_pts(k - timedelta(hours=2), k - timedelta(minutes=5)),), []
    ) is None


def test_helper_keeps_completed_at_when_a_reading_reaches_it():
    k = datetime(2026, 9, 24, 16, 0, tzinfo=UTC)
    assert _observed_play_end(
        k + LATE_WRITE, k, 3.5, (_pts(k + timedelta(hours=1), k + LATE_WRITE + timedelta(minutes=5)),), []
    ) is None


def test_helper_ignores_a_corrupt_or_missing_clock():
    k = datetime(2026, 9, 24, 16, 0, tzinfo=UTC)
    series = (_pts(k + timedelta(hours=1)),)
    assert _observed_play_end(k - timedelta(hours=1), k, 3.5, series, []) is None
    assert _observed_play_end(None, k, 3.5, series, []) is None
    assert _observed_play_end(k + LATE_WRITE, None, 3.5, series, []) is None


def test_helper_reads_naive_stamps_as_utc():
    k = datetime(2026, 9, 24, 16, 0, tzinfo=UTC)
    naive = [{"timestamp": "2026-09-24T17:52:00"}]
    assert _observed_play_end(k + LATE_WRITE, k, 3.5, (naive,), []) == k + timedelta(minutes=113)


def test_helper_does_not_let_the_result_write_vouch_for_itself():
    """The completion write is outside the plausible window, so it is no reading."""
    k = datetime(2026, 9, 24, 16, 0, tzinfo=UTC)
    write = _pts(k + LATE_WRITE)
    assert _observed_play_end(
        k + LATE_WRITE, k, 3.5, (_pts(k + LAST_READING),), write
    ) == k + LAST_READING + timedelta(minutes=1)
