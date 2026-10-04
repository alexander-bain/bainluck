"""Synthetic packaging gates for the embedded Watch companion candidate."""
from pathlib import Path
import plistlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watch_companion_archive import inspect_archive

PHONE = "com.bainluck.Bain-Luck"
WATCH = PHONE + ".watchkitapp"
ACTIVITY = "com.bainluck.view-game"


class WatchCompanionArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / "Candidate.xcarchive"
        self.phone = self.archive / "Products/Applications/Bain Luck.app"
        self.watch = self.phone / "Watch/Watch.app"
        self.extension = self.watch / "PlugIns/Complication.appex"
        self.extension.mkdir(parents=True)
        self.write(self.archive / "Info.plist", {"ApplicationProperties": {"ApplicationPath": "Applications/Bain Luck.app"}})
        self.phone_info = {"CFBundleIdentifier": PHONE, "CFBundleExecutable": "Bain Luck",
                           "CFBundleSupportedPlatforms": ["iPhoneOS"], "CFBundleShortVersionString": "1.0",
                           "CFBundleVersion": "10", "NSUserActivityTypes": [ACTIVITY]}
        self.watch_info = dict(self.phone_info, CFBundleIdentifier=WATCH, CFBundleExecutable="Watch",
                               CFBundleSupportedPlatforms=["WatchOS"], WKCompanionAppBundleIdentifier=PHONE,
                               WKRunsIndependentlyOfCompanionApp=True)
        self.extension_info = {"CFBundleIdentifier": WATCH + ".Complication",
                               "CFBundleExecutable": "Complication",
                               "CFBundleSupportedPlatforms": ["WatchOS"],
                               "CFBundleShortVersionString": "1.0", "CFBundleVersion": "10",
                               "NSExtension": {"NSExtensionPointIdentifier": "com.apple.widgetkit-extension"}}
        self.save_infos()
        (self.extension / "Complication").write_bytes(b"synthetic executable")
        (self.phone / "Bain Luck").write_bytes(b"synthetic executable")
        (self.watch / "Watch").write_bytes(b"synthetic executable")

    def write(self, path, value):
        path.write_bytes(plistlib.dumps(value))

    def save_infos(self):
        self.write(self.phone / "Info.plist", self.phone_info)
        self.write(self.watch / "Info.plist", self.watch_info)
        self.write(self.extension / "Info.plist", self.extension_info)

    def platform(self, path):
        return "WATCHOS" if path.parent in (self.watch, self.extension) else "IOS"

    def inspect(self):
        return inspect_archive(self.archive, platform_reader=self.platform)

    def reject(self):
        with self.assertRaises(ValueError):
            self.inspect()

    def test_packaged_candidate_is_not_install_or_distribution_proof(self):
        result = self.inspect()
        self.assertEqual(result["verdict"], "PACKAGED_UNSIGNED_CANDIDATE")
        self.assertEqual(result["physical_install"], "UNVERIFIED")
        self.assertEqual(result["distribution"], "UNVERIFIED")
        self.assertEqual(len(result["applications"]), 3)
        self.assertEqual(result["applications"][2]["bundle_id"], WATCH + ".Complication")
        self.watch_info["WKWatchOnly"] = False
        self.save_infos()
        self.inspect()

    def test_missing_watch_reproduces_old_phone_only_archive(self):
        shutil.rmtree(self.watch)
        self.reject()

    def test_complication_required_and_no_extra_extension(self):
        shutil.rmtree(self.extension)
        self.reject()
        self.extension.mkdir()
        self.save_infos()
        (self.extension / "Complication").write_bytes(b"synthetic executable")
        (self.watch / "PlugIns/Extra.appex").mkdir()
        self.reject()

    def test_complication_identity_version_type_and_platform(self):
        original = dict(self.extension_info)
        for key, value in [
            ("CFBundleIdentifier", "wrong.extension"),
            ("CFBundleExecutable", "Watch"),
            ("CFBundleShortVersionString", "999"),
            ("CFBundleVersion", "999"),
            ("CFBundleSupportedPlatforms", ["WatchSimulator"]),
            ("NSExtension", {"NSExtensionPointIdentifier": "wrong.extension-point"}),
            ("NSExtension", {}),
        ]:
            with self.subTest(key=key):
                self.extension_info = dict(original, **{key: value})
                self.save_infos()
                self.reject()
        self.extension_info = original
        self.save_infos()
        for wrong in ["WATCHOSSIMULATOR", "IOS", "MACOS"]:
            with self.subTest(binary_platform=wrong):
                with self.assertRaises(ValueError):
                    inspect_archive(self.archive, platform_reader=lambda path: wrong if path.parent == self.extension else self.platform(path))

    def test_identity_relationship_and_watch_only_rejected(self):
        original = dict(self.watch_info)
        for key, value in [("CFBundleIdentifier", "wrong.watch"), ("WKCompanionAppBundleIdentifier", "wrong.phone"),
                           ("WKWatchOnly", True), ("WKRunsIndependentlyOfCompanionApp", False)]:
            with self.subTest(key=key):
                self.watch_info = dict(original)
                self.watch_info[key] = value
                self.save_infos()
                self.reject()
        self.watch_info = original
        self.phone_info["CFBundleIdentifier"] = "wrong.phone"
        self.save_infos()
        self.reject()

    def test_versions_must_match(self):
        for key in ["CFBundleShortVersionString", "CFBundleVersion"]:
            with self.subTest(key=key):
                old = self.watch_info[key]
                self.watch_info[key] = "999"
                self.save_infos()
                self.reject()
                self.watch_info[key] = old

    def test_missing_activity_on_either_platform(self):
        for info in [self.phone_info, self.watch_info]:
            old = info.pop("NSUserActivityTypes")
            self.save_infos()
            self.reject()
            info["NSUserActivityTypes"] = old

    def test_plist_and_binary_platforms(self):
        for info, wrong in [(self.phone_info, ["iPhoneSimulator"]), (self.watch_info, ["WatchSimulator"])]:
            old = info["CFBundleSupportedPlatforms"]
            info["CFBundleSupportedPlatforms"] = wrong
            self.save_infos()
            self.reject()
            info["CFBundleSupportedPlatforms"] = old
        self.save_infos()
        for wrong in ["IOSSIMULATOR", "WATCHOSSIMULATOR", "MACOS"]:
            with self.subTest(platform=wrong):
                with self.assertRaises(ValueError):
                    inspect_archive(self.archive, platform_reader=lambda _: wrong)

    def test_missing_or_empty_executable(self):
        for binary in [self.phone / "Bain Luck", self.watch / "Watch", self.extension / "Complication"]:
            contents = binary.read_bytes()
            binary.write_bytes(b"")
            self.reject()
            binary.unlink()
            self.reject()
            binary.write_bytes(contents)

    def test_executable_path_cannot_escape_bundle(self):
        for bad in ["../outside", "/tmp/outside"]:
            self.watch_info["CFBundleExecutable"] = bad
            self.save_infos()
            self.reject()

    def test_complication_executable_path_cannot_escape_bundle(self):
        for bad in ["../outside", "/tmp/outside", "", ".", ".."]:
            with self.subTest(executable=bad):
                self.extension_info["CFBundleExecutable"] = bad
                self.save_infos()
                self.reject()

    def test_complication_extension_dictionary_is_required(self):
        for bad in [None, "com.apple.widgetkit-extension", []]:
            with self.subTest(extension=bad):
                if bad is None:
                    self.extension_info.pop("NSExtension", None)
                else:
                    self.extension_info["NSExtension"] = bad
                self.save_infos()
                self.reject()

    def test_complication_supported_platform_must_be_exactly_watchos(self):
        for bad in [[], ["WatchOS", "iPhoneOS"], "WatchOS"]:
            with self.subTest(platforms=bad):
                self.extension_info["CFBundleSupportedPlatforms"] = bad
                self.save_infos()
                self.reject()

    def test_exactly_one_watch_and_one_top_level_phone(self):
        extra_watch = self.phone / "Watch/Extra.app"
        extra_watch.mkdir()
        self.reject()
        extra_watch.rmdir()
        extra_phone = self.archive / "Products/Applications/Extra.app"
        extra_phone.mkdir()
        self.reject()

    def test_archive_application_path_cannot_escape(self):
        for bad in ["../Applications/Bain Luck.app", str(self.phone), "Applications/../../outside.app"]:
            with self.subTest(path=bad):
                self.write(self.archive / "Info.plist", {"ApplicationProperties": {"ApplicationPath": bad}})
                self.reject()

    def test_symlink_executable_and_info_are_rejected(self):
        for path in [self.phone / "Bain Luck", self.watch / "Watch", self.watch / "Info.plist",
                     self.extension / "Complication", self.extension / "Info.plist"]:
            contents = path.read_bytes()
            outside = Path(self.temp.name) / "outside"
            outside.write_bytes(contents)
            path.unlink()
            path.symlink_to(outside)
            self.reject()
            path.unlink()
            path.write_bytes(contents)

    def test_symlink_watch_bundle_is_rejected(self):
        target = Path(self.temp.name) / "ExternalWatch.app"
        self.watch.rename(target)
        self.watch.symlink_to(target, target_is_directory=True)
        self.reject()

    def test_symlink_complication_bundle_is_rejected(self):
        target = Path(self.temp.name) / "ExternalComplication.appex"
        self.extension.rename(target)
        self.extension.symlink_to(target, target_is_directory=True)
        self.reject()

    def test_symlink_plugins_directory_is_rejected(self):
        plugins = self.watch / "PlugIns"
        target = Path(self.temp.name) / "ExternalPlugIns"
        plugins.rename(target)
        plugins.symlink_to(target, target_is_directory=True)
        self.reject()


if __name__ == "__main__":
    unittest.main()
