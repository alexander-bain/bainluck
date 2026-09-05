import XCTest
@testable import Bain_Luck

/// Guards for the MATCH primitive at GLYPH size (#3313, native/027).
///
/// Two properties a sparkline can violate while still looking perfectly plausible
/// on screen, so both are tested as arithmetic on the pure rules rather than
/// inferred from a rendered path:
///
///  * an auto-scaled y-axis turns a one-point wobble into a mountain;
///  * a full-0-100 y-axis flattens a 19-point swing into noise — the defect this
///    ship fixes, measured on production over 26 live events on 2026-09-05.
///
/// One number, `minimumSpan`, has to bound BOTH, which is why the tests come in
/// pairs: every "stays flat" case has a "still resolves" partner.
final class LiveSparklineDomainTests: XCTestCase {

    private func point(_ minutesAgo: Double, _ probability: Double,
                       source: String = "aggregate",
                       now: Date = Date()) -> ChartDataPoint {
        ChartDataPoint(
            date: now.addingTimeInterval(-minutesAgo * 60),
            probability: probability,
            source: source)
    }

    // MARK: - The shared literal

    func testMinimumSpanIsTheNumberTheWebAlsoPins() {
        // ONE CONTRACT: MIN_SPAN in frontend/components/event/LiveSparkline.tsx
        // carries 0.2 and liveSparkline.test.tsx pins it there. Changing one side
        // must redden the other, the way CEILING_STEPS / RaceChart.ceilingSteps do.
        XCTAssertEqual(LiveSparklineChart.minimumSpan, 0.2, accuracy: 1e-9)
    }

    func testTheWindowIsTenMinutes() {
        XCTAssertEqual(LiveSparklineChart.windowMinutes, 10)
    }

    // MARK: - The axis floor

    func testNarrowSeriesIsWidenedToTheFloorAndCentred() {
        let range = LiveSparklineChart.domain(for: [0.5, 0.51, 0.5])
        XCTAssertEqual(range.upperBound - range.lowerBound,
                       LiveSparklineChart.minimumSpan, accuracy: 1e-9)
        XCTAssertEqual((range.lowerBound + range.upperBound) / 2, 0.505, accuracy: 1e-9)
    }

    func testSeriesWiderThanTheFloorKeepsItsOwnRange() {
        // The floor is a FLOOR. A fix that swapped one fixed axis for another
        // fixed axis would pass every "stays flat" test and fail this one.
        let range = LiveSparklineChart.domain(for: [0.2, 0.65, 0.4])
        XCTAssertEqual(range.lowerBound, 0.2, accuracy: 1e-9)
        XCTAssertEqual(range.upperBound, 0.65, accuracy: 1e-9)
    }

    func testTheCubsMarlinsSwingFillsTheGlyph() {
        // Measured on production 2026-09-05: event 15296785 travelled 19 points
        // inside the ten-minute window. Under the old full-0-100 axis that drew
        // 4.6px in a 24pt box. It must now use nearly all of it.
        let range = LiveSparklineChart.domain(for: [0.35, 0.16, 0.22])
        let fraction = (0.35 - 0.16) / (range.upperBound - range.lowerBound)
        XCTAssertGreaterThan(fraction, 0.9)
        // The control that gives that number meaning: what master drew.
        XCTAssertEqual(0.19 / 1.0, 0.19, accuracy: 1e-9)
        XCTAssertGreaterThan(fraction, (0.19 / 1.0) * 4)
    }

    func testAOnePointWobbleStaysFlat() {
        let range = LiveSparklineChart.domain(for: [0.5, 0.51, 0.5])
        let fraction = 0.01 / (range.upperBound - range.lowerBound)
        // A twentieth of the box — next to a 1.5pt stroke in a 24pt box that is
        // flat, which is the honest reading of a market that has not moved.
        XCTAssertEqual(fraction, 0.05, accuracy: 1e-9)
    }

    func testTravelScalesWithTheSizeOfTheMove() {
        func fraction(_ lo: Double, _ hi: Double) -> Double {
            let range = LiveSparklineChart.domain(for: [lo, hi])
            return (hi - lo) / (range.upperBound - range.lowerBound)
        }
        let small = fraction(0.5, 0.52)
        let large = fraction(0.5, 0.7)
        XCTAssertLessThan(small, 0.15)
        XCTAssertGreaterThan(large, 0.9)
        XCTAssertGreaterThan(large, small * 5)
    }

    // MARK: - Sliding at the edges

    func testNearCertainMarketSlidesInsideTheAxisInsteadOfSquashing() {
        // 96% centred would want 0.86...1.06. Clipping to 0.86...1.0 would judge
        // this series against a 14-point span while every other glyph used 20 —
        // the same move would look bigger here than on the next match.
        let range = LiveSparklineChart.domain(for: [0.95, 0.96, 0.97])
        XCTAssertEqual(range.upperBound, 1.0, accuracy: 1e-9)
        XCTAssertEqual(range.lowerBound, 0.8, accuracy: 1e-9)
    }

    func testNearHopelessMarketSlidesTheOtherWayWithTheSameSpan() {
        let range = LiveSparklineChart.domain(for: [0.03, 0.04, 0.02])
        XCTAssertEqual(range.lowerBound, 0.0, accuracy: 1e-9)
        XCTAssertEqual(range.upperBound, 0.2, accuracy: 1e-9)
    }

    func testEveryDomainKeepsExactlyTheFloorWidthAcrossTheWholeAxis() {
        // Property over the whole range: wherever a flat market sits, it is judged
        // against the same span. A per-position span would make "how much did it
        // move" mean different things at 5% and at 50%.
        for centre in stride(from: 0.0, through: 1.0, by: 0.01) {
            let range = LiveSparklineChart.domain(for: [centre])
            XCTAssertEqual(range.upperBound - range.lowerBound,
                           LiveSparklineChart.minimumSpan, accuracy: 1e-9,
                           "span drifted at centre \(centre)")
            XCTAssertGreaterThanOrEqual(range.lowerBound, 0)
            XCTAssertLessThanOrEqual(range.upperBound, 1)
        }
    }

    func testValuesOutsideZeroToOneAreClampedBeforeTheRangeIsTaken() {
        let range = LiveSparklineChart.domain(for: [-0.5, 0.5, 1.5])
        XCTAssertGreaterThanOrEqual(range.lowerBound, 0)
        XCTAssertLessThanOrEqual(range.upperBound, 1)
    }

    func testEmptySeriesAsksNoOpinionAndGetsTheFullAxis() {
        let range = LiveSparklineChart.domain(for: [])
        XCTAssertEqual(range.lowerBound, 0, accuracy: 1e-9)
        XCTAssertEqual(range.upperBound, 1, accuracy: 1e-9)
    }

    // MARK: - The window

    func testWindowKeepsRecentPointsAndDropsTheRest() {
        let now = Date()
        let kept = LiveSparklineChart.windowed(
            [point(30, 0.4, now: now), point(5, 0.5, now: now), point(1, 0.6, now: now)],
            minutes: 10, now: now)
        XCTAssertEqual(kept.map(\.probability), [0.5, 0.6])
    }

    func testWindowReturnsOldestFirstRegardlessOfInputOrder() {
        // A pushed point is APPENDED, and an out-of-order vertex draws a line that
        // doubles back on itself.
        let now = Date()
        let kept = LiveSparklineChart.windowed(
            [point(1, 0.6, now: now), point(9, 0.4, now: now), point(5, 0.5, now: now)],
            minutes: 10, now: now)
        XCTAssertEqual(kept.map(\.probability), [0.4, 0.5, 0.6])
    }

    func testAWholeMatchSeriesIsClippedNotSummarised() {
        let now = Date()
        let threeHours = (0..<180).map { point(Double(180 - $0), 0.5, now: now) }
        XCTAssertLessThanOrEqual(
            LiveSparklineChart.windowed(threeHours, minutes: 10, now: now).count, 11)
    }

    // MARK: - Drawability (#3278 one size down)

    func testTooFewReadingsDrawNothing() {
        let now = Date()
        let two = LiveSparklineChart.windowed(
            [point(5, 0.5, now: now), point(3, 0.6, now: now)], minutes: 10, now: now)
        // Two points DO make a line — hasDrawableLine says so — but the glyph's
        // own floor is stricter, because a single segment's slope on a ten-minute
        // glance is one reading's worth of noise.
        XCTAssertTrue(OddsChartView.hasDrawableLine(in: two))
        XCTAssertFalse(LiveSparklineChart.isDrawable(two))
    }

    func testThreeReadingsDraw() {
        let now = Date()
        let three = LiveSparklineChart.windowed(
            [point(9, 0.4, now: now), point(6, 0.5, now: now), point(3, 0.6, now: now)],
            minutes: 10, now: now)
        XCTAssertTrue(LiveSparklineChart.isDrawable(three))
    }

    func testAnEmptyWindowDrawsNothing() {
        XCTAssertFalse(LiveSparklineChart.isDrawable([]))
    }

    func testThreeReadingsSplitAcrossSourcesDoNotDraw() {
        // #3278's lesson, one size down: the rule is PER SERIES. Three points from
        // three different sources is three points and still no line. A bare
        // `count >= 3` test would call this drawable and render an empty glyph.
        let now = Date()
        let split = [
            point(9, 0.4, source: "kalshi", now: now),
            point(6, 0.5, source: "polymarket", now: now),
            point(3, 0.6, source: "consensus", now: now),
        ]
        XCTAssertFalse(LiveSparklineChart.isDrawable(split))
    }

    // MARK: - Which line the glyph is allowed to draw

    func testTheGlyphDrawsTheBlendAndNothingElse() {
        // "The blend is the product." The glyph must never disagree with the chart
        // below it about which line is the story, so it reuses the chart's own
        // choice rather than picking its own.
        let now = Date()
        let mixed = [
            point(9, 0.40, source: "aggregate", now: now),
            point(6, 0.42, source: "aggregate", now: now),
            point(3, 0.44, source: "aggregate", now: now),
            point(9, 0.10, source: "consensus", now: now),
            point(6, 0.90, source: "consensus", now: now),
        ]
        let series = LiveSparklineChart.primarySeries(in: mixed)
        XCTAssertEqual(series.count, 3)
        XCTAssertTrue(series.allSatisfy { $0.source == "aggregate" })
        // And the wild consensus values must not reach the axis.
        let range = LiveSparklineChart.domain(for: series.map(\.probability))
        XCTAssertLessThan(range.upperBound, 0.75)
    }

    func testWithNoBlendTheGlyphFallsBackToConsensus() {
        let now = Date()
        let noBlend = [
            point(9, 0.40, source: "consensus", now: now),
            point(6, 0.42, source: "consensus", now: now),
        ]
        XCTAssertTrue(
            LiveSparklineChart.primarySeries(in: noBlend).allSatisfy { $0.source == "consensus" })
    }

    // MARK: - Colour

    func testColourFollowsNetDirection() {
        let now = Date()
        let up = LiveSparklineChart.windowed(
            [point(9, 0.4, now: now), point(3, 0.6, now: now)], minutes: 10, now: now)
        let down = LiveSparklineChart.windowed(
            [point(9, 0.6, now: now), point(3, 0.4, now: now)], minutes: 10, now: now)
        XCTAssertTrue(LiveSparklineChart.isRising(up))
        XCTAssertFalse(LiveSparklineChart.isRising(down))
    }

    func testAccessibilityLabelNamesBothEndsOfTheWindow() {
        let now = Date()
        let series = LiveSparklineChart.windowed(
            [point(9, 0.4, now: now), point(6, 0.5, now: now), point(3, 0.62, now: now)],
            minutes: 10, now: now)
        XCTAssertEqual(
            LiveSparklineChart.accessibilityLabel(for: series, minutes: 10),
            "Last 10 minutes: 40% to 62%")
    }
}
