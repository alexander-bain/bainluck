import importlib.util
from pathlib import Path
import unittest

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
            self.assertIn("compilation and runtime unverified", result["scope"])

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

if __name__ == "__main__":
    unittest.main()
