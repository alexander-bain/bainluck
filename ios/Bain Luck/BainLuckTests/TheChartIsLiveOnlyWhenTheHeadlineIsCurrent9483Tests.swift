import XCTest
@testable import Bain_Luck

/// #9483 Argon P1 — the chart's live treatment (the dot and number on the end
/// of the line, the arrival ring) follows the headline's currentness, on the
/// quote's own clock. Before this, `LiveEdgeReading.current` admitted on status
/// and value alone, so a quote the headline called "last recorded" (stale,
/// undated, interrupted, started but not live) could still pulse as current.
///
/// The value admission itself (`LiveEdgeReading.current`, `edgeVertex`) is
/// unchanged; the rendered half is
/// `TheLiveChartEndCarriesTheHeroNumber9436Tests.testAQuoteThatIsNotCurrentKeepsTheLineAndDrawsNoNumber`.
final class TheChartIsLiveOnlyWhenTheHeadlineIsCurrent9483Tests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_790_000_000)

    private func isCurrent(
        status: String? = "live", commenceIn: TimeInterval? = -3_600, isOpeningLine: Bool = false,
        observedAgo: TimeInterval? = 60, interrupted: Bool = false
    ) -> Bool {
        EventHeadlinePhase9483.isCurrent(
            status: status, commenceTime: commenceIn.map { now.addingTimeInterval($0) },
            isOpeningLine: isOpeningLine,
            observedAt: observedAgo.map { now.addingTimeInterval(-$0) },
            deliveryInterrupted: interrupted, now: now)
    }

    func testAFreshLiveQuoteIsCurrent() {
        XCTAssertTrue(isCurrent())
    }

    func testAFreshQuoteBeforeTheOffIsCurrent() {
        XCTAssertTrue(isCurrent(status: "scheduled", commenceIn: 3_600))
    }

    func testAStaleQuoteIsNotCurrent() {
        XCTAssertTrue(isCurrent(observedAgo: SourceAge.liveStaleAfter), "control: at the bound")
        XCTAssertFalse(isCurrent(observedAgo: SourceAge.liveStaleAfter + 1))
    }

    func testAnUndatedQuoteIsNotCurrent() {
        XCTAssertFalse(isCurrent(observedAgo: nil))
    }

    func testAnInterruptedQuoteIsNotCurrent() {
        XCTAssertFalse(isCurrent(interrupted: true))
    }

    func testAStartedGameThatIsNotLiveIsNotCurrent() {
        XCTAssertFalse(isCurrent(status: "suspended"))
        XCTAssertFalse(isCurrent(status: "scheduled", commenceIn: -60))
        XCTAssertFalse(isCurrent(status: "scheduled", commenceIn: nil), "an undated game fails closed")
    }

    func testFinishedAndOpeningLineHeroesAreNotCurrent() {
        XCTAssertFalse(isCurrent(status: "final"))
        XCTAssertFalse(isCurrent(isOpeningLine: true))
    }

    /// The helper is the label's own decision, never a second rule: every
    /// case above agrees with `resolve` on the same inputs.
    func testItIsExactlyTheHeadlinesDecision() {
        for status in ["live", "scheduled", "suspended", "final", nil] as [String?] {
            for commence in [-3_600, 3_600, nil] as [TimeInterval?] {
                for observed in [60, SourceAge.liveStaleAfter + 1, nil] as [TimeInterval?] {
                    for interrupted in [false, true] {
                        let phase = EventHeadlinePhase9483.resolve(
                            status: status, commenceTime: commence.map { now.addingTimeInterval($0) },
                            isOpeningLine: false, observedAt: observed.map { now.addingTimeInterval(-$0) },
                            deliveryInterrupted: interrupted, now: now)
                        XCTAssertEqual(
                            isCurrent(status: status, commenceIn: commence, observedAgo: observed,
                                      interrupted: interrupted),
                            phase == .current, "\(String(describing: status)) \(String(describing: commence)) \(String(describing: observed)) \(interrupted)")
                    }
                }
            }
        }
    }

    // MARK: - The page hands the chart that decision, on the minute tick

    private func page() throws -> String {
        let here = URL(fileURLWithPath: #filePath)
        let url = here.deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testThePageGivesTheChartTheHeadlinesCurrentnessOnTheQuotesClock() throws {
        let text = try page()
        XCTAssertEqual(text.components(separatedBy: "OddsChartView(").count - 1, 1, "control: one chart mount")
        let call = try XCTUnwrap(text.range(of: "quoteIsCurrent: EventHeadlinePhase9483.isCurrent("))
        let args = String(text[call.upperBound...].prefix(600))
        XCTAssertTrue(args.contains("observedAt: event.heroProbabilityObservedAt?.asDate"),
                      "the chart must read the hero quote's own clock")
        XCTAssertTrue(args.contains("deliveryInterrupted: vm.liveUpdateStatus == .interrupted"))
        XCTAssertTrue(args.contains("now: tick.date"), "the chart must age on the minute tick")
        let mount = try XCTUnwrap(text.range(of: "OddsChartView("))
        XCTAssertLessThan(mount.lowerBound, call.lowerBound, "the argument belongs to the chart mount")
        let before = String(text[..<mount.lowerBound].suffix(120))
        XCTAssertTrue(before.contains("TimelineView(.periodic(from: .now, by: 60)) { tick in"),
                      "with no new price, only the tick can age the edge out")
    }
}
