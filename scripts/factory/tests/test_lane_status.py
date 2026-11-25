"""Fixed NOW input controls and the two November 22 Apps deliveries."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crew import add_crew_week
from model import build, classify, instant
from signals import lane_updates_from
from speech import lane_facts


class LaneStatusTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parent / "fixtures" / "nov22-lane-status.json"
        self.fixture = json.loads(path.read_text())
        self.now = instant(self.fixture["observed_at"])
        self.posts = self.fixture["now_posts"]

    def test_fixed_trusted_lines_strip_links_and_ignore_invalid_overrides(self):
        self.assertEqual(lane_updates_from(reversed(list(self.posts.values())), self.now), {
            "F": {"at": self.posts["good"]["created_at"], "text": "retaking the iPad screenshots from build 5852"},
            "C": {"at": self.posts["link"]["created_at"], "text": "checking the screenshots"},
        })

    def test_account_identifiers_and_email_are_removed_from_the_statement(self):
        address = "test-inbox" + chr(64) + "example.invalid"
        post = {**self.posts["good"], "user": {"login": "internal-handle"},
                "body": "Factory now: checking the handoff @unused internal-handle " + address}
        self.assertEqual(lane_updates_from([post], self.now)["Factory"]["text"], "checking the handoff")

    def test_latest_plain_line_wins_and_quotes_or_expired_lines_are_ignored(self):
        first = self.posts["good"]
        last = {**first, "created_at": "2026-11-22T19:50:00Z",
                "body": "Builder F now: checking the finished iPad screenshots"}
        quoted = {**last, "created_at": "2026-11-22T19:54:00Z", "body":
                  "\n".join(["> " + first["body"], "\x60" + first["body"] + "\x60",
                             "\x60\x60\x60", first["body"], "\x60\x60\x60"])}
        outdated = {**first, "created_at": "2026-11-22T16:54:59Z", "body": "Speed now: checking the result"}
        self.assertEqual(lane_updates_from([outdated, quoted, last, first], self.now), {
            "F": {"at": last["created_at"], "text": "checking the finished iPad screenshots"},
        })

    def test_apps_delivery_receipts_credit_builder_c_for_both_changes(self):
        floor = build({
            "captured_at": self.fixture["observed_at"],
            "pulls": self.fixture["pulls"],
            "deployments": self.fixture["deployments"],
            "master": {"tests": "passing", "testflight": "success"},
        })
        self.assertEqual(
            [(c["number"], c["builder"], c["line"], c["station"]) for c in floor["changes"]],
            [(13423, "C", "Apps", "Live"), (13427, "C", "Apps", "Live")],
        )
        add_crew_week(floor, self.fixture["pulls"])
        self.assertEqual(floor["crew_week"]["builders"]["C"]["changes"], 2)

    def test_lane_prefixes_keep_one_speech_lane_and_never_share_factory_credit(self):
        pull = self.fixture["pulls"][0]
        for prefix, builder in (("ios/", "C"), ("bc/", "C"), ("factory/", "Factory"), ("factory-misc/", "Other")):
            with self.subTest(prefix=prefix):
                self.assertEqual(classify(
                    {**pull, "branch": prefix + "test"},
                    self.fixture["deployments"], self.now, "Apps", False,
                )["builder"], builder)
        facts = lane_facts({"generated_at": self.fixture["observed_at"], "changes": [],
                            "lane_updates": lane_updates_from([self.posts["good"]], self.now)})
        self.assertEqual(list(facts).count("C"), 1)
        self.assertIn("Factory", facts)
        self.assertNotIn("screenshots", json.dumps(facts))
