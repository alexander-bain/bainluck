import SwiftUI
import XCTest
@testable import Bain_Luck

/// #3817 — the period-chip strip stops deleting real periods for want of ink it
/// never draws.
///
/// PHOTOGRAPHED on master `a2ed380e`, iPhone 17, 2026-09-07: the completed
/// Cardinals 10 — Rockies 8 (15305472). Its MATCH chart drew the strip
///
///     2nd · 3rd · 5th · 7th · 8th · Final
///
/// directly beneath a Game Segments table printing `1 2 3 4 5 6 7 8 9 T`. The
/// same page's score chart, on the same domain, drew eight chips. Two strips,
/// one game, and neither of them the game.
///
/// `place` had not MISplaced anything. It answered every predicted collision by
/// DELETING a chip, and the collisions were tiny:
///
///  * `4th` was 0.4pt short of clearing `5th`;
///  * `9th` and `1st` were deleted by moves they did not make — the mandatory
///    clamp that keeps `Final` and the first chip inside the plot displaces them
///    up to half a chip's width, and that displacement was charged to the
///    neighbour's existence.
///
/// The strip held 238pt of ink in a 280pt plot. It was never out of room; it was
/// out of willingness to move. Chips are placed by relaxation now, and dropped
/// only when they still cannot be drawn — bounded by `nudgeBudget`, so a chip
/// that is drawn still overlaps the gridline it names.
///
/// A second, smaller contributor, kept separate because the first diagnosis got
/// it backwards: `chipWidth` charged 6pt per character as a deliberate upper
/// bound. Over-estimating is safe for avoiding an overlap and UNSAFE for keeping
/// information. Measured, though, 10pt bold really does draw ~5.9pt per glyph —
/// the surplus was in "Final" (5.4pt) and across the whole 8pt score strip, not
/// in the inning chips. Width is measured now regardless; see
/// `testTheRetiredPerCharacterRuleErredMostOnLongLabelsAndTheSmallStrip`.
final class PeriodChipWidthTests: XCTestCase {

    /// Every label `PeriodLabel.normalize` can hand the strip. Quarters, hockey
    /// periods, halves, halftime, overtimes, intermission, golf rounds and the
    /// playoff, the 1…N inning ladder (#1831 made two digits reachable), and the
    /// terminal chip.
    private static let vocabulary: [String] = {
        var labels = ["Q1", "Q2", "Q3", "Q4",
                      "P1", "P2", "P3",
                      "1H", "2H", "HT", "INT",
                      "OT", "OT1", "OT2", "OT3", "OT4",
                      "R1", "R2", "R3", "R4", "PO",
                      "Final"]
        for n in 1...20 {
            let suffix: String
            switch (n % 10, n % 100) {
            case (1, let h) where h != 11: suffix = "st"
            case (2, let h) where h != 12: suffix = "nd"
            case (3, let h) where h != 13: suffix = "rd"
            default: suffix = "th"
            }
            labels.append("\(n)\(suffix)")
        }
        return labels
    }()

    // MARK: - the model is measured, not guessed

    #if canImport(UIKit)
    /// The width model must track the ink in BOTH directions.
    ///
    /// Upper bound: a model narrower than the drawing lets two chips touch, which
    /// is the defect #3237 exists to prevent. Lower bound: a model wider than the
    /// drawing deletes chips that fit, which is the defect this file exists to
    /// prevent — and the one that shipped, because the old rule asserted only the
    /// upper bound and was free to be as generous as it liked underneath it.
    ///
    /// The tolerance is 0.5pt, tight enough that the 4pt-per-chip slack the
    /// 6pt-per-character rule carried cannot come back.
    func testMeasuredChipWidthTracksDrawnInkBothWays() {
        for (name, metrics, weight) in [
            ("match", PeriodChipGeometry.ChipMetrics.match, UIFont.Weight.bold),
            ("score", PeriodChipGeometry.ChipMetrics.score, UIFont.Weight.semibold),
        ] {
            let font = UIFont.systemFont(ofSize: metrics.fontSize, weight: weight)
            var widest: (label: String, width: Double) = ("", 0)
            for label in Self.vocabulary {
                let drawn = Double((label as NSString).size(withAttributes: [.font: font]).width)
                    + metrics.horizontalPadding * 2
                let modelled = PeriodChipGeometry.chipWidth(for: label, metrics: metrics)
                XCTAssertEqual(
                    modelled, drawn, accuracy: 0.5,
                    "\(name) chip \"\(label)\": model says \(modelled)pt, "
                        + "the strip draws \(drawn)pt")
                if drawn > widest.width { widest = (label, drawn) }
            }
            print("MEASURED \(name): widest chip \"\(widest.label)\" = \(widest.width)pt")
        }
    }

    /// WHERE THE RETIRED PER-CHARACTER RULE WAS ACTUALLY WRONG, measured rather
    /// than assumed — because the first diagnosis of #3817 assumed it was wrong
    /// everywhere and the measurement refuted that.
    ///
    /// At 10pt bold a glyph really is close to the 6pt the old rule charged, so a
    /// three-character inning chip was over-charged by a third of a point. The
    /// error lived in the LONG label and the SMALL strip: "Final" was charged
    /// 38pt against 32.5pt of ink, and the score strip's 5pt-per-character model
    /// over-charged every one of its chips by about a fifth.
    ///
    /// This matters for the record as much as for the code. The width model was a
    /// contributor to the photographed strip, not its cause — the cause was
    /// `place` answering a 0.4pt collision by deleting an inning — and a test
    /// asserting the widths were badly wrong would have been a false account of
    /// the bug kept alive as a guard.
    func testTheRetiredPerCharacterRuleErredMostOnLongLabelsAndTheSmallStrip() {
        func retired(_ label: String, _ metrics: PeriodChipGeometry.ChipMetrics) -> Double {
            metrics.horizontalPadding * 2
                + Double(label.count) * metrics.fallbackCharacterWidth
        }
        let match = PeriodChipGeometry.ChipMetrics.match

        // A three-character inning: the old rule was very nearly right.
        XCTAssertLessThan(
            retired("4th", match) - PeriodChipGeometry.chipWidth(for: "4th", metrics: match),
            1.0, "10pt bold really does draw close to 6pt per character")
        // "Final" is where it went wide.
        XCTAssertGreaterThan(
            retired("Final", match)
                - PeriodChipGeometry.chipWidth(for: "Final", metrics: match),
            4.0, "the terminal chip was the over-charged one")
        // And the whole small strip was loose.
        let score = PeriodChipGeometry.ChipMetrics.score
        XCTAssertGreaterThan(
            retired("Final", score)
                - PeriodChipGeometry.chipWidth(for: "Final", metrics: score),
            4.0, "8pt semibold draws nowhere near 5pt per character")
    }
    #endif

    /// `chipWidthPoints` is still the conservative two-character bound the
    /// spacing fraction is derived from, and measuring must not have pushed a
    /// real chip past it.
    func testTwoCharacterChipStaysUnderTheDerivedSpacingBound() {
        XCTAssertLessThanOrEqual(
            PeriodChipGeometry.chipWidth(for: "10"), PeriodChipGeometry.chipWidthPoints)
    }

    /// The score strip's 8pt type stays narrower than the MATCH strip's 10pt for
    /// the same label — the reason the two metrics exist at all.
    func testScoreStripChipsAreNarrowerThanMatchStripChips() {
        for label in ["1st", "Final", "OT2"] {
            XCTAssertLessThan(
                PeriodChipGeometry.chipWidth(for: label, metrics: .score),
                PeriodChipGeometry.chipWidth(for: label, metrics: .match),
                "\(label) must be narrower on the small strip")
        }
    }

    // MARK: - the specimen

    /// 15305472's own period boundaries, read from
    /// `/api/events/15305472/history` on 2026-09-07: nine innings and the
    /// terminal chip, over a domain running from first pitch to `completed_at`.
    private static let cardinalsRockies: [(label: String, minutesAfterStart: Double)] = [
        ("1st", 2.93), ("2nd", 23.0), ("3rd", 41.0), ("4th", 62.0), ("5th", 79.0),
        ("6th", 106.0), ("7th", 115.0), ("8th", 137.0), ("9th", 168.0), ("Final", 188.0),
    ]
    /// The chart's measured plot width on an iPhone 17. Narrower than the score
    /// chart's below it, because "100%" is a wider y-axis label than "+6" — which
    /// is why the MATCH chart, the one that matters, was losing the most chips.
    private static let specimenPlotWidth: Double = 280
    private static let specimenSpanMinutes: Double = 188.7

    private static func specimenRequests(
        dropping dropped: Set<String> = []
    ) -> [PeriodChipGeometry.ChipRequest] {
        cardinalsRockies
            .filter { !dropped.contains($0.label) }
            .enumerated()
            .map { index, marker in
                PeriodChipGeometry.ChipRequest(
                    key: index, label: marker.label,
                    rawX: marker.minutesAfterStart / specimenSpanMinutes * specimenPlotWidth)
            }
    }

    private static func labels(
        _ placements: [PeriodChipGeometry.ChipPlacement],
        from requests: [PeriodChipGeometry.ChipRequest]
    ) -> [String] {
        placements.compactMap { placement in
            requests.first { $0.key == placement.key }?.label
        }
    }

    /// THE PHOTOGRAPH, PINNED. `6th` is dropped upstream by the extraction's
    /// spacing rule (its 9-minute gap to `7th` is genuinely too small), so the
    /// strip is placed from the nine markers the chart actually receives.
    ///
    /// Under the retired per-character rule this returned six chips and the game
    /// appeared to start in the 2nd inning. The assertion is on the innings that
    /// came back, not on an exact strip, so a future change that recovers MORE of
    /// them strengthens the chart without failing its guard.
    func testTheSpecimenStripStopsLosingRealInnings() {
        let requests = Self.specimenRequests(dropping: ["6th"])
        let drawn = Self.labels(
            PeriodChipGeometry.place(
                requests, plotWidth: Self.specimenPlotWidth, metrics: .match),
            from: requests)

        XCTAssertTrue(
            drawn.contains("4th"),
            "the 4th inning was deleted over 0.4pt of movement; strip: \(drawn)")
        XCTAssertTrue(
            drawn.contains("1st"),
            "a nine-inning game must not appear to begin in the 2nd; strip: \(drawn)")
        XCTAssertTrue(drawn.contains("Final"), "the terminal chip always survives")
        XCTAssertGreaterThanOrEqual(
            drawn.count, 8,
            "the photographed strip drew 6 of 9; strip: \(drawn)")
    }

    /// Whatever survives, the strip must still be collision-free and inside the
    /// plot — the property the width model exists to serve. Asserted against the
    /// measured widths, so tightening the model cannot buy chips by letting them
    /// overlap.
    func testTheSpecimenStripNeitherOverlapsNorOverhangs() {
        let requests = Self.specimenRequests(dropping: ["6th"])
        let placements = PeriodChipGeometry.place(
            requests, plotWidth: Self.specimenPlotWidth, metrics: .match)
        let drawn = Self.labels(placements, from: requests)

        var previousTrailingEdge = -Double.infinity
        for (placement, label) in zip(placements, drawn) {
            let half = PeriodChipGeometry.chipWidth(for: label, metrics: .match) / 2
            XCTAssertGreaterThanOrEqual(
                placement.centerX - half, 0, "\(label) overhangs the leading edge")
            XCTAssertLessThanOrEqual(
                placement.centerX + half, Self.specimenPlotWidth,
                "\(label) overhangs the trailing edge")
            XCTAssertGreaterThanOrEqual(
                placement.centerX - half, previousTrailingEdge,
                "\(label) overlaps the chip before it")
            previousTrailingEdge = placement.centerX + half
        }
    }

    // MARK: - the placement policy itself

    /// Every chip that survives still touches the boundary it names. This is the
    /// rule that makes moving a chip legitimate rather than a lie: the period's
    /// gridline is drawn exactly, and a label overlapping its own line reads as
    /// belonging to it.
    func testEveryDrawnChipStillOverlapsItsOwnBoundary() {
        let requests = Self.specimenRequests(dropping: ["6th"])
        let placements = PeriodChipGeometry.place(
            requests, plotWidth: Self.specimenPlotWidth, metrics: .match)
        for placement in placements {
            guard let request = requests.first(where: { $0.key == placement.key })
            else { return XCTFail("placement \(placement.key) has no request") }
            // The clamp into the plot is mandatory, so the boundary a chip must
            // still reach is its clamped ideal.
            let ideal = PeriodChipGeometry.clampedCenterX(
                rawX: request.rawX, label: request.label,
                plotWidth: Self.specimenPlotWidth, metrics: .match)
            XCTAssertLessThanOrEqual(
                abs(placement.centerX - ideal),
                PeriodChipGeometry.nudgeBudget(for: request.label, metrics: .match) + 0.001,
                "\(request.label) drifted off the gridline it labels")
        }
    }

    /// A strip with room to spare is not touched at all — relaxation is a last
    /// resort before dropping, never a re-layout of a chart that was already fine.
    func testAWellSpacedStripIsNeitherMovedNorThinned() {
        let requests = [
            PeriodChipGeometry.ChipRequest(key: 0, label: "1st", rawX: 40),
            PeriodChipGeometry.ChipRequest(key: 1, label: "2nd", rawX: 140),
            PeriodChipGeometry.ChipRequest(key: 2, label: "3rd", rawX: 240),
        ]
        let placements = PeriodChipGeometry.place(requests, plotWidth: 337)
        XCTAssertEqual(placements.map(\.key), [0, 1, 2])
        XCTAssertEqual(placements.map(\.centerX), [40, 140, 240])
    }

    /// THE CASE THE OLD POLICY GOT WRONG, in miniature. Two chips 0.4pt too close
    /// used to cost one of them; they are now moved a fifth of a point each and
    /// both drawn.
    func testAHairsBreadthCollisionMovesBothChipsInsteadOfDeletingOne() {
        let width = PeriodChipGeometry.chipWidth(for: "4th")
        let requests = [
            PeriodChipGeometry.ChipRequest(key: 0, label: "3rd", rawX: 100),
            PeriodChipGeometry.ChipRequest(key: 1, label: "4th", rawX: 100 + width - 0.4),
        ]
        let placements = PeriodChipGeometry.place(requests, plotWidth: 337)
        XCTAssertEqual(placements.map(\.key), [0, 1], "neither chip needed deleting")
        XCTAssertGreaterThanOrEqual(
            placements[1].centerX - placements[0].centerX, width - 0.001,
            "…and they were separated rather than merely kept")
    }

    /// The clamp's displacement is no longer charged to the neighbour. `Final`
    /// sits on the trailing edge and must be pulled inward; `9th` beside it keeps
    /// its chip when there is room for both.
    func testTheTerminalClampNoLongerEvictsItsNeighbour() {
        let requests = [
            PeriodChipGeometry.ChipRequest(key: 0, label: "8th", rawX: 250),
            PeriodChipGeometry.ChipRequest(key: 1, label: "9th", rawX: 300),
            PeriodChipGeometry.ChipRequest(key: 2, label: "Final", rawX: 335),
        ]
        let placements = PeriodChipGeometry.place(requests, plotWidth: 337)
        XCTAssertEqual(
            placements.map(\.key), [0, 1, 2],
            "all three fit in 337pt once the strip is allowed to shuffle")
    }

    /// …but a strip that genuinely cannot fit still drops, and still keeps the
    /// terminal chip. Ten periods crammed into the last tenth of the plot.
    func testAnImpossibleStripStillDropsAndStillKeepsTheLastChip() {
        let labels = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "Final"]
        let plotWidth = 337.0
        let requests = labels.enumerated().map { index, label in
            PeriodChipGeometry.ChipRequest(
                key: index, label: label,
                rawX: plotWidth * 0.9 + plotWidth * 0.1 * Double(index) / 9.0)
        }
        let placements = PeriodChipGeometry.place(requests, plotWidth: plotWidth)
        XCTAssertFalse(placements.isEmpty, "an impossible strip must not go blank")
        XCTAssertLessThan(placements.count, labels.count, "…and must not pretend to fit")
        XCTAssertEqual(placements.last?.key, 9, "the terminal chip is the survivor")
    }

    /// The two strips on the event page are placed from the same markers, and the
    /// smaller type must never carry FEWER chips than the larger — if it does,
    /// the page is drawing two different games again.
    func testTheSmallStripNeverCarriesFewerChipsThanTheLargeOne() {
        let requests = Self.specimenRequests(dropping: ["6th"])
        let match = PeriodChipGeometry.place(
            requests, plotWidth: Self.specimenPlotWidth, metrics: .match)
        let score = PeriodChipGeometry.place(
            requests, plotWidth: Self.specimenPlotWidth, metrics: .score)
        XCTAssertGreaterThanOrEqual(score.count, match.count)
    }
}
