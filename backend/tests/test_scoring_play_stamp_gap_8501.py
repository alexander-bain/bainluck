"""#8501 — a live NCAAF chart drew its touchdown 15 minutes late.

`/events/15315984` (Liberty at Coastal Carolina): ESPN was not captured between
00:14:38Z (3–3) and 00:30:38Z (3–10). `_assign_wall_clock_timestamps` stamped the
touchdown at the first ESPN capture after that gap and called it resolved, while
`score_history` in the SAME response had seen 3–10 at 00:15:38Z.

The rule now: a play is stamped at the EARLIEST served sighting of its post-play
score (either series), and it is `timestamp_resolved` only when the sighting
before that one is at most `_PLAY_STAMP_MAX_GAP` earlier.

The fixture is the served payload of the specimen (see its `_provenance`).
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.events import (
    _PLAY_STAMP_MAX_GAP,
    _assign_wall_clock_timestamps,
    get_event_odds_history,
)
from tests.test_game_period_timing_5140 import _dt, _ReplaySession, _Result, _session

FX = json.loads(
    (
        pathlib.Path(__file__).resolve().parent
        / "fixtures"
        / "ncaaf_15315984_scoring_play_gap_8501.json"
    ).read_text()
)
TD_3_10 = (3, 10)  # D. Purdie 58-yd pass to M. Jackson, Q1 3:13


def _by_score(plays):
    return {(p["home_score"], p["away_score"]): p for p in plays}


def _first_sighting(score):
    times = [
        _dt(s["timestamp"])
        for s in FX["espn_history"] + FX["score_history"]
        if (s["home_score"], s["away_score"]) == score
    ]
    return min(times)


class TestSpecimen:
    def test_the_banked_before_is_the_defect(self):
        """The fixture really is the filing: the touchdown was served at the
        post-gap ESPN capture and called resolved."""
        before = _by_score(FX["served_before"])[TD_3_10]
        assert before["timestamp"].startswith("2026-09-25T00:30:38")
        assert before["timestamp_resolved"] is True

    def test_the_touchdown_is_stamped_when_the_score_was_first_seen(self):
        out = _by_score(
            _assign_wall_clock_timestamps(
                FX["scoring_plays_raw"], FX["espn_history"], FX["score_history"]
            )
        )
        td = out[TD_3_10]
        assert td["timestamp"] == "2026-09-25T00:15:38.022941+00:00"
        # ESPN saw 3–3 at 00:14:38, a minute earlier: the play is placed.
        assert td["timestamp_resolved"] is True

    def test_no_play_is_stamped_after_the_first_sighting_of_its_score(self):
        out = _assign_wall_clock_timestamps(
            FX["scoring_plays_raw"], FX["espn_history"], FX["score_history"]
        )
        assert len(out) == len(FX["scoring_plays_raw"])
        for play in out:
            score = (play["home_score"], play["away_score"])
            assert _dt(play["timestamp"]) == _first_sighting(score), play

    def test_a_sighting_after_a_capture_gap_is_not_called_resolved(self):
        """10–10: ESPN first shows it at 01:10:38, seven minutes after the capture
        before it (01:03:38), and score_history only at 01:20:38. The earliest
        sighting is the stamp; it bounds the play from after, so it is not
        resolved."""
        out = _by_score(
            _assign_wall_clock_timestamps(
                FX["scoring_plays_raw"], FX["espn_history"], FX["score_history"]
            )
        )
        tie = out[(10, 10)]
        assert tie["timestamp"] == "2026-09-25T01:10:38.114144+00:00"
        assert tie["timestamp_resolved"] is False

    def test_every_resolved_play_has_a_recent_capture_before_it(self):
        sightings = sorted(
            _dt(s["timestamp"]) for s in FX["espn_history"] + FX["score_history"]
        )
        out = _assign_wall_clock_timestamps(
            FX["scoring_plays_raw"], FX["espn_history"], FX["score_history"]
        )
        resolved = [p for p in out if p["timestamp_resolved"]]
        assert len(resolved) == 8  # all but 10–10
        for play in resolved:
            at = _dt(play["timestamp"])
            before = [t for t in sightings if t < at]
            assert before and at - before[-1] <= _PLAY_STAMP_MAX_GAP, play


class TestControls:
    def test_espn_alone_keeps_the_old_stamp_but_stops_calling_it_resolved(self):
        """Without score_history the stamp is what it was (00:30:38) — the only
        change on that path is the flag, because 16 minutes separate it from
        the capture before."""
        td = _by_score(
            _assign_wall_clock_timestamps(FX["scoring_plays_raw"], FX["espn_history"])
        )[TD_3_10]
        assert td["timestamp"] == "2026-09-25T00:30:38.382084+00:00"
        assert td["timestamp_resolved"] is False

    def test_a_play_seen_in_the_first_capture_is_not_resolved(self):
        """Nothing before the first capture says when the score changed."""
        out = _assign_wall_clock_timestamps(
            [{"home_score": 0, "away_score": 7, "period": 1, "clock": "9:00"}],
            [{"timestamp": "2026-09-25T00:00:00+00:00", "home_score": 0, "away_score": 7}],
        )
        assert out[0]["timestamp_resolved"] is False

    def test_a_tie_keeps_espns_timestamp_string(self):
        """Both series seeing a score at the same instant serves ESPN's string, as
        before. (On the specimen the two strings are byte-identical — the score
        row is written from the same poll — so the tie is built here with two
        spellings of one instant, or this could not fail.)"""
        out = _assign_wall_clock_timestamps(
            [{"home_score": 0, "away_score": 7, "period": 1, "clock": "9:00"}],
            [
                {"timestamp": "2026-09-25T00:00:00+00:00", "home_score": 0, "away_score": 0},
                {"timestamp": "2026-09-25T00:01:00+00:00", "home_score": 0, "away_score": 7},
            ],
            [{"timestamp": "2026-09-25T00:01:00.000000+00:00", "home_score": 0, "away_score": 7}],
        )
        assert out[0]["timestamp"] == "2026-09-25T00:01:00+00:00"
        assert out[0]["timestamp_resolved"] is True

    def test_exactly_the_gap_bound_is_resolved_and_one_second_more_is_not(self):
        t0 = datetime.fromisoformat("2026-09-25T00:00:00+00:00")
        play = [{"home_score": 0, "away_score": 7, "period": 1, "clock": "9:00"}]
        for extra, expected in ((timedelta(0), True), (timedelta(seconds=1), False)):
            snaps = [
                {"timestamp": t0.isoformat(), "home_score": 0, "away_score": 0},
                {
                    "timestamp": (t0 + _PLAY_STAMP_MAX_GAP + extra).isoformat(),
                    "home_score": 0,
                    "away_score": 7,
                },
            ]
            assert _assign_wall_clock_timestamps(play, snaps)[0]["timestamp_resolved"] is expected


# ── the route passes score_history through ──────────────────────────────────
class _WithScores(_ReplaySession):
    def __init__(self, base, scores):
        super().__init__(base.event, espn=base.espn, win_prob=base.win_prob)
        self.scores = scores

    async def execute(self, statement, *a, **kw):
        if "FROM score_snapshots" in str(statement):
            return _Result(self.scores)
        return await super().execute(statement, *a, **kw)


@pytest.mark.asyncio
async def test_the_route_stamps_the_touchdown_from_score_history():
    base = _session(
        event_id=FX["event_id"],
        sport_key="americanfootball_ncaaf",
        commence=_dt("2026-09-24T23:30:00+00:00"),
        completed=_dt("2026-09-25T03:40:00+00:00"),
        plays=FX["scoring_plays_raw"],
        espn_rows=FX["espn_history"],
    )
    scores = [
        SimpleNamespace(
            event_id=FX["event_id"],
            captured_at=_dt(s["timestamp"]),
            home_score=s["home_score"],
            away_score=s["away_score"],
        )
        for s in FX["score_history"]
    ]
    body = await get_event_odds_history(
        event_id=FX["event_id"],
        hours=720,
        response=MagicMock(headers={}),
        db=_WithScores(base, scores),
    )
    assert len(body["score_history"]) == len(FX["score_history"])
    td = _by_score(body["scoring_plays"])[TD_3_10]
    assert td["timestamp"] == "2026-09-25T00:15:38.022941+00:00"
    assert td["timestamp_resolved"] is True
