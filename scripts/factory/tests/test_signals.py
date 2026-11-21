from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import build, instant, unchanged_after
from signals import (
    commands_from,
    crew_posts_from,
    reader_behind,
    resolve_holds,
    stopped_rules,
    test_file,
)


class CrewPosts(unittest.TestCase):
    now = instant("2026-11-18T18:00:00Z")

    def post(self, body, at="2026-11-18T17:58:00Z", association="OWNER"):
        return {
            "body": body,
            "created_at": at,
            "updated_at": "2026-11-18T18:00:00Z",
            "author_association": association,
        }

    def test_latest_own_post_records_activity_without_a_change_and_clears_old_wait(self):
        posts = [
            self.post("**Apple (9:56 AM PT):** Working on screenshots."),
            self.post("Builder F: Waiting for change #13001.", at="2026-11-18T17:55:00Z"),
            self.post("ready to look at #13004 — Builder B (9:57 AM PT).\nWaiting on [#12998](https://example.com/change).",
                      at="2026-11-18T17:57:00Z", association="COLLABORATOR"),
            self.post("I’m waiting on #13002 and #13003.\n\n— Wee-Bey"),
        ]
        self.assertEqual(crew_posts_from(posts, self.now), {
            "F": {"at": "2026-11-18T17:58:00Z"},
            "B": {"at": "2026-11-18T17:57:00Z", "waiting_on": 12998},
            "W": {"at": "2026-11-18T17:58:00Z"},
        })

    def test_unsigned_outside_quoted_old_and_future_posts_clock_in_nobody(self):
        posts = [
            self.post("Waiting on #12998."),
            self.post("Speed: Waiting on #12998.", association="CONTRIBUTOR"),
            self.post("**Fable: Floor report.**\n> Waiting on #12998 — Builder E"),
            self.post("> Waiting on #12998 — Atlas"),
            self.post("Builder C: Checked the floor.", at="2026-11-18T17:44:59Z"),
            self.post("Builder B: Checked the floor.", at="2026-11-18T18:00:01Z"),
        ]
        self.assertEqual(crew_posts_from(posts, self.now), {})


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
        hold = {
            "kind": "hold",
            "line": "Server",
            "at": "2026-11-18T17:00:00Z",
            "source": {"id": 10, "author": "Fable"},
        }
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

    def test_november_18_live_posts_clear_holds_with_or_without_named_slots(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/now-nov18-holds.json").read_text()
        )
        now = instant("2026-11-19T00:35:00Z")
        origin = fixture["server_start"]
        self.assertEqual(commands_from([origin])[0]["source"]["id"], 6994962892)
        expected = [["Server", "Website"], ["Server"], ["Server"]]
        for post, slots in zip(fixture["live"], expected):
            with self.subTest(at=post["created_at"]):
                commands = commands_from([post])
                self.assertEqual(
                    [(c["kind"], c["line"]) for c in commands],
                    [("live", slot) for slot in slots],
                )
                holds = resolve_holds(commands_from([origin, post]), [], {}, now)
                self.assertEqual(holds["Server"]["ended_at"], post["created_at"])
        website = {**origin, "id": 1, "body": "stuck: HOLD (website)"}
        commands = commands_from([origin, website, *fixture["live"]])
        holds = resolve_holds(commands, [], {}, now)
        self.assertEqual(holds["Server"]["ended_at"], fixture["live"][0]["created_at"])
        self.assertEqual(holds["Website"]["ended_at"], fixture["live"][0]["created_at"])
        stops = stopped_rules([], commands, {}, {}, origin["created_at"], now)
        self.assertFalse(any(stop["kind"] == "hold" for stop in stops))

    def test_only_stuck_and_uppercase_hold_with_provenance_starts_a_hold(self):
        post = {
            "id": 1,
            "author_association": "OWNER",
            "created_at": "2026-11-18T17:00:00Z",
        }
        for body in (
            "Server HOLD",
            "stuck on server hold",
            "stuck: Server HOLD is over",
            "stuck: Server HOLD lifted",
            "stuck: Server HOLD is cleared",
            "The server is stuck with HOLD",
            "stuck: HOLD",
        ):
            self.assertFalse(
                any(
                    c["kind"] == "hold" for c in commands_from([{**post, "body": body}])
                ),
                body,
            )
        self.assertEqual(
            commands_from([{**post, "body": "stuck: HOLD (server), Website can go"}])[
                0
            ]["line"],
            "Server",
        )
        self.assertEqual(
            commands_from(
                [{**post, "body": "stuck: HOLD (server)", "author_association": "NONE"}]
            ),
            [],
        )

    def test_a_delivery_new_green_master_run_or_coordinator_can_end_a_hold(self):
        start = {
            "kind": "hold",
            "line": "Server",
            "at": "2026-11-18T17:00:00Z",
            "source": {"id": 10, "author": "Fable"},
        }
        done = "2026-11-18T17:40:00Z"
        before = {
            "successful_runs": [
                {"started_at": "2026-11-18T16:59:00Z", "finished_at": done}
            ]
        }
        after = {
            "successful_runs": [
                {"started_at": "2026-11-18T17:01:00Z", "finished_at": done}
            ]
        }
        delivery = {
            "line": "Server",
            "station": "Live",
            "merged_at": "2026-11-18T17:05:00Z",
            "live_at": done,
        }
        self.assertIsNone(
            resolve_holds([start], [], before, self.now)["Server"]["ended_at"]
        )
        self.assertEqual(
            resolve_holds([start], [], after, self.now)["Server"]["ended_at"], done
        )
        self.assertEqual(
            resolve_holds([start], [delivery], {}, self.now)["Server"]["ended_at"], done
        )
        for name in ("Fable", "Alex"):
            comment = {
                "body": f"{name}: Server HOLD is over.",
                "author_association": "OWNER",
                "created_at": "2026-11-18T17:25:00Z",
            }
            holds = resolve_holds(
                [start, *commands_from([comment])], [delivery], after, self.now
            )
            self.assertEqual(holds["Server"]["ended_at"], comment["created_at"])
            self.assertEqual(resolve_holds([start], [], {}, self.now, holds), holds)
        other_lane = {
            "body": "live — Apple. The server HOLD is over.",
            "author_association": "OWNER",
            "created_at": done,
        }
        self.assertIsNone(
            resolve_holds([start, *commands_from([other_lane])], [], {}, self.now)[
                "Server"
            ]["ended_at"]
        )

    def test_repeat_hold_keeps_original_now_line_and_starts_again_after_clearance(self):
        a = {
            "kind": "hold",
            "line": "Server",
            "at": "2026-11-18T17:00:00Z",
            "source": {"id": 10, "author": "Fable"},
        }
        b = {
            **a,
            "at": "2026-11-18T17:30:00Z",
            "source": {"id": 11, "author": "Builder B"},
        }
        clear = {"kind": "resume", "line": "Server", "at": "2026-11-18T17:20:00Z"}
        self.assertEqual(
            resolve_holds([a, b], [], {}, self.now)["Server"]["source"], a["source"]
        )
        self.assertEqual(
            resolve_holds([a, clear, b], [], {}, self.now)["Server"]["source"],
            b["source"],
        )

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
                    "number": 12002,
                    "waiting_since": ready,
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
