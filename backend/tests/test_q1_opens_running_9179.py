"""#9179, second arm — a Q1 whose ESPN stream opens already running stands at the
first running reading, bounded below by the listed kickoff, and stays there.

    cd backend && python3 -m pytest tests/test_q1_opens_running_9179.py

SNF LAR@DEN 14780548, 2026-09-28: `espn_history[0]` is `00:23:51Z 14:55 - 1st
Quarter` — no `15:00` row — so `_opening_clock_bracket` (the first arm, PR #9184)
had nothing, the chain fell to the first-SCORE tier, and production served Q1 at
the Rams touchdown (00:49:52Z, 26 minutes into the quarter). ux's notice-42 held
page watched the line move from ~5:23 to ~5:50 PM PT. Once Q2 is observed the
transition tier replaces the chain and Q1 would vanish altogether.

`TestServedQ1OpensRunning` drives the REAL route over a trimmed replay of that game
(`fixtures/nfl_14780548_opens_running_replay.json`, read-only /history +
box_score_data.scoring_plays, 01:02Z). The listed kickoff is a schedule fact, so it
is only ever `not_before`; the marker stands on an observation. The refusals pin
what keeps it a bound and not a guess.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.routes import events as events_route
from app.routes.events import get_event_odds_history
from app.utils import period_markers as pm
from tests.test_game_period_timing_5140 import _session

UTC = timezone.utc
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "nfl_14780548_opens_running_replay.json"

LISTED_KICKOFF = "2026-09-28T00:20:00+00:00"
FIRST_RUNNING_READ = "2026-09-28T00:23:51.695372+00:00"  # `14:55 - 1st Quarter`
RAMS_TD_ROW = "2026-09-28T00:49:52.124362+00:00"         # what production served


def _dt(iso):
    return datetime.fromisoformat(iso)


def _fx():
    return json.loads(FIXTURE.read_text())


async def _serve(*, until=None, plays=True):
    """The route's markers for LAR@DEN as a page open at `until` would read them."""
    fx = _fx()

    def keep(ts):
        return until is None or _dt(ts) <= _dt(until)

    session = _session(
        event_id=fx["event_id"], sport_key=fx["sport_key"],
        commence=_dt(fx["commence_time"]), completed=None,
        plays=[
            p for p, served in zip(fx["scoring_plays_raw"], fx["served_scoring_plays_at_fetch"])
            if keep(served["timestamp"])
        ] if plays else [],
        espn_rows=[r for r in fx["espn_history"] if keep(r["timestamp"])],
        wp_rows=[(s, [p for p in pts if keep(p["timestamp"])])
                 for s, pts in fx["win_prob_history"].items()],
    )
    session.event.status = "live"
    body = await get_event_odds_history(
        event_id=fx["event_id"], hours=720, response=MagicMock(headers={}), db=session
    )
    return body["period_markers"]


def _q1(markers):
    hit = [m for m in markers if m["period"] in ("1st Quarter", "1")]
    assert len(hit) <= 1, f"Q1 served more than once: {markers}"
    return hit[0] if hit else None


@pytest.mark.asyncio
class TestServedQ1OpensRunning:
    async def test_the_fixture_is_the_defect(self):
        fx = _fx()
        assert fx["espn_history"][0]["timestamp"] == FIRST_RUNNING_READ
        assert fx["espn_history"][0]["period"] == "14:55 - 1st Quarter"
        assert not any(r["period"].startswith("15:00") for r in fx["espn_history"])
        served = fx["served_period_markers_at_fetch"]
        assert [(m["timestamp"], m["precision"]) for m in served] == [
            (RAMS_TD_ROW, pm.PRECISION_FIRST_SCORE)]

    async def test_q1_is_the_first_running_reading_not_the_touchdown(self):
        q1 = _q1(await _serve())
        assert q1 is not None
        assert q1["timestamp"] == FIRST_RUNNING_READ, (
            f"Q1 at {q1['timestamp']}; {RAMS_TD_ROW} is the Rams touchdown"
        )
        assert _dt(q1["not_before"]) == _dt(LISTED_KICKOFF)
        assert q1["precision"] == pm.PRECISION_FIRST_SEEN
        assert q1["source"] == pm.SOURCE_ESPN_STATE

    async def test_a_held_page_q1_does_not_move_when_the_rams_score(self):
        reads = {}
        for until in ("2026-09-28T00:26:00+00:00", "2026-09-28T00:45:00+00:00",
                      "2026-09-28T00:50:30+00:00", None):
            q1 = _q1(await _serve(until=until))
            reads[until] = q1 and (q1["timestamp"], _dt(q1["not_before"]))
        assert set(reads.values()) == {(FIRST_RUNNING_READ, _dt(LISTED_KICKOFF))}, reads

    async def test_q1_survives_q2_being_observed(self):
        """The transition tier replaces the whole chain once Q2 is seen; Q1 must be in it."""
        fx = _fx()
        last = fx["espn_history"][-1]["timestamp"]
        q2_at = (_dt(last) + timedelta(minutes=1)).isoformat()
        fx["espn_history"].append({**fx["espn_history"][-1], "timestamp": q2_at,
                                   "period": "15:00 - 2nd Quarter", "game_clock": "15:00"})
        session = _session(
            event_id=fx["event_id"], sport_key=fx["sport_key"],
            commence=_dt(fx["commence_time"]), completed=None,
            plays=fx["scoring_plays_raw"], espn_rows=fx["espn_history"],
            wp_rows=list(fx["win_prob_history"].items()),
        )
        session.event.status = "live"
        body = await get_event_odds_history(
            event_id=fx["event_id"], hours=720, response=MagicMock(headers={}), db=session
        )
        periods = [m["period"] for m in body["period_markers"]]
        assert periods == ["1st Quarter", "2nd Quarter"], body["period_markers"]
        assert _q1(body["period_markers"])["timestamp"] == FIRST_RUNNING_READ

    async def test_a_scored_and_a_scoreless_read_agree(self):
        scored = _q1(await _serve(plays=True))
        scoreless = _q1(await _serve(plays=False))
        assert scored == scoreless

    async def test_a_venue_expiration_clock_is_never_the_bound(self):
        """#7878: a commence_time that is the venue's expected END bounds nothing."""
        with patch.object(events_route, "_commence_time_is_venue_expiration", return_value=True):
            q1 = _q1(await _serve())
        assert q1 is None or q1.get("not_before") is None or \
            _dt(q1["not_before"]) != _dt(LISTED_KICKOFF), q1


class TestKickoffBracketRefusals:
    T0 = datetime(2026, 9, 28, 0, 20, tzinfo=UTC)  # listed kickoff

    def _obs(self, minute, period, second=0):
        return {"timestamp": (self.T0 + timedelta(minutes=minute, seconds=second)).isoformat(),
                "period": period}

    def _q1(self, rows, kickoff=None, sport="americanfootball_nfl"):
        return _q1(pm.observed_transition_markers(
            sport, rows, kickoff_not_before=self.T0 if kickoff is None else kickoff))

    def test_positive_control(self):
        rows = [self._obs(3, "14:55 - 1st Quarter", 51), self._obs(4, "14:25 - 1st Quarter", 51)]
        q1 = self._q1(rows)
        assert (q1["timestamp"], _dt(q1["not_before"])) == (rows[0]["timestamp"], self.T0)
        assert q1["precision"] == pm.PRECISION_FIRST_SEEN

    def test_no_kickoff_still_no_marker(self):
        """The first arm's refusal is unchanged for a caller that passes nothing."""
        rows = [self._obs(3, "14:55 - 1st Quarter"), self._obs(4, "14:25 - 1st Quarter")]
        assert _q1(pm.observed_transition_markers("americanfootball_nfl", rows)) is None

    def test_a_kickoff_after_the_first_reading_is_no_bound(self):
        rows = [self._obs(3, "14:55 - 1st Quarter")]
        assert self._q1(rows, kickoff=self.T0 + timedelta(minutes=5)) is None

    def test_a_bracket_wider_than_first_seen_allows_is_no_marker(self):
        late = pm.MAX_FIRST_SEEN_BRACKET + timedelta(minutes=1)
        rows = [{"timestamp": (self.T0 + late).isoformat(), "period": "14:10 - 1st Quarter"}]
        assert self._q1(rows) is None

    def test_a_clock_further_along_than_the_wall_is_no_bound(self):
        """3 minutes after the listing the clock has run 6: the game began before
        the listed kickoff, so the listing bounds nothing."""
        assert self._q1([self._obs(3, "9:00 - 1st Quarter")]) is None
        # the edge: exactly as much game time as wall time is still a bound
        assert self._q1([self._obs(3, "12:00 - 1st Quarter")]) is not None

    def test_a_lone_start_clock_is_still_no_marker(self):
        """`15:00` means the quarter may not have begun; the kickoff cannot change that."""
        assert self._q1([self._obs(3, "15:00 - 1st Quarter")]) is None

    def test_a_stream_that_opens_in_q2_does_not_bound_q2_from_kickoff(self):
        got = pm.observed_transition_markers(
            "americanfootball_nfl", [self._obs(10, "14:30 - 2nd Quarter")],
            kickoff_not_before=self.T0)
        assert got == []

    def test_a_stale_q1_delivered_after_q2_was_seen_is_no_marker(self):
        """A lagging source's Q1 row after the stream reached Q2 is a regression;
        it says nothing about its own instant, so the kickoff cannot anchor it."""
        rows = [self._obs(3, "14:30 - 2nd Quarter"), self._obs(4, "13:50 - 2nd Quarter"),
                self._obs(5, "14:55 - 1st Quarter"), self._obs(6, "13:10 - 2nd Quarter")]
        assert self._q1(rows) is None

    def test_a_contradictory_first_instant_is_no_marker(self):
        t = self._obs(3, "")["timestamp"]
        rows = [{"timestamp": t, "period": "14:55 - 1st Quarter"},
                {"timestamp": t, "period": "End of 1st Quarter"}]
        assert self._q1(rows) is None

    def test_a_string_kickoff_parses_like_a_datetime(self):
        rows = [self._obs(3, "14:55 - 1st Quarter")]
        assert self._q1(rows, kickoff=self.T0.isoformat()) == self._q1(rows)

    def test_the_opening_clock_bracket_still_wins_when_it_exists(self):
        """A stream WITH a 15:00 row keeps the tighter two-observation bracket."""
        rows = [self._obs(3, "15:00 - 1st Quarter"), self._obs(4, "14:44 - 1st Quarter")]
        q1 = self._q1(rows)
        assert (q1["timestamp"], q1["not_before"]) == (rows[1]["timestamp"], rows[0]["timestamp"])

    def test_other_sports_are_untouched(self):
        assert pm.observed_transition_markers(
            "basketball_nba", [self._obs(3, "11:40 - 1st Quarter")],
            kickoff_not_before=self.T0) == []
