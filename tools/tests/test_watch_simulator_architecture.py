"""Architecture selection must use the actual pair, never the host or a guess."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools.watch_simulator_architecture import select, select_build_runtime_pair


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


WATCH_RUNTIME = "com.apple.CoreSimulator.SimRuntime.watchOS-27-0"
PHONE_RUNTIME = "com.apple.CoreSimulator.SimRuntime.iOS-27-0"
WATCH_TYPE = "com.apple.CoreSimulator.SimDeviceType.Apple-Watch-Series-12-46mm"
PHONE_TYPE = "com.apple.CoreSimulator.SimDeviceType.iPhone-18-Pro"
SCRIPT = Path(__file__).resolve().parents[1] / "watch_simulator_architecture.py"


def runtime(identifier, platform, build, kinds, architectures=("arm64",)):
    return {
        "identifier": identifier,
        "platform": platform,
        "isAvailable": True,
        "version": "27.0",
        "buildversion": build,
        "supportedArchitectures": list(architectures),
        "supportedDeviceTypes": [
            {"identifier": kind, "productFamily": family} for kind, family in kinds
        ],
    }


class BuildRuntimePairArchitectureTests(unittest.TestCase):
    """The producer selects from exact runtimes alone: no device, pair or host."""

    def fixture(self):
        # Shape of the retained f691 hosted simctl list --json (Xcode 27.0).
        return {
            "runtimes": [
                runtime(
                    PHONE_RUNTIME,
                    "iOS",
                    "24A434",
                    [
                        (PHONE_TYPE, "iPhone"),
                        ("com.apple.CoreSimulator.SimDeviceType.iPad-Pro", "iPad"),
                    ],
                ),
                runtime(
                    "com.apple.CoreSimulator.SimRuntime.tvOS-27-0",
                    "tvOS",
                    "24J360",
                    [("com.apple.CoreSimulator.SimDeviceType.Apple-TV", "Apple TV")],
                ),
                runtime(
                    WATCH_RUNTIME, "watchOS", "24R362", [(WATCH_TYPE, "Apple Watch")]
                ),
            ],
            # Producer must not depend on these at all.
            "devices": {},
            "pairs": {},
        }

    def runtime(self, info, identifier):
        return next(r for r in info["runtimes"] if r["identifier"] == identifier)

    def choose(self, info, watch=WATCH_RUNTIME, phone=PHONE_RUNTIME, **kwargs):
        sdks = {"watch_sdk": "27.0", "phone_sdk": "27.0"}
        sdks.update(kwargs)
        return select_build_runtime_pair(info, watch, phone, **sdks)

    def test_exact_runtimes_and_sdks_select_the_one_shared_architecture(self):
        result = self.choose(
            self.fixture(), watch_device_type=WATCH_TYPE, phone_device_type=PHONE_TYPE
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["architecture"], "arm64")
        self.assertEqual(
            [(r["runtime"], r["runtime_build"]) for r in result["runtimes"]],
            [(WATCH_RUNTIME, "24R362"), (PHONE_RUNTIME, "24A434")],
        )
        self.assertIn("no device, pair or execution", result["scope"])
        # Device types are optional; the family must still be advertised.
        self.assertEqual(self.choose(self.fixture())["architecture"], "arm64")
        # "27" and "27.0.0" name the same exact SDK as runtime "27.0".
        self.assertEqual(
            self.choose(self.fixture(), watch_sdk="27", phone_sdk="27.0.0")[
                "architecture"
            ],
            "arm64",
        )

    def test_shared_architecture_follows_runtime_metadata_not_the_host(self):
        info = self.fixture()
        self.runtime(info, PHONE_RUNTIME)["supportedArchitectures"] = [
            "arm64",
            "x86_64",
        ]
        self.assertEqual(self.choose(info)["architecture"], "arm64")
        info = self.fixture()
        for identifier in (WATCH_RUNTIME, PHONE_RUNTIME):
            self.runtime(info, identifier)["supportedArchitectures"] = ["x86_64"]
        host = mock.Mock(side_effect=AssertionError("host architecture consulted"))
        with mock.patch("os.uname", host), mock.patch("platform.machine", host):
            self.assertEqual(self.choose(info)["architecture"], "x86_64")

    def test_no_device_or_pair_record_is_read(self):
        info = self.fixture()
        del info["devices"], info["pairs"]
        self.assertEqual(self.choose(info)["architecture"], "arm64")
        info = self.fixture()
        # Unbooted, unavailable or unpaired devices cannot affect the producer.
        info["devices"] = {
            WATCH_RUNTIME: [{"udid": "w", "isAvailable": False, "state": "Shutdown"}]
        }
        self.assertEqual(self.choose(info)["architecture"], "arm64")

    def test_missing_reused_or_non_string_runtime_ids_refused(self):
        for watch, phone in [
            ("", PHONE_RUNTIME),
            (WATCH_RUNTIME, ""),
            (None, PHONE_RUNTIME),
            (WATCH_RUNTIME, WATCH_RUNTIME),
            ([WATCH_RUNTIME], PHONE_RUNTIME),
            ("com.apple.CoreSimulator.SimRuntime.watchOS-26-0", PHONE_RUNTIME),
        ]:
            with self.subTest(watch=watch, phone=phone), self.assertRaisesRegex(
                ValueError, "distinct exact runtime|missing or duplicated"
            ):
                self.choose(self.fixture(), watch, phone)

    def test_swapped_or_wrong_platform_runtime_refused(self):
        with self.assertRaises(ValueError):
            self.choose(self.fixture(), PHONE_RUNTIME, WATCH_RUNTIME)
        with self.assertRaises(ValueError):
            self.choose(
                self.fixture(), phone="com.apple.CoreSimulator.SimRuntime.tvOS-27-0"
            )

    def test_malformed_runtime_list_refused(self):
        for info in [
            None,
            [],
            {},
            {"runtimes": None},
            {"runtimes": {}},
            {"runtimes": self.fixture()["runtimes"] + ["junk"]},
        ]:
            with self.subTest(info=info), self.assertRaises(ValueError):
                self.choose(info)

    def test_duplicate_exact_runtime_record_refused(self):
        info = self.fixture()
        info["runtimes"].append(copy.deepcopy(self.runtime(info, WATCH_RUNTIME)))
        with self.assertRaisesRegex(ValueError, "duplicated"):
            self.choose(info)

    def test_unavailable_or_sdk_mismatched_runtime_refused(self):
        for identifier in (WATCH_RUNTIME, PHONE_RUNTIME):
            for field, value in [
                ("isAvailable", False),
                ("isAvailable", "true"),
                ("isAvailable", 1),
                ("isAvailable", None),
                ("version", "26.0"),
                ("version", "27.1"),
                ("version", "27.0.1"),
                ("version", "27.x"),
                ("version", "27.0.0.0"),
                ("version", ""),
                ("version", None),
                ("version", 27.0),
                ("platform", "watchOS Simulator"),
            ]:
                info = self.fixture()
                self.runtime(info, identifier)[field] = value
                with self.subTest(
                    runtime=identifier, field=field, value=value
                ), self.assertRaises(ValueError):
                    self.choose(info)
        for sdks in [
            {"watch_sdk": "26.0"},
            {"phone_sdk": "27.1"},
            {"watch_sdk": ""},
            {"phone_sdk": None},
            {"watch_sdk": "watchsimulator27.0"},
        ]:
            with self.subTest(sdks=sdks), self.assertRaises(ValueError):
                self.choose(self.fixture(), **sdks)
        # A malformed version cannot pass by being malformed the same way twice.
        info = self.fixture()
        self.runtime(info, WATCH_RUNTIME)["version"] = "27.0.0.0"
        with self.assertRaisesRegex(ValueError, "malformed"):
            self.choose(info, watch_sdk="27.0.0.0")

    def test_missing_wrong_or_ambiguous_device_family_type_refused(self):
        cases = [
            (WATCH_RUNTIME, None, {}),
            (WATCH_RUNTIME, [], {}),
            (WATCH_RUNTIME, "Apple Watch", {}),
            (WATCH_RUNTIME, [None], {}),
            (
                WATCH_RUNTIME,
                [{"identifier": WATCH_TYPE, "productFamily": "iPhone"}],
                {},
            ),
            (PHONE_RUNTIME, [{"identifier": "ipad", "productFamily": "iPad"}], {}),
            (
                WATCH_RUNTIME,
                [{"identifier": WATCH_TYPE, "productFamily": "Apple Watch"}] * 2,
                {"watch_device_type": WATCH_TYPE},
            ),
            (None, None, {"watch_device_type": PHONE_TYPE}),
            (None, None, {"phone_device_type": WATCH_TYPE}),
            (
                None,
                None,
                {"phone_device_type": "com.apple.CoreSimulator.SimDeviceType.iPad-Pro"},
            ),
            (None, None, {"watch_device_type": "missing"}),
        ]
        for identifier, kinds, kwargs in cases:
            info = self.fixture()
            if identifier:
                self.runtime(info, identifier)["supportedDeviceTypes"] = kinds
            with self.subTest(
                runtime=identifier, kinds=kinds, kwargs=kwargs
            ), self.assertRaises(ValueError):
                self.choose(info, **kwargs)

    def test_missing_malformed_or_unsupported_architecture_refused(self):
        for identifier in (WATCH_RUNTIME, PHONE_RUNTIME):
            for value in [
                None,
                [],
                "arm64",
                ["arm64", "arm64"],
                [None],
                ["mips"],
                ["arm64", "mips"],
                ["arm64e"],
            ]:
                info = self.fixture()
                self.runtime(info, identifier)["supportedArchitectures"] = value
                with self.subTest(
                    runtime=identifier, value=value
                ), self.assertRaisesRegex(ValueError, "Runtime architecture"):
                    self.choose(info)
            info = self.fixture()
            del self.runtime(info, identifier)["supportedArchitectures"]
            with self.subTest(
                runtime=identifier, value="absent"
            ), self.assertRaisesRegex(ValueError, "Runtime architecture"):
                self.choose(info)

    def test_incompatible_or_ambiguous_shared_architecture_refused(self):
        for watch, phone in [
            (["arm64"], ["x86_64"]),
            (["x86_64"], ["arm64"]),
            (["arm64", "x86_64"], ["arm64", "x86_64"]),
        ]:
            info = self.fixture()
            self.runtime(info, WATCH_RUNTIME)["supportedArchitectures"] = watch
            self.runtime(info, PHONE_RUNTIME)["supportedArchitectures"] = phone
            with self.subTest(watch=watch, phone=phone), self.assertRaisesRegex(
                ValueError, "one unambiguous"
            ):
                self.choose(info)


class BuildRuntimePairCommandTests(unittest.TestCase):
    def run_script(self, info, *extra):
        with tempfile.TemporaryDirectory() as directory:
            simulators = Path(directory, "simulators.json")
            output = Path(directory, "selection.json")
            simulators.write_text(json.dumps(info))
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(output)]
                + ["--simulators", str(simulators), *extra],
                capture_output=True,
                text=True,
            )
            written = json.loads(output.read_text()) if output.exists() else None
        return completed, written

    BUILD = (
        "--build-runtime-pair",
        "--watch-runtime",
        WATCH_RUNTIME,
        "--phone-runtime",
        PHONE_RUNTIME,
        "--watch-sdk",
        "27.0",
        "--phone-sdk",
        "27.0",
    )

    def test_build_mode_prints_and_records_the_architecture(self):
        info = BuildRuntimePairArchitectureTests().fixture()
        completed, written = self.run_script(
            info,
            *self.BUILD,
            "--watch-device-type",
            WATCH_TYPE,
            "--phone-device-type",
            PHONE_TYPE,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "arm64\n")
        self.assertEqual(written["verdict"], "PASS")
        self.assertEqual(written["watch_runtime"], WATCH_RUNTIME)

    def test_build_mode_refusal_records_unpaid_and_fails(self):
        info = BuildRuntimePairArchitectureTests().fixture()
        info["runtimes"] = [r for r in info["runtimes"] if r["platform"] != "watchOS"]
        completed, written = self.run_script(info, *self.BUILD)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(written["verdict"], "UNPAID")

    def test_build_mode_refuses_device_ids_and_incomplete_runtime_arguments(self):
        info = BuildRuntimePairArchitectureTests().fixture()
        for extra, message in [
            (self.BUILD + ("--watch-id", "watch"), "never device ids"),
            (self.BUILD + ("--phone-id", "phone"), "never device ids"),
            (self.BUILD + ("--runtime-pair",), "never device ids"),
            (self.BUILD[:-2], "requires --simulators"),
        ]:
            with self.subTest(extra=extra):
                completed, written = self.run_script(info, *extra)
                self.assertEqual(completed.returncode, 2)
                self.assertIn(message, completed.stderr)
                self.assertIsNone(written)

    def test_existing_destination_and_runtime_pair_modes_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, platform, udid in [
                ("watch.log", "watchOS Simulator", "watch"),
                ("phone.log", "iOS Simulator", "phone"),
            ]:
                root.joinpath(name).write_text(destinations(platform, udid, "arm64"))
            info, pairs, products = RuntimePairArchitectureTests().fixture()
            for name, value in [
                ("simulators.json", info),
                ("pairs.json", pairs),
                ("products.json", products),
            ]:
                root.joinpath(name).write_text(json.dumps(value))
            ids = ["--watch-id", "watch", "--phone-id", "phone"]
            for mode in [
                [
                    "--watch-destinations",
                    str(root / "watch.log"),
                    "--phone-destinations",
                    str(root / "phone.log"),
                ],
                [
                    "--runtime-pair",
                    "--simulators",
                    str(root / "simulators.json"),
                    "--pairs",
                    str(root / "pairs.json"),
                    "--products",
                    str(root / "products.json"),
                ],
            ]:
                with self.subTest(mode=mode[0]):
                    output = root / "selection.json"
                    completed = subprocess.run(
                        [sys.executable, str(SCRIPT), "--output", str(output)]
                        + mode
                        + ids,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stdout, "arm64\n")
                    written = json.loads(output.read_text())
                    self.assertEqual(
                        (written["watch_id"], written["phone_id"]), ("watch", "phone")
                    )

    def test_existing_modes_still_require_both_device_ids(self):
        for extra in [(), ("--runtime-pair",), ("--watch-id", "watch")]:
            with self.subTest(extra=extra):
                completed, written = self.run_script({}, *extra)
                self.assertEqual(completed.returncode, 2)
                self.assertIn("--watch-id, --phone-id", completed.stderr)
                self.assertIsNone(written)


if __name__ == "__main__":
    unittest.main()
