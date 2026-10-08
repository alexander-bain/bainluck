import importlib.util
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "runner", Path(__file__).with_name("runner.py")
)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "inbox").mkdir()
        (self.root / "runs").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_snapshot_git_bypasses_path_wrapper_and_preserves_bound(self):
        expected = "/usr/bin/git" if Path("/usr/bin/git").is_file() else "git"
        with patch.object(r, "run_bounded") as bounded:
            r.snapshot_git(self.root, "add", "-A", timeout=600)
        bounded.assert_called_once_with(
            [expected, "-C", str(self.root), "add", "-A"], timeout=600
        )

    def test_failure_preserves_issue_run_and_retry_deadline(self):
        failure = r.WorkerFailure("runtime acknowledgement timed out", self.root)
        record = r.failure_record(failure, {"failures": 1}, 1763, at=1000)
        self.assertEqual(record["failures"], 2)
        self.assertEqual(record["retry_after"], 1900)
        status = r.wait_status(record)
        self.assertEqual(status["state"], "retry_wait")
        self.assertEqual(status["issue"], 1763)
        self.assertEqual(status["run"], str(self.root))
        self.assertIn("1970-01-01T00:31:40", status["reason"])
        self.assertIn("acknowledgement timed out", status["reason"])
        self.assertEqual(
            r.wait_status({k: v for k, v in record.items() if k != "retry_at"})[
                "reason"
            ],
            status["reason"],
        )

    def test_third_failure_requires_attention_not_a_fourth_retry(self):
        record = r.failure_record(
            RuntimeError("failed"), {"failures": 2}, 1763, at=1000
        )
        self.assertEqual(r.wait_status(record)["state"], "needs_attention")
        self.assertNotIn("retry_after", record)

    def test_reviewed_failed_issue_is_not_rediagnosed_and_other_work_continues(self):
        issues = [
            dict(number=n, labels=[{"name": "needs-agent"}], assignees=[], state="OPEN")
            for n in [1763, 1764]
        ]
        for record in [
            {"status": "reviewed", "disposition": "rejected"},
            {"status": "retry", "retry_after": 10**12},
        ]:
            with patch.object(r, "gh", side_effect=[issues, []]):
                self.assertEqual(
                    r.choose(self.root, {"issue:1763": record})[1]["issue"], 1764
                )

    def test_worker_runtime_failure_is_not_terminal_completion(self):
        log = self.root / "worker.jsonl"
        log.write_text(
            json.dumps({"payload_type": "task.lifecycle.completed"}) + "\n"
            "muse: runtime host shutdown timed out after 2s\n"
            "runtime command acknowledgement timed out after 30s\n"
        )
        self.assertFalse(r.completed(log))
        self.assertIn("runtime host shutdown", r.worker_error(log, 1))
        self.assertIn("acknowledgement timed out", r.worker_error(log, 1))

    def test_once_failure_publishes_retry_state_and_returns_failure(self):
        with patch.object(
            sys, "argv", ["runner", "once", "--root", str(self.root)]
        ), patch.object(
            r, "choose", return_value=("issue:1763", {"issue": 1763})
        ), patch.object(
            r, "run", side_effect=r.WorkerFailure("shutdown timeout", self.root)
        ):
            self.assertEqual(r.main(), 1)
        status = r.read(self.root / "STATUS.json", {})
        self.assertEqual((status["state"], status["issue"]), ("retry_wait", 1763))
        self.assertIn("retry eligible at", status["reason"])

    def test_loop_continues_after_failed_issue_without_global_cooldown(self):
        with patch.object(
            sys, "argv", ["runner", "loop", "--root", str(self.root)]
        ), patch.object(
            r, "choose", return_value=("issue:1763", {"issue": 1763})
        ), patch.object(
            r, "run", side_effect=r.WorkerFailure("shutdown timeout", self.root)
        ), patch.object(
            r.time, "sleep", side_effect=KeyboardInterrupt
        ) as sleep:
            with self.assertRaises(KeyboardInterrupt):
                r.main()
            sleep.assert_called_once_with(10)

    def test_delivery_requires_artifacts_not_exit_zero(self):
        with self.assertRaises(ValueError):
            r.validate_result(self.root, 6176, "abc")
        data = dict(
            issue=6176,
            base_sha="abc",
            status="blocked",
            pillar="TRUTH",
            ship="accurate comparison",
            summary="missing provenance",
            next_owner="Codex",
            next_action="read receipt",
            evidence=["REPORT.md"],
        )
        r.save(self.root / "RESULT.json", data)
        (self.root / "REPORT.md").write_text("Missing evidence.")
        self.assertEqual(r.validate_result(self.root, 6176, "abc"), data)
        data["base_sha"] = "wrong"
        r.save(self.root / "RESULT.json", data)
        with self.assertRaises(ValueError):
            r.validate_result(self.root, 6176, "abc")

    def test_evidence_cannot_escape_run(self):
        data = dict(
            issue=1,
            base_sha="abc",
            status="candidate",
            pillar="TRUTH",
            ship="x",
            summary="x",
            next_owner="x",
            next_action="x",
            evidence=["../outside"],
        )
        r.save(self.root / "RESULT.json", data)
        (self.root / "REPORT.md").write_text("x")
        with self.assertRaises(ValueError):
            r.validate_result(self.root, 1, "abc")

    def test_explicit_mission_retries_but_completed_does_not(self):
        r.save(
            self.root / "inbox" / "first.json",
            {"issue": 6176, "prompt": "bounded task"},
        )
        with patch.object(r, "gh", return_value=[]):
            self.assertEqual(r.choose(self.root, {})[0], "mission:first.json")
            self.assertIsNone(
                r.choose(self.root, {"mission:first.json": {"status": "delivered"}})
            )
            self.assertIsNone(
                r.choose(
                    self.root,
                    {"mission:first.json": {"status": "retry", "retry_after": 10**12}},
                )
            )
            self.assertIsNotNone(
                r.choose(
                    self.root,
                    {"mission:first.json": {"status": "retry", "retry_after": 0}},
                )
            )

    def test_active_owner_and_pr_excluded_priority_preserved(self):
        def issue(n, p, owner=False):
            return dict(
                number=n,
                labels=[{"name": "needs-agent"}, {"name": f"priority:p{p}"}],
                assignees=[{"login": "owner"}] if owner else [],
                state="OPEN",
            )

        issues = [issue(10, 2), issue(20, 1), issue(30, 0, True), issue(40, 0)]
        prs = [{"body": "Fixes #40", "title": "fix"}]
        with patch.object(r, "gh", side_effect=[issues, prs]):
            self.assertEqual(r.choose(self.root, {})[1]["issue"], 20)
        with patch.object(r, "gh", side_effect=[issues, prs]):
            self.assertEqual(
                r.choose(self.root, {"issue:20": {"status": "delivered"}})[1]["issue"],
                10,
            )
        with patch.object(r, "gh", side_effect=[issues, prs]):
            self.assertEqual(
                r.choose(
                    self.root, {"issue:20": {"status": "retry", "retry_after": 0}}
                )[1]["issue"],
                20,
            )

    def test_automatic_scout_refuses_foreign_lane_before_active_claim(self):
        def issue(n, lane=None):
            labels = [{"name": "needs-agent"}, {"name": "priority:p1"}]
            if lane:
                labels.append({"name": lane})
            return dict(number=n, labels=labels, assignees=[], state="OPEN")

        for lane in [
            "lane:latency",
            "lane:native",
            "lane:lane1b",
            "lane:future-builder",
        ]:
            routed = issue(10488, lane)
            self.assertFalse(r.eligible(routed))
            with patch.object(r, "gh", side_effect=[[routed, issue(10489)], []]):
                self.assertEqual(r.choose(self.root, {})[1]["issue"], 10489)
        self.assertTrue(r.eligible(issue(10488, "lane:diagnosis")))
        mixed = issue(10488, "lane:diagnosis")
        mixed["labels"].append({"name": "lane:latency"})
        self.assertFalse(r.eligible(mixed))

    def test_automatic_run_rechecks_lane_changed_after_scout(self):
        issue = dict(
            number=10488,
            labels=[{"name": "needs-agent"}, {"name": "lane:latency"}],
            comments=[],
            assignees=[],
            state="OPEN",
        )
        with patch.object(r, "gh", side_effect=[issue, []]), patch.object(
            r, "snapshot_git"
        ) as snap:
            result = r.run(self.root, self.root, {"issue": 10488}, None, 1)
        self.assertEqual(result["result"], "ownership_changed")
        snap.assert_not_called()

    def test_explicit_scoped_mission_preserves_coordinator_assignment(self):
        issue = dict(
            number=10488,
            labels=[{"name": "needs-agent"}, {"name": "lane:latency"}],
            comments=[],
            assignees=[],
            state="OPEN",
        )
        mission = {
            "issue": 10488,
            "explicit_scope": True,
            "prompt": "local source review only",
        }
        r.save(self.root / "inbox" / "assigned.json", mission)
        self.assertEqual(r.choose(self.root, {})[1], mission)
        # Stop before snapshot/runtime creation; this asserts admission, not execution.
        with patch.object(r, "gh", return_value=issue), patch.object(
            r, "command", return_value="pin"
        ), patch.object(
            r, "snapshot_git", side_effect=RuntimeError("admission passed")
        ):
            with self.assertRaisesRegex(RuntimeError, "admission passed"):
                r.run(self.root, self.root, mission, None, 1)

    def test_truncated_pr_inventory_is_unknown(self):
        with patch.object(r, "gh", side_effect=[[], [{}] * 500]):
            with self.assertRaises(RuntimeError):
                r.choose(self.root, {})

    def test_foreign_release_note_anchor_is_not_local_ownership(self):
        # Actual PR #5288 Firebase release-note link; its bare label is foreign.
        body = '<p><a href="https://redirect.github.com/firebase/firebase-js-sdk/pull/10248">#10248</a> - Fixed LanguageModel detection.</p>'
        self.assertFalse(r.pr_mentions({"body": body}, 10248))

    def test_foreign_link_labels_and_qualified_refs_are_not_local(self):
        for body in [
            "[#10248](https://github.com/firebase/firebase-js-sdk/issues/10248)",
            "<a href='https://github.com/firebase/firebase-js-sdk/issues/10248'>#10248</a>",
            "firebase/firebase-js-sdk#10248",
            "https://github.com/firebase/firebase-js-sdk/issues/10248",
            '<a href="https://github.com.evil/firebase/firebase-js-sdk/issues/10248">#10248</a>',
            "[#10248](https://github.com/alexander-bain/bainluck/issues/10249)",
        ]:
            with self.subTest(body=body):
                self.assertFalse(r.pr_mentions({"body": body}, 10248))

    def test_genuine_local_refs_still_protect_the_owner(self):
        for body in [
            "Fixes #10248",
            "alexander-bain/bainluck#10248",
            "https://github.com/alexander-bain/bainluck/issues/10248",
            "https://redirect.github.com/alexander-bain/bainluck/issues/10248#issuecomment-1",
            "[the fix](https://github.com/alexander-bain/bainluck/issues/10248)",
            '<a href="https://github.com/alexander-bain/bainluck/issues/10248">the fix</a>',
            "firebase/firebase-js-sdk#10248; genuinely fixes #10248",
        ]:
            with self.subTest(body=body):
                self.assertTrue(r.pr_mentions({"body": body}, 10248))
        self.assertTrue(
            r.pr_mentions(
                {"title": "Fixes #10248", "body": "firebase/firebase-js-sdk#10248"},
                10248,
            )
        )

    def test_adjacent_issue_numbers_do_not_claim_this_issue(self):
        for body in [
            "Fixes #102480",
            "Fixes #110248",
            "alexander-bain/bainluck#102480",
            "https://github.com/alexander-bain/bainluck/issues/102480",
        ]:
            with self.subTest(body=body):
                self.assertFalse(r.pr_mentions({"body": body}, 10248))

    def test_foreign_pr_does_not_block_selector_but_local_pr_does(self):
        issues = [
            dict(number=n, labels=[{"name": "needs-agent"}], assignees=[], state="OPEN")
            for n in [10248, 10249]
        ]
        foreign = {
            "body": '<a href="https://redirect.github.com/firebase/firebase-js-sdk/pull/10248">#10248</a>'
        }
        with patch.object(r, "gh", side_effect=[issues, [foreign]]):
            self.assertEqual(r.choose(self.root, {})[1]["issue"], 10248)
        with patch.object(
            r, "gh", side_effect=[issues, [foreign, {"body": "Fixes #10248"}]]
        ):
            self.assertEqual(r.choose(self.root, {})[1]["issue"], 10249)

    def test_review_backpressure_never_queries_gh(self):
        for i in range(5):
            r.save(self.root / "runs" / str(i) / "RESULT.json", {"status": "candidate"})
        with patch.object(r, "gh", side_effect=AssertionError("unexpected query")):
            self.assertIsNone(r.choose(self.root, {}))

    def test_dry_run_does_not_write_or_call_worker(self):
        target = self.root / "absent"
        result = subprocess.run(
            [sys.executable, str(Path(r.__file__)), "dry-run", "--root", str(target)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())

    def test_terminal_event_required(self):
        p = self.root / "log"
        p.write_text("SMOKE_OK\n")
        self.assertFalse(r.completed(p))
        p.write_text(json.dumps({"payload_type": "run.terminal.completed"}) + "\n")
        self.assertTrue(r.completed(p))

    def test_setup_timeout_kills_wrapper_descendant(self):
        heartbeat = self.root / "child-heartbeat"
        code = """import os, signal, time, sys
if os.fork() == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with open(sys.argv[1], 'a', buffering=1) as f:
        while True:
            f.write('alive\\n')
            time.sleep(.03)
else:
    time.sleep(60)
"""
        with self.assertRaises(subprocess.TimeoutExpired):
            r.run_bounded([sys.executable, "-c", code, str(heartbeat)], timeout=2)
        self.assertTrue(heartbeat.exists(), "descendant must actually run")
        size = heartbeat.stat().st_size
        self.assertGreater(size, 0)
        r.time.sleep(0.15)
        self.assertEqual(heartbeat.stat().st_size, size)
        self.assertIsNone(r.CHILD)

    def test_setup_preserves_failure_code_and_command_output(self):
        self.assertEqual(
            r.command([sys.executable, "-c", "print('receipt')"]), "receipt"
        )
        with self.assertRaises(subprocess.CalledProcessError) as error:
            r.run_bounded([sys.executable, "-c", "raise SystemExit(7)"])
        self.assertEqual(error.exception.returncode, 7)
        self.assertIsNone(r.CHILD)

    def test_stop_terminates_child_group(self):
        r.CHILD = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            start_new_session=True,
        )
        r.stop_child()
        self.assertIsNotNone(r.CHILD.poll())

    def test_duplicate_runner_cannot_enter_intake(self):
        lock = (self.root / "runner.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(r.__file__)),
                    "once",
                    "--root",
                    str(self.root),
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already running", result.stdout)
            self.assertFalse((self.root / "STATUS.json").exists())
        finally:
            lock.close()


if __name__ == "__main__":
    unittest.main()
