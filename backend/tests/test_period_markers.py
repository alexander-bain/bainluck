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
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.period_markers import (
    MEASURED_SOURCES,
    SOURCE_ESPN_BOX,
    SOURCE_ESTIMATED,
    SOURCE_STATPAL,
    SOURCE_WIN_PROB,
    drop_markers_outside_span,
    estimated_period_markers,
    series_span,
)


def _pt(ts: str) -> dict:
    return {"timestamp": ts}


def _marker(ts: str, period: str = "1H", source: str = SOURCE_ESTIMATED) -> dict:
    return {"timestamp": ts, "period": period, "source": source}


class TestSeriesSpan:
    def test_spans_every_series_the_chart_draws(self):
        lo, hi = series_span(
            [_pt("2026-08-30T12:00:00+00:00")],           # history
            [_pt("2026-08-30T09:00:00+00:00")],           # espn_history
            [_pt("2026-08-30T15:00:00+00:00")],           # aggregate_line
            [_pt("2026-08-30T11:00:00+00:00")],           # a win_prob source
        )
        assert lo == datetime(2026, 8, 30, 9, tzinfo=timezone.utc)
        assert hi == datetime(2026, 8, 30, 15, tzinfo=timezone.utc)

    def test_no_series_at_all_is_no_span_not_an_unbounded_one(self):
        """(None, None) must mean "there is no line", never "no bound"."""
        assert series_span(None, [], {}.values() and []) == (None, None)

    def test_ignores_unparseable_points_without_losing_the_rest(self):
        lo, hi = series_span(
            [_pt("not-a-timestamp"), _pt("2026-08-30T12:00:00+00:00"), {}]
        )
        assert lo == hi == datetime(2026, 8, 30, 12, tzinfo=timezone.utc)

    def test_accepts_a_trailing_z(self):
        lo, _ = series_span([_pt("2026-08-30T12:00:00Z")])
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
        lo, hi = series_span(history)
        assert drop_markers_outside_span(markers, lo, hi) == []

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
        lo, hi = series_span(win_prob)
        assert drop_markers_outside_span(markers, lo, hi) == []

    def test_event_15298122_no_line_at_all_places_no_marker(self):
        """Ajax v Union SG: every series empty, two chips served anyway.

        56% of the cohort (39/70). A chart with no line cannot place a boundary
        on it, so the honest answer is no markers.
        """
        markers = [
            _marker("2026-08-30T17:50:00.260799+00:00", "1H"),
            _marker("2026-08-30T18:37:00.260799+00:00", "2H"),
        ]
        lo, hi = series_span([], None)
        assert (lo, hi) == (None, None)
        assert drop_markers_outside_span(markers, lo, hi) == []

    def test_a_partially_off_line_set_keeps_only_what_lands(self):
        """Event 15291077: one marker inside, one 36 minutes past the end."""
        history = [
            _pt("2026-08-29T10:00:00+00:00"),
            _pt("2026-08-29T12:00:00+00:00"),
        ]
        inside = _marker("2026-08-29T11:00:00+00:00", "1H")
        past = _marker("2026-08-29T12:36:00+00:00", "2H")
        lo, hi = series_span(history)
        assert drop_markers_outside_span([inside, past], lo, hi) == [inside]


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
        lo, hi = series_span(points)
        assert drop_markers_outside_span(markers, lo, hi) == markers

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
        lo, hi = series_span(history)
        assert drop_markers_outside_span(markers, lo, hi) == markers

    def test_a_live_chart_is_drawn_to_now_so_a_present_marker_is_kept(self):
        """The route widens `hi` to now for an unfinished event. Without that a
        marker later than the last banked snapshot would be dropped off a live
        chart that is in fact drawn out to the present."""
        now = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)
        history = [_pt("2026-08-30T19:00:00+00:00")]
        marker = _marker("2026-08-30T19:50:00+00:00", "2H", SOURCE_STATPAL)
        lo, hi = series_span(history)
        assert drop_markers_outside_span([marker], lo, hi) == []       # without
        assert drop_markers_outside_span([marker], lo, max(hi, now)) == [marker]


class TestBoundaryHandling:
    def test_the_minute_bucket_tolerance_keeps_an_edge_marker(self):
        """`history` truncates timestamps to the minute, so a marker may sit a
        few seconds outside a bucket boundary it genuinely belongs to."""
        history = [_pt("2026-08-30T19:00:00+00:00")]
        lo, hi = series_span(history)
        edge = _marker("2026-08-30T19:00:30+00:00")
        assert drop_markers_outside_span([edge], lo, hi) == [edge]

    def test_the_tolerance_is_far_too_small_to_admit_a_real_defect(self):
        """The closest measured miss is 11 minutes; the tolerance is 1."""
        history = [_pt("2026-08-30T19:00:00+00:00")]
        lo, hi = series_span(history)
        near_miss = _marker("2026-08-30T19:11:00+00:00")
        assert drop_markers_outside_span([near_miss], lo, hi) == []

    def test_an_unplaceable_marker_is_dropped(self):
        history = [_pt("2026-08-30T19:00:00+00:00")]
        lo, hi = series_span(history)
        assert drop_markers_outside_span([{"period": "1H"}], lo, hi) == []
        assert drop_markers_outside_span([_marker("garbage")], lo, hi) == []

    def test_an_empty_marker_list_stays_empty(self):
        assert drop_markers_outside_span([], None, None) == []


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
