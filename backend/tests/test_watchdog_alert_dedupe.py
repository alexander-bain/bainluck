"""Watchdog alert dedupe — one condition, one open issue (Queue #328, #1727).

The defect these tests lock down: the watchdog's dedupe used to be a bare
``SETEX watchdog:alert:{check_name} 86400`` with NO fingerprint written into the
issue body and no reference to the board at all. A condition that stayed failing
therefore filed a brand-new issue every single day — 23 open ``[Data Quality]``
issues for 5 live conditions, six of them P0s for the one ``espn_freshness``
condition on six different days.

The acceptance test is deliberately "fire it TWICE". A single firing proves
nothing: the old code also filed exactly one issue on its first run.
"""

from unittest.mock import patch, MagicMock

from app.tasks.data_quality_watchdog import (
    _WATCHDOG_MARKER,
    _has_open_canonical,
    _watchdog_title_prefix,
    build_alert_issue_body,
    build_alert_issue_title,
    reconcile_alert_issue,
    watchdog_alert_fingerprint,
)
from app.tasks.sentinel_filing import (
    OpenIssuesResult,
    declared_fingerprints,
    find_matching_issue,
)


CHECK = {
    "name": "espn_freshness",
    "severity": "P0",
    "threshold": 1,
    "comparison": "gte",
    "message": "A live/recent ESPN-matched game produced NO ESPN win-probability snapshot",
}


class TestFingerprintIdentity:
    """The fingerprint keys on the CONDITION, not on the rendered title."""

    def test_fingerprint_is_stable_across_calls(self):
        assert watchdog_alert_fingerprint("espn_freshness") == watchdog_alert_fingerprint(
            "espn_freshness"
        )

    def test_distinct_conditions_get_distinct_fingerprints(self):
        fps = {
            watchdog_alert_fingerprint(n)
            for n in (
                "espn_freshness",
                "espn_capture_gap",
                "odds_api_sparsity",
                "mlb_win_prob_freshness",
                "calibration_publish_age",
            )
        }
        assert len(fps) == 5, "each live condition must own a distinct fingerprint"

    def test_dimension_splits_the_fingerprint(self):
        assert watchdog_alert_fingerprint("x") != watchdog_alert_fingerprint("x", "nba")

    def test_fingerprint_is_hex_so_the_shared_parser_matches_it(self):
        """The one shared declaration parser only accepts ``<marker>:<hex6-40>``.

        A raw ``check_name`` would be written into the body and then never match —
        dedupe that reads as implemented and files a duplicate every run."""
        fp = watchdog_alert_fingerprint("espn_freshness")
        assert len(fp) == 12
        assert all(c in "0123456789abcdef" for c in fp)

    def test_value_in_the_message_does_not_change_the_fingerprint(self):
        """The regression that produced #1680 and #1759 for ONE condition."""
        a = dict(CHECK, message="no calibration publish since 2026-08-02 (8.9 days)")
        b = dict(CHECK, message="no successful calibration publish in over 2 hours")
        assert build_alert_issue_title(a) != build_alert_issue_title(b)
        assert watchdog_alert_fingerprint(a["name"]) == watchdog_alert_fingerprint(b["name"])


class TestBodyDeclaration:
    """The body must DECLARE the fingerprint in the canonical parseable form."""

    def test_body_declares_a_fingerprint_the_shared_parser_recognises(self):
        body = build_alert_issue_body(CHECK, 0, "diagnosis text")
        fp = watchdog_alert_fingerprint(CHECK["name"])
        assert (_WATCHDOG_MARKER, fp) in declared_fingerprints(body)

    def test_declaration_survives_a_round_trip_through_issue_matching(self):
        body = build_alert_issue_body(CHECK, 0, "d")
        issue = {"number": 1241, "title": build_alert_issue_title(CHECK), "body": body}
        assert (
            find_matching_issue(
                [issue], watchdog_alert_fingerprint(CHECK["name"]), _WATCHDOG_MARKER
            )
            == 1241
        )

    def test_title_prefix_is_stable_under_a_changing_value(self):
        prefix = _watchdog_title_prefix(CHECK["name"])
        for msg in ("value 2 of 3", "value 91 of 400"):
            assert build_alert_issue_title(dict(CHECK, message=msg)).startswith(prefix)


class TestFireTwiceFilesOnce:
    """THE acceptance test: same condition twice → one issue carrying both."""

    def test_second_firing_comments_instead_of_filing(self):
        created: list = []
        comments: list = []

        def _create(title, body, labels):
            created.append((title, body, labels))
            return 4242, "NODE"

        with patch("app.tasks.bug_report_github.GITHUB_TOKEN", "tok"), patch(
            "app.tasks.bug_report_github.create_github_issue", side_effect=_create
        ), patch(
            "app.tasks.bug_report_github.comment_on_issue",
            side_effect=lambda n, c: comments.append((n, c)),
        ), patch(
            "app.tasks.bug_report_github.add_to_project_board", return_value=None
        ), patch(
            "app.tasks.sentinel_filing._claim_fingerprint", return_value="no_redis"
        ):
            # Firing 1 — board empty.
            first = reconcile_alert_issue(
                CHECK, 0, "d1", open_issues=OpenIssuesResult(ok=True, issues=[])
            )
            assert first["action"] == "filed", first
            assert first["issue"] == 4242

            # The issue the rail just created is now open on the board.
            board = [
                {"number": 4242, "title": created[0][0], "body": created[0][1]}
            ]

            # Firing 2 — same condition, DIFFERENT observed value.
            second = reconcile_alert_issue(
                dict(CHECK, message="still no ESPN snapshot (value 7)"),
                7,
                "d2",
                open_issues=OpenIssuesResult(ok=True, issues=board),
            )

        assert second["action"] == "commented", second
        assert second["issue"] == 4242
        assert len(created) == 1, "a second firing must NOT create a second issue"
        assert len(comments) == 1
        # The recurrence comment carries the new observation, so frequency and
        # value stay visible in one place.
        assert "7" in comments[0][1]
        assert "espn_freshness" in comments[0][1]

    def test_a_distinct_condition_still_files_its_own_issue(self):
        """Dedupe must not over-collapse — that hides a real new alarm."""
        created: list = []
        with patch("app.tasks.bug_report_github.GITHUB_TOKEN", "tok"), patch(
            "app.tasks.bug_report_github.create_github_issue",
            side_effect=lambda t, b, l: (created.append(t), (99, "N"))[1],
        ), patch(
            "app.tasks.bug_report_github.add_to_project_board", return_value=None
        ), patch(
            "app.tasks.bug_report_github.comment_on_issue", return_value=None
        ), patch(
            "app.tasks.sentinel_filing._claim_fingerprint", return_value="no_redis"
        ):
            espn_body = build_alert_issue_body(CHECK, 0, "d")
            board = [
                {
                    "number": 1241,
                    "title": build_alert_issue_title(CHECK),
                    "body": espn_body,
                }
            ]
            other = {
                "name": "odds_api_sparsity",
                "severity": "P1",
                "threshold": 0,
                "comparison": "lte",
                "message": "Active Tier 1 events have sparse snapshot coverage",
            }
            res = reconcile_alert_issue(
                other, 5, "d", open_issues=OpenIssuesResult(ok=True, issues=board)
            )
        assert res["action"] == "filed", res
        assert len(created) == 1


class TestUnreadableBoardNoOps:
    """A FAILED dedup read is not an empty board."""

    def test_failed_read_produces_dedup_unknown_no_op(self):
        with patch("app.tasks.bug_report_github.GITHUB_TOKEN", "tok"), patch(
            "app.tasks.bug_report_github.create_github_issue"
        ) as create, patch(
            "app.tasks.bug_report_github.comment_on_issue"
        ) as comment:
            res = reconcile_alert_issue(
                CHECK,
                0,
                "d",
                open_issues=OpenIssuesResult(ok=False, error="rate limited"),
            )
        assert res["action"] == "dedup_unknown_no_op", res
        create.assert_not_called()
        comment.assert_not_called()

    def test_truncated_read_also_no_ops(self):
        with patch("app.tasks.bug_report_github.GITHUB_TOKEN", "tok"), patch(
            "app.tasks.bug_report_github.create_github_issue"
        ) as create:
            res = reconcile_alert_issue(
                CHECK,
                0,
                "d",
                open_issues=OpenIssuesResult(
                    ok=False, issues=[], truncated=True, error="truncated"
                ),
            )
        assert res["action"] == "dedup_unknown_no_op"
        create.assert_not_called()


class TestRateLimiterIsNotTheFilingGate:
    """The 24h TTL may suppress a COMMENT; it must never suppress a FILE."""

    def test_has_open_canonical_true_when_declared_issue_is_open(self):
        board = [
            {
                "number": 1241,
                "title": build_alert_issue_title(CHECK),
                "body": build_alert_issue_body(CHECK, 0, "d"),
            }
        ]
        assert _has_open_canonical("espn_freshness", OpenIssuesResult(ok=True, issues=board))

    def test_has_open_canonical_false_when_board_is_empty(self):
        assert not _has_open_canonical(
            "espn_freshness", OpenIssuesResult(ok=True, issues=[])
        )

    def test_unreadable_board_is_not_treated_as_already_handled(self):
        """An unknown resolved into 'already handled' is how a condition goes
        unfiled during an outage. It must fall through to the rail."""
        assert not _has_open_canonical(
            "espn_freshness", OpenIssuesResult(ok=False, error="boom")
        )
        assert not _has_open_canonical("espn_freshness", None)

    def test_other_conditions_issue_does_not_satisfy_this_condition(self):
        board = [
            {
                "number": 1241,
                "title": build_alert_issue_title(CHECK),
                "body": build_alert_issue_body(CHECK, 0, "d"),
            }
        ]
        assert not _has_open_canonical(
            "odds_api_sparsity", OpenIssuesResult(ok=True, issues=board)
        )
