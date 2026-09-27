"""#9179 — a live NFL page's Q1 line stands where the game clock started, and stays.

    cd backend && python3 -m pytest tests/test_q1_clock_bracket_9179.py

The 2026-09-27 17:00Z slate drew Q1 at the FIRST SCORE on 4 of 9 games (LAC@BUF
+7.5 min, SEA@WSH +17.5) and at the first ESPN reading on the other 5. Then, the
moment Q2 was observed, the transition tier replaced the whole chain with `[Q2]`
and Q1 disappeared. The stream already brackets Q1: the clock reads `15:00` at
one poll and is running at the next.

`TestServedQ1` drives the REAL route over a trimmed replay of LAC@BUF 14781134
(`fixtures/nfl_14781134_history_replay.json`, read-only /history, ~18:00Z).
Red-first on master `406b79e0c9`, measured: 7 of 17 fail — the four
served-Q1 claims, the two positive helper cases and the tier-3 case. The fixture
check, the refusals and the NBA control pass on both sides, which is their job
(the refusals pin #6718's rules in place). Each refusal was mutated separately
and each mutant is caught.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.routes.events import get_event_odds_history
from app.utils import period_markers as pm
from tests.test_game_period_timing_5140 import _session

UTC = timezone.utc
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "nfl_14781134_history_replay.json"

CLOCK_LEFT_15_00_AFTER = "2026-09-27T17:04:37.713258+00:00"  # last `15:00 - 1st Quarter`
CLOCK_SEEN_RUNNING_AT = "2026-09-27T17:05:37.485953+00:00"   # `14:44 - 1st Quarter`
FIRST_SCORE_AT = "2026-09-27T17:12:37.815989+00:00"          # what the parent served


def _dt(iso):
    return datetime.fromisoformat(iso)


async def _serve(*, until=None, plays=True):
    """The route's markers for LAC@BUF as a page open at `until` would read them."""
    fx = json.loads(FIXTURE.read_text())

    def keep(ts):
        return until is None or _dt(ts) <= _dt(until)

    session = _session(
        event_id=fx["event_id"], sport_key=fx["sport_key"],
        commence=_dt(fx["commence_time"]), completed=_dt(fx["completed_at"]),
        plays=[
            p for p, served in zip(fx["scoring_plays_raw"], fx["served_scoring_plays_at_fetch"])
            if keep(served["timestamp"])
        ] if plays else [],
        espn_rows=[r for r in fx["espn_history"] if keep(r["timestamp"])],
        wp_rows=[(s, [p for p in pts if keep(p["timestamp"])])
                 for s, pts in fx["win_prob_history"].items()],
    )
    body = await get_event_odds_history(
        event_id=fx["event_id"], hours=720, response=MagicMock(headers={}), db=session
    )
    return body["period_markers"]


def _q1(markers):
    hit = [m for m in markers if m["period"] in ("1st Quarter", "1")]
    assert len(hit) <= 1, f"Q1 served more than once: {markers}"
    return hit[0] if hit else None


@pytest.mark.asyncio
class TestServedQ1:
    async def test_the_fixture_is_the_defect(self):
        """Production served no Q1 at all at fetch time — only the observed Q2."""
        fx = json.loads(FIXTURE.read_text())
        assert [m["period"] for m in fx["served_period_markers_at_fetch"]] == ["2nd Quarter"]

    async def test_q1_is_where_the_clock_started_not_the_first_score(self):
        q1 = _q1(await _serve(until="2026-09-27T17:20:00+00:00"))
        assert q1 is not None
        assert q1["timestamp"] == CLOCK_SEEN_RUNNING_AT, (
            f"Q1 at {q1['timestamp']}; {FIRST_SCORE_AT} is the touchdown"
        )
        assert q1["not_before"] == CLOCK_LEFT_15_00_AFTER
        assert q1["precision"] == pm.PRECISION_FIRST_SEEN
        assert q1["source"] == pm.SOURCE_ESPN_STATE

    async def test_q1_survives_q2_being_observed(self):
        """The whole-chain replacement is what deleted it on production."""
        markers = await _serve()
        assert [m["period"] for m in markers] == ["1st Quarter", "2nd Quarter"], markers
        assert _q1(markers)["timestamp"] == CLOCK_SEEN_RUNNING_AT

    async def test_a_held_page_q1_does_not_move_as_the_game_goes_on(self):
        """A page open from the first running reading through the touchdown, the
        field goal and into Q2 draws Q1 in one place at every refresh."""
        reads = {}
        for until in ("2026-09-27T17:06:00+00:00", "2026-09-27T17:11:00+00:00",
                      "2026-09-27T17:13:00+00:00", "2026-09-27T17:36:00+00:00", None):
            q1 = _q1(await _serve(until=until))
            reads[until] = q1 and (q1["timestamp"], q1["not_before"])
        assert set(reads.values()) == {(CLOCK_SEEN_RUNNING_AT, CLOCK_LEFT_15_00_AFTER)}, reads

    async def test_a_scored_and_a_scoreless_game_put_q1_in_the_same_bracket(self):
        """Same slate, same stream: whether anyone has scored must not decide which
        kind of moment Q1 is drawn at (parent: touchdown vs first ESPN reading)."""
        scored = _q1(await _serve(until="2026-09-27T17:20:00+00:00", plays=True))
        scoreless = _q1(await _serve(until="2026-09-27T17:20:00+00:00", plays=False))
        assert scored == scoreless


class TestClockBracketRefusals:
    """#6718's refusals survive: the bracket needs two observations, both clean."""

    T0 = datetime(2026, 9, 27, 17, 3, tzinfo=UTC)

    def _obs(self, minute, period, second=0):
        return {"timestamp": (self.T0 + timedelta(minutes=minute, seconds=second)).isoformat(),
                "period": period}

    def _q1(self, rows, sport="americanfootball_nfl"):
        return _q1(pm.observed_transition_markers(sport, rows))

    def test_a_lone_start_clock_is_no_marker(self):
        assert self._q1([self._obs(0, "15:00 - 1st Quarter")]) is None
        assert self._q1([self._obs(0, "15:00 - 1st Quarter"),
                         self._obs(1, "15:00 - 1st Quarter")]) is None

    def test_a_stream_that_opens_running_is_no_marker(self):
        assert self._q1([self._obs(0, "14:44 - 1st Quarter"),
                         self._obs(1, "13:58 - 1st Quarter")]) is None

    def test_a_start_clock_after_a_running_one_brackets_nothing(self):
        """A lagging source repeating `15:00` after the clock ran is not a lower bound."""
        assert self._q1([self._obs(0, "14:44 - 1st Quarter"), self._obs(1, "15:00 - 1st Quarter"),
                         self._obs(2, "13:58 - 1st Quarter")]) is None

    def test_the_marker_sits_on_the_running_row_never_the_start_clock(self):
        rows = [self._obs(0, "15:00 - 1st Quarter"), self._obs(1, "15:00 - 1st Quarter"),
                self._obs(2, "14:44 - 1st Quarter"), self._obs(3, "14:35 - 1st Quarter")]
        q1 = self._q1(rows)
        assert (q1["timestamp"], q1["not_before"]) == (rows[2]["timestamp"], rows[1]["timestamp"])
        assert q1["precision"] == pm.PRECISION_FIRST_SEEN

    def test_even_a_tight_clock_bracket_is_only_first_seen(self):
        """The clock can sit at 15:00 through a touchback kickoff, so this bracket
        never earns `boundary_observed`, however close the two polls are."""
        q1 = self._q1([self._obs(0, "15:00 - 1st Quarter"), self._obs(0, "14:58 - 1st Quarter", 20)])
        assert q1["precision"] == pm.PRECISION_FIRST_SEEN

    def test_a_contradictory_instant_is_neither_end_of_the_bracket(self):
        t = self._obs(1, "")["timestamp"]
        rows = [self._obs(0, "15:00 - 1st Quarter"),
                {"timestamp": t, "period": "14:44 - 1st Quarter"},
                {"timestamp": t, "period": "End of 1st Quarter"}]
        assert self._q1(rows) is None

    def test_a_bracket_wider_than_first_seen_allows_is_no_marker(self):
        wide = pm.MAX_FIRST_SEEN_BRACKET + timedelta(minutes=1)
        rows = [self._obs(0, "15:00 - 1st Quarter"),
                {"timestamp": (self.T0 + wide).isoformat(), "period": "9:00 - 1st Quarter"}]
        assert self._q1(rows) is None

    def test_the_stream_moving_on_before_the_clock_ran_is_no_marker(self):
        assert self._q1([self._obs(0, "15:00 - 1st Quarter"),
                         self._obs(30, "15:00 - 2nd Quarter")]) is None

    def test_overtime_is_not_clock_bracketed(self):
        """Quarters only — even a playoff overtime that opens on `15:00`."""
        for opening in ("10:00", "15:00"):
            got = pm.observed_transition_markers("americanfootball_nfl", [
                self._obs(0, f"{opening} - Overtime"), self._obs(1, "9:31 - Overtime")])
            assert got == [], opening

    def test_other_sports_are_untouched(self):
        assert pm.observed_transition_markers("basketball_nba", [
            self._obs(0, "15:00 - 1st Quarter"), self._obs(1, "14:44 - 1st Quarter")]) == []


@pytest.mark.asyncio
class TestWinProbTierKeysOnThePeriod:
    """(b): the tier-3 fallback served one marker per CLOCK READING on football."""

    async def _served(self, sport_key, periods):
        t0 = datetime(2026, 9, 27, 17, 3, tzinfo=UTC)
        pts = [{"timestamp": (t0 + timedelta(minutes=i)).isoformat(), "home_probability": 0.5,
                "away_probability": 0.5, "game_state": {"period": p}} for i, p in enumerate(periods)]
        session = _session(event_id=14999179, sport_key=sport_key, commence=t0,
                           completed=t0 + timedelta(hours=3), plays=[], wp_rows=[("espn", pts)])
        body = await get_event_odds_history(event_id=14999179, hours=720,
                                            response=MagicMock(headers={}), db=session)
        return [(m["period"], m["timestamp"]) for m in body["period_markers"]], t0

    async def test_clock_readings_of_one_quarter_are_one_marker(self):
        # opens running, so the transition tier has nothing and tier 3 is served
        got, t0 = await self._served("americanfootball_nfl", [
            "Sun, September 27th at 1:00 PM EDT", "14:51 - 1st Quarter",
            "14:30 - 1st Quarter", "13:02 - 1st Quarter"])
        assert got == [("1st Quarter", (t0 + timedelta(minutes=1)).isoformat())], got

    async def test_control_a_non_football_period_string_is_keyed_as_before(self):
        got, t0 = await self._served("basketball_nba", ["Q1 11:40", "Q1 11:02"])
        assert got == [("Q1 11:40", t0.isoformat()), ("Q1 11:02", (t0 + timedelta(minutes=1)).isoformat())]
