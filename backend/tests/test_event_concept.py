"""#999 slice 1: generic event-concept core (key parsing + golf envelope)."""

from datetime import datetime, timedelta, timezone

from app.utils.event_concept import (
    parse_event_key,
    golf_detail_to_envelope,
    get_adapter,
    registered_domains,
    fuse_golf_live,
    golf_live_deltas,
    downsample_points,
    _golf_leaderboard_has_live_rows,
    _golf_within_play_window,
    _golf_leaderboard_is_fresh,
)


class TestDownsamplePoints:
    """L2-71: bound per-competitor history to ~target points, keep first + last."""

    def test_under_target_unchanged(self):
        pts = [(1, 0.1), (2, 0.2), (3, 0.3)]
        assert downsample_points(pts, 25) == pts

    def test_downsamples_keeping_first_and_last(self):
        pts = [(i, i / 100) for i in range(200)]
        out = downsample_points(pts, 25)
        assert len(out) <= 25
        assert out[0] == pts[0]      # first kept
        assert out[-1] == pts[-1]    # last kept
        # monotonic (order preserved)
        assert [p[0] for p in out] == sorted(p[0] for p in out)

    def test_target_below_2_returns_copy(self):
        pts = [(1, 0.1), (2, 0.2)]
        assert downsample_points(pts, 1) == pts


class TestGolfLiveDeltas:
    """L2-69: true in-play win-prob delta ('who's charging'). competitor.probability
    (0-1) == DataGolf win_prob, so delta vs the day's baseline is source-consistent."""

    def test_snapshot_baseline_delta_points(self):
        comps = [
            {"name": "Rory McIlroy", "probability": 0.161, "opening_probability": 0.077},
            {"name": "Tom Kim", "probability": 0.042, "opening_probability": 0.041},
        ]
        # Start-of-day snapshot baseline in POINTS (0-100), keyed by lower name.
        baseline = {"rory mcilroy": 7.3, "tom kim": 4.0}
        golf_live_deltas(comps, baseline)
        assert comps[0]["prob_delta_live"] == 8.8   # 16.1 - 7.3
        assert comps[1]["prob_delta_live"] == 0.2    # 4.2 - 4.0

    def test_round1_falls_back_to_opening_probability(self):
        # No snapshot baseline → use opening_probability (round-1 ≈ pre-tournament).
        comps = [{"name": "Rory McIlroy", "probability": 0.161, "opening_probability": 0.077}]
        golf_live_deltas(comps, {})
        assert comps[0]["prob_delta_live"] == 8.4   # 16.1 - 7.7

    def test_no_baseline_no_field(self):
        # No snapshot AND no opening_probability → never fabricate a delta.
        comps = [{"name": "Ghost", "probability": 0.05}]
        golf_live_deltas(comps, {})
        assert "prob_delta_live" not in comps[0]

    def test_null_probability_skipped(self):
        comps = [{"name": "X", "probability": None, "opening_probability": 0.1}]
        golf_live_deltas(comps, {})
        assert "prob_delta_live" not in comps[0]


class TestParseEventKey:
    def test_canonical_form(self):
        assert parse_event_key("event:golf:2026-masters") == ("golf", "2026-masters")
        assert parse_event_key("event:tennis:wimbledon-2026") == ("tennis", "wimbledon-2026")

    def test_domain_slug_form(self):
        assert parse_event_key("golf:2026-masters") == ("golf", "2026-masters")

    def test_slug_may_contain_colons(self):
        # only the domain segment is split off
        assert parse_event_key("event:ufc:ufc-310:main") == ("ufc", "ufc-310:main")

    def test_bare_slug_defaults_to_golf(self):
        assert parse_event_key("2026-masters") == ("golf", "2026-masters")


class TestRegistry:
    def test_golf_adapter_registered(self):
        assert "golf" in registered_domains()
        adapter = get_adapter("golf")
        assert adapter is not None and adapter.domain == "golf"

    def test_tennis_adapter_registered(self):
        assert "tennis" in registered_domains()  # slice 2

    def test_unknown_domain_returns_none(self):
        assert get_adapter("ufc") is None  # future slice (F1/UFC/awards)


def _golf_fixture():
    return {
        "tournament": {
            "name": "The Masters",
            "key": "masters",
            "is_major": True,
            "is_womens": False,
            "start_date": "2026-04-09",
            "end_date": "2026-04-12",
            "venue": "Augusta National",
            "location": "Augusta, GA",
            "schedule_status": "completed",
        },
        "golfers": [{"name": "Scottie Scheffler", "probability": 0.22}],
        "markets": [{"type": "winner", "label": "Winner", "market_ids": [1]}],
        "related_futures": [{"market_id": 5, "market_name": "H2H: A vs B"}],
        "evolution_market_id": 1,
        "biggest_movers": [{"name": "Rory", "change": 0.05}],
    }


class TestGolfEnvelope:
    def test_maps_to_generic_envelope(self):
        env = golf_detail_to_envelope("event:golf:the-masters", "the-masters", _golf_fixture())
        assert env["event"]["domain"] == "golf"
        assert env["event"]["name"] == "The Masters"
        assert env["event"]["status"] == "settled"      # completed -> settled
        assert env["event"]["venue"] == "Augusta National"
        assert env["event"]["is_major"] is True
        assert env["primary"]["kind"] == "winner_field"
        assert env["primary"]["competitors"][0]["name"] == "Scottie Scheffler"
        assert env["primary"]["evolution_market_id"] == 1
        assert env["sections"][0]["type"] == "winner"
        assert env["children"][0]["market_name"] == "H2H: A vs B"
        assert env["movers"][0]["name"] == "Rory"

    def test_status_normalization(self):
        def status(raw):
            f = _golf_fixture(); f["tournament"]["schedule_status"] = raw
            return golf_detail_to_envelope("k", "s", f)["event"]["status"]
        assert status("in_progress") == "live"
        # L2-66: DataGolf reports the HYPHEN form — must also map to live.
        assert status("in-progress") == "live"
        assert status("upcoming") == "upcoming"
        assert status("") == "upcoming"
        assert status("resolved") == "settled"

    def test_envelope_carries_as_of_slot(self):
        # L2-66: the freshness slot always exists (None until live fusion sets it).
        env = golf_detail_to_envelope("event:golf:x", "x", _golf_fixture())
        assert env["event"]["as_of"] is None


class TestFuseGolfLive:
    """L2-66: fuse stored DataGolf leaderboard into competitors by name."""

    def _leaderboard(self):
        return [
            {"name": "Scottie Scheffler", "position": "T1", "total_score": -7,
             "today_score": -3, "thru": "12", "current_round": 3},
            {"name": "Rory McIlroy", "position": "T3", "total_score": -5,
             "today_score": -1, "thru": "F", "current_round": 3},
        ]

    def test_merges_live_fields_by_name(self):
        comps = [
            {"name": "Scottie Scheffler", "probability": 0.30},
            {"name": "Rory McIlroy", "probability": 0.18},
        ]
        as_of = fuse_golf_live(comps, self._leaderboard(), "2026-07-09T15:00:00+00:00")
        assert as_of == "2026-07-09T15:00:00+00:00"
        assert comps[0]["position"] == "T1"
        assert comps[0]["score_to_par"] == -7
        assert comps[0]["thru"] == "12"
        assert comps[0]["current_round"] == 3
        assert comps[1]["thru"] == "F"

    def test_name_match_is_case_and_space_insensitive(self):
        comps = [{"name": "  scottie   scheffler ", "probability": 0.3}]
        fuse_golf_live(comps, self._leaderboard(), None)
        assert comps[0]["position"] == "T1"

    def test_unmatched_competitor_is_left_probability_only(self):
        comps = [{"name": "Ludvig Aberg", "probability": 0.09}]
        fuse_golf_live(comps, self._leaderboard(), None)
        assert "position" not in comps[0]  # never fabricate live state
        assert comps[0]["probability"] == 0.09

    def test_empty_leaderboard_safe(self):
        comps = [{"name": "X", "probability": 0.1}]
        assert fuse_golf_live(comps, [], "t") == "t"
        assert fuse_golf_live(comps, None, None) is None

    def test_key_defaults_when_bare(self):
        env = golf_detail_to_envelope("the-masters", "the-masters", _golf_fixture())
        assert env["event"]["key"] == "event:golf:the-masters"

    def test_missing_fields_safe(self):
        env = golf_detail_to_envelope("event:golf:x", "x", {"tournament": {}})
        assert env["primary"]["competitors"] == []
        assert env["sections"] == []
        assert env["children"] == []


class TestGolfLiveFallback:
    """#144: leaderboard-presence + play-window fallback for LIVE detection.

    DataGolf's get-schedule `status` did not flip to in-progress during Scottish
    Open round 1, so the schedule-string path alone left the event 'upcoming'
    while a fresh 156-row in-play leaderboard sat in the win-market metadata.
    """

    def _live_rows(self):
        return [
            {"name": "Rory McIlroy", "position": "T1", "thru": "18",
             "total_score": -5, "today_score": -5, "current_round": 1},
        ]

    def test_live_rows_detected(self):
        assert _golf_leaderboard_has_live_rows(self._live_rows())

    def test_position_only_row_counts(self):
        assert _golf_leaderboard_has_live_rows([{"name": "X", "position": "T5"}])

    def test_thru_only_row_counts(self):
        assert _golf_leaderboard_has_live_rows([{"name": "X", "thru": "3"}])

    def test_field_dump_without_inplay_signal_is_not_live(self):
        # Pre-tournament field: names only, no position/thru/score → not live.
        assert not _golf_leaderboard_has_live_rows(
            [{"name": "A"}, {"name": "B", "dg_id": 1}]
        )

    def test_empty_or_none_not_live(self):
        assert not _golf_leaderboard_has_live_rows([])
        assert not _golf_leaderboard_has_live_rows(None)

    def test_within_play_window_inclusive(self):
        now = datetime(2026, 7, 9, 16, 0, tzinfo=timezone.utc)
        # Scottish Open: 07-09 → 07-12, today 07-09.
        assert _golf_within_play_window(
            "2026-07-09T00:00:00+00:00", "2026-07-12T00:00:00+00:00", now
        )

    def test_play_window_tail_grace(self):
        now = datetime(2026, 7, 13, 2, 0, tzinfo=timezone.utc)  # end + 1d
        assert _golf_within_play_window(
            "2026-07-09T00:00:00+00:00", "2026-07-12T00:00:00+00:00", now
        )

    def test_before_start_not_in_window(self):
        now = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
        assert not _golf_within_play_window(
            "2026-07-09T00:00:00+00:00", "2026-07-12T00:00:00+00:00", now
        )

    def test_after_window_not_live(self):
        now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        assert not _golf_within_play_window(
            "2026-07-09T00:00:00+00:00", "2026-07-12T00:00:00+00:00", now
        )

    def test_missing_dates_returns_false(self):
        now = datetime(2026, 7, 9, 16, 0, tzinfo=timezone.utc)
        assert not _golf_within_play_window(None, None, now)
        assert not _golf_within_play_window("2026-07-09T00:00:00+00:00", None, now)

    def test_leaderboard_fresh_within_window(self):
        now = datetime(2026, 7, 9, 16, 0, tzinfo=timezone.utc)
        assert _golf_leaderboard_is_fresh("2026-07-09T15:30:00+00:00", now)

    def test_leaderboard_stale_is_not_fresh(self):
        now = datetime(2026, 7, 9, 16, 0, tzinfo=timezone.utc)
        assert not _golf_leaderboard_is_fresh("2026-07-08T00:00:00+00:00", now)

    def test_fresh_handles_z_suffix_and_naive(self):
        now = datetime(2026, 7, 9, 16, 0, tzinfo=timezone.utc)
        assert _golf_leaderboard_is_fresh("2026-07-09T15:30:00Z", now)
        assert _golf_leaderboard_is_fresh("2026-07-09T15:30:00", now)  # naive→utc

    def test_fresh_none_or_garbage_is_false(self):
        now = datetime(2026, 7, 9, 16, 0, tzinfo=timezone.utc)
        assert not _golf_leaderboard_is_fresh(None, now)
        assert not _golf_leaderboard_is_fresh("not-a-date", now)
