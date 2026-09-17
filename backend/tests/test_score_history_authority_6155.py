"""#6155 — a completed game's score line stops replaying PROVABLY superseded
readings, and keeps every reading the evidence cannot convict.

PILLAR: TRUTH. SHIP: `/events/14637256` (Giants v Cowboys, 2026-09-14) stops
drawing `7-0 -> 0-0 -> 7-0`; an overturned touchdown still draws going down.

Everything here drives the REAL route, `get_event_odds_history`, through the
#6390/#6462 rig. Two kinds of input, never mixed:

  * REAL — `fixtures/score_history_6155/history_<id>.json`, the public
    `/api/events/<id>/history` payload fetched 2026-09-17T04:46:56Z, sanitized
    (provenance inside each file). `espn_history` there is OUR ingest of ESPN,
    not a fresh provider read.
  * SYNTHETIC — built by `_game()`. Every such test says SYNTHETIC in its
    docstring. They prove what the RULE does with a shape; they prove nothing
    about what any provider ever sent.

A prettier chart is not the acceptance. The named trace keeps 9 of its 20
downward steps ON PURPOSE, and `TestWhatStaysOnTheNamedTrace` pins each one to
the reason the evidence cannot convict it.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.models import ESPNSnapshot, Event, ScoreSnapshot, Sport
from tests.test_price_table_fold_6390 import _HistoryResult, _HistoryRouteSession

FIXTURES = Path(__file__).parent / "fixtures" / "score_history_6155"
NFL_ID, MLB_ID = 14637256, 15311156
KICKOFF = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)


class _Session(_HistoryRouteSession):
    """The #6390 rig, also answering `score_snapshots` and `espn_snapshots`,
    each honouring the id filter (the parent's docstring says why)."""

    def __init__(self, event, score_rows, espn_rows):
        super().__init__(event, [(event.id, event.home_team_name, event.away_team_name)], [])
        self.score_rows, self.espn_rows = list(score_rows), list(espn_rows)

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())
        for table, rows in (("score_snapshots", self.score_rows), ("espn_snapshots", self.espn_rows)):
            if f"FROM {table}" in sql:
                ids = self._requested_ids(statement)
                kept = [r for r in rows if ids is None or r.event_id in ids]
                return _HistoryResult(sorted(kept, key=lambda r: r.captured_at))
        return await super().execute(statement, *_a, **_kw)


def _serve(event_id, home, away, sport_key, score_points, espn_points, plays, *,
           final, status="completed"):
    from app.routes import events as events_route

    def at(p):
        return datetime.fromisoformat(p["timestamp"])

    last = max(at(p) for p in score_points)
    event = Event(
        id=event_id, sport_id=90_006_155, home_team_name=home, away_team_name=away,
        commence_time=min(at(p) for p in score_points), status=status,
        home_score=final[0], away_score=final[1],
        completed_at=(last + timedelta(minutes=10)) if status == "completed" else None,
        box_score_data={"scoring_plays": plays} if plays else None,
    )
    event.sport = Sport(id=90_006_155, key=sport_key, name=sport_key)
    scores = [
        ScoreSnapshot(id=i + 1, event_id=event_id, captured_at=at(p),
                      home_score=p["home_score"], away_score=p["away_score"])
        for i, p in enumerate(score_points)
    ]
    espn = [
        ESPNSnapshot(id=i + 1, event_id=event_id, captured_at=at(p),
                     home_score=p["home_score"], away_score=p["away_score"],
                     game_clock=p.get("game_clock"), period=p.get("period"))
        for i, p in enumerate(espn_points)
    ]
    session = _Session(event, scores, espn)
    return asyncio.run(events_route.get_event_odds_history(event_id, hours=24 * 30, db=session))


def _real(event_id, sport_key):
    fx = json.loads((FIXTURES / f"history_{event_id}.json").read_text())
    payload = _serve(
        event_id, fx["event"]["home_team"], fx["event"]["away_team"], sport_key,
        fx["score_history"], fx["espn_history"], fx["scoring_plays"],
        final=fx["final_score"],
    )
    return fx, payload


def _line(points):
    return [(p["timestamp"][11:19], p["home_score"], p["away_score"]) for p in points]


def _down_steps(points):
    xs = [(p["home_score"], p["away_score"]) for p in points]
    return sum(1 for a, b in zip(xs, xs[1:]) if b[0] < a[0] or b[1] < a[1])


def _everything(payload):
    """Served + withheld, in time order: what is STORED, on either tree."""
    both = payload["score_history"] + payload.get("score_history_withheld", [])
    return sorted(both, key=lambda p: p["timestamp"])


def _withheld(payload):
    """For KEEP-controls only: they must hold on master too, where the key does
    not exist yet. Ship and positive-control tests read the key directly."""
    return payload.get("score_history_withheld", [])


# ─── REAL: the named trace ────────────────────────────────────────────────────


class TestTheNamedTrace:
    def test_the_stored_history_is_the_issues_49_rows_with_20_down_steps(self):
        """REAL. The reproduction, true before AND after: nothing is erased."""
        fx, payload = _real(NFL_ID, "americanfootball_nfl")
        stored = _everything(payload)
        assert _line(stored) == _line(fx["score_history"])
        assert len(stored) == 49 and _down_steps(stored) == 20
        assert ("00:41:41", 0, 0) in _line(stored), "the 7-0 -> 0-0 the issue names"

    def test_the_ship_eleven_superseded_readings_leave_the_drawn_line(self):
        """REAL. FAILS on master@776f22b9 (no `score_history_withheld` key)."""
        _, payload = _real(NFL_ID, "americanfootball_nfl")
        assert _line(payload["score_history_withheld"]) == [
            ("00:41:41", 0, 0), ("00:43:07", 0, 0),
            ("01:21:45", 7, 0), ("01:23:07", 7, 0),
            ("02:20:07", 14, 7), ("02:20:43", 20, 7), ("02:22:07", 20, 7),
            ("02:34:08", 21, 7), ("02:59:09", 21, 14),
            ("03:12:09", 28, 14), ("03:13:09", 28, 14),
        ]
        drawn = _line(payload["score_history"])
        assert len(drawn) == 38
        assert (0, 0) not in [(h, a) for t, h, a in drawn if t > "00:41:09"]
        assert drawn[-1][1:] == (28, 20)

    def test_the_espn_trace_it_leans_on_never_goes_down_on_this_game(self):
        """REAL. The premise, asserted rather than assumed."""
        fx, _ = _real(NFL_ID, "americanfootball_nfl")
        assert _down_steps(fx["espn_history"]) == 0


class TestWhatStaysOnTheNamedTrace:
    """REAL. Nine downward steps are KEPT. Truthful, not pretty."""

    def test_the_nine_kept_down_steps_and_why_each_cannot_be_convicted(self):
        _, payload = _real(NFL_ID, "americanfootball_nfl")
        drawn = _line(payload["score_history"])
        kept_down = [b for a, b in zip(drawn, drawn[1:]) if b[1] < a[1] or b[2] < a[2]]
        assert kept_down == [
            # ESPN never held these: TD-before-PAT states, or a real correction.
            ("01:23:46", 7, 6),
            # ESPN's own snapshots still read 7-7 on both sides: it AGREES.
            ("01:50:07", 7, 7), ("01:51:07", 7, 7),
            ("01:51:39", 13, 7),
            # A scoring play (the 6:59 TD) sits inside the bracket: a re-score
            # after a real correction would look exactly like this.
            ("02:19:07", 14, 7),
            ("02:33:08", 21, 7),
            ("02:34:42", 21, 13),
            ("03:00:09", 27, 14), ("03:01:09", 27, 14),
        ]


class TestTheMlbSpecimenIsNotCorrected:
    def test_no_play_evidence_means_nothing_is_withheld(self):
        """REAL. 15311156 has 15 down steps and ZERO box-score scoring plays;
        ESPN's position is mostly NULL. The rule refuses the whole event. This
        is the evidence limitation, pinned so nobody 'fixes' it with a clamp."""
        fx, payload = _real(MLB_ID, "baseball_mlb")
        assert fx["scoring_plays"] == []
        assert _withheld(payload) == []
        assert _down_steps(payload["score_history"]) == 15


# ─── SYNTHETIC controls ───────────────────────────────────────────────────────


def _t(seconds):
    return (KICKOFF + timedelta(seconds=seconds)).isoformat()


def _clock(minute):
    """Authority minute n of a 4th quarter counting down from 15:00."""
    return f"{15 - minute}:00 - 4th Quarter"


def _game(authority, scores, plays, **kw):
    """SYNTHETIC. `authority`: [(minute, home, away)] one ESPN row per minute on
    the :00, positioned by `_clock`. `scores`: [(second, home, away)]."""
    espn = [
        {"timestamp": _t(m * 60), "home_score": h, "away_score": a,
         "period": kw.get("period_at", _clock)(m), "game_clock": None}
        for m, h, a in authority
    ]
    pts = [{"timestamp": _t(s), "home_score": h, "away_score": a} for s, h, a in scores]
    final = kw.get("final", (scores[-1][1], scores[-1][2]))
    return _serve(990_006_155, "Home FC", "Away FC", "americanfootball_nfl",
                  pts, espn, plays, final=final, status=kw.get("status", "completed"))


def _play(minute, home, away, period="4"):
    return {"period": period, "clock": f"{15 - minute}:00" if isinstance(minute, int)
            else minute, "home_score": home, "away_score": away, "type": "TD", "team": "x"}


#: A lagging feed re-asserting 7-7 after the authority has moved to 14-7.
LAG_AUTH = [(0, 7, 7), (1, 7, 7), (2, 14, 7), (3, 14, 7), (4, 14, 7), (5, 14, 7)]
LAG_SCORES = [(0, 7, 7), (120, 14, 7), (150, 7, 7), (180, 14, 7), (300, 14, 7)]
LAG_PLAYS = [_play(2, 14, 7)]


class TestSyntheticControls:
    def test_positive_control_a_superseded_reading_is_withheld(self):
        """SYNTHETIC. Without this every control below passes vacuously."""
        p = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS)
        assert _line(p["score_history_withheld"]) == [("00:02:30", 7, 7)]

    def test_overturned_touchdown_that_persists_is_drawn_going_down(self):
        """SYNTHETIC. 14-7 -> 7-7 and it stays: the authority follows it."""
        auth = [(0, 7, 7), (1, 14, 7), (2, 14, 7), (3, 7, 7), (4, 7, 7), (5, 7, 7)]
        scores = [(0, 7, 7), (60, 14, 7), (150, 7, 7), (180, 7, 7), (300, 7, 7)]
        p = _game(auth, scores, [_play(1, 7, 7)])
        assert _withheld(p) == []
        assert _down_steps(p["score_history"]) == 1

    def test_correction_later_reversed_keeps_both_moves(self):
        """SYNTHETIC. 14-7 -> 7-7 -> 14-7: the authority RETURNS to each value,
        so neither the dip nor readings of 14-7 during it are withheld."""
        auth = [(0, 7, 7), (1, 14, 7), (2, 7, 7), (3, 7, 7), (4, 14, 7), (5, 14, 7)]
        scores = [(0, 7, 7), (60, 14, 7), (120, 7, 7), (150, 14, 7), (180, 7, 7),
                  (240, 14, 7), (300, 14, 7)]
        p = _game(auth, scores, [_play(1, 14, 7)])
        assert _withheld(p) == []

    def test_delayed_authoritative_correction_keeps_the_early_reading(self):
        """SYNTHETIC. The other feed shows the overturn two minutes before
        ESPN does. ESPN reads 14-7 on both sides of it — and later agrees."""
        auth = [(0, 7, 7), (1, 14, 7), (2, 14, 7), (3, 14, 7), (4, 7, 7), (5, 7, 7)]
        scores = [(0, 7, 7), (60, 14, 7), (150, 7, 7), (180, 14, 7), (240, 7, 7), (300, 7, 7)]
        p = _game(auth, scores, [_play(1, 7, 7)])
        assert ("00:02:30", 7, 7) in _line(p["score_history"])
        assert _withheld(p) == []

    def test_two_quick_legitimate_scores_around_a_correction(self):
        """SYNTHETIC. 14-7 is wiped to 7-7 and re-scored inside one ESPN
        minute. ESPN reads 14-7 both sides; the PLAY inside the bracket is
        what keeps the 7-7 reading."""
        plays = [_play(2, 14, 7), _play("12:30", 14, 7)]
        p = _game(LAG_AUTH, LAG_SCORES, plays)
        assert _withheld(p) == []

    def test_unchanged_score_in_the_same_inning_has_no_play_evidence(self):
        """SYNTHETIC. Span labels, no positioned plays: refused whole."""
        p = _game(LAG_AUTH, LAG_SCORES, [], period_at=lambda m: "Top 4th")
        assert _withheld(p) == []
        assert _down_steps(p["score_history"]) == 1

    def test_out_of_order_authority_convicts_nothing(self):
        """SYNTHETIC. ESPN's own position runs BACKWARDS across the span."""
        back = lambda m: _clock({2: 0, 3: 1}.get(m, m))  # noqa: E731
        p = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS, period_at=back)
        assert _withheld(p) == []

    def test_missing_authority(self):
        """SYNTHETIC."""
        p = _game([], LAG_SCORES, LAG_PLAYS)
        assert _withheld(p) == []
        assert len(p["score_history"]) == len(LAG_SCORES)

    def test_source_outage_around_the_reading(self):
        """SYNTHETIC. ESPN dark from minute 2 to minute 7: the reading is 150s
        from either side, outside `MAX_BRACKET_GAP_S`."""
        auth = [(0, 7, 7), (1, 7, 7), (2, 14, 7), (7, 14, 7), (8, 14, 7)]
        scores = [(0, 7, 7), (120, 14, 7), (270, 7, 7), (300, 14, 7), (480, 14, 7)]
        p = _game(auth, scores, LAG_PLAYS)
        assert _withheld(p) == []

    def test_swapped_home_away_evidence_is_no_authority(self):
        """SYNTHETIC. ESPN rows crossed against the score rows."""
        crossed = [(m, a, h) for m, h, a in LAG_AUTH]
        p = _game(crossed, LAG_SCORES, LAG_PLAYS)
        assert _withheld(p) == []

    def test_a_feed_ahead_of_the_authority_is_kept(self):
        """SYNTHETIC. 21-7 was never held by ESPN before the reading."""
        scores = [(0, 7, 7), (120, 14, 7), (150, 21, 7), (180, 14, 7), (300, 14, 7)]
        p = _game(LAG_AUTH, scores, LAG_PLAYS)
        assert _withheld(p) == []

    def test_a_live_game_is_never_touched(self):
        """SYNTHETIC. 'Never again' is a forecast until the game is over."""
        p = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS, status="live")
        assert _withheld(p) == []

    def test_a_play_list_that_stops_short_of_the_final_is_refused(self):
        """SYNTHETIC. A 'last 10' list cannot prove an empty bracket."""
        p = _game(LAG_AUTH, LAG_SCORES, [_play(0, 7, 7)])
        assert _withheld(p) == []


class TestEachRefusalIsLoadBearing:
    """SYNTHETIC. The controls above prove the rule WITHHOLDS the right reading;
    these prove each safety refusal carries its own weight.

    Written from a mutation run (live/348, `mutants.txt`): deleting the
    same-ending check, the stored-final cross-check, the orientation count or
    the `positioned` requirement each left all 29 tests green. The first two
    were covering for EACH OTHER — the one crossed fixture
    (`test_swapped_home_away_evidence_is_no_authority`) is refused by the
    same-ending check before the orientation count is ever consulted, so
    removing either ALONE changed nothing. A refusal that only holds while its
    neighbour holds is not pinned.

    Each test below satisfies every refusal except its own, so it fails the
    moment its own condition is deleted. They are the safety half of a filter
    that HIDES rows from a public chart, which is the half worth pinning.
    """

    def test_an_authority_that_stops_before_the_final_convicts_nothing(self):
        """SYNTHETIC — the same-ending check, alone. ESPN's trace ends 14-7 but
        the game finished 21-7 and the score rows say so. The authority never
        saw the end, so "never holds it again THROUGH THE FINAL" is a forecast,
        not a fact. Orientation agrees and the stored final matches the score
        rows, so nothing else here can refuse."""
        auth = [(0, 7, 7), (1, 7, 7), (2, 14, 7), (3, 14, 7), (4, 14, 7)]
        scores = [(0, 7, 7), (120, 14, 7), (150, 7, 7), (180, 14, 7), (300, 21, 7)]
        p = _game(auth, scores, [_play(2, 14, 7), _play(5, 21, 7)], final=(21, 7))
        assert _withheld(p) == []

    def test_a_stored_final_neither_series_reaches_convicts_nothing(self):
        """SYNTHETIC — the stored-final cross-check, alone. Both series agree
        with each other and end 14-7; the event row says the game finished
        21-7. They agree because they are BOTH truncated, so their agreement
        is not evidence. The same-ending check cannot see this."""
        p = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS, final=(21, 7))
        assert _withheld(p) == []

    def test_crossed_evidence_that_ends_on_a_tie_convicts_nothing(self):
        """SYNTHETIC — the orientation count, alone. The authority is recorded
        in the opposite team slots, but the game ends 7-7, so the two series
        end on the SAME tuple and the same-ending check waves it through. Only
        counting how many readings match each way catches it."""
        auth = [(0, 0, 0), (1, 0, 0), (2, 7, 14), (3, 7, 14), (4, 7, 7), (5, 7, 7)]
        scores = [(0, 0, 0), (120, 14, 7), (150, 0, 0), (180, 14, 7), (300, 7, 7)]
        p = _game(auth, scores, [_play(2, 7, 14), _play(4, 7, 7)], final=(7, 7))
        assert _withheld(p) == []

    def test_an_unpositioned_bracket_convicts_nothing(self):
        """SYNTHETIC — the `positioned` requirement, alone. The two ESPN rows
        bracketing the reading carry no readable period, so "no scoring play
        sits inside the bracket" cannot be evaluated at all. Without this the
        play check returns False for want of a bracket and reads as agreement:
        the one condition that KEEPS a reading would be silently skipped."""
        p = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS,
                  period_at=lambda m: _clock(m) if m < 2 else None)
        assert _withheld(p) == []


#: The mutation run behind the two classes around this note (live/348) ends with
#: three survivors, and each is EQUIVALENT — a mutant no test can kill because it
#: cannot change an answer. Recorded with its proof so the next reader neither
#: re-derives them nor "fixes" them with a contrived test:
#:
#:   * dropping `score not in (before[1], after[1])` — implied by `not returns`.
#:     `before` is `authority[prv]` and `after` is `authority[nxt]`, and
#:     `returns` scans `range(prv, len(authority))`, which contains both indices.
#:   * `len(authority) < 2` -> `< 1` — with one row, bracketing needs `prv >= 0`
#:     and `nxt < 1`, so `nxt` is 0 and `prv` is -1. Nothing is ever withheld.
#:     (Zero rows still returns early, so `authority[-1]` stays safe.)
#:   * dropping the countdown-LABEL check in `_countdown_position`, leaving the
#:     rank ceiling — every other branch of `live_progress_position` today ranks
#:     at 5.0 or above (an inning is `inning * 4 + state`, so 5.0 at the
#:     earliest; an overtime is `_REGULATION_PERIODS + n`) or returns None, so
#:     the ceiling already refuses all of them. The label check is fail-closed
#:     cover for a FUTURE branch that returns a low rank — the `Half` that
#:     `game_state` deliberately leaves unparseable would rank 1.0-2.0 on a
#:     clock that runs the other way. Kept on purpose, unkillable on purpose.


class TestTheBracketAndThePlaysShareOneScale:
    """SYNTHETIC. `_play_position` refuses any play outside periods 1..4, while
    `live_progress_position` happily ranks an overtime at 5.0 and a 'Top 4th'
    at 8.0. Where those disagree the bracket sits somewhere no play can ever
    land, so `play_inside` is False by CONSTRUCTION — and that check is the
    only one that KEEPS a reading. Silence from a check that cannot speak must
    not be read as agreement, so such a bracket is refused instead.

    Both shapes below are withheld if the authority is positioned with the raw
    helper, which is what made the period ceiling look untested.
    """

    def test_an_overtime_bracket_convicts_nothing(self):
        """SYNTHETIC. Overtime: the authority ranks 5.0, an overtime scoring
        play has no position at all, so no play could ever exonerate the
        reading — the rule would be strictly HARSHER in overtime, where it has
        less evidence, not more."""
        p = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS,
                  period_at=lambda m: f"{15 - m}:00 - Overtime")
        assert _withheld(p) == []

    def test_a_fifth_quarter_bracket_convicts_nothing(self):
        """SYNTHETIC. The label a feed uses for basketball overtime: it reads
        as a countdown period, so it is positioned (5.0) on the RIGHT scale —
        but `_play_position` refuses period 5, so once again no play can reach
        the bracket. This is the one shape the rank ceiling catches and the
        countdown-label check does not; the overtime and inning tests above are
        caught by either, so without this the ceiling is not pinned."""
        p = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS,
                  period_at=lambda m: f"{15 - m}:00 - 5th Quarter")
        assert _withheld(p) == []

    def test_an_inning_bracket_convicts_nothing(self):
        """SYNTHETIC. Baseball: a 'Top 4th' row ranks 8.0 on the inning scale
        while an inning-4 play ranks 4.0. The companion test above with no
        plays at all refuses on the play list; this one HAS plays and must
        still refuse, on the scale."""
        p = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS, period_at=lambda m: "Top 4th")
        assert _withheld(p) == []


class TestTheFilterDoesNotMoveTheChartsFurniture:
    """REAL. The served `score_history` is not only drawn — it is one of the
    three series `renderable_span` measures to decide which period markers sit
    under a line (#5140/CERT-1984). Withholding a reading therefore has a
    second, non-obvious reader, and a marker dropped here would look exactly
    like a period-marker regression on the same page."""

    def test_the_markers_and_the_drawn_span_are_untouched(self):
        """The assertion is a DIFFERENCE, never a transcript of the markers.

        The first cut pinned the literal list the route served at the time
        (`("1", "espn_box")` x4). #5140 landed mid-review and moved football
        onto observed transitions — `("1st Quarter", "win_prob")` x5, with a
        Halftime — so the pin reddened at the desk on a payload this filter had
        not touched. Re-deriving that list from this branch's own output would
        have made the test agree with whatever the code now does, which is how
        a pinning test quietly becomes a mirror.

        So the control is the SAME fixture served with the filter disabled.
        Whatever tier computes the markers, withholding a reading may not
        change them — which is the claim, and it survives the next tier
        change too.

        WHAT THIS ASSERTION IS AND IS NOT, measured rather than assumed. The
        marker equality is a TRIPWIRE, not a demonstration: on this fixture it
        cannot currently fire. Replacing the filter with one that withholds
        EVERY reading (49 of 49) leaves all five markers in place, as do
        dropping only the first, only the last, or all but the first. The
        reason is the one `period_markers.py` already states — the measured
        tiers take their timestamps from the very series that define the
        renderable span, so the domain guard is a no-op for them by
        construction, and `espn_history` sustains the score renderer's span on
        its own regardless of what `score_history` does. The assertion that
        carries weight here is the span one below: the withhold path needs a
        reading to be strictly bracketed by two authority rows (`prv >= 0 and
        nxt < len(authority)`), so the extremes are structurally kept. The
        equality is retained because it costs one serve and would catch a
        future tier whose markers are NOT span-derived (tier 4 `estimated` is
        exactly that shape).
        """
        import app.utils.score_history_authority as authority

        real = authority.split_superseded_score_history
        authority.split_superseded_score_history = lambda history, *a, **k: (history, [])
        try:
            _, unfiltered = _real(NFL_ID, "americanfootball_nfl")
        finally:
            authority.split_superseded_score_history = real
        _, payload = _real(NFL_ID, "americanfootball_nfl")

        assert payload["score_history_withheld"], "otherwise this passes vacuously"
        assert not unfiltered.get("score_history_withheld"), "the control must be unfiltered"
        assert payload["period_markers"], "no markers at all would pass vacuously"
        assert payload["period_markers"] == unfiltered["period_markers"]

        stored, served = _everything(payload), payload["score_history"]
        assert (served[0]["timestamp"], served[-1]["timestamp"]) == (
            stored[0]["timestamp"], stored[-1]["timestamp"]
        ), "the first and last stored readings are never withheld, so the span holds"


class TestTheStatedResidual:
    def test_two_causes_one_set_of_rows(self):
        """SYNTHETIC, and the honest limit. WORLD A: a feed 30s behind
        re-asserts 7-7. WORLD B: the TD is overturned and re-instated inside
        one ESPN minute, no new play. Both worlds store EXACTLY these rows, so
        no function of them can differ. The rule withholds; in world B that
        hides a real <=60s excursion. It is returned in
        `score_history_withheld`, never deleted — and this test exists so the
        residual is a recorded decision, not a surprise."""
        world_a = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS)
        world_b = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS)
        assert world_a["score_history"] == world_b["score_history"]
        assert _line(world_a["score_history_withheld"]) == [("00:02:30", 7, 7)]
