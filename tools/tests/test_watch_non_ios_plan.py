import importlib.util
from pathlib import Path
import unittest
import plistlib
import tempfile

spec = importlib.util.spec_from_file_location("plan", Path(__file__).resolve().parents[1] / "watch_non_ios_plan.py")
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)

GOOD = """Target dependency graph (2 targets)
    Target 'Bain Luck' in project 'Bain Luck'
    Target 'FirebaseCore' in project 'Firebase'
** BUILD SUCCEEDED **
"""

class PlanTests(unittest.TestCase):
    def test_accepts_both_platforms_with_explicit_limited_scope(self):
        for platform in ("macOS", "visionOS"):
            result = plan.inspect(GOOD, platform, 0)
            self.assertEqual(result["target_count"], 2)
            self.assertIn("runtime and distribution unverified", result["scope"])

    def test_rejects_unpaid_plans(self):
        for log, platform, status in [
            (GOOD, "iOS", 0), (GOOD, "macOS", 74),
            ("", "macOS", 0), (GOOD.replace("BUILD SUCCEEDED", "BUILD FAILED"), "macOS", 0),
            (GOOD.replace("2 targets", "3 targets"), "macOS", 0),
            (GOOD + GOOD, "macOS", 0),
            (GOOD + "** BUILD FAILED **", "macOS", 0),
            (GOOD.replace("Target 'Bain Luck'", "Target 'Other'"), "macOS", 0),
        ]:
            with self.subTest(log=log, platform=platform, status=status):
                with self.assertRaises(ValueError): plan.inspect(log, platform, status)

    def test_rejects_each_watch_target(self):
        for target in ("BainLuckWatch", "BainLuckWatch Watch App", "BainLuckComplication"):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    plan.inspect(GOOD.replace("FirebaseCore", target), "macOS", 0)

    def test_rejects_copy_even_when_graph_omits_watch(self):
        for command in ("builtin-copy /build/BainLuckWatch.app /App/Watch/", "Copy /tmp/app.watchkitapp", "CpResource /App/Watch/content", "ditto /tmp/BainLuckComplication.appex /App"):
            with self.subTest(command=command):
                with self.assertRaises(ValueError): plan.inspect(GOOD + command, "visionOS", 0)

    def test_rejects_watch_compile_or_sign_command(self):
        for command in ("SwiftCompile BainLuckWatch", "Ld BainLuckComplication", "CodeSign /tmp/BainLuckWatch.app"):
            with self.assertRaises(ValueError): plan.inspect(GOOD + command, "macOS", 0)


class ProductTests(unittest.TestCase):
    def fixture(self, root, platform):
        products = Path(root) / ("Release" if platform == "macOS" else "Release-xros")
        app = products / "Bain Luck.app"
        info_path = app / ("Contents/Info.plist" if platform == "macOS" else "Info.plist")
        binary = app / ("Contents/MacOS/Bain Luck" if platform == "macOS" else "Bain Luck")
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"synthetic built executable")
        info = {"CFBundleIdentifier": "com.bainluck.Bain-Luck", "CFBundleExecutable": "Bain Luck",
                "CFBundleSupportedPlatforms": ["MacOSX" if platform == "macOS" else "XROS"]}
        info_path.write_bytes(plistlib.dumps(info))
        return products, app, info_path, binary, info

    def test_correct_mac_and_vision_products(self):
        for platform in ("macOS", "visionOS"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as root:
                products, app, _, _, _ = self.fixture(root, platform)
                result = plan.inspect_product(products, platform)
                self.assertEqual(result["app"], str(app))
                self.assertEqual(result["built_platform"], "MacOSX" if platform == "macOS" else "XROS")
                self.assertEqual(result["watch_payload"], "ABSENT")

    def test_missing_and_empty_executables(self):
        for platform in ("macOS", "visionOS"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as root:
                products, _, _, binary, _ = self.fixture(root, platform)
                binary.write_bytes(b"")
                with self.assertRaises(ValueError): plan.inspect_product(products, platform)
                binary.unlink()
                with self.assertRaises(ValueError): plan.inspect_product(products, platform)

    def test_wrong_main_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            products, _, info_path, _, info = self.fixture(root, "macOS")
            info["CFBundleIdentifier"] = "com.example.wrong-app"
            info_path.write_bytes(plistlib.dumps(info))
            with self.assertRaises(ValueError): plan.inspect_product(products, "macOS")

    def test_platform_mismatch(self):
        for platform in ("macOS", "visionOS"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as root:
                products, _, info_path, _, info = self.fixture(root, platform)
                info["CFBundleSupportedPlatforms"] = ["XROS" if platform == "macOS" else "MacOSX"]
                info_path.write_bytes(plistlib.dumps(info))
                with self.assertRaises(ValueError): plan.inspect_product(products, platform)

    def test_watch_directory_is_rejected(self):
        for platform in ("macOS", "visionOS"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as root:
                products, app, _, _, _ = self.fixture(root, platform)
                (app / "Watch").mkdir()
                with self.assertRaises(ValueError): plan.inspect_product(products, platform)

    def test_disguised_watch_bundles_are_rejected(self):
        for platform in ("macOS", "visionOS"):
            for child_info in [
                {"CFBundleIdentifier": "innocent.name", "CFBundleSupportedPlatforms": ["WatchOS"]},
                {"CFBundleIdentifier": "com.bainluck.Bain-Luck.watchkitapp.Complication", "CFBundleSupportedPlatforms": ["XROS"]},
            ]:
                with self.subTest(platform=platform, child=child_info), tempfile.TemporaryDirectory() as root:
                    products, app, _, _, _ = self.fixture(root, platform)
                    child = app / "Resources/Disguised.appex"
                    child.mkdir(parents=True)
                    (child / "Info.plist").write_bytes(plistlib.dumps(child_info))
                    with self.assertRaises(ValueError): plan.inspect_product(products, platform)

    def test_missing_or_duplicate_main_product(self):
        with tempfile.TemporaryDirectory() as root:
            products = Path(root)
            with self.assertRaises(ValueError): plan.inspect_product(products, "macOS")
            self.fixture(products / "one", "macOS")
            self.fixture(products / "two", "macOS")
            with self.assertRaises(ValueError): plan.inspect_product(products, "macOS")

if __name__ == "__main__":
    unittest.main()
