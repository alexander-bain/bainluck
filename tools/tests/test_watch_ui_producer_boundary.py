"""A build-only producer must not require a CoreSimulator device lifecycle."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ProducerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tools").mkdir()
        shutil.copyfile(
            ROOT / "tools/watch-ui-products.sh",
            self.root / "tools/watch-ui-products.sh",
        )
        shutil.copyfile(
            ROOT / "tools/watch_simulator_architecture.py",
            self.root / "tools/watch_simulator_architecture.py",
        )
        (self.root / "tools/__init__.py").write_text("")
        self.pins = (
            self.root
            / "ios/Bain Luck/Bain Luck.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"
        )
        self.pins.parent.mkdir(parents=True)
        self.pins.write_text('{"pins": []}\n')
        subprocess.run(
            ["git", "-C", str(self.root), "init", "-q"], check=True, capture_output=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "user.name=Fixture",
                "commit",
                "--allow-empty",
                "-qm",
                "fixture identity",
            ],
            check=True,
            capture_output=True,
        )
        self.info = {"runtimes": [], "devices": {}}
        for platform, family, identifier in (
            ("watchOS", "Apple Watch", "watch-runtime"),
            ("iOS", "iPhone", "phone-runtime"),
        ):
            self.info["runtimes"].append(
                {
                    "identifier": identifier,
                    "platform": platform,
                    "version": "27.0",
                    "isAvailable": True,
                    "supportedArchitectures": ["arm64"],
                    "supportedDeviceTypes": [
                        {"identifier": "type-" + platform, "productFamily": family}
                    ],
                }
            )
            self.info["devices"][identifier] = [
                {
                    "udid": "stock-" + platform,
                    "isAvailable": True,
                    "deviceTypeIdentifier": (
                        "Apple-Watch" if platform == "watchOS" else "iPhone"
                    ),
                }
            ]
        self.info_path = self.root / "metadata.json"
        self.record = self.root / "commands.jsonl"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        stub = """#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
with open(os.environ["RECORD"],"a") as stream:stream.write(json.dumps({"tool":name,"args":args})+"\\n")
if name=="xcrun":
 if args==["swiftc","--version"]: print("fixture compiler");sys.exit(0)
 if args[:1]==["--sdk"] and args[2:]==["--show-sdk-version"]:
  print(os.environ.get("PHONE_SDK_VERSION" if args[1]=="iphonesimulator" else "WATCH_SDK_VERSION","27.0"));sys.exit(0)
 if args==["simctl","list","--json"]: print(Path(os.environ["METADATA"]).read_text());sys.exit(0)
 raise SystemExit("Device mutation/discovery forbidden in producer fixture: "+str(args))
if args==["-version"] or args==["-showsdks"]: print("fixture SDKs");sys.exit(0)
if "-showdestinations" in args:
 print('Destinations compatible with the scheme:\\n{ platform:iOS Simulator, id:placeholder, name:Any iOS Simulator Device }');sys.exit(0)
if args[0]=="-resolvePackageDependencies":
 if os.environ.get("MUTATE_PINS"):Path(os.environ["PINS"]).write_text("changed")
 sys.exit(0)
if args[0] not in ["build-for-testing","build"]:raise SystemExit("Unexpected Xcode action")
if os.environ.get("FAIL_BUILD")==args[0]:sys.exit(65)
print("fixture build complete")
"""
        # Use the current interpreter explicitly; never invoke any real Apple command.
        stub = stub.replace("#!/usr/bin/env python3", "#!" + sys.executable)
        for name in ("xcodebuild", "xcrun"):
            path = self.bin / name
            path.write_text(stub)
            path.chmod(0o755)
        (self.root / "tools/watch_ui_stage.py").write_text(
            "# Fixture phase recording only\n"
        )
        (self.root / "tools/watch_resolve_packages.py").write_text(
            'import subprocess,sys\nsubprocess.run(sys.argv[sys.argv.index("--")+1:],check=True)\n'
        )
        (self.root / "tools/watch_ui_products.py").write_text("""import json,os,sys
from pathlib import Path
def source_fingerprint(root):return "fixture-source"
if __name__=="__main__":
 args=sys.argv[1:]
 with open(os.environ["RECORD"],"a") as stream:stream.write(json.dumps({"tool":"package","args":args})+"\\n")
 if os.environ.get("FAIL_PACKAGE"):raise SystemExit(1)
 output=Path(args[args.index("--output")+1]);output.mkdir(parents=True)
 (output/"manifest.json").write_text(json.dumps({"scope":"fixture only","architecture":args[args.index("--architecture")+1]}))
""")

    def run_producer(self, **extra):
        self.info_path.write_text(json.dumps(self.info))
        env = {
            **os.environ,
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "GITHUB_ACTIONS": "true",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "RECORD": str(self.record),
            "METADATA": str(self.info_path),
            "PINS": str(self.pins),
            **extra,
        }
        result = subprocess.run(
            ["bash", "tools/watch-ui-products.sh"],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        calls = (
            [json.loads(line) for line in self.record.read_text().splitlines()]
            if self.record.exists()
            else []
        )
        return result, calls

    def test_build_only_succeeds_without_devices_or_concrete_destination_discovery(
        self,
    ):
        self.info["devices"] = {}
        result, calls = self.run_producer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(
            any(
                call["tool"] == "xcodebuild" and "-showdestinations" in call["args"]
                for call in calls
            )
        )
        sim_calls = [
            call["args"]
            for call in calls
            if call["tool"] == "xcrun" and call["args"][:1] == ["simctl"]
        ]
        self.assertEqual(sim_calls, [["simctl", "list", "--json"]])
        builds = [
            call["args"]
            for call in calls
            if call["tool"] == "xcodebuild"
            and call["args"][:1] in (["build-for-testing"], ["build"])
        ]
        self.assertEqual([args[0] for args in builds], ["build-for-testing", "build"])
        self.assertEqual(
            [args[args.index("-destination") + 1] for args in builds],
            ["generic/platform=watchOS Simulator", "generic/platform=iOS Simulator"],
        )
        for args in builds:
            self.assertEqual(args.count("ARCHS=arm64"), 1)
            self.assertIn("CODE_SIGNING_ALLOWED=YES", args)
            self.assertIn("CODE_SIGNING_REQUIRED=YES", args)
            self.assertIn("CODE_SIGN_IDENTITY=-", args)
            self.assertIn("-disableAutomaticPackageResolution", args)
            self.assertIn("-clonedSourcePackagesDirPath", args)
        self.assertEqual(len([call for call in calls if call["tool"] == "package"]), 1)
        package = next(call["args"] for call in calls if call["tool"] == "package")
        self.assertEqual(package[package.index("--watch-runtime") + 1], "watch-runtime")
        self.assertNotIn("test-without-building", json.dumps(calls))

    def test_distinct_watch_and_phone_sdks_select_their_own_exact_runtimes(self):
        self.info["runtimes"][1]["version"] = "27.1"
        result, calls = self.run_producer(PHONE_SDK_VERSION="27.1")
        self.assertEqual(result.returncode, 0, result.stderr)
        selection = json.loads(
            (
                self.root / "build/watch-ui-products/simulator-architecture.json"
            ).read_text()
        )
        self.assertEqual([r["sdk"] for r in selection["runtimes"]], ["27.0", "27.1"])
        self.assertEqual(selection["phone_runtime"], "phone-runtime")
        self.assertEqual(sum(call["tool"] == "package" for call in calls), 1)

    def test_duplicate_same_sdk_runtimes_stop_before_build_or_package(self):
        duplicate = dict(self.info["runtimes"][0], identifier="second-watch-runtime")
        self.info["runtimes"].append(duplicate)
        result, calls = self.run_producer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            any(
                call["tool"] == "package"
                or call["args"][:1] in (["build"], ["build-for-testing"])
                for call in calls
            )
        )
        self.assertEqual(
            json.loads(
                (self.root / "build/watch-ui-products/receipt.json").read_text()
            )["verdict"],
            "UNPAID",
        )

    def test_incompatible_runtime_cannot_start_build_or_package(self):
        self.info["runtimes"][1]["version"] = "26.0"
        result, calls = self.run_producer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            any(
                call["tool"] == "package"
                or call["args"][:1] in (["build"], ["build-for-testing"])
                for call in calls
            )
        )
        self.assertEqual(
            json.loads(
                (self.root / "build/watch-ui-products/receipt.json").read_text()
            )["verdict"],
            "UNPAID",
        )

    def test_ambiguous_shared_architecture_cannot_build(self):
        for runtime in self.info["runtimes"]:
            runtime["supportedArchitectures"] = ["arm64", "x86_64"]
        result, calls = self.run_producer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            any(
                call["tool"] == "package"
                or call["args"][:1] in (["build"], ["build-for-testing"])
                for call in calls
            )
        )

    def test_changed_package_pins_stop_before_build(self):
        result, calls = self.run_producer(MUTATE_PINS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            any(
                call["tool"] == "package"
                or call["args"][:1] in (["build"], ["build-for-testing"])
                for call in calls
            )
        )

    def test_failed_watch_build_stops_without_companion_retry_or_package(self):
        result, calls = self.run_producer(FAIL_BUILD="build-for-testing")
        self.assertEqual(result.returncode, 65)
        self.assertFalse(
            any(
                call["tool"] == "package" or call["args"][:1] == ["build"]
                for call in calls
            )
        )
        self.assertEqual(
            sum(call["args"][:1] == ["build-for-testing"] for call in calls), 1
        )

    def test_failed_companion_build_stops_without_package(self):
        result, calls = self.run_producer(FAIL_BUILD="build")
        self.assertEqual(result.returncode, 65)
        self.assertFalse(any(call["tool"] == "package" for call in calls))
        self.assertEqual(sum(call["args"][:1] == ["build"] for call in calls), 1)

    def test_failed_product_attestation_is_not_hidden(self):
        result, calls = self.run_producer(FAIL_PACKAGE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sum(call["tool"] == "package" for call in calls), 1)
        self.assertEqual(
            json.loads(
                (self.root / "build/watch-ui-products/receipt.json").read_text()
            )["verdict"],
            "UNPAID",
        )


if __name__ == "__main__":
    unittest.main()
