"""1.0.3 selected-game product boundary and real launcher acceptance stay coupled."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = "ios/Bain Luck/BainLuckWatch Watch App/"
UI = "ios/Bain Luck/BainLuckWatchUITests/"
SPEC = importlib.util.spec_from_file_location(
    "scope_shards", ROOT / "tools/watch_ui_shards.py"
)
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)
LABEL = "Open your selected game in Bain Luck, or choose a game"
LAUNCHERS = (
    (
        "WidgetTapJourneyTests",
        "testActualCornerLauncherAndTap",
        "WATCH_UI_ACTUAL_CORNER_LAUNCHER=PASS",
    ),
    (
        "WidgetTapJourneyTests",
        "testActualCircularLauncherAndTap",
        "WATCH_UI_ACTUAL_CIRCULAR_LAUNCHER=PASS",
    ),
    (
        "RectangularWidgetHostJourneyTests",
        "testActualRectangularLauncherAndTap",
        "WATCH_UI_ACTUAL_RECTANGULAR_LAUNCHER=PASS",
    ),
)


def require_product(view, content, widget):
    for removed in ("showingDiscoveries", "WatchDiscoverView(", 'Text("Discoveries")'):
        assert removed not in view
    for retained in (
        "WatchDiscoverGameTransport()",
        "await store.runForegroundRefresh()",
        "await picker.refresh()",
        "store.clearSelection()",
        "GameContinuation.configure(activity, eventID: id)",
        "guard WatchLaunchRoute.accepts(url)",
        'scroll.scrollTo("watch.game.top", anchor: .top)',
        "Your selection is retained. Refresh to try again.",
    ):
        assert retained in view
    assert content.count(LABEL) == 3
    for identifier in (
        "watch.complication.fallback",
        "watch.complication.circular.fallback",
        "watch.complication.corner.fallback",
    ):
        assert f'.accessibilityIdentifier("{identifier}")' in content
    for numerical in (
        "if let snapshot",
        "snapshot.",
        "TimelineView",
        "ProgressView",
        "score-columns",
        "homeProbability",
        "observationAge",
        "corner.reading",
        "circular.reading",
    ):
        assert numerical not in content
    assert widget.count("BainLuckEntry(date: Date(), snapshot: nil)") == 2
    assert "else if family == .accessoryCorner" in widget
    assert "WatchComplicationSnapshot.read" not in widget
    assert 'let kind = "BainLuckComplication"' in widget
    assert ".widgetURL(WatchLaunchRoute.url)" in widget
    assert (
        ".supportedFamilies([.accessoryCircular, .accessoryRectangular, .accessoryCorner])"
        in widget
    )
    assert LABEL in widget


class SelectedGameScopeTests(unittest.TestCase):
    def test_reduced_surface_keeps_selected_game_and_installed_widget_identity(self):
        require_product(
            *[
                (ROOT / (APP + name)).read_text()
                for name in (
                    "WatchSelectedGameView.swift",
                    "WatchSavedComplicationContent.swift",
                    "BainLuckComplication.swift",
                )
            ]
        )

    def test_product_boundary_rejects_returning_features_or_lost_routes(self):
        sources = [
            (ROOT / (APP + name)).read_text()
            for name in (
                "WatchSelectedGameView.swift",
                "WatchSavedComplicationContent.swift",
                "BainLuckComplication.swift",
            )
        ]
        for index, old, new in (
            (0, "WatchDiscoverGameTransport()", "REMOVED"),
            (0, "await store.runForegroundRefresh()", "REMOVED"),
            (0, "GameContinuation.configure(activity, eventID: id)", "REMOVED"),
            (0, "guard WatchLaunchRoute.accepts(url)", "REMOVED"),
            (
                0,
                "struct WatchSelectedGameView",
                "// showingDiscoveries\nstruct WatchSelectedGameView",
            ),
            (1, "var body: some View {", "var body: some View { if let snapshot {"),
            (1, LABEL, "64%"),
            (2, "snapshot: nil", "snapshot: saved"),
            (2, ".widgetURL(WatchLaunchRoute.url)", ""),
            (2, ".accessoryCorner", ".accessoryInline"),
            (2, 'let kind = "BainLuckComplication"', 'let kind = "NewKind"'),
        ):
            with self.subTest(index=index, old=old):
                altered = sources.copy()
                self.assertIn(old, altered[index])
                altered[index] = altered[index].replace(old, new, 1)
                with self.assertRaises(AssertionError):
                    require_product(*altered)

    def test_exact_scope_accounts_for_every_original_identity(self):
        groups = SHARDS.manifest()
        scope = json.loads((ROOT / "tools/watch_ui_scope_1_0_3.json").read_text())
        self.assertEqual(len(scope["rows"]), 137)
        self.assertEqual(sum(r["disposition"] == "retained" for r in scope["rows"]), 98)
        self.assertEqual(
            sum(
                r["disposition"] == "replaced_for_removed_display"
                for r in scope["rows"]
            ),
            3,
        )
        self.assertEqual(sum(r["disposition"] == "deferred" for r in scope["rows"]), 36)
        self.assertEqual(
            {k: len(v) for k, v in groups.items()},
            dict(corner=1, readings=11, navigation=39, controls=33, widgets=17),
        )
        self.assertEqual(
            sum(
                c.startswith("PickerCurrentGameJourneyTests/")
                for g in groups.values()
                for c in g
            ),
            75,
        )

    def test_case_removal_mapping_substitution_or_group_move_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tools").mkdir()
            shutil.copytree(ROOT / UI, root / UI)
            original_groups = (ROOT / "tools/watch_ui_cases.json").read_text()
            original_scope = (ROOT / "tools/watch_ui_scope_1_0_3.json").read_text()
            for mutation in ("missing", "duplicate", "swap", "mapping", "restored"):
                groups = json.loads(original_groups)
                scope = json.loads(original_scope)
                if mutation == "missing":
                    groups["readings"].pop()
                if mutation == "duplicate":
                    groups["readings"].append(groups["readings"][0])
                if mutation == "swap":
                    groups["readings"][0], groups["widgets"][0] = (
                        groups["widgets"][0],
                        groups["readings"][0],
                    )
                if mutation == "mapping":
                    scope["rows"][1]["old_case"] = "InventedTests/testInvented"
                if mutation == "restored":
                    (root / UI / "WatchDiscoverJourneyTests.swift").write_text(
                        "func testRestoredDiscoveries() {}"
                    )
                (root / "tools/watch_ui_cases.json").write_text(json.dumps(groups))
                (root / "tools/watch_ui_scope_1_0_3.json").write_text(json.dumps(scope))
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    SHARDS.manifest(root)

    def test_all_actual_host_launchers_require_one_marker_and_one_pass(self):
        script = (ROOT / "tools/watch-ui-journey.sh").read_text()
        code = script.split("<<'PYCORNER'\n", 1)[1].split("\nPYCORNER", 1)[0]
        lines = [
            (
                marker,
                f"Test Case '-[BainLuckWatchUITests.{suite} {case}]' passed (90.0 seconds).",
            )
            for suite, case, marker in LAUNCHERS
        ]
        good = "\n".join(item for pair in lines for item in pair)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tests.log"

            def gate(log):
                path.write_text(log)
                return subprocess.run(
                    [sys.executable, "-c", code, str(path)], capture_output=True
                ).returncode

            self.assertEqual(gate(good), 0)
            for marker, case in lines:
                for old, new in (
                    (marker, ""),
                    (marker, marker + "\n" + marker),
                    (marker, "quoted " + marker),
                    (case, ""),
                    (case, case + "\n" + case),
                    (case, case.replace("passed", "failed")),
                    (case, case.replace("passed", "skipped")),
                    (case, case.replace("LauncherAndTap", "SavedReadingAndTap")),
                ):
                    with self.subTest(old=old, new=new):
                        self.assertEqual(gate(good.replace(old, new)), 1)


if __name__ == "__main__":
    unittest.main()
