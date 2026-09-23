import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #1833 — the two stacked event-page charts draw ONE clock at 440pt.
///
/// SPECIMEN: Nationals @ Tigers (`15317535`), live 2026-09-23 from 17:10Z,
/// native/308's frames on the candidate tree (`n308-w440-s350*.png`, reopening
/// comment on #1833). Plot widths MEASURED off `n308-w440-s350.png` (1320px,
/// 3.0 px/pt) as the contiguous run of each chart's horizontal gridlines:
/// Win Probability 969px = **323pt**, Score Differential 1014px = **338pt**,
/// identical on every gridline row sampled. The 15pt is SD's narrower y-gutter
/// (`+6…-6` against `75%…0%`).
///
/// Rendered result on that game, before this change:
///   "50-min" frame  WP 15-min ticks · SD 10-min ticks (SD end gaps at the 6pt floor)
///   "80-min" frame  WP 20-min ticks · SD 15-min ticks
///   1h52m frame     both 30-min ticks
///
/// The frame names are n308's approximate game clock, not the plotted domain.
/// The planner's own arithmetic BOUNDS the domains those frames must have had
/// (10-minute ticks clear 338pt only up to 50.1 min; 15-minute ticks clear
/// 338pt only up to 75.1 min and fail 323pt above 71.8 min), so the control
/// below uses 49 and 73 minutes — inside those bounds — rather than the labels.
///
/// The fix is page-level: both charts publish their inline plot width, the page
/// hands the narrower back, and both plan on it (`OddsChartView.axisPlanWidth`).
final class OneClockPerPage1833Tests: XCTestCase {

    private let winProbPlot: CGFloat = 323
    private let scoreDiffPlot: CGFloat = 338

    private var utc: Calendar = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return cal
    }()

    private func date(_ iso: String) -> Date { ISO8601DateFormatter().date(from: iso)! }

    /// First pitch plus `minutes`, the `+30 s` `domain(upTo:)` adds included.
    private func domain(minutes: Double) -> ClosedRange<Date> {
        let start = date("2026-09-23T17:10:00Z")
        return start...start.addingTimeInterval(minutes * 60 + 30)
    }

    private func strideSeconds(_ plan: OddsChartView.XAxisPlan) -> TimeInterval {
        let unit: TimeInterval
        switch plan.component {
        case .minute: unit = 60
        case .hour: unit = 3600
        case .day: unit = 86400
        default: return .infinity
        }
        return unit * Double(plan.count)
    }

    private func plan(_ domain: ClosedRange<Date>, _ width: CGFloat) -> OddsChartView.XAxisPlan {
        OddsChartView.xAxisPlan(for: domain, plotWidth: width, calendar: utc)
    }

    /// The page's reduction over what the two inline charts publish.
    private func pageNarrowest(_ widths: [CGFloat]) -> CGFloat {
        var value = PageAxisPlotWidthPreferenceKey.defaultValue
        for w in widths { PageAxisPlotWidthPreferenceKey.reduce(value: &value) { w } }
        return value
    }

    // MARK: - The defect, on the measured widths

    /// CONTROL. Each chart planning from its own plot reproduces the two
    /// frames n308 photographed — so the fix below is tested against the real
    /// straddle and not a constructed one.
    func testOwnWidthsReproduceTheTwoClocksOnTheSpecimen() {
        let fifty = domain(minutes: 49)
        XCTAssertEqual(strideSeconds(plan(fifty, winProbPlot)), 15 * 60)
        XCTAssertEqual(strideSeconds(plan(fifty, scoreDiffPlot)), 10 * 60)

        let eighty = domain(minutes: 73)
        XCTAssertEqual(strideSeconds(plan(eighty, winProbPlot)), 20 * 60)
        XCTAssertEqual(strideSeconds(plan(eighty, scoreDiffPlot)), 15 * 60)

        let late = domain(minutes: 112)
        XCTAssertEqual(strideSeconds(plan(late, winProbPlot)), 30 * 60)
        XCTAssertEqual(strideSeconds(plan(late, scoreDiffPlot)), 30 * 60)
    }

    // MARK: - The fix

    /// Both charts, planned the way they now are, take one stride — and it is
    /// the UPPER chart's own stride, so Win Probability does not change.
    func testSharedWidthGivesBothChartsOneStrideOnTheSpecimen() {
        let page = pageNarrowest([winProbPlot, scoreDiffPlot])
        XCTAssertEqual(page, winProbPlot)
        for minutes in [49.0, 73, 112] {
            let d = domain(minutes: minutes)
            let upper = plan(d, OddsChartView.axisPlanWidth(own: winProbPlot, pageNarrowest: page))
            let lower = plan(d, OddsChartView.axisPlanWidth(own: scoreDiffPlot, pageNarrowest: page))
            XCTAssertEqual(strideSeconds(upper), strideSeconds(lower), "\(minutes) min")
            XCTAssertEqual(upper.labelStyle, lower.labelStyle, "\(minutes) min")
            XCTAssertEqual(strideSeconds(upper), strideSeconds(plan(d, winProbPlot)),
                           "\(minutes) min: the upper chart's axis must not move")
        }
    }

    /// Across a whole game at every phone width: one stride, and it clears on
    /// BOTH plots (it was chosen on the narrower one, so the wider one only
    /// gains slack).
    func testOneClockAcrossAGameAtEveryPhoneWidth() {
        for screen in [375.0, 390, 440] as [CGFloat] {
            let wp = screen - 117          // 440 → 323, the measured plot
            let sd = wp + 15               // the measured gutter difference
            let page = pageNarrowest([wp, sd])
            var minutes = 15.0
            while minutes <= 240 {
                let d = domain(minutes: minutes)
                let upper = plan(d, OddsChartView.axisPlanWidth(own: wp, pageNarrowest: page))
                let lower = plan(d, OddsChartView.axisPlanWidth(own: sd, pageNarrowest: page))
                XCTAssertEqual(strideSeconds(upper), strideSeconds(lower),
                               "\(screen)pt, \(minutes) min")
                let intervals = d.upperBound.timeIntervalSince(d.lowerBound) / strideSeconds(lower)
                for width in [wp, sd] {
                    XCTAssertTrue(
                        OddsChartView.xAxisFits(intervals: intervals, plotWidth: width,
                                                style: lower.labelStyle),
                        "\(screen)pt, \(minutes) min: shared stride does not clear at \(width)pt")
                }
                minutes += 5
            }
        }
    }

    // MARK: - The page reduction and the fallbacks

    func testPageReductionIsTheNarrowestMeasuredPlot() {
        XCTAssertEqual(pageNarrowest([]), 0, "no chart: nothing measured")
        XCTAssertEqual(pageNarrowest([338]), 338, "one chart plans on its own width")
        XCTAssertEqual(pageNarrowest([338, 323]), 323)
        XCTAssertEqual(pageNarrowest([323, 338]), 323, "order does not matter")
        // The fullscreen sheet and an unmeasured first pass publish 0, which
        // must never win the minimum — it would read as "use the count budget".
        XCTAssertEqual(pageNarrowest([0, 338, 0]), 338)
        XCTAssertEqual(pageNarrowest([323, 0]), 323)
    }

    func testAxisPlanWidthFallsBackRatherThanToZero() {
        XCTAssertEqual(OddsChartView.axisPlanWidth(own: 338, pageNarrowest: 0), 338)
        XCTAssertEqual(OddsChartView.axisPlanWidth(own: 0, pageNarrowest: 323), 323)
        XCTAssertEqual(OddsChartView.axisPlanWidth(own: 0, pageNarrowest: 0), 0)
        XCTAssertEqual(OddsChartView.axisPlanWidth(own: 338, pageNarrowest: 323), 323)
        XCTAssertEqual(OddsChartView.axisPlanWidth(own: 323, pageNarrowest: 338), 323,
                       "a page width can only NARROW a chart's plan, never widen it")
    }
}
