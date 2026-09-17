import XCTest
@testable import Bain_Luck

/// #6718 — **a period marker sits on a time the feed actually observed.**
///
/// `OddsChartView.extractPeriodMarkers` used to invent one. If the feed opened
/// in Q2, it inferred the missing "Q1" from the labels present and inserted it
/// at `gameStartDate` — which is `commenceTime`, the **scheduled** kickoff:
///
/// ```swift
/// if isGameStarted, let startDate = gameStartDate, !firstSeen.isEmpty {
///     let firstPeriodLabel = inferFirstPeriodLabel(from: firstSeen.map(\.label))
///     if let firstPeriodLabel, !seenLabels.contains(firstPeriodLabel) {
///         firstSeen.insert((firstPeriodLabel, startDate), at: 0)
///     }
/// }
/// ```
///
/// That is two unevidenced claims in one marker: that the period happened at
/// all, and that it began when the fixture was *listed* to begin. A game that
/// starts late — weather, an overrunning preceding fixture, a broadcast window
/// — got a labelled boundary minutes or hours away from anything anybody saw,
/// drawn in the same ink as the boundaries we did observe. The reader has no
/// way to tell the two apart.
///
/// Alex, 2026-09-14: *"align meaningful sport-specific state markers to
/// evidenced times"* and *"scheduled kickoff/capture timestamps are not
/// automatically actual start/finish."*
///
/// ## Why this file is scans plus a control, and not a call
///
/// `extractPeriodMarkers` is `private` on a SwiftUI `View` and returns a
/// `private struct PeriodMarker`, so no unit test can call it or name its
/// result. The removal is therefore pinned two ways: the source no longer
/// reaches for the scheduled start while assembling markers (the scans), and
/// the rule that was removed is reproduced verbatim so the defect stays
/// provable against a control rather than argued from a diff (ruling 067).
///
/// ## The sibling was already right
///
/// `ScoreDifferentialChartView.extractScoreDiffPeriodMarkers` — the other chart
/// on the same event page — has always taken every marker date from an observed
/// `timestamp`, using the scheduled start only as a filter floor. This change
/// makes the two charts agree, which is the same drift `PeriodLabel` (#1831)
/// exists to prevent.
///
/// The server states the rule on its own side as of live's half of #6718: a
/// `boundary_observed` marker always carries a `not_before` lower bound, and a
/// transition the feed never bracketed is omitted rather than pinned to
/// kickoff. Absent beats invented on both sides of the wire.
final class AChartMarkerSitsOnAnObservedTime6718Tests: XCTestCase {

    // MARK: - The scheduled start is not a marker position

    func testMarkerAssemblyNeverReachesForTheScheduledStart() throws {
        let body = try markerAssemblyBody()

        XCTAssertFalse(
            body.contains("gameStartDate"),
            """
            `extractPeriodMarkers` consults the SCHEDULED commence time again. Every marker it \
            emits must come from an observed reading; `gameStartDate` is `commenceTime?.asDate` \
            and is evidence of nothing that happened. This scan is scoped to the function body \
            on purpose — the same property is legitimate elsewhere in the file, where it CLIPS \
            data to the game window rather than placing a label.
            """
        )
        XCTAssertFalse(
            body.contains("firstSeen.insert("),
            """
            A marker is being inserted ahead of the observed ones. That is the exact mechanism \
            of #6718: everything else in this function APPENDS what it read from the feed.
            """
        )
    }

    /// The helper existed only to answer "which period is missing from the
    /// front of this list" so one could be manufactured. Nothing should ask.
    func testTheInferenceHelperIsGoneFromTheWholeFile() throws {
        let source = try code(at: Self.oddsChartView)

        XCTAssertFalse(
            source.contains("inferFirstPeriodLabel"),
            "the first-period inference is back; #6718 is back with it"
        )
    }

    // MARK: - …and the markers we DO draw are still drawn
    //
    // Without these, deleting `extractPeriodMarkers` outright would satisfy
    // every assertion above. A guard that only forbids must also require.

    func testTheObservedSourcesAreStillRead() throws {
        let body = try markerAssemblyBody()

        XCTAssertTrue(
            body.contains("espnHistory"),
            "ESPN history is the primary source of observed period boundaries")
        XCTAssertTrue(
            body.contains("winProbHistory"),
            "win_prob history game_state supplements periods ESPN did not carry")
        XCTAssertTrue(
            body.contains("HalvesFromGap.markers"),
            """
            The half-time inference stays. It is not the same class as the deleted rule: it \
            derives from an observed PAUSE between real readings (#3317), so the times it \
            produces are times the feed saw.
            """
        )
    }

    // MARK: - The shipped behaviour, pinned

    /// Verbatim reference copy of the removed `inferFirstPeriodLabel(from:)`.
    ///
    /// Kept as a literal rather than a call into production code: a control that
    /// shares an implementation with its subject stops being a control the
    /// moment the subject changes — and here the subject no longer exists.
    private struct LegacyFirstPeriodInference {
        func firstPeriodLabel(from labels: [String]) -> String? {
            guard let first = labels.first else { return nil }
            if first.hasPrefix("Q") && first != "Q1" { return "Q1" }
            if first.hasPrefix("P") && first != "P1" { return "P1" }
            if first.hasSuffix("H") && first != "1H" { return "1H" }
            if let num = Int(first), num > 1 { return "1" }
            return nil
        }
    }

    func testTheLegacyRuleManufacturedAPeriodFromEveryShapeOfFeed() {
        let legacy = LegacyFirstPeriodInference()

        XCTAssertEqual(legacy.firstPeriodLabel(from: ["Q2", "Q3", "Q4"]), "Q1",
                       "football/basketball: a feed opening in Q2 grew a Q1")
        XCTAssertEqual(legacy.firstPeriodLabel(from: ["P2", "P3"]), "P1",
                       "hockey: a feed opening in P2 grew a P1")
        XCTAssertEqual(legacy.firstPeriodLabel(from: ["2H"]), "1H",
                       "halves: a feed opening in the second half grew a first")
        XCTAssertEqual(legacy.firstPeriodLabel(from: ["3"]), "1",
                       "baseball: a feed opening in the 3rd grew a 1st")

        // The one case it declined, which is why the defect was invisible on
        // any game we happened to watch from the opening whistle.
        XCTAssertNil(legacy.firstPeriodLabel(from: ["Q1", "Q2"]),
                     "a complete feed was left alone — so this only ever hit late-attached games")
    }

    /// The consequence, in the units the reader sees: the manufactured marker
    /// was placed at the scheduled start, however far that was from anything
    /// observed. This is what "not automatically actual start" costs.
    func testTheManufacturedMarkerLandedWhereNothingWasObserved() {
        let legacy = LegacyFirstPeriodInference()
        let scheduledKickoff = Date(timeIntervalSince1970: 1_757_700_000)
        let firstObservedReading = scheduledKickoff.addingTimeInterval(47 * 60)

        let manufactured = legacy.firstPeriodLabel(from: ["Q2", "Q3"])
        XCTAssertEqual(manufactured, "Q1")

        // The legacy code inserted `(manufactured, gameStartDate)` — the
        // scheduled time — not the first time the feed spoke.
        let drawnAt = scheduledKickoff
        XCTAssertEqual(
            firstObservedReading.timeIntervalSince(drawnAt), 2_820, accuracy: 0.5,
            """
            A "Q1" chip drawn 47 minutes before the earliest reading we hold. The chart cannot \
            show the reader which of its boundaries were watched and which were assumed, so the \
            honest answer is to omit the one nobody saw.
            """
        )
    }

    // MARK: - Helpers

    private static var projectRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
    }

    private static var oddsChartView: URL {
        projectRoot.appendingPathComponent("Bain Luck/Components/OddsChartView.swift")
    }

    /// Just `extractPeriodMarkers`'s body.
    ///
    /// Scoping matters in both directions: `gameStartDate` is used legitimately
    /// elsewhere in this file (it clips the series to the game window), so a
    /// whole-file scan for it would be red on correct code; and the deleted
    /// block lived here, so a scan that missed this span would be green on the
    /// defect.
    ///
    /// Both delimiters are asserted rather than defaulted — if either moves,
    /// this fails loudly instead of silently grading an empty string.
    private func markerAssemblyBody() throws -> String {
        let source = try code(at: Self.oddsChartView)
        let opening = "private func extractPeriodMarkers"
        // The next declaration in the file. Not a `// MARK:` — `code(at:)`
        // strips comment lines, so a comment anchor would never be found.
        let closing = "private func chartContent"

        guard let start = source.range(of: opening) else {
            XCTFail("`\(opening)` not found — the scan has no subject")
            return ""
        }
        guard let end = source.range(of: closing, range: start.upperBound..<source.endIndex) else {
            XCTFail("`\(closing)` not found after the subject — the slice is unbounded")
            return ""
        }

        let body = String(source[start.upperBound..<end.lowerBound])
        XCTAssertGreaterThan(
            body.count, 500,
            "the sliced body is too short to be this function — the anchors have drifted")
        return body
    }

    /// Source with its comment lines removed.
    ///
    /// Load-bearing: this file's subject documents the defect it removed, in
    /// code-fenced prose quoting `gameStartDate`, `firstSeen.insert(` and
    /// `inferFirstPeriodLabel` verbatim — deliberately, so the next reader knows
    /// what used to be there. A scan over raw source would read those comments
    /// and report the defect present on correct code.
    ///
    /// The non-empty check is there because an over-eager filter makes every
    /// `contains` pass against an empty string.
    private func code(at url: URL) throws -> String {
        let source = try String(contentsOf: url, encoding: .utf8)
        let stripped = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertTrue(
            stripped.contains("private func extractPeriodMarkers"),
            "the comment strip left nothing to scan in \(url.lastPathComponent)")
        return stripped
    }
}
