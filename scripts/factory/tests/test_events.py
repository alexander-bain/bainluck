from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect import deployment_start
from events import add_events


class FloorEvents(unittest.TestCase):
    def setUp(self):
        self.number = 12969
        self.before = "2026-11-18T23:40:00Z"
        self.now = "2026-11-18T23:44:00Z"
        self.change = {
            "number": self.number,
            "line": "Server",
            "builder": "B",
            "station": "Test",
            "live_at": None,
            "merged_at": None,
        }
        self.floor = {"generated_at": self.now, "changes": [self.change]}
        self.previous = {
            "generated_at": self.before,
            "changes": [deepcopy(self.change)],
        }
        self.pull = {
            "number": self.number,
            "created_at": self.before,
            "head_sha": "new",
            "commits_complete": True,
            "checks_complete": True,
            "comments_complete": True,
            "reviews_complete": True,
            "commits": [{"sha": "new", "at": "2026-11-18T23:41:00Z"}],
        }

    def test_a_new_commit_and_each_finished_check_get_one_event_per_change(self):
        self.floor["changes"].append({**self.change, "line": "Website"})
        self.pull["checks"] = [
            {
                "name": "tests",
                "state": "completed",
                "conclusion": "success",
                "finished_at": "2026-11-18T23:42:00Z",
            },
            {
                "name": "build",
                "state": "completed",
                "conclusion": "failure",
                "finished_at": "2026-11-18T23:43:00Z",
            },
            {"name": "lint", "state": "in_progress"},
        ]
        prior = {
            **self.pull,
            "head_sha": "old",
            "commits": [{"sha": "old"}],
            "checks": [],
        }
        add_events(
            self.floor, {"pulls": [self.pull]}, self.previous, {str(self.number): prior}
        )
        self.assertEqual(
            [e["kind"] for e in self.floor["events"]], ["commit", "check", "check"]
        )
        self.assertEqual(
            [(e["done"], e["total"], e["outcome"]) for e in self.floor["events"][1:]],
            [(1, 3, "passed"), (2, 3, "failed")],
        )
        self.assertEqual(
            self.floor["changes"][1]["check_progress"], {"done": 2, "total": 3}
        )
        self.assertNotIn("lint", str(self.floor["events"]))
        following = dict(self.floor, generated_at="2026-11-18T23:44:20Z")
        add_events(
            following, {"pulls": [self.pull]}, self.floor, {str(self.number): self.pull}
        )
        self.assertEqual(following["events"], self.floor["events"])

    def test_trusted_review_and_the_return_use_their_recorded_times(self):
        fable = "2026-11-18T23:43:30Z"
        self.pull["comments"] = [
            {"created_at": fable, "association": "OWNER", "fable_changes": True}
        ]
        self.pull["reviews"] = [
            {
                "state": "APPROVED",
                "login": "claude[bot]",
                "commit_id": "new",
                "submitted_at": "2026-11-18T23:42:00Z",
            }
        ]
        self.change.update(station="Write", sent_back=True)
        self.floor["transitions"] = [
            {
                "number": self.number,
                "line": "Server",
                "from": "Review",
                "to": "Write",
                "at": self.before,
                "observed_at": self.now,
            }
        ]
        prior = {**self.pull, "comments": [], "reviews": []}
        add_events(
            self.floor, {"pulls": [self.pull]}, self.previous, {str(self.number): prior}
        )
        self.assertEqual(
            [(e["kind"], e["at"]) for e in self.floor["events"]],
            [("bot", "2026-11-18T23:42:00Z"), ("returned", fable)],
        )

    def test_merge_deploy_and_live_remain_three_separately_proven_events(self):
        self.previous["changes"][0]["station"] = "Merge line"
        self.change.update(
            station="Live",
            merged_at="2026-11-18T23:41:00Z",
            live_at="2026-11-18T23:43:00Z",
        )
        self.pull.update(merged_at=self.change["merged_at"], merge_commit_sha="merge")
        origins = [
            {"line": "Server", "contains": ["wrong"], "at": "2026-11-18T23:41:05Z"},
            {"line": "Server", "contains": ["merge"], "at": "2026-11-18T23:42:00Z"},
        ]
        add_events(
            self.floor,
            {"pulls": [self.pull], "deploy_starts": origins},
            self.previous,
            {},
        )
        self.assertEqual(
            [e["kind"] for e in self.floor["events"]], ["merge", "deploy", "live"]
        )
        self.assertEqual(self.floor["events"][0]["from"], "Merge line")
        self.assertEqual(self.floor["events"][1]["at"], origins[1]["at"])

    def test_generic_pending_status_and_skipped_deploy_cannot_start_a_truck(self):
        status = {"context": "Vercel", "state": "PENDING", "createdAt": self.now}
        self.assertIsNone(deployment_start(status))
        self.assertEqual(
            deployment_start({**status, "description": "Vercel is deploying your app"}),
            ("Website", self.now),
        )
        check = {
            "name": "deploy",
            "status": "COMPLETED",
            "conclusion": "SKIPPED",
            "startedAt": self.now,
            "checkSuite": {"workflowRun": {"workflow": {"name": "CI"}}},
        }
        self.assertIsNone(deployment_start(check))
