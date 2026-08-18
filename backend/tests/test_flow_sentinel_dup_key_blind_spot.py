"""UX-P091 — the Flow Sentinel's REPORTING rail, pinned with production specimens.

Cycle 88 was asked to triage #1941 / #1942 to mechanism. Doing that turned out to
require archaeology against the sentinel's own filed issues, and the archaeology
is what this file is about: the rail DETECTS well and REPORTS badly, in three
separate, measured ways.

Every fixture here is a verbatim production row from 2026-08-17, not an invention.
"""

import json

from app.tasks.flow_sentinel import (
    build_flow_issue_body,
    build_flow_redetect_comment,
    event_dup_key,
    find_duplicate_events,
    inverted_completed_events,
    live_before_commence_events,
    render_failure_lines,
)

# ---------------------------------------------------------------------------
# Production specimens, 2026-08-17. Team pair + times verified against ESPN's
# own scoreboard for 2026-08-17 and 2026-08-19.
# ---------------------------------------------------------------------------

# The "A" rows: LEGITIMATE 2026-08-19 game rows (their commence_time matches
# ESPN's 08-19 slate exactly) that received TONIGHT's in-progress game state.
ROW_A_PIRATES = {
    "id": 15199901,
    "sport": "baseball_mlb",
    "home_team": "Pittsburgh Pirates",
    "away_team": "Detroit Tigers",
    "commence_time": "2026-08-19T16:35:00+00:00",  # == ESPN 401816587 (08-19)
    "status": "live",                              # but carries ESPN 401816564 (08-17)
    "completed_at": None,
}

# The "B" row: created 2026-08-17T17:05:39Z by the new 10-digit StatPal
# namespace, dated 19:00Z when ESPN says the game is at 23:00Z — exactly -4h,
# Eastern local stamped as UTC.
ROW_B_PIRATES = {
    "id": 15200760,
    "sport": "baseball_mlb",
    "home_team": "Pittsburgh Pirates",
    "away_team": "Detroit Tigers",
    "commence_time": "2026-08-17T19:00:00+00:00",
    "status": "closed",
    "completed_at": None,
}

# The cross-merge: a settled result written onto the 08-20 row.
ROW_REDS_CROSS_MERGED = {
    "id": 15200380,
    "sport": "baseball_mlb",
    "home_team": "Cincinnati Reds",
    "away_team": "St. Louis Cardinals",
    "commence_time": "2026-08-20T16:40:00+00:00",  # == ESPN 401816603
    "status": "completed",
    "completed_at": "2026-08-17T20:26:51.558951+00:00",
}


class TestDupKeyBlindSpot:
    """The minute-granular key cannot see a post-ruling-048 duplicate.

    This is an ASSERTED LIMITATION, not a wish. It exists so the gap stays
    visible to the next reader instead of being rediscovered by hand a third
    time. If someone makes the key id-anchored and this test goes red, that is
    the gap CLOSING — update the test, do not restore the blindness.
    """

    def test_the_two_rows_are_the_same_real_world_game(self):
        # Same sport, same pair. Only the clock disagrees.
        assert ROW_A_PIRATES["sport"] == ROW_B_PIRATES["sport"]
        assert ROW_A_PIRATES["home_team"] == ROW_B_PIRATES["home_team"]
        assert ROW_A_PIRATES["away_team"] == ROW_B_PIRATES["away_team"]

    def test_minute_key_cannot_pair_them(self):
        assert event_dup_key(ROW_A_PIRATES) != event_dup_key(ROW_B_PIRATES)
        assert find_duplicate_events([ROW_A_PIRATES, ROW_B_PIRATES]) == []

    def test_a_day_granular_key_would_not_have_saved_it_either(self):
        """Why the fix is id-anchoring and not a wider time window.

        The A row is dated 08-19 and the B row 08-17 — they do not even share a
        DAY. And the -4h offset on the B row sits inside a legitimate
        doubleheader gap, so no tolerance separates this class from a real
        second game. Widening the clock is not the answer; this pins that.
        """
        day_a = ROW_A_PIRATES["commence_time"][:10]
        day_b = ROW_B_PIRATES["commence_time"][:10]
        assert day_a != day_b

    def test_the_class_IS_caught_by_resolved_state(self):
        """The sentinel is not blind to the MECHANISM — only to the pairing.

        Both limbs below fired on these exact rows in production on 2026-08-17.
        Recording that here keeps the blind spot honest: it is a reporting gap,
        not an undetected defect.
        """
        from datetime import datetime, timezone

        now = datetime(2026, 8, 18, 0, 22, tzinfo=timezone.utc)
        assert [b["event_id"] for b in live_before_commence_events([ROW_A_PIRATES], now)] == [
            15199901
        ]
        inverted = inverted_completed_events([ROW_REDS_CROSS_MERGED])
        assert [i["event_id"] for i in inverted] == [15200380]
        assert inverted[0]["inversion_hours"] == 68.2


class TestFiledIssueKeepsItsIdentifiers:
    """#1942's actual defect: filed naming two teams and no id.

    ``event_completeness`` puts the id in the dict and not in the prose, so the
    body rendered a sentence that could not be reproduced. Recovering it needed
    a SIBLING issue's evidence JSON.
    """

    EVENT_COMPLETENESS_FAILURE = {
        "event_id": 15201122,
        "detail": (
            "live baseball_mlb game Kansas City Royals vs Athletics has zero "
            "markets in every section"
        ),
    }

    def test_structured_keys_survive_rendering(self):
        lines = render_failure_lines([self.EVENT_COMPLETENESS_FAILURE])
        assert len(lines) == 1
        assert "event_id=15201122" in lines[0]
        assert "zero markets in every section" in lines[0]

    def test_the_filed_body_carries_the_id(self):
        body = build_flow_issue_body(
            {
                "flow": "event_completeness",
                "checked": 8,
                "failures": [self.EVENT_COMPLETENESS_FAILURE],
                "evidence": {"live_tier1_sampled": 8},
            }
        )
        assert "15201122" in body

    def test_detail_only_failures_are_unchanged(self):
        """The limbs that already write ids into prose must not grow noise."""
        lines = render_failure_lines([{"detail": "plain finding"}])
        assert lines == ["- plain finding"]

    def test_cap_is_reported_not_silent(self):
        lines = render_failure_lines([{"detail": f"f{i}"} for i in range(45)])
        assert lines[-1] == "- …and 5 more"

    def test_non_dict_failures_do_not_crash(self):
        assert render_failure_lines(["bare string"]) == ["- bare string"]


class TestRedetectCommentCarriesTheFailures:
    """#1483's defect: nineteen days of "N failing. Still open."

    ``reconcile_issue``'s dedupe path is comment-only, so the body is frozen at
    first-file. The comment was the only live channel and it carried two
    integers — a flow acquiring a whole new failure class read identically to
    one standing still.
    """

    FIRST_RUN = {
        "flow": "resolved_state",
        "checked": 54,
        "failures": [{"detail": "some older finding"}, {"detail": "another older finding"}],
    }
    TONIGHTS_RUN = {
        "flow": "resolved_state",
        "checked": 49,
        "failures": [
            {
                "detail": (
                    "live baseball_mlb event Pittsburgh Pirates vs Detroit Tigers "
                    "renders LIVE but its commence_time 2026-08-19T16:35:00+00:00 is "
                    "40.2h in the FUTURE (live before start, id 15199901)"
                )
            },
            {
                "detail": (
                    "settled baseball_mlb event Cincinnati Reds vs St. Louis Cardinals "
                    "has completed_at 2026-08-17T20:26:51.558951+00:00 BEFORE "
                    "commence_time 2026-08-20T16:40:00+00:00 (68.2h inverted, id "
                    "15200380) — cross-merged event (#190/gotcha #32)"
                )
            },
        ],
    }

    def test_the_new_class_reaches_the_reader(self):
        comment = build_flow_redetect_comment(self.TONIGHTS_RUN)
        assert "15199901" in comment
        assert "15200380" in comment
        assert "68.2h inverted" in comment

    def test_it_says_the_body_is_stale(self):
        """A reader must not take the frozen body as current state."""
        comment = build_flow_redetect_comment(self.TONIGHTS_RUN)
        assert "frozen at first-file" in comment

    def test_two_runs_with_equal_counts_but_different_findings_differ(self):
        """The regression that motivated this: identical counts, different bugs.

        Both runs have exactly 2 failures. Under the old count-only comment the
        two were byte-identical apart from `checked`. They must not be now.
        """
        first = build_flow_redetect_comment(self.FIRST_RUN)
        tonight = build_flow_redetect_comment(self.TONIGHTS_RUN)
        assert len(self.FIRST_RUN["failures"]) == len(self.TONIGHTS_RUN["failures"])
        assert first != tonight
        assert "15199901" not in first

    def test_comment_is_bounded(self):
        many = {"flow": "resolved_state", "checked": 900,
                "failures": [{"detail": f"finding {i}"} for i in range(100)]}
        comment = build_flow_redetect_comment(many)
        assert "…and 80 more" in comment
        assert len(comment) < 8000


class TestProvenanceMeterTrend:
    """Ruling 048's declared cost, read twice in one evening.

    Not a behaviour assertion — a recorded measurement, so the next cycle has a
    prior value to compare against. The meter emits no history of its own, which
    is exactly why `_run_duplicate_events` refuses to infer a trend.
    """

    READINGS = [
        # (UTC timestamp, created_unanchored, reconciled, window_events)
        ("2026-08-17T23:59Z", 467, 0, 21966),
        ("2026-08-18T00:22Z", 500, 0, 21985),
    ]

    def test_nothing_has_ever_reconciled(self):
        assert all(r[2] == 0 for r in self.READINGS)

    def test_the_backlog_grew_between_the_two_reads(self):
        assert self.READINGS[1][1] > self.READINGS[0][1]
        assert self.READINGS[1][1] - self.READINGS[0][1] == 33

    def test_readings_are_json_serialisable_for_the_next_cycle(self):
        assert json.loads(json.dumps(self.READINGS))
