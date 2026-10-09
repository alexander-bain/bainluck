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
        let host = UIHostingController(rootView: content)
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
        }.environment(\.dynamicTypeSize, .accessibility3)
        let host = UIHostingController(rootView: content)
        let measured = host.sizeThatFits(in: CGSize(width: 326, height: 1500))
        XCTAssertEqual(measured.width, 326, accuracy: 1)
        XCTAssertGreaterThan(measured.height, 80)
        XCTAssertLessThan(measured.height, 350)
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
