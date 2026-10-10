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
    "WATCH_UI_RECTANGULAR_TYPED=PASS",
    "WATCH_UI_RECTANGULAR_MONOCHROME=PASS",
    "WATCH_UI_RECTANGULAR_LEGACY=PASS",
    "WATCH_UI_RECTANGULAR_ACTUAL_TYPED=PASS",
)
CASES = (
    (
        "ComplicationContentJourneyTests",
        "testRectangularTypedNamedValuesFitWithMonochromeRendering",
    ),
    (
        "ComplicationContentJourneyTests",
        "testRectangularLegacyMismatchUnknownAndEmptyStayHonest",
    ),
    (
        "RectangularWidgetHostJourneyTests",
        "testActualRectangularWidgetShowsPublishedSavedReading",
    ),
)


def rectangular_scenarios(tests):
    # Identity variants are environment values on rectangular-long, not routes.
    # Keep literal launch routes even inside that matrix so reachability stays guarded.
    route_cases = re.sub(
        r"for \(identity, requiredBranch, requiredWidth\) in \[.*?\]\s*\{",
        "",
        tests,
        flags=re.S,
    )
    scenarios = set(re.findall(r'\("([a-z-]+)", "', route_cases))
    for loop in re.findall(r"for scenario in \[(.*?)\]", route_cases, re.S):
        scenarios.update(re.findall(r'"([a-z-]+)"', loop))
    scenarios.update(re.findall(r'launchRectangular\("([a-z-]+)"', tests))
    return scenarios


def case_line(suite, case, result="passed"):
    return (
        f"Test Case '-[BainLuckWatchUITests.{suite} {case}]' {result} (20.123 seconds)."
    )


class RectangularReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = (
            (ROOT / "tools/watch-ui-journey.sh")
            .read_text()
            .split("<<'PYVERIFY'\n", 1)[1]
            .split("\nPYVERIFY", 1)[0]
        )
        prior = []
        for node in ast.walk(ast.parse(cls.code)):
            if (
                isinstance(node, ast.For)
                and isinstance(node.target, ast.Name)
                and node.target.id == "marker"
            ):
                prior.extend(ast.literal_eval(node.iter))
        cls.lines = [
            "WATCH_UI_STRESS_TYPE=accessibility5",
            "WATCH_UI_STANDARD_TYPE=large",
            *prior,
            case_line(
                "WidgetTapJourneyTests",
                "testFreshConfiguredFaceIsActiveBeforeActualLauncherTap",
            ),
            case_line(
                "PickerReturnJourneyTests",
                "testNetworkFailureGuidanceRetainsChoicesAndRecoversSelection",
            ),
            *(case_line(*case) for case in CASES),
            case_line(
                "SelectedGameUpdatingJourneyTests",
                "testUpdatingIsVisibleUntilRequestFinishes",
            ),
            case_line(
                "SelectedGameUpdatingJourneyTests",
                "testUpdatingIsVisibleAtAccessibilitySize",
            ),
            case_line(
                "PickerSelectedStateJourneyTests",
                "testSelectedGameIsMarkedInPickerAndCanChange",
            ),
            case_line(
                "PickerSelectedStateJourneyTests",
                "testSelectedGameIsMarkedAtAccessibilitySize",
            ),
        ]

    def verify(self, lines):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tests.log"
            path.write_text("\n".join(lines) + "\n")
            return subprocess.run(
                [sys.executable, "-c", self.code, str(path)],
                capture_output=True,
                text=True,
            )

    def test_every_rectangular_fixture_route_is_reachable(self):
        tests = (
            ROOT
            / "ios/Bain Luck/BainLuckWatchUITests/ComplicationContentJourneyTests.swift"
        ).read_text()
        tests = tests.split(
            "func testRectangularTypedNamedValuesFitWithMonochromeRendering()", 1
        )[1].split("func testSavedCircularNamedProbabilityFinalAndScoreLayout()", 1)[0]
        routes = (
            ROOT / "ios/Bain Luck/BainLuckWatch Watch App/WatchTabView.swift"
        ).read_text()
        scenarios = rectangular_scenarios(tests)
        self.assertTrue(scenarios)
        for scenario in scenarios:
            self.assertIn(f'"rectangular-{scenario}"', routes)

    def test_identity_variants_are_not_routes_but_their_launch_route_is_retained(self):
        fixture = """for (identity, requiredBranch, requiredWidth) in [
            ("provided", "watch.complication.rectangular.opponent", CGFloat(156)),
            ("missing", "watch.complication.rectangular.compact", CGFloat(156)),
            ("invalid", "watch.complication.rectangular.compact", CGFloat(156)),
            ("wide-opponent", "compact-or-launcher", CGFloat(100))
        ] {
            launchRectangular("long", monochrome: false, awayIdentity: identity, in: app)
        }"""
        self.assertEqual(rectangular_scenarios(fixture), {"long"})
        # A changed literal launch route must still be checked against WatchTabView.
        self.assertEqual(
            rectangular_scenarios(fixture.replace('"long"', '"unrouted"')),
            {"unrouted"},
        )

    def test_compact_score_fallback_keeps_both_full_team_score_associations(self):
        source = (
            ROOT
            / "ios/Bain Luck/BainLuckWatch Watch App/WatchSavedComplicationContent.swift"
        ).read_text()
        compact = source.split("private func compactReading(", 1)[1].split(
            "private func metadata(", 1
        )[0]
        self.assertIn(
            ".accessibilityLabel(namedAccessibilityReading(snapshot, reading: reading))",
            compact,
        )
        self.assertNotIn(".accessibilityLabel(accessibilityReading(snapshot))", compact)
        named = source.split("private func namedAccessibilityReading(", 1)[1].split(
            "private func compactOpponentReading(", 1
        )[0]
        # The full-name helper must keep actual association and tie/provenance truth.
        for required in (
            "namedScoreTeam(reading, home: false)",
            "namedScoreTeam(reading, home: true)",
            "score \\(awayScore)",
            "score \\(homeScore)",
            '"Final tie"',
            "snapshot.observedAt",
            "return accessibilityReading(snapshot)",
        ):
            self.assertIn(required, named)

    def test_circular_score_parent_keeps_full_names_and_associated_scores(self):
        source = (
            ROOT
            / "ios/Bain Luck/BainLuckWatch Watch App/WatchSavedComplicationContent.swift"
        ).read_text()
        circular = source.split(
            "struct WatchSavedCircularComplicationContent: View", 1
        )[1].split("struct WatchSavedCornerComplicationContent: View", 1)[0]
        self.assertIn(
            ".accessibilityLabel(circularAccessibilityReading(snapshot, reading: reading))",
            circular,
        )
        helper = circular.split("private func circularAccessibilityReading(", 1)[
            1
        ].split("private var launcher:", 1)[0]
        for required in (
            "reading.awayName",
            "reading.homeName",
            "awayScore > homeScore",
            "homeScore > awayScore",
            "awayScore == homeScore",
            '"Final tie"',
            r"score \(awayScore)",
            r"score \(homeScore)",
            "snapshot.observedAt",
            "reading.kind != .forecast",
            "snapshot.title",
            "snapshot.detail",
        ):
            self.assertIn(required, helper)
        self.assertIn(
            r'.accessibilityValue("Saved · \(reading.subject) · \(reading.value)")',
            circular,
        )

    def test_named_forecast_wraps_full_title_beside_30pt_value_without_truncation(self):
        source = (
            ROOT
            / "ios/Bain Luck/BainLuckWatch Watch App/WatchSavedComplicationContent.swift"
        ).read_text()
        named = source.split("private func namedReading(", 1)[1].split(
            "private func namedScoreRow(", 1
        )[0]
        forecast = named.split("} else {", 1)[1].split(
            "metadata(snapshot, reading: reading)", 1
        )[0]
        # A–C v2 proposes a fixed 12pt full title beside the unchanged 30pt
        # value. Root reviews this explicit replacement of the own-row/14pt
        # contract; native slot/readability assertions remain independent.
        self.assertIn("HStack(alignment: .center, spacing: 6)", forecast)
        self.assertLess(
            forecast.index("Text(snapshot.title)"),
            forecast.index("Text(prominentValue(reading))"),
        )
        self.assertIn("size: 12, weight: .semibold", forecast)
        self.assertIn("size: 30, weight: .bold, design: .rounded", forecast)
        self.assertIn(".fixedSize(horizontal: false, vertical: true)", forecast)
        self.assertNotIn(".lineLimit", forecast)
        self.assertNotIn(".minimumScaleFactor", forecast)
        self.assertEqual(named.count("metadata(snapshot, reading: reading)"), 1)

    def test_full_name_score_columns_keep_intrinsic_headers_and_score_baselines(self):
        source = (
            ROOT
            / "ios/Bain Luck/BainLuckWatch Watch App/WatchSavedComplicationContent.swift"
        ).read_text()
        body = source.split("private func namedScoreColumns(", 1)[0]
        self.assertLess(
            body.index("namedScoreColumns(snapshot"),
            body.index("namedReading(snapshot"),
        )
        columns = source.split("private func namedScoreColumns(", 1)[1].split(
            "private func namedReading(", 1
        )[0]
        for required in (
            "GridRow(alignment: .top)",
            "GridRow(alignment: .firstTextBaseline)",
            "namedScoreTeam(reading, home: false)",
            "namedScoreTeam(reading, home: true)",
            "Text(String(awayScore))",
            "Text(String(homeScore))",
            "size: 22",
            "stateLabel: reading.kind == .final && awayScore == homeScore",
            '"Final tie"',
            "namedAccessibilityReading(snapshot, reading: reading)",
        ):
            self.assertIn(required, columns)
        for forbidden in (".lineLimit", ".minimumScaleFactor", "height:"):
            self.assertNotIn(forbidden, columns)
        self.assertIn("namedReading(snapshot", body)
        self.assertIn("compactScoreColumns(snapshot", body)
        self.assertIn("compactReading(snapshot", body)
        self.assertIn("savedLauncher(snapshot)", body)

    def test_complete_rendering_evidence_passes(self):
        result = self.verify(self.lines)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_marker_and_executed_case_is_required(self):
        for line in [
            *NETWORK_FREE_MARKERS,
            case_line(
                "PickerReturnJourneyTests",
                "testNetworkFailureGuidanceRetainsChoicesAndRecoversSelection",
            ),
            *(case_line(*case) for case in CASES),
            case_line(
                "PickerSelectedStateJourneyTests",
                "testSelectedGameIsMarkedInPickerAndCanChange",
            ),
            case_line(
                "PickerSelectedStateJourneyTests",
                "testSelectedGameIsMarkedAtAccessibilitySize",
            ),
        ]:
            with self.subTest(missing=line):
                result = self.verify([item for item in self.lines if item != line])
                self.assertEqual(result.returncode, 1)

    def test_failed_skipped_or_started_cases_are_not_paid_by_markers(self):
        for case in CASES:
            for verdict in ["failed", "skipped", "started"]:
                with self.subTest(case=case, verdict=verdict):
                    self.assertEqual(
                        self.verify(
                            [
                                (
                                    case_line(*case, verdict)
                                    if item == case_line(*case)
                                    else item
                                )
                                for item in self.lines
                            ]
                        ).returncode,
                        1,
                    )

    def test_partial_and_prefixed_markers_and_prior_gates_remain_unpaid(self):
        for marker in NETWORK_FREE_MARKERS:
            for substitute in [
                "prefix " + marker,
                marker[:-1],
                marker + " synthesized",
            ]:
                with self.subTest(marker=marker, substitute=substitute):
                    self.assertEqual(
                        self.verify(
                            [
                                substitute if item == marker else item
                                for item in self.lines
                            ]
                        ).returncode,
                        1,
                    )
        for missing in [
            "WATCH_UI_STRESS_TYPE=accessibility5",
            "WATCH_UI_FRESH_FACE_ACTIVATION=PASS",
            case_line(
                "WidgetTapJourneyTests",
                "testFreshConfiguredFaceIsActiveBeforeActualLauncherTap",
            ),
        ]:
            self.assertEqual(
                self.verify(
                    [item for item in self.lines if item != missing]
                ).returncode,
                1,
            )


if __name__ == "__main__":
    unittest.main()
