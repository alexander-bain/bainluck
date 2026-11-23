"""Real response replay plus explicitly labelled counterfactual gate controls."""

from copy import deepcopy
from datetime import timedelta
import json
import re
from pathlib import Path
import sys
import unittest
import io
import tempfile
from contextlib import redirect_stdout
from http.client import IncompleteRead
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/factory"))
from model import (
    advance_jams,
    build,
    checks_green,
    classify,
    instant,
    iso,
    lines_for,
    public_title,
)
from collect import (
    collect,
    is_review_bot,
    safe_comment,
    floor_changed,
    authorize_publication,
    read_published,
    publish_asset,
    GitHub,
    main,
    master_checks,
)
from unittest.mock import call, patch, MagicMock
from notes import ModelBudget, make_notes
from speech import make_speech
from signals import stopped_rules

FIXTURES = Path(__file__).parent / "fixtures"


class GitHubRequestTests(unittest.TestCase):
    def test_history_query_retries_a_transient_504_and_counts_both_calls(self):
        api = GitHub(token="fake")
        error = HTTPError("https://api.github.com/graphql", 504, "Gateway Timeout", {}, None)
        response = MagicMock()
        response.__enter__.return_value.headers = {
            "X-RateLimit-Remaining": "98", "X-RateLimit-Resource": "graphql",
        }
        response.__enter__.return_value.read.return_value = b'{"data": {"history": []}}'
        with patch("collect.urllib.request.urlopen", side_effect=[error, response]), patch("collect.time.sleep") as delay:
            result = api.request("graphql", {"query": "query { repository { id } }"})
        self.assertEqual(result, {"data": {"history": []}})
        self.assertEqual(api.api_calls, 2)
        self.assertEqual(api.api_calls_by_resource["graphql"], 2)
        self.assertEqual(api.rates["graphql"], 98)
        delay.assert_called_once_with(20)

    def test_incomplete_history_body_and_invalid_json_wait_for_a_third_read(self):
        api = GitHub(token="fake")
        response = MagicMock()
        reply = response.__enter__.return_value
        reply.headers = {}
        reply.read.side_effect = [
            IncompleteRead(b'{"data":', 20),
            b'{"data":',
            b'{"data":{"history":[]}}',
        ]
        with patch("collect.urllib.request.urlopen", return_value=response), patch("collect.time.sleep") as delay:
            data = api.request("graphql", {"query": "query { repository { id } }"})
        self.assertEqual(data, {"data": {"history": []}})
        self.assertEqual(api.api_calls_by_resource["graphql"], 3)
        self.assertEqual(delay.call_args_list, [call(20), call(20)])

    def test_stops_after_three_read_failures_and_never_retries_a_write(self):
        error = HTTPError("https://api.github.com/example", 502, "Bad Gateway", {}, None)
        for method, attempts in [("GET", 3), ("PATCH", 1), ("POST", 1)]:
            with self.subTest(method=method):
                api = GitHub(token="fake", read_only=False)
                with patch("collect.urllib.request.urlopen", side_effect=error) as send, patch("collect.time.sleep") as delay:
                    with self.assertRaises(HTTPError):
                        api.request("example", method=method)
                self.assertEqual(send.call_count, attempts)
                self.assertEqual(api.api_calls, attempts)
                self.assertEqual(delay.call_args_list, [call(20)] * (attempts - 1))

    def test_missing_asset_remains_a_single_read(self):
        error = HTTPError("https://api.github.com/example", 404, "Not Found", {}, None)
        api = GitHub(token="fake")
        with patch("collect.urllib.request.urlopen", side_effect=error) as send, patch("collect.time.sleep") as delay:
            with self.assertRaises(HTTPError):
                api.request("example")
        send.assert_called_once()
        delay.assert_not_called()

    def test_public_snapshot_reads_retry_transport_errors(self):
        api = GitHub(token="fake")
        data = {"generated_at": "2026-11-22T15:55:32Z"}
        with patch("collect.read_public", side_effect=[IncompleteRead(b'{"data"'), TimeoutError(), data]), patch(
            "collect.time.sleep"
        ) as delay:
            self.assertEqual(api.public_json("https://example.invalid/factory.json"), data)
        self.assertEqual(api.public_reads, 3)
        self.assertEqual(delay.call_args_list, [call(20), call(20)])


class FactoryCollectorTests(unittest.TestCase):
    def test_collects_recent_now_posts_across_pacific_midnight(self):
        now = instant("2026-11-22T08:05:00Z")
        post_at = "2026-11-22T07:59:00Z"
        api = MagicMock()
        api.public_json.return_value = {"status": "ok", "commit": "server"}
        api.pages.return_value = [
            {"body": "Builder F: Waiting on #13346.", "created_at": post_at, "author_association": "OWNER"},
            {"body": "Builder F now: retaking the iPad screenshots from build 5852",
             "created_at": "2026-11-22T06:40:00Z", "author_association": "MEMBER"},
        ]
        api.request.side_effect = lambda endpoint: {"workflow_runs": []} if "/actions/" in endpoint else []
        receipts = [
            {"line": "Website", "commit": "web", "at": iso(now)},
            {"line": "Apps", "commit": "apps", "at": iso(now)},
        ]
        git_output = {"rev-parse": "server", "show": iso(now), "rev-list": "web\napps\nserver"}
        with (
            patch("collect.datetime") as clock,
            patch("collect.history_signals", return_value=(receipts, {}, [], None)),
            patch("collect.git", side_effect=lambda command, *args: git_output[command]),
        ):
            clock.now.return_value = now
            snapshot = collect(api, open_summaries=[])
        api.pages.assert_called_once_with("issues/12779/comments?since=2026-11-22T05:05:00Z")
        self.assertEqual(snapshot["crew_posts"], {"F": {"at": post_at, "waiting_on": 13346}})
        self.assertEqual(snapshot["lane_updates"]["F"]["at"], "2026-11-22T06:40:00Z")

    def test_13444_stays_held_while_failed_master_attempt_is_rerun(self):
        fixture = json.loads((FIXTURES / "master-retry-nov22.json").read_text())
        api = MagicMock()
        api.request.side_effect = [fixture["previous_attempt"], fixture["failed_attempt_jobs"]]
        rerun = fixture["rerun_as_of_capture"]
        pull = fixture["pull"]
        master = master_checks(api, [rerun], [fixture["another_commit_passed"]], [pull])
        self.assertEqual(master, {
            "tests": "failing", "tests_at": "2026-11-22T23:35:42Z",
            "blocked_server_release": 13444,
        })
        self.assertEqual(api.request.call_args_list, [
            call("repos/alexander-bain/bainluck/actions/runs/45082983839/attempts/1", timeout=5),
            call("repos/alexander-bain/bainluck/actions/runs/45082983839/attempts/1/jobs?per_page=100", timeout=5),
        ])
        change = {**pull, "line": "Server", "station": "Ship"}
        at = fixture["captured_at"]
        stops = stopped_rules([change], [], master, {}, at, instant(at))
        self.assertEqual(stops, [{
            "kind": "master", "line": "Server", "station": "Ship", "number": 13444,
            "since": "2026-11-22T23:35:42Z", "count": 1, "level": "amber",
        }])

        cleared = fixture["rerun_passed"]
        api.reset_mock()
        green = master_checks(api, [cleared], [cleared], [pull])
        self.assertEqual(green, {"tests": "passing", "tests_at": cleared["updated_at"]})
        self.assertEqual(stopped_rules([change], [], green, {}, at, instant(cleared["updated_at"])), [])
        api.request.assert_not_called()

    def test_failed_workflow_without_a_failed_release_gate_does_not_hold_the_server(self):
        fixture = json.loads((FIXTURES / "master-retry-nov22.json").read_text())
        failed = fixture["previous_attempt"]
        jobs = fixture["failed_attempt_jobs"]["jobs"]
        for without_gate in (
            [job for job in jobs if job["name"] != "backend-tests (8)"],
            [job for job in jobs if job["name"] != "deploy"],
        ):
            api = MagicMock()
            api.request.return_value = {"jobs": without_gate}
            result = master_checks(api, [failed], [failed], [fixture["pull"]])
            self.assertEqual(result, {"tests": "failing", "tests_at": failed["updated_at"]})


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
        lines, unsure = lines_for(pull)
        return classify(pull, self.snapshot["deployments"], self.now, lines[0], unsure)

    def test_only_an_observed_failed_check_is_marked_on_a_change_at_checks(self):
        for name, ci, state, conclusion, expected in (
            ("tests", True, "completed", "failure", True),
            ("tests", True, "completed", "timed_out", True),
            ("tests", True, "in_progress", None, False),
            ("tests", True, "completed", "success", False),
            ("Tier-B approval", False, "completed", "failure", False),
            ("flaky-canary", True, "completed", "failure", False),
        ):
            with self.subTest(name=name, state=state, conclusion=conclusion):
                pull = self.ready()
                pull["checks"][0].update(name=name, ci=ci, state=state, conclusion=conclusion)
                self.assertEqual(self.place(pull).get("checks_failed", False), expected)
        pull["checks"][0].update(name="tests", ci=True)
        pull["checks_complete"] = False
        self.assertNotIn("checks_failed", self.place(pull))

    def test_only_green_quiet_changes_park_and_activity_brings_them_back(self):
        pull = self.ready()
        quiet = iso(self.now - timedelta(hours=48))
        pull.update(updated_at=quiet, comments=[])
        pull["reviews"][0]["submitted_at"] = quiet
        self.assertTrue(self.place(pull)["parked"])
        pull["updated_at"] = iso(self.now - timedelta(hours=47))
        self.assertFalse(self.place(pull).get("parked", False))
        pull["checks"][0].update(state="in_progress", ci=True)
        self.assertTrue(self.place(pull)["checks_running"])
        pull["checks"][0]["ci"] = False
        self.assertFalse(self.place(pull).get("checks_running", False))

    def test_a_numbered_merge_announcement_puts_only_the_ready_crate_on_the_truck(self):
        pull = self.ready()
        post = {
            "kind": "merging",
            "line": "Website",
            "numbers": [pull["number"]],
            "at": iso(self.now),
        }
        sample = {**self.snapshot, "pulls": [pull], "master": {}}
        previous = build(sample)
        current = build({**sample, "commands": [post]}, previous)
        self.assertEqual(current["changes"][0]["station"], "Ship")
        self.assertIsNone(current["changes"][0]["merged_at"])
        self.assertEqual(
            current["transitions"][0]["observed_at"], sample["captured_at"]
        )
        rerouted = build({**sample, "commands": [{**post, "line": "Apps"}]})
        self.assertEqual(
            [(c["line"], c["station"]) for c in rerouted["changes"]], [("Apps", "Ship")]
        )

    def test_builder_f_posts_app_build_without_claiming_unverified_delivery(self):
        from signals import commands_from

        pull = self.ready()
        pull.update(
            state="closed",
            merged_at=iso(self.now - timedelta(minutes=5)),
            merge_commit_sha="proof",
            files=["ios/Bain Luck/Home.swift"],
        )
        post = {
            "body": f'Builder F (6:40 PM PT): live: #{pull["number"]} (apps) — TestFlight build 5801',
            "author_association": "OWNER",
            "created_at": iso(self.now),
        }
        commands = commands_from([post])
        self.assertEqual(
            [(c["line"], c.get("build")) for c in commands], [("Apps", 5801)]
        )
        signed = {
            **post,
            "body": f'live — Builder F, #{pull["number"]} (apps) is in TestFlight 1.0.7 (5801).',
        }
        self.assertEqual(commands_from([signed]), commands)
        sample = {
            **self.snapshot,
            "pulls": [pull],
            "commands": commands,
            "deployments": [],
        }
        ship = build(sample)["changes"][0]
        self.assertEqual((ship["station"], ship["testflight_build"]), ("Ship", 5801))
        self.assertNotIn("live_posted_at", ship)
        sample["deployments"] = [
            {
                "line": "Apps",
                "at": iso(self.now),
                "kind": "reported",
                "contains": ["proof"],
            }
        ]
        arrived = build(sample)["changes"][0]
        self.assertEqual(
            (arrived["station"], arrived["live_post_observed_at"]),
            ("Live", iso(self.now)),
        )

    def test_fables_real_changes_verdict_sends_12765_back_to_write(self):
        fixture = json.loads((FIXTURES / "now-nov18-holds.json").read_text())
        pull = self.ready()
        earlier = {
            "created_at": "2026-11-16T19:54:53Z",
            "association": "OWNER",
            "fable_accept": True,
        }
        pull.update(
            number=12765, comments=[earlier, safe_comment(fixture["fable_changes"])]
        )
        placed = self.place(pull)
        self.assertEqual((placed["station"], placed["sent_back"]), ("Write", True))
        pull["comments"].append({**earlier, "created_at": "2026-11-19T01:00:00Z"})
        self.assertEqual(self.place(pull)["station"], "Merge line")

    def test_dependabot_12211_does_not_raise_an_inspection_wait(self):
        pull = self.ready()
        pull.update(
            number=12211,
            branch="dependabot/github_actions/actions/github-script-9",
            reviews=[],
            comments=[],
            created_at=iso(self.now - timedelta(days=4)),
            updated_at=iso(self.now - timedelta(hours=30)),
        )
        pull["checks"][0]["finished_at"] = iso(self.now - timedelta(hours=30))
        actual = build({**self.snapshot, "pulls": [pull], "master": {}})
        self.assertTrue(actual["changes"][0]["bot_update"])
        self.assertEqual(actual["changes"][0]["station"], "Review")
        self.assertFalse(
            any(stop["kind"] == "review-waiting" for stop in actual["stops"])
        )

    def test_saved_real_github_responses_place_at_least_twelve_changes(self):
        self.assertGreaterEqual(len(self.expected["placements"]), 12)
        self.assertEqual(
            {v[0] for v in self.expected["placements"].values()},
            {"Write", "Test", "Review", "Merge line", "Ship", "Live"},
        )
        results = {(c["number"], c["line"]): c for c in build(self.snapshot)["changes"]}
        for number, expected in self.expected["placements"].items():
            with self.subTest(change=number):
                result = results[int(number), expected[1]]
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
        line, unsure = lines_for(pull)
        self.assertEqual(
            classify(pull, receipts, moment, line[0], unsure)["station"], "Ship"
        )
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
                {"parents": 2, "merge_from_master": True, "at": "2026-11-17T12:00:00Z"},
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
        for paths, lines in [
            (["ios/Bain Luck/View.swift"], ("Apps",)),
            (["frontend/app/a.tsx"], ("Website",)),
            (["frontend/a.tsx", "ios/a.swift"], ("Website", "Apps")),
            (["backend/a.py", "frontend/a.tsx", "docs/a.md"], ("Server", "Website")),
            (["scripts/a.py"], ("Server",)),
        ]:
            pull["files"] = paths
            self.assertEqual(lines_for(pull), (lines, False))
        pull["files_complete"] = False
        self.assertEqual(lines_for(pull), (("Server",), True))
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

    def test_timer_publication_has_one_master_only_job(self):
        workflow = (ROOT / ".github/workflows/factory.yml").read_text()
        for event in (
            "schedule:",
            "push:",
            "workflow_dispatch:",
            "workflow_run:",
        ):
            self.assertIn(event, workflow)
        self.assertIn('cron: "*/5 * * * *"', workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertNotRegex(
            workflow,
            r"(?m)^  (pull_request(?:_review)?|issue_comment|status):",
        )
        self.assertEqual(
            re.findall(r"^  ([\w-]+):", workflow.split("jobs:\n")[1], re.M),
            ["snapshot"],
        )
        self.assertNotIn("needs:", workflow)
        self.assertNotIn("pull_request.head", workflow)
        self.assertIn("github.ref == 'refs/heads/master'", workflow)
        self.assertIn("ref: master", workflow)
        self.assertIn("workflows: [CI]", workflow)
        self.assertIn("types: [completed]", workflow)
        self.assertIn("timeout-minutes: 5", workflow)
        self.assertFalse((ROOT / ".github/workflows/factory-tests.yml").exists())
        collector = (ROOT / "scripts/factory/collect.py").read_text()
        for verb in ('"push"', '"commit"', '"update-ref"'):
            self.assertNotIn('["git", ' + verb, collector)
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            if path.name != "factory.yml":
                self.assertNotRegex(path.read_text(), r"(?m)^  release:")
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertEqual(
            re.findall(r"secrets\.([A-Z0-9_]+)", workflow), ["OPENAI_API_KEY"]
        )
        publisher = workflow.split(
            "- name: Collect, compare and publish a changed floor"
        )[1]
        self.assertIn("OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}", publisher)
        self.assertIn("LLM_MODEL_FACTORY_NOTES:", publisher)

    def test_explicit_no_look_description_clears_the_fable_gate(self):
        pull = self.ready()
        pull.update(
            fable_needed=True,
            fable_not_needed=True,
            comments_complete=False,
            commits_complete=False,
        )
        self.assertEqual(self.place(pull)["station"], "Merge line")

    def test_accepted_change_stays_cleared_after_tests_and_master_sync(self):
        pull = self.ready()
        reviewed = pull["head_sha"]
        pull.update(head_sha="new-head", fable_needed=True)
        pull["commits"] = [
            {"sha": reviewed, "parents": 1, "at": "2026-11-17T10:00:00Z"},
            {
                "sha": "tests",
                "parents": 1,
                "test_only": True,
                "at": "2026-11-17T12:00:00Z",
            },
            {
                "sha": "new-head",
                "parents": 2,
                "merge_from_master": True,
                "at": "2026-11-17T13:00:00Z",
            },
        ]
        pull["comments"] = [
            {
                "fable_accept": True,
                "association": "OWNER",
                "created_at": "2026-11-17T11:00:00Z",
            }
        ]
        self.assertEqual(self.place(pull)["station"], "Merge line")
        pull["commits"][1]["test_only"] = False
        self.assertEqual(self.place(pull)["station"], "Review")

    def test_trusted_no_look_comment_is_bound_to_the_last_non_merge_commit(self):
        pull = self.ready()
        pull.update(
            fable_needed=True, commits=[{"parents": 1, "at": "2026-11-17T10:00:00Z"}]
        )
        comment = safe_comment(
            {
                "body": "**Fable** no look needed for these fields",
                "created_at": "2026-11-17T11:00:00Z",
                "updated_at": "2026-11-17T11:00:00Z",
                "author_association": "OWNER",
            }
        )
        pull["comments"] = [comment]
        self.assertEqual(self.place(pull)["station"], "Merge line")
        comment["association"] = "NONE"
        self.assertEqual(self.place(pull)["station"], "Review")
        self.assertFalse(
            safe_comment(
                {
                    **comment,
                    "body": "Something **Fable** ACCEPT",
                    "author_association": "OWNER",
                }
            )["fable_accept"]
        )

    def test_timing_omits_merges_before_observation(self):
        first = build(self.snapshot)
        self.assertTrue(
            all(c["merge_to_live_seconds"] is None for c in first["changes"])
        )
        observed = {"observed_since": "2026-01-01T00:00:00Z"}
        later = build(self.snapshot, observed)
        self.assertTrue(
            any(c["merge_to_live_seconds"] is not None for c in later["changes"])
        )

    def test_comparison_ignores_read_time_and_incidental_api_order(self):
        previous = build(self.snapshot)
        current = deepcopy(previous)
        current["generated_at"] = iso(self.now + timedelta(minutes=5))
        current["changes"].reverse()
        current["jams"].reverse()
        self.assertFalse(floor_changed(previous, current))
        current["changes"][0]["station"] = "Review"
        current["changes"][0]["title"] += " changed"
        self.assertTrue(floor_changed(previous, current))
        self.assertTrue(floor_changed({}, current))

    def test_unchanged_floor_skips_both_uploads_and_still_prints_metrics(self):
        queue = {"machines": 40, "unavailable": True}
        previous = {
            "generated_at": "2026-11-18T01:00:00Z",
            "changes": [],
            "jams": [],
            "events": [],
            "signals": {"checks_queue": queue},
        }
        budget = ModelBudget("", None, now=instant(previous["generated_at"]))
        previous["notes"], _ = make_notes(previous, [], {}, budget, None)
        previous["speech"], _ = make_speech(previous, {}, budget, None)
        previous["model_usage"] = {"day": budget.state()["day"], "calls": 0}
        from crew import add_crew_week

        crew_week = add_crew_week(previous, [])
        current = {**deepcopy(previous), "generated_at": "2026-11-18T01:05:00Z"}
        api = MagicMock()
        api.pages.return_value = []
        api.metrics.return_value = {"github_api_calls": 3}
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(
            output
        ), patch.dict("os.environ", {"OPENAI_API_KEY": ""}), patch(
            "sys.argv",
            ["collect.py", "--publish", "--output", f"{directory}/factory.json"],
        ), patch(
            "collect.authorize_publication"
        ), patch(
            "collect.GitHub", return_value=api
        ), patch(
            "collect.read_published", return_value=({"id": 1}, previous, {"crew_week": crew_week})
        ), patch(
            "collect.collect", return_value={"pulls": []}
        ), patch(
            "collect.build", return_value=current
        ), patch(
            "collect.machine_queue", return_value=queue
        ), patch(
            "collect.ModelBudget", return_value=budget
        ), patch(
            "collect.publish_asset"
        ) as publish:
            main()
            publish.assert_not_called()
        self.assertIn('"published": false', output.getvalue())
        self.assertIn("FACTORY_METRICS", output.getvalue())
        self.assertIn("FACTORY_NOTES", output.getvalue())

    def test_branch_or_pull_request_publication_is_refused(self):
        with patch.dict(
            "os.environ",
            {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/factory/the-factory"},
        ):
            with self.assertRaisesRegex(RuntimeError, "master"):
                authorize_publication()

        with patch.dict(
            "os.environ",
            {
                "GITHUB_ACTIONS": "true",
                "GITHUB_REF": "refs/heads/master",
                "GITHUB_EVENT_NAME": "pull_request",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "Pull request"):
                authorize_publication()
        with patch.dict(
            "os.environ",
            {
                "GITHUB_ACTIONS": "true",
                "GITHUB_REF": "refs/heads/master",
                "GITHUB_EVENT_NAME": "push",
                "GITHUB_TOKEN": "fixture",
            },
        ):
            with patch(
                "collect.git",
                side_effect=lambda *args: (
                    "master" if args[0] == "branch" else "older-master-commit"
                ),
            ), patch("collect.contains", return_value=True):
                authorize_publication()

    def test_read_only_client_refuses_a_mutation_before_any_request(self):
        api = object.__new__(GitHub)
        api.read_only = True
        with self.assertRaisesRegex(RuntimeError, "read-only"):
            api.request("repos/example/releases", {"name": "example"}, method="POST")

    def test_mismatched_cache_keeps_the_public_history_and_forces_a_reread(self):
        class API:
            def request(self, endpoint):
                return {
                    "id": 1,
                    "assets": [
                        {
                            "name": "factory.json",
                            "browser_download_url": "public",
                            "updated_at": "1",
                        },
                        {
                            "name": "factory-cache.json",
                            "browser_download_url": "cache",
                            "updated_at": "2",
                        },
                    ],
                }

            def public_json(self, url):
                return (
                    {"generated_at": "old", "changes": [], "jams": [{"key": "kept"}]}
                    if url.startswith("public")
                    else {"generated_at": "new", "pulls": {"1": {}}}
                )

        _, previous, cache = read_published(API())
        self.assertEqual(previous["jams"], [{"key": "kept"}])
        self.assertEqual(cache, {})

    def test_cache_and_public_snapshot_are_uploaded_as_distinct_assets(self):
        class API:
            def __init__(self):
                self.assets = {}
                self.calls = []

            def request(self, endpoint, data=None, method=None, binary=None):
                self.calls.append((endpoint, method))
                if binary is not None:
                    name = endpoint.split("name=")[1]
                    asset = {
                        "id": len(self.calls),
                        "name": name,
                        "payload": json.loads(binary),
                    }
                    self.assets[asset["id"]] = asset
                    return asset
                if method == "PATCH":
                    asset = self.assets[int(endpoint.rsplit("/", 1)[1])]
                    asset["name"] = data["name"]
                    return asset
                if method == "DELETE":
                    return self.assets.pop(int(endpoint.rsplit("/", 1)[1]))
                return list(self.assets.values())

        api = API()
        release = {
            "id": 1,
            "upload_url": "https://uploads.github.com/repos/example/releases/1/assets{?name,label}",
        }
        publish_asset(
            api, release, "factory-cache.json", {"pulls": {"1": {"head_sha": "abc"}}}
        )
        publish_asset(api, release, "factory.json", {"changes": []})
        assets = {a["name"]: a["payload"] for a in api.assets.values()}
        self.assertEqual(set(assets), {"factory-cache.json", "factory.json"})
        self.assertEqual(assets["factory.json"], {"changes": []})


if __name__ == "__main__":
    unittest.main()
