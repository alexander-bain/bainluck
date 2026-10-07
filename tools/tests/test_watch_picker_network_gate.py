"""Typed network guidance requires the complete visible recovery journey."""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
NETWORK = ("WATCH_UI_PICKER_NETWORK_OFFLINE=PASS", "WATCH_UI_PICKER_NETWORK_INTERRUPTED=PASS", "WATCH_UI_PICKER_NETWORK_TIMEOUT=PASS")
CASE = "Test Case '-[BainLuckWatchUITests.PickerReturnJourneyTests testNetworkFailureGuidanceRetainsChoicesAndRecoversSelection]' passed (100.0 seconds)."
FRESH = "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testFreshConfiguredFaceIsActiveBeforeActualLauncherTap]' passed (60.0 seconds)."


class PickerNetworkReceiptTests(unittest.TestCase):
    def setUp(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        self.code = harness.split("<<'PYVERIFY'\n", 1)[1].split("\nPYVERIFY", 1)[0]
        # Carry all existing marker prerequisites while testing the new obligation
        # independently: deleting a NETWORK requirement must break these guards.
        marker_loop = next(node for node in ast.walk(ast.parse(self.code))
                           if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "marker")
        markers = ast.literal_eval(marker_loop.iter)
        self.rows = ["WATCH_UI_STRESS_TYPE=accessibility5", "WATCH_UI_STANDARD_TYPE=xLarge", FRESH, CASE,
                     *dict.fromkeys((*markers, *NETWORK)),
                     *(f"Test Case '-[BainLuckWatchUITests.PickerSelectedStateJourneyTests {case}]' passed (12.0 seconds)."
                       for case in ("testSelectedGameIsMarkedInPickerAndCanChange", "testSelectedGameIsMarkedAtAccessibilitySize")),
                     *(f"Test Case '-[BainLuckWatchUITests.SelectedGameUpdatingJourneyTests {case}]' passed (12.0 seconds)."
                       for case in ("testUpdatingIsVisibleUntilRequestFinishes", "testUpdatingIsVisibleAtAccessibilitySize"))]

    def run_gate(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "tests.log"
            log.write_text("\n".join(rows))
            return subprocess.run([sys.executable, "-c", self.code, str(log)], capture_output=True).returncode

    def test_all_network_scenarios_and_passed_case_are_required(self):
        self.assertEqual(self.run_gate(self.rows), 0)
        for missing in (*NETWORK, CASE):
            with self.subTest(missing=missing):
                self.assertEqual(self.run_gate([row for row in self.rows if row != missing]), 1)

    def test_failed_skipped_or_started_case_cannot_be_paid_by_markers(self):
        for replacement in (CASE.replace("passed", "failed"), CASE.replace("passed", "skipped"), CASE.split(" passed")[0] + " started."):
            with self.subTest(replacement=replacement):
                self.assertEqual(self.run_gate([replacement if row == CASE else row for row in self.rows]), 1)

    def test_partial_or_synthesized_marker_does_not_count(self):
        for marker in NETWORK:
            with self.subTest(marker=marker):
                self.assertEqual(self.run_gate(["prefix " + row if row == marker else row for row in self.rows]), 1)

    def test_existing_fresh_face_and_stress_requirements_remain(self):
        for missing in (FRESH, "WATCH_UI_STRESS_TYPE=accessibility5"):
            with self.subTest(missing=missing):
                self.assertEqual(self.run_gate([row for row in self.rows if row != missing]), 1)


if __name__ == "__main__":
    unittest.main()
