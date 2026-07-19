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
    build_golf_props_script,
    classify_prop_kind,
    _clean_prop_label,
    _golf_leaderboard_has_live_rows,
    _golf_within_play_window,
    _golf_leaderboard_is_fresh,
    _golf_status,
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

    def test_f1_and_ufc_adapters_registered(self):
        # L2-72: slices 3/4 (co_equal_list UFC + winner-field F1).
        assert "f1" in registered_domains()
        assert "ufc" in registered_domains()
        assert get_adapter("ufc").domain == "ufc"

    def test_awards_adapter_registered(self):
        # L2-87 (B6): the awards ceremony adapter (co_equal_list, design §6).
        assert "awards" in registered_domains()
        assert get_adapter("awards").domain == "awards"

    def test_unknown_domain_returns_none(self):
        assert get_adapter("cricket") is None  # no adapter for this domain yet


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
        assert status("resolved") == "settled"
        # L2-124 (#202): non-terminal statuses ("", "upcoming", unknown) now fall
        # back to the schedule DATE. The fixture is past-dated (April 2026), so a
        # stale "upcoming"/empty status on a finished tournament resolves to
        # "settled" — it no longer leaks into the hub's upcoming rail. Date-fallback
        # edges (future dates, fail-open, grace) are covered in
        # test_status_date_fallback_both_directions.
        assert status("") == "settled"
        assert status("upcoming") == "settled"

    def test_status_date_fallback_both_directions(self):
        # L2-124 (#202): _golf_status must fall back to schedule DATES when
        # schedule_status is absent/non-terminal — guard BOTH directions
        # (gotcha #43): a past card demotes to settled AND a future card stays
        # upcoming, plus fail-open on missing/unparseable dates.
        now = datetime(2026, 7, 15, tzinfo=timezone.utc)

        # (a) PAST end_date, no terminal status -> settled (the hub-rail leak fix)
        assert _golf_status(
            {"schedule_status": "", "start_date": "2026-06-30", "end_date": "2026-07-03"}, now
        ) == "settled"

        # (b) FUTURE end_date -> stays upcoming (the flood we must NOT hide)
        assert _golf_status(
            {"schedule_status": None, "start_date": "2026-07-16", "end_date": "2026-07-19"}, now
        ) == "upcoming"

        # (c) end_date == today and yesterday are within the 1-day grace -> upcoming
        #     (a final round in progress must not be prematurely demoted)
        assert _golf_status({"schedule_status": "", "end_date": "2026-07-15"}, now) == "upcoming"
        assert _golf_status({"schedule_status": "", "end_date": "2026-07-14"}, now) == "upcoming"
        assert _golf_status({"schedule_status": "", "end_date": "2026-07-13"}, now) == "settled"

        # (d) FAIL-OPEN: missing or unparseable dates stay upcoming — never hide a
        #     real card because a date field was bad.
        assert _golf_status({"schedule_status": ""}, now) == "upcoming"
        assert _golf_status({"schedule_status": "", "end_date": "not-a-date"}, now) == "upcoming"
        assert _golf_status({"schedule_status": "", "end_date": None}, now) == "upcoming"

        # (e) start_date fallback (no end_date) uses a 7-day grace (tournaments run
        #     ~4 days); a start >7d ago is settled, within 7d stays upcoming.
        assert _golf_status({"schedule_status": "", "start_date": "2026-07-01"}, now) == "settled"
        assert _golf_status({"schedule_status": "", "start_date": "2026-07-12"}, now) == "upcoming"

        # (e') commence_time fallback: the finished DP-World-Tour cards (BMW
        #     International Open) carry NO schedule start_date — the date lives in
        #     commence_time — and a FUTURE Kalshi resolution_date. The past
        #     commence_time must still settle them (the actual hub-rail leak).
        assert _golf_status(
            {"schedule_status": None, "commence_time": "2026-07-03T18:59:53+00:00",
             "resolution_date": "2026-08-02T00:00:00+00:00"}, now
        ) == "settled"
        # …but a FUTURE commence_time (genuinely upcoming, no start_date) stays up.
        assert _golf_status(
            {"schedule_status": None, "commence_time": "2026-07-20T00:00:00+00:00"}, now
        ) == "upcoming"

        # (f) explicit terminal/live status always wins over dates
        assert _golf_status(
            {"schedule_status": "in-progress", "end_date": "2026-01-01"}, now
        ) == "live"

    def test_envelope_carries_as_of_slot(self):
        # L2-66: the freshness slot always exists (None until live fusion sets it).
        env = golf_detail_to_envelope("event:golf:x", "x", _golf_fixture())
        assert env["event"]["as_of"] is None

    def test_round_groups_forwarded_as_prop_children(self):
        # L2-89: round leaders + per-round Top-N were dropped from the envelope
        # entirely (invisible on /event/<key>). They must forward as PROP children
        # with a round-qualified label so the props section renders them.
        f = _golf_fixture()
        f["round_top_groups"] = [
            {
                "market_id": 11, "round": 1, "top_n": None, "kind": "leader",
                "label": "Round Leader",
                "outcomes": [{"name": "Scottie Scheffler", "probability": 0.08}],
            },
            {
                "market_id": 12, "round": 2, "top_n": 5, "kind": "top",
                "label": "Top 5 Finishers",
                "outcomes": [{"name": "Rory McIlroy", "probability": 0.3}],
            },
        ]
        env = golf_detail_to_envelope("event:golf:x", "x", f)
        # Original related_futures child still present, plus two prop children.
        assert env["children"][0]["market_name"] == "H2H: A vs B"
        props = [c for c in env["children"] if c.get("kind") == "prop"]
        assert len(props) == 2
        assert all(c["prop_type"] == "round" for c in props)
        labels = {c["market_name"] for c in props}
        assert labels == {"Round 1 Leader", "Round 2: Top 5 Finishers"}

    def test_no_round_groups_leaves_children_unchanged(self):
        env = golf_detail_to_envelope("event:golf:x", "x", _golf_fixture())
        assert len(env["children"]) == 1
        assert env["children"][0]["market_name"] == "H2H: A vs B"


class TestCleanPropLabel:
    def test_strips_tournament_prefix(self):
        assert _clean_prop_label("The Open Championship: Playoff", "The Open Championship") == "Playoff"

    def test_strips_prefix_case_insensitive_and_dashes(self):
        assert _clean_prop_label("the open championship – Hole-in-One", "The Open Championship") == "Hole-in-One"

    def test_no_prefix_returned_verbatim(self):
        assert _clean_prop_label("Round 1 Leader", "The Open Championship") == "Round 1 Leader"

    def test_empty_falls_back(self):
        assert _clean_prop_label("", "The Open") == "Prop"
        assert _clean_prop_label(None, None) == "Prop"

    def test_prefix_only_does_not_blank_the_label(self):
        # A market named exactly the tournament name keeps the tournament name
        # rather than collapsing to "Prop".
        assert _clean_prop_label("The Open Championship", "The Open Championship") == "The Open Championship"


class TestBuildGolfPropsScript:
    def _children(self):
        return [
            # Field-shaped round leader — names the current pick; opening→current arc.
            {
                "market_id": 11,
                "market_name": "Round 1 Leader",
                "kind": "prop",
                "prop_type": "round",
                "outcomes": [
                    {"name": "Scottie Scheffler", "probability": 0.044, "opening_probability": 0.0495},
                    {"name": "Rory McIlroy", "probability": 0.035, "opening_probability": 0.0375},
                ],
            },
            # Binary occurrence prop — reads as the question; big mover.
            {
                "market_id": 22,
                "market_name": "The Open Championship: Playoff",
                "outcomes": [{"name": "Yes", "probability": 0.205, "opening_probability": 0.28}],
            },
            # Threshold prop — leading rung, small mover.
            {
                "market_id": 33,
                "market_name": "The Open Championship: Hole-in-One",
                "outcomes": [
                    {"name": "1+ holes-in-one", "probability": 0.515, "opening_probability": 0.56},
                    {"name": "2+ holes-in-one", "probability": 0.155, "opening_probability": 0.185},
                ],
            },
        ]

    def test_one_mark_per_prop_tracking_the_favorite(self):
        marks = build_golf_props_script(self._children(), "The Open Championship", "upcoming")
        assert len(marks) == 3
        by_id = {m["market_id"]: m for m in marks}
        # Round leader labels the current pick; endpoints come from THAT outcome.
        assert by_id[11]["label"] == "Round 1 Leader: Scottie Scheffler"
        assert by_id[11]["current"] == 0.044
        assert by_id[11]["pregame_mark"] == 0.0495
        # Binary/threshold props read as the (prefix-stripped) question.
        assert by_id[22]["label"] == "Playoff"
        assert by_id[22]["current"] == 0.205 and by_id[22]["pregame_mark"] == 0.28
        assert by_id[33]["label"] == "Hole-in-One"
        assert by_id[33]["current"] == 0.515
        # Graded is intentionally deferred (WHAT HIT is a separate backend).
        assert all(m["graded_result"] is None for m in marks)

    def test_sorted_biggest_mover_first(self):
        marks = build_golf_props_script(self._children(), "The Open Championship", "upcoming")
        # Playoff moved 7.5pts, Hole-in-One 4.5pts, Round leader ~0.55pt.
        assert [m["market_id"] for m in marks] == [22, 33, 11]

    def test_settled_suppresses_marks(self):
        assert build_golf_props_script(self._children(), "The Open Championship", "settled") == []

    def test_missing_opening_leaves_pregame_null(self):
        children = [
            {
                "market_id": 44,
                "market_name": "Round 2 Leader",
                "kind": "prop",
                "prop_type": "round",
                "outcomes": [{"name": "John Daly", "probability": 0.24}],
            }
        ]
        marks = build_golf_props_script(children, "The Open Championship", "live")
        assert len(marks) == 1
        assert marks[0]["pregame_mark"] is None
        assert marks[0]["current"] == 0.24

    def test_child_without_usable_leader_is_skipped(self):
        children = [
            {"market_id": 55, "market_name": "Empty", "outcomes": []},
            {"market_id": 56, "market_name": "AllNull", "outcomes": [{"name": "X", "probability": None}]},
        ]
        assert build_golf_props_script(children, "The Open", "upcoming") == []

    def test_key_and_market_id_both_carry_the_id(self):
        marks = build_golf_props_script(self._children(), "The Open Championship", "upcoming")
        assert all(m["key"] == m["market_id"] for m in marks)

    # ---- L2-123 / #199: degenerate (no-honest-price) families render pending ----

    def test_degenerate_round_leader_gets_opens_after_round_label(self):
        # The Open's real R2 leader: 10 golfers all tied at 0.24, no openings — the
        # wide-spread/no-trade capture class. Must render an honest pending row, NOT
        # a fabricated flat and NOT an arbitrary crowned "leader".
        children = [
            {
                "market_id": 77,
                "market_name": "Round 2 Leader",
                "kind": "prop",
                "prop_type": "round",
                "round": 2,
                "outcomes": [
                    {"name": f"Golfer {i}", "probability": 0.24, "opening_probability": None}
                    for i in range(10)
                ],
            }
        ]
        marks = build_golf_props_script(children, "The Open Championship", "upcoming")
        assert len(marks) == 1
        m = marks[0]
        assert m["pending_label"] == "Opens after Round 1"
        assert m["current"] is None and m["pregame_mark"] is None
        assert m["label"] == "Round 2 Leader"  # no arbitrary golfer crowned

    def test_degenerate_round3_labels_opens_after_round_2(self):
        children = [
            {
                "market_id": 78,
                "market_name": "Round 3 Leader",
                "kind": "prop",
                "prop_type": "round",
                "round": 3,
                "outcomes": [
                    {"name": f"G{i}", "probability": 0.30, "opening_probability": None}
                    for i in range(10)
                ],
            }
        ]
        marks = build_golf_props_script(children, "The Open Championship", "upcoming")
        assert marks[0]["pending_label"] == "Opens after Round 2"

    def test_near_flat_placeholder_not_perfectly_tied_is_degenerate(self):
        # The Open's LIVE R3 was not perfectly tied — 0.29–0.30 (a ~1pp spread) with
        # null openings. The relative-flatness test must still classify it degenerate
        # (an absolute 0.5pp floor alone missed it in the first ship).
        outs = [{"name": f"G{i}", "probability": 0.30, "opening_probability": None} for i in range(9)]
        outs.append({"name": "G9", "probability": 0.29, "opening_probability": None})
        children = [
            {"market_id": 81, "market_name": "Round 3 Leader", "kind": "prop",
             "prop_type": "round", "round": 3, "outcomes": outs}
        ]
        marks = build_golf_props_script(children, "The Open Championship", "upcoming")
        assert marks[0]["pending_label"] == "Opens after Round 2"
        assert marks[0]["current"] is None

    def test_all_null_multi_outcome_family_is_no_market_yet(self):
        # A multi-outcome family with outcomes but no priced probabilities at all →
        # honestly "No market yet" (never blank), not silently dropped.
        children = [
            {
                "market_id": 79,
                "market_name": "The Open Championship: Top 5 Finish",
                "outcomes": [
                    {"name": "A", "probability": None},
                    {"name": "B", "probability": None},
                ],
            }
        ]
        marks = build_golf_props_script(children, "The Open Championship", "upcoming")
        assert len(marks) == 1
        assert marks[0]["pending_label"] == "No market yet"
        assert marks[0]["current"] is None

    def test_priced_round_leader_is_not_degenerate(self):
        # A real spread with openings (R1) must render normally, NOT as pending.
        marks = build_golf_props_script(self._children(), "The Open Championship", "upcoming")
        by_id = {m["market_id"]: m for m in marks}
        assert by_id[11].get("pending_label") is None
        assert by_id[11]["current"] == 0.044

    def test_first_round_leader_with_null_openings_but_real_spread_prices(self):
        # Openings never captured but the live book has a genuine spread → NOT
        # degenerate (the spread is the honest price); renders normally, pregame null.
        children = [
            {
                "market_id": 80,
                "market_name": "Round 1 Leader",
                "kind": "prop",
                "prop_type": "round",
                "round": 1,
                "outcomes": [
                    {"name": "Fav", "probability": 0.09, "opening_probability": None},
                    {"name": "Mid", "probability": 0.04, "opening_probability": None},
                    {"name": "Long", "probability": 0.01, "opening_probability": None},
                ],
            }
        ]
        marks = build_golf_props_script(children, "The Open Championship", "upcoming")
        assert marks[0].get("pending_label") is None
        assert marks[0]["current"] == 0.09
        assert marks[0]["label"] == "Round 1 Leader: Fav"

    # ---- The Open 2026 p0: settled-means-settled for completed rounds ----

    def test_settled_round_renders_graded_not_live(self):
        # A completed round on a still-live tournament: the leader is graded
        # upstream (routes/golf sets settled/graded_winner). It must render WHAT
        # HIT — the graded leader — and NEVER a live current/pregame number.
        children = [
            {
                "market_id": 88,
                "market_name": "Round 1 Leader",
                "kind": "prop",
                "prop_type": "round",
                "round": 1,
                "settled": True,
                "graded_winner": "Jackson Suber",
                "outcomes": [
                    {"name": "Jackson Suber", "probability": 0.999, "opening_probability": None},
                ],
            }
        ]
        marks = build_golf_props_script(children, "The Open Championship", "live")
        assert len(marks) == 1
        m = marks[0]
        assert m["settled"] is True
        assert m["graded_result"] == "hit"
        assert m["graded_label"] == "Jackson Suber led"
        assert m["label"] == "Round 1 Leader: Jackson Suber"
        # The defect being fixed: NO live number for a completed round.
        assert m["current"] is None
        assert m["pregame_mark"] is None
        # A graded row, not a live field card/bar.
        assert m["kind"] is None

    def test_settled_round_takes_precedence_over_degenerate_losers(self):
        # Even if the losers look like the #199 degenerate all-tied placeholder
        # class, a graded round is settled — it renders the winner, not a pending
        # "Opens after Round N" row.
        children = [
            {
                "market_id": 89,
                "market_name": "Round 3 Leader",
                "kind": "prop",
                "prop_type": "round",
                "round": 3,
                "settled": True,
                "graded_winner": "Sam Burns",
                "outcomes": (
                    [{"name": "Sam Burns", "probability": 0.99, "opening_probability": None}]
                    + [{"name": f"G{i}", "probability": 0.30, "opening_probability": None} for i in range(8)]
                ),
            }
        ]
        marks = build_golf_props_script(children, "The Open Championship", "live")
        assert len(marks) == 1
        assert marks[0]["settled"] is True
        assert marks[0]["graded_label"] == "Sam Burns led"
        assert marks[0].get("pending_label") is None

    def test_live_round_marks_are_not_settled(self):
        # Regression guard: a live (ungraded) round leader keeps the live path —
        # settled must be False, current populated. (The whole point is that only
        # graded rounds flip to WHAT HIT.)
        marks = build_golf_props_script(self._children(), "The Open Championship", "live")
        by_id = {m["market_id"]: m for m in marks}
        assert by_id[11]["settled"] is False
        assert by_id[11]["current"] == 0.044

    def test_envelope_threads_settled_and_graded_winner(self):
        # golf_detail_to_envelope must forward settled/graded_winner from
        # round_top_groups onto round children so a completed round grades.
        f = _golf_fixture()
        f["tournament"]["schedule_status"] = "live"
        f["tournament"]["start_date"] = None
        f["tournament"]["end_date"] = None
        f["round_top_groups"] = [
            {
                "market_id": 91,
                "kind": "leader",
                "round": 3,
                "settled": True,
                "graded_winner": "Sam Burns",
                "outcomes": [
                    {"name": "Sam Burns", "probability": 0.99, "opening_probability": None},
                ],
            }
        ]
        env = golf_detail_to_envelope("event:golf:x", "x", f)
        child = next(c for c in env["children"] if c.get("market_id") == 91)
        assert child["settled"] is True
        assert child["graded_winner"] == "Sam Burns"
        ps = [p for p in env["props_script"] if p["market_id"] == 91]
        assert len(ps) == 1
        assert ps[0]["settled"] is True
        assert ps[0]["graded_result"] == "hit"
        assert ps[0]["current"] is None

    def test_envelope_round_children_carry_round_and_pending(self):
        # golf_detail_to_envelope must forward `round` onto round children so the
        # degenerate-family label can say "Opens after Round N".
        f = _golf_fixture()
        f["tournament"]["schedule_status"] = "upcoming"
        # L2-124 (#202): the shared fixture is past-dated, and _golf_status now
        # date-demotes a stale "upcoming" to settled; clear the dates so this
        # envelope-logic test stays a genuine not-settled tournament (fail-open).
        f["tournament"]["start_date"] = None
        f["tournament"]["end_date"] = None
        f["round_top_groups"] = [
            {
                "market_id": 90,
                "kind": "leader",
                "round": 2,
                "outcomes": [
                    {"name": f"G{i}", "probability": 0.24, "opening_probability": None}
                    for i in range(10)
                ],
            }
        ]
        env = golf_detail_to_envelope("event:golf:x", "x", f)
        ps = [p for p in env["props_script"] if p["market_id"] == 90]
        assert len(ps) == 1
        assert ps[0]["pending_label"] == "Opens after Round 1"

    def test_envelope_carries_props_script_when_not_settled(self):
        f = _golf_fixture()
        f["tournament"]["schedule_status"] = "upcoming"
        # L2-124 (#202): clear the past dates so the date fallback keeps this a
        # genuine not-settled tournament (else stale "upcoming" + past date settles).
        f["tournament"]["start_date"] = None
        f["tournament"]["end_date"] = None
        f["related_futures"] = [
            {
                "market_id": 22,
                "market_name": "The Masters: Playoff",
                "outcomes": [{"name": "Yes", "probability": 0.2, "opening_probability": 0.28}],
            }
        ]
        env = golf_detail_to_envelope("event:golf:x", "x", f)
        assert "props_script" in env
        assert len(env["props_script"]) == 1
        assert env["props_script"][0]["label"] == "Playoff"

    def test_envelope_props_script_empty_when_settled(self):
        # Default fixture status is "completed" -> settled.
        env = golf_detail_to_envelope("event:golf:x", "x", _golf_fixture())
        assert env["props_script"] == []

    def test_envelope_drops_junk_related_futures_rows(self):
        # L2-123 Item 3: a related-future with no name AND no outcomes must not reach
        # the children rails (it would render as an empty row).
        f = _golf_fixture()
        f["tournament"]["schedule_status"] = "upcoming"
        f["related_futures"] = [
            {"market_id": 1, "name": None, "outcomes": []},  # pure junk → dropped
            {
                "market_id": 2,
                "market_name": "The Open: Playoff",
                "outcomes": [{"name": "Yes", "probability": 0.2, "opening_probability": 0.28}],
            },
        ]
        env = golf_detail_to_envelope("event:golf:x", "x", f)
        child_ids = {c.get("market_id") for c in env["children"]}
        assert 1 not in child_ids  # junk dropped
        assert 2 in child_ids  # real market kept


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


class TestClassifyPropKind:
    """Prop archetype classification (Alex's ruling, The Open 2026): the shape
    decides the visual — binary → divergence bar, ladder → QuantityGroup rungs,
    field → named top-N (never a probability without a name)."""

    def test_single_outcome_is_binary(self):
        assert classify_prop_kind([{"name": "Yes", "probability": 0.18}]) == "binary"

    def test_yes_no_family_is_binary(self):
        outs = [{"name": "Yes", "probability": 0.6}, {"name": "No", "probability": 0.4}]
        assert classify_prop_kind(outs) == "binary"

    def test_threshold_rungs_are_a_ladder(self):
        outs = [
            {"name": "Under 67.5", "probability": 0.92},
            {"name": "Under 66.5", "probability": 0.88},
            {"name": "Under 65.5", "probability": 0.815},
        ]
        assert classify_prop_kind(outs) == "ladder"

    def test_count_rungs_are_a_ladder(self):
        outs = [
            {"name": "1+ holes-in-one", "probability": 0.525},
            {"name": "2+ holes-in-one", "probability": 0.175},
            {"name": "3+ holes-in-one", "probability": 0.045},
        ]
        assert classify_prop_kind(outs) == "ladder"

    def test_exactly_rungs_are_a_ladder(self):
        outs = [
            {"name": "Exactly 2 strokes", "probability": 0.295},
            {"name": "Exactly 1 stroke", "probability": 0.27},
            {"name": "Exactly 0 strokes", "probability": 0.2},
        ]
        assert classify_prop_kind(outs) == "ladder"

    def test_named_entities_are_a_field(self):
        outs = [
            {"name": "Min Woo Lee", "probability": 0.125},
            {"name": "Si Woo Kim", "probability": 0.12},
            {"name": "Adam Scott", "probability": 0.09},
        ]
        assert classify_prop_kind(outs) == "field"

    def test_name_first_threshold_labels_stay_a_field(self):
        # "R1: Alex Fitzpatrick under 70.5 strokes" carries a NAME first — a
        # ladder of unrelated golfers would be dishonest. Anchored patterns keep
        # these a field so the names render.
        outs = [
            {"name": "R1: Alex Fitzpatrick under 70.5 strokes", "probability": 0.81},
            {"name": "R1: Matt Wallace under 71.5 strokes", "probability": 0.8},
            {"name": "R1: Nick Taylor under 70.5 strokes", "probability": 0.775},
        ]
        assert classify_prop_kind(outs) == "field"


class TestPropsScriptArchetypeFields:
    def _field_child(self):
        return {
            "market_id": 91,
            "market_name": "The Open Championship: Top Asian/Oceanic Golfer",
            "outcomes": [
                {"name": "Min Woo Lee", "probability": 0.125, "opening_probability": 0.125},
                {"name": "Si Woo Kim", "probability": 0.12, "opening_probability": 0.12},
                {"name": "Adam Scott", "probability": 0.09, "opening_probability": None},
                {"name": "Tom Kim", "probability": 0.085, "opening_probability": 0.085},
            ],
        }

    def test_field_mark_names_its_favorite_in_the_label(self):
        # The original bug: "Top Asian/Oceanic Golfer — 12.5%" with no name. A
        # field mark's legacy label must carry the favorite; the visual renderer
        # reads `question` + `outcomes` instead.
        marks = build_golf_props_script([self._field_child()], "The Open Championship", "upcoming")
        m = marks[0]
        assert m["kind"] == "field"
        assert m["label"] == "Top Asian/Oceanic Golfer: Min Woo Lee"
        assert m["question"] == "Top Asian/Oceanic Golfer"

    def test_field_mark_carries_top3_named_outcomes(self):
        marks = build_golf_props_script([self._field_child()], "The Open Championship", "upcoming")
        outs = marks[0]["outcomes"]
        assert [o["name"] for o in outs] == ["Min Woo Lee", "Si Woo Kim", "Adam Scott"]
        assert outs[0]["probability"] == 0.125
        assert outs[0]["opening_probability"] == 0.125
        assert outs[2]["opening_probability"] is None  # honest null, no fabrication

    def test_binary_mark_keeps_question_label_and_empty_outcomes(self):
        children = [{
            "market_id": 92,
            "market_name": "The Open Championship: Playoff",
            "outcomes": [{"name": "Yes", "probability": 0.18, "opening_probability": 0.28}],
        }]
        m = build_golf_props_script(children, "The Open Championship", "upcoming")[0]
        assert m["kind"] == "binary"
        assert m["label"] == "Playoff"
        assert m["outcomes"] == []

    def test_ladder_mark_carries_its_rungs(self):
        children = [{
            "market_id": 93,
            "market_name": "The Open Championship: Bogey-Free Round",
            "outcomes": [
                {"name": f"{i}+ Bogey-Free Rounds", "probability": 0.9 - i * 0.05,
                 "opening_probability": None}
                for i in range(1, 6)
            ],
        }]
        m = build_golf_props_script(children, "The Open Championship", "upcoming")[0]
        assert m["kind"] == "ladder"
        assert m["question"] == "Bogey-Free Round"
        assert len(m["outcomes"]) == 5
        assert m["outcomes"][0]["name"] == "1+ Bogey-Free Rounds"

    def test_pending_mark_still_classifies_and_carries_no_outcomes(self):
        children = [{
            "market_id": 94,
            "market_name": "Round 2 Leader",
            "kind": "prop",
            "prop_type": "round",
            "round": 2,
            "outcomes": [
                {"name": f"Golfer {i}", "probability": 0.24, "opening_probability": None}
                for i in range(10)
            ],
        }]
        m = build_golf_props_script(children, "The Open Championship", "upcoming")[0]
        assert m["pending_label"] == "Opens after Round 1"
        assert m["kind"] == "field"
        assert m["outcomes"] == []
