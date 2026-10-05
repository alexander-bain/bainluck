import XCTest
import SwiftUI
import Charts
import UIKit
import Vision
@testable import Bain_Luck

/// #4974 — **on a finished game, the chart shows the probability checkpoints
/// the server recorded, answers a scrub only near one of them, and leaves what
/// nobody recorded empty.**
///
/// `PublicationCheckpointMount4974` is the chart's side of the accepted layer
/// and journey: which checkpoints this chart draws, what a finger lands on, and
/// what the readout may say. Most tests here pin those decisions on real
/// `ChartDataPoint`s and journeys ADOPTED through Lane1b's `adopt` — never a
/// hand-built window. Each refusal is paired with a positive control showing
/// the pre-#4974 path would have printed a number in the same place, so the
/// assertion cannot pass on a fixture that never had a gap to hide.
///
/// The hosted tests at the bottom mount the real chart and readouts.
@MainActor
final class PublicationCheckpointChart4974Tests: XCTestCase {

    private typealias Mount = PublicationCheckpointMount4974
    private typealias Journey = PublicationJourney4974.Journey
    private typealias Checkpoint = PublicationJourney4974.Checkpoint

    /// 2026-10-04T20:15:00Z = 1:15 PM PDT (`PublicationCheckpointLayer4974Tests.t0`).
    private let t0 = Date(timeIntervalSince1970: 1_791_144_900)
    private let eventID = 15_321_333

    // MARK: - Fixtures

    private func at(_ seconds: TimeInterval) -> Date { t0.addingTimeInterval(seconds) }

    private func point(_ seconds: TimeInterval, _ probability: Double,
                       source: String = "aggregate") -> ChartDataPoint {
        ChartDataPoint(date: at(seconds), probability: probability, source: source)
    }

    private func adoptedJourney(
        _ vertices: [(rev: Int64, seconds: TimeInterval, p: Double)],
        event: Int? = nil,
        file: StaticString = #filePath, line: UInt = #line
    ) throws -> Journey {
        let response = PublicationCheckpointsResponse(
            eventId: event ?? eventID,
            schemaVersion: 1,
            timeBasis: "recorded_at_insert_before_commit",
            truncated: false,
            vertices: vertices.map {
                PublicationCheckpointVertex(rev: $0.rev, t: at($0.seconds).ISO8601Format(), p: $0.p)
            })
        switch PublicationJourney4974.adopt(response, expectedEventID: event ?? eventID, finished: true) {
        case .success(let journey): return journey
        case .failure(let refusal):
            XCTFail("expected adoption, got \(refusal)", file: file, line: line)
            throw refusal
        }
    }

    /// Checkpoints at 20:15:10 (rev 7, 61%) and 20:15:50 (rev 9, 58%): a
    /// recorded window inside ONE minute, between legacy readings at 20:15:00
    /// and 20:16:00.
    private func subMinuteJourney() throws -> Journey {
        try adoptedJourney([(7, 10, 0.61), (9, 50, 0.58)])
    }

    private func mount(_ journey: Journey?, _ points: [ChartDataPoint],
                       status: String? = "completed", event: Int? = nil,
                       admits: (Date) -> Bool = { _ in true }) -> Mount? {
        OddsChartView.publicationCheckpointMount(
            journey: journey, eventId: event ?? eventID, status: status,
            points: points, gameStart: nil, admits: admits)
    }

    /// Two plot points per second from 20:15:00: rev 7 sits at x = 20, rev 9 at x = 100.
    private func linearX(_ checkpoint: Checkpoint) -> Double? {
        2 * checkpoint.date.timeIntervalSince(t0)
    }

    private func date(atPlotX x: Double) -> Date { t0.addingTimeInterval(x / 2) }

    private func land(_ mount: Mount, atPlotX x: Double, plotWidth: Double = 400,
                      position: ((Checkpoint) -> Double?)? = nil) -> Mount.Landing {
        mount.landing(cursorX: x, cursorDate: date(atPlotX: x), plotWidth: plotWidth,
                      position: position ?? linearX)
    }

    private func checkpoint(of readout: PublicationCheckpointReadout4974,
                            file: StaticString = #filePath, line: UInt = #line) -> Checkpoint? {
        guard case .checkpoint(let checkpoint) = readout else {
            XCTFail("expected a checkpoint readout, got \(readout)", file: file, line: line)
            return nil
        }
        return checkpoint
    }

    private func legacy(of readout: PublicationCheckpointReadout4974,
                        file: StaticString = #filePath, line: UInt = #line) -> ChartDataPoint? {
        guard case .legacy(let point) = readout else {
            XCTFail("expected a legacy readout, got \(readout)", file: file, line: line)
            return nil
        }
        return point
    }

    private func isWithheld(_ readout: PublicationCheckpointReadout4974) -> Bool {
        if case .withheld = readout { return true }
        return false
    }

    // MARK: - When the mount exists at all

    func testMountsOnlyForThisFinishedEventOverItsBlend() throws {
        let journey = try subMinuteJourney()
        let points = [point(0, 0.40), point(60, 0.55)]
        XCTAssertNotNil(mount(journey, points), "control: this event, finished, over a blend")
        XCTAssertNotNil(mount(journey, points, status: "closed"))
        XCTAssertNil(mount(nil, points), "no journey: today's chart")
        XCTAssertNil(mount(journey, points, event: eventID + 1), "another event's journey")
        XCTAssertNil(mount(journey, points, status: "live"), "a live page")
        XCTAssertNil(mount(journey, points, status: "scheduled"))
        XCTAssertNil(mount(journey, points, status: nil))
        XCTAssertNil(mount(journey, [point(0, 0.40, source: "polymarket"), point(60, 0.55, source: "polymarket")]),
                     "no blend line to stand in for")
    }

    /// The no-journey chart keeps today's fallback exactly: same point, same number.
    func testWithoutAMountTheReadoutIsTodays() {
        let points = [point(0, 0.40), point(60, 0.55)]
        let today = OddsChartSelectionReadout.selectedPoint(at: at(30), in: points, sportKey: nil, pageGaveCard: true)
        XCTAssertEqual(today?.homeProb, 0.40)
        let selection = OddsChartSelection()
        let readout = OddsChartSelectionReadout(selection: selection, readout: card(), dataPoints: points,
                                                sportKey: nil, pageGaveCard: true)
        XCTAssertNil(readout.checkpoints)
        XCTAssertNil(readout.publicationCheckpoints(nil).checkpoints)
        XCTAssertNil(selection.checkpoint)
    }

    // MARK: - A scrub inside the window with no checkpoint in reach

    /// The sub-minute window between two legacy readings: the cursor at
    /// 20:15:30 is 40pt from both checkpoints.
    func testAScrubInTheGapIsWithheldNotIdle() throws {
        let points = [point(0, 0.40), point(60, 0.55)]
        let m = try XCTUnwrap(mount(try subMinuteJourney(), points))

        XCTAssertEqual(land(m, atPlotX: 60), .withheld(at(30)))
        let picked = m.selection(atChartX: 60, plotFrame: CGRect(x: 0, y: 0, width: 400, height: 200),
                                 dateAt: { self.date(atPlotX: Double($0)) },
                                 position: { self.linearX($0).map { CGFloat($0) } })
        XCTAssertEqual(picked.date, at(30), "the crosshair stays under the finger")
        XCTAssertEqual(picked.scrub, .withheld)
        XCTAssertTrue(isWithheld(m.readout(date: picked.date, scrub: picked.scrub)))

        // Recorded in the selection it is still a scrub, not rest.
        let selection = OddsChartSelection()
        selection.hold(date: picked.date, checkpoint: picked.scrub)
        XCTAssertTrue(selection.isScrubbing)
        XCTAssertEqual(selection.checkpoint, .withheld)

        // POSITIVE CONTROL — the pre-#4974 readout prints a number here, and
        // VoiceOver speaks one.
        let old = OddsChartSelectionReadout.selectedPoint(at: at(30), in: points, sportKey: nil, pageGaveCard: true)
        XCTAssertNotNil(old, "the legacy fallback must display a number in this gap for the test to mean anything")
        XCTAssertTrue(OddsChartView.accessibilityValue(dataPoints: points, selectedDate: at(30),
                                                       homeShort: "SEA", awayShort: "LAR").contains("%"))
        XCTAssertEqual(m.accessibilityValue(date: picked.date, scrub: picked.scrub, homeShort: "SEA",
                                            awayShort: "LAR", moments: [], gameFinished: true, sportKey: nil),
                       PublicationCheckpointReadoutSlot4974.withheldText)
    }

    /// The card's own fallback: shown nil, it prints its resting point. The
    /// mounted readout therefore never hands it nil.
    func testTheCardsNilFallbackIsTheDefectBeingAvoided() {
        let page = card(lastPoint: GamePlayPoint(timestamp: at(60).ISO8601Format(), homeProb: 0.77, awayProb: 0.23))
        let shown = page.showing(nil)
        XCTAssertNil(shown.selectedPoint)
        XCTAssertEqual(shown.lastPoint?.homeProb, 0.77, "control: showing(nil) falls back to the page's point")
        XCTAssertEqual(page.resting(on: nil).lastPoint?.homeProb, 0.77, "control: resting(on: nil) keeps it")
    }

    /// An active scrub whose time cannot be resolved stays a withheld scrub.
    func testAScrubWithNoResolvableTimeIsWithheldNotIdle() throws {
        let m = try XCTUnwrap(mount(try subMinuteJourney(), [point(0, 0.40), point(60, 0.55)]))
        let landed = m.landing(cursorX: 60, cursorDate: nil, plotWidth: 400, position: linearX)
        XCTAssertEqual(landed, .withheld(nil))
        let picked = m.selection(atChartX: 60, plotFrame: CGRect(x: 0, y: 0, width: 400, height: 200),
                                 dateAt: { _ in nil }, position: { self.linearX($0).map { CGFloat($0) } })
        XCTAssertNil(picked.date)
        XCTAssertEqual(picked.scrub, .withheld)
        let selection = OddsChartSelection()
        selection.hold(date: picked.date, checkpoint: picked.scrub)
        XCTAssertTrue(selection.isScrubbing, "no time is not no finger")
        XCTAssertTrue(isWithheld(m.readout(date: selection.date, scrub: selection.checkpoint)),
                      "must not resurrect the resting value")
        // A checkpoint in reach still answers without a time.
        XCTAssertEqual(m.landing(cursorX: 22, cursorDate: nil, plotWidth: 400, position: linearX),
                       .checkpoint(m.drawn[0]))
        selection.end()
        XCTAssertFalse(selection.isScrubbing)
        XCTAssertNil(selection.checkpoint)
    }

    // MARK: - Landing on a checkpoint

    func testAScrubSnapsToTheCheckpointsOwnTimeAndValue() throws {
        let m = try XCTUnwrap(mount(try subMinuteJourney(), [point(0, 0.40), point(60, 0.55)]))
        let picked = m.selection(atChartX: 23, plotFrame: CGRect(x: 0, y: 0, width: 400, height: 200),
                                 dateAt: { self.date(atPlotX: Double($0)) },
                                 position: { self.linearX($0).map { CGFloat($0) } })
        guard case .checkpoint(let hit)? = picked.scrub else { return XCTFail("expected a hit, got \(String(describing: picked.scrub))") }
        XCTAssertEqual(hit.vertex.rev, 7)
        XCTAssertEqual(hit.vertex.p, 0.61)
        XCTAssertEqual(hit.vertex.t, at(10).ISO8601Format(), "the served stamp, verbatim")
        XCTAssertEqual(hit.date, at(10))
        XCTAssertEqual(picked.date, at(10), "the crosshair stands on the checkpoint, not the cursor (20:15:11.5)")
        XCTAssertNotEqual(picked.date, date(atPlotX: 23))
        let shown = checkpoint(of: m.readout(date: picked.date, scrub: picked.scrub))
        XCTAssertEqual(shown, hit)
        XCTAssertEqual(m.readout(date: picked.date, scrub: picked.scrub).probability, 0.61)

        // Eight points is the reach, inclusive; nine is not.
        XCTAssertEqual(land(m, atPlotX: 28), .checkpoint(m.drawn[0]))
        XCTAssertEqual(land(m, atPlotX: 29), .withheld(date(atPlotX: 29)))
    }

    func testEqualTimeRevisionsGoToTheGreatestRev() throws {
        let journey = try adoptedJourney([(7, 10, 0.61), (8, 10, 0.63), (9, 50, 0.58), (11, 50, 0.57)])
        let m = try XCTUnwrap(mount(journey, [point(0, 0.40), point(60, 0.55)]))
        guard case .checkpoint(let hit) = land(m, atPlotX: 21) else { return XCTFail("expected a hit") }
        XCTAssertEqual(hit.vertex.rev, 8)
        XCTAssertEqual(hit.vertex.p, 0.63)
        let rest = checkpoint(of: try XCTUnwrap(m.resting))
        XCTAssertEqual(rest?.vertex.rev, 11, "the resting tie goes to the greatest rev too")
        XCTAssertEqual(m.plan.checkpoints.map(\.id), [7, 8, 9, 11], "two revisions at one instant are two dots")
    }

    // MARK: - Hit candidates are the visible checkpoints only

    /// A checkpoint clipped 5pt past the edge would win the unfiltered hit
    /// against a visible one 6pt inside it.
    func testAClippedCheckpointPastTheEdgeCannotCaptureTheFinger() throws {
        let journey = try adoptedJourney([(7, 10, 0.61), (9, 50, 0.58)])
        let m = try XCTUnwrap(mount(journey, [point(0, 0.40), point(60, 0.55)]))
        let xs: [Int64: Double] = [7: 194, 9: 205]
        let landed = m.landing(cursorX: 200, cursorDate: at(30), plotWidth: 200,
                               position: { xs[$0.vertex.rev] })
        guard case .checkpoint(let hit) = landed else { return XCTFail("expected the visible checkpoint, got \(landed)") }
        XCTAssertEqual(hit.vertex.rev, 7)

        // POSITIVE CONTROL — handed every checkpoint, `hit` takes the clipped one.
        XCTAssertEqual(journey.hit(cursorX: 200, position: { xs[$0.vertex.rev] })?.checkpoint.vertex.rev, 9)
    }

    /// A checkpoint with no position is not a candidate; it never reaches
    /// `hit`, which would refuse the whole scrub over it.
    func testACheckpointWithNoPositionDropsOutAloneNotTheScrub() throws {
        let journey = try subMinuteJourney()
        let m = try XCTUnwrap(mount(journey, [point(0, 0.40), point(60, 0.55)]))
        let position: (Checkpoint) -> Double? = { $0.vertex.rev == 7 ? nil : 100 }
        guard case .checkpoint(let hit) = m.landing(cursorX: 98, cursorDate: at(49), plotWidth: 400,
                                                    position: position) else { return XCTFail("expected rev 9") }
        XCTAssertEqual(hit.vertex.rev, 9)
        XCTAssertNil(journey.hit(cursorX: 98, position: position), "control: the unfiltered hit refuses it")
    }

    /// The cursor is plot-local: a 40pt y-axis gutter in front of the plot must
    /// not shift what the finger lands on.
    func testANonzeroPlotOriginIsSubtractedBeforeTheHit() throws {
        let m = try XCTUnwrap(mount(try subMinuteJourney(), [point(0, 0.40), point(60, 0.55)]))
        var asked: [CGFloat] = []
        let frame = CGRect(x: 40, y: 12, width: 200, height: 150)
        let picked = m.selection(atChartX: 63, plotFrame: frame,
                                 dateAt: { asked.append($0); return self.date(atPlotX: Double($0)) },
                                 position: { self.linearX($0).map { CGFloat($0) } })
        XCTAssertEqual(asked, [23], "the time is read at the plot-local x")
        guard case .checkpoint(let hit)? = picked.scrub else { return XCTFail("expected rev 7 at plot x 20") }
        XCTAssertEqual(hit.vertex.rev, 7)
        // Control: the whole-chart x is 43pt from rev 7 and lands on nothing.
        XCTAssertEqual(land(m, atPlotX: 63), .withheld(date(atPlotX: 63)))
    }

    // MARK: - Outside the window: surviving legacy points only

    /// The raw nearest point to 20:15:02 is the in-window 20:15:12 reading the
    /// layer removed.
    func testOutsideTheWindowTheReadoutPicksOnlySurvivingPoints() throws {
        let points = [point(-40, 0.40), point(12, 0.45), point(90, 0.55)]
        let m = try XCTUnwrap(mount(try subMinuteJourney(), points))
        XCTAssertEqual(land(m, atPlotX: 4), .line(at(2)), "16pt from rev 7 and outside the window")
        let shown = legacy(of: m.readout(date: at(2), scrub: nil))
        XCTAssertEqual(shown?.date, at(-40))
        XCTAssertEqual(shown?.probability, 0.40)
        XCTAssertFalse(m.survivors.contains { $0.date == at(12) })

        // POSITIVE CONTROL — the legacy selection names the removed point.
        XCTAssertEqual(OddsChartSelectionReadout.selectedPoint(at: at(2), in: points, sportKey: nil,
                                                               pageGaveCard: true)?.homeProb, 0.45)
    }

    func testReturningOutsideTheWindowRestoresTheLineSelection() throws {
        let points = [point(-40, 0.40), point(0, 0.42), point(60, 0.55), point(120, 0.57)]
        let m = try XCTUnwrap(mount(try subMinuteJourney(), points))
        let selection = OddsChartSelection()
        for x in [60.0, 22, 130] {
            let picked = m.selection(atChartX: CGFloat(x), plotFrame: CGRect(x: 0, y: 0, width: 400, height: 200),
                                     dateAt: { self.date(atPlotX: Double($0)) },
                                     position: { self.linearX($0).map { CGFloat($0) } })
            selection.hold(date: picked.date, checkpoint: picked.scrub)
        }
        XCTAssertNil(selection.checkpoint, "back on the line, the checkpoint state is cleared")
        XCTAssertEqual(selection.date, at(65))
        XCTAssertEqual(legacy(of: m.readout(date: selection.date, scrub: selection.checkpoint))?.date, at(60))
        // A line date inside the window (the Mac's built-in selection) withholds.
        XCTAssertTrue(isWithheld(m.readout(date: at(30), scrub: nil)))
        // No surviving blend point anywhere: a line selection has nothing to name.
        let none = try XCTUnwrap(mount(try subMinuteJourney(), [point(20, 0.4), point(40, 0.5)]))
        XCTAssertTrue(none.survivors.isEmpty)
        XCTAssertTrue(isWithheld(none.readout(date: at(90), scrub: nil)))
    }

    // MARK: - Resting endpoint

    /// The legacy line's last reading sits inside the window; idle must rest on
    /// the drawn checkpoint, not that suppressed point.
    func testIdleRestsOnTheLatestCheckpointWhenTheLinesEndIsSuppressed() throws {
        let points = [point(0, 0.40), point(30, 0.47)]
        let m = try XCTUnwrap(mount(try subMinuteJourney(), points))
        let rest = checkpoint(of: m.readout(date: nil, scrub: nil))
        XCTAssertEqual(rest?.vertex.rev, 9)
        XCTAssertEqual(rest?.vertex.p, 0.58)
        XCTAssertEqual(m.resting?.date, at(50), "its own time")

        // POSITIVE CONTROL — today's resting readout names the suppressed 47%.
        XCTAssertEqual(OddsChartView.fullscreenRestingPoint(in: points, sportKey: nil, pageGaveCard: true)?.homeProb, 0.47)
        XCTAssertEqual(OddsChartView.latestPrimaryPoint(in: points)?.probability, 0.47)
    }

    func testIdleRestsOnALaterSurvivingReading() throws {
        let points = [point(0, 0.40), point(120, 0.71)]
        let m = try XCTUnwrap(mount(try subMinuteJourney(), points))
        let rest = legacy(of: m.readout(date: nil, scrub: nil))
        XCTAssertEqual(rest?.date, at(120))
        XCTAssertEqual(rest?.probability, 0.71)
    }

    func testWithNoEndpointIdleWithholdsInsteadOfThePagesPoint() throws {
        let points = [point(20, 0.45), point(40, 0.50)]
        let m = try XCTUnwrap(mount(try subMinuteJourney(), points, admits: { _ in false }))
        XCTAssertTrue(m.drawn.isEmpty)
        XCTAssertTrue(m.survivors.isEmpty)
        XCTAssertNil(m.resting)
        XCTAssertTrue(isWithheld(m.readout(date: nil, scrub: nil)))
        XCTAssertNil(m.reservePoint(sportKey: nil))
    }

    // MARK: - What the drawn range admits

    func testCheckpointsWidenTheNaturalDomainOnly() throws {
        let legacyDates = [at(0), at(60)]
        let checkpointDates = [at(200)]
        let without = try XCTUnwrap(OddsChartView.naturalDomain(of: legacyDates))
        let with = try XCTUnwrap(OddsChartView.naturalDomain(of: legacyDates + checkpointDates))
        XCTAssertEqual(without, at(-60)...at(120), "the unchanged padding: max(2%, a minute)")
        XCTAssertLessThan(without.upperBound, at(200), "control: the legacy domain alone clips it")
        XCTAssertEqual(with, at(-60)...at(260))
        XCTAssertNil(OddsChartView.naturalDomain(of: []))
    }

    func testTheDrawnRangeAdmitsCheckpointsTheWayItAdmitsPoints() {
        let forced = at(-90)...at(30)
        XCTAssertTrue(OddsChartView.admitsPublicationCheckpoint(at(10), gameEnd: nil, forcedDomain: forced, sinceStart: nil))
        XCTAssertFalse(OddsChartView.admitsPublicationCheckpoint(at(50), gameEnd: nil, forcedDomain: forced, sinceStart: nil),
                       "an externally forced domain wins")
        XCTAssertFalse(OddsChartView.admitsPublicationCheckpoint(at(50), gameEnd: at(40), forcedDomain: nil, sinceStart: nil))
        XCTAssertTrue(OddsChartView.admitsPublicationCheckpoint(at(40), gameEnd: at(40), forcedDomain: nil, sinceStart: nil))
        XCTAssertFalse(OddsChartView.admitsPublicationCheckpoint(at(5), gameEnd: nil, forcedDomain: nil, sinceStart: at(6)))
        XCTAssertTrue(OddsChartView.admitsPublicationCheckpoint(at(6), gameEnd: nil, forcedDomain: nil, sinceStart: at(6)))
    }

    /// rev 9 falls outside the forced domain: it is not drawn and cannot be
    /// hit, and the window it closes still cuts the line — nothing reconnects
    /// 20:15:00 to 20:16:00 and nothing is invented at the domain's edge.
    func testAClippedCheckpointKeepsTheLineBreak() throws {
        let points = [point(-60, 0.40), point(0, 0.42), point(60, 0.55), point(120, 0.57)]
        let forced = at(-90)...at(30)
        let m = try XCTUnwrap(mount(try subMinuteJourney(), points, admits: {
            OddsChartView.admitsPublicationCheckpoint($0, gameEnd: nil, forcedDomain: forced, sinceStart: nil)
        }))
        XCTAssertEqual(m.drawn.map(\.vertex.rev), [7])
        XCTAssertEqual(m.plan.checkpoints.map(\.id), [7])
        XCTAssertEqual(m.journey.window, at(10)...at(50), "the adopted window, not the drawn one")
        for line in m.plan.lines {
            for (a, b) in zip(line.points, line.points.dropFirst()) {
                XCTAssertFalse(a.date <= at(50) && b.date >= at(10),
                               "a segment from \(a.date) to \(b.date) meets the recorded window")
            }
        }
        let inputIDs = Set(points.map(\.id))
        XCTAssertTrue(m.survivors.allSatisfy { inputIDs.contains($0.id) }, "no point fabricated")
        XCTAssertEqual(m.survivors.map(\.date), [at(-60), at(0), at(60), at(120)])
        XCTAssertEqual(land(m, atPlotX: 100), .withheld(at(50)), "the clipped rev 9 answers nothing")
    }

    // MARK: - Formatting

    func testADrawPricedSportPrintsNoAwayComplement() throws {
        let m = try XCTUnwrap(mount(try subMinuteJourney(), [point(0, 0.40), point(60, 0.55)]))
        let rev7 = m.drawn[0]
        let soccer = PublicationCheckpointReadoutSlot4974.playPoint(for: rev7, sportKey: "soccer_epl")
        XCTAssertEqual(soccer.homeProb, 0.61)
        XCTAssertNil(soccer.awayProb, "a draw is not the away team (#5271)")
        let football = PublicationCheckpointReadoutSlot4974.playPoint(for: rev7, sportKey: "americanfootball_nfl")
        XCTAssertEqual(try XCTUnwrap(football.awayProb), 0.39, accuracy: 1e-9, "control: a two-way sport prints it")

        let spoken = m.accessibilityValue(date: rev7.date, scrub: .checkpoint(rev7), homeShort: "ARS",
                                          awayShort: "CHE", moments: [], gameFinished: true, sportKey: "soccer_epl")
        XCTAssertTrue(spoken.hasPrefix("ARS 61%"), spoken)
        XCTAssertFalse(spoken.contains("CHE"), spoken)
        let twoWay = m.accessibilityValue(date: rev7.date, scrub: .checkpoint(rev7), homeShort: "SEA",
                                          awayShort: "LAR", moments: [], gameFinished: true,
                                          sportKey: "americanfootball_nfl")
        XCTAssertTrue(twoWay.contains("LAR 39%"), twoWay)
    }

    /// No score, period, clock, play or result rides on a checkpoint, even when
    /// the nearest legacy reading carries all of them.
    func testACheckpointInheritsNoGameState() throws {
        var scored = point(0, 0.40)
        scored.homeScore = 14
        scored.awayScore = 7
        scored.period = "Q2"
        scored.clock = "4:12"
        let m = try XCTUnwrap(mount(try subMinuteJourney(), [scored, point(60, 0.55)]))
        let play = PublicationCheckpointReadoutSlot4974.playPoint(for: m.drawn[0], sportKey: nil)
        XCTAssertNil(play.homeScore)
        XCTAssertNil(play.awayScore)
        XCTAssertNil(play.period)
        XCTAssertNil(play.clock)
        XCTAssertNil(play.scoringPlay)
        XCTAssertEqual(play.timestamp, "", "the card prints no device-zone clock for it")
        let spoken = m.accessibilityValue(date: at(10), scrub: .checkpoint(m.drawn[0]), homeShort: "SEA",
                                          awayShort: "LAR", moments: [], gameFinished: true, sportKey: nil)
        XCTAssertFalse(spoken.contains("score"), spoken)
        XCTAssertFalse(spoken.contains("Q2"), spoken)
    }

    func testTheCheckpointClockIsPacificToTheMinute() {
        let us = Locale(identifier: "en_US")
        func normalized(_ s: String) -> String {
            s.replacingOccurrences(of: "\u{202F}", with: " ").replacingOccurrences(of: "\u{00A0}", with: " ")
        }
        // 20:15:50Z in October is PDT.
        XCTAssertEqual(normalized(PublicationCheckpointReadoutSlot4974.clock(at(50), dated: false, locale: us)),
                       "1:15 PM PT")
        // December is PST: the zone, not a fixed offset.
        let december = Date(timeIntervalSince1970: 1_796_156_150) // 2026-12-01T20:15:50Z
        XCTAssertEqual(normalized(PublicationCheckpointReadoutSlot4974.clock(december, dated: false, locale: us)),
                       "12:15 PM PT")
        let dated = normalized(PublicationCheckpointReadoutSlot4974.clock(at(50), dated: true, locale: us))
        XCTAssertTrue(dated.hasPrefix("Sun"), dated)
        XCTAssertTrue(dated.hasSuffix("1:15 PM PT"), dated)
        XCTAssertFalse(dated.contains(":50"), "minute precision")
        for word in ["publish", "deliver", "sent", "post"] {
            XCTAssertFalse(dated.lowercased().contains(word))
        }
    }

    // MARK: - Nothing inferred across the window

    /// The legacy pair either side of the window crosses 50% (40% → 60%), and
    /// so do the two checkpoints (45% → 55%). Neither pair is joined, so no
    /// line can carry a favourite flip through the window.
    func testNoFlipIsDrawnFromCheckpointsOrACrossWindowPair() throws {
        let journey = try adoptedJourney([(7, 10, 0.45), (9, 50, 0.55)])
        let points = [point(-60, 0.38), point(0, 0.40), point(60, 0.60), point(120, 0.62)]
        let m = try XCTUnwrap(mount(journey, points))
        XCTAssertEqual(m.plan.lines.map { $0.points.map(\.date) }, [[at(-60), at(0)], [at(60), at(120)]])
        for line in m.plan.lines {
            let probabilities = line.points.map(\.probability)
            XCTAssertTrue(probabilities.allSatisfy { $0 < 0.5 } || probabilities.allSatisfy { $0 > 0.5 },
                          "a drawn run crosses 50%: \(probabilities)")
        }
        let linePointDates = Set(m.plan.lines.flatMap { $0.points.map(\.date) })
        XCTAssertTrue(m.plan.checkpoints.allSatisfy { !linePointDates.contains($0.date) })

        // POSITIVE CONTROL — without the mount the chart draws 0s → 60s as one run.
        let today = OddsChartView.observationSegments(points, gameStart: nil)
        XCTAssertEqual(today.count, 1)
        XCTAssertTrue(zip(today[0], today[0].dropFirst()).contains { $0.probability < 0.5 && $1.probability > 0.5 })
    }

    /// The balance ink colors the line home above 50% and away below; under a
    /// mount it would redraw the blend uncut and color a crossing nobody
    /// recorded. The body is not rendered in tests, so this reads the source.
    func testTheMountedChartRunsNoBalanceInkAndNoLiveSplit() throws {
        let chart = try code("Bain Luck/Components/OddsChartView.swift")
        XCTAssertTrue(chart.contains("letliveSplit=checkpoints==nil?liveEdgeSplit(dataPoints:dataPoints,domain:domain):nil"))
        XCTAssertTrue(chart.contains("letbalance=checkpoints==nil?balancePlan(dataPoints:dataPoints,liveSplit:liveSplit,domain:domain):nil"))
        XCTAssertTrue(chart.contains("ifletcheckpoints{PublicationCheckpointLayer4974(plan:checkpoints.plan,"))
    }

    /// A moment inside the window would sit on the line the window removed.
    func testNoMomentIsDrawnOnTheSuppressedLine() throws {
        let points = [point(0, 0.40), point(30, 0.47), point(60, 0.55)]
        let m = try XCTUnwrap(mount(try subMinuteJourney(), points))
        let raw = [
            GameMomentPoint(ts: at(30).ISO8601Format(), label: "Touchdown", confidence: 0.9, momentType: nil,
                            actorTeam: nil, probDelta: 0.2, period: "Q2"),
            GameMomentPoint(ts: at(58).ISO8601Format(), label: "Field goal", confidence: 0.9, momentType: nil,
                            actorTeam: nil, probDelta: 0.05, period: "Q2"),
        ]
        let moments = m.moments(from: raw)
        XCTAssertEqual(moments.map(\.label), ["Field goal"])
        XCTAssertEqual(moments.first?.probability, 0.55, "anchored on a surviving reading")
        // POSITIVE CONTROL — today the touchdown sits on the suppressed 47%.
        XCTAssertEqual(OddsChartView.chartMoments(from: raw, points: points).first { $0.label == "Touchdown" }?.probability,
                       0.47)
    }

    // MARK: - Wiring (comment-stripped, whitespace-free scans)

    private func code(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    /// Inline and fullscreen take one mount, built the same way.
    func testInlineAndFullscreenShareOneIntegration() throws {
        let chart = try code("Bain Luck/Components/OddsChartView.swift")
        XCTAssertEqual(chart.components(separatedBy: "letcheckpoints=checkpointMount(for:dataPoints)").count - 1, 2)
        XCTAssertEqual(chart.components(separatedBy: "periodMarkers:periodMarkers,moments:moments,checkpoints:checkpoints,").count - 1, 2)
        XCTAssertTrue(chart.contains("pageGaveCard:readout!=nil).publicationCheckpoints(checkpoints)"))
        XCTAssertTrue(chart.contains("gameFinished:EventState.isFinished(status),checkpoints:checkpoints,"))
        XCTAssertEqual(chart.components(separatedBy: "checkpoints.selection(atChartX:location.x,plotFrame:plotFrame,proxy:proxy)").count - 1, 2,
                       "both the pan and the hold decide over the mount")
    }

    /// The finger's state stays in the selection leaves: the plot owner still
    /// holds the selection in plain `@State` and never observes it.
    func testFingerStateStaysInTheSelectionLeaves() throws {
        let chart = try code("Bain Luck/Components/OddsChartView.swift")
        XCTAssertTrue(chart.contains("@Stateprivatevarselection:OddsChartSelection"))
        XCTAssertFalse(chart.contains("@ObservedObjectvarselection"))
        XCTAssertFalse(chart.contains("selection.checkpoint"), "the plot owner reads the finger's state")
        let leaves = try code("Bain Luck/Components/OddsChartSelection.swift")
        XCTAssertEqual(leaves.components(separatedBy: "scrub:selection.checkpoint").count - 1, 3,
                       "the fullscreen readout, the floating card and VoiceOver")
    }

    // MARK: - Hosted renders

    private func card(lastPoint: GamePlayPoint? = nil) -> GamePlayCardView {
        GamePlayCardView(homeTeam: "Seattle Seahawks", awayTeam: "Los Angeles Rams", lastPoint: lastPoint)
    }

    private func pump(_ host: UIViewController, times: Int = 5) {
        for _ in 0..<times {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
    }

    private func visibleText(_ host: UIViewController, name: String) throws -> String {
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("4974-chart-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("#4974 rendered evidence: \(url.path)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    private func hosted<V: View>(_ view: V, width: CGFloat = 390, height: CGFloat = 844)
        -> (UIViewController, UIWindow) {
        let host = hostForMeasurement(view.frame(width: width), at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: height)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        pump(host, times: 12)
        return (host, window)
    }

    /// The fullscreen readout: withheld in the gap where the old readout printed
    /// the legacy 40%, the checkpoint's own 61% on a hit, and at rest the later
    /// of the last checkpoint (20:15:50) and the last surviving reading
    /// (20:16:00, 55%) — never the page's 77%.
    func testHostedFullscreenReadoutWithholdsTheGapAndPrintsTheCheckpoint() throws {
        let points = [point(0, 0.40), point(60, 0.55)]
        let m = try XCTUnwrap(mount(try subMinuteJourney(), points))
        let page = card(lastPoint: GamePlayPoint(timestamp: at(60).ISO8601Format(), homeProb: 0.77, awayProb: 0.23))
            .pinningProbabilities().finished(true)

        // POSITIVE CONTROL — today's readout prints a number in the gap.
        let oldSelection = OddsChartSelection()
        oldSelection.select(at(30))
        let (oldHost, oldWindow) = hosted(OddsChartSelectionReadout(selection: oldSelection, readout: page,
                                                                    dataPoints: points, sportKey: nil))
        defer { oldWindow.isHidden = true }
        let oldText = try visibleText(oldHost, name: "fullscreen-old-gap")
        XCTAssertTrue(oldText.contains("%"), "the legacy readout must print a number in this gap: \(oldText)")

        let selection = OddsChartSelection()
        let readout = OddsChartSelectionReadout(selection: selection, readout: page, dataPoints: points,
                                                sportKey: nil).publicationCheckpoints(m)
        let (host, window) = hosted(readout)
        defer { window.isHidden = true }

        selection.hold(date: at(30), checkpoint: .withheld)
        pump(host)
        let gap = try visibleText(host, name: "fullscreen-gap")
        XCTAssertTrue(gap.contains(PublicationCheckpointReadoutSlot4974.withheldText), gap)
        XCTAssertFalse(gap.contains("%"), "a number leaked into the withheld readout: \(gap)")

        selection.hold(date: at(10), checkpoint: .checkpoint(m.drawn[0]))
        pump(host)
        let hit = try visibleText(host, name: "fullscreen-hit")
        XCTAssertTrue(hit.contains("61%"), hit)
        XCTAssertTrue(hit.contains("PT"), hit)
        XCTAssertFalse(hit.contains("77%"), hit)

        selection.end()
        pump(host)
        let rest = try visibleText(host, name: "fullscreen-rest")
        XCTAssertTrue(rest.contains("55%"), "rest on the later endpoint, the 20:16 reading: \(rest)")
        XCTAssertFalse(rest.contains("77%"), "the page's point leaked into the resting readout: \(rest)")
    }

    private func finishedPayload() throws -> EventHistoryResponse {
        let line: [[String: Any]] = [(0.0, 0.40), (60.0, 0.55)].map {
            ["timestamp": at($0.0).ISO8601Format(), "home_probability": $0.1]
        }
        let data = try JSONSerialization.data(withJSONObject: [
            "event_id": eventID, "home_team": "Seattle Seahawks", "away_team": "Los Angeles Rams",
            "status": "completed", "history": [], "win_prob_history": ["polymarket": line],
            "aggregate_line": line,
        ])
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: data)
    }

    /// The inline chart's floating card: withheld in the gap, absent at rest,
    /// and every scrub over the mounted chart leaves the data marks unbuilt
    /// (#8651's guard, preserved).
    func testHostedInlineChartWithholdsTheGapWithoutRebuildingThePlot() throws {
        let payload = try finishedPayload()
        let journey = try subMinuteJourney()
        let model = OddsChartViewModel(eventId: eventID, preloaded: payload)
        let selection = OddsChartSelection()
        var plotBuilds = 0
        model.onPlotBuild = { plotBuilds += 1 }
        defer { model.onPlotBuild = nil }
        let chart = OddsChartView(eventId: eventID, status: "completed",
                                  homeTeamName: "Seattle Seahawks", awayTeamName: "Los Angeles Rams",
                                  preloadedHistory: payload, readout: card(), publicationJourney: journey,
                                  model: model, selection: selection)
        let (host, window) = hosted(chart)
        defer { window.isHidden = true }
        XCTAssertGreaterThan(plotBuilds, 0, "the real plot must render for this test to mean anything")
        let before = plotBuilds

        selection.hold(date: at(30), checkpoint: .withheld)
        pump(host)
        let gap = try visibleText(host, name: "inline-gap")
        XCTAssertTrue(gap.contains(PublicationCheckpointReadoutSlot4974.withheldText), gap)

        for step in 0..<10 {
            let scrub: PublicationCheckpointScrub4974 = step.isMultiple(of: 2) ? .checkpoint(journey.checkpoints[0]) : .withheld
            selection.change(date: at(Double(10 + step)), translation: CGSize(width: 30 + step, height: 2),
                             checkpoint: scrub)
            pump(host, times: 1)
        }
        XCTAssertTrue(selection.isScrubbing)
        XCTAssertEqual(plotBuilds, before, "a scrub over the mounted chart re-evaluated the Chart marks")

        selection.end()
        pump(host)
        XCTAssertEqual(plotBuilds, before, "releasing rebuilt the data plot")
        let rest = try visibleText(host, name: "inline-rest")
        XCTAssertFalse(rest.contains(PublicationCheckpointReadoutSlot4974.withheldText),
                       "the inline card rests nowhere (#9517): \(rest)")
    }
}
