from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import build, instant, unchanged_after
from signals import commands_from, reader_behind, stopped_rules, test_file


class FactoryStops(unittest.TestCase):
    def setUp(self):
        self.now = instant("2026-11-18T18:00:00Z")
        self.waiting = {
            "number": 12971,
            "line": "Server",
            "station": "Merge line",
            "station_since": "2026-11-18T16:00:00Z",
            "merged_at": None,
        }

    def stops(self, changes=None, commands=None, master=None, last=None):
        return stopped_rules(
            changes or [self.waiting],
            commands or [],
            master or {},
            last or {},
            "2026-11-18T17:45:00Z",
            self.now,
        )

    def test_a_line_stalled_after_thirty_minutes(self):
        self.assertEqual(
            self.stops(last={"Server": "2026-11-18T17:30:00Z"})[0]["kind"],
            "line-stalled",
        )
        self.assertEqual(self.stops(last={"Server": "2026-11-18T17:30:01Z"}), [])

    def test_b_latest_announcement_without_any_merge_after_fifteen_minutes(self):
        command = {
            "kind": "merging",
            "line": "Server",
            "numbers": [12971, 12974],
            "at": "2026-11-18T17:45:00Z",
        }
        self.assertEqual(self.stops(commands=[command])[0]["kind"], "announced")
        merged = {
            **self.waiting,
            "number": 12974,
            "station": "Ship",
            "merged_at": "2026-11-18T17:50:00Z",
        }
        self.assertEqual(
            self.stops(changes=[self.waiting, merged], commands=[command]), []
        )

    def test_c_hold_lasts_until_a_later_live_line_for_that_line(self):
        hold = {"kind": "hold", "line": "Server", "at": "2026-11-18T17:00:00Z"}
        self.assertEqual(self.stops(commands=[hold])[0]["kind"], "hold")
        live = {"kind": "live", "line": "Server", "at": "2026-11-18T17:30:00Z"}
        self.assertEqual(self.stops(commands=[hold, live]), [])
        self.assertEqual(self.stops(commands=[live, hold]), [])
        live["line"] = "Apps"
        self.assertEqual(self.stops(commands=[hold, live])[0]["kind"], "hold")

    def test_d_failed_latest_completed_master_run_stops_testing(self):
        stop = self.stops(
            master={"tests": "failing", "tests_at": "2026-11-18T17:20:00Z"}
        )[0]
        self.assertEqual(
            (stop["kind"], stop["station"], stop["since"]),
            ("master", "Test", "2026-11-18T17:20:00Z"),
        )
        self.assertEqual(self.stops(master={"tests": "passing"}), [])

    def test_e_review_wait_over_two_hours_is_amber(self):
        review = {
            **self.waiting,
            "station": "Review",
            "station_since": "2026-11-18T15:59:59Z",
            "last_activity": "2026-11-16T18:00:00Z",
        }
        self.assertEqual(self.stops(changes=[review])[0]["level"], "amber")
        review["station_since"] = "2026-11-18T16:00:00Z"
        self.assertEqual(self.stops(changes=[review]), [])

    def test_review_wait_uses_readiness_and_excludes_parked_changes(self):
        opened = "2026-11-03T17:00:00Z"
        ready = "2026-11-18T15:00:00Z"
        parked = {
            "number": 12001,
            "title": "Older change",
            "branch": "codex/older-change",
            "state": "open",
            "draft": False,
            "created_at": opened,
            "updated_at": opened,
            "files": ["backend/app/main.py"],
            "files_complete": True,
            "checks_complete": True,
            "reviews_complete": True,
            "checks": [
                {
                    "name": "CI",
                    "app": "github-actions",
                    "state": "completed",
                    "conclusion": "success",
                    "finished_at": opened,
                }
            ],
        }
        active = {
            **parked,
            "number": 12002,
            "title": "Recently ready change",
            "review_resumed_at": ready,
            "updated_at": "2026-11-18T16:30:00Z",
        }
        just_green = {
            **active,
            "number": 12003,
            "checks": [{**parked["checks"][0], "finished_at": "2026-11-18T17:00:00Z"}],
        }
        snapshot = {
            "captured_at": "2026-11-18T18:00:00Z",
            "pulls": [parked, active, just_green],
            "deployments": [],
            "master": {},
        }
        legacy_jam = {
            "kind": "review-waiting",
            "station": "Review",
            "started_at": opened,
            "qualifies_at": "2026-11-03T19:00:00Z",
            "ended_at": None,
            "count": 3,
        }
        legacy = {
            "changes": [
                {
                    "number": 12002,
                    "line": "Server",
                    "station": "Review",
                    "station_since": opened,
                }
            ],
            "jams": [
                {
                    **legacy_jam,
                    "key": "review-waiting:Server",
                    "line": "Server",
                },
                {
                    **legacy_jam,
                    "key": "review-waiting:Website",
                    "line": "Website",
                },
            ],
        }
        floor = build(snapshot, legacy)
        stops = [stop for stop in floor["stops"] if stop["kind"] == "review-waiting"]
        self.assertEqual(
            stops,
            [
                {
                    "kind": "review-waiting",
                    "line": "Server",
                    "station": "Review",
                    "since": ready,
                    "count": 1,
                    "level": "amber",
                }
            ],
        )
        jams = [j for j in floor["jams"] if j["kind"] == "review-waiting"]
        self.assertEqual([(j["started_at"], j["count"]) for j in jams], [(ready, 1)])

    def test_f_reader_behind_after_fifteen_minutes(self):
        self.assertTrue(reader_behind("2026-11-18T17:44:59Z", self.now))
        self.assertFalse(reader_behind("2026-11-18T17:45:00Z", self.now))

    def test_real_november_18_morning_at_ten(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/morning-nov18.json").read_text()
        )
        stops = stopped_rules(
            fixture["changes"],
            fixture["commands"],
            fixture["master"],
            fixture["last_merges"],
            fixture["observed_since"],
            self.now,
        )
        stalled = next(
            s for s in stops if s["kind"] == "line-stalled" and s["line"] == "Server"
        )
        self.assertGreaterEqual(
            self.now - instant(stalled["since"]), timedelta(hours=3, minutes=45)
        )
        announced = next(
            s for s in stops if s["kind"] == "announced" and s["line"] == "Server"
        )
        self.assertEqual(announced["since"], "2026-11-18T16:47:17Z")
        self.assertEqual(announced["count"], 2)

    def test_only_recognized_commands_from_trusted_comments_leave_the_collector(self):
        comment = {
            "body": "merging #12971, #12974 (server)",
            "created_at": "2026-11-18T16:47:17Z",
            "author_association": "OWNER",
        }
        self.assertEqual(commands_from([comment])[0]["numbers"], [12971, 12974])
        self.assertNotIn("body", commands_from([comment])[0])
        self.assertEqual(commands_from([{**comment, "author_association": "NONE"}]), [])

    def test_announcement_rejects_repeated_tokens_with_a_bad_suffix(self):
        comment = {
            "body": "merging" + "\t#0" * 5000 + " (serverx)",
            "created_at": "2026-11-18T16:47:17Z",
            "author_association": "OWNER",
        }
        self.assertEqual(commands_from([comment]), [])

    def test_reviews_survive_test_only_commits_and_master_merges(self):
        pull = {
            "head_sha": "latest",
            "commits_complete": True,
            "commits": [
                {"sha": "approved"},
                {"sha": "tests", "test_only": True},
                {"sha": "latest", "merge_from_master": True},
            ],
        }
        self.assertTrue(unchanged_after(pull, "approved"))
        pull["commits"][1]["test_only"] = False
        self.assertFalse(unchanged_after(pull, "approved"))
        self.assertFalse(unchanged_after(pull, "missing"))

    def test_production_changes_cannot_be_hidden_by_a_test_rename(self):
        self.assertTrue(test_file("frontend/__tests__/page.test.tsx"))
        self.assertTrue(test_file("ios/BainLuckTests/Example.swift"))
        self.assertFalse(test_file("frontend/app/test/page.tsx"))
        self.assertFalse(test_file("backend/app/services/testing.py"))

    def test_station_transfers_are_recorded_only_after_two_observations(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/github.json").read_text()
        )
        first = build(fixture)
        self.assertEqual(first["transitions"], [])
        old = deepcopy(first)
        old["changes"][0]["station"] = (
            "Write" if first["changes"][0]["station"] != "Write" else "Review"
        )
        second = build(fixture, old)
        self.assertEqual(len(second["transitions"]), 1)
        self.assertEqual(
            second["transitions"][0]["number"], first["changes"][0]["number"]
        )
