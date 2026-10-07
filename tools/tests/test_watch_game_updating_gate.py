"""Updating selected game acceptance requires both complete hosted test cases and markers."""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MARKERS = ("WATCH_UI_GAME_UPDATING_STANDARD=PASS", "WATCH_UI_GAME_UPDATING_LARGE=PASS")
METHODS = ("testUpdatingIsVisibleUntilRequestFinishes", "testUpdatingIsVisibleAtAccessibilitySize")
CASES = tuple(f"Test Case '-[BainLuckWatchUITests.SelectedGameUpdatingJourneyTests {case}]' passed (12.0 seconds)." for case in METHODS)


def receipt_code():
    harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
    return harness.split("<<'PYVERIFY'\n", 1)[1].split("\nPYVERIFY", 1)[0]


def accepted_log():
    # Read the existing receipt's marker contract so unrelated composed markers
    # remain required rather than weakening their checks in this focused guard.
    code = ast.parse(receipt_code())
    required = next(ast.literal_eval(node.iter) for node in ast.walk(code)
                    if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "marker")
    return "\n".join(("WATCH_UI_STRESS_TYPE=accessibility5", "WATCH_UI_STANDARD_TYPE=large", *required,
        "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testFreshConfiguredFaceIsActiveBeforeActualLauncherTap]' passed (90.0 seconds).", "Test Case '-[BainLuckWatchUITests.PickerReturnJourneyTests testNetworkFailureGuidanceRetainsChoicesAndRecoversSelection]' passed (100.0 seconds).", *CASES, "Test Case '-[BainLuckWatchUITests.PickerSelectedStateJourneyTests testSelectedGameIsMarkedInPickerAndCanChange]' passed (12.0 seconds).", "Test Case '-[BainLuckWatchUITests.PickerSelectedStateJourneyTests testSelectedGameIsMarkedAtAccessibilitySize]' passed (12.0 seconds)."))


class WatchGameUpdatingGateTests(unittest.TestCase):
    def gate(self, log):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tests.log"
            path.write_text(log)
            return subprocess.run([sys.executable, "-c", receipt_code(), str(path)], capture_output=True, text=True)

    def test_both_markers_and_both_executed_cases_are_required(self):
        self.assertEqual(self.gate(accepted_log()).returncode, 0)
        for item in (*MARKERS, *CASES):
            with self.subTest(item=item):
                self.assertEqual(self.gate(accepted_log().replace(item, "")).returncode, 1)

    def test_failed_skipped_duplicate_or_wrong_case_cannot_be_replaced_by_markers(self):
        for case in CASES:
            for replacement in (case.replace("passed", "failed"), case.replace("passed", "skipped"),
                                case + "\n" + case, case.replace("SelectedGameUpdatingJourneyTests", "UnrelatedTests")):
                with self.subTest(case=case, replacement=replacement):
                    self.assertEqual(self.gate(accepted_log().replace(case, replacement)).returncode, 1)

    def test_marker_substring_or_synthetic_summary_cannot_pay_case(self):
        for marker in MARKERS:
            with self.subTest(marker=marker):
                self.assertEqual(self.gate(accepted_log().replace(marker, "prefix " + marker)).returncode, 1)
        summary = "Test Suite 'All tests' passed at now.\n Executed 99 tests, with 0 failures\n** TEST EXECUTE SUCCEEDED **"
        self.assertEqual(self.gate(accepted_log().replace(CASES[0], summary)).returncode, 1)

    def test_existing_markers_and_source_methods_remain_required(self):
        self.assertEqual(self.gate(accepted_log().replace("WATCH_UI_PICKER_RETURN=PASS", "")).returncode, 1)
        source = (ROOT / "ios/Bain Luck/BainLuckWatchUITests/SelectedGameUpdatingJourneyTests.swift").read_text()
        for method in METHODS:
            self.assertEqual(source.count("func " + method + "()"), 1)
        for marker in MARKERS:
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
