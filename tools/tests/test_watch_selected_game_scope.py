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
    # A newer reading the card fetched goes to its own store, and the face is asked to draw it.
    "let shown = await WatchYourGameRefresh.reading(saved: saved, now: now, keep: { kept in\n"
    "            if WatchYourGameRefresh.keep(kept, in: WatchYourGameCardReading.sharedDirectory) {\n"
    '                WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckComplication")\n'
    "            }\n"
    "        })\n"
    "        return YourGameEntry(date: max(now, shown.savedAt), snapshot: shown)",
    # One reading for both kinds: the newer of the app's saved file and the card's own store.
    "    static func newest(now: Date) -> WatchComplicationSnapshot? {\n"
    "        let directory = WatchYourGameCardReading.sharedDirectory\n"
    "        return WatchYourGameCardReading.newest(saved: WatchComplicationSnapshot.read(from: directory, now: now),\n"
    "                                               card: WatchYourGameCardReading.read(from: directory), now: now)",
    "return BainLuckEntry(date: now, snapshot: Self.newest(now: now))",
    "guard let saved = BainLuckProvider.newest(now: now), let window = saved.relevanceWindow,",
    "let saved = BainLuckProvider.newest(now: now)\n        // A suggestion made for an earlier choice never shows a different game.",
    "WatchSavedComplicationContent(snapshot: entry.snapshot, now: entry.date, liveAge: true)",
    ".containerBackground(.fill.tertiary, for: .widget)\n"
    "                .widgetURL(WatchLaunchRoute.url)\n        }",
    '#Preview("Your game in the Smart Stack", widget: { BainLuckYourGameWidget() },\n'
    "         relevanceProvider: { YourGameRelevanceProvider() })",
    # With the app closed only the face slot runs: mid-game it asks again soon, and a saved
    # reading past two minutes asks the card (no timeline of its own) for an entry, which fetches.
    "if let saved = current.snapshot, WatchYourGameRefresh.wantsRefresh(saved, now: current.date) {\n"
    '            WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckYourGame")\n'
    "        }\n"
    "        if let recheck = WatchYourGameRefresh.faceRecheck(current.snapshot, now: current.date) {\n"
    "            completion(Timeline(entries: entries, policy: .after(recheck)))\n"
    "            return\n"
    "        }\n"
    "        completion(Timeline(entries: entries, policy: dates.count > 1 ? .atEnd : .never))",
)
SMART_STACK_CONTENT = (
    "var liveAge: Bool = false",
    "if liveAge, let leadIn = reading.metadataLeadIn(at: now) {\n"
    "                liveMetadata(reading, leadIn: leadIn)",
    "let age = WatchRectangularReading.liveAgeFormat(observedAt: reading.observedAt)",
    'return Text("\\(leadIn)\\(.currentDate, format: age) ago")',
    ".minimumScaleFactor(0.85)\n            .truncationMode(.middle)",
    "observedClock: WatchRectangularReading.spokenClock(observedAt: reading.observedAt))",
)
SMART_STACK_PUBLISHER = (
    'WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckComplication")\n'
    "        // #12316: the Smart Stack keeps drawing the card's first entry until it is asked for a\n"
    "        // new one, so a new saved reading asks (else mid-game it shows the pregame reading).\n"
    "        // Only a reading asks: back-to-back asks are throttled, and choosing a game writes an\n"
    "        // empty file seconds before its first reading, which would spend the ask on no game.\n"
    "        if snapshot != nil {\n"
    '            WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckYourGame")\n'
    "        }\n"
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


def require_one_age_rule(snapshot, content):
    """#12316: the face and the Smart Stack card print the same whole number of minutes for the
    same reading. One rule, `wholeAge`: whole units from the reading's own time, rounded down.
    The face prints it per entry; the card hands watchOS a date offset that rounds the same way
    (the relative style it replaced rounded to the nearest minute)."""
    for pin in (
        "    static func wholeAge(observedAt: Date, now: Date) -> (count: Int, unit: AgeUnit)? {",
        "        let minutes = Int(raw) / 60\n        if minutes < 60 { return (minutes, .minute) }",
        "        SystemFormatStyle.DateOffset(to: observedAt, allowedFields: [.day, .hour, .minute],\n"
        "                                     maxFieldCount: 1, sign: .never)",
    ):
        assert pin in snapshot, pin
    assert snapshot.count("guard let age = wholeAge(observedAt: observedAt, now: now) else { return nil }") == 2, (
        "the face's words and the spoken age both come from the one rule"
    )
    for pin in (
        "let age = WatchRectangularReading.liveAgeFormat(observedAt: reading.observedAt)",
        'return Text("\\(leadIn)\\(.currentDate, format: age) ago")',
    ):
        assert pin in content, pin
    for source in (snapshot, content):
        for forbidden in ("DateReference", "style: .relative", "RelativeDateTimeFormatter", ".reference(to:"):
            assert forbidden not in source, forbidden


def require_shared_reading(refresh, publisher, store, view, widget, project):
    """#12316: the face and the Smart Stack card draw one reading. The card keeps a newer
    reading in its own store, written only by the extension; the app stays the only writer of
    its saved file, reads the card's store, and opens on the face's newer reading."""
    app_exceptions = project.split(
        'Exceptions for "BainLuckWatch Watch App" folder in "BainLuckWatch Watch App" target */ = {', 1
    )[1].split("};", 1)[0]
    assert "WatchYourGameRefresh.swift," in app_exceptions, "the card's writer stays out of the app"
    extension = project.split(
        'Exceptions for "BainLuckWatch Watch App" folder in "BainLuckComplication" target */ = {', 1
    )[1].split("};", 1)[0]
    for member in ("WatchYourGameRefresh.swift,", "WatchComplicationPublisher.swift,"):
        assert member in extension, member
    for pin in (
        "    static func keep(_ card: WatchYourGameCardReading, in directory: URL?) -> Bool {",
        "try data.write(to: directory.appendingPathComponent(WatchYourGameCardReading.filename), options: .atomic)",
        "keep: (WatchYourGameCardReading) -> Void = { _ in }) async -> WatchComplicationSnapshot {",
        "fresh.observedAt > saved.observedAt,\n"
        "              fresh.validatedRectangularReading(now: kept.fetchedAt) != nil else { return saved }\n"
        "        keep(kept)\n        return fresh",
        "let stale = saved.observedAt.addingTimeInterval(WatchRectangularReading.liveStaleThresholdSeconds + 1)",
        "return stale > now ? min(stale, regular) : regular",
    ):
        assert pin in refresh, pin
    assert refresh.count("keep(kept)") == 1
    for forbidden in ("WatchComplicationPublisher", "selected-game.json"):
        assert forbidden not in refresh, forbidden
        assert forbidden not in widget, forbidden
    for pin in (
        'static let filename = "your-game-card.json"',
        "guard let saved, let kept = card?.snapshot, kept.eventID == saved.eventID,\n"
        "              kept.observedAt > saved.observedAt,\n"
        "              kept.validatedRectangularReading(now: now) != nil else { return saved }",
    ):
        assert pin in publisher, pin
    assert "WatchYourGameCardReading.filename), options" not in publisher
    for pin in (
        "        publish(game, fetchedAt)\n        adoptNewerCardReading()\n    }",
        "while the app was away.\n        adoptNewerCardReading()\n",
        "let shown = WatchYourGameCardReading.newest(saved: saved, card: card, now: now()),",
        "        self.fetchedAt = card.fetchedAt\n        isRestoredReading = true",
    ):
        assert pin in store, pin
    adopt = store.split("private func adoptNewerCardReading() -> Bool {", 1)[1].split("\n    }\n", 1)[0]
    assert "defaults.set" not in adopt, "the app does not store the card's reading"
    # Nor publishes it: the face already draws it, and a redraw pushes the face's next check back.
    assert "publish(" not in adopt and "if adoptNewerCardReading()" not in store
    assert store.count("adoptNewerCardReading()") == 3, "declared once, called at open and on return"
    assert (
        "cardReading: { WatchYourGameCardReading.read(from: WatchYourGameCardReading.sharedDirectory) },"
        in view
    )
    for pin in (
        "return BainLuckEntry(date: now, snapshot: Self.newest(now: now))",
        "card: WatchYourGameCardReading.read(from: directory), now: now)",
        "if WatchYourGameRefresh.keep(kept, in: WatchYourGameCardReading.sharedDirectory) {\n"
        '                WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckComplication")',
    ):
        assert pin in widget, pin
    assert widget.count("BainLuckProvider.newest(now: now)") == 2, "relevance and the card"


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
            (1, "await WatchYourGameRefresh.reading(saved: saved, now: now, keep: { kept in", "saved; _ = { (kept: WatchYourGameCardReading) in"),
            (1, "if WatchYourGameRefresh.keep(kept, in: WatchYourGameCardReading.sharedDirectory) {", "if true {"),
            (1, '                WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckComplication")\n            }\n        })', "            }\n        })"),
            (1, "card: WatchYourGameCardReading.read(from: directory), now: now)", "card: nil, now: now)"),
            (1, "snapshot: Self.newest(now: now))", "snapshot: WatchComplicationSnapshot.read(from: WatchYourGameCardReading.sharedDirectory, now: now))"),
            (1, "let saved = BainLuckProvider.newest(now: now)\n", "let saved = WatchComplicationSnapshot.read(from: WatchYourGameCardReading.sharedDirectory, now: now)\n"),
            (1, "guard let saved = BainLuckProvider.newest(now: now), let window", "guard let saved = WatchComplicationSnapshot.read(from: WatchYourGameCardReading.sharedDirectory, now: now), let window"),
            (1, "liveAge: true", "liveAge: false"),
            (1, "                .widgetURL(WatchLaunchRoute.url)\n        }", "        }"),
            (1, "relevanceProvider: { YourGameRelevanceProvider() })", "relevanceEntries: { [] })"),
            (1, "\nstruct YourGameIntent", "\nnonisolated struct YourGameIntent"),
            (1, "            completion(Timeline(entries: entries, policy: .after(recheck)))\n            return\n", ""),
            (
                1,
                '            WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckYourGame")\n        }\n        if let recheck',
                "        }\n        if let recheck",
            ),
            (
                1,
                "if let saved = current.snapshot, WatchYourGameRefresh.wantsRefresh(saved, now: current.date) {",
                "if current.snapshot != nil {",
            ),
            (0, "if liveAge, let leadIn", "if false, let leadIn"),
            (0, "            .truncationMode(.middle)\n", ""),
            (0, "(.currentDate, format: age)", "(reading.observedAt, format: .dateTime)"),
            (
                0,
                "reading.accessibilityDescription(\n                    at: now, observedClock: WatchRectangularReading.spokenClock(observedAt: reading.observedAt))",
                "reading.accessibilityDescription(at: now)",
            ),
            (2, 'invalidateRelevance(ofKind: "BainLuckYourGame")', 'invalidateRelevance(ofKind: "BainLuckComplication")'),
            (2, '            WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckYourGame")\n', ""),
            (2, "        if snapshot != nil {\n            WidgetCenter", "        if true {\n            WidgetCenter"),
            (2, "sportKey: game.sportKey, status: game.status)", "sportKey: nil, status: game.status)"),
        ):
            with self.subTest(index=index, old=old):
                altered = sources.copy()
                self.assertIn(old, altered[index])
                altered[index] = altered[index].replace(old, new, 1)
                with self.assertRaises(AssertionError):
                    require_smart_stack(*altered)

    def test_face_and_card_print_the_same_whole_minutes(self):
        sources = [
            (ROOT / (APP + name)).read_text()
            for name in ("WatchComplicationSnapshot.swift", "WatchSavedComplicationContent.swift")
        ]
        require_one_age_rule(*sources)
        for index, old, new in (
            (1, "let age = WatchRectangularReading.liveAgeFormat(observedAt: reading.observedAt)",
             "let age = SystemFormatStyle.DateReference(to: reading.observedAt, allowedFields: [.day, .hour, .minute], maxFieldCount: 1)"),
            (1, "liveAgeFormat(observedAt: reading.observedAt)", "liveAgeFormat(observedAt: now)"),
            (1, "(.currentDate, format: age) ago\")", "(.currentDate, format: age)\")"),
            (0, "allowedFields: [.day, .hour, .minute],\n", "allowedFields: [.day, .hour, .minute, .second],\n"),
            (0, "maxFieldCount: 1, sign: .never)", "maxFieldCount: 2, sign: .never)"),
            (0, "        let minutes = Int(raw) / 60\n", "        let minutes = Int((raw + 30) / 60)\n"),
            (0, "        guard let age = wholeAge(observedAt: observedAt, now: now) else { return nil }\n        switch",
             "        guard let age = wholeAge(observedAt: observedAt, now: now.addingTimeInterval(30)) else { return nil }\n        switch"),
        ):
            with self.subTest(index=index, old=old):
                altered = sources.copy()
                self.assertIn(old, altered[index])
                altered[index] = altered[index].replace(old, new, 1)
                with self.assertRaises(AssertionError):
                    require_one_age_rule(*altered)

    def test_face_and_card_share_one_reading_and_each_file_keeps_one_writer(self):
        sources = [
            (ROOT / (APP + name)).read_text()
            for name in (
                "WatchYourGameRefresh.swift",
                "WatchComplicationPublisher.swift",
                "WatchSelectedGameStore.swift",
                "WatchSelectedGameView.swift",
                "BainLuckComplication.swift",
            )
        ]
        project = (ROOT / "ios/Bain Luck/Bain Luck.xcodeproj/project.pbxproj").read_text()
        require_shared_reading(*sources, project)
        app_files = {
            path.name: path.read_text()
            for path in (ROOT / APP).glob("*.swift")
            if path.name not in ("WatchYourGameRefresh.swift", "BainLuckComplication.swift")
        }
        # Only the extension writes the card's store; the app has no writer to call.
        for name, text in app_files.items():
            self.assertNotIn("WatchYourGameRefresh.keep(", text, name)
            self.assertNotIn("WatchYourGameCardReading.filename), options", text, name)
        for index, old, new in (
            (0, "    static func keep(", "    static func remember("),
            (0, "fresh.observedAt > saved.observedAt,\n              fresh.validatedRectangularReading(now: kept.fetchedAt) != nil else { return saved }\n        keep(kept)",
             "fresh.validatedRectangularReading(now: kept.fetchedAt) != nil else { return saved }\n        keep(kept)"),
            (0, "        keep(kept)\n        return fresh", "        return fresh"),
            (0, "return stale > now ? min(stale, regular) : regular", "return regular"),
            (1, "kept.observedAt > saved.observedAt,", ""),
            (1, "guard let saved, let kept = card?.snapshot, kept.eventID == saved.eventID,", "guard let saved, let kept = card?.snapshot,"),
            (1, "kept.validatedRectangularReading(now: now) != nil else { return saved }", "true else { return saved }"),
            (2, "        publish(game, fetchedAt)\n        adoptNewerCardReading()\n    }", "        publish(game, fetchedAt)\n    }"),
            (2, "        publish(game, fetchedAt)\n        adoptNewerCardReading()\n    }", "        adoptNewerCardReading()\n        publish(game, fetchedAt)\n    }"),
            (2, "while the app was away.\n        adoptNewerCardReading()\n", "while the app was away.\n"),
            (2, "while the app was away.\n        adoptNewerCardReading()\n", "while the app was away.\n        if adoptNewerCardReading() { publish(game, fetchedAt) }\n"),
            (2, "        self.fetchedAt = card.fetchedAt\n        isRestoredReading = true\n        return true",
             "        self.fetchedAt = card.fetchedAt\n        isRestoredReading = true\n        publish(self.game, self.fetchedAt)\n        return true"),
            (2, "let shown = WatchYourGameCardReading.newest(saved: saved, card: card, now: now()),", "let shown = card.snapshot,"),
            (2, "        self.fetchedAt = card.fetchedAt\n        isRestoredReading = true", "        self.fetchedAt = card.fetchedAt\n        isRestoredReading = false"),
            (3, "cardReading: { WatchYourGameCardReading.read(from: WatchYourGameCardReading.sharedDirectory) },", ""),
            (5, "\t\t\t\tWatchYourGameRefresh.swift,\n\t\t\t);\n\t\t\ttarget = A70F40102FA6C20000170BF2", "\t\t\t);\n\t\t\ttarget = A70F40102FA6C20000170BF2"),
        ):
            with self.subTest(index=index, old=old):
                altered = sources + [project]
                self.assertIn(old, altered[index])
                altered[index] = altered[index].replace(old, new, 1)
                with self.assertRaises(AssertionError):
                    require_shared_reading(*altered)

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
