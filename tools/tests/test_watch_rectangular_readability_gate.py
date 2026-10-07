"""Incomplete captures cannot pay the named rectangular readability ship."""
import ast
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
NETWORK_FREE_MARKERS = (
    "WATCH_UI_RECTANGULAR_TYPED=PASS", "WATCH_UI_RECTANGULAR_MONOCHROME=PASS",
    "WATCH_UI_RECTANGULAR_LEGACY=PASS", "WATCH_UI_RECTANGULAR_ACTUAL_TYPED=PASS",
)
CASES = (
    ("ComplicationContentJourneyTests", "testRectangularTypedNamedValuesFitWithMonochromeRendering"),
    ("ComplicationContentJourneyTests", "testRectangularLegacyMismatchUnknownAndEmptyStayHonest"),
    ("RectangularWidgetHostJourneyTests", "testActualRectangularWidgetShowsPublishedSavedReading"),
)


def case_line(suite, case, result="passed"):
    return f"Test Case '-[BainLuckWatchUITests.{suite} {case}]' {result} (20.123 seconds)."


class RectangularReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = (ROOT / "tools/watch-ui-journey.sh").read_text().split("<<'PYVERIFY'\n", 1)[1].split("\nPYVERIFY", 1)[0]
        prior = []
        for node in ast.walk(ast.parse(cls.code)):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "marker":
                prior.extend(ast.literal_eval(node.iter))
        cls.lines = ["WATCH_UI_STRESS_TYPE=accessibility5", "WATCH_UI_STANDARD_TYPE=large", *prior,
                     case_line("WidgetTapJourneyTests", "testFreshConfiguredFaceIsActiveBeforeActualLauncherTap"),
                     case_line("PickerReturnJourneyTests", "testNetworkFailureGuidanceRetainsChoicesAndRecoversSelection"),
                     *(case_line(*case) for case in CASES),
                     case_line("PickerSelectedStateJourneyTests", "testSelectedGameIsMarkedInPickerAndCanChange"),
                     case_line("PickerSelectedStateJourneyTests", "testSelectedGameIsMarkedAtAccessibilitySize")]

    def verify(self, lines):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tests.log"
            path.write_text("\n".join(lines) + "\n")
            return subprocess.run([sys.executable, "-c", self.code, str(path)], capture_output=True, text=True)

    def test_every_rectangular_fixture_route_is_reachable(self):
        tests = (ROOT / "ios/Bain Luck/BainLuckWatchUITests/ComplicationContentJourneyTests.swift").read_text()
        tests = tests.split("func testRectangularTypedNamedValuesFitWithMonochromeRendering()", 1)[1].split(
            "func testSavedCircularNamedProbabilityFinalAndScoreLayout()", 1)[0]
        routes = (ROOT / "ios/Bain Luck/BainLuckWatch Watch App/WatchTabView.swift").read_text()
        scenarios = set(re.findall(r'\("([a-z-]+)", "', tests))
        for loop in re.findall(r'for scenario in \[(.*?)\]', tests, re.S):
            scenarios.update(re.findall(r'"([a-z-]+)"', loop))
        self.assertTrue(scenarios)
        for scenario in scenarios:
            self.assertIn(f'"rectangular-{scenario}"', routes)

    def test_complete_rendering_evidence_passes(self):
        result = self.verify(self.lines)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_marker_and_executed_case_is_required(self):
        for line in [*NETWORK_FREE_MARKERS, case_line("PickerReturnJourneyTests", "testNetworkFailureGuidanceRetainsChoicesAndRecoversSelection"),
                     *(case_line(*case) for case in CASES),
                     case_line("PickerSelectedStateJourneyTests", "testSelectedGameIsMarkedInPickerAndCanChange"),
                     case_line("PickerSelectedStateJourneyTests", "testSelectedGameIsMarkedAtAccessibilitySize")]:
            with self.subTest(missing=line):
                result = self.verify([item for item in self.lines if item != line])
                self.assertEqual(result.returncode, 1)

    def test_failed_skipped_or_started_cases_are_not_paid_by_markers(self):
        for case in CASES:
            for verdict in ["failed", "skipped", "started"]:
                with self.subTest(case=case, verdict=verdict):
                    self.assertEqual(self.verify([case_line(*case, verdict) if item == case_line(*case)
                                                 else item for item in self.lines]).returncode, 1)

    def test_partial_and_prefixed_markers_and_prior_gates_remain_unpaid(self):
        for marker in NETWORK_FREE_MARKERS:
            for substitute in ["prefix " + marker, marker[:-1], marker + " synthesized"]:
                with self.subTest(marker=marker, substitute=substitute):
                    self.assertEqual(self.verify([substitute if item == marker else item
                                                 for item in self.lines]).returncode, 1)
        for missing in ["WATCH_UI_STRESS_TYPE=accessibility5", "WATCH_UI_FRESH_FACE_ACTIVATION=PASS",
                        case_line("WidgetTapJourneyTests", "testFreshConfiguredFaceIsActiveBeforeActualLauncherTap")]:
            self.assertEqual(self.verify([item for item in self.lines if item != missing]).returncode, 1)


if __name__ == "__main__":
    unittest.main()
