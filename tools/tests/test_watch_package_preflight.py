"""Synthetic guards for final Watch package and supplied evidence consistency."""
import copy
import hashlib
import json
import contextlib
import io
import os
from pathlib import Path
import plistlib
import sys
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import watch_package_preflight as tool
import test_watch_companion_archive as archive_tests


class WatchPackagePreflightTests(unittest.TestCase):
    def setUp(self):
        self.fixture = archive_tests.WatchCompanionArchiveTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.archive = self.fixture.archive
        self.widget = self.fixture.phone / "PlugIns/Widget.appex"
        self.widget.mkdir(parents=True)
        self.widget_info = dict(self.fixture.extension_info,
            CFBundleIdentifier=tool.WIDGET, CFBundleExecutable="Widget",
            CFBundleSupportedPlatforms=["iPhoneOS"])
        (self.widget / "Info.plist").write_bytes(plistlib.dumps(self.widget_info))
        (self.widget / "Widget").write_bytes(b"synthetic executable")
        digest = hashlib.sha256(b"synthetic executable").hexdigest()
        self.manifest = {"version": 1, "applications": [
            {"bundle_id": bid, "executable_sha256": digest, "entitlements": {
                "application-identifier": "TEAM." + bid,
                "com.apple.developer.team-identifier": "TEAM",
                "com.apple.security.application-groups": [tool.GROUP],
            }} for bid in (tool.PHONE, tool.WATCH, tool.COMPLICATION, tool.WIDGET)]}

    def platform(self, path):
        return "WATCHOS" if "Watch.app" in path.parts else "IOS"

    def inspect(self, artifact=None, manifest=None):
        return tool.inspect_package(artifact or self.archive, manifest or self.manifest, self.platform)

    def ipa(self):
        ipa = self.archive.parent / "Candidate.ipa"
        with zipfile.ZipFile(ipa, "w") as package:
            base = self.archive / "Products/Applications"
            for file in base.rglob("*"):
                if file.is_file():
                    package.write(file, "Payload/" + file.relative_to(base).as_posix())
        return ipa

    def test_archive_and_ipa_consistency_preserves_evidence_limits(self):
        for artifact in (self.archive, self.ipa()):
            result = self.inspect(artifact)
            self.assertEqual(result["verdict"], "PACKAGE_AND_SUPPLIED_EVIDENCE_CONSISTENT")
            self.assertEqual(len(result["applications"]), 4)
            self.assertEqual(result["signature_authenticity"], "UNVERIFIED")
            self.assertEqual(result["distribution"], "UNVERIFIED")
            self.assertIn("NOT_CRYPTOGRAPHICALLY_VERIFIED", result["entitlements_evidence"])

    def test_missing_embedded_payload_and_widget_are_rejected(self):
        for folder in (self.fixture.watch, self.fixture.extension, self.widget):
            with self.subTest(folder=folder):
                moved = folder.with_name(folder.name + ".hidden")
                folder.rename(moved)
                try:
                    with self.assertRaises(ValueError): self.inspect()
                finally: moved.rename(folder)

    def test_version_mismatch_rejected(self):
        for file in (self.widget / "Info.plist", self.fixture.watch / "Info.plist"):
            original = file.read_bytes()
            info = plistlib.loads(original)
            info["CFBundleVersion"] = "999"
            file.write_bytes(plistlib.dumps(info))
            with self.assertRaises(ValueError): self.inspect()
            file.write_bytes(original)

    def test_hash_group_identity_and_team_mismatch_rejected(self):
        variants = []
        for key, value in [("executable_sha256", "0" * 64), ("bundle_id", "wrong")]:
            manifest = copy.deepcopy(self.manifest)
            manifest["applications"][1][key] = value
            variants.append(manifest)
        for key, value in [("com.apple.security.application-groups", []),
                           ("application-identifier", "TEAM.wrong"),
                           ("com.apple.developer.team-identifier", "OTHER")]:
            manifest = copy.deepcopy(self.manifest)
            manifest["applications"][1]["entitlements"][key] = value
            variants.append(manifest)
        variants += [{"version": 1, "applications": []},
                     {"version": 2, "applications": self.manifest["applications"]}]
        for manifest in variants:
            with self.subTest(manifest=manifest):
                with self.assertRaises(ValueError): self.inspect(manifest=manifest)

    def test_zip_traversal_duplicate_symlink_and_size_limits_rejected(self):
        for name in ("../escape", "/absolute", "Payload/../escape", "Payload\\escape"):
            ipa = self.ipa()
            with zipfile.ZipFile(ipa, "a") as package: package.writestr(name, b"x")
            with self.assertRaises(ValueError): self.inspect(ipa)
        ipa = self.ipa()
        with zipfile.ZipFile(ipa, "a") as package:
            package.writestr("Payload/Bain Luck.app/Info.plist", b"duplicate")
        with self.assertRaises(ValueError): self.inspect(ipa)
        ipa = self.ipa()
        with zipfile.ZipFile(ipa, "a") as package:
            link = zipfile.ZipInfo("Payload/link")
            link.create_system = 3
            link.external_attr = 0o120777 << 16
            package.writestr(link, "target")
        with self.assertRaises(ValueError): self.inspect(ipa)
        ipa = self.ipa()
        for constant in ("MAX_ENTRIES", "MAX_MEMBER", "MAX_TOTAL"):
            with patch.object(tool, constant, 1):
                with self.assertRaises(ValueError): self.inspect(ipa)

    def test_receipt_output_hardlinks_cannot_mutate_inputs(self):
        ipa = self.ipa()
        manifest = self.archive.parent / "manifest.json"
        manifest.write_text(json.dumps(self.manifest))
        for source in (ipa, manifest):
            output = self.archive.parent / "receipt.json"
            os.link(source, output)
            before = source.read_bytes()
            try:
                with patch.object(sys, "argv", ["preflight", "--artifact", str(ipa),
                        "--entitlements-evidence", str(manifest), "--output", str(output)]):
                    with self.assertRaises(ValueError):
                        tool.main()
                self.assertEqual(source.read_bytes(), before)
            finally:
                output.unlink()

    def test_dot_zip_member_emits_unpaid_receipt(self):
        ipa = self.ipa()
        with zipfile.ZipFile(ipa, "a") as package:
            package.writestr(".", b"x")
        manifest = self.archive.parent / "manifest.json"
        manifest.write_text(json.dumps(self.manifest))
        output = self.archive.parent / "receipt.json"
        with patch.object(sys, "argv", ["preflight", "--artifact", str(ipa),
                "--entitlements-evidence", str(manifest), "--output", str(output)]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(tool.main(), 1)
        self.assertEqual(json.loads(output.read_text())["verdict"], "UNPAID")
        self.assertIn("Unsafe IPA path", json.loads(output.read_text())["reason"])

    def test_wrong_widget_platform_and_missing_executable_rejected(self):
        with self.assertRaises(ValueError):
            tool.inspect_package(self.archive, self.manifest, lambda path: "WATCHOS")
        (self.widget / "Widget").unlink()
        with self.assertRaises(ValueError): self.inspect()


if __name__ == "__main__":
    unittest.main()
