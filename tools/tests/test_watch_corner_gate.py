"""A corner PASS requires the actual configured host case and fallback controls."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKERS = ("WATCH_UI_ACTUAL_CORNER_SAVED=PASS", "WATCH_UI_CORNER_FALLBACK=PASS")
CASES = (
    "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testActualCornerSavedReadingAndTap]' passed (130.0 seconds).",
    "Test Case '-[BainLuckWatchUITests.ComplicationContentJourneyTests testCornerUnsupportedReadingsStayLaunchers]' passed (60.0 seconds).",
)


class WatchCornerGateTests(unittest.TestCase):
    def gate(self, log):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        code = harness.split("<<'PYCORNER'\n", 1)[1].split("\nPYCORNER", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tests.log"
            path.write_text(log)
            return subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, text=True)

    def test_complete_actual_and_fallback_cases_pass(self):
        self.assertEqual(self.gate("\n".join((*MARKERS, *CASES))).returncode, 0)

    def test_missing_marker_or_executed_case_is_unpaid(self):
        for item in (*MARKERS, *CASES):
            with self.subTest(item=item):
                self.assertEqual(self.gate("\n".join(x for x in (*MARKERS, *CASES) if x != item)).returncode, 1)

    def test_failed_or_skipped_case_cannot_be_replaced_by_markers(self):
        for outcome in ("failed", "skipped"):
            with self.subTest(outcome=outcome):
                log = "\n".join((*MARKERS, CASES[0].replace("passed", outcome), CASES[1]))
                self.assertEqual(self.gate(log).returncode, 1)

    def test_all_corner_fallback_scenarios_have_debug_routes(self):
        tests = (ROOT / "ios/Bain Luck/BainLuckWatchUITests/ComplicationContentJourneyTests.swift").read_text()
        block = tests.split("func testCornerUnsupportedReadingsStayLaunchers()", 1)[1].split("private func launchCircular", 1)[0]
        cases = re.search(r"for cornerScenario in \[(.*?)\]", block, re.S).group(1)
        routes = (ROOT / "ios/Bain Luck/BainLuckWatch Watch App/WatchTabView.swift").read_text()
        for scenario in re.findall(r'"([a-z-]+)"', cases):
            self.assertIn(f'"corner-{scenario}"', routes)


if __name__ == "__main__":
    unittest.main()
