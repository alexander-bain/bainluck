"""Replay the affected changes at 9:41 AM PT on November 19."""

from datetime import timedelta
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect import collect_pull, hold_for_108, reconcile_commands
from model import build, instant, iso
from notes import caption_facts
from signals import commands_from, on_floor


class MorningReplay(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parent / "fixtures/morning-nov19.json"
        self.fixture = json.loads(path.read_text())
        self.now = instant(self.fixture["captured_at"])
        self.pulls = {p["number"]: p for p in self.fixture["pulls"]}
        self.pulls[13070]["hold_for_108"] = hold_for_108(
            self.fixture["held_description"]
        )
        self.posts = self.fixture["posts"]
        self.previous = {
            "observed_since": "2026-11-18T15:00:00Z",
            "signals": {"last_merged_at": self.fixture["prior_merges"]},
        }

    def replay(self, *, posts=None, deployments=None, previous=None):
        commands = commands_from(self.posts if posts is None else posts)
        return build(
            {
                **self.fixture,
                "pulls": list(self.pulls.values()),
                "deployments": (
                    self.fixture["deployments"] if deployments is None else deployments
                ),
                "commands": commands,
            },
            self.previous if previous is None else previous,
        )

    @staticmethod
    def placement(floor, number):
        return {c["line"]: c for c in floor["changes"] if c["number"] == number}

    def test_13069_is_live_on_both_announced_lines_and_updates_website_clock(self):
        self.pulls[13069]["files_complete"] = False
        floor = self.replay()
        rows = self.placement(floor, 13069)
        self.assertEqual(set(rows), {"Website", "Apps"})
        self.assertEqual(rows["Website"]["live_at"], "2026-11-19T15:33:15Z")
        self.assertEqual(rows["Apps"]["live_at"], "2026-11-19T15:45:44Z")
        self.assertEqual(rows["Apps"]["testflight_build"], 5811)
        self.assertNotIn("testflight_build", rows["Website"])
        self.assertTrue(
            all(c["station"] == "Live" and not c["unsure"] for c in rows.values())
        )
        website = next(
            s
            for s in floor["stops"]
            if s["kind"] == "line-stalled" and s["line"] == "Website"
        )
        self.assertEqual(website["since"], "2026-11-19T15:30:38Z")
        self.assertEqual(website["number"], 13058)
        facts = caption_facts(floor, self.pulls.values())
        self.assertEqual(facts["counts"]["live"], 1)
        self.assertEqual(facts["stations"]["Live"]["count"], 1)

    def test_file_fallback_uses_separate_receipts_and_retires_wrong_server_count(self):
        first = self.replay(posts=[])
        old_server = {
            **self.placement(first, 13069)["Website"],
            "line": "Server",
            "live_at": "2026-11-19T15:54:08.902374Z",
        }
        prior = {
            **self.previous,
            "changes": [old_server],
            "signals": {"last_merged_at": {"Server": old_server["merged_at"]}},
        }
        only_website = [
            d for d in self.fixture["deployments"] if d["line"] == "Website"
        ]
        second = self.replay(posts=[], deployments=only_website, previous=prior)
        rows = self.placement(second, 13069)
        self.assertEqual(set(rows), {"Website", "Apps"})
        self.assertEqual(rows["Website"]["station"], "Live")
        self.assertEqual(rows["Apps"]["station"], "Ship")
        self.assertIsNone(rows["Apps"]["live_at"])
        self.assertNotIn("Server", second["signals"]["last_merged_at"])

    def test_12873_returns_to_loading_dock_after_the_904_refusal(self):
        before = self.replay(posts=self.posts[:3])
        self.assertEqual(self.placement(before, 12873)["Server"]["station"], "Ship")
        after = self.replay(previous=before)
        self.assertEqual(
            self.placement(after, 12873)["Server"]["station"], "Merge line"
        )
        self.assertTrue(
            any(
                (t["number"], t["line"], t["from"], t["to"])
                == (12873, "Server", "Ship", "Merge line")
                for t in after["transitions"]
            )
        )
        self.assertFalse(any(s["kind"] == "announced" for s in after["stops"]))

    def test_refusal_only_cancels_its_own_changes_and_a_new_turn_can_dispatch(self):
        merge = {
            **self.posts[2],
            "body": "merging #12873, #13058 (server, website)",
        }
        floor = self.replay(posts=[merge, *self.posts[3:]])
        self.assertTrue(
            all(
                c["station"] == "Merge line"
                for c in self.placement(floor, 12873).values()
            )
        )
        self.assertTrue(
            all(c["station"] == "Ship" for c in self.placement(floor, 13058).values())
        )
        retry = {**merge, "created_at": "2026-11-19T17:40:00Z"}
        floor = self.replay(posts=[merge, *self.posts[3:], retry])
        self.assertTrue(
            all(c["station"] == "Ship" for c in self.placement(floor, 12873).values())
        )

    def test_cached_merge_routes_survive_new_announcements_and_cutoffs(self):
        commands = commands_from(self.posts)
        replacement = {
            "kind": "merging",
            "line": "Website",
            "at": "2026-11-19T17:40:00Z",
            "numbers": [13058],
        }
        pulls = list(self.pulls.values())
        saved = reconcile_commands([*commands, replacement], pulls, self.previous)
        self.assertEqual(
            {
                c["line"]
                for c in saved
                if c["kind"] == "merging" and 13069 in c["numbers"]
            },
            {"Apps", "Website"},
        )
        self.assertIn(
            {
                "kind": "stuck",
                "line": None,
                "numbers": [12873],
                "at": "2026-11-19T17:04:34Z",
            },
            saved,
        )
        self.assertEqual(
            reconcile_commands([], pulls, {"signals": {"commands": saved}}),
            saved,
        )

    def test_13070_moves_from_the_apps_dock_to_the_release_shelf(self):
        pull = self.pulls[13070]
        pull["hold_for_108"] = False
        before = self.replay()
        self.assertTrue(on_floor(self.placement(before, 13070)["Apps"]))
        self.assertTrue(any(s.get("number") == 13070 for s in before["stops"]))

        pull["hold_for_108"] = True
        after = self.replay()
        held = self.placement(after, 13070)["Apps"]
        self.assertTrue(held["held_for_108"])
        self.assertFalse(on_floor(held))
        self.assertFalse(any(s["line"] == "Apps" for s in after["stops"]))

        # Exercise inspection too, with this change's checks green for 3 hours
        # and no approval yet.
        pull["reviews"] = []
        pull["checks"][0]["finished_at"] = iso(self.now - timedelta(hours=3))
        self.assertFalse(any(s["line"] == "Apps" for s in self.replay()["stops"]))
        pull["hold_for_108"] = False
        self.assertTrue(
            any(
                s["kind"] == "review-waiting" and s["number"] == 13070
                for s in self.replay()["stops"]
            )
        )

    def test_current_description_sets_and_clears_108_hold_on_a_cached_head(self):
        pull = self.pulls[13070]
        summary = {**pull, "head": {"ref": pull["branch"], "sha": pull["head_sha"]}}
        for phrase in (
            self.fixture["held_description"],
            "Held for 1.0.8",
            "Holds merge until after Mon Nov 23 1.0.7 freeze",
        ):
            with self.subTest(phrase=phrase):
                cached = collect_pull(None, {**summary, "body": phrase}, pull)
                self.assertTrue(cached["hold_for_108"])
                self.assertNotIn("body", cached)
        for phrase in (
            "Targets 1.0.8",
            "No longer held for 1.0.8",
            "Hold merge until CI is green",
        ):
            with self.subTest(phrase=phrase):
                self.assertFalse(
                    collect_pull(None, {**summary, "body": phrase}, pull)[
                        "hold_for_108"
                    ]
                )

    def test_drafts_park_at_48_hours_and_return_to_the_bench_on_new_activity(self):
        draft = self.pulls[12621]
        parked = self.placement(self.replay(), 12621)["Server"]
        self.assertEqual(parked["last_activity"], "2026-11-11T22:31:12Z")
        self.assertTrue(parked["parked"])
        self.assertFalse(on_floor(parked))

        draft["updated_at"] = iso(self.now - timedelta(hours=48))
        boundary = self.placement(self.replay(), 12621)["Server"]
        self.assertTrue(boundary["parked"])
        self.assertFalse(boundary["side_track"])
        draft["updated_at"] = iso(instant(draft["updated_at"]) + timedelta(seconds=1))
        active = self.placement(self.replay(), 12621)["Server"]
        self.assertEqual(active["station"], "Write")
        self.assertTrue(on_floor(active))
