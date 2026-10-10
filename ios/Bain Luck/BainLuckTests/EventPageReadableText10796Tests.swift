import XCTest
import SwiftUI
@testable import Bain_Luck

#if os(iOS)
import UIKit

final class EventPageReadableText10796Tests: XCTestCase {
    @MainActor
    func testLargeTextHeroUsesTallestTeamHeightInsteadOfAddingBothTeams() {
        let content = EventHeroTeamLayout {
            Color.red.frame(height: 80)
            Color.green.frame(height: 60)
            Color.blue.frame(height: 90)
        }
        let host = hostForMeasurement(content)
        let measured = host.sizeThatFits(in: CGSize(width: 358, height: 1000))
        XCTAssertEqual(measured.width, 358, accuracy: 1)
        XCTAssertEqual(measured.height, 162, accuracy: 1)
    }

    @MainActor
    func testLongTeamNamesGrowInsideTheirHalfOfThePhone() {
        let content = EventHeroTeamLayout {
            Text("Las Vegas Raiders").font(.caption2).fixedSize(horizontal: false, vertical: true)
            Text("36% – 64%").font(.title)
            Text("New England Patriots").font(.caption2).fixedSize(horizontal: false, vertical: true)
        }
        let host = hostForMeasurement(content, at: .accessibility3)
        let measured = host.sizeThatFits(in: CGSize(width: 326, height: 1500))
        XCTAssertEqual(measured.width, 326, accuracy: 1)
        XCTAssertGreaterThan(measured.height, 80)
        XCTAssertLessThan(measured.height, 350)
    }

    func testVerdictAndDeliveryCueReleaseTheirNarrowSlotWhenTheHeroRestacks() {
        for size: DynamicTypeSize in [.small, .large, .xLarge] {
            XCTAssertEqual(EventDetailView.heroVerdictWidth(at: size), 150)
        }
        for size: DynamicTypeSize in [.xxLarge, .xxxLarge, .accessibility1, .accessibility3, .accessibility5] {
            XCTAssertNil(EventDetailView.heroVerdictWidth(at: size))
        }
    }

    func testChartLabelsGrowButLeaveRoomForThePlot() {
        XCTAssertEqual(EventChartTypography.labelSize(scaled: 12), 12)
        XCTAssertEqual(EventChartTypography.labelSize(scaled: 14), 14)
        XCTAssertEqual(EventChartTypography.labelSize(scaled: 16), 16)
        XCTAssertEqual(EventChartTypography.labelSize(scaled: 36), 16)
    }

    func testASevenDayChartKeepsBothDateEndsWithoutCollidingAtPhoneWidths() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let start = Date(timeIntervalSince1970: 1_791_547_200).addingTimeInterval(13 * 3600)
        let domain = start...start.addingTimeInterval(7 * 86400)
        for plotWidth: CGFloat in [180, 220, 280, 340] {
            for scaled: CGFloat in [12, 14, 18, 28, 36] {
                let scale = EventChartTypography.labelSize(scaled: scaled) / 9
                let plan = OddsChartView.xAxisPlan(for: domain, plotWidth: plotWidth, calendar: calendar, labelScale: scale)
                let ticks = OddsChartView.xAxisContextTicks(for: domain, plan: plan, plotWidth: plotWidth,
                                                            labelScale: scale, calendar: calendar)
                XCTAssertEqual(ticks.first, domain.lowerBound)
                XCTAssertEqual(ticks.last, domain.upperBound)
                XCTAssertGreaterThanOrEqual(ticks.count, 2)
                let positions = ticks.map { CGFloat($0.timeIntervalSince(start) / (7 * 86400)) * plotWidth }
                let width = OddsChartView.xAxisLabelWidth(for: plan.labelStyle) * scale
                let centers = OddsChartView.xAxisLabelCenters(tickPositions: positions, plotWidth: plotWidth, labelWidth: width)
                XCTAssertTrue(OddsChartView.xAxisLabelsClear(centers: centers, labelWidth: width))
            }
        }
    }

    func testShortGameClockTicksKeepTheirExistingInstants() {
        let start = Date(timeIntervalSince1970: 1_791_547_200)
        let domain = start...start.addingTimeInterval(2 * 3600)
        let plan = OddsChartView.xAxisPlan(for: domain, plotWidth: 240, labelScale: 16.0 / 9)
        XCTAssertEqual(
            OddsChartView.xAxisContextTicks(for: domain, plan: plan, plotWidth: 240, labelScale: 16.0 / 9),
            OddsChartView.xAxisTicks(for: domain, plan: plan))
    }

    func testLargerAxisLabelsThinTicksInsteadOfOverlapping() {
        let start = Date(timeIntervalSince1970: 1_791_547_200)
        let domain = start...start.addingTimeInterval(7 * 86400)
        for scale: CGFloat in [12.0 / 9, 18.0 / 9, 28.0 / 9] {
            let plan = OddsChartView.xAxisPlan(for: domain, plotWidth: 280, labelScale: scale)
            let ticks = OddsChartView.xAxisTicks(for: domain, plan: plan)
            XCTAssertFalse(ticks.isEmpty)
            let positions = ticks.map { CGFloat($0.timeIntervalSince(start) / (7 * 86400)) * 280 }
            let width = OddsChartView.xAxisLabelWidth(for: plan.labelStyle) * scale
            let centers = OddsChartView.xAxisLabelCenters(tickPositions: positions, plotWidth: 280, labelWidth: width)
            XCTAssertTrue(OddsChartView.xAxisLabelsClear(centers: centers, labelWidth: width))
        }
    }
}
#endif
