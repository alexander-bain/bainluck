import XCTest
@testable import Bain_Luck

/// #10830 — Alex on installed build 46 (South Carolina–Florida, Oct 10):
/// "'start live activity' gets too much prime real estate, and win probability
/// needs more V space"; the headline card had "weigh empty space" below Live
/// updates; and the Live updates popup was large, repeated the receipt time, and
/// described the hero's confidence with inputs the hero never reads.
final class TheEventPageGivesTheChartTheRoom10830Tests: XCTestCase {

    private func code(_ directory: String, _ file: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(directory)
            .appendingPathComponent(file)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    private func span(_ text: String, from start: String, to end: String) throws -> String {
        let lower = try XCTUnwrap(text.range(of: start), "moved: \(start)")
        let rest = text[lower.upperBound...]
        let upper = rest.range(of: end)?.lowerBound ?? rest.endIndex
        return String(rest[..<upper])
    }

    // MARK: - Live Activity is secondary

    func testTheLiveActivityControlFollowsTheChartCard() throws {
        let content = try span(code("Views", "EventDetailView.swift"),
                               from: "privatevarcontentView:someView{",
                               to: "staticfuncgameMarketsHaveContent(")
        let hero = try XCTUnwrap(content.range(of: "heroSection(event)"))
        let chart = try XCTUnwrap(content.range(of: "OddsChartView(eventId:"))
        let control = try XCTUnwrap(content.range(of: "GameActivityControl(snapshot:reading)"))
        XCTAssertLessThan(hero.lowerBound, chart.lowerBound)
        XCTAssertLessThan(chart.lowerBound, control.lowerBound,
                          "Start Live Activity stands between the hero and the chart again")
        XCTAssertEqual(content.components(separatedBy: "GameActivityControl(").count - 1, 1)
    }

    func testTheControlIsCompactButKeepsItsTargetAndBothActions() throws {
        let control = try code("Components", "GameActivityControl.swift")
        XCTAssertTrue(control.contains("compactAction(\"StartLiveActivity\""))
        XCTAssertTrue(control.contains("compactAction(\"StopLiveActivity\""))
        XCTAssertTrue(control.contains(".accessibilityIdentifier(\"game.activity.start\")"))
        XCTAssertTrue(control.contains(".accessibilityIdentifier(\"game.activity.stop\")"))
        let action = try span(control, from: "privatefunccompactAction(", to: "nonisolatedstructGameActivityControlPresentation")
        XCTAssertTrue(action.contains(".font(.footnote"), "the control is body-sized again")
        XCTAssertTrue(action.contains(".frame(minHeight:44"), "the 44pt touch target")
    }

    // MARK: - The chart gets the room

    func testThePhoneChartIsTallerThanBuild46() {
        XCTAssertGreaterThan(OddsChartView.phoneChartHeight, 260)
    }

    func testThePhoneChartReadsTheOneConstant() throws {
        let chart = try code("Components", "OddsChartView.swift")
        XCTAssertTrue(chart.contains("guardsizeClass==.regularelse{returnSelf.phoneChartHeight}"))
    }

    // MARK: - The headline card fits its content

    func testStackedTheCaptionRidesThePaddingAndOtherwiseKeepsItsSlot() throws {
        let page = try code("Views", "EventDetailView.swift")
        XCTAssertTrue(page.contains(
            "letcaptionRidesPadding=stacked&&!dynamicTypeSize.isAccessibilitySize"),
            "accessibility sizes outgrow the padding; a row never had the band")
        XCTAssertTrue(page.contains(
            "probabilityDetails(confidenceTier:confidenceTier).overlay(alignment:.bottom){"
            + "ifpriceStreamingEligible&&captionRidesPadding{"
            + "movementCaptionSlot(event,colors:colors).alignmentGuide(.bottom){$0[.top]}"),
            "the stacked caption reserves a band under Live updates again")
        XCTAssertTrue(page.contains(
            "ifpriceStreamingEligible&&!shown.isOpeningLine&&!captionRidesPadding{"
            + "movementCaptionSlot(event,colors:colors)}"),
            "the caption lost its slot where it cannot ride the padding")
        XCTAssertEqual(page.components(separatedBy: "LivePriceMovementCaption(").count - 1, 1)
    }

    // MARK: - The popup is compact and says what the hero reads

    func testTodaysReceiptPrintsTheClockOnly() throws {
        let calendar = Calendar(identifier: .gregorian)
        let now = try XCTUnwrap(calendar.date(from: DateComponents(
            year: 2026, month: 10, day: 10, hour: 15, minute: 37, second: 13)))
        let receivedAt = now.addingTimeInterval(-17)
        let text = FreshnessRevealView.receiptClock(receivedAt, now: now, calendar: calendar)
        XCTAssertFalse(text.contains("2026"), text)
        XCTAssertFalse(text.contains("Oct"), text)
        XCTAssertEqual(text, receivedAt.formatted(date: .omitted, time: .standard))
    }

    func testAnEarlierDaysReceiptKeepsItsDate() throws {
        let calendar = Calendar(identifier: .gregorian)
        let now = try XCTUnwrap(calendar.date(from: DateComponents(
            year: 2026, month: 10, day: 10, hour: 0, minute: 5)))
        let receivedAt = now.addingTimeInterval(-15 * 60)
        let text = FreshnessRevealView.receiptClock(receivedAt, now: now, calendar: calendar)
        XCTAssertEqual(text, receivedAt.formatted(date: .abbreviated, time: .standard))
    }

    func testTheExactReceiptStaysInTheAccessibleDetail() throws {
        let feedback = try code("Components", "LivePriceChangeFeedback.swift")
        let reveal = try span(feedback, from: "structFreshnessRevealView:View{", to: "privatefuncreceipt(")
        XCTAssertTrue(reveal.contains(
            ".accessibilityLabel(\"Receivedonthisdeviceat\\(lastReceivedAt.formatted(date:.abbreviated,time:.standard)).\")"))
    }

    func testTheHeroBasisNamesOnlyWhatTheHeroReads() {
        let basis = Confidence.heroBasis.lowercased()
        XCTAssertTrue(basis.contains("source"))
        XCTAssertTrue(basis.contains("moved") || basis.contains("movement"))
        for absent in ["liquidity", "freshness", "volume"] {
            XCTAssertFalse(basis.contains(absent), "the hero tier never reads \(absent): \(basis)")
        }
    }

    func testThePopupDescribesTheHeroTierAndSeparatesItFromDelivery() throws {
        let feedback = try code("Components", "LivePriceChangeFeedback.swift")
        let reveal = try span(feedback, from: "structFreshnessRevealView:View{", to: "privatefuncreceipt(")
        XCTAssertTrue(reveal.contains("Text(Confidence.heroBasis)"))
        XCTAssertFalse(reveal.contains("Confidence.tooltip"))
        let tier = try XCTUnwrap(reveal.range(of: "iflettier=Confidence.normalize(confidenceTier){"))
        let rest = reveal[tier.upperBound...]
        XCTAssertTrue(rest.hasPrefix("Divider()"), "confidence reads as part of the delivery status again")
    }

    func testTheHeroStillComputesItsTierFromSourcesAndMovementOnly() throws {
        let page = try code("Views", "EventDetailView.swift")
        XCTAssertTrue(page.contains(
            "letconfidenceTier=Confidence.fromSources(sourceCount:event.winProbabilitySources?.count,"
            + "hasMovement:event.openingOdds?.homeProbability"),
            "the hero's inputs changed; re-word Confidence.heroBasis with them")
    }
}
