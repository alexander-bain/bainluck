"""Architecture selection must use the actual pair, never the host or a guess."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.watch_simulator_architecture import select

SCRIPT = Path(__file__).resolve().parents[2] / "tools/watch_simulator_architecture.py"


def destinations(platform, udid, *architectures):
    return "Destinations compatible with the scheme:\n" + "\n".join(
        f"{{ platform:{platform}, arch:{arch}, id:{udid}, OS:27.0, name:Owned simulator }}"
        for arch in architectures
    )


class SimulatorArchitectureTests(unittest.TestCase):
    def selection(self, watch=("arm64",), phone=("arm64",)):
        return select(
            destinations("watchOS Simulator", "watch", *watch),
            "watch",
            destinations("iOS Simulator", "phone", *phone),
            "phone",
        )

    def test_actual_common_architecture_including_rosetta_phone_options(self):
        self.assertEqual(
            self.selection(phone=("arm64", "x86_64"))["architecture"], "arm64"
        )
        self.assertEqual(
            self.selection(("x86_64",), ("x86_64",))["architecture"], "x86_64"
        )

    def test_other_devices_and_unavailable_destinations_cannot_pay(self):
        log = destinations("watchOS Simulator", "other", "arm64")
        log += "\nDestinations incompatible with the scheme:\n{ platform:watchOS Simulator, arch:arm64, id:watch, error:unavailable }"
        with self.assertRaises(ValueError):
            select(
                log, "watch", destinations("iOS Simulator", "phone", "arm64"), "phone"
            )

    def test_wrong_platform_and_unsupported_architecture_refused(self):
        for platform, architecture in [
            ("watchOS", "arm64"),
            ("watchOS Simulator", ""),
            ("watchOS Simulator", "unknown"),
        ]:
            with self.subTest(
                platform=platform, architecture=architecture
            ), self.assertRaises(ValueError):
                select(
                    destinations(platform, "watch", architecture),
                    "watch",
                    destinations("iOS Simulator", "phone", "arm64"),
                    "phone",
                )

    def test_incompatible_or_ambiguous_pair_refused(self):
        for watch, phone in [
            (("arm64",), ("x86_64",)),
            (("arm64", "x86_64"), ("arm64", "x86_64")),
        ]:
            with self.subTest(watch=watch, phone=phone), self.assertRaises(ValueError):
                self.selection(watch, phone)

    def test_older_header_and_reported_error(self):
        watch = destinations("watchOS Simulator", "watch", "arm64").replace(
            "Destinations compatible with", "Available destinations for"
        )
        phone = destinations("iOS Simulator", "phone", "arm64")
        self.assertEqual(
            select(watch, "watch", phone, "phone")["architecture"], "arm64"
        )
        with self.assertRaises(ValueError):
            select(
                watch.replace("name:Owned simulator", "error:unavailable"),
                "watch",
                phone,
                "phone",
            )

    def test_missing_or_reused_identity_refused(self):
        for watch, phone in [("", "phone"), ("watch", "watch")]:
            with self.assertRaises(ValueError):
                select("", watch, "", phone)


class RuntimePairArchitectureTests(unittest.TestCase):
    def fixture(self):
        info = {"runtimes": [], "devices": {}}
        for platform, family, udid in [
            ("watchOS", "Apple Watch", "watch"),
            ("iOS", "iPhone", "phone"),
        ]:
            runtime = "runtime-" + platform
            kind = "type-" + platform
            info["runtimes"].append(
                {
                    "identifier": runtime,
                    "platform": platform,
                    "isAvailable": True,
                    "version": "27.0",
                    "supportedArchitectures": ["arm64"],
                    "supportedDeviceTypes": [
                        {"identifier": kind, "productFamily": family}
                    ],
                }
            )
            info["devices"][runtime] = [
                {
                    "udid": udid,
                    "deviceTypeIdentifier": kind,
                    "isAvailable": True,
                    "state": "Booted",
                }
            ]
        pairs = {
            "pairs": {
                "pair": {
                    "watch": {"udid": "watch"},
                    "phone": {"udid": "phone"},
                    "state": "(active, connected)",
                }
            }
        }
        products = {
            "architecture": "arm64",
            "toolchain": {"watch_sdk": "27.0", "phone_sdk": "27.0"},
        }
        return info, pairs, products

    def verify(self, info, pairs, products):
        from tools.watch_simulator_architecture import select_runtime_pair

        return select_runtime_pair(info, pairs, "watch", "phone", products)

    def test_exact_available_booted_pair_supports_unique_product_architecture(self):
        self.assertEqual(self.verify(*self.fixture())["architecture"], "arm64")

    def test_missing_wrong_platform_runtime_type_or_ambiguous_arch_refused(self):
        for field, value in [
            ("isAvailable", False),
            ("platform", "iOS"),
            ("version", "26.0"),
            ("supportedArchitectures", []),
            ("supportedArchitectures", ["mips"]),
            ("supportedDeviceTypes", []),
        ]:
            info, pairs, products = self.fixture()
            info["runtimes"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify(info, pairs, products)
        info, pairs, products = self.fixture()
        for runtime in info["runtimes"]:
            runtime["supportedArchitectures"] = ["arm64", "x86_64"]
        with self.assertRaises(ValueError):
            self.verify(info, pairs, products)

    def test_product_architecture_wrong_id_unpaired_or_unbooted_refused(self):
        mutations = [
            lambda i, p, b: b.update(architecture="x86_64"),
            lambda i, p, b: i["devices"]["runtime-watchOS"][0].update(udid="other"),
            lambda i, p, b: i["devices"]["runtime-watchOS"][0].update(state="Shutdown"),
            lambda i, p, b: p["pairs"]["pair"].update(state="inactive"),
        ]
        for mutate in mutations:
            info, pairs, products = self.fixture()
            mutate(info, pairs, products)
            with self.assertRaises(ValueError):
                self.verify(info, pairs, products)

    def test_copied_checker_requires_identical_actual_runtime_build(self):
        info, pairs, products = self.fixture()
        info["runtimes"][0]["buildversion"] = "24R362"
        products["runtime_support"] = [
            {"runtime": "runtime-watchOS", "runtime_build": "different"}
        ]
        with self.assertRaisesRegex(ValueError, "runtime build"):
            self.verify(info, pairs, products)
        products["runtime_support"][0]["runtime_build"] = "24R362"
        self.assertEqual(self.verify(info, pairs, products)["architecture"], "arm64")


def _devices(info, platform):
    return info["devices"]["runtime-" + platform]


class PreparedPairTests(unittest.TestCase):
    """#11201: the producer gates on CoreSimulator's exact pair before products exist."""

    # Each refusal is a CoreSimulator state the producer must never build from.
    REFUSALS = {
        "watch absent from simctl": lambda i, p: _devices(i, "watchOS").clear(),
        "phone absent from simctl": lambda i, p: _devices(i, "iOS").clear(),
        "pair inactive": lambda i, p: p["pairs"]["pair"].update(state="(inactive)"),
        "pair bound to another phone": lambda i, p: p["pairs"]["pair"].update(
            phone={"udid": "other"}
        ),
        "watch unbooted": lambda i, p: _devices(i, "watchOS")[0].update(
            state="Shutdown"
        ),
        "phone unbooted": lambda i, p: _devices(i, "iOS")[0].update(state="Shutdown"),
        "watch unavailable": lambda i, p: _devices(i, "watchOS")[0].update(
            isAvailable=False
        ),
        "phone unavailable": lambda i, p: _devices(i, "iOS")[0].update(
            isAvailable=False
        ),
        "watch runtime is not the SDK": lambda i, p: i["runtimes"][0].update(
            version="26.0"
        ),
        "phone runtime is not the SDK": lambda i, p: i["runtimes"][1].update(
            version="26.0"
        ),
        "unsupported device type": lambda i, p: i["runtimes"][0].update(
            supportedDeviceTypes=[
                {"identifier": "type-watchOS", "productFamily": "iPhone"}
            ]
        ),
        # A watch-only or union reading would pay this pair (M7a).
        "watch arm64, phone x86_64": lambda i, p: i["runtimes"][1].update(
            supportedArchitectures=["x86_64"]
        ),
        # Shared set without the size test would pay this pair (M7b).
        "both arm64 and x86_64": lambda i, p: [
            runtime.update(supportedArchitectures=["arm64", "x86_64"])
            for runtime in i["runtimes"]
        ],
    }

    def fixture(self):
        info, pairs, _ = RuntimePairArchitectureTests.fixture(self)
        return info, pairs

    def prepared(self, info, pairs, watch_sdk="27.0", phone_sdk="27.0"):
        from tools.watch_simulator_architecture import select_prepared_pair

        return select_prepared_pair(info, pairs, "watch", "phone", watch_sdk, phone_sdk)

    def cli(self, *extra, info=None, pairs=None, watch_sdk="27.0", phone_sdk="27.0"):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        default_info, default_pairs = self.fixture()
        (root / "simulators.json").write_text(json.dumps(info or default_info))
        (root / "pairs.json").write_text(json.dumps(pairs or default_pairs))
        output = root / "simulator-architecture.json"
        command = [
            sys.executable,
            str(SCRIPT),
            "--prepared-pair",
            "--watch-id",
            "watch",
            "--phone-id",
            "phone",
            "--simulators",
            str(root / "simulators.json"),
            "--pairs",
            str(root / "pairs.json"),
            "--output",
            str(output),
        ]
        if watch_sdk is not None:
            command += ["--watch-sdk", watch_sdk]
        if phone_sdk is not None:
            command += ["--phone-sdk", phone_sdk]
        command += [
            str(root / "simulators.json") if arg == "<file>" else arg for arg in extra
        ]
        return subprocess.run(command, capture_output=True, text=True), output

    def assert_cli_unpaid(self, run):
        process, receipt_path = run
        self.assertNotEqual(process.returncode, 0)
        self.assertNotIn("Traceback", process.stderr)
        self.assertNotIn("AttributeError", process.stderr)
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["verdict"], "UNPAID")
        self.assertTrue(receipt["reason"])
        self.assertEqual(process.stdout, "")

    def test_exact_active_booted_pair_passes_its_one_shared_architecture(self):
        result = self.prepared(*self.fixture())
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["architecture"], "arm64")
        self.assertEqual((result["watch_id"], result["phone_id"]), ("watch", "phone"))
        self.assertIn("before products exist", result["scope"])
        process, output = self.cli()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout, "arm64\n")
        self.assertEqual(json.loads(output.read_text())["verdict"], "PASS")

    def test_every_unproven_coresimulator_pair_refuses(self):
        for name, mutate in self.REFUSALS.items():
            info, pairs = self.fixture()
            mutate(info, pairs)
            with self.subTest(name), self.assertRaises(ValueError):
                self.prepared(info, pairs)

    def test_every_refusal_writes_the_unpaid_receipt(self):
        for name, mutate in self.REFUSALS.items():
            info, pairs = self.fixture()
            mutate(info, pairs)
            with self.subTest(name):
                self.assert_cli_unpaid(self.cli(info=info, pairs=pairs))

    def test_phone_runtime_is_checked_against_the_phone_sdk(self):
        info, pairs = self.fixture()
        with self.assertRaises(ValueError):
            self.prepared(info, pairs, watch_sdk="27.0", phone_sdk="27.1")
        self.assert_cli_unpaid(self.cli(watch_sdk="27.0", phone_sdk="27.1"))

    def test_cli_dispatch_fails_closed_with_a_receipt(self):
        for name, run in {
            "both modes": lambda: self.cli("--runtime-pair"),
            "phone SDK missing": lambda: self.cli(phone_sdk=None),
            "phone SDK empty": lambda: self.cli(phone_sdk=""),
            "watch SDK missing": lambda: self.cli(watch_sdk=None),
            "with --products": lambda: self.cli("--products", "<file>"),
            "with --watch-destinations": lambda: self.cli(
                "--watch-destinations", "<file>"
            ),
            "with --phone-destinations": lambda: self.cli(
                "--phone-destinations", "<file>"
            ),
        }.items():
            with self.subTest(name):
                self.assert_cli_unpaid(run())


if __name__ == "__main__":
    unittest.main()
