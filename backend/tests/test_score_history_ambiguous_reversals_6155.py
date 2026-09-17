"""#6155 — a completed game's score line draws EVERY stored reading, including
the ones that step it down, because nothing this system stores can tell a stale
reading from a real reversal.

PILLAR: TRUTH. SHIP: score charts retain legitimate score reversals when the
saved evidence cannot distinguish them from stale readings.

## Why this file replaces a filter rather than tuning one

For twelve hours the route ran a serve-time suppressor. It withheld a reading
only when an independent positioned ESPN trace showed the event was completed,
the two series ended together, observations bracketed the reading tightly on
both sides, the authority had held exactly that score EARLIER and never returned
to it, and no scoring play sat inside the bracket. That is a careful rule and it
was still wrong, for a reason its own residual test admitted:

    a ruling overturned and re-instated between two authority samples produces
    BYTE-IDENTICAL stored rows to a feed lagging by the same interval.

An overturn is a score DECREASE that creates no scoring-play row. The only
positioned ledger this system has — ESPN's box-score plays — records increases
only. So the competing explanation leaves no trace anywhere, by construction,
and "the authority never returns to this value" is precisely the signature an
unobserved transient excursion would leave. The filter's firing condition WAS
the ambiguity.

`TestTheEvidenceCannotSeparateTheTwoCauses` is the measurement, not an argument:
replaying the removed predicate over the real specimen, **10 of the 11 rows it
withheld sat inside a bracket where the authority read the SAME score on both
sides** — it observed no change at all across the window it convicted on.

So there is no disproved subset to keep the filter for, and narrowing it would
be inventing confidence. It is removed. If a future observation carries
per-reading provenance, or a ledger that records reversals, the discriminator
becomes buildable and this file is the specification it must satisfy.

## The trade, stated plainly

Drawing a stale reading shows a dip that did not happen. Hiding a real one
deletes a correction that did. The second is worse and it is silent, so the
route fails OPEN.

Two kinds of input, never mixed:

  * REAL — `fixtures/score_history_6155/history_<id>.json`, the public
    `/api/events/<id>/history` payload fetched 2026-09-17T04:46:56Z, sanitized
    (provenance inside each file). `espn_history` there is OUR ingest of ESPN,
    not a fresh provider read.
  * SYNTHETIC — built by `_game()`. Every such test says SYNTHETIC in its
    docstring. They prove what the ROUTE does with a shape; they prove nothing
    about what any provider ever sent.

Everything here drives the REAL route, `get_event_odds_history`, through the
#6390/#6462 rig.
"""

from __future__ import annotations

import asyncio
import json
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.models import ESPNSnapshot, Event, ScoreSnapshot, Sport
from tests.test_price_table_fold_6390 import _HistoryResult, _HistoryRouteSession

FIXTURES = Path(__file__).parent / "fixtures" / "score_history_6155"
NFL_ID, MLB_ID = 14637256, 15311156
KICKOFF = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)

#: The 11 readings the removed suppressor hid on the named trace, by wall clock.
#: Every one of them must now be drawn.
FORMERLY_WITHHELD = [
    ("00:41:41", 0, 0),
    ("00:43:07", 0, 0),
    ("01:21:45", 7, 0),
    ("01:23:07", 7, 0),
    ("02:20:07", 14, 7),
    ("02:20:43", 20, 7),
    ("02:22:07", 20, 7),
    ("02:34:08", 21, 7),
    ("02:59:09", 21, 14),
    ("03:12:09", 28, 14),
    ("03:13:09", 28, 14),
]


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


# ─── REAL: the named trace draws everything it stores ─────────────────────────


class TestTheNamedTraceKeepsEveryStoredReading:
    def test_all_49_stored_readings_are_drawn_with_all_20_down_steps(self):
        """REAL. The issue's own subject. The stored line has 49 rows and 20
        downward steps; every one of them reaches the chart."""
        fx, payload = _real(NFL_ID, "americanfootball_nfl")
        assert len(fx["score_history"]) == 49
        assert _line(payload["score_history"]) == _line(fx["score_history"])
        assert _down_steps(payload["score_history"]) == 20

    def test_the_eleven_formerly_withheld_readings_are_all_drawn(self):
        """REAL. Named one by one rather than counted, so a future filter that
        hides a DIFFERENT eleven cannot pass this."""
        _, payload = _real(NFL_ID, "americanfootball_nfl")
        drawn = _line(payload["score_history"])
        for reading in FORMERLY_WITHHELD:
            assert reading in drawn, f"{reading} was suppressed again"

    def test_the_route_serves_no_withheld_key_at_all(self):
        """REAL. The removed filter returned hidden rows in
        `score_history_withheld`. No client ever read it, which is exactly why
        returning them there did not make the chart truthful. The key is gone —
        if it comes back, something is hiding rows again."""
        _, payload = _real(NFL_ID, "americanfootball_nfl")
        assert "score_history_withheld" not in payload

    def test_the_mlb_specimen_is_unchanged_and_still_uncorrected(self):
        """REAL. 15311156 keeps all 15 of its down steps. MLB was ~93% of the
        symptom count and no filter ever touched it; it is not fixed by this
        change and is not claimed to be."""
        fx, payload = _real(MLB_ID, "baseball_mlb")
        assert fx["scoring_plays"] == []
        assert _down_steps(payload["score_history"]) == 15
        assert _line(payload["score_history"]) == _line(fx["score_history"])


# ─── SYNTHETIC ────────────────────────────────────────────────────────────────


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


#: The shape the removed filter convicted: the feed re-asserts 7-7 at 02:30
#: while the authority has been on 14-7 since minute 2 and never goes back.
LAG_AUTH = [(0, 7, 7), (1, 7, 7), (2, 14, 7), (3, 14, 7), (4, 14, 7), (5, 14, 7)]
LAG_SCORES = [(0, 7, 7), (120, 14, 7), (150, 7, 7), (180, 14, 7), (300, 14, 7)]
LAG_PLAYS = [_play(2, 14, 7)]


class TestTheAmbiguousReadingStaysOnTheChart:
    """The control this correction exists for."""

    def test_the_two_indistinguishable_worlds_both_keep_the_reading_visible(self):
        """SYNTHETIC, and the whole point.

        WORLD A: a feed 30s behind re-asserts 7-7 after the touchdown.
        WORLD B: the touchdown is overturned at 02:30 and re-instated before the
        next authority sample — a REAL excursion, no new scoring play, because
        re-instating a play does not create one.

        Both worlds store exactly these rows, so no function of them can tell
        the two apart. The old rule withheld here, which in world B silently
        deleted a real correction. Now the reading is DRAWN in both."""
        world_a = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS)
        world_b = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS)
        assert world_a["score_history"] == world_b["score_history"]
        assert ("00:02:30", 7, 7) in _line(world_a["score_history"])
        assert _down_steps(world_a["score_history"]) == 1

    def test_a_reading_the_authority_contradicts_on_both_sides_is_still_drawn(self):
        """SYNTHETIC. The tightest case the old rule had: the authority sits on
        14-7 either side of the reading, one minute apart, with no play between.
        That is the strongest evidence available and it is still not enough —
        it cannot see a 30-second overturn between its own samples."""
        p = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS)
        assert ("00:02:30", 7, 7) in _line(p["score_history"])

    def test_an_overturned_touchdown_that_persists_is_drawn_going_down(self):
        """SYNTHETIC. The case that always worked, kept so the correction is
        not confused with a regression: 14-7 -> 7-7 and it stays."""
        auth = [(0, 7, 7), (1, 14, 7), (2, 14, 7), (3, 7, 7), (4, 7, 7), (5, 7, 7)]
        scores = [(0, 7, 7), (60, 14, 7), (150, 7, 7), (180, 7, 7), (300, 7, 7)]
        p = _game(auth, scores, [_play(1, 7, 7)])
        assert _down_steps(p["score_history"]) == 1

    def test_a_correction_later_reversed_keeps_both_moves(self):
        """SYNTHETIC. 14-7 -> 7-7 -> 14-7: both moves drawn."""
        auth = [(0, 7, 7), (1, 14, 7), (2, 7, 7), (3, 7, 7), (4, 14, 7), (5, 14, 7)]
        scores = [(0, 7, 7), (60, 14, 7), (120, 7, 7), (150, 14, 7), (180, 7, 7),
                  (240, 14, 7), (300, 14, 7)]
        p = _game(auth, scores, [_play(1, 14, 7)])
        assert _down_steps(p["score_history"]) == 2

    def test_a_live_game_draws_everything_too(self):
        """SYNTHETIC. The old rule only ran on completed events, so a filter
        re-introduced for live games would slip past the controls above."""
        p = _game(LAG_AUTH, LAG_SCORES, LAG_PLAYS, status="in_progress")
        assert ("00:02:30", 7, 7) in _line(p["score_history"])


class TestTheEvidenceCannotSeparateTheTwoCauses:
    """The measurement behind the removal, replayed over the real specimen so it
    is a result and not a claim."""

    def test_ten_of_the_eleven_sat_in_a_bracket_the_authority_saw_no_change_in(self):
        """REAL. Reconstructs, for each formerly-withheld reading, the two
        authority observations that bracketed it. For 10 of 11 the authority
        read the SAME score on both sides: it observed no change whatsoever
        across the window on whose strength the reading was convicted. In those
        windows a real overturn-and-reinstate and a lagging feed are the same
        stored bytes, so no per-row disproof exists and there is no subset the
        filter could have been narrowed to."""
        fx, _ = _real(NFL_ID, "americanfootball_nfl")
        auth = sorted(
            (datetime.fromisoformat(p["timestamp"]), (p["home_score"], p["away_score"]))
            for p in fx["espn_history"]
            if isinstance(p.get("home_score"), int) and isinstance(p.get("away_score"), int)
        )
        times = [t for t, _s in auth]
        steady = 0
        for stamp, _h, _a in FORMERLY_WITHHELD:
            row = next(p for p in fx["score_history"] if p["timestamp"][11:19] == stamp)
            nxt = bisect_right(times, datetime.fromisoformat(row["timestamp"]))
            assert 0 < nxt < len(auth), f"{stamp} is not bracketed"
            if auth[nxt - 1][1] == auth[nxt][1]:
                steady += 1
        assert steady == 10, f"expected 10 steady brackets, measured {steady}"

    def test_the_scoring_play_ledger_records_no_reversal_on_the_named_trace(self):
        """REAL. The reason the ambiguity has no fix with today's inputs: the
        only positioned ledger is monotonic. Every scoring play on the named
        trace moves the score UP, so a reversal can never appear in it, and
        'no play inside the bracket' can never mean 'no reversal happened'."""
        fx, _ = _real(NFL_ID, "americanfootball_nfl")
        totals = [
            (p["home_score"] or 0, p["away_score"] or 0) for p in fx["scoring_plays"]
        ]
        assert len(totals) == 7, "the ledger must be whole or this says nothing"
        assert all(
            b[0] >= a[0] and b[1] >= a[1] for a, b in zip(totals, totals[1:])
        ), "a decreasing scoring play would BE the missing discriminator"


class TestTheChartsFurnitureIsUnaffected:
    def test_markers_span_and_final_result_match_the_stored_trace(self):
        """REAL. Removing the filter must move the score line and NOTHING else.
        The drawn span runs the full stored extent, the four period markers keep
        the positions #5140/#6718 give them, and the line still ends on the
        stored final score. Marker timestamps are pinned as literals because
        `score_history` and the markers are both derived in this route — a
        change that let one disturb the other would otherwise pass unseen."""
        fx, payload = _real(NFL_ID, "americanfootball_nfl")
        stored = fx["score_history"]
        assert (payload["score_history"][0]["timestamp"],
                payload["score_history"][-1]["timestamp"]) == (
            stored[0]["timestamp"], stored[-1]["timestamp"])
        assert [(m["period"], m["timestamp"][11:19]) for m in payload["period_markers"]] == [
            ("2nd Quarter", "00:58:35"),
            ("Halftime", "01:54:35"),
            ("3rd Quarter", "02:09:35"),
            ("4th Quarter", "02:42:36"),
        ]
        assert (payload["score_history"][-1]["home_score"],
                payload["score_history"][-1]["away_score"]) == tuple(fx["final_score"])


class TestNoSuppressorIsReintroduced:
    def test_the_removed_helper_module_is_gone(self):
        """The filter's machinery was persuasive enough to ship once. If it
        returns as an importable helper, this fails and whoever revives it has
        to argue with the measurement above first."""
        import importlib.util

        assert importlib.util.find_spec("app.utils.score_history_authority") is None
