"""Replay trimmed exact-head and TestFlight evidence from November 22."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect import safe_comment
from events import add_events
from model import build
from signals import commands_from


class CurrentSignals(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parent / "fixtures" / "nov22-factory-signals.json"
        self.fixture = json.loads(path.read_text())
        self.pull = self.fixture["pull"]
        self.raw_accept = self.fixture["fable_accept"]
        self.pull["comments"] = [safe_comment(self.raw_accept)]
        self.snapshot = {
            "captured_at": self.fixture["observed_at"],
            "pulls": [self.pull],
            "deployments": self.fixture["testflight_statuses"],
            "master": {"tests": "passing", "testflight": "success"},
            "commands": commands_from(self.fixture["testflight_reports"]),
        }

    def test_13396_moves_from_review_after_fables_exact_head_accept(self):
        without_sha = deepcopy(self.snapshot)
        without_sha["pulls"][0]["comments"][0].pop("fable_accept_sha")
        before = build(without_sha)
        self.assertEqual(before["changes"][0]["station"], "Review")
        self.assertTrue(any(stop["kind"] == "review-waiting" for stop in before["stops"]))

        after = build(self.snapshot, before)
        add_events(after, self.snapshot, before, {})
        self.assertEqual(after["changes"][0]["station"], "Merge line")
        self.assertEqual(after["changes"][0]["approvals"], {"fable": self.raw_accept["created_at"]})
        self.assertFalse(any(stop["kind"] == "review-waiting" for stop in after["stops"]))

    def test_exact_accept_preserves_draft_checks_trust_and_newer_changes(self):
        release = self.pull["comments"][0]
        checks = self.pull["checks"][0]
        self.pull["draft"] = True
        self.assertEqual(build(self.snapshot)["changes"][0]["station"], "Write")
        self.pull["draft"] = False
        checks["conclusion"] = "failure"
        self.assertEqual(build(self.snapshot)["changes"][0]["station"], "Test")
        checks["conclusion"] = "success"

        for invalid in ({"association": "NONE"}, {"fable_accept_sha": self.pull["commits"][0]["sha"]}):
            self.pull["comments"] = [{**release, **invalid}]
            self.assertEqual(build(self.snapshot)["changes"][0]["station"], "Review")
        self.pull["comments"] = [release, safe_comment({
            **self.raw_accept, "body": "**Fable: CHANGES**",
            "created_at": "2026-11-22T00:35:00Z", "updated_at": "2026-11-22T00:35:00Z",
        })]
        change = build(self.snapshot)["changes"][0]
        self.assertEqual(change["station"], "Write")
        self.assertTrue(change["sent_back"])

    def test_5849_requires_a_successful_master_status_and_beats_older_mentions(self):
        older, current = self.fixture["testflight_reports"]
        later = "2026-11-22T14:30:00Z"
        self.snapshot["commands"] = commands_from([
            older, current,
            {**older, "created_at": later},
            {**current, "created_at": later, "body": "Awaiting TestFlight build 5850 on `9b1d7491b2`."},
            {**current, "created_at": later, "author_association": "NONE", "body":
                "Latest TestFlight build is `1.0.7 (5850)` on `f76a840256`."},
        ])
        expected = {
            "build": 5849, "at": current["created_at"],
            "commit": "f76a84025691c21db9929fcd6d588cef265c1a47",
        }
        floor = build(self.snapshot)
        self.assertEqual(floor["signals"]["testflight_post"], expected)
        self.snapshot["commands"] = []
        self.assertEqual(build(self.snapshot, floor)["signals"]["testflight_post"], expected)
        self.snapshot["deployments"] = self.snapshot["deployments"][:1]
        self.assertNotIn("testflight_post", build(self.snapshot, floor)["signals"])

    def test_a_build_report_cannot_prove_a_newer_pending_build(self):
        latest = self.fixture["testflight_reports"][-1]
        pending = "9b1d7491b2c59b85a08ee62abc8f034504b4db2c"
        self.snapshot["commands"] += commands_from([{
            **latest, "body": "Latest TestFlight build is `1.0.7 (5850)` on `9b1d7491b2`."
        }])
        self.snapshot["deployments"].append({
            "line": "Apps", "state": "pending", "commit": pending,
            "committed_at": "2026-11-22T06:55:16Z", "at": "2026-11-22T14:00:00Z",
            "contains": [],
        })
        self.assertEqual(build(self.snapshot)["signals"]["testflight_post"]["build"], 5849)

    def test_builder_c_build_report_requires_the_fixed_line(self):
        informal, *fixed = self.fixture["build_report_wording"]
        self.assertEqual(commands_from([informal]), [])
        self.assertEqual(
            [(post["build"], post["commit"]) for post in commands_from(fixed)],
            [(5850, "865d44c9ac"), (5851, "b248129f30"), (5852, "8abcd1cea9")],
        )
