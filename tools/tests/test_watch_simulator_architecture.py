"""Architecture selection must use the actual pair, never the host or a guess."""

import unittest

from tools.watch_simulator_architecture import select


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


if __name__ == "__main__":
    unittest.main()
