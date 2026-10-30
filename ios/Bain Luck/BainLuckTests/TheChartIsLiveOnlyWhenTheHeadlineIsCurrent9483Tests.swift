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
        // #10090 — the displayed number's clock: committed, or a shown preview's own;
        // decision J: aged by a confirmation of it (`displayedProbabilityAgeClock`).
        XCTAssertTrue(args.contains("observedAt: vm.displayedProbabilityAgeClock(event)"),
                      "the chart must read the hero quote's own clock")
        XCTAssertTrue(args.contains("deliveryInterrupted: vm.liveUpdateStatus == .interrupted"))
        // #9483 — on the page's display clock, which is the tick in production.
        XCTAssertTrue(args.contains("now: displayNow(tick.date)"), "the chart must age on the minute tick")
        let mount = try XCTUnwrap(text.range(of: "OddsChartView("))
        XCTAssertLessThan(mount.lowerBound, call.lowerBound, "the argument belongs to the chart mount")
        let before = String(text[..<mount.lowerBound].suffix(120))
        XCTAssertTrue(before.contains("TimelineView(.periodic(from: .now, by: 60)) { tick in"),
                      "with no new price, only the tick can age the edge out")
    }

    // MARK: - A venue-settled verdict is never a current quote

    /// The headline shows a verdict, and no phase label, when the venue has
    /// settled a started game whose status still says "live"; the chart must
    /// not pulse that quote as current beside it. The same existing predicate,
    /// at the same caller, on the same tick.
    func testThePageDeclinesTheChartsCurrentnessOnAVenueSettledVerdict() throws {
        let text = try page()
        let call = try XCTUnwrap(text.range(of: "quoteIsCurrent: EventHeadlinePhase9483.isCurrent("))
        let close = try XCTUnwrap(text.range(of: "now: displayNow(tick.date))", range: call.upperBound..<text.endIndex))
        let rest = text[close.upperBound...]
        XCTAssertTrue(rest.drop(while: \.isWhitespace).hasPrefix("&& !EventState.showsVenueSettledVerdict("),
                      "the verdict decline must be ANDed onto the same argument")
        let end = try XCTUnwrap(rest.range(of: "displayNow(tick.date)),"), "the decline closes the argument on the tick")
        let verdict = String(rest[..<end.upperBound])
        XCTAssertTrue(verdict.contains("event.status, venueSettled: event.venueSettled,"))
        XCTAssertTrue(verdict.contains("commenceTime: event.commenceTime?.asDate, now: displayNow(tick.date))"),
                      "the verdict reads the same tick as the currentness it declines")
        XCTAssertFalse(verdict.contains("venueClosedNoWinner"), "a no-winner close is not this decline")
    }

    /// The predicate the page ANDs on: started + settled at the venue declines
    /// even while status says live; a kick-off still ahead stays eligible as a
    /// fresh pregame quote; false or absent changes nothing.
    func testTheVerdictDeclinesOnlyAStartedSettledGame() {
        let started = now.addingTimeInterval(-3_600), ahead = now.addingTimeInterval(3_600)
        XCTAssertTrue(isCurrent(), "control: a fresh live quote is current before the decline")
        XCTAssertTrue(EventState.showsVenueSettledVerdict("live", venueSettled: true, commenceTime: started, now: now))
        XCTAssertFalse(EventState.showsVenueSettledVerdict("scheduled", venueSettled: true, commenceTime: ahead, now: now))
        XCTAssertTrue(isCurrent(status: "scheduled", commenceIn: 3_600), "and that pregame quote stays current")
        XCTAssertFalse(EventState.showsVenueSettledVerdict("live", venueSettled: false, commenceTime: started, now: now))
        XCTAssertFalse(EventState.showsVenueSettledVerdict("live", venueSettled: nil, commenceTime: started, now: now))
    }
}
