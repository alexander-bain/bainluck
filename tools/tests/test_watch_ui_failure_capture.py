"""A preparation failure keeps its exit and names the failed install."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FailureCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "out"
        self.out.mkdir()
        (self.out / "preflight.log").write_text("")
        (self.out / "tests.log").write_text("")
        self.calls = self.root / "calls.jsonl"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.root / "tools").mkdir()
        stub = self.bin / "xcrun"
        stub.write_text(
            "#!" + sys.executable + "\n"
            "import json,os,sys\n"
            "with open(os.environ['CALLS'],'a') as f:"
            "f.write(json.dumps({'tool':'xcrun','args':sys.argv[1:]})+'\\n')\n"
            "assert sys.argv[1:3]==['simctl','install']\n"
            "if sys.argv[3]==os.environ.get('FAIL_DEVICE'):\n"
            " print('fixture install failed',file=sys.stderr);sys.exit(149)\n"
        )
        stub.chmod(0o755)
        (self.root / "tools/watch_failure_evidence.py").write_text(
            "import json,os,sys\n"
            "with open(os.environ['CALLS'],'a') as f:"
            "f.write(json.dumps({'tool':'snapshot','args':sys.argv[1:]})+'\\n')\n"
            "raise SystemExit(int(os.environ.get('SNAPSHOT_EXIT','0')))\n"
        )
        self.source = (ROOT / "tools/watch-ui-journey.sh").read_text()

    def function(self, name):
        return (
            name
            + "() {"
            + self.source.split(name + "() {", 1)[1].split("\n}\n", 1)[0]
            + "\n}\n"
        )

    def run_installs(self, **extra):
        env = {
            **os.environ,
            "ROOT": str(self.root),
            "OUT": str(self.out),
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "CALLS": str(self.calls),
            "PHASE": "explicitly install companion and nested Watch app on the new pair",
            "SHA": "a" * 40,
            "PHONE_UDID": "11111111-1111-1111-1111-111111111111",
            "TEST_UDID": "22222222-2222-2222-2222-222222222222",
            "BUILT_PHONE": "/package/phone/Bain Luck.app",
            "BUILT_APP": "/package/watch/BainLuckWatch.app",
            **extra,
        }
        calls = (
            'install_product "$PHONE_UDID" "$BUILT_PHONE" phone\n'
            'install_product "$TEST_UDID" "$BUILT_APP" watch\n'
        )
        self.assertIn(calls.rstrip(), self.source)
        shell = (
            "set -euo pipefail\n"
            + self.function("failure")
            + self.function("install_product")
            + "trap failure ERR\n"
            + calls
        )
        result = subprocess.run(
            ["bash", "-c", shell],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        rows = [json.loads(line) for line in self.calls.read_text().splitlines()]
        return result, rows, (self.out / "install-lifecycle.txt").read_text()

    def test_phone_failure_records_status_and_stops_before_watch(self):
        result, rows, lifecycle = self.run_installs(
            FAIL_DEVICE="11111111-1111-1111-1111-111111111111"
        )
        self.assertEqual(result.returncode, 149)
        self.assertIn("phone install-start", lifecycle)
        self.assertIn("phone install-end exit=149", lifecycle)
        self.assertNotIn("watch install-start", lifecycle)
        self.assertEqual([r["tool"] for r in rows], ["xcrun", "snapshot"])
        args = rows[1]["args"]
        self.assertEqual(args[args.index("--exit-code") + 1], "149")
        self.assertEqual(args[args.index("--sha") + 1], "a" * 40)
        self.assertIn("fixture install failed", result.stderr)

    def test_watch_failure_records_both_exact_installs(self):
        result, rows, lifecycle = self.run_installs(
            FAIL_DEVICE="22222222-2222-2222-2222-222222222222"
        )
        self.assertEqual(result.returncode, 149)
        self.assertIn("phone install-end exit=0", lifecycle)
        self.assertIn("watch install-end exit=149", lifecycle)
        self.assertEqual([r["tool"] for r in rows], ["xcrun", "xcrun", "snapshot"])
        self.assertEqual(
            [r["args"][2:] for r in rows[:2]],
            [
                [
                    "11111111-1111-1111-1111-111111111111",
                    "/package/phone/Bain Luck.app",
                ],
                [
                    "22222222-2222-2222-2222-222222222222",
                    "/package/watch/BainLuckWatch.app",
                ],
            ],
        )

    def test_snapshot_failure_cannot_mask_or_retry_original_failure(self):
        result, rows, _ = self.run_installs(
            FAIL_DEVICE="11111111-1111-1111-1111-111111111111", SNAPSHOT_EXIT="42"
        )
        self.assertEqual(result.returncode, 149)
        self.assertEqual([r["tool"] for r in rows], ["xcrun", "snapshot"])
        self.assertIn("snapshot unavailable", result.stderr)
        self.assertIn("failed (exit 149)", result.stderr)

    def test_success_has_no_failure_snapshot_or_extra_simulator_action(self):
        result, rows, lifecycle = self.run_installs()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([r["tool"] for r in rows], ["xcrun", "xcrun"])
        self.assertEqual(lifecycle.count("install-start"), 2)
        self.assertEqual(lifecycle.count("install-end exit=0"), 2)

    def test_missing_snapshot_helper_keeps_original_nonzero_exit(self):
        (self.root / "tools/watch_failure_evidence.py").unlink()
        result, rows, lifecycle = self.run_installs(
            FAIL_DEVICE="11111111-1111-1111-1111-111111111111"
        )
        self.assertEqual(result.returncode, 149)
        self.assertEqual([r["tool"] for r in rows], ["xcrun"])
        self.assertIn("phone install-end exit=149", lifecycle)

    def test_real_helper_records_failed_install_and_only_the_exact_pair(self):
        log_root = self.root / "logs"
        log_root.mkdir()
        (log_root / "CoreSimulator.log").write_text("fixture service failure\n")
        (self.root / "tools/watch_failure_evidence.py").write_text(
            "import importlib.util,os,sys\nfrom pathlib import Path\n"
            f"s=importlib.util.spec_from_file_location('helper',{str(ROOT / 'tools/watch_failure_evidence.py')!r})\n"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
            "raise SystemExit(m.main(sys.argv[1:],log_root=Path(os.environ['SNAPSHOT_LOG_ROOT'])))\n"
        )
        stub = self.bin / "xcrun"
        stub.write_text(
            "#!" + sys.executable + "\n"
            "import json,os,sys\nargs=sys.argv[1:]\n"
            "with open(os.environ['CALLS'],'a') as f:"
            "f.write(json.dumps({'tool':'xcrun','args':args})+'\\n')\n"
            "if args[:2]==['simctl','install']:sys.exit(149)\n"
            "if args==['simctl','list','devices','--json']:\n"
            " print(json.dumps({'devices':{'runtime':["
            "{'udid':os.environ['TEST_UDID'],'state':'Booted'},"
            "{'udid':os.environ['PHONE_UDID'],'state':'Shutdown'}]}}));sys.exit(0)\n"
            "if args==['simctl','list','pairs','--json']:\n"
            " print(json.dumps({'pairs':{'exact':{"
            "'watch':{'udid':os.environ['TEST_UDID']},"
            "'phone':{'udid':os.environ['PHONE_UDID']},"
            "'state':'(active, disconnected)'}}}));sys.exit(0)\n"
            "raise SystemExit('Unexpected command')\n"
        )
        result, rows, lifecycle = self.run_installs(SNAPSHOT_LOG_ROOT=str(log_root))
        self.assertEqual(result.returncode, 149, result.stderr)
        self.assertIn("phone install-end exit=149", lifecycle)
        self.assertEqual(
            [r["args"][:3] for r in rows],
            [
                ["simctl", "install", "11111111-1111-1111-1111-111111111111"],
                ["simctl", "list", "devices"],
                ["simctl", "list", "pairs"],
            ],
        )
        evidence = json.loads((self.out / "failure-evidence.json").read_text())
        self.assertEqual(evidence["original_failure"]["exit_code"], 149)
        self.assertEqual(evidence["original_failure"]["status"], "unpaid")
        self.assertFalse(evidence["test_receipt"])
        self.assertEqual(evidence["devices"]["phone"]["state"], "Shutdown")
        self.assertEqual(evidence["pairs"]["exact_pair_count"], 1)
        self.assertEqual(
            (self.out / "failure-evidence-coresimulator.log").read_text(),
            "fixture service failure\n",
        )

    def test_xcode_failure_diagnostics_preserve_every_execution_argument(self):
        call = self.source.split("if xcodebuild test-without-building", 1)[1].split(
            '> "$OUT/tests.log" 2>&1; then', 1
        )[0]
        shell = (
            "set -euo pipefail\n"
            "xcodebuild() { "
            + sys.executable
            + " -c 'import json,sys; print(json.dumps(sys.argv[1:]))' \"$@\"; }\n"
            "XCODE_ARGS=(-xctestrun owned.xctestrun -destination owned-watch -parallel-testing-enabled NO)\n"
            "TEST_SELECTION=(-only-testing:ExactCase)\nRESULT=owned.xcresult\n"
            "xcodebuild test-without-building" + call
        )
        result = subprocess.run(
            ["bash", "-c", shell], capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(result.stdout)
        self.assertEqual(args[args.index("-collect-test-diagnostics") + 1], "never")
        self.assertEqual(
            args[args.index("-default-test-execution-time-allowance") + 1], "180"
        )
        self.assertEqual(
            args[args.index("-maximum-test-execution-time-allowance") + 1], "300"
        )
        self.assertIn("-only-testing:ExactCase", args)
        self.assertIn("-test-timeouts-enabled", args)
        self.assertEqual(
            args,
            [
                "test-without-building",
                "-xctestrun",
                "owned.xctestrun",
                "-destination",
                "owned-watch",
                "-parallel-testing-enabled",
                "NO",
                "-only-testing:ExactCase",
                "-resultBundlePath",
                "owned.xcresult",
                "-collect-test-diagnostics",
                "never",
                "-test-timeouts-enabled",
                "YES",
                "-default-test-execution-time-allowance",
                "180",
                "-maximum-test-execution-time-allowance",
                "300",
            ],
        )


if __name__ == "__main__":
    unittest.main()
