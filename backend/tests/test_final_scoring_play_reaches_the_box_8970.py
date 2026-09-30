"""#8970 — a finished game's scoring plays end on its final score.

Seen on production 2026-09-26, `/events/15313791` (Iowa 20 @ Michigan 19): Iowa
won on a touchdown at 0:00, and 29 minutes after the final the page's scoring
plays still ended on Michigan's 11:59 touchdown (19–14).

Mechanism: `fetch_live_box_scores` stamps `live: True` and reads only rows whose
status is `live`; `fetch_completed_box_scores` read only rows with NO box at
all. So the box froze at the last live fetch — 23:02:56Z here, 105 s before the
23:04:41Z final — and nothing ever asked ESPN again. Measured the same evening:
114 completed ESPN-linked events in the trailing 48 h still carried a live box,
and 13 football finals had stored scoring plays ending short of their own score
(Ohio State 41 of 42, Dartmouth 28–28 of 28–31, Georgetown 17–17 of 17–20, …).

The rule these tests pin: a completed row whose box is still the live one is
asked once more, the settled answer replaces it (line score kept), and the
rewrite carries no live stamp so the row is not asked again.
"""

from __future__ import annotations

import contextlib

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

# The six plays production held for 15313791 (fetched 23:02:56Z, live box) …
_STORED_PLAYS = [
    {"team": "Michigan Wolverines", "type": "Passing Touchdown", "clock": "1:58", "period": 1, "away_score": 0, "home_score": 7},
    {"team": "Iowa Hawkeyes", "type": "Kickoff", "clock": "1:44", "period": 1, "away_score": 7, "home_score": 7},
    {"team": "Michigan Wolverines", "type": "Field Goal Good", "clock": "12:58", "period": 2, "away_score": 7, "home_score": 10},
    {"team": "Michigan Wolverines", "type": "Field Goal Good", "clock": "1:29", "period": 3, "away_score": 7, "home_score": 13},
    {"team": "Iowa Hawkeyes", "type": "Passing Touchdown", "clock": "14:02", "period": 4, "away_score": 14, "home_score": 13},
    {"team": "Michigan Wolverines", "type": "Passing Touchdown", "clock": "11:59", "period": 4, "away_score": 14, "home_score": 19},
]
# … and the play ESPN's summary for 401858463 lists after them.
_WALK_OFF = {"team": "Iowa Hawkeyes", "type": "Passing Touchdown", "clock": "0:00", "period": 4, "away_score": 20, "home_score": 19}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _RecordingSession:
    """Answers the SELECT with `events` and records every later `execute`."""

    def __init__(self, events):
        self._events = events
        self.selects: list = []
        self.writes: list = []

    async def execute(self, statement, params=None):
        if params is None:
            self.selects.append(statement)
            return _FakeResult(self._events)
        self.writes.append((statement, params))
        return _FakeResult([])

    def begin_nested(self):
        # #9713: the settled box-score write runs in a per-game SAVEPOINT.
        return contextlib.nullcontext()


def _completed_event(box_score_data):
    event = MagicMock()
    event.id = 15313791
    event.espn_id = "401858463"
    event.status = "completed"
    event.box_score_data = box_score_data
    event.sport = MagicMock()
    event.sport.key = "americanfootball_ncaaf"
    return event


def _live_box():
    return {
        "source": "espn",
        "fetched_at": "2026-09-26T23:02:56.624218+00:00",
        "players": {"Hank Brown": {"passing_yards": 201}},
        "scoring_plays": list(_STORED_PLAYS),
        "home_period_scores": [7, 3, 3, 6],
        "away_period_scores": [7, 0, 0, 7],
        "live": True,
    }


async def _run_completed_pass(event, context):
    from app.utils import espn_helpers

    service = MagicMock()
    service.get_event_context = AsyncMock(return_value=context)
    service.close = AsyncMock()
    session = _RecordingSession([event])
    stats: dict = {}
    with patch("app.services.espn_api.ESPNAPIService", return_value=service):
        await espn_helpers.fetch_completed_box_scores(session, stats)
    return session, stats, service


def _where_sql(session) -> str:
    assert len(session.selects) == 1
    return str(
        session.selects[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


@pytest.mark.asyncio
async def test_the_pass_asks_a_completed_row_whose_box_is_still_the_live_one():
    """The selection half: without it the specimen is never read again."""
    session, _, _ = await _run_completed_pass(_completed_event(_live_box()), None)
    sql = _where_sql(session)

    assert "events.box_score_data IS NULL" in sql
    assert "(events.box_score_data ->> 'live') = 'true'" in sql
    # Still only finished rows: the live pass owns a game while it is live.
    assert "events.status IN ('completed', 'closed')" in sql


@pytest.mark.asyncio
async def test_the_walk_off_touchdown_reaches_the_stored_scoring_plays():
    """The specimen: six stored plays ending 19–14 become seven ending 19–20."""
    event = _completed_event(_live_box())
    session, stats, _ = await _run_completed_pass(
        event,
        {
            "box_score": {"Hank Brown": {"passing_yards": 217}},
            "scoring_plays": _STORED_PLAYS + [_WALK_OFF],
            "scores": {
                "home_period_scores": [7, 3, 3, 6],
                "away_period_scores": [7, 0, 0, 13],
                "is_final": True,
            },
        },
    )

    assert len(session.writes) == 1
    written = json.loads(session.writes[0][1]["bsd"])
    last = written["scoring_plays"][-1]
    assert (last["home_score"], last["away_score"]) == (19, 20)
    assert len(written["scoring_plays"]) == 7
    # The rewrite is the settled box: no live stamp, so it is asked once.
    assert "live" not in written
    # The line score the live box carried is not dropped (#5088).
    assert written["away_period_scores"] == [7, 0, 0, 13]
    assert written["home_period_scores"] == [7, 3, 3, 6]
    assert stats["box_scores_settled_over_live"] == 1


@pytest.mark.asyncio
async def test_an_empty_settled_answer_keeps_the_live_box_and_drops_only_the_stamp():
    """ESPN answering with nothing must not replace a box we hold with an error
    stamp — and must not leave the row re-asked every minute for 48 hours."""
    event = _completed_event(_live_box())
    session, _, _ = await _run_completed_pass(
        event, {"box_score": {}, "scoring_plays": [], "scores": {}}
    )

    assert len(session.writes) == 1
    written = json.loads(session.writes[0][1]["bsd"])
    assert "error" not in written
    assert written["scoring_plays"] == _STORED_PLAYS
    assert written["players"] == {"Hank Brown": {"passing_yards": 201}}
    assert written["live"] is False


@pytest.mark.asyncio
async def test_authority_dark_writes_nothing_so_the_row_is_asked_again():
    session, _, _ = await _run_completed_pass(_completed_event(_live_box()), None)
    assert session.writes == []


@pytest.mark.asyncio
async def test_THE_CONTROL_a_row_with_no_box_still_gets_the_not_available_stamp():
    """The pass's original population behaves exactly as before."""
    event = _completed_event(None)
    session, stats, _ = await _run_completed_pass(
        event, {"box_score": {}, "scoring_plays": [], "scores": {}}
    )

    assert len(session.writes) == 1
    written = json.loads(session.writes[0][1]["bsd"])
    assert written["error"] == "not_available"
    assert "box_scores_settled_over_live" not in stats


@pytest.mark.asyncio
async def test_THE_CONTROL_a_first_box_for_a_row_with_none_is_written_as_before():
    event = _completed_event(None)
    session, stats, _ = await _run_completed_pass(
        event, {"box_score": {"A": {}}, "scoring_plays": [_WALK_OFF], "scores": {}}
    )

    written = json.loads(session.writes[0][1]["bsd"])
    assert written["scoring_plays"] == [_WALK_OFF]
    assert "live" not in written and "home_period_scores" not in written
    assert stats["box_scores_fetched"] == 1
    assert "box_scores_settled_over_live" not in stats
