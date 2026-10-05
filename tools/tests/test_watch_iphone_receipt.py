"""Guard the completed full-suite evidence required by the iPhone receipt."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "watch_iphone_receipt.py"
SPEC = importlib.util.spec_from_file_location("watch_iphone_receipt", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
RECEIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECEIPT)


def summary(count=2083, failures=0, state="passed"):
    return (
        f"Test Suite 'All tests' {state} at 2026-10-03 12:00:00.000.\n"
        f"\t Executed {count} tests, with {failures} failures (0 unexpected) "
        "in 27.902 (29.156) seconds\n"
    )


class VerifiedSummaryTests(unittest.TestCase):
    def test_accepts_completed_test_without_building_log(self):
        # Retained Watch UI output: the xctest total precedes All tests, and
        # xcodebuild diagnostics/results separate the total from its banner.
        log = (
            "Test Suite 'BainLuckWatchUITests.xctest' passed at 2026-10-05 05:57:15.722.\n"
            "\t Executed 13 tests, with 0 failures (0 unexpected) in 785.352 (785.389) seconds\n"
            "Test Suite 'All tests' passed at 2026-10-05 05:57:15.722.\n"
            "\t Executed 13 tests, with 0 failures (0 unexpected) in 785.352 (785.396) seconds\n"
            "2026-10-05 05:57:17.104 xcodebuild[67562:180007] [MT] "
            "IDETestOperationsObserverDebug: 805.861 elapsed -- Testing started completed.\n"
            "\nTest session results, code coverage, and logs:\n"
            "\t/build/watch-ui-journey/BainLuckWatchUITests.xcresult\n"
            "\n** TEST EXECUTE SUCCEEDED **\n\nTesting started\n"
        )
        count, line = RECEIPT.verified_summary(log, 0)
        self.assertEqual(count, 13)
        self.assertEqual(
            line,
            "Executed 13 tests, with 0 failures (0 unexpected) in 785.352 (785.396) seconds",
        )

    def test_execute_banner_does_not_relax_completed_suite_requirements(self):
        banner = "** TEST EXECUTE SUCCEEDED **\n"
        cases = {
            "nonzero exit": (summary(count=13) + banner, 65),
            "cancelled process": (summary(count=13) + banner, 143),
            "missing summary": (banner, 0),
            "class total only": (summary(count=13).replace("'All tests'", "'WidgetTapJourneyTests'") + banner, 0),
            "started suite only": (summary(count=13, state="started") + banner, 0),
            "zero tests": (summary(count=0) + banner, 0),
            "contradictory failures": (summary(count=13, failures=1) + banner, 0),
            "failed suite": (summary(count=13, state="failed") + banner, 0),
            "duplicate completed totals": (summary(count=13) * 2 + banner, 0),
            "nonadjacent total": (summary(count=13).replace("\n\t", "\nOther output\n\t") + banner, 0),
            "diagnostic success text": (summary(count=13) + "diagnostic: " + banner, 0),
            "failed execute banner": (summary(count=13) + "** TEST EXECUTE FAILED **\n", 0),
            "build without test execution": (summary(count=13) + "** TEST BUILD SUCCEEDED **\n", 0),
        }
        for name, (log, exit_code) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    RECEIPT.verified_summary(log, exit_code)

    def test_rejects_failed_banner_even_with_success_and_zero_exit(self):
        for failed_banner in ("** TEST FAILED **", "** TEST EXECUTE FAILED **"):
            for success_banner in ("** TEST SUCCEEDED **", "** TEST EXECUTE SUCCEEDED **"):
                for failure_first in (False, True):
                    banners = [failed_banner, success_banner]
                    if not failure_first:
                        banners.reverse()
                    with self.subTest(
                        failed=failed_banner, success=success_banner, failure_first=failure_first
                    ):
                        log = summary(count=13) + "\n".join(banners) + "\n"
                        with self.assertRaises(ValueError):
                            RECEIPT.verified_summary(log, 0)

    def test_named_total_survives_trailing_class_bait(self):
        log = (
            summary()
            + "Test Suite 'StragglerTests' passed at 2026-10-03 12:00:01.000.\n"
            + "\t Executed 2 tests, with 0 failures (0 unexpected) in 0.1 seconds\n"
            + "** TEST SUCCEEDED **\n"
        )
        count, line = RECEIPT.verified_summary(log, 0)
        self.assertEqual(count, 2083)
        self.assertIn("Executed 2083 tests, with 0 failures", line)

    def test_rejects_incomplete_or_contradictory_evidence(self):
        class_only = (
            "Test Suite 'ExampleTests' passed at 2026-10-03 12:00:00.000.\n"
            "\t Executed 5 tests, with 0 failures (0 unexpected) in 0.1 seconds\n"
        )
        cases = {
            "failed suite": (summary(failures=3, state="failed") + "** TEST FAILED **\n", 65),
            "missing summary": ("** TEST SUCCEEDED **\n", 0),
            "class total only": (class_only + "** TEST SUCCEEDED **\n", 0),
            "started suite only": ("Test Suite 'All tests' started at 12:00.\n" + class_only, 137),
            "zero tests": (summary(count=0) + "** TEST SUCCEEDED **\n", 0),
            "missing success marker": (summary(), 0),
            "nonzero exit": (summary() + "** TEST SUCCEEDED **\n", 65),
            "contradictory failures": (summary(failures=2) + "** TEST SUCCEEDED **\n", 0),
            "failed suite with success marker": (summary(state="failed") + "** TEST SUCCEEDED **\n", 0),
            "unanchored success marker": (summary() + "diagnostic: ** TEST SUCCEEDED **\n", 0),
            "nonadjacent total": (summary().replace("\n\t", "\nOther output\n\t") + "** TEST SUCCEEDED **\n", 0),
        }
        for name, (log, exit_code) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    RECEIPT.verified_summary(log, exit_code)


if __name__ == "__main__":
    unittest.main()
