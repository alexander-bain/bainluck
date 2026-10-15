"""Execute the real setup shell against disposable worktrees/install metadata."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "setup-worktree-deps.sh"
REQUIRED = ["ts-jest", "jest", "jest-environment-jsdom", "next", "typescript"]


class SetupWorktreeDepsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="worktree-deps-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.target, self.source = self.root / "target", self.root / "source"
        for root in (self.target, self.source):
            (root / "frontend").mkdir(parents=True)
        subprocess.run(["git", "-C", str(self.target), "init", "-q"], check=True)
        (self.target / ".gitignore").write_text("node_modules\n")
        self.pkg = {
            "name": "fixture",
            "devDependencies": {name: "1.0.0" for name in REQUIRED},
        }
        self.packages = {
            "node_modules/"
            + name: {
                "version": "1.0.0",
                "resolved": "https://example.invalid/" + name,
                "integrity": "sha512-fixture",
            }
            for name in REQUIRED
        }
        self.packages["node_modules/transitive-helper"] = {
            "version": "2.0.0",
            "integrity": "sha512-transitive",
        }
        self.lock = {"lockfileVersion": 3, "packages": {"": self.pkg, **self.packages}}
        for root in (self.target, self.source):
            self.write(root / "frontend/package.json", self.pkg)
            self.write(root / "frontend/package-lock.json", self.lock)
        modules = self.source / "frontend/node_modules"
        for key, entry in self.packages.items():
            package = self.source / "frontend" / key
            package.mkdir(parents=True)
            self.write(
                package / "package.json",
                {"name": package.name, "version": entry["version"], "main": "index.js"},
            )
            (package / "index.js").write_text("module.exports = {};\n")
        self.write(
            modules / ".package-lock.json",
            {"lockfileVersion": 3, "packages": self.packages},
        )

    @staticmethod
    def write(path, obj):
        path.write_text(json.dumps(obj, sort_keys=True) + "\n")

    def invoke(self, source=None):
        return subprocess.run(
            ["bash", str(SCRIPT), str(self.target), str(source or self.source)],
            capture_output=True,
            text=True,
            timeout=15,
        )

    def snapshot(self, root):
        return {
            str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }

    def refuses_without_mutation(self, expected):
        before = self.snapshot(self.source)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stderr)
        self.assertIn("private", result.stderr)
        self.assertFalse((self.target / "frontend/node_modules").exists())
        self.assertEqual(before, self.snapshot(self.source))

    def test_matching_install_links_and_tools_resolve_from_target_idempotently(self):
        before = self.snapshot(self.source)
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        link = self.target / "frontend/node_modules"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), self.source / "frontend/node_modules")
        resolved = subprocess.run(
            ["node", "-e", "console.log(require.resolve('jest-environment-jsdom'))"],
            cwd=self.target / "frontend",
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            Path(resolved.stdout.strip()),
            self.source / "frontend/node_modules/jest-environment-jsdom/index.js",
        )
        self.assertEqual(self.invoke().returncode, 0)
        self.assertEqual(before, self.snapshot(self.source))

    def test_missing_jsdom_refuses_before_linking(self):
        shutil.rmtree(self.source / "frontend/node_modules/jest-environment-jsdom")
        self.refuses_without_mutation("jest-environment-jsdom")

    def test_missing_jsdom_installed_lock_entry_refuses(self):
        del self.packages["node_modules/jest-environment-jsdom"]
        self.write(
            self.source / "frontend/node_modules/.package-lock.json",
            {"lockfileVersion": 3, "packages": self.packages},
        )
        self.refuses_without_mutation(
            "missing required package node_modules/jest-environment-jsdom"
        )

    def test_changed_package_inputs_refuse(self):
        self.write(
            self.target / "frontend/package.json",
            {**self.pkg, "description": "target changed"},
        )
        self.refuses_without_mutation(
            "Target/source package.json or package-lock.json differ"
        )

    def test_changed_lock_inputs_refuse(self):
        self.write(
            self.target / "frontend/package-lock.json",
            {**self.lock, "name": "target changed"},
        )
        self.refuses_without_mutation(
            "Target/source package.json or package-lock.json differ"
        )

    def test_package_and_lock_disagreement_refuses(self):
        self.write(
            self.target / "frontend/package.json",
            {
                **self.pkg,
                "devDependencies": {**self.pkg["devDependencies"], "jest": "2.0.0"},
            },
        )
        self.refuses_without_mutation("disagree on devDependencies")

    def test_mismatched_actual_required_version_refuses(self):
        self.write(
            self.source / "frontend/node_modules/jest/package.json",
            {"version": "9.0.0", "main": "index.js"},
        )
        self.refuses_without_mutation(
            "Installed version differs from target lock: node_modules/jest"
        )

    def test_mismatched_installed_lock_version_refuses(self):
        installed = {
            **self.packages,
            "node_modules/jest": {
                **self.packages["node_modules/jest"],
                "version": "9.0.0",
            },
        }
        self.write(
            self.source / "frontend/node_modules/.package-lock.json",
            {"lockfileVersion": 3, "packages": installed},
        )
        self.refuses_without_mutation(
            "Installed lock differs from target lock: node_modules/jest"
        )

    def test_incompatible_transitive_metadata_refuses(self):
        installed = {
            **self.packages,
            "node_modules/transitive-helper": {
                "version": "2.0.0",
                "integrity": "sha512-other",
            },
        }
        self.write(
            self.source / "frontend/node_modules/.package-lock.json",
            {"lockfileVersion": 3, "packages": installed},
        )
        self.refuses_without_mutation(
            "Installed lock differs from target lock: node_modules/transitive-helper"
        )

    def test_missing_transitive_package_refuses(self):
        shutil.rmtree(self.source / "frontend/node_modules/transitive-helper")
        self.refuses_without_mutation("transitive-helper")

    def test_no_installed_lock_metadata_refuses(self):
        (self.source / "frontend/node_modules/.package-lock.json").unlink()
        self.refuses_without_mutation(".package-lock.json")

    def test_unresolvable_tool_entry_refuses(self):
        (self.source / "frontend/node_modules/jest-environment-jsdom/index.js").unlink()
        self.refuses_without_mutation("jest-environment-jsdom")

    def test_hand_linked_jsdom_cannot_replace_coherent_install(self):
        package = self.source / "frontend/node_modules/jest-environment-jsdom"
        moved = self.root / "hand-linked-jsdom"
        package.rename(moved)
        package.symlink_to(moved, target_is_directory=True)
        self.refuses_without_mutation("Package must not be hand-linked")

    def test_valid_private_install_is_preserved_without_a_shared_source(self):
        private = self.target / "frontend/node_modules"
        shutil.copytree(self.source / "frontend/node_modules", private)
        before = self.snapshot(private)
        result = self.invoke(self.root / "nonexistent-shared")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified private install, preserved", result.stdout)
        self.assertFalse(private.is_symlink())
        self.assertEqual(before, self.snapshot(private))

    def test_invalid_private_install_is_preserved_and_refuses(self):
        private = self.target / "frontend/node_modules"
        shutil.copytree(self.source / "frontend/node_modules", private)
        self.write(private / "jest/package.json", {"version": "9.0.0"})
        before = self.snapshot(private)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(private.is_symlink())
        self.assertEqual(before, self.snapshot(private))

    def test_existing_different_link_is_preserved(self):
        other = self.root / "other-install"
        shutil.copytree(self.source / "frontend/node_modules", other)
        link = self.target / "frontend/node_modules"
        link.symlink_to(other, target_is_directory=True)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("points elsewhere", result.stderr)
        self.assertEqual(link.resolve(), other)

    def test_existing_file_is_preserved(self):
        destination = self.target / "frontend/node_modules"
        destination.write_text("caller owned\n")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(destination.read_text(), "caller owned\n")

    def test_missing_target_or_source_refuses(self):
        result = self.invoke(self.root / "missing-source")
        self.assertNotEqual(result.returncode, 0)
        shutil.rmtree(self.target / "frontend")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)

    def test_unignored_dependency_link_refuses_before_creation(self):
        (self.target / ".gitignore").write_text("")
        self.refuses_without_mutation("ignoring frontend/node_modules")

    def test_missing_declared_required_tool_cannot_be_hidden_in_the_lock(self):
        pkg = {**self.pkg, "devDependencies": dict(self.pkg["devDependencies"])}
        del pkg["devDependencies"]["jest-environment-jsdom"]
        lock = {**self.lock, "packages": {**self.lock["packages"], "": pkg}}
        for root in (self.target, self.source):
            self.write(root / "frontend/package.json", pkg)
            self.write(root / "frontend/package-lock.json", lock)
        self.refuses_without_mutation(
            "Target must declare required frontend tool jest-environment-jsdom"
        )

    def test_invalid_target_lock_package_version_refuses(self):
        lock = json.loads(json.dumps(self.lock))
        del lock["packages"]["node_modules/jest"]["version"]
        for root in (self.target, self.source):
            self.write(root / "frontend/package-lock.json", lock)
        self.refuses_without_mutation(
            "Target lock lacks an exact package version: node_modules/jest"
        )

    def test_malformed_lock_refuses_without_link(self):
        (self.source / "frontend/node_modules/.package-lock.json").write_text("{broken")
        self.refuses_without_mutation("FAIL:")


if __name__ == "__main__":
    unittest.main()
