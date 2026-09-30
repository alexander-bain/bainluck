"""Dispatch uses live issue state, not empty model wakeups or historical prose."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("lane_ready_issue", ROOT / "scripts/lane_ready_issue.py")
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)


def issue(number=1, status="Ready", labels=None):
    return {
        "number": number, "createdAt": "2026-09-29T00:00:00Z",
        "labels": {"pageInfo": {"hasNextPage": False}, "nodes": [
            {"name": label} for label in (labels or ["lane:discover", "needs-agent"])
        ]},
        "projectItems": {"pageInfo": {"hasNextPage": False}, "nodes": [{
            "project": {"number": 1, "owner": {"login": "alexander-bain"}},
            "fieldValues": {"pageInfo": {"hasNextPage": False}, "nodes": [
                {"name": status, "field": {"name": "Status"}}
            ]},
        }]},
    }


def payload(*issues):
    return {"data": {"repository": {"issues": {
        "pageInfo": {"hasNextPage": False}, "nodes": list(issues)
    }}}}


class SelectionTests(unittest.TestCase):
    def test_priority_then_oldest(self):
        older = issue(3, labels=["lane:discover", "needs-agent", "priority:p1"])
        older["createdAt"] = "2026-09-28T00:00:00Z"
        newer = issue(2, labels=["lane:discover", "needs-agent", "priority:p1"])
        self.assertEqual(selector.select_issue(payload(issue(), newer, older), "discover"), 3)

    def test_active_work_prevents_another_implementation(self):
        self.assertIsNone(selector.select_issue(payload(issue(), issue(2, "In Progress")), "discover"))
        self.assertIsNone(selector.select_issue(payload(issue(), issue(2, labels=["lane:discover", "in-progress"])), "discover"))

    def test_label_and_board_must_both_authorize(self):
        for status in ["Inbox", "Blocked", "Needs User", "Parked", "Review / Verify", "Done"]:
            with self.subTest(status=status):
                self.assertIsNone(selector.select_issue(payload(issue(status=status)), "discover"))
        for label in ["blocked", "needs-user", "parked"]:
            self.assertIsNone(selector.select_issue(payload(issue(labels=["lane:discover", "needs-agent", label])), "discover"))
        self.assertIsNone(selector.select_issue(payload(issue(labels=["lane:discover"])), "discover"))

    def test_fail_closed_on_partial_or_ambiguous_state(self):
        base = payload(issue())
        bad = copy.deepcopy(base)
        bad["data"]["repository"]["issues"]["pageInfo"]["hasNextPage"] = True
        cases = [bad, {"errors": [{"message": "unavailable"}]}]
        for path in ["labels", "projectItems"]:
            bad = payload(issue())
            bad["data"]["repository"]["issues"]["nodes"][0][path]["pageInfo"]["hasNextPage"] = True
            cases.append(bad)
        cases += [payload(issue(status="Unknown")), payload(issue(labels=["lane:discover", "lane:live", "needs-agent"])), payload(issue(labels=["lane:live", "needs-agent"]))]
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    selector.select_issue(bad, "discover")

    def test_another_users_project_is_not_our_lock(self):
        row = issue()
        row["projectItems"]["nodes"][0]["project"]["owner"]["login"] = "someone-else"
        with self.assertRaises(ValueError):
            selector.select_issue(payload(row), "discover")

    def test_empty_is_normal_not_a_task(self):
        self.assertIsNone(selector.select_issue(payload(), "discover"))


class PolicyTests(unittest.TestCase):
    def test_only_explicit_service_modes_allow_legacy_dispatch(self):
        for mode, expected in [("build", 0), ("integration", 1), ("quality", 1), ("buid", 2), (None, 2)]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "config").mkdir()
                lanes = {"test": {"mode": mode}} if mode else {}
                (root / "config/lane-ownership.json").write_text(json.dumps({"schema_version": 1, "lanes": lanes}))
                with patch.object(selector, "ROOT", root), patch("sys.argv", ["selector", "test", "--is-build-lane"]):
                    self.assertEqual(selector.main(), expected)


    def test_malformed_policy_is_unknown_not_legacy_permission(self):
        for policy in [[], {"lanes": []}, {"schema_version": 1, "lanes": []}, {"schema_version": 1, "lanes": {"test": []}}]:
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "config").mkdir()
                (root / "config/lane-ownership.json").write_text(json.dumps(policy))
                with patch.object(selector, "ROOT", root), patch("sys.argv", ["selector", "test", "--is-build-lane"]):
                    self.assertEqual(selector.main(), 2)


class RestockTests(unittest.TestCase):
    def run_restock(self, data, *, lane="discover", dry=False, queued=False, twice=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "handoff/runner-inbox" / lane
            inbox.mkdir(parents=True)
            if queued:
                (inbox / "existing.md").write_text("already assigned")
            bindir = root / "bin"
            bindir.mkdir()
            fixture = root / "payload.json"
            fixture.write_text(json.dumps(data))
            counter = root / "calls"
            gh = bindir / "gh"
            gh.write_text('#!/bin/sh\necho call >> "$DISPATCH_TEST_CALLS"\ncat "$DISPATCH_TEST_FIXTURE"\n')
            gh.chmod(0o755)
            text = (ROOT / "lane-runner.sh").read_text()
            # Include the real due/queue helpers used by maybe_restock. A slice
            # of only the restock body would miss the deferred-inbox guard.
            functions = text[text.index("runner_now ()"):text.index("# --dry-run: evaluate every named lane")]
            prelude = '''
rs_dummy=1
inbox_queued() { find "$1" -maxdepth 1 -name '*.md' | wc -l; }
inbox_running() { find "$1" -maxdepth 1 -name '*.running' | wc -l; }
inbox_restocks() { find "$1" -maxdepth 1 -name 'RESTOCK-*.md' | wc -l; }
lane_program() { echo PROGRAM-SHOPPER.md; }
'''
            env = dict(os.environ, BL_REPO=str(ROOT), HANDOFF=str(root / "handoff"),
                       DRYRUN=str(int(dry)), RESTOCK_MIN_INTERVAL="120",
                       PATH=str(bindir) + os.pathsep + os.environ["PATH"],
                       DISPATCH_TEST_CALLS=str(counter), DISPATCH_TEST_FIXTURE=str(fixture))
            command = prelude + functions + f'\nmaybe_restock {lane}\n'
            if twice:
                command += f'maybe_restock {lane}\n'
            command += 'exit 0\n'
            result = subprocess.run(["bash", "-c", command], env=env, text=True, capture_output=True, timeout=15, check=True)
            files = {p.name: p.read_text() for p in inbox.iterdir()}
            calls = len(counter.read_text().splitlines()) if counter.exists() else 0
            return result.stdout, files, calls

    def test_ready_issue_produces_one_named_directive_without_old_program_priority(self):
        _, files, calls = self.run_restock(payload(issue(42)))
        task = next(value for name, value in files.items() if name.startswith("RESTOCK-"))
        self.assertIn("Ready issue #42", task)
        self.assertIn("selection is not a claim", task)
        self.assertNotIn("Pick the work yourself", task)
        self.assertEqual(calls, 1)

    def test_empty_and_failed_reads_launch_no_task_and_throttle_api(self):
        for data in [payload(), {"errors": [{"message": "rate limit"}]}]:
            with self.subTest(data=data):
                _, files, calls = self.run_restock(data, twice=True)
                self.assertFalse(any(name.startswith("RESTOCK-") for name in files))
                self.assertEqual(calls, 1)

    def test_existing_assignment_is_untouched(self):
        _, files, calls = self.run_restock(payload(issue()), queued=True)
        self.assertEqual(files, {"existing.md": "already assigned"})
        self.assertEqual(calls, 0)

    def test_dry_run_does_not_write(self):
        output, files, _ = self.run_restock(payload(issue(42)), dry=True)
        self.assertIn("Ready issue #42", output)
        self.assertEqual(files, {})

    def test_unknown_lane_does_not_fall_back_to_old_program(self):
        output, files, calls = self.run_restock(payload(), lane="typo")
        self.assertIn("policy unavailable", output)
        self.assertEqual(files, {})
        self.assertEqual(calls, 0)

    def test_shopper_keeps_quality_program_without_querying_build_queue(self):
        _, files, calls = self.run_restock(payload(), lane="shopper")
        self.assertEqual(calls, 0)
        self.assertIn("PROGRAM-SHOPPER.md", next(v for k, v in files.items() if k.startswith("RESTOCK-")))


if __name__ == "__main__":
    unittest.main()
