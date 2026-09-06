"""Guards for period-marker provenance and the domain guard (#3348).

The class of bug: `period_markers` served a chip the chart could not place —
either past the end of the drawn line (worst measured: 36 hours), to the left of
the only point on it, or over a chart with no line at all — and every tier looked
identical, so no client could tell an observed period from arithmetic on the
scheduled kickoff.

Every timestamp below is copied from a real production payload fetched
2026-09-05; the event ids are in the docstrings so the cases stay checkable.

The tests run BOTH directions on purpose. It is easy to write a guard that drops
the bad markers by dropping nearly everything, so the control tests
(`TestGuardIsANoOpOnHealthyData`) pin that measured markers and a healthy
estimated set survive untouched.

CERT-1984 found the first cut of this guard defining a span from timestamps
alone, which is a different question from "is there a line here" on a payload
production actually serves. `TestATimestampIsNotALine` and
`TestTheScoreChartIsALineToo` are the two shapes it named; the route-level
versions of both are in `tests/test_events_history_period_markers.py`, because a
utility test cannot prove what the endpoint assembles.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.period_markers import (
    MEASURED_SOURCES,
    PROBABILITY_KEYS,
    SCORE_KEYS,
    SOURCE_ESPN_BOX,
    SOURCE_ESTIMATED,
    SOURCE_STATPAL,
    SOURCE_WIN_PROB,
    drop_markers_off_every_line,
    estimated_period_markers,
    extend_span_to,
    renderable_span,
)


def _pt(ts: str, **values) -> dict:
    """A point ON the win-probability line.

    The probability is explicit and non-null because that is what makes it a
    point the chart draws. A bare `{"timestamp": ...}` is a different animal —
    see `TestATimestampIsNotALine`, which builds those on purpose.
    """
    return {"timestamp": ts, "home_probability": 0.55, **values}


def _score_pt(ts: str, home: int = 2, away: int = 1) -> dict:
    """A point on the score-differential line and NOT on the probability one."""
    return {"timestamp": ts, "home_score": home, "away_score": away}


def _marker(ts: str, period: str = "1H", source: str = SOURCE_ESTIMATED) -> dict:
    return {"timestamp": ts, "period": period, "source": source}


def _prob_span(*series):
    """The win-probability renderer's span, exactly as `routes/events.py` asks."""
    return renderable_span(*((points, PROBABILITY_KEYS) for points in series))


def _score_span(*series):
    """The score-differential renderer's span, ditto."""
    return renderable_span(*((points, SCORE_KEYS) for points in series))


class TestRenderableSpan:
    def test_spans_every_series_the_chart_draws(self):
        lo, hi = _prob_span(
            [_pt("2026-08-30T12:00:00+00:00")],           # history
            [_pt("2026-08-30T09:00:00+00:00")],           # espn_history
            [_pt("2026-08-30T15:00:00+00:00")],           # aggregate_line
            [_pt("2026-08-30T11:00:00+00:00")],           # a win_prob source
        )
        assert lo == datetime(2026, 8, 30, 9, tzinfo=timezone.utc)
        assert hi == datetime(2026, 8, 30, 15, tzinfo=timezone.utc)

    def test_no_series_at_all_is_no_span_not_an_unbounded_one(self):
        """(None, None) must mean "there is no line", never "no bound"."""
        assert _prob_span(None, [], {}.values() and []) == (None, None)

    def test_ignores_unparseable_points_without_losing_the_rest(self):
        lo, hi = _prob_span(
            [_pt("not-a-timestamp"), _pt("2026-08-30T12:00:00+00:00"), {}]
        )
        assert lo == hi == datetime(2026, 8, 30, 12, tzinfo=timezone.utc)

    def test_accepts_a_trailing_z(self):
        lo, _ = _prob_span([_pt("2026-08-30T12:00:00Z")])
        assert lo == datetime(2026, 8, 30, 12, tzinfo=timezone.utc)


class TestProductionCasesDrop:
    """The three payloads that motivated the guard. All fetched 2026-09-05."""

    def test_event_15292946_chips_36_hours_past_the_end_of_the_line(self):
        """Londrina v Juventude: books stopped quoting 08-28, kickoff was 08-29.

        Six history points ending 2026-08-28T03:35. Both estimated chips sit
        ~2,172 minutes past the last point, over empty axis.
        """
        history = [
            _pt("2026-08-26T12:37:00+00:00"),
            _pt("2026-08-26T17:05:00+00:00"),
            _pt("2026-08-26T21:05:00+00:00"),
            _pt("2026-08-27T10:05:00+00:00"),
            _pt("2026-08-27T14:35:00+00:00"),
            _pt("2026-08-28T03:35:00+00:00"),
        ]
        markers = [
            _marker("2026-08-29T15:00:00+00:00", "1H"),
            _marker("2026-08-29T15:47:00+00:00", "2H"),
        ]
        lo, hi = _prob_span(history)
        assert drop_markers_off_every_line(markers, [(lo, hi)]) == []

    def test_event_15297176_chips_left_of_the_only_point_on_the_chart(self):
        """Atalanta v Cagliari: one Polymarket tick, both chips before it.

        This is the `before_start` half — 10 of native/029's 70-event cohort,
        more common than the `past_end` case #3348 headlines. A guard that
        bounded only the late end would leave both of these drawing.
        """
        win_prob = [_pt("2026-08-30T06:00:41.965351+00:00")]
        markers = [
            _marker("2026-08-30T05:00:25+00:00", "1H"),
            _marker("2026-08-30T05:47:25+00:00", "2H"),
        ]
        lo, hi = _prob_span(win_prob)
        assert drop_markers_off_every_line(markers, [(lo, hi)]) == []

    def test_event_15298122_no_line_at_all_places_no_marker(self):
        """Ajax v Union SG: every series empty, two chips served anyway.

        56% of the cohort (39/70). A chart with no line cannot place a boundary
        on it, so the honest answer is no markers.
        """
        markers = [
            _marker("2026-08-30T17:50:00.260799+00:00", "1H"),
            _marker("2026-08-30T18:37:00.260799+00:00", "2H"),
        ]
        lo, hi = _prob_span([], None)
        assert (lo, hi) == (None, None)
        assert drop_markers_off_every_line(markers, [(lo, hi)]) == []

    def test_a_partially_off_line_set_keeps_only_what_lands(self):
        """Event 15291077: one marker inside, one 36 minutes past the end."""
        history = [
            _pt("2026-08-29T10:00:00+00:00"),
            _pt("2026-08-29T12:00:00+00:00"),
        ]
        inside = _marker("2026-08-29T11:00:00+00:00", "1H")
        past = _marker("2026-08-29T12:36:00+00:00", "2H")
        lo, hi = _prob_span(history)
        assert drop_markers_off_every_line([inside, past], [(lo, hi)]) == [inside]


class TestATimestampIsNotALine:
    """CERT-1984, finding 1. The first cut spanned timestamps, and production
    serves timestamped rows that draw nothing."""

    def test_null_only_probability_history_is_no_line(self):
        """`routes/events.py` appends a `history` row per odds bucket whether or
        not `aggregate_bookmaker_odds()` found a probability. Six rows, six
        timestamps, zero ink — spanning them keeps the chip that #3348 is about.
        """
        history = [
            {"timestamp": "2026-08-30T18:00:00+00:00", "home_probability": None,
             "away_probability": None},
            {"timestamp": "2026-08-30T19:00:00+00:00", "home_probability": None,
             "away_probability": None},
        ]
        assert _prob_span(history) == (None, None)
        marker = _marker("2026-08-30T18:30:00+00:00")   # squarely between them
        assert drop_markers_off_every_line([marker], [_prob_span(history)]) == []

    def test_one_real_value_among_nulls_bounds_the_line_at_that_value(self):
        """Not all-or-nothing: the span starts where the ink starts. A chip in
        the null-only run BEFORE the first real point is still off the line."""
        history = [
            {"timestamp": "2026-08-30T18:00:00+00:00", "home_probability": None},
            {"timestamp": "2026-08-30T19:00:00+00:00", "home_probability": 0.61},
            {"timestamp": "2026-08-30T20:00:00+00:00", "home_probability": None},
        ]
        lo, hi = _prob_span(history)
        assert lo == hi == datetime(2026, 8, 30, 19, tzinfo=timezone.utc)
        before = _marker("2026-08-30T18:30:00+00:00")
        on = _marker("2026-08-30T19:00:00+00:00", source=SOURCE_STATPAL)
        assert drop_markers_off_every_line([before, on], [(lo, hi)]) == [on]

    def test_a_draw_only_soccer_source_is_still_a_line(self):
        """A soccer win-prob source can carry only the draw leg. That plots, so
        it counts — the value check must not narrow to the home key."""
        points = [{"timestamp": "2026-08-30T19:00:00+00:00",
                   "home_probability": None, "draw_probability": 0.28}]
        assert _prob_span(points) != (None, None)

    def test_a_zero_probability_is_a_value_not_an_absence(self):
        """0.0 is a real, drawable probability. A falsiness check instead of a
        None check would read a settled 0% as no line and drop good markers."""
        points = [{"timestamp": "2026-08-30T19:00:00+00:00",
                   "home_probability": 0.0, "away_probability": 1.0}]
        assert _prob_span(points) != (None, None)


class TestTheScoreChartIsALineToo:
    """CERT-1984, finding 2. One `period_markers` array feeds two renderers, and
    the first cut only measured one of them."""

    def test_score_only_history_keeps_its_measured_marker(self):
        """`score_history` is a real line drawn by ScoreDifferentialChart. An
        event with scores but no probabilities must not lose a measured inning.
        """
        score_history = [
            _score_pt("2026-08-30T18:00:00+00:00", 0, 0),
            _score_pt("2026-08-30T20:00:00+00:00", 4, 2),
        ]
        marker = _marker("2026-08-30T19:00:00+00:00", "Top 5th", SOURCE_STATPAL)
        prob_span = _prob_span([])                      # no probability line
        score_span = _score_span(score_history)
        assert prob_span == (None, None)
        assert drop_markers_off_every_line(
            [marker], [prob_span, score_span]
        ) == [marker]

    def test_a_marker_on_neither_line_still_drops(self):
        """The control for the clause above: adding a second span must widen the
        guard, not disable it."""
        score_history = [_score_pt("2026-08-30T18:00:00+00:00")]
        far = _marker("2026-09-01T18:00:00+00:00", "Top 5th", SOURCE_STATPAL)
        assert drop_markers_off_every_line(
            [far], [_prob_span([]), _score_span(score_history)]
        ) == []

    def test_two_disjoint_lines_do_not_manufacture_a_middle(self):
        """Membership is per span, never the min/max of both. A probability line
        on Monday and a score line on Wednesday leave Tuesday undrawn."""
        prob_span = _prob_span([_pt("2026-08-31T12:00:00+00:00")])
        score_span = _score_span([_score_pt("2026-09-02T12:00:00+00:00")])
        tuesday = _marker("2026-09-01T12:00:00+00:00")
        assert drop_markers_off_every_line(
            [tuesday], [prob_span, score_span]
        ) == []

    def test_projected_scores_in_history_are_a_score_line(self):
        """The score chart's primary series is `history.projected_*`, which lives
        on the same rows as the probabilities and can outlive them."""
        history = [
            {"timestamp": "2026-08-30T18:00:00+00:00", "home_probability": None,
             "projected_home_score": 24.5, "projected_away_score": 21.0},
        ]
        assert _prob_span(history) == (None, None)
        assert _score_span(history) != (None, None)


class TestExtendSpanToNow:
    def test_a_live_chart_reaches_the_present(self):
        now = datetime(2026, 8, 30, 20, tzinfo=timezone.utc)
        span = _prob_span([_pt("2026-08-30T19:00:00+00:00")])
        assert extend_span_to(span, now)[1] == now

    def test_it_never_moves_the_early_end_backwards(self):
        """`now` widens the late end only — it is not a second lower bound."""
        now = datetime(2026, 8, 30, 20, tzinfo=timezone.utc)
        span = _prob_span([_pt("2026-08-30T19:00:00+00:00")])
        assert extend_span_to(span, now)[0] == span[0]

    def test_an_empty_span_does_not_acquire_a_line_from_the_clock(self):
        """The bug this exists to prevent: a chart with no ink must not become
        drawable because time passed."""
        now = datetime(2026, 8, 30, 20, tzinfo=timezone.utc)
        assert extend_span_to((None, None), now) == (None, None)
        assert drop_markers_off_every_line(
            [_marker("2026-08-30T19:50:00+00:00")],
            [extend_span_to(_prob_span([]), now)],
        ) == []


class TestGuardIsANoOpOnHealthyData:
    """The control. A guard that drops the bad chips by dropping everything is
    not a fix, so pin that the good cases survive."""

    def test_measured_markers_derived_from_the_series_all_survive(self):
        """Tiers 1-3 read their timestamps off the very series that define the
        span, so the guard is a no-op for them by construction."""
        points = [
            _pt("2026-08-30T18:00:00+00:00"),
            _pt("2026-08-30T18:45:00+00:00"),
            _pt("2026-08-30T19:30:00+00:00"),
        ]
        markers = [
            _marker("2026-08-30T18:00:00+00:00", "1st Quarter", SOURCE_WIN_PROB),
            _marker("2026-08-30T18:45:00+00:00", "2nd Quarter", SOURCE_ESPN_BOX),
            _marker("2026-08-30T19:30:00+00:00", "3rd Quarter", SOURCE_STATPAL),
        ]
        lo, hi = _prob_span(points)
        assert drop_markers_off_every_line(markers, [(lo, hi)]) == markers

    def test_a_healthy_estimated_set_survives(self):
        """On a normal event the odds line spans days either side of kickoff
        (the in-domain cohort measures 7-13 day spans), so commence_time and its
        offsets sit comfortably inside."""
        history = [
            _pt("2026-08-23T00:00:00+00:00"),   # a week before kickoff
            _pt("2026-08-30T22:00:00+00:00"),   # hours after the whistle
        ]
        markers = estimated_period_markers(
            "soccer_epl", datetime(2026, 8, 30, 19, 0, tzinfo=timezone.utc)
        )
        lo, hi = _prob_span(history)
        assert drop_markers_off_every_line(markers, [(lo, hi)]) == markers

    def test_a_live_chart_is_drawn_to_now_so_a_present_marker_is_kept(self):
        """The route widens `hi` to now for an unfinished event. Without that a
        marker later than the last banked snapshot would be dropped off a live
        chart that is in fact drawn out to the present."""
        now = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)
        history = [_pt("2026-08-30T19:00:00+00:00")]
        marker = _marker("2026-08-30T19:50:00+00:00", "2H", SOURCE_STATPAL)
        lo, hi = _prob_span(history)
        assert drop_markers_off_every_line([marker], [(lo, hi)]) == []       # without
        assert drop_markers_off_every_line([marker], [extend_span_to((lo, hi), now)]) == [marker]


class TestBoundaryHandling:
    def test_the_minute_bucket_tolerance_keeps_an_edge_marker(self):
        """`history` truncates timestamps to the minute, so a marker may sit a
        few seconds outside a bucket boundary it genuinely belongs to."""
        history = [_pt("2026-08-30T19:00:00+00:00")]
        lo, hi = _prob_span(history)
        edge = _marker("2026-08-30T19:00:30+00:00")
        assert drop_markers_off_every_line([edge], [(lo, hi)]) == [edge]

    def test_the_tolerance_is_far_too_small_to_admit_a_real_defect(self):
        """The closest measured miss is 11 minutes; the tolerance is 1."""
        history = [_pt("2026-08-30T19:00:00+00:00")]
        lo, hi = _prob_span(history)
        near_miss = _marker("2026-08-30T19:11:00+00:00")
        assert drop_markers_off_every_line([near_miss], [(lo, hi)]) == []

    def test_an_unplaceable_marker_is_dropped(self):
        history = [_pt("2026-08-30T19:00:00+00:00")]
        lo, hi = _prob_span(history)
        assert drop_markers_off_every_line([{"period": "1H"}], [(lo, hi)]) == []
        assert drop_markers_off_every_line([_marker("garbage")], [(lo, hi)]) == []

    def test_an_empty_marker_list_stays_empty(self):
        assert drop_markers_off_every_line([], [(None, None)]) == []


class TestEstimatedMarkerProvenance:
    @pytest.mark.parametrize(
        "sport_key,expected_periods",
        [
            ("soccer_epl", ["1H", "2H"]),
            ("aussierules_afl", ["1st Quarter", "2nd Quarter", "3rd Quarter", "4th Quarter"]),
            ("basketball_nba", ["1st Quarter", "2nd Quarter", "3rd Quarter", "4th Quarter"]),
            ("basketball_ncaab", ["1st Half", "2nd Half"]),
            ("basketball_wncaab", ["1st Half", "2nd Half"]),
            ("americanfootball_nfl", ["1st Quarter", "2nd Quarter", "3rd Quarter", "4th Quarter"]),
            ("icehockey_nhl", ["1st Period", "2nd Period", "3rd Period"]),
        ],
    )
    def test_every_estimated_marker_is_tagged_as_an_estimate(
        self, sport_key, expected_periods
    ):
        ct = datetime(2026, 8, 30, 19, 0, tzinfo=timezone.utc)
        markers = estimated_period_markers(sport_key, ct)
        assert [m["period"] for m in markers] == expected_periods
        assert {m["source"] for m in markers} == {SOURCE_ESTIMATED}
        assert not {m["source"] for m in markers} & MEASURED_SOURCES

    def test_the_first_estimated_marker_sits_on_commence_time(self):
        ct = datetime(2026, 8, 30, 19, 0, tzinfo=timezone.utc)
        assert estimated_period_markers("soccer_epl", ct)[0]["timestamp"] == ct.isoformat()

    def test_offsets_are_preserved_from_the_shipped_table(self):
        """The estimates are unchanged by the refactor — only tagged."""
        ct = datetime(2026, 8, 30, 19, 0, tzinfo=timezone.utc)
        soccer = estimated_period_markers("soccer_epl", ct)
        assert soccer[1]["timestamp"] == (ct + timedelta(minutes=47)).isoformat()
        nfl = estimated_period_markers("americanfootball_nfl", ct)
        assert [m["timestamp"] for m in nfl] == [
            (ct + timedelta(minutes=o)).isoformat() for o in (0, 45, 110, 155)
        ]

    @pytest.mark.parametrize(
        "sport_key", ["tennis_atp_us_open", "golf_pga", "cricket_ipl", "mma_mixed_martial_arts", ""]
    )
    def test_a_sport_with_no_fixed_period_structure_invents_nothing(self, sport_key):
        ct = datetime(2026, 8, 30, 19, 0, tzinfo=timezone.utc)
        assert estimated_period_markers(sport_key, ct) == []

    def test_no_commence_time_invents_nothing(self):
        assert estimated_period_markers("soccer_epl", None) == []
