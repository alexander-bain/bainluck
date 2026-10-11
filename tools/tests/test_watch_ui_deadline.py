"""Exercise real owned child processes; no Apple/simulator operations."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "watch_ui_deadline", ROOT / "tools/watch_ui_deadline.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WatchUIDeadlineTests(unittest.TestCase):
    def run_child(self, code, seconds=3):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            result = MODULE.run_gate(
                [sys.executable, "-c", code, directory],
                out,
                seconds=seconds,
                grace_seconds=0.15,
            )
            record = json.loads((out / "deadline.json").read_text())
            files = {p.name: p.read_text() for p in out.iterdir() if p.is_file()}
            return result, record, files

    def test_success_only_preserves_actual_gate_receipt_and_command_runs_once(self):
        result, record, files = self.run_child(
            """
import pathlib,sys
p=pathlib.Path(sys.argv[1]); (p/'receipt.json').write_text('{"verdict":"PASS"}')
print('one invocation')
"""
        )
        self.assertEqual(result, 0)
        self.assertEqual(record["status"], "COMPLETED")
        self.assertEqual(json.loads(files["receipt.json"])["verdict"], "PASS")
        self.assertEqual(files["gate-supervisor.log"].count("one invocation"), 1)

    def test_nonzero_exit_is_preserved_and_cannot_leave_pass(self):
        result, record, files = self.run_child(
            """
import pathlib,sys
(pathlib.Path(sys.argv[1])/'receipt.json').write_text('{"sha":"source","verdict":"PASS"}')
sys.exit(7)
"""
        )
        self.assertEqual(result, 7)
        self.assertEqual(record["status"], "FAILED")
        self.assertEqual(json.loads(files["receipt.json"])["verdict"], "UNPAID")
        self.assertEqual(json.loads(files["receipt.json"])["sha"], "source")

    def test_deadline_preserves_partial_logs_and_allows_interrupt_flush(self):
        result, record, files = self.run_child(
            """
import pathlib,sys,time,signal
p=pathlib.Path(sys.argv[1]); (p/'tests.log').write_text('first case passed; second started')
def stop(*args):
 (p/'result-flushed.txt').write_text('flushed'); sys.exit(0)
signal.signal(signal.SIGINT,stop)
time.sleep(20)
""",
            seconds=0.4,
        )
        self.assertEqual(result, 124, (record, files))
        self.assertEqual(record["status"], "DEADLINE")
        self.assertEqual(files["result-flushed.txt"], "flushed")
        self.assertIn("second started", files["tests.log"])
        self.assertEqual(json.loads(files["receipt.json"])["verdict"], "UNPAID")

    def test_stubborn_owned_child_cannot_extend_deadline_or_trigger_retry(self):
        result, record, files = self.run_child(
            """
import signal,time
signal.signal(signal.SIGINT,signal.SIG_IGN); signal.signal(signal.SIGTERM,signal.SIG_IGN)
print('only once',flush=True); time.sleep(20)
""",
            seconds=0.4,
        )
        self.assertEqual(result, 124, (record, files))
        self.assertLess(record["elapsed_seconds"], 3)
        self.assertEqual(files["gate-supervisor.log"].count("only once"), 1)

    def test_descendant_is_stopped_even_after_shell_exit_and_unrelated_process_survives(
        self,
    ):
        outsider = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(20)"]
        )
        try:
            with tempfile.TemporaryDirectory() as directory:
                child = (
                    "import signal,time,pathlib; "
                    "signal.signal(signal.SIGINT,signal.SIG_IGN); "
                    "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                    "time.sleep(2); pathlib.Path("
                    + repr(directory + "/escaped")
                    + ").touch()"
                )
                parent = (
                    "import subprocess,sys,time,signal; "
                    "subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); "
                    "signal.signal(signal.SIGINT,lambda *a: sys.exit(0)); time.sleep(20)"
                )
                code = MODULE.run_gate(
                    [sys.executable, "-c", parent],
                    directory,
                    seconds=0.4,
                    grace_seconds=0.15,
                )
                self.assertEqual(code, 124)
                time.sleep(2)
                self.assertFalse((Path(directory) / "escaped").exists())
                self.assertIsNone(outsider.poll())
        finally:
            outsider.terminate()
            outsider.wait(timeout=3)

    def test_shutdown_does_not_probe_group_zero_while_reaping(self):
        import errno
        from unittest.mock import patch

        killpg = MODULE.os.killpg

        def reject_probe(pid, signum):
            if signum == 0:
                raise OSError(errno.EPERM, "injected liveness-probe failure")
            return killpg(pid, signum)

        with patch.object(MODULE.os, "killpg", side_effect=reject_probe):
            result, record, files = self.run_child(
                "import signal,sys,time; signal.signal(signal.SIGINT,lambda *a: sys.exit(0)); time.sleep(20)",
                seconds=0.4,
            )
        self.assertEqual(result, 124, (record, files))
        self.assertEqual(record["status"], "DEADLINE")

    def test_process_control_error_is_not_reported_as_launch_failure(self):
        import errno
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(MODULE.subprocess, "Popen") as launch:
                launch.return_value.wait.side_effect = MODULE.subprocess.TimeoutExpired(
                    "gate", 1
                )
                with patch.object(
                    MODULE, "_stop", side_effect=OSError(errno.EPERM, "private group")
                ):
                    result = MODULE.run_gate(["owned-gate"], directory)
            record = json.loads((Path(directory) / "deadline.json").read_text())
            self.assertEqual(result, 1)
            self.assertEqual(record["status"], "PROCESS_CONTROL_FAILED")
            self.assertEqual(record["error_phase"], "stop")
            self.assertEqual(record["error_errno"], errno.EPERM)
            self.assertEqual(
                json.loads((Path(directory) / "receipt.json").read_text())["verdict"],
                "UNPAID",
            )

    def test_cancelled_gate_is_unpaid(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(MODULE.subprocess, "Popen") as launch:
                process = launch.return_value
                process.wait.side_effect = MODULE.Interrupted(15)
                with patch.object(MODULE, "_stop") as stop:
                    self.assertEqual(MODULE.run_gate(["owned-gate"], directory), 143)
                    stop.assert_called_once_with(process, 15)
            self.assertEqual(
                json.loads((Path(directory) / "deadline.json").read_text())["status"],
                "CANCELLED",
            )
            self.assertEqual(
                json.loads((Path(directory) / "receipt.json").read_text())["verdict"],
                "UNPAID",
            )

    def test_missing_executable_returns_unpaid_launch_failure(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(MODULE.run_gate(["/missing/watch-gate"], out), 127)
            self.assertEqual(
                json.loads((Path(out) / "receipt.json").read_text())["verdict"],
                "UNPAID",
            )

    def test_deadline_cannot_be_disabled_or_raised(self):
        for value in (0, -1, float("inf"), float("nan"), MODULE.MAX_SECONDS + 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.run_gate(["unused"], "unused", seconds=value)

    def test_workflow_reserves_upload_time_without_changing_test_timeouts(self):
        workflow = (ROOT / ".github/workflows/watch-mvp.yml").read_text()
        job = workflow.split("  watch-ui-journey:", 1)[1].split(
            "  companion-archive:", 1
        )[0]
        self.assertIn("timeout-minutes: 60", job)
        self.assertIn(
            "python3 tools/watch_ui_stage.py execute --output-dir build/watch-ui-journey -- bash tools/watch-ui-journey.sh execute",
            job,
        )
        self.assertIn("if: always()", job)
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        self.assertIn("-default-test-execution-time-allowance 180", harness)
        self.assertIn("-maximum-test-execution-time-allowance 300", harness)
        self.assertNotIn("-skip-testing", harness)
        self.assertNotIn("-only-testing", harness)
        self.assertLess(MODULE.MAX_SECONDS + 30, 60 * 60 - 5 * 60)


if __name__ == "__main__":
    unittest.main()
