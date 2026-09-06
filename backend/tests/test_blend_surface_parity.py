"""UX-P003 — card == hero == chart. One blend, every surface.

Standing ruling #1: THE BLEND IS THE PRODUCT — one number per question, and the
hero and the chart must show the SAME number. This file is the backend half of
that contract; the frontend half is
`frontend/__tests__/lib/probabilityInvariant.test.ts`.

The three surfaces and where their number comes from:

  Discover card   `current_odds.home_probability`  (routes/feed.py:4592)
                  = compute_aggregate_probability(event)
  Event hero      `hero_probability`               (routes/events.py, source "blend")
                  = compute_aggregate_probability(event)
  Chart live edge last point of `aggregate_line`
                  = compute_aggregated_probability(...) → pinned by
                    _pin_blend_edge() on a live game

Card and hero were already the same function. The chart's live edge was not: the
time-series blend reads the odds-snapshot consensus history and applies staleness
decay per bucket, and it used to run an α=0.3 EMA on top. Measured against live
MLB on production 2026-08-05:

    Giants @ Rangers   card 60% vs chart 78%  → EMA +14.5 pts, residual +4.3
    Dodgers @ Cubs     card 89% vs chart 99%  → EMA  +0.6 pts, residual +10.0
    Blue Jays @ Astros card 99% vs chart 100% → EMA  +0.6 pts

Note the second row: dropping the EMA alone leaves a 10-point gap. Both halves of
the fix are load-bearing, so both are asserted here.
"""

from datetime import datetime, timezone, timedelta

import pytest

from app.routes.events import _pin_blend_edge
from app.utils.aggregation import (
    TimestampedProb,
    compute_aggregate_probability,
    compute_aggregated_probability,
)

NOW = datetime(2026, 8, 5, 18, 5, 0, tzinfo=timezone.utc)


def _event(status="live", *, home_score=None, away_score=None, completed_at=None,
           **sources):
    """An Event-shaped stand-in carrying the fields the blend reads.

    The three score/settlement fields are what ``resolve_settled_hero`` reads —
    the pin asks it before touching a non-live line, so a test that means
    "settled" has to say so with a real result, not just a terminal status.
    """
    return type("Event", (), {
        "status": status,
        "win_probability_sources": dict(sources),
        "espn_win_prob_home": None,
        "opening_home_probability": 0.5,
        "home_score": home_score,
        "away_score": away_score,
        "completed_at": completed_at,
    })()


def _line(*pairs):
    """Build an aggregate_line payload from (minutes_before_now, prob) pairs."""
    return [
        {
            "timestamp": (NOW - timedelta(minutes=m)).isoformat(),
            "home_probability": p,
        }
        for m, p in pairs
    ]


def _card_probability(event):
    """What the Discover card renders (routes/feed.py:4592)."""
    return compute_aggregate_probability(event)


def _hero_probability(event):
    """What the event hero renders (routes/events.py `hero_probability`)."""
    return compute_aggregate_probability(event, event_status=event.status)


def _chart_live_edge(line):
    """What the chart's right edge — and the web live hero — renders."""
    return line[-1]["home_probability"] if line else None


class TestLiveSurfaceParity:
    """The payoff: on a LIVE game all three surfaces reduce to one number."""

    def test_card_hero_and_chart_edge_are_identical(self):
        # The production Giants @ Rangers shape: a betting reading that carries
        # the weighted median, plus four disagreeing model/market sources.
        event = _event(
            betting=0.5956, mlb=0.582, espn=0.609, kalshi=0.375, stat_model=0.9952,
        )
        # A blend line whose last bucket has drifted well away from the blend.
        line = _line((3, 0.81), (2, 0.80), (1, 0.7837))

        _pin_blend_edge(line, event, is_live=True, now=NOW)

        card = _card_probability(event)
        hero = _hero_probability(event)
        edge = _chart_live_edge(line)

        assert card == hero == edge
        # And it is the real blend, not whatever the series happened to end on.
        assert edge == pytest.approx(0.5956)

    def test_integer_rounded_surfaces_agree(self):
        """What the user actually reads: the rounded percentage on each surface."""
        event = _event(betting=0.5205, mlb=0.987, espn=0.887, kalshi=0.995,
                       stat_model=0.999)
        line = _line((2, 0.999), (1, 0.9927))

        _pin_blend_edge(line, event, is_live=True, now=NOW)

        card = round(_card_probability(event) * 100)
        hero = round(_hero_probability(event) * 100)
        edge = round(_chart_live_edge(line) * 100)
        assert card == hero == edge

    def test_desmoothing_alone_would_not_have_closed_the_gap(self):
        """Why the pin exists — the Dodgers @ Cubs residual.

        With the EMA gone the series still ends on its own last bucket, which is
        built from different inputs than the point-in-time blend (staleness decay
        drops an hours-old sportsbook reading the card still counts at full
        weight). Un-pinned, the chart reads ~99% while the card reads ~89%.
        """
        event = _event(betting=0.5205, mlb=0.987, espn=0.887, kalshi=0.995,
                       stat_model=0.999)
        # De-smoothed series edge — betting decayed out, models dominate.
        line = _line((2, 0.999), (1, 0.987))

        unpinned_edge = _chart_live_edge(line)
        card = _card_probability(event)
        assert abs(unpinned_edge - card) > 0.05, "the residual gap this pin closes"

        _pin_blend_edge(line, event, is_live=True, now=NOW)
        assert _chart_live_edge(line) == card

    def test_pin_replaces_current_minute_rather_than_duplicating_it(self):
        event = _event(betting=0.60, espn=0.40)
        line = _line((1, 0.30), (0, 0.31))
        before = len(line)

        assert _pin_blend_edge(line, event, is_live=True, now=NOW) is True
        assert len(line) == before, "must not append a second point for this minute"
        assert _chart_live_edge(line) == _card_probability(event)

    def test_pin_appends_when_the_series_edge_is_older(self):
        event = _event(betting=0.60, espn=0.40)
        line = _line((7, 0.30))

        assert _pin_blend_edge(line, event, is_live=True, now=NOW) is True
        assert len(line) == 2
        assert line[-1]["timestamp"] == NOW.isoformat()
        assert line[-1]["home_probability"] == _card_probability(event)

    def test_history_before_the_edge_is_untouched(self):
        """Only the right edge is pinned — real movement stays honest (ruling #4).

        The series here ends a minute before `now`, so the pin appends: every
        pre-existing point, jagged swings included, must survive verbatim as a
        prefix of the returned line.
        """
        event = _event(betting=0.60, espn=0.40)
        line = _line((5, 0.10), (4, 0.90), (3, 0.20), (1, 0.55))
        original = [dict(p) for p in line]

        _pin_blend_edge(line, event, is_live=True, now=NOW)

        assert line[: len(original)] == original
        assert len(line) == len(original) + 1
        assert _chart_live_edge(line) == _card_probability(event)


class TestPreMatchSurfaceParity:
    """#3714: the same split, before first ball.

    Ben Shelton v Stefanos Tsitsipas (15305016), read on production at 22:56Z on
    2026-09-06 while the page said "Starts in 6m": hero 0.7147, ``aggregate_line``
    ending 0.725 one minute earlier, because only Polymarket wrote the last ten
    buckets. 71% headline, 73% curve, one screen. Three of the eleven drawable US
    Open lines disagreed by a rendered point at that read.

    The pre-match arm is weaker than the live one on purpose — overwrite only,
    and only while the edge is still "now" — so the two halves are asserted
    separately below.
    """

    def test_the_shelton_specimen_reconciles(self):
        event = _event(status="scheduled", betting=0.7147, polymarket=0.725)
        line = _line((2, 0.6889), (1, 0.725))

        assert _pin_blend_edge(line, event, is_live=False, now=NOW) is True

        hero = _hero_probability(event)
        assert _chart_live_edge(line) == hero
        # The number the reader sees, not just the float.
        assert round(hero * 100) == round(_chart_live_edge(line) * 100) == 71

    def test_pre_match_overwrites_and_never_appends(self):
        """#1561 inverted: a pre-match series is not carried forward to the clock,
        so inventing a "now" point would render a stale reading as a fresh one."""
        event = _event(status="scheduled", betting=0.60, espn=0.40)
        line = _line((1, 0.30))
        before = len(line)

        assert _pin_blend_edge(line, event, is_live=False, now=NOW) is True
        assert len(line) == before
        assert line[-1]["timestamp"] == (NOW - timedelta(minutes=1)).isoformat()

    def test_a_stale_pre_match_edge_is_left_alone(self):
        """Past the freshness window the chart is not contradicting anything: it
        says "at that minute it was 30%", which a hero saying "now, 50%" does not
        argue with. Pinning there would stamp today's blend onto an old minute."""
        event = _event(status="scheduled", betting=0.60, espn=0.40)
        line = _line((30, 0.30))

        assert _pin_blend_edge(line, event, is_live=False, now=NOW) is False
        assert _chart_live_edge(line) == 0.30
        assert len(line) == 1

    def test_the_window_boundary_is_the_live_price_poll(self):
        """Two minutes — one `poll_live_prediction_markets` cycle — is inside."""
        for minutes, pinned in ((2, True), (3, False)):
            event = _event(status="scheduled", betting=0.60, espn=0.40)
            line = _line((minutes, 0.30))
            assert _pin_blend_edge(line, event, is_live=False, now=NOW) is pinned

    def test_history_before_a_pinned_pre_match_edge_survives(self):
        event = _event(status="scheduled", betting=0.60, espn=0.40)
        line = _line((9, 0.10), (5, 0.90), (1, 0.30))
        original = [dict(p) for p in line[:-1]]

        _pin_blend_edge(line, event, is_live=False, now=NOW)

        assert line[:-1] == original


class TestSettledLinesStayOut:
    """The right edge of a settled row has two other owners, and they disagree
    about which rows they hold — so the pin asks both before standing down."""

    def test_finished_line_is_not_pinned(self):
        """A settled game's chart converges to the resolved winner (ruling #2),
        which the terminal-point injection owns — the pin must stay out of it."""
        event = _event(
            status="completed",
            home_score=7,
            away_score=0,
            completed_at=NOW - timedelta(minutes=20),
            betting=0.60,
            espn=0.40,
        )
        line = _line((1, 1.0))
        assert (
            _pin_blend_edge(line, event, is_live=False, is_finished=True, now=NOW)
            is False
        )
        assert _chart_live_edge(line) == 1.0

    def test_terminal_scores_without_a_completed_at_still_stand_down(self):
        """`is_finished` holds this row and `resolve_settled_hero` does not (it
        requires completed_at). The terminal injection is about to append the
        resolved point; overwriting the bucket underneath it is not the pin's
        business."""
        event = _event(
            status="completed", home_score=7, away_score=0, betting=0.60, espn=0.40
        )
        line = _line((1, 0.93))
        assert (
            _pin_blend_edge(line, event, is_live=False, is_finished=True, now=NOW)
            is False
        )
        assert _chart_live_edge(line) == 0.93

    def test_a_settled_hero_over_a_future_commence_still_stands_down(self):
        """The mirror row: status `completed` with a commence_time still in the
        future is corrupt (gotcha #32 family), so `_event_is_really_finished` says
        NOT finished and the chart renders live — but the hero resolves it to a
        winner. Pinning to the blend would put 60% under a 100% headline."""
        event = _event(
            status="completed",
            home_score=3,
            away_score=0,
            completed_at=NOW - timedelta(hours=2),
            betting=0.60,
            espn=0.40,
        )
        line = _line((1, 0.93))
        assert (
            _pin_blend_edge(line, event, is_live=False, is_finished=False, now=NOW)
            is False
        )
        assert _chart_live_edge(line) == 0.93


class TestNonLiveUnaffected:
    """The remaining stand-down arms, live and pre-match alike."""

    def test_empty_line_is_left_empty(self):
        """No blend line → the frontend falls back to hero_probability, which is
        the same number anyway. The pin must not invent a one-point chart."""
        event = _event(betting=0.60, espn=0.40)
        line = []
        assert _pin_blend_edge(line, event, is_live=True, now=NOW) is False
        assert line == []

    def test_no_sources_means_no_pin(self):
        event = _event()
        event.opening_home_probability = None
        line = _line((1, 0.30))
        assert _pin_blend_edge(line, event, is_live=True, now=NOW) is False
        assert _chart_live_edge(line) == 0.30


class TestNoSmoothingOnTheDisplayedLine:
    """Ruling #4 — the EMA that de-synced the surfaces must not come back."""

    def test_flat_fresh_series_reports_its_sources_exactly(self):
        current = {"betting": 0.57, "espn": 0.20, "mlb": 0.20, "stat_model": 0.20}
        series = {
            src: [
                TimestampedProb(timestamp=NOW - timedelta(seconds=s),
                                home_probability=val)
                for s in (120, 60, 0)
            ]
            for src, val in current.items()
        }
        line = compute_aggregated_probability(series, bucket_seconds=60)
        assert line
        assert line[-1].home_probability == pytest.approx(
            compute_aggregate_probability(_event(**current))
        )

    def test_a_real_move_reaches_the_edge_in_one_bucket(self):
        """An EMA would need several buckets to get there; that lag WAS the bug."""
        series = {
            "betting": [
                TimestampedProb(timestamp=NOW - timedelta(seconds=s),
                                home_probability=p)
                for s, p in ((180, 0.20), (120, 0.20), (60, 0.20), (0, 0.90))
            ]
        }
        line = compute_aggregated_probability(series, bucket_seconds=60)
        assert line[-1].home_probability == pytest.approx(0.90)
