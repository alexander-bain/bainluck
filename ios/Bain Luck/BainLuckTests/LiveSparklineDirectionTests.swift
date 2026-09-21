import XCTest
@testable import Bain_Luck

/// #7794 — the colour and the label are ONE answer, not two.
///
/// The glyph decided its direction on the RAW probabilities with no dead band
/// while its own `accessibilityLabel` printed a rounded percent, so a fall of one
/// ten-thousandth painted the line red above a label reading "99% to 99%". On a
/// 99% favourite at halftime that is the only kind of move there is.
///
/// These assert the two channels AGAINST EACH OTHER, because that is the only
/// relation that cannot quietly come apart again — a test of the hex alone would
/// pass on whatever threshold somebody picked next, and a test of the label alone
/// never looked at the colour.
///
/// The iOS twin of `sparklineDirection` in `frontend/components/event/LiveSparkline.tsx`
/// (#5734, ux/1413): same rule, same three hexes, same case table. Each side pins
/// its own behaviour in its own runner — the arrangement `minimumSpan` / `MIN_SPAN`
/// already uses — and `frontend/__tests__/ios/liveSparklineDirectionParity7794.test.ts`
/// is the CI-reachable half, because CI compiles no Swift (#4302).
final class LiveSparklineDirectionTests: XCTestCase {

    private func point(_ minutesAgo: Double, _ probability: Double,
                       now: Date = Date()) -> ChartDataPoint {
        ChartDataPoint(
            date: now.addingTimeInterval(-minutesAgo * 60),
            probability: probability,
            source: "aggregate")
    }

    // MARK: - The filed shape

    func testATenThousandthOfAFallOnANinetyNinePercentFavouriteIsFlat() {
        // The filed specimen: Real Madrid 3-0 at HT, hero at 99% and rising since
        // open, glyph painted red.
        XCTAssertEqual(LiveSparklineChart.direction(from: 0.9901, to: 0.99), .flat)
    }

    func testARiseThatRendersAsATieIsFlatToo() {
        // The other 401 of the 467 tied windows ux measured on production. A fix
        // that only silenced the RED half would still be claiming a direction the
        // label denies — it would just read benignly.
        XCTAssertEqual(LiveSparklineChart.direction(from: 0.986, to: 0.994), .flat)
    }

    func testIdenticalEndpointsAreFlat() {
        XCTAssertEqual(LiveSparklineChart.direction(from: 0.5, to: 0.5), .flat)
    }

    // MARK: - The colour is narrowed, not deleted

    func testAMoveTheLabelReportsKeepsItsDirection() {
        XCTAssertEqual(LiveSparklineChart.direction(from: 0.6, to: 0.55), .down)
        XCTAssertEqual(LiveSparklineChart.direction(from: 0.4, to: 0.62), .up)
        // One whole point either way is the narrowest move the label can report,
        // so it is the narrowest the colour may claim. These two are what stop the
        // fix from being "paint everything grey".
        XCTAssertEqual(LiveSparklineChart.direction(from: 0.5, to: 0.49), .down)
        XCTAssertEqual(LiveSparklineChart.direction(from: 0.5, to: 0.51), .up)
    }

    func testAValueThatCannotBeRenderedClaimsNothing() {
        // `max(0, .nan)` is 0 in Swift — every NaN comparison is false — so a
        // clamp applied before the finiteness guard would turn an unrenderable
        // reading into a confident 0%. This is that ordering, asserted.
        XCTAssertEqual(LiveSparklineChart.direction(from: .nan, to: 0.5), .flat)
        XCTAssertEqual(LiveSparklineChart.direction(from: 0.5, to: .infinity), .flat)
        XCTAssertNil(LiveSparklineChart.publishedPercent(.nan))
        XCTAssertEqual(LiveSparklineChart.publishedPercent(0.5), 50)
    }

    // MARK: - The relation itself

    func testFlatIsExactlyTheCaseTheLabelPrintsAsNoChange() {
        // The relation, not a sample: whatever `renderedPercent`'s contract does
        // next, the colour is neutral on precisely the pairs whose label repeats
        // itself. The same grid the web arm sweeps.
        let grid: [Double] = [0.0, 0.004, 0.005, 0.0149, 0.285, 0.4949, 0.5, 0.5051,
                              0.986, 0.99, 0.9901, 0.9949, 1.0]
        var ties = 0
        var moves = 0
        for a in grid {
            for b in grid {
                let labelRepeats =
                    LiveSparklineChart.publishedPercent(a) == LiveSparklineChart.publishedPercent(b)
                XCTAssertEqual(
                    LiveSparklineChart.direction(from: a, to: b) == .flat, labelRepeats,
                    "direction(\(a) → \(b)) disagrees with the label it is drawn beside")
                if labelRepeats { ties += 1 } else { moves += 1 }
            }
        }
        // Not vacuous in either direction: the grid exercises both branches.
        XCTAssertGreaterThan(ties, 10)
        XCTAssertGreaterThan(moves, 10)
    }

    /// The end-to-end form: one series, both published channels, asserted together.
    func testTheGlyphsOwnTwoChannelsAgreeOnTheSpecimen() {
        let now = Date()
        let specimen = LiveSparklineChart.windowed(
            [point(9, 0.9901, now: now), point(6, 0.9902, now: now), point(3, 0.99, now: now)],
            minutes: 10, now: now)

        XCTAssertTrue(LiveSparklineChart.isDrawable(specimen),
                      "the specimen must actually draw, or this asserts nothing")
        XCTAssertEqual(LiveSparklineChart.direction(specimen), .flat)
        XCTAssertEqual(
            LiveSparklineChart.accessibilityLabel(for: specimen, minutes: 10),
            "Last 10 minutes: 99% to 99%")
    }

    // MARK: - The label rounds on the shared contract, not a local `* 100`

    func testTheLabelUsesTheRenderedPercentContract() {
        let now = Date()
        // #3867's specimen. `* 100` scores 0.565 as 56 because the double the wire
        // value became sits a hair under the boundary; the contract scales by 1000
        // first and lands 57, which is what every other surface prints. The label
        // used to be the `* 100` form.
        let series = LiveSparklineChart.windowed(
            [point(9, 0.565, now: now), point(6, 0.57, now: now), point(3, 0.585, now: now)],
            minutes: 10, now: now)
        XCTAssertEqual(
            LiveSparklineChart.accessibilityLabel(for: series, minutes: 10),
            "Last 10 minutes: 57% to 59%")
        XCTAssertEqual(LiveSparklineChart.publishedPercent(0.565), renderedPercent(0.565))
        XCTAssertNotEqual(Int((0.565 * 100).rounded()), renderedPercent(0.565),
                          "if these agree the contract changed and this test is no longer "
                          + "distinguishing the two rules")
    }

    func testAnEmptyWindowSaysSo() {
        XCTAssertEqual(LiveSparklineChart.accessibilityLabel(for: [], minutes: 10),
                       "No recent readings")
        XCTAssertEqual(LiveSparklineChart.direction([]), .flat)
    }

    // MARK: - The shared literals

    func testTheThreeStrokeColoursAreTheOnesTheWebAlsoPins() {
        // ONE CONTRACT: STROKE_UP / STROKE_DOWN / STROKE_FLAT in LiveSparkline.tsx
        // carry these three, and `#9CA3AF` is `--text-muted` in globals.css.
        XCTAssertEqual(LiveSparklineChart.strokeUp, "#10B981")
        XCTAssertEqual(LiveSparklineChart.strokeDown, "#EF4444")
        XCTAssertEqual(LiveSparklineChart.strokeFlat, "#9CA3AF")
    }
}
