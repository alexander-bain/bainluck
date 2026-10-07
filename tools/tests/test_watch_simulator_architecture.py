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


if __name__ == "__main__":
    unittest.main()
