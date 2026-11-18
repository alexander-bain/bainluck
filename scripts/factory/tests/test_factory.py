"""Real response replay plus explicitly labelled counterfactual gate controls."""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/factory"))
from model import (
    advance_jams,
    build,
    checks_green,
    classify,
    instant,
    iso,
    line_for,
    public_title,
)
from collect import is_review_bot

FIXTURES = Path(__file__).parent / "fixtures"


class FactoryRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads((FIXTURES / "github.json").read_text())
        cls.expected = json.loads((FIXTURES / "expected.json").read_text())
        cls.now = instant(cls.snapshot["captured_at"])

    def sample(self):
        return deepcopy(self.snapshot["pulls"][0])

    def ready(self):
        pull = self.sample()
        pull.update(
            state="open",
            draft=False,
            merged_at=None,
            files=["frontend/app/factory/page.tsx"],
            files_complete=True,
            checks_complete=True,
            checks=[
                {
                    "app": "github-actions",
                    "name": "tests",
                    "state": "completed",
                    "conclusion": "success",
                }
            ],
            reviews_complete=True,
            commits_complete=True,
            comments_complete=True,
            fable_needed=False,
        )
        pull["reviews"] = [
            {
                "login": "claude[bot]",
                "commit_id": pull["head_sha"],
                "state": "APPROVED",
                "submitted_at": iso(self.now),
            }
        ]
        return pull

    def place(self, pull):
        return classify(pull, self.snapshot["deployments"], self.now)

    def test_saved_real_github_responses_place_at_least_twelve_changes(self):
        self.assertGreaterEqual(len(self.expected["placements"]), 12)
        self.assertEqual(
            {v[0] for v in self.expected["placements"].values()},
            {"Write", "Test", "Review", "Merge line", "Ship", "Live"},
        )
        results = {c["number"]: c for c in build(self.snapshot)["changes"]}
        for number, expected in self.expected["placements"].items():
            with self.subTest(change=number):
                result = results[int(number)]
                self.assertEqual(
                    [result["station"], result["line"], result["unsure"]], expected
                )

    def test_saved_merge_event_precedes_saved_live_receipt(self):
        case = self.expected["shipping_replay"]
        pull = next(p for p in self.snapshot["pulls"] if p["number"] == case["number"])
        moment = instant(pull["merged_at"]) + timedelta(milliseconds=1)
        receipts = [
            r for r in self.snapshot["deployments"] if instant(r["at"]) <= moment
        ]
        self.assertEqual(classify(pull, receipts, moment)["station"], "Ship")
        self.assertEqual(self.place(pull)["station"], "Live")

    def test_draft_precedes_all_other_gates(self):
        pull = self.ready()
        pull.update(draft=True, checks_complete=False)
        self.assertEqual(self.place(pull)["station"], "Write")

    def test_pending_failing_cancelled_missing_and_latest_rerun_checks(self):
        for state, conclusion in [
            ("in_progress", None),
            ("completed", "failure"),
            ("completed", "cancelled"),
        ]:
            pull = self.ready()
            pull["checks"][0].update(state=state, conclusion=conclusion)
            self.assertEqual(self.place(pull)["station"], "Test")
        pull["checks"] = []
        self.assertTrue(self.place(pull)["unsure"])
        pull = self.ready()
        first = {**pull["checks"][0], "started_at": "2026-11-17T10:00:00Z"}
        pull["checks"] = [
            first,
            {
                **first,
                "state": "in_progress",
                "conclusion": None,
                "started_at": "2026-11-17T11:00:00Z",
            },
        ]
        self.assertEqual(checks_green(pull), (False, False))

    def test_approval_is_bound_to_exact_head_and_can_be_dismissed(self):
        pull = self.ready()
        pull["reviews"][0]["commit_id"] = "an-older-commit"
        self.assertEqual(self.place(pull)["station"], "Review")
        pull = self.ready()
        pull["reviews"][0]["state"] = "DISMISSED"
        self.assertEqual(self.place(pull)["station"], "Review")
        pull = self.ready()
        self.assertEqual(self.place(pull)["station"], "Merge line")

    def test_graphql_bot_identity_matches_rest_without_accepting_a_human(self):
        # GitHub's real 12892 GraphQL response has Bot/login=claude. Its REST
        # review response uses user.login=claude[bot].
        self.assertTrue(is_review_bot({"__typename": "Bot", "login": "claude"}))
        self.assertFalse(is_review_bot({"__typename": "User", "login": "claude"}))
        self.assertFalse(is_review_bot(None))

    def test_a_pending_retry_does_not_clear_a_recorded_failure(self):
        first = advance_jams(
            [], {"tests": "failing", "testflight": "failure"}, [], self.now
        )
        pending = advance_jams(
            [],
            {"tests": "running", "testflight": "pending"},
            first,
            self.now + timedelta(minutes=1),
        )
        self.assertTrue(all(j["ended_at"] is None for j in pending))

    def test_fable_acceptance_follows_last_non_merge_commit_and_is_trusted(self):
        pull = self.ready()
        pull.update(
            fable_needed=True,
            commits=[
                {"parents": 1, "at": "2026-11-17T10:00:00Z"},
                {"parents": 2, "at": "2026-11-17T12:00:00Z"},
            ],
        )
        pull["comments"] = [
            {
                "fable_accept": True,
                "association": "OWNER",
                "created_at": "2026-11-17T11:00:00Z",
            }
        ]
        self.assertEqual(self.place(pull)["station"], "Merge line")
        pull["comments"][0]["association"] = "NONE"
        self.assertEqual(self.place(pull)["station"], "Review")
        pull["comments"][0].update(
            association="OWNER", created_at="2026-11-17T09:00:00Z"
        )
        self.assertEqual(self.place(pull)["station"], "Review")
        pull["commits_complete"] = False
        self.assertTrue(self.place(pull)["unsure"])

    def test_file_routing_and_unknown_file_list(self):
        pull = self.ready()
        for paths, line in [
            (["ios/Bain Luck/View.swift"], "Apps"),
            (["frontend/app/a.tsx"], "Website"),
            (["frontend/a.tsx", "ios/a.swift"], "Server"),
            (["scripts/a.py"], "Server"),
        ]:
            pull["files"] = paths
            self.assertEqual(line_for(pull), (line, False))
        pull["files_complete"] = False
        self.assertEqual(line_for(pull), ("Server", True))
        self.assertEqual(self.place(pull)["station"], "Review")

    def test_side_track_uses_latest_activity_and_keeps_original_station(self):
        pull = self.ready()
        pull.update(
            updated_at=iso(self.now - timedelta(days=3)), comments=[], reviews=[]
        )
        self.assertTrue(self.place(pull)["side_track"])
        pull["comments"] = [
            {
                "updated_at": iso(self.now - timedelta(minutes=2)),
                "created_at": iso(self.now - timedelta(minutes=2)),
            }
        ]
        self.assertFalse(self.place(pull)["side_track"])

    def test_crowding_requires_ten_changes_for_thirty_minutes_and_records_end(self):
        changes = [
            {
                **self.place(self.ready()),
                "number": p["number"],
                "station": "Test",
                "side_track": False,
            }
            for p in self.snapshot["pulls"][:10]
        ]
        start = advance_jams(changes, {}, [], self.now)
        crowd = next(j for j in start if j["kind"] == "crowd")
        self.assertEqual(
            instant(crowd["qualifies_at"]) - self.now, timedelta(minutes=30)
        )
        short = advance_jams([], {}, start, self.now + timedelta(minutes=29))
        self.assertFalse(any(j["kind"] == "crowd" for j in short))
        ended = advance_jams([], {}, start, self.now + timedelta(minutes=31))
        self.assertIsNotNone(next(j for j in ended if j["kind"] == "crowd")["ended_at"])

    def test_master_failure_and_testflight_cancelled_or_failed_jams(self):
        for flight in ("cancelled", "failure", "error", "timed_out"):
            jams = advance_jams(
                [], {"tests": "failing", "testflight": flight}, [], self.now
            )
            self.assertEqual({j["kind"] for j in jams}, {"master", "testflight"})
            cleared = advance_jams(
                [],
                {"tests": "passing", "testflight": "success"},
                jams,
                self.now + timedelta(minutes=2),
            )
            self.assertTrue(all(j["ended_at"] for j in cleared))

    def test_empty_merge_line_clock_is_separate_for_each_delivery_line(self):
        change = {**self.place(self.ready()), "station": "Review", "side_track": False}
        jams = advance_jams([change], {}, [], self.now)
        self.assertEqual([(j["line"], j["kind"]) for j in jams], [("Website", "empty")])
        self.assertEqual(
            instant(jams[0]["qualifies_at"]) - self.now, timedelta(minutes=15)
        )
        end = advance_jams(
            [{**change, "station": "Merge line"}],
            {},
            jams,
            self.now + timedelta(minutes=20),
        )
        self.assertIsNotNone(end[0]["ended_at"])

    def test_replays_keep_first_sighting_and_do_not_double_count(self):
        first = build(self.snapshot)
        second = build(self.snapshot, first)
        self.assertEqual(first["changes"], second["changes"])
        self.assertEqual(first["observed_since"], second["observed_since"])

    def test_privacy_projection_excludes_discussion_and_author_data(self):
        public = json.dumps(build(self.snapshot))
        self.assertNotIn('"login"', public)
        self.assertNotIn('"body"', public)
        self.assertNotIn('"files"', public)
        self.assertEqual(
            public_title("Ask Alex @example about test@example.com"),
            "Ask the founder [account removed] about [email removed]",
        )

    def test_event_only_release_publication_cannot_push_code(self):
        workflow = (ROOT / ".github/workflows/factory.yml").read_text()
        for event in (
            "pull_request:",
            "pull_request_review:",
            "workflow_run:",
            "status:",
            "issue_comment:",
            "workflow_dispatch:",
        ):
            self.assertIn(event, workflow)
        self.assertNotIn("cron:", workflow)
        self.assertIn("github.event.issue.number == 12779", workflow)
        self.assertIn("github.event.workflow_run.name != 'The Factory'", workflow)
        collector = (ROOT / "scripts/factory/collect.py").read_text()
        for verb in ('"push"', '"commit"', '"update-ref"'):
            self.assertNotIn('["git", ' + verb, collector)
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            if path.name != "factory.yml":
                self.assertNotRegex(path.read_text(), r"(?m)^  release:")
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertNotIn("secrets.", workflow)


if __name__ == "__main__":
    unittest.main()
