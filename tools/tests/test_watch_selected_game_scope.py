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

# #12316: the followed game's Smart Stack card. The bundle keeps the installed face kind and
# adds a relevance-only kind; the card reuses the face reading with an age that keeps counting.
SMART_STACK_WIDGET = (
    "@main\nstruct BainLuckWidgets: WidgetBundle {\n    var body: some Widget {\n"
    "        BainLuckWidget()\n        BainLuckYourGameWidget()\n    }\n}",
    'let kind = "BainLuckYourGame"',
    "RelevanceConfiguration(kind: kind, provider: YourGameRelevanceProvider())",
    '.description("Your chosen game on game day, with its saved reading and its age.")\n'
    "        // The Smart Stack draws rectangular cards; the reading is laid out for no other size.\n"
    "        .supportedFamilies([.accessoryRectangular])",
    "WidgetRelevanceAttribute(configuration: YourGameIntent(eventID: saved.eventID),",
    # .scheduled reads as a calendar event: the Smart Stack drops the card at the start.
    "context: .date(interval: window, kind: .informational)",
    "window.end > now else { return WidgetRelevance([]) }",
    "guard let saved, saved.eventID == configuration.eventID else {\n"
    "            return YourGameEntry(date: now, snapshot: nil)",
    "guard !context.isPreview else { return YourGameEntry(date: now, snapshot: saved) }",
    "let shown = await WatchYourGameRefresh.reading(saved: saved, now: now)\n"
    "        return YourGameEntry(date: max(now, shown.savedAt), snapshot: shown)",
    "WatchSavedComplicationContent(snapshot: entry.snapshot, now: entry.date, liveAge: true)",
    ".containerBackground(.fill.tertiary, for: .widget)\n"
    "                .widgetURL(WatchLaunchRoute.url)\n        }",
    '#Preview("Your game in the Smart Stack", widget: { BainLuckYourGameWidget() },\n'
    "         relevanceProvider: { YourGameRelevanceProvider() })",
)
SMART_STACK_CONTENT = (
    "var liveAge: Bool = false",
    "if liveAge, let leadIn = reading.metadataLeadIn(at: now) {\n"
    "                liveMetadata(reading, leadIn: leadIn)",
    'return Text("\\(leadIn)\\(.currentDate, format: age)")',
    ".minimumScaleFactor(0.85)\n            .truncationMode(.middle)",
    "observedClock: WatchRectangularReading.spokenClock(observedAt: reading.observedAt))",
)
SMART_STACK_PUBLISHER = (
    'WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckComplication")\n'
    "        // #12316: the Smart Stack keeps drawing the card's first entry until it is asked for a\n"
    "        // new one, so a new saved reading asks (else mid-game it shows the pregame reading).\n"
    '        WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckYourGame")\n'
    "        // #12316: the game-day window may have moved, so the Smart Stack asks again.\n"
    "        if #available(iOS 18.0, macOS 15.0, watchOS 11.0, *) {\n"
    '            WidgetCenter.shared.invalidateRelevance(ofKind: "BainLuckYourGame")',
    "commenceTime: game.commenceTime, sportKey: game.sportKey, status: game.status)",
)


def require_smart_stack(content, widget, publisher):
    for pin in SMART_STACK_WIDGET:
        assert pin in widget, pin
    assert widget.count("@main") == 1
    # A nonisolated intent cannot hold an @Parameter (a warning today, an error in Swift 6).
    assert "\nstruct YourGameIntent: WidgetConfigurationIntent {" in widget
    for pin in SMART_STACK_CONTENT:
        assert pin in content, pin
    for pin in SMART_STACK_PUBLISHER:
        assert pin in publisher, pin


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
    for retained_rectangular in (
        "snapshot.validatedRectangularReading(now: now)",
        "watch.complication.rectangular.reading",
        "watch.complication.rectangular.header",
        "watch.complication.rectangular.primary",
        "watch.complication.rectangular.metadata",
    ):
        assert retained_rectangular in content
    for circular_corner_numerical in (
        "TimelineView",
        "ProgressView",
        "corner.reading",
        "circular.reading",
    ):
        assert circular_corner_numerical not in content
    assert "BainLuckEntry(date: Date(), snapshot: nil)" in widget
    assert "WatchComplicationSnapshot.read(from: directory, now: now)" in widget
    assert "else if family == .accessoryCorner" in widget
    assert 'let kind = "BainLuckComplication"' in widget
    # The face view's own tap route; the #12316 Smart Stack card carries a second one.
    assert (
        ".widgetURL(WatchLaunchRoute.url)\n    }\n    private var accessibilityDescription"
        in widget
    )
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
            (1, "snapshot.validatedRectangularReading(now: now)", "REMOVED"),
            (1, LABEL, "64%"),
            (2, "WatchComplicationSnapshot.read(from: directory, now: now)", "REMOVED"),
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

    def test_smart_stack_card_keeps_face_kind_relevance_window_and_counting_age(self):
        sources = [
            (ROOT / (APP + name)).read_text()
            for name in (
                "WatchSavedComplicationContent.swift",
                "BainLuckComplication.swift",
                "WatchComplicationPublisher.swift",
            )
        ]
        require_smart_stack(*sources)
        for index, old, new in (
            (1, "        BainLuckYourGameWidget()\n    }", "    }"),
            (1, "        BainLuckWidget()\n", ""),
            (1, 'let kind = "BainLuckYourGame"', 'let kind = "BainLuckComplication"'),
            (1, "kind: .informational)", "kind: .scheduled)"),
            (1, "        .supportedFamilies([.accessoryRectangular])\n", ""),
            (1, "window.end > now else", "true else"),
            (1, "guard let saved, saved.eventID == configuration.eventID else", "guard let saved else"),
            (1, "await WatchYourGameRefresh.reading(saved: saved, now: now)", "saved"),
            (1, "liveAge: true", "liveAge: false"),
            (1, "                .widgetURL(WatchLaunchRoute.url)\n        }", "        }"),
            (1, "relevanceProvider: { YourGameRelevanceProvider() })", "relevanceEntries: { [] })"),
            (1, "\nstruct YourGameIntent", "\nnonisolated struct YourGameIntent"),
            (0, "if liveAge, let leadIn", "if false, let leadIn"),
            (0, "            .truncationMode(.middle)\n", ""),
            (0, "(.currentDate, format: age)", "(reading.observedAt, format: .dateTime)"),
            (
                0,
                "reading.accessibilityDescription(\n                    at: now, observedClock: WatchRectangularReading.spokenClock(observedAt: reading.observedAt))",
                "reading.accessibilityDescription(at: now)",
            ),
            (2, 'invalidateRelevance(ofKind: "BainLuckYourGame")', 'invalidateRelevance(ofKind: "BainLuckComplication")'),
            (2, '        WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckYourGame")\n', ""),
            (2, "sportKey: game.sportKey, status: game.status)", "sportKey: nil, status: game.status)"),
        ):
            with self.subTest(index=index, old=old):
                altered = sources.copy()
                self.assertIn(old, altered[index])
                altered[index] = altered[index].replace(old, new, 1)
                with self.assertRaises(AssertionError):
                    require_smart_stack(*altered)

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
