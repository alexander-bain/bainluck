"""Finished products must survive relocation and reject mixed/corrupt evidence."""

import copy
import io
import json
from pathlib import Path
import plistlib
import tarfile
import tempfile
import unittest

from tools import watch_ui_products as gate


class ProductContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "package"
        self.payload = self.root / "payload"
        products = self.payload / "watch/Build/Products"
        watch = products / "Debug-watchsimulator"
        runner = watch / "BainLuckWatchUITests-Runner.app"
        (runner / "PlugIns/BainLuckWatchUITests.xctest").mkdir(parents=True)
        expected = {
            "TestHostPath": "__TESTROOT__/Debug-watchsimulator/BainLuckWatchUITests-Runner.app",
            "TestBundlePath": "__TESTHOST__/PlugIns/BainLuckWatchUITests.xctest",
            "UITargetAppPath": "__TESTROOT__/Debug-watchsimulator/BainLuckWatch Watch App.app",
            "DependentProductPaths": [
                "__TESTROOT__/Debug-watchsimulator/BainLuckComplication.appex",
                "__TESTROOT__/Debug-watchsimulator/BainLuckWatch Watch App.app",
                "__TESTROOT__/Debug-watchsimulator/BainLuckWatchUITests-Runner.app",
                "__TESTROOT__/Debug-watchsimulator/BainLuckWatchUITests-Runner.app/PlugIns/BainLuckWatchUITests.xctest",
            ],
        }
        self.run = products / "actual.xctestrun"
        self.run.write_bytes(
            plistlib.dumps({gate.XCTEST: expected, "__xctestrun_metadata__": {}})
        )
        for base, bundle, platform in [
            (
                self.payload / "phone/Bain Luck.app",
                "com.bainluck.Bain-Luck",
                "iPhoneSimulator",
            ),
            (
                self.payload / "phone/Bain Luck.app/Watch/BainLuckWatch Watch App.app",
                "com.bainluck.Bain-Luck.watchkitapp",
                "WatchSimulator",
            ),
            (
                watch / "BainLuckWatch Watch App.app",
                "com.bainluck.Bain-Luck.watchkitapp",
                "WatchSimulator",
            ),
            (
                watch / "BainLuckComplication.appex",
                "com.bainluck.Bain-Luck.watchkitapp.SavedGlance",
                "WatchSimulator",
            ),
        ]:
            base.mkdir(parents=True, exist_ok=True)
            (base / "Info.plist").write_bytes(
                plistlib.dumps(
                    {
                        "CFBundleIdentifier": bundle,
                        "CFBundleSupportedPlatforms": [platform],
                        "MinimumOSVersion": "10.0",
                    }
                )
            )
        for target, filename in gate.XCTENTS.items():
            path = (
                self.payload
                / "watch/Build/Intermediates.noindex/Bain Luck.build/Debug-watchsimulator"
                / (target + ".build")
                / filename
            )
            path.parent.mkdir(parents=True)
            path.write_bytes(
                plistlib.dumps({"com.apple.security.application-groups": [gate.GROUP]})
            )
        # Test bundle directories contain real payload files and executable modes.
        (runner / "PlugIns/BainLuckWatchUITests.xctest/test-binary").write_bytes(
            b"compiled-tests"
        )
        (runner / "runner").write_bytes(b"compiled-runner")
        (runner / "runner").chmod(0o755)
        self.environment = {
            "xcode": "27A266a",
            "watch_sdk": "27.0",
            "phone_sdk": "27.0",
        }
        self.manifest = {
            "schema": 1,
            "configuration": "Debug",
            "sha": "a" * 40,
            "source_fingerprint": "b" * 64,
            "toolchain": self.environment,
            "pins_sha256": "c" * 64,
            "architecture": "arm64",
            "xctestrun": gate.check_layout(self.payload),
            "files": gate.inventory(self.payload),
        }
        self.save()

    def save(self):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))

    def verify(self, root=None):
        return gate.verify_manifest(
            root or self.root, "a" * 40, self.environment, "c" * 64, "b" * 64
        )

    def test_relocation_preserves_paths_bytes_and_modes(self):
        archive = Path(self.temp.name) / "products.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            for path in self.root.rglob("*"):
                if path.is_file():
                    stream.add(path, path.relative_to(self.root), recursive=False)
        relocated = Path(self.temp.name) / "different-root"
        gate.unpack(archive, relocated)
        self.assertEqual(self.verify(), self.verify(relocated))
        with self.assertRaisesRegex(ValueError, "fresh"):
            gate.unpack(archive, relocated)

    def test_wrong_source_fingerprint_toolchain_sdk_pins_arch_rejected(self):
        for key, value in [
            ("sha", "d" * 40),
            ("source_fingerprint", "d" * 64),
            ("toolchain", {**self.environment, "watch_sdk": "26.0"}),
            ("pins_sha256", "d" * 64),
            ("architecture", "mips"),
        ]:
            with self.subTest(key=key):
                before = copy.deepcopy(self.manifest)
                self.manifest[key] = value
                self.save()
                with self.assertRaises(ValueError):
                    self.verify()
                self.manifest = before
                self.save()

    def test_corrupt_missing_extra_or_mode_changed_product_rejected(self):
        binary = (
            self.payload
            / "watch/Build/Products/Debug-watchsimulator/BainLuckWatchUITests-Runner.app/runner"
        )
        for mutation in [
            lambda: binary.write_bytes(b"wrong"),
            lambda: binary.unlink(),
            lambda: binary.chmod(0o644),
        ]:
            binary.write_bytes(b"compiled-runner")
            binary.chmod(0o755)
            mutation()
            with self.assertRaises(ValueError):
                self.verify()
        binary.write_bytes(b"compiled-runner")
        binary.chmod(0o755)
        (self.payload / "unexpected").write_text("extra")
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_xcent_or_group_rejected_even_with_rehashed_manifest(self):
        xcent = next(self.payload.rglob("*.xcent"))
        for content in [plistlib.dumps({}), None]:
            if content is None:
                xcent.unlink()
            else:
                xcent.write_bytes(content)
            self.manifest["files"] = gate.inventory(self.payload)
            self.save()
            with self.assertRaises((ValueError, OSError)):
                self.verify()

    def test_external_and_traversal_xctestrun_paths_refused(self):
        data = plistlib.loads(self.run.read_bytes())
        for value in [
            "/tmp/unrelated",
            "__TESTROOT__/../../escape",
            "__TESTROOT__/absent.app",
        ]:
            data[gate.XCTEST]["ExtraPath"] = value
            self.run.write_bytes(plistlib.dumps(data))
            with self.assertRaises(ValueError):
                gate.check_layout(self.payload)

    def test_minimum_os_and_platform_refused(self):
        path = self.payload / "phone/Bain Luck.app/Info.plist"
        info = plistlib.loads(path.read_bytes())
        info["MinimumOSVersion"] = "99.0"
        path.write_bytes(plistlib.dumps(info))
        with self.assertRaisesRegex(ValueError, "minimum OS"):
            gate.check_layout(self.payload, self.environment)
        info["CFBundleSupportedPlatforms"] = ["iPhoneOS"]
        path.write_bytes(plistlib.dumps(info))
        with self.assertRaisesRegex(ValueError, "platform"):
            gate.check_layout(self.payload)

    def test_tar_traversal_links_duplicates_rejected_before_extract(self):
        for variant in ["../escape", "symlink", "hardlink", "duplicate"]:
            archive = Path(self.temp.name) / (variant.replace("/", "_") + ".tar")
            with tarfile.open(archive, "w") as stream:
                member = tarfile.TarInfo(
                    "../escape" if variant == "../escape" else "payload/file"
                )
                if variant in {"symlink", "hardlink"}:
                    member.type = (
                        tarfile.SYMTYPE if variant == "symlink" else tarfile.LNKTYPE
                    )
                    member.linkname = "../../escape"
                stream.addfile(member, io.BytesIO())
                if variant == "duplicate":
                    stream.addfile(member, io.BytesIO())
            with self.assertRaises(ValueError):
                gate.unpack(archive, Path(self.temp.name) / "bad-output")


class BinaryCoverageTests(unittest.TestCase):
    def test_standalone_debug_dylib_is_checked_without_info_plist(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "standalone.debug.dylib").write_bytes(
                bytes.fromhex("cffaedfe") + b"payload"
            )
            with patch.object(
                gate.subprocess, "check_output", return_value="x86_64\n"
            ), self.assertRaisesRegex(ValueError, "architecture"):
                gate.verify_binaries(root, "arm64")


class RuntimeSupportTests(unittest.TestCase):
    setUp = ProductContractTests.setUp
    save = ProductContractTests.save

    def test_known_checker_path_relocated_with_diagnostics_unchanged(self):
        runtime_root = (
            Path(self.temp.name) / "Watch.simruntime/Contents/Resources/RuntimeRoot"
        )
        library = runtime_root / "usr/lib/libMainThreadChecker.dylib"
        library.parent.mkdir(parents=True)
        library.write_bytes(b"exact-runtime-checker")
        data = plistlib.loads(self.run.read_bytes())
        data[gate.XCTEST]["TestingEnvironmentVariables"] = {
            "DYLD_INSERT_LIBRARIES": str(library)
        }
        data[gate.XCTEST]["TestTimeoutsEnabled"] = False
        self.run.write_bytes(plistlib.dumps(data))
        runtime = {
            "runtimeRoot": str(runtime_root),
            "identifier": "watch27",
            "version": "27.0",
            "buildversion": "24R362",
            "isAvailable": True,
            "platform": "watchOS",
        }
        mapping = gate.runtime_support(self.payload, runtime)
        gate.verify_runtime_support(self.payload, mapping, self.environment)
        legacy = copy.deepcopy(mapping)
        legacy[0].pop("original_paths")
        legacy[0].pop("runtime_checker_path")
        gate.verify_runtime_support(self.payload, legacy, self.environment)
        self.assertEqual(
            plistlib.loads(self.run.read_bytes())[gate.XCTEST]["TestTimeoutsEnabled"],
            False,
        )
        gate.check_layout(self.payload)
        # A settings change disguised as relocation is rejected.
        changed = plistlib.loads(self.run.read_bytes())
        changed[gate.XCTEST]["TestTimeoutsEnabled"] = True
        self.run.write_bytes(plistlib.dumps(changed))
        with self.assertRaisesRegex(ValueError, "beyond exact"):
            gate.verify_runtime_support(self.payload, mapping, self.environment)

    def cryptex_fixture(self, extra_path=None):
        # Exact retained hosted path; simctl names /private/var, Xcode /var.
        injected = (
            "/var/run/com.apple.security.cryptexd/mnt/"
            "com.apple.WatchOS.SimulatorRuntime-v24.18.362.0.wdAulf/"
            "Library/Developer/CoreSimulator/Profiles/Runtimes/"
            "watchOS 27.0.simruntime/Contents/Resources/RuntimeRoot/"
            "usr/lib/libMainThreadChecker.dylib"
        )
        selected = "/private" + injected
        runtime = {
            "runtimeRoot": str(Path(selected).parents[2]),
            "identifier": "com.apple.CoreSimulator.SimRuntime.watchOS-27-0",
            "version": "27.0",
            "buildversion": "24R362",
            "isAvailable": True,
            "platform": "watchOS",
        }
        data = plistlib.loads(self.run.read_bytes())
        data[gate.XCTEST]["TestingEnvironmentVariables"] = {
            "DYLD_INSERT_LIBRARIES": injected,
            "OTHER_DIAGNOSTIC": "retained",
        }
        data[gate.XCTEST]["EnvironmentVariables"] = {
            "DYLD_INSERT_LIBRARIES": selected + (":" + extra_path if extra_path else "")
        }
        self.run.write_bytes(plistlib.dumps(data))
        return injected, selected, runtime

    def test_hosted_cryptex_var_alias_relocates_only_identical_selected_checker(self):
        from unittest.mock import call, patch

        injected, selected, runtime = self.cryptex_fixture()
        original = self.run.read_bytes()

        def copy_checker(source, destination):
            self.assertEqual(source, selected)
            destination.write_bytes(b"selected-runtime-checker")

        with patch.object(Path, "samefile", autospec=True, return_value=True) as same:
            with patch.object(gate.shutil, "copy2", side_effect=copy_checker):
                mapping = gate.runtime_support(self.payload, runtime)
        # Old source leaves the /var spelling absolute, reproducing hosted refusal.
        gate.check_layout(self.payload)
        self.assertCountEqual(
            same.call_args_list,
            [call(Path(injected), selected), call(Path(selected), selected)],
        )
        self.assertEqual(mapping[0]["runtime_checker_path"], selected)
        self.assertEqual(set(mapping[0]["original_paths"]), {injected, selected})
        self.assertEqual(
            (self.payload / "provenance/original.xctestrun").read_bytes(), original
        )
        gate.verify_runtime_support(self.payload, mapping, self.environment)
        gate.check_layout(self.payload)
        self.assertEqual(mapping[0]["runtime_build"], "24R362")
        self.assertEqual(mapping[0]["runtime"], runtime["identifier"])
        self.assertEqual(
            plistlib.loads(self.run.read_bytes())[gate.XCTEST][
                "TestingEnvironmentVariables"
            ]["OTHER_DIAGNOSTIC"],
            "retained",
        )
        for bad_path in (injected.replace("wdAulf", "another"), "/tmp/checker"):
            bad = copy.deepcopy(mapping)
            bad[0]["original_paths"].append(bad_path)
            with self.assertRaisesRegex(ValueError, "alias provenance"):
                gate.verify_runtime_support(self.payload, bad, self.environment)
        bad = copy.deepcopy(mapping)
        bad[0]["runtime_checker_path"] = selected.replace("wdAulf", "another")
        with self.assertRaisesRegex(ValueError, "alias provenance"):
            gate.verify_runtime_support(self.payload, bad, self.environment)
        with self.assertRaisesRegex(ValueError, "provenance"):
            gate.verify_runtime_support(self.payload, mapping, {"watch_sdk": "26.0"})

    def test_cryptex_alias_different_or_missing_file_fails_before_copy(self):
        from unittest.mock import patch

        _, _, runtime = self.cryptex_fixture()
        original = self.run.read_bytes()
        for result in (False, FileNotFoundError("missing selected checker")):
            with self.subTest(result=result):
                with patch.object(Path, "samefile", side_effect=[result]) as same:
                    with patch.object(gate.shutil, "copy2") as copy_checker:
                        with self.assertRaises((ValueError, FileNotFoundError)):
                            gate.runtime_support(self.payload, runtime)
                        copy_checker.assert_not_called()
                    same.assert_called_once()
                self.assertEqual(self.run.read_bytes(), original)

    def test_cryptex_unknown_external_library_remains_rejected(self):
        from unittest.mock import patch

        _, _, runtime = self.cryptex_fixture("/var/run/unknown/libOther.dylib")
        with patch.object(Path, "samefile", return_value=True):
            with patch.object(
                gate.shutil,
                "copy2",
                side_effect=lambda source, destination: destination.write_bytes(
                    b"checker"
                ),
            ):
                mapping = gate.runtime_support(self.payload, runtime)
        gate.verify_runtime_support(self.payload, mapping, self.environment)
        with self.assertRaisesRegex(ValueError, "External absolute"):
            gate.check_layout(self.payload)

    def test_same_named_checker_in_other_mount_is_not_an_alias(self):
        from unittest.mock import patch

        injected, _, runtime = self.cryptex_fixture()
        data = plistlib.loads(self.run.read_bytes())
        del data[gate.XCTEST]["EnvironmentVariables"]
        data[gate.XCTEST]["TestingEnvironmentVariables"]["DYLD_INSERT_LIBRARIES"] = (
            injected.replace("wdAulf", "different")
        )
        self.run.write_bytes(plistlib.dumps(data))
        with patch.object(Path, "samefile") as same:
            self.assertEqual(gate.runtime_support(self.payload, runtime), [])
            same.assert_not_called()
        with self.assertRaisesRegex(ValueError, "External absolute"):
            gate.check_layout(self.payload)

    def test_unknown_external_checker_is_never_whitelisted(self):
        data = plistlib.loads(self.run.read_bytes())
        data[gate.XCTEST]["TestingEnvironmentVariables"] = {
            "DYLD_INSERT_LIBRARIES": "/wrong/RuntimeRoot/usr/lib/libMainThreadChecker.dylib"
        }
        self.run.write_bytes(plistlib.dumps(data))
        self.assertEqual(
            gate.runtime_support(self.payload, {"runtimeRoot": "/actual/RuntimeRoot"}),
            [],
        )
        with self.assertRaisesRegex(ValueError, "External absolute"):
            gate.check_layout(self.payload)


class CarrierStubTests(unittest.TestCase):
    setUp = ProductContractTests.setUp
    save = ProductContractTests.save

    def add_stub(
        self, name="FirebaseAnalytics", location="phone/Bain Luck.app/Frameworks"
    ):
        base = self.payload / location / (name + ".framework")
        base.mkdir(parents=True)
        (base / name).write_bytes(bytes.fromhex("cffaedfe") + b"stub")
        (base / "Info.plist").write_bytes(
            plistlib.dumps(
                {
                    "CFBundleExecutable": name,
                    "CFBundlePackageType": "FMWK",
                    "CFBundleSupportedPlatforms": ["iPhoneSimulator"],
                    "MinimumOSVersion": "100.0",
                }
            )
        )
        return base

    def classify(self, *, export="", load="", platform="IOSSIMULATOR", minimum="100.0"):
        from unittest.mock import patch

        def command(args, **kwargs):
            if args[0] == "otool":
                return (
                    "Load command 1\n cmd LC_LOAD_DYLIB\n name "
                    + load
                    + " (offset 24)\n"
                    if load
                    else ""
                )
            if args[0] == "lipo":
                return "arm64\n"
            if args[0] == "nm":
                return export
            if args[:2] == ["xcrun", "vtool"]:
                return f"Load command 1\n cmd LC_BUILD_VERSION\n platform {platform}\n minos {minimum}\n sdk 27.0\n"
            raise AssertionError(args)

        with patch.object(gate.subprocess, "check_output", side_effect=command):
            return gate.classify_carrier_stubs(self.payload, self.environment)

    def test_only_proven_empty_unreferenced_exact_phone_carrier_is_allowed(self):
        self.add_stub()
        classification = self.classify()
        gate.check_layout(self.payload, self.environment, classification)
        self.assertEqual(len(classification), 1)
        with self.assertRaisesRegex(ValueError, "minimum OS"):
            gate.check_layout(self.payload, self.environment)

    def test_exported_referenced_or_wrong_platform_binary_is_not_a_carrier(self):
        self.add_stub()
        for options in [
            {"export": "00000001 T _real_code\n"},
            {"load": "@rpath/FirebaseAnalytics.framework/FirebaseAnalytics"},
            {"platform": "WATCHOSSIMULATOR"},
            {"minimum": "99.0"},
        ]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.classify(**options)

    def test_misplaced_or_unknown_future_minimum_framework_never_exempt(self):
        self.add_stub("UnknownFramework")
        self.assertEqual(self.classify(), {})
        with self.assertRaises(ValueError):
            gate.check_layout(self.payload, self.environment)
        self.add_stub(location="watch/Build/Products/Debug-watchsimulator")
        self.assertEqual(self.classify(), {})
        with self.assertRaises(ValueError):
            gate.check_layout(self.payload, self.environment)


if __name__ == "__main__":
    unittest.main()
