"""A full Watch verdict cannot be assembled from partial or mixed-source runs."""

import ast
import subprocess
import importlib.util
import json
import os
import plistlib
import shlex
import signal
import sys
from pathlib import Path
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "watch_ui_shards", ROOT / "tools/watch_ui_shards.py"
)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


ALIAS_MARKERS = (
    "WATCH_UI_PICKER_ALIAS_STANDARD=PASS",
    "WATCH_UI_PICKER_ALIAS_LARGE=PASS",
    "WATCH_UI_PICKER_ALIAS_UNPROVEN_CONTROL=PASS",
    "WATCH_UI_PICKER_ALIAS_SAVED_BANNER_LARGE=PASS",
)
ALIAS_CASES = (
    "testResolvedAliasRetainsReadingOfflineAndAfterRestart",
    "testResolvedAliasRetainsReadingAtAccessibilitySize",
    "testUnprovenSameNameChoiceDoesNotReuseSavedReading",
    "testRestoredSavedBannerIsReadableAtAccessibilitySize",
)


class WatchUIShardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.groups = gate.manifest()
        self.sha = "a" * 40
        for index, (shard, cases) in enumerate(self.groups.items()):
            part = self.root / shard
            part.mkdir()
            rows = [
                f"Test Case '-[BainLuckWatchUITests.{case.replace('/', ' ')}]' passed (1.0 seconds)."
                for case in cases
            ]
            rows += [
                "Test Suite 'Selected tests' passed at now.",
                f" Executed {len(cases)} tests, with 0 failures (0 unexpected)",
                "** TEST EXECUTE SUCCEEDED **",
            ]
            (part / "tests.log").write_text("\n".join(rows))
            (part / "test-exit.txt").write_text("0")
            (part / "source.txt").write_text(self.sha)
            (part / "destination.txt").write_text(f"watch-{index}")
            (part / "phone-destination.txt").write_text(f"phone-{index}")
            (part / "simulator-widget-signing.json").write_text(
                json.dumps({"sha": self.sha, "verdict": "PASS"})
            )
            (part / "products-verification.json").write_text(
                json.dumps(
                    {
                        "sha": self.sha,
                        "verdict": "PASS",
                        "manifest_sha256": "c" * 64,
                    }
                )
            )
            self.save_receipt(shard)

    def save_receipt(self, shard):
        part = self.root / shard
        receipt = gate.shard_receipt(part, shard, self.sha, 0, self.groups)
        (part / "receipt.json").write_text(json.dumps(receipt))

    def verify(self):
        return gate.aggregate(self.root, self.sha, self.groups, verify_markers=False)

    def test_complete_distinct_pairs_cover_all_101_selected_game_cases(self):
        self.assertEqual(self.verify()["tests"], 101)
        self.assertEqual(
            self.groups["corner"],
            ["WidgetTapJourneyTests/testActualCornerLauncherAndTap"],
        )
        self.assertEqual(len(self.groups["readings"]), 11)
        self.assertEqual(len(self.groups["navigation"]), 39)
        self.assertEqual(len(self.groups["controls"]), 33)
        self.assertEqual(len(self.groups["widgets"]), 17)

    def test_composed_fixture_preserves_fixed_clock_and_provider_alias(self):
        source = (
            ROOT / "ios/Bain Luck/BainLuckWatch Watch App/WatchUIFixture.swift"
        ).read_text()
        environment_keys = source.split("let keys =", 1)[1].split(
            "UserDefaults.standard.set", 1
        )[0]
        self.assertIn('"BAINLUCK_WATCH_UI_FIXED_OBSERVATION"', environment_keys)
        for required in (
            "var fixedObservation: Date? = nil",
            'fixedObservation: environment["BAINLUCK_WATCH_UI_FIXED_OBSERVATION"]',
            "fixedObservation ?? Date().addingTimeInterval(-60)",
            "var pickerAlias: WatchPickerAliasFixture?",
            'pickerAlias: environment["BAINLUCK_WATCH_UI_PICKER_ALIAS"]',
            "if offline && pickerAlias == nil",
            "if let pickerAlias { return try await pickerAlias.fetch(eventID: eventID) }",
            "actor WatchPickerAliasFixture {",
            "guard !resolved else { throw URLError(.notConnectedToInternet) }",
            '"id": 111',
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)

    def test_preparation_builds_selected_architecture_in_fresh_runs(self):
        harness = (ROOT / "tools/watch-ui-products.sh").read_text()
        setup = "RUN=" + harness.split("RUN=", 1)[1].split("RESULT=", 1)[0]
        builds = (
            "XCODE_ARGS=("
            + harness.split("XCODE_ARGS=(", 1)[1].split("PHASE='package immutable", 1)[
                0
            ]
        )
        builds = "\n".join(
            line for line in builds.splitlines() if "watch_ui_stage.py" not in line
        )
        record = self.root / "build-commands.jsonl"
        capture = (
            "import json,os,sys; "
            "open(os.environ['RECORD'], 'a').write(json.dumps(sys.argv[1:])+'\\n')"
        )
        shell = (
            "set -eu\n"
            "xcodebuild() { "
            + shlex.quote(sys.executable)
            + " -c "
            + shlex.quote(capture)
            + ' "$@"; }\n'
            + setup
            + builds
        )
        environment = dict(
            os.environ,
            ROOT=str(self.root),
            OUT=str(self.root),
            RECORD=str(record),
            TEST_UDID="owned-watch",
            PHONE_UDID="owned-phone",
            SIM_ARCH="arm64",
        )
        roots = []
        for _ in range(2):
            record.write_text("")
            subprocess.run(["bash", "-c", shell], env=environment, check=True)
            calls = [json.loads(line) for line in record.read_text().splitlines()]
            self.assertEqual(
                [call[0] for call in calls], ["build-for-testing", "build"]
            )
            build_for_testing, companion = calls
            # Only a concrete-device build writes the checker insert (#11201).
            self.assertEqual(build_for_testing.count("-destination"), 1)
            self.assertEqual(
                build_for_testing[build_for_testing.index("-destination") + 1],
                "platform=watchOS Simulator,id=owned-watch",
            )
            self.assertEqual(companion.count("-destination"), 1)
            self.assertEqual(
                companion[companion.index("-destination") + 1],
                "generic/platform=iOS Simulator",
            )
            self.assertFalse(
                [argument for argument in companion if "id=" in argument],
                "No companion build may ask Xcode for a concrete simulator",
            )
            derived = [call[call.index("-derivedDataPath") + 1] for call in calls]
            for call in calls:
                self.assertEqual(call.count("ARCHS=arm64"), 1)
            roots.append(derived)
            self.assertTrue(Path(derived[0]).parent.is_dir())
        self.assertNotEqual(
            roots[0], roots[1], "New runs must never reuse old products"
        )

    def run_architecture_phase(self, listing_devices=True, simctl_phone=True):
        harness = (ROOT / "tools/watch-ui-products.sh").read_text()
        phase = (
            "PHASE='resolve the architecture"
            + harness.split("PHASE='resolve the architecture", 1)[1].split(
                "XCODE_ARGS=(", 1
            )[0]
        )
        phase = "\n".join(
            line for line in phase.splitlines() if "watch_ui_stage.py" not in line
        )
        out = self.root / "products"
        out.mkdir()
        fixtures = self.root / "fixtures"
        fixtures.mkdir()
        info = {"runtimes": [], "devices": {}}
        for platform, family, udid in [
            ("watchOS", "Apple Watch", "owned-watch"),
            ("iOS", "iPhone", "owned-phone"),
        ]:
            info["runtimes"].append(
                {
                    "identifier": "runtime-" + platform,
                    "platform": platform,
                    "isAvailable": True,
                    "version": "27.0",
                    "supportedArchitectures": ["arm64"],
                    "supportedDeviceTypes": [
                        {"identifier": "type-" + platform, "productFamily": family}
                    ],
                }
            )
            info["devices"]["runtime-" + platform] = [
                {
                    "udid": udid,
                    "deviceTypeIdentifier": "type-" + platform,
                    "isAvailable": True,
                    "state": "Booted",
                }
            ]
        if not simctl_phone:
            info["devices"]["runtime-iOS"] = []
        (fixtures / "simulators.json").write_text(json.dumps(info))
        (fixtures / "pairs.json").write_text(
            json.dumps(
                {
                    "pairs": {
                        "pair": {
                            "watch": {"udid": "owned-watch"},
                            "phone": {"udid": "owned-phone"},
                            "state": "(active, connected)",
                        }
                    }
                }
            )
        )
        # The attempt-1 / 39089526172 shape: only the generic placeholder survives.
        listing = "Available destinations for the scheme:\n"
        listing += "\t{ platform:watchOS Simulator, id:dvtdevice-generic, name:Any watchOS Simulator Device }\n"
        listing += "\t{ platform:iOS Simulator, id:dvtdevice-generic, name:Any iOS Simulator Device }\n"
        if listing_devices:
            listing += "\t{ platform:watchOS Simulator, arch:arm64, id:owned-watch, OS:27.0, name:Owned }\n"
            listing += "\t{ platform:iOS Simulator, arch:arm64, id:owned-phone, OS:27.0, name:Owned }\n"
        (fixtures / "listing.log").write_text(listing)
        record = self.root / "phase-commands.log"
        shell = (
            "set -euo pipefail\n"
            'xcodebuild() { printf "xcodebuild %s\\n" "$*" >> "$RECORD"; '
            'cat "$FIXTURES/listing.log"; }\n'
            'xcrun() { printf "xcrun %s\\n" "$*" >> "$RECORD"; case "$*" in\n'
            '  "simctl list --json") cat "$FIXTURES/simulators.json" ;;\n'
            '  "simctl list pairs --json") cat "$FIXTURES/pairs.json" ;;\n'
            '  "--sdk iphonesimulator --show-sdk-version") echo 27.0 ;;\n'
            "  *) return 97 ;;\n"
            "esac; }\n"
            'python3() { printf "python3 %s\\n" "$*" >> "$RECORD"; '
            + shlex.quote(sys.executable)
            + ' "$@"; }\n'
            + phase
            + '\nprintf "%s\\n" "$SIM_ARCH" > "$OUT/sim-arch.txt"\n'
        )
        environment = dict(
            os.environ,
            ROOT=str(ROOT),
            OUT=str(out),
            PACKAGES=str(self.root / "packages"),
            FIXTURES=str(fixtures),
            RECORD=str(record),
            TEST_UDID="owned-watch",
            PHONE_UDID="owned-phone",
            SDK_VERSION="27.0",
        )
        process = subprocess.run(
            ["bash", "-c", shell], env=environment, capture_output=True, text=True
        )
        return process, out, record.read_text().splitlines()

    def test_architecture_comes_from_coresimulator_not_xcode_listings(self):
        for listing_devices in (True, False):
            with self.subTest(listing_devices=listing_devices):
                self.root = Path(tempfile.mkdtemp(dir=self.temp.name))
                process, out, commands = self.run_architecture_phase(listing_devices)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual((out / "sim-arch.txt").read_text(), "arm64\n")
                gate = [c for c in commands if "watch_simulator_architecture.py" in c]
                self.assertEqual(len(gate), 1)
                arguments = shlex.split(gate[0])
                self.assertIn("--prepared-pair", arguments)
                for flag, value in (
                    ("--watch-id", "owned-watch"),
                    ("--phone-id", "owned-phone"),
                    ("--watch-sdk", "27.0"),
                    ("--phone-sdk", "27.0"),
                ):
                    self.assertEqual(arguments[arguments.index(flag) + 1], value)
                self.assertNotIn("--watch-destinations", arguments)
                self.assertNotIn("--phone-destinations", arguments)
                listings = [c for c in commands if c.startswith("xcodebuild ")]
                self.assertEqual(len(listings), 2)
                for log in ("watch-destinations.log", "phone-destinations.log"):
                    self.assertIn("Any ", (out / log).read_text())
                self.assertEqual(
                    json.loads((out / "simulator-architecture.json").read_text())[
                        "verdict"
                    ],
                    "PASS",
                )

    def test_a_pair_coresimulator_does_not_hold_stops_the_producer(self):
        process, out, commands = self.run_architecture_phase(simctl_phone=False)
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse((out / "sim-arch.txt").exists())
        receipt = json.loads((out / "simulator-architecture.json").read_text())
        self.assertEqual(receipt["verdict"], "UNPAID")
        self.assertIn("missing", receipt["reason"])

    def test_generic_products_still_execute_on_the_exact_new_pair(self):
        journey = (ROOT / "tools/watch-ui-journey.sh").read_text()
        execute = journey.split("XCODE_ARGS=(-xctestrun", 1)[1].split("\n", 1)[0]
        self.assertEqual(
            execute,
            ' "$XCTESTRUN" -destination "platform=watchOS Simulator,id=$TEST_UDID"'
            " -parallel-testing-enabled NO)",
        )
        self.assertNotIn("generic/", journey)

    def test_products_pack_from_the_runtime_record_taken_after_preparation(self):
        # 1775's producer listed the Watch runtime under Volumes/ before booting
        # the pair and under the cryptexd mount afterwards; a concrete build
        # writes the mounted checker path. Only the later record relocates it.
        harness = (ROOT / "tools/watch-ui-products.sh").read_text()
        prepared = harness.index('> "$OUT/prepared-simulators.json"')
        self.assertLess(harness.index('bootstatus "$TEST_UDID" -b'), prepared)
        self.assertLess(prepared, harness.index("xcodebuild build-for-testing"))
        start = harness.index('python3 "$ROOT/tools/watch_ui_products.py" pack')
        end = harness.index("\n", harness.index('--watch-runtime "$RUNTIME"', start))
        out = self.root / "products"
        out.mkdir()
        record = self.root / "pack-command.jsonl"
        capture = (
            "import json,os,sys; "
            "open(os.environ['RECORD'], 'a').write(json.dumps(sys.argv[1:])+'\\n')"
        )
        shell = (
            "set -eu\npython3() { "
            + shlex.quote(sys.executable)
            + " -c "
            + shlex.quote(capture)
            + ' "$@"; }\n'
            + harness[start:end]
            + "\n"
        )
        environment = dict(
            os.environ,
            ROOT=str(ROOT),
            OUT=str(out),
            RUN=str(self.root / "run"),
            RECORD=str(record),
            SHA=self.sha,
            DERIVED="derived",
            PHONE_DERIVED="phone-derived",
            SIM_ARCH="arm64",
            RUNTIME="com.apple.CoreSimulator.SimRuntime.watchOS-27-0",
        )
        subprocess.run(["bash", "-c", shell], env=environment, check=True)
        (arguments,) = [json.loads(line) for line in record.read_text().splitlines()]
        self.assertEqual(
            arguments[arguments.index("--simulators") + 1],
            str(out / "prepared-simulators.json"),
        )
        spec = importlib.util.spec_from_file_location(
            "watch_ui_products", ROOT / "tools/watch_ui_products.py"
        )
        products = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(products)
        tail = "Library/Developer/CoreSimulator/Profiles/Runtimes/watchOS 27.0.simruntime/Contents/Resources/RuntimeRoot"
        mounted = self.root / "cryptexd/mnt/watchOS_24R362" / tail
        checker = mounted / "usr/lib/libMainThreadChecker.dylib"
        checker.parent.mkdir(parents=True)
        checker.write_bytes(b"selected-runtime-checker")
        for name, root in (
            ("simulators.json", self.root / "Volumes/watchOS_24R362" / tail),
            ("prepared-simulators.json", mounted),
        ):
            runtime = {
                "identifier": environment["RUNTIME"],
                "platform": "watchOS",
                "isAvailable": True,
                "version": "27.0",
                "buildversion": "24R362",
                "runtimeRoot": str(root),
            }
            (out / name).write_text(json.dumps({"runtimes": [runtime]}))

        def relocation(simulators):
            from unittest.mock import patch

            selected = []
            argv = list(arguments)
            argv[argv.index("--simulators") + 1] = str(simulators)
            with patch.object(sys, "argv", argv), patch.object(
                products, "pack", side_effect=lambda *a: selected.append(a[6])
            ):
                products.main()
            payload = Path(tempfile.mkdtemp(dir=self.root)) / "payload"
            run = payload / "watch/Build/Products/BainLuckWatchUITests.xctestrun"
            run.parent.mkdir(parents=True)
            run.write_bytes(
                plistlib.dumps(
                    {
                        products.XCTEST: {
                            "TestingEnvironmentVariables": {
                                "DYLD_INSERT_LIBRARIES": str(checker)
                            }
                        },
                        "__xctestrun_metadata__": {"FormatVersion": 1},
                    }
                )
            )
            mapping = products.runtime_support(payload, selected[0])
            inserted = plistlib.loads(run.read_bytes())[products.XCTEST][
                "TestingEnvironmentVariables"
            ]["DYLD_INSERT_LIBRARIES"]
            return mapping, inserted

        mapping, inserted = relocation(out / "prepared-simulators.json")
        self.assertEqual(
            inserted, "__TESTROOT__/RuntimeSupport/libMainThreadChecker.dylib"
        )
        self.assertEqual(mapping[0]["sections"], ["TestingEnvironmentVariables"])
        self.assertEqual(mapping[0]["runtime_checker_path"], str(checker))
        # The first listing names no mount the build used: nothing relocates and
        # the journey would have to find the producer's absolute path itself.
        self.assertEqual(relocation(out / "simulators.json"), ([], str(checker)))

    def test_runtime_receipts_record_three_points_without_changing_the_gate(self):
        journey = (ROOT / "tools/watch-ui-journey.sh").read_text()
        lines = journey.splitlines()
        calls = [line for line in lines if line.startswith("runtime_receipt ")]
        self.assertEqual(
            calls,
            [
                "runtime_receipt before-products-verification",
                'runtime_receipt boot-ready "$TEST_UDID" "$PHONE_UDID"',
                'runtime_receipt before-test-without-building "$TEST_UDID" "$PHONE_UDID"',
            ],
        )
        # Before any device exists, then this run's own pair at boot-ready and
        # directly before XCTest, each beside the step it describes.
        self.assertLess(
            journey.index(calls[0]), journey.index('TEST_UDID="$(xcrun simctl create')
        )
        self.assertTrue(
            lines[lines.index(calls[0]) + 1].startswith(
                'python3 "$ROOT/tools/watch_ui_products.py" verify '
            )
        )
        self.assertLess(journey.index("boot-ready' >>"), journey.index(calls[1]))
        self.assertEqual(
            lines[lines.index(calls[1]) - 1 : lines.index(calls[1]) + 2 : 2],
            ["STATE", "exit 0"],
        )
        self.assertTrue(
            lines[lines.index(calls[2]) + 1].startswith(
                'if xcodebuild test-without-building "${XCODE_ARGS[@]}"'
            )
        )
        start = journey.index("runtime_receipt() {")
        end = "\nRUNTIME_RECEIPT\n}\n"
        helper = journey[start : journey.index(end, start) + len(end)]
        fixtures = self.root / "receipt-fixtures"
        (fixtures / "bin").mkdir(parents=True)
        runtimes = [
            {
                "identifier": "com.apple.CoreSimulator.SimRuntime.watchOS-27-0",
                "bundlePath": "/Library/Developer/CoreSimulator/Volumes/watchOS_24R362/x.simruntime",
                "isAvailable": True,
            }
        ]
        (fixtures / "runtimes.json").write_text(json.dumps({"runtimes": runtimes}))
        devices = {
            "devices": {
                "watch-runtime": [
                    {"udid": "owned-watch", "state": "Booted"},
                    {"udid": "shared-watch", "state": "Shutdown"},
                ],
                "phone-runtime": [{"udid": "owned-phone", "state": "Booted"}],
                "other-runtime": [{"udid": "shared-phone", "state": "Booted"}],
            }
        }
        (fixtures / "devices.json").write_text(json.dumps(devices))
        xcrun = fixtures / "bin/xcrun"
        xcrun.write_text(
            "#!/bin/bash\n"
            'printf "%s\\n" "$*" >> "$FIXTURES/xcrun-calls.txt"\n'
            'case "$XCRUN_MODE $*" in\n'
            '  "ok simctl list runtimes --json") cat "$FIXTURES/runtimes.json" ;;\n'
            '  "ok simctl list devices --json") cat "$FIXTURES/devices.json" ;;\n'
            "  fail*) echo 'The watchOS 27.0 simulator runtime is not available' >&2; exit 3 ;;\n"
            "  *) exit 97 ;;\n"
            "esac\n"
        )
        xcrun.chmod(0o755)

        def run(mode, unwritable=False):
            out = Path(tempfile.mkdtemp(dir=self.root))
            (fixtures / "xcrun-calls.txt").write_text("")
            if unwritable:
                (out / "runtime-receipts.jsonl").mkdir()
            shell = (
                "set -euo pipefail\n"
                "trap 'echo trapped > \"$OUT/trapped.txt\"; exit 99' ERR\n"
                + helper
                + "runtime_receipt before-products-verification\n"
                + "runtime_receipt boot-ready owned-watch owned-phone\n"
                + 'echo continued > "$OUT/continued.txt"\n'
            )
            environment = dict(
                os.environ,
                OUT=str(out),
                FIXTURES=str(fixtures),
                XCRUN_MODE=mode,
                PATH=str(fixtures / "bin") + os.pathsep + os.environ["PATH"],
            )
            process = subprocess.run(
                ["bash", "-c", shell], env=environment, capture_output=True, text=True
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertFalse((out / "trapped.txt").exists())
            self.assertEqual((out / "continued.txt").read_text(), "continued\n")
            calls = (fixtures / "xcrun-calls.txt").read_text().splitlines()
            # One read of each record per point: never retried.
            self.assertEqual(
                calls,
                [
                    "simctl list runtimes --json",
                    "simctl list runtimes --json",
                    "simctl list devices --json",
                ],
            )
            if unwritable:
                return out, None
            receipts = [
                json.loads(line)
                for line in (out / "runtime-receipts.jsonl").read_text().splitlines()
            ]
            self.assertEqual(
                [r["point"] for r in receipts],
                ["before-products-verification", "boot-ready"],
            )
            self.assertEqual(receipts[0]["selected_devices"], [])
            self.assertNotIn("devices_read", receipts[0])
            self.assertEqual(
                receipts[1]["selected_devices"], ["owned-watch", "owned-phone"]
            )
            return out, receipts

        _, receipts = run("ok")
        for receipt in receipts:
            self.assertEqual(receipt["runtimes"], runtimes)
            self.assertEqual(receipt["runtimes_read"]["exit_code"], 0)
        self.assertEqual(
            receipts[1]["devices"],
            {
                "watch-runtime": [{"udid": "owned-watch", "state": "Booted"}],
                "phone-runtime": [{"udid": "owned-phone", "state": "Booted"}],
            },
        )
        _, receipts = run("fail")
        for receipt in receipts:
            for key in ("runtimes", "devices"):
                self.assertNotIn(key, receipt)
            read = receipt["runtimes_read"]
            self.assertEqual(read["exit_code"], 3)
            self.assertIn("runtime is not available", read["stderr"])
            self.assertIn("read_error", read)
        self.assertEqual(receipts[1]["devices_read"]["exit_code"], 3)
        out, _ = run("ok", unwritable=True)
        self.assertEqual(
            (out / "preflight.log").read_text().splitlines(),
            [
                "runtime receipt before-products-verification not written (exit 1)",
                "runtime receipt boot-ready not written (exit 1)",
            ],
        )

    def test_a_hung_runtime_read_is_cut_at_fifteen_seconds_and_the_gate_continues(self):
        # A hung simctl is likely in the runtime-loss family these receipts
        # describe. The 15 s bound is what keeps the receipt from spending the
        # step's own timeout and losing the real xcodebuild result.
        journey = (ROOT / "tools/watch-ui-journey.sh").read_text()
        start = journey.index("runtime_receipt() {")
        end = "\nRUNTIME_RECEIPT\n}\n"
        helper = journey[start : journey.index(end, start) + len(end)]
        fixtures = self.root / "hang-fixtures"
        (fixtures / "bin").mkdir(parents=True)
        xcrun = fixtures / "bin/xcrun"
        xcrun.write_text(
            "#!/bin/bash\n"
            'printf "%s\\n" "$*" >> "$FIXTURES/xcrun-calls.txt"\n'
            "exec sleep 120\n"
        )
        xcrun.chmod(0o755)
        out = Path(tempfile.mkdtemp(dir=self.root))
        shell = (
            "set -euo pipefail\n"
            "trap 'echo trapped > \"$OUT/trapped.txt\"; exit 99' ERR\n"
            + helper
            + "runtime_receipt before-products-verification\n"
            + 'echo continued > "$OUT/continued.txt"\n'
        )
        environment = dict(
            os.environ,
            OUT=str(out),
            FIXTURES=str(fixtures),
            PATH=str(fixtures / "bin") + os.pathsep + os.environ["PATH"],
        )
        process = subprocess.Popen(
            ["bash", "-c", shell],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        began = time.monotonic()
        try:
            _, stderr = process.communicate(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            self.fail("the receipt waited on a hung simctl past 45 s: it is unbounded")
        elapsed = time.monotonic() - began
        self.assertEqual(process.returncode, 0, stderr)
        self.assertFalse((out / "trapped.txt").exists())
        self.assertEqual((out / "continued.txt").read_text(), "continued\n")
        # The fixture really hung: the read was cut by the bound, not answered.
        self.assertGreaterEqual(elapsed, 14)
        # One attempt, no retry.
        self.assertEqual(
            (fixtures / "xcrun-calls.txt").read_text().splitlines(),
            ["simctl list runtimes --json"],
        )
        (receipt,) = [
            json.loads(line)
            for line in (out / "runtime-receipts.jsonl").read_text().splitlines()
        ]
        self.assertEqual(receipt["point"], "before-products-verification")
        self.assertNotIn("runtimes", receipt)
        read = receipt["runtimes_read"]
        self.assertNotIn("exit_code", read)
        self.assertTrue(read["read_error"].startswith("TimeoutExpired("), read)
        self.assertTrue(read["read_error"].endswith(", 15)"), read)
        self.assertFalse((out / "preflight.log").exists())

    def test_mixed_immutable_product_packages_cannot_form_full_gate(self):
        path = self.root / "readings/products-verification.json"
        data = json.loads(path.read_text())
        data["manifest_sha256"] = "d" * 64
        path.write_text(json.dumps(data))
        self.save_receipt("readings")
        with self.assertRaisesRegex(ValueError, "different immutable"):
            self.verify()

    def test_missing_failed_or_wrong_source_shard_is_unpaid(self):
        path = self.root / "readings/receipt.json"
        original = path.read_text()
        for mutation in (
            {"verdict": "UNPAID"},
            {"sha": "b" * 40},
            {"shard": "navigation"},
        ):
            with self.subTest(mutation=mutation):
                receipt = json.loads(original)
                receipt.update(mutation)
                path.write_text(json.dumps(receipt))
                with self.assertRaises(ValueError):
                    self.verify()
        path.unlink()
        with self.assertRaises(OSError):
            self.verify()

    def test_duplicate_missing_failed_skipped_or_interrupted_execution_is_unpaid(self):
        part = self.root / "readings"
        log = (part / "tests.log").read_text()
        first = log.splitlines()[0]
        for broken in (
            log + "\n" + first,
            log.replace(first, ""),
            log.replace("passed (", "failed ("),
            log.replace("passed (", "skipped ("),
            log.replace("** TEST EXECUTE SUCCEEDED **", ""),
            log + "\n** TEST EXECUTE FAILED **",
        ):
            with self.subTest(broken=broken):
                with self.assertRaises(ValueError):
                    gate.completed_cases(broken, 0, self.groups["readings"])
        with self.assertRaises(ValueError):
            gate.completed_cases(log, 65, self.groups["readings"])

    def test_retained_log_or_signature_cannot_disagree_with_receipt(self):
        part = self.root / "readings"
        (part / "simulator-widget-signing.json").write_text(
            json.dumps({"sha": self.sha, "verdict": "UNPAID"})
        )
        with self.assertRaises(ValueError):
            self.verify()

    def test_reused_pair_cannot_claim_isolation(self):
        (self.root / "readings/destination.txt").write_text(
            (self.root / "navigation/destination.txt").read_text()
        )
        self.save_receipt("readings")
        with self.assertRaises(ValueError):
            self.verify()

    def test_aggregate_requires_existing_markers_and_consent_receipt(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        code = ast.parse(
            harness.split("<<'PYVERIFY'\n", 1)[1].split("\nPYVERIFY", 1)[0]
        )
        markers = next(
            ast.literal_eval(node.iter)
            for node in ast.walk(code)
            if isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "marker"
        )
        path = self.root / "readings/tests.log"
        original = path.read_text()
        rows = [
            *markers,
            *ALIAS_MARKERS,
            "WATCH_UI_ACTUAL_CORNER_LAUNCHER=PASS",
            "WATCH_UI_STRESS_TYPE=accessibility5",
            "WATCH_UI_STANDARD_TYPE=xLarge",
            "WATCH_UI_DIAGNOSTICS_STANDARD=PASS",
            "WATCH_UI_DIAGNOSTICS_LARGE=PASS",
        ]
        complete = original + "\n" + "\n".join(rows)
        path.write_text(complete)
        self.assertEqual(gate.aggregate(self.root, self.sha, self.groups)["tests"], 101)
        for marker in (
            "WATCH_UI_ACTUAL_CIRCULAR_LAUNCHER=PASS",
            "WATCH_UI_ACTUAL_RECTANGULAR_LAUNCHER=PASS",
            *ALIAS_MARKERS,
            "WATCH_UI_ACTUAL_CORNER_LAUNCHER=PASS",
            "WATCH_UI_GAME_UPDATING_LARGE=PASS",
            "WATCH_UI_DIAGNOSTICS_LARGE=PASS",
        ):
            with self.subTest(marker=marker):
                path.write_text(complete.replace(marker, ""))
                with self.assertRaises(subprocess.CalledProcessError):
                    gate.aggregate(self.root, self.sha, self.groups)
        path.write_text(complete + "\nWATCH_UI_DIAGNOSTICS_LARGE=PASS")
        with self.assertRaises(subprocess.CalledProcessError):
            gate.aggregate(self.root, self.sha, self.groups)

    def test_alias_receipt_requires_exact_markers_and_one_passed_case(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        code = harness.split("<<'PYALIAS'\n", 1)[1].split("\nPYALIAS", 1)[0]
        cases = [
            f"Test Case '-[BainLuckWatchUITests.PickerAliasJourneyTests {case}]' passed (12.0 seconds)."
            for case in ALIAS_CASES
        ]
        complete = "\n".join((*ALIAS_MARKERS, *cases))
        log = self.root / "alias.log"

        def verify(text):
            log.write_text(text)
            return subprocess.run(
                [sys.executable, "-c", code, str(log)], capture_output=True, text=True
            ).returncode

        self.assertEqual(verify(complete), 0)
        for marker in ALIAS_MARKERS:
            for replacement in ("", marker + "\n" + marker, "prefix " + marker):
                with self.subTest(marker=marker, replacement=replacement):
                    self.assertEqual(verify(complete.replace(marker, replacement)), 1)
        for case in cases:
            for replacement in (
                "",
                case + "\n" + case,
                case.replace("passed", "failed"),
                case.replace("passed", "skipped"),
                case + "\n" + case.replace("passed", "failed"),
            ):
                with self.subTest(case=case, replacement=replacement):
                    self.assertEqual(verify(complete.replace(case, replacement)), 1)

    def test_full_harness_executes_alias_gate_without_optional_condition(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        full = harness.split(
            'if [[ "$TEST_EXIT" -eq 0 && "$SHARD" == full ]]; then', 1
        )[1]
        full = full.split("\nfi\n", 1)[0]
        between = full.split("\nPYVERIFY\n", 1)[1].split("<<'PYALIAS'", 1)[0]
        self.assertEqual(between.strip(), 'python3 - "$OUT/tests.log"')

    def test_workflow_runs_every_shard_and_always_checks_aggregate(self):
        import re

        workflow = (ROOT / ".github/workflows/watch-mvp.yml").read_text()
        split = workflow.split("  watch-ui-journey:", 1)[1].split(
            "  watch-ui-complete:", 1
        )[0]
        matrix = re.search(r"shard: \[(.*?)\]", split).group(1)
        self.assertEqual(set(matrix.split(", ")), set(self.groups))
        self.assertIn("fail-fast: false", split)
        self.assertIn("timeout-minutes: 60", split)
        self.assertIn("group: watch-ui-${{ matrix.shard }}-", split)
        complete = workflow.split("  watch-ui-complete:", 1)[1].split(
            "  companion-archive:", 1
        )[0]
        self.assertIn("needs: watch-ui-journey", complete)
        self.assertIn("if: always()", complete)
        downloads = set(re.findall(r"name: (watch-ui-journey-\w+)", complete))
        self.assertEqual(
            downloads, {f"watch-ui-journey-{shard}" for shard in self.groups}
        )

    def test_actual_corner_cannot_share_a_pair_with_other_cases(self):
        tools = self.root / "tools"
        source = self.root / "ios/Bain Luck/BainLuckWatchUITests"
        tools.mkdir()
        source.mkdir(parents=True)
        groups = {name: list(cases) for name, cases in self.groups.items()}
        groups["corner"].append(groups["readings"].pop())
        (tools / "watch_ui_cases.json").write_text(json.dumps(groups))
        suites = {}
        for cases in groups.values():
            for case in cases:
                suite, method = case.split("/")
                suites.setdefault(suite, []).append(f"func {method}() {{}}")
        for suite, methods in suites.items():
            (source / f"{suite}.swift").write_text("\n".join(methods))
        with self.assertRaisesRegex(ValueError, "own fresh pair"):
            gate.manifest(self.root)

    def test_manifest_cannot_omit_or_duplicate_a_future_source_case(self):
        tools = self.root / "tools"
        source = self.root / "ios/Bain Luck/BainLuckWatchUITests"
        tools.mkdir()
        source.mkdir(parents=True)
        readings = self.groups["readings"][0]
        (tools / "watch_ui_cases.json").write_text(
            json.dumps(
                {
                    "corner": self.groups["corner"],
                    "readings": [readings],
                    "navigation": [],
                    "controls": [],
                    "widgets": [],
                }
            )
        )
        (source / "WidgetTapJourneyTests.swift").write_text(
            "#if DEBUG\nfunc testActualCornerLauncherAndTap() {}\nfunc testNewCoverage() {}\n#endif"
        )
        with self.assertRaises(ValueError):
            gate.manifest(self.root)
        (tools / "watch_ui_cases.json").write_text(
            json.dumps(
                {
                    "corner": self.groups["corner"],
                    "readings": [readings],
                    "navigation": [readings],
                    "controls": [],
                    "widgets": [],
                }
            )
        )
        with self.assertRaises(ValueError):
            gate.manifest(self.root)


if __name__ == "__main__":
    unittest.main()
