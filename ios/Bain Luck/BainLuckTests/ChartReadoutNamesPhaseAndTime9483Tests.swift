import XCTest
@testable import Bain_Luck

/// #9483 — **an inspected chart reading names its subject, chance, phase and
/// observation time, and the pregame baseline reads as pregame.**
///
/// The design review of `5f542c7b96` (scope §2) and Native's field inventory
/// found subject and chance on every path, checkpoint time already spoken, and
/// two holes: nothing said "Pregame" (or "Final" on a finished line's settled
/// end), so a pregame point printed only a wall clock, the same as a point in a
/// timeout with no state; and VoiceOver never spoke a legacy point's time.
///
/// Every positive below is paired with the same reading WITHOUT the chart's
/// context — what the readout said before — so no assertion can pass on a
/// fixture that never lacked the field.
@MainActor
final class ChartReadoutNamesPhaseAndTime9483Tests: XCTestCase {

    /// 2026-10-04T20:15:00Z, a Sunday.
    private let t0 = Date(timeIntervalSince1970: 1_791_144_900)
    private let utc = TimeZone(identifier: "UTC")!
    private let us = Locale(identifier: "en_US")

    private func at(_ seconds: TimeInterval) -> Date { t0.addingTimeInterval(seconds) }

    private func point(_ seconds: TimeInterval, _ p: Double, source: String = "aggregate") -> ChartDataPoint {
        ChartDataPoint(date: at(seconds), probability: p, source: source)
    }

    /// Kickoff an hour after `t0`; "today" is `t0`'s day unless `now` says otherwise.
    private func context(playStart: Date? = nil, terminal: Date? = nil,
                         now: Date? = nil) -> ChartReadoutContext9483 {
        ChartReadoutContext9483(playStart: playStart, terminal: terminal,
                                timeZone: utc, locale: us, now: now ?? t0)
    }

    private func plain(_ s: String) -> String {
        s.replacingOccurrences(of: "\u{202F}", with: " ").replacingOccurrences(of: "\u{00A0}", with: " ")
    }

    // MARK: - Spoken, legacy series

    func testAPregameReadingIsSpokenAsPregameWithItsTime() {
        let ctx = context(playStart: at(3600))
        let spoken = OddsChartView.selectionReadout(for: point(0, 0.61), homeShort: "SEA",
                                                    awayShort: "LAR", context: ctx)
        XCTAssertEqual(plain(spoken), "SEA 61%, LAR 39%, Pregame, 8:15 PM")
        // BEFORE — no phase, no time: indistinguishable from a stateless in-play point.
        XCTAssertEqual(OddsChartView.selectionReadout(for: point(0, 0.61), homeShort: "SEA",
                                                      awayShort: "LAR"), "SEA 61%, LAR 39%")
    }

    func testAnInPlayReadingKeepsItsStateAndGainsItsTime() {
        var live = point(4500, 0.54)
        live.homeScore = 14
        live.awayScore = 7
        live.period = "Q3"
        live.clock = "13:31"
        let spoken = OddsChartView.selectionReadout(for: live, homeShort: "PHI", awayShort: "JAX",
                                                    context: context(playStart: at(3600)))
        XCTAssertEqual(plain(spoken), "PHI 54%, JAX 46%, score 14–7, Q3, 13:31, 9:30 PM")
        XCTAssertFalse(spoken.contains("Pregame"))
        XCTAssertEqual(OddsChartView.selectionReadout(for: live, homeShort: "PHI", awayShort: "JAX"),
                       "PHI 54%, JAX 46%, score 14–7, Q3, 13:31", "before: no time")
    }

    /// A state carried onto a pre-start point is not play: the badge is Pregame.
    func testAPregameReadingSpeaksNoCarriedPeriodOrClock() {
        var early = point(0, 0.61)
        early.period = "Q1"
        early.clock = "15:00"
        let spoken = OddsChartView.selectionReadout(for: early, homeShort: "SEA", awayShort: "LAR",
                                                    context: context(playStart: at(3600)))
        XCTAssertEqual(plain(spoken), "SEA 61%, LAR 39%, Pregame, 8:15 PM")
    }

    /// No start the page trusts (the stored start is not a kickoff) ⇒ nothing is
    /// called Pregame; the time is still spoken.
    func testNoPlayStartMeansNoPregameWord() {
        let spoken = OddsChartView.selectionReadout(for: point(0, 0.61), homeShort: "SEA",
                                                    awayShort: "LAR", context: context())
        XCTAssertEqual(plain(spoken), "SEA 61%, LAR 39%, 8:15 PM")
    }

    func testAnEarlierDaysReadingCarriesItsWeekday() {
        let spoken = OddsChartView.selectionReadout(
            for: point(0, 0.61), homeShort: "SEA", awayShort: "LAR",
            context: context(playStart: at(3600), now: at(2 * 86_400)))
        XCTAssertEqual(plain(spoken), "SEA 61%, LAR 39%, Pregame, Sun 8:15 PM")
    }

    /// The end falls after UTC midnight, so it is dated (Monday) against Sunday.
    func testAFinishedLinesSettledEndIsSpokenAsFinal() {
        let end = point(14_400, 1.0)
        let ctx = context(playStart: at(3600), terminal: end.date)
        let spoken = OddsChartView.selectionReadout(for: end, homeShort: "LAC", awayShort: "GSW",
                                                    gameFinished: true, context: ctx)
        XCTAssertEqual(plain(spoken), "LAC 100%, GSW 0%, Final, Mon 12:15 AM")
        XCTAssertEqual(OddsChartView.selectionReadout(for: end, homeShort: "LAC", awayShort: "GSW",
                                                      gameFinished: true),
                       "LAC 100%, GSW 0%", "before: no phase")
    }

    /// A finished line that stops short of 0 or 1 ends on a quote, not a result.
    func testAFinishedLineEndingOnAQuoteIsNotCalledFinal() {
        let end = point(14_400, 0.97)
        let spoken = OddsChartView.selectionReadout(
            for: end, homeShort: "LAC", awayShort: "GSW", gameFinished: true,
            context: context(playStart: at(3600), terminal: end.date))
        XCTAssertFalse(spoken.contains("Final"), spoken)
        XCTAssertTrue(spoken.hasPrefix("LAC 97%, GSW 3%"), spoken)
    }

    /// ESPN's settled row already says Final; it is not said twice.
    func testAFinalStateIsNotRepeated() {
        var end = point(14_400, 0.0)
        end.period = "Final"
        end.homeScore = 101
        end.awayScore = 104
        let spoken = OddsChartView.selectionReadout(
            for: end, homeShort: "LAC", awayShort: "GSW", gameFinished: true,
            context: context(playStart: at(3600), terminal: end.date))
        XCTAssertEqual(plain(spoken), "LAC 0%, GSW 100%, score 101–104, Final, Mon 12:15 AM")
    }

    func testTheChartsAccessibilityValuePassesTheContextThrough() {
        let points = [point(0, 0.40), point(4500, 0.55), point(14_400, 1.0)]
        let ctx = context(playStart: at(3600), terminal: at(14_400))
        let resting = OddsChartView.accessibilityValue(dataPoints: points, selectedDate: nil,
                                                       homeShort: "H", awayShort: "A",
                                                       gameFinished: true, context: ctx)
        XCTAssertEqual(plain(resting), "H 100%, A 0%, Final, Mon 12:15 AM")
        let scrubbed = OddsChartView.accessibilityValue(dataPoints: points, selectedDate: at(60),
                                                        homeShort: "H", awayShort: "A",
                                                        gameFinished: true, context: ctx)
        XCTAssertEqual(plain(scrubbed), "H 40%, A 60%, Pregame, 8:15 PM")
    }

    // MARK: - Visible card badge

    func testTheCardBadgeSaysPregameFinalOrTheState() {
        let ctx = context(playStart: at(3600), terminal: at(14_400))
        XCTAssertEqual(OddsChartView.playPoint(for: point(0, 0.61), sportKey: nil, context: ctx).badgeDisplay,
                       "Pregame")
        XCTAssertEqual(OddsChartView.playPoint(for: point(0, 0.61), sportKey: nil).badgeDisplay, "",
                       "before: a pregame point printed no badge at all")

        var live = point(4500, 0.54)
        live.period = "Q3"
        live.clock = "13:31"
        let livePlay = OddsChartView.playPoint(for: live, sportKey: nil, context: ctx)
        XCTAssertEqual(livePlay.badgeDisplay, livePlay.timeDisplay, "in play the state badge is unchanged")
        XCTAssertFalse(livePlay.badgeDisplay.isEmpty)

        XCTAssertEqual(OddsChartView.playPoint(for: point(14_400, 1.0), sportKey: nil, context: ctx).badgeDisplay,
                       "Final")
        var overtime = point(14_400, 1.0)
        overtime.period = "Final/OT"
        let ot = OddsChartView.playPoint(for: overtime, sportKey: nil, context: ctx)
        XCTAssertEqual(ot.badgeDisplay, ot.timeDisplay, "a state that already says Final stays")
        XCTAssertTrue(ot.badgeDisplay.contains("OT"))
    }

    /// The card prints the phase badge, not the bare state badge.
    func testTheCardPrintsTheBadgeWithThePhase() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/GamePlayCardView.swift")
        let card = try String(contentsOf: url, encoding: .utf8).filter { !$0.isWhitespace }
        XCTAssertTrue(card.contains("if!point.badgeDisplay.isEmpty{Text(point.badgeDisplay)"))
        XCTAssertFalse(card.contains("Text(point.timeDisplay)"), "the card bypasses the phase badge")
    }

    func testTheFullscreenRestingAndScrubbedCardsCarryThePhase() {
        let points = [point(0, 0.40), point(4500, 0.55), point(14_400, 0.0)]
        let ctx = context(playStart: at(3600), terminal: at(14_400))
        XCTAssertEqual(OddsChartView.fullscreenRestingPoint(in: points, sportKey: nil, pageGaveCard: true,
                                                            context: ctx)?.phase, .final)
        XCTAssertEqual(OddsChartSelectionReadout.selectedPoint(at: at(30), in: points, sportKey: nil,
                                                               pageGaveCard: true, context: ctx)?.phase, .pregame)
        XCTAssertNil(OddsChartSelectionReadout.selectedPoint(at: at(4500), in: points, sportKey: nil,
                                                             pageGaveCard: true, context: ctx)?.phase)
    }

    // MARK: - The chart's context

    /// The fullscreen readout and the inline overlay (card + VoiceOver) both
    /// take the chart's context; a site that drops it reads as before, silently.
    func testBothChartReadoutSitesTakeTheContext() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/OddsChartView.swift")
        let chart = try String(contentsOf: url, encoding: .utf8).filter { !$0.isWhitespace }
        XCTAssertEqual(chart.components(separatedBy: ".readingPhases(readoutContext(dataPoints:dataPoints,checkpoints:checkpoints,").count - 1, 2)
        XCTAssertTrue(chart.contains(".publicationCheckpoints(checkpoints).readingPhases(readoutContext("),
                      "the fullscreen readout lost its phases")
        XCTAssertTrue(chart.contains("sportKey:sportKey,floatingCard:floatingCard).readingPhases(readoutContext("),
                      "the inline overlay lost its phases")
        XCTAssertTrue(chart.contains("return.chart(playStart:sinceStartDate,gameFinished:EventState.isFinished(status),"),
                      "the phase must read the chart's own Since Start cut, not a new start rule")
    }

    func testTheChartContextUsesTheReadoutSeriesEndOnlyWhenFinished() {
        let points = [point(0, 0.40), point(4500, 0.55)]
        XCTAssertNil(ChartReadoutContext9483.chart(playStart: at(3600), gameFinished: false,
                                                   readoutPoints: points, checkpoints: nil).terminal)
        let done = ChartReadoutContext9483.chart(playStart: at(3600), gameFinished: true,
                                                 readoutPoints: points, checkpoints: nil)
        XCTAssertEqual(done.terminal, at(4500))
        XCTAssertEqual(done.playStart, at(3600))
    }

    // MARK: - Publication checkpoints

    private func checkpointMount(points: [ChartDataPoint]) throws -> PublicationCheckpointMount4974 {
        let response = PublicationCheckpointsResponse(
            eventId: 15_321_333, schemaVersion: 1, timeBasis: "recorded_at_insert_before_commit",
            truncated: false,
            vertices: [PublicationCheckpointVertex(rev: 7, t: at(10).ISO8601Format(), p: 0.61),
                       PublicationCheckpointVertex(rev: 9, t: at(50).ISO8601Format(), p: 0.58)])
        guard case .success(let journey) = PublicationJourney4974.adopt(
            response, expectedEventID: 15_321_333, finished: true) else {
            throw XCTSkip("adoption refused the fixture")
        }
        return try XCTUnwrap(OddsChartView.publicationCheckpointMount(
            journey: journey, eventId: 15_321_333, status: "completed",
            points: points, gameStart: nil, admits: { _ in true }))
    }

    func testACheckpointBeforeKickoffIsSpokenAndPrintedAsPregame() throws {
        let m = try checkpointMount(points: [point(0, 0.40), point(60, 0.55)])
        let rev7 = m.drawn[0]
        let ctx = context(playStart: at(3600))
        let spoken = m.accessibilityValue(date: rev7.date, scrub: .checkpoint(rev7), homeShort: "SEA",
                                          awayShort: "LAR", moments: [], gameFinished: true,
                                          sportKey: nil, context: ctx)
        XCTAssertEqual(plain(spoken), "SEA 61%, LAR 39%, Pregame, 1:15 PM PT")
        let before = m.accessibilityValue(date: rev7.date, scrub: .checkpoint(rev7), homeShort: "SEA",
                                          awayShort: "LAR", moments: [], gameFinished: true, sportKey: nil)
        XCTAssertFalse(before.contains("Pregame"), "before: no phase on a checkpoint")
        XCTAssertEqual(PublicationCheckpointReadoutSlot4974.playPoint(for: rev7, sportKey: nil, context: ctx)
                        .badgeDisplay, "Pregame")
        // Still no game state rides on a checkpoint (#4974).
        let play = PublicationCheckpointReadoutSlot4974.playPoint(for: rev7, sportKey: nil, context: ctx)
        XCTAssertNil(play.period)
        XCTAssertNil(play.homeScore)
    }

    func testTheWithheldReadingStaysExactlyAsItWas() throws {
        let m = try checkpointMount(points: [point(0, 0.40), point(60, 0.55)])
        let spoken = m.accessibilityValue(date: at(30), scrub: .withheld, homeShort: "SEA",
                                          awayShort: "LAR", moments: [], gameFinished: true,
                                          sportKey: nil, context: context(playStart: at(3600)))
        XCTAssertEqual(spoken, PublicationCheckpointReadoutSlot4974.withheldText)
    }
}
