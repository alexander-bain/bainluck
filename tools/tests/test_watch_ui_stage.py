"""Preparation and upload cannot reset the50m gate or consume an hour silently."""

import json
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
