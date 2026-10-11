"""Preparation and upload cannot reset the50m gate or consume an hour silently."""

import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from tools import watch_ui_stage as stage

ROOT = Path(__file__).resolve().parents[2]


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def prepare(self):
        self.assertEqual(stage.admission(self.root, "prepare", 100), 1200)
        path = self.root / "global-deadline.json"
        data = json.loads(path.read_text())
        data["stages"]["prepare"] = 0
        path.write_text(json.dumps(data))

    def test_upload_time_counts_and_global_deadline_cannot_reset(self):
        self.prepare()
        self.assertEqual(stage.admission(self.root, "execute", 700), 2400)
        with self.assertRaisesRegex(ValueError, "reset"):
            stage.admission(self.root, "prepare", 701)
        with self.assertRaisesRegex(ValueError, "admission"):
            stage.admission(self.root, "execute", 1301)
        with self.assertRaisesRegex(ValueError, "exhausted"):
            stage.admission(self.root, "execute", 3101)

    def test_failed_missing_or_repeated_preparation_cannot_start_execution(self):
        with self.assertRaises(OSError):
            stage.admission(self.root, "execute", 100)
        stage.admission(self.root, "prepare", 100)
        with self.assertRaisesRegex(ValueError, "successful"):
            stage.admission(self.root, "execute", 150)
        path = self.root / "global-deadline.json"
        data = json.loads(path.read_text())
        data["stages"] = {"prepare": 0, "execute": 1}
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "repeated"):
            stage.admission(self.root, "execute", 150)

    def test_consumer_has_no_build_or_package_operations_and_keeps_test_limits(self):
        source = (ROOT / "tools/watch-ui-journey.sh").read_text()
        for forbidden in [
            "-resolvePackageDependencies",
            "-clonedSourcePackagesDirPath",
            "build-for-testing",
            "xcodebuild build ",
            "-scheme ",
        ]:
            self.assertNotIn(forbidden, source)
        for required in [
            '-xctestrun "$XCTESTRUN"',
            "-test-timeouts-enabled YES",
            "-default-test-execution-time-allowance 180",
            "-maximum-test-execution-time-allowance 300",
        ]:
            self.assertIn(required, source)
        workflow = (ROOT / ".github/workflows/watch-mvp.yml").read_text()
        matrix = workflow.split("  watch-ui-journey:")[1].split("  watch-ui-complete:")[
            0
        ]
        self.assertIn("needs: watch-ui-products", matrix)
        self.assertLess(
            matrix.index("watch_ui_stage.py prepare"),
            matrix.index("name: watch-ui-preparation-"),
        )
        self.assertLess(
            matrix.index("name: watch-ui-preparation-"),
            matrix.index("watch_ui_stage.py execute"),
        )
        self.assertIn("if: always()", matrix)
        self.assertIn("timeout-minutes: 60", matrix)


class RestartBoundaryTests(unittest.TestCase):
    phases = (
        "post-install shutdown of only this run disposable Watch",
        "post-install boot of only this run disposable Watch",
        "post-install boot readiness of only this run disposable Watch",
        "post-install Watch ready; verify installed containers",
    )
    commands = (
        ["simctl", "shutdown", "owned-watch"],
        ["simctl", "boot", "owned-watch"],
        ["simctl", "bootstatus", "owned-watch", "-b"],
        ["simctl", "get_app_container", "owned-phone", "com.bainluck.Bain-Luck", "app"],
        [
            "simctl",
            "get_app_container",
            "owned-watch",
            "com.bainluck.Bain-Luck.watchkitapp",
            "app",
        ],
    )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_restart(self, failing=""):
        # Execute the real restart and prepared-state block, with no real Apple
        # executable reachable through its xcrun name. Test both old/new phase
        # layouts so the historical coarse boundary is a meaningful RED control.
        source = (ROOT / "tools/watch-ui-journey.sh").read_text()
        shutdown = source.index('xcrun simctl shutdown "$TEST_UDID"')
        start = source.rfind("\nPHASE=", 0, shutdown) + 1
        end = source.index("\nSTATE\n", shutdown) + len("\nSTATE\n")
        block = source[start:end]
        directory = self.root / (failing or "success")
        directory.mkdir()
        output = directory / "output"
        output.mkdir()
        binaries = directory / "bin"
        binaries.mkdir()
        fake = binaries / "xcrun"
        fake.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "out = Path(os.environ['OUT'])\n"
            "argv = sys.argv[1:]\n"
            "phase = json.loads((out / 'phase.json').read_text())['phase']\n"
            "with (out / 'calls.jsonl').open('a') as stream:\n"
            "    stream.write(json.dumps({'argv': argv, 'phase': phase}) + '\\n')\n"
            "if len(argv) < 2 or argv[0] != 'simctl': sys.exit(99)\n"
            "if argv[1] not in ('shutdown', 'boot', 'bootstatus', 'get_app_container'): sys.exit(99)\n"
            "if argv[1] == os.environ.get('FAIL_COMMAND'): sys.exit(47)\n"
            "if argv[1] == 'get_app_container': print('/installed/' + argv[2] + '.app')\n"
        )
        fake.chmod(0o755)
        environment = dict(
            os.environ,
            PATH=str(binaries) + os.pathsep + os.environ["PATH"],
            ROOT=str(ROOT),
            OUT=str(output),
            TEST_UDID="owned-watch",
            PHONE_UDID="owned-phone",
            FAIL_COMMAND=failing,
            RUN="owned-run",
            DERIVED="verified-products",
            RESULT="owned-result.xcresult",
            SHA="a" * 40,
            XCTESTRUN="verified-products/Watch.xctestrun",
        )
        result = subprocess.run(
            ["bash", "-c", "set -euo pipefail\n" + block],
            cwd=directory,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )
        calls = [
            json.loads(line)
            for line in (output / "calls.jsonl").read_text().splitlines()
        ]
        phases = [
            json.loads(line)["phase"]
            for line in (output / "phases.jsonl").read_text().splitlines()
        ]
        return result, output, calls, phases

    def test_success_keeps_exact_owned_commands_order_and_ready_boundary(self):
        result, output, calls, phases = self.run_restart()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call["argv"] for call in calls], list(self.commands))
        self.assertEqual(
            [call["phase"] for call in calls],
            [*self.phases[:3], self.phases[3], self.phases[3]],
        )
        self.assertEqual(phases, list(self.phases))
        lifecycle = (output / "install-lifecycle.txt").read_text()
        self.assertEqual(lifecycle.count("boot-ready"), 1)
        self.assertIn("/installed/owned-phone.app", lifecycle)
        self.assertIn("/installed/owned-watch.app", lifecycle)
        prepared = json.loads((output / "prepared.json").read_text())
        self.assertEqual(prepared["watch"], "owned-watch")
        self.assertEqual(prepared["phone"], "owned-phone")
        self.assertEqual(prepared["sha"], "a" * 40)
        self.assertEqual(prepared["xctestrun"], "verified-products/Watch.xctestrun")

    def test_each_failure_propagates_without_retry_later_command_or_ready_claim(self):
        for index, failing in enumerate(("shutdown", "boot", "bootstatus")):
            with self.subTest(failing=failing):
                result, output, calls, phases = self.run_restart(failing)
                self.assertEqual(result.returncode, 47, result.stderr)
                self.assertEqual(
                    [call["argv"] for call in calls], list(self.commands[: index + 1])
                )
                self.assertEqual(
                    [call["phase"] for call in calls], list(self.phases[: index + 1])
                )
                self.assertEqual(phases, list(self.phases[: index + 1]))
                self.assertEqual(
                    json.loads((output / "phase.json").read_text())["phase"],
                    self.phases[index],
                )
                self.assertFalse((output / "prepared.json").exists())
                self.assertFalse((output / "install-lifecycle.txt").exists())


class SignalTests(unittest.TestCase):
    def test_stage_entrypoint_installs_bounded_supervisor_interrupt_path(self):
        import signal

        previous = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
        try:
            stage.install_signal_handlers()
            handler = signal.getsignal(signal.SIGTERM)
            with self.assertRaises(stage.Interrupted):
                handler(signal.SIGTERM, None)
            self.assertEqual(signal.getsignal(signal.SIGTERM), signal.SIG_IGN)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)


if __name__ == "__main__":
    unittest.main()
