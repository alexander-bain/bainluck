"""Guard #4933: large rectangular complication candidate contract, target membership, and signed App Group access."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "ios/Bain Luck/BainLuckWatch Watch App"
PBXPROJ = ROOT / "ios/Bain Luck/Bain Luck.xcodeproj/project.pbxproj"
ENTITLEMENTS = ROOT / "ios/Bain Luck/BainLuckWatchShared.entitlements"


class WatchRectangularComplication4933Tests(unittest.TestCase):
    def test_complication_target_membership_and_shared_app_group_entitlement(self):
        pbx = PBXPROJ.read_text()
        self.assertIn(
            'A7C0000000000000000000DE /* Exceptions for "BainLuckWatch Watch App" folder in "BainLuckComplication" target */',
            pbx,
        )
        exception_block = pbx.split(
            'A7C0000000000000000000DE /* Exceptions for "BainLuckWatch Watch App" folder in "BainLuckComplication" target */',
            1,
        )[1].split("};", 1)[0]
        for member in (
            "BainLuckComplication.swift",
            "WatchSavedComplicationContent.swift",
            "WatchComplicationSnapshot.swift",
            "WatchLaunchRoute.swift",
        ):
            self.assertIn(member, exception_block)
        self.assertIn("group.com.bainluck.watch", ENTITLEMENTS.read_text())

    def test_rectangular_reading_covers_probability_and_final_states_and_keeps_tap_route(self):
        snapshot = (WATCH / "WatchComplicationSnapshot.swift").read_text()
        publisher = (WATCH / "WatchComplicationPublisher.swift").read_text()
        content = (WATCH / "WatchSavedComplicationContent.swift").read_text()
        widget = (WATCH / "BainLuckComplication.swift").read_text()

        for kind in (
            "case liveForecast",
            "case scheduledForecast",
            "case finalResult",
        ):
            self.assertIn(kind, snapshot)
        for retired_kind in (
            "case liveScoreOnly",
            "case scheduledStart",
        ):
            self.assertNotIn(retired_kind, snapshot)
        self.assertIn("static let maxSingleLineHeaderCharacters = 26", snapshot)
        self.assertIn("static let maxSingleLineMetadataCharacters = 28", snapshot)
        self.assertIn("static let liveAgeThresholdSeconds: TimeInterval = 120", snapshot)
        self.assertIn('"\\(team) \\(pct)"', snapshot)
        self.assertIn('"Final · \\(homeLabel) \\(hs), \\(awayLabel) \\(ascore)"', snapshot)
        self.assertIn('"Final · \\(awayLabel) \\(ascore), \\(homeLabel) \\(hs)"', snapshot)
        self.assertIn('"Open to update"', snapshot)
        self.assertIn('"As of \\(Self.asOfClock(observedAt, timeZone: timeZone))"', snapshot)
        for forbidden in ("Saved ·", "Stale reading", "No win prob", "Past start", "Start unconfirmed"):
            self.assertNotIn(forbidden, snapshot)
            self.assertNotIn(forbidden, content)
            self.assertNotIn(forbidden, widget)
        self.assertIn("existing.rectangularReading == valid.rectangularReading", publisher)
        self.assertIn("snapshot.validatedRectangularReading(now: now)", content)
        self.assertNotIn(
            "legacyCard",
            content,
            "Odds-less snapshots must fall back to the launcher, never a Saved legacy card",
        )
        view_that_fits_block = content.split("ViewThatFits(in: [.horizontal, .vertical]) {", 1)[1].split("}", 1)[0]
        self.assertIn("readingCard(reading, preferCompact: false)", view_that_fits_block)
        self.assertIn("readingCard(reading, preferCompact: true)", view_that_fits_block)
        primary_block = content.split("Text(reading.primaryLine(preferCompact: preferCompact, at: now))", 1)[1].split("Text(reading.metadataLine(at: now))", 1)[0]
        self.assertIn(
            ".lineLimit(preferCompact ? 1 : 2)",
            primary_block,
            "Compact fallback card must cap primary line to 1 line so 41mm vertical slots never clip bottom metadata",
        )
        self.assertIn(
            ".minimumScaleFactor(0.85)",
            primary_block,
            "A slightly wide single primary line must shrink before it is cut off (lane1b P1)",
        )
        metadata_block = content.split("Text(reading.metadataLine(at: now))", 1)[1].split("}", 1)[0]
        self.assertIn(".minimumScaleFactor(0.85)", metadata_block)
        self.assertIn("WatchRectangularReading.timelineDates(for: current.snapshot, now: current.date)", widget)
        self.assertIn("BainLuckEntry(date: $0, snapshot: current.snapshot)", widget)
        self.assertIn("dates.count > 1 ? .atEnd : .never", widget)
        self.assertIn('.accessibilityIdentifier("watch.complication.fallback")', content)
        self.assertIn(".widgetURL(WatchLaunchRoute.url)", widget)


if __name__ == "__main__":
    unittest.main()
