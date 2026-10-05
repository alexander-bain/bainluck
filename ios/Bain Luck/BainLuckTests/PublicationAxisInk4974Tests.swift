import XCTest
import SwiftUI
import Charts
import UIKit
import Vision
@testable import Bain_Luck

/// #4974 — **a finished game's stored checkpoints widen the time axis to their
/// insertion times; the market prices and score rows stamped in that widened
/// tail stay off the chart, and the final score is not carried across it.**
///
/// The page hands both charts two windows: `forcedDomain`, widened to the
/// latest stored checkpoint, is the axis and decides which checkpoints are
/// drawn and scrubbed; `legacyDataDomain`, the page's ORIGINAL window, bounds
/// every legacy reading, score row and the final-score carry.
///
/// The fixture is Root's discriminating case: the original window ends at
/// 20:17:30; checkpoints were stored at 20:20 and 20:21, so the axis ends at
/// 20:21:30; the blend drifts to 31% at 20:18 and 29% at 20:19, and the score
/// changes at the same two times — all INSIDE each chart's own finish clip and
/// OUTSIDE the original window. Every refusal is paired with the same input
/// without the legacy window (today's chart), which draws the drift; removing
/// the new bound turns each of those assertions red.
///
/// Authored by latency; compiled and executed only by Native.
@MainActor
final class PublicationAxisInk4974Tests: XCTestCase {

    private typealias Mount = PublicationCheckpointMount4974
    private typealias Journey = PublicationJourney4974.Journey
    private typealias Checkpoint = PublicationJourney4974.Checkpoint

    /// 2026-10-04T20:15:00Z (`PublicationCheckpointChart4974Tests.t0`).
    private let t0 = Date(timeIntervalSince1970: 1_791_144_900)
    private let eventID = 15_321_333

    private func at(_ seconds: TimeInterval) -> Date { t0.addingTimeInterval(seconds) }

    /// Kick-off, 19:15:00.
    private var kickoff: Date { at(-3_600) }
    /// The page's original window ends here: 20:17:30.
    private var legacyEnd: Date { at(150) }
    /// The widened axis ends 30 s after the latest stored checkpoint: 20:21:30.
    private var axisEnd: Date { at(390) }

    private static let ranges: [OddsTimeRange] = [.all, .sinceStart]

    /// Where each range's windows open: All at 18:13:20, Since Start at kick-off.
    /// The caller passes the same lower bound in both windows.
    private func opening(_ range: OddsTimeRange) -> Date { range == .all ? at(-7_300) : kickoff }
    private func axis(_ range: OddsTimeRange) -> ClosedRange<Date> { opening(range)...axisEnd }
    private func legacy(_ range: OddsTimeRange) -> ClosedRange<Date> { opening(range)...legacyEnd }

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    /// A finished game. ESPN's win probability runs from 18:15 to 20:17:30, so
    /// the probability chart's own finish clip is 20:19:30 (last ESPN + 120 s).
    /// The blend's last reading in the original window is 57% at 20:17:30; then
    /// it drifts to 31% at 20:18 and 29% at 20:19. `blend: false` serves none.
    private func payload(blend: Bool = true) throws -> EventHistoryResponse {
        func rows(_ pairs: [(TimeInterval, Double)]) -> [[String: Any]] {
            pairs.map { ["timestamp": self.at($0.0).ISO8601Format(), "home_probability": $0.1] }
        }
        var object: [String: Any] = [
            "event_id": eventID, "home_team": "Seattle Seahawks", "away_team": "Los Angeles Rams",
            "status": "completed", "history": [],
            "win_prob_history": ["espn": rows([(-7_200, 0.46), (-3_600, 0.50), (-1_800, 0.62), (150, 0.90)])],
        ]
        if blend {
            object["aggregate_line"] = rows([(-7_200, 0.45), (-3_600, 0.50), (-1_800, 0.62), (60, 0.66),
                                            (150, 0.57), (180, 0.31), (240, 0.29)])
        }
        let data = try JSONSerialization.data(withJSONObject: object)
        return try Self.decoder().decode(EventHistoryResponse.self, from: data)
    }

    /// Stored at 20:20:00 (rev 7, 93%) and 20:21:00 (rev 9, 96%), adopted
    /// through the strict contract — never a hand-built journey.
    private func lateJourney(event: Int? = nil) throws -> Journey {
        let id = event ?? eventID
        let body = PublicationCheckpointsResponse(
            eventId: id, schemaVersion: 1, timeBasis: "recorded_at_insert_before_commit",
            truncated: false,
            vertices: [PublicationCheckpointVertex(rev: 7, t: at(300).ISO8601Format(), p: 0.93),
                       PublicationCheckpointVertex(rev: 9, t: at(360).ISO8601Format(), p: 0.96)])
        return try PublicationJourney4974.adopt(body, expectedEventID: id, finished: true).get()
    }

    /// The probability chart's points, composed as `OddsChartView.filterPoints`
    /// composes them for this finished game: its finish clip, the axis, the
    /// legacy window, then Since Start. `testTheChartsFilterRunsTheseStepsInOrder`
    /// pins the private function to exactly these steps. `legacy: nil` is the
    /// chart without the correction.
    private func drawn(_ history: EventHistoryResponse, axis: ClosedRange<Date>?,
                       legacy: ClosedRange<Date>?, range: OddsTimeRange) throws -> [ChartDataPoint] {
        let end = try XCTUnwrap(OddsChartView.gameEndDate(status: "completed", history: history))
        var points = OddsChartView.chartPoints(from: history)
            .filter { $0.date <= end }
            .filter { SharedChartWindow.contains($0.date, in: axis) }
        if let legacy {
            points = points.filter { SharedChartWindow.contains($0.date, in: legacy) }
        }
        return OddsChartView.sinceStartWindow(points, range: range, kickoff: kickoff)
    }

    /// The chart's checkpoint mount, under the admission the chart applies: the
    /// axis and, for Since Start, the kick-off cut. No legacy window.
    private func mount(_ journey: Journey?, _ points: [ChartDataPoint], range: OddsTimeRange,
                       status: String = "completed", event: Int? = nil) -> Mount? {
        OddsChartView.publicationCheckpointMount(
            journey: journey, eventId: event ?? eventID, status: status, points: points,
            gameStart: kickoff, forcedDomain: axis(range),
            sinceStart: range == .sinceStart ? kickoff : nil)
    }

    private func blend(_ points: [ChartDataPoint]) -> [ChartDataPoint] {
        points.filter { $0.source == Mount.blendSource }
    }

    private func signature(_ points: [ChartDataPoint]) -> [String] {
        points.map { "\($0.source)@\($0.date.timeIntervalSince1970)=\($0.probability)" }
    }

    private func legacyPoint(of readout: PublicationCheckpointReadout4974?,
                             file: StaticString = #filePath, line: UInt = #line) -> ChartDataPoint? {
        guard case .legacy(let point)? = readout else {
            XCTFail("expected a legacy readout, got \(String(describing: readout))", file: file, line: line)
            return nil
        }
        return point
    }

    private func checkpoint(of readout: PublicationCheckpointReadout4974?,
                            file: StaticString = #filePath, line: UInt = #line) -> Checkpoint? {
        guard case .checkpoint(let checkpoint)? = readout else {
            XCTFail("expected a checkpoint readout, got \(String(describing: readout))", file: file, line: line)
            return nil
        }
        return checkpoint
    }

    // MARK: - The probability chart

    /// The fixture IS the case, or nothing below means anything: the drift sits
    /// inside the chart's own finish clip and after the original window, and
    /// both stored dots sit after that window and inside the axis.
    func testTheFixtureIsRootsDiscriminatingCase() throws {
        let history = try payload()
        let finish = try XCTUnwrap(OddsChartView.gameEndDate(status: "completed", history: history))
        XCTAssertEqual(finish, at(270), "the chart's own finish clip: the last ESPN reading + 120 s")
        for drift in [at(180), at(240)] {
            XCTAssertLessThanOrEqual(drift, finish, "the drift must survive the chart's own finish clip")
            XCTAssertGreaterThan(drift, legacyEnd, "the drift must lie outside the original window")
        }
        let journey = try lateJourney()
        XCTAssertEqual(journey.checkpoints.map(\.date), [at(300), at(360)])
        for range in Self.ranges {
            XCTAssertTrue(journey.checkpoints.allSatisfy { !legacy(range).contains($0.date) && axis(range).contains($0.date) },
                          "\(range): every stored dot is past the original window and inside the axis")
        }
    }

    /// Both ranges. The dots stay drawn and a finger near one hits it; the
    /// widened tail's prices are not drawn, and a finger there outside the
    /// recorded window reads the original window's last reading, 57%. Without
    /// the legacy window the same chart draws 31% and 29% and reads 29%.
    func testTheStoredDotsStayAndTheWidenedTailsPricesStayOff() throws {
        let history = try payload()
        let journey = try lateJourney()
        for range in Self.ranges {
            let points = try drawn(history, axis: axis(range), legacy: legacy(range), range: range)
            XCTAssertFalse(points.contains { $0.date > legacyEnd }, "\(range): a widened-tail reading is drawn")
            XCTAssertEqual(blend(points).last?.date, legacyEnd, "\(range)")
            XCTAssertEqual(blend(points).last?.probability, 0.57, "\(range)")

            let m = try XCTUnwrap(mount(journey, points, range: range), "\(range): the mount must exist")
            XCTAssertEqual(m.drawn.map(\.vertex.rev), [7, 9], "\(range): the stored dots stay drawn")
            XCTAssertEqual(m.plan.checkpoints.map(\.id), [7, 9], "\(range)")
            XCTAssertEqual(m.survivors.last?.date, legacyEnd, "\(range): the line ends at the original window")
            XCTAssertEqual(checkpoint(of: m.resting)?.vertex.rev, 9, "\(range): the line rests on the stored 96%")

            // A finger 3 plot points right of rev 9, on a plot laid out over the AXIS.
            let width = 4_000.0
            let span = axis(range).upperBound.timeIntervalSince(axis(range).lowerBound)
            let lower = axis(range).lowerBound
            let position: (Checkpoint) -> Double? = { width * $0.date.timeIntervalSince(lower) / span }
            let rev9 = try XCTUnwrap(position(m.drawn[1]))
            XCTAssertEqual(m.landing(cursorX: rev9 + 3, cursorDate: nil, plotWidth: width, position: position),
                           .checkpoint(m.drawn[1]), "\(range): the stored dot is hittable")

            let read = legacyPoint(of: m.readout(date: at(240), scrub: nil))
            XCTAssertEqual(read?.date, legacyEnd, "\(range)")
            XCTAssertEqual(read?.probability, 0.57, "\(range): the finger read a widened-tail price")

            // MUTANT — the same chart without the legacy window draws the drift
            // and the finger reads it. This is what the bound removes.
            let unbounded = try drawn(history, axis: axis(range), legacy: nil, range: range)
            XCTAssertEqual(blend(unbounded).suffix(2).map(\.date), [at(180), at(240)], "\(range)")
            let um = try XCTUnwrap(mount(journey, unbounded, range: range))
            XCTAssertEqual(um.drawn.map(\.vertex.rev), [7, 9], "\(range)")
            XCTAssertEqual(um.survivors.last?.date, at(240), "\(range)")
            XCTAssertEqual(legacyPoint(of: um.readout(date: at(240), scrub: nil))?.probability, 0.29, "\(range)")
        }
    }

    /// Moments and the readout are chosen from the drawn points (the mount's
    /// survivors), so a moment stamped in the widened tail has nothing to sit on.
    func testAMomentInTheWidenedTailHasNoLineToSitOn() throws {
        let history = try payload()
        let range = OddsTimeRange.sinceStart
        let raw = [
            GameMomentPoint(ts: at(60).ISO8601Format(), label: "Field goal", confidence: 0.9, momentType: nil,
                            actorTeam: nil, probDelta: 0.05, period: "Q4"),
            GameMomentPoint(ts: at(240).ISO8601Format(), label: "Line move", confidence: 0.9, momentType: nil,
                            actorTeam: nil, probDelta: -0.2, period: "Q4"),
        ]
        let points = try drawn(history, axis: axis(range), legacy: legacy(range), range: range)
        let m = try XCTUnwrap(mount(try lateJourney(), points, range: range))
        XCTAssertEqual(m.moments(from: raw).map(\.label), ["Field goal"])
        XCTAssertFalse(OddsChartView.chartMoments(from: raw, points: points).contains { $0.label == "Line move" },
                       "the unmounted chart drops it too: it draws no tail reading")
        // POSITIVE CONTROL — without the legacy window the move sits on the drift.
        let unbounded = try drawn(history, axis: axis(range), legacy: nil, range: range)
        XCTAssertEqual(OddsChartView.chartMoments(from: raw, points: unbounded).first { $0.label == "Line move" }?.probability,
                       0.29)
    }

    /// No legacy window is today's chart, and so is one that admits the whole
    /// axis. An explicit legacy window never admits a mark outside the axis,
    /// and with no axis the legacy window alone bounds the line.
    func testWithoutALegacyWindowTheChartIsTodaysAndBothBoundsIntersect() throws {
        let history = try payload()
        for range in Self.ranges {
            let today = signature(try drawn(history, axis: axis(range), legacy: nil, range: range))
            XCTAssertEqual(signature(try drawn(history, axis: axis(range), legacy: axis(range), range: range)), today,
                           "\(range): a legacy window equal to the axis changes nothing")
            XCTAssertEqual(signature(try drawn(history, axis: axis(range), legacy: at(-90_000)...at(90_000), range: range)),
                           today, "\(range): a wider legacy window admits nothing outside the axis")
        }
        // All's legacy window opens before Since Start's axis: the axis still cuts.
        let crossed = try drawn(history, axis: axis(.sinceStart), legacy: legacy(.all), range: .all)
        XCTAssertFalse(crossed.contains { $0.date < kickoff }, "the legacy window admitted a reading left of the axis")
        XCTAssertFalse(crossed.contains { $0.date > legacyEnd })
        XCTAssertTrue(crossed.contains { $0.date == kickoff }, "control: the intersection is not empty")
        // No axis (nil forcedDomain): the legacy window alone bounds; the finish clip still runs.
        XCTAssertEqual(blend(try drawn(history, axis: nil, legacy: legacy(.all), range: .all)).last?.date, legacyEnd)
        XCTAssertEqual(blend(try drawn(history, axis: nil, legacy: nil, range: .all)).last?.date, at(240),
                       "control: with neither window only the finish clip runs, and the drift is today's ink")
    }

    /// The legacy window draws no checkpoint and invents nothing: another
    /// event's, a live page's or a missing journey mounts nothing, and a payload
    /// with no blend keeps its refusal — the widened tail stays empty.
    func testOnlyAMatchingFinishedBlendMountsAndTheTailIsNeverFilledIn() throws {
        let range = OddsTimeRange.sinceStart
        let journey = try lateJourney()
        let points = try drawn(try payload(), axis: axis(range), legacy: legacy(range), range: range)
        XCTAssertNotNil(mount(journey, points, range: range), "control: the matching finished blend mounts")
        XCTAssertNil(mount(journey, points, range: range, event: eventID + 1), "another event's journey")
        XCTAssertNil(mount(try lateJourney(event: eventID + 1), points, range: range), "a journey adopted for another event")
        XCTAssertNil(mount(journey, points, range: range, status: "live"), "a live page")
        XCTAssertNil(mount(nil, points, range: range), "no journey")

        let noBlend = try drawn(try payload(blend: false), axis: axis(range), legacy: legacy(range), range: range)
        XCTAssertFalse(noBlend.isEmpty, "control: the venue line is still there")
        XCTAssertTrue(blend(noBlend).isEmpty)
        XCTAssertNil(mount(journey, noBlend, range: range), "no blend: no checkpoint is drawn or scrubbed")
        XCTAssertFalse(noBlend.contains { $0.date > legacyEnd }, "nothing is drawn in the widened tail")
    }

    /// The axis and the checkpoints answer to the widened window only: the
    /// original window would refuse both dots, and nothing on the admission or
    /// axis path reads it.
    func testTheAxisAndTheDotsAnswerToTheWidenedWindowOnly() throws {
        for range in Self.ranges {
            for date in [at(300), at(360)] {
                XCTAssertTrue(OddsChartView.admitsPublicationCheckpoint(date, forcedDomain: axis(range), sinceStart: nil),
                              "\(range)")
                XCTAssertFalse(legacy(range).contains(date), "\(range): control — the original window refuses it")
            }
        }
        let chart = try code("Bain Luck/Components/OddsChartView.swift")
        let mounting = try XCTUnwrap(chart.range(of: "privatefunccheckpointMount(for"))
        let admission = try XCTUnwrap(chart.range(of: "staticfuncadmitsPublicationCheckpoint(",
                                                  range: mounting.upperBound..<chart.endIndex))
        let close = try XCTUnwrap(chart.range(of: "returntrue}", range: admission.upperBound..<chart.endIndex))
        XCTAssertFalse(chart[mounting.lowerBound..<close.upperBound].contains("legacyDataDomain"),
                       "the checkpoint mount or its admission reads the legacy window")
        let axisStart = try XCTUnwrap(chart.range(of: "privatefuncxAxisDomain("))
        let axisClose = try XCTUnwrap(chart.range(of: "staticfuncnaturalDomain(", range: axisStart.upperBound..<chart.endIndex))
        let axisBody = chart[axisStart.lowerBound..<axisClose.lowerBound]
        XCTAssertTrue(axisBody.contains("ifletforced=forcedDomain{returnforced}"))
        XCTAssertFalse(axisBody.contains("legacyDataDomain"), "the axis reads the legacy window")
    }

    /// `filterPoints` is private and reads view state, so its steps are pinned
    /// by source: the finish clip, the axis, the legacy window, then Since
    /// Start, in that order — the composition `drawn` replays. Inline and
    /// fullscreen both draw from it.
    func testTheChartsFilterRunsTheseStepsInOrder() throws {
        let chart = try code("Bain Luck/Components/OddsChartView.swift")
        let start = try XCTUnwrap(chart.range(of: "privatefuncfilterPoints(_points:[ChartDataPoint])->[ChartDataPoint]{"))
        let end = try XCTUnwrap(chart.range(of: "returnSelf.sinceStartWindow(filtered,range:drawnRange,kickoff:sinceStartDate)}",
                                            range: start.upperBound..<chart.endIndex))
        let body = chart[start.upperBound..<end.upperBound]
        var cursor = body.startIndex
        for step in [
            "ifEventState.isFinished(status),letendDate=gameEndDate{filtered=filtered.filter{$0.date<=endDate}}",
            "ifletforcedDomain{filtered=filtered.filter{SharedChartWindow.contains($0.date,in:forcedDomain)}}",
            "ifletlegacyDataDomain{filtered=filtered.filter{SharedChartWindow.contains($0.date,in:legacyDataDomain)}}",
            "guardisGameStartedelse{returnfiltered}",
        ] {
            let found = try XCTUnwrap(body.range(of: step, range: cursor..<body.endIndex), "missing or out of order: \(step)")
            cursor = found.upperBound
        }
        XCTAssertEqual(chart.components(separatedBy: "letdataPoints=filterPoints(enrichedPoints)").count - 1, 2,
                       "the inline and fullscreen charts draw from the one filter")
        XCTAssertTrue(chart.contains("forcedDomain:ClosedRange<Date>?=nil,legacyDataDomain:ClosedRange<Date>?=nil,"),
                      "the input defaults to nil, so every existing caller draws as before")
        XCTAssertTrue(chart.contains("self.legacyDataDomain=legacyDataDomain"))
    }

    // MARK: - The score chart

    /// The final margin is carried to the original window's end, never past the
    /// axis, and to the axis's edge when there is no legacy window (#9175).
    func testTheFinalScoreIsCarriedToTheOriginalWindowNotTheWidenedEdge() {
        for range in Self.ranges {
            XCTAssertEqual(ScoreDifferentialChartView.actualCarryEdge(axis: axis(range), legacyDataDomain: legacy(range)),
                           legacyEnd, "\(range)")
            XCTAssertEqual(ScoreDifferentialChartView.actualCarryEdge(axis: axis(range), legacyDataDomain: nil),
                           axisEnd, "\(range): no legacy window is today's edge")
            XCTAssertEqual(ScoreDifferentialChartView.actualCarryEdge(axis: axis(range),
                                                                      legacyDataDomain: opening(range)...at(9_000)),
                           axisEnd, "\(range): never past the axis")
        }
        let readings: [(date: Date, diff: Double)] = [(at(-540), 0), (at(-300), 7), (at(60), 7)]
        let edge = ScoreDifferentialChartView.actualCarryEdge(axis: axis(.all), legacyDataDomain: legacy(.all))
        let steps = ScoreDifferentialChartView.actualSteps(readings, carriedTo: edge)
        XCTAssertEqual(steps.map { $0.date }, [at(-540), at(-300), at(60), legacyEnd])
        XCTAssertEqual(steps.last?.diff, 7, "the carry repeats the final margin; no score is manufactured")
        // MUTANT — today's carry runs to the widened edge.
        XCTAssertEqual(ScoreDifferentialChartView.actualSteps(readings, carriedTo: axisEnd).last?.date, axisEnd)
    }

    /// The score chart's rows take the axis cut AND the legacy window; the
    /// carry reads `actualCarryEdge`; the projection still starts from the axis
    /// (the caller passes the same lower bound in both); the axis is
    /// `forcedDomain`. The new property sits directly after `forcedDomain`, so
    /// the memberwise initializer takes it there and defaults it to nil.
    func testTheScoreChartCutsItsRowsAndCarryByTheLegacyWindow() throws {
        let score = try code("Bain Luck/Components/ScoreDifferentialChartView.swift")
        XCTAssertTrue(score.contains(
            "letcontained=merged.filter{SharedChartWindow.contains($0.date,in:forcedDomain)}.filter{SharedChartWindow.contains($0.date,in:legacyDataDomain)}"))
        XCTAssertTrue(score.contains("ifletendDate{returncontained.filter{$0.date<=endDate}}"), "the finish clip stays")
        XCTAssertTrue(score.contains("carriedTo:Self.actualCarryEdge(axis:domain,legacyDataDomain:legacyDataDomain))"))
        XCTAssertFalse(score.contains("carriedTo:domain.upperBound"))
        XCTAssertTrue(score.contains("range:range,gameStart:startDate,window:forcedDomain)"))
        XCTAssertTrue(score.contains("ifletforced=forcedDomain{returnforced}"))
        XCTAssertTrue(score.contains("varforcedDomain:ClosedRange<Date>?varlegacyDataDomain:ClosedRange<Date>?varpageAxisPlotWidth"))
    }

    /// The score rows: 0–0 at 20:06, 7–0 at 20:10, 10–3 at 20:16 (the final),
    /// then 10–10 at 20:18 and 17–10 at 20:19. `completed_at` 20:17:30, so the
    /// score chart's own finish clip is 20:19:30 and both late rows survive it.
    private func scoreHistory() throws -> EventHistoryResponse {
        func row(_ seconds: TimeInterval, _ home: Int, _ away: Int) -> [String: Any] {
            ["timestamp": at(seconds).ISO8601Format(), "home_score": home, "away_score": away]
        }
        let object: [String: Any] = [
            "event_id": eventID, "home_team": "Seattle Seahawks", "away_team": "Los Angeles Rams",
            "status": "completed", "completed_at": legacyEnd.ISO8601Format(), "history": [],
            "score_history": [row(-540, 0, 0), row(-300, 7, 0), row(60, 10, 3), row(180, 10, 10), row(240, 17, 10)],
        ]
        let data = try JSONSerialization.data(withJSONObject: object)
        return try Self.decoder().decode(EventHistoryResponse.self, from: data)
    }

    /// The real score chart, rasterised at 3x, and the right-most column of its
    /// teal actual-score ink. Its axis opens at 20:05 and ends at 20:21:30.
    private func scoreRaster(legacy: ClosedRange<Date>?, name: String) throws -> (png: Data, tealMaxX: Int) {
        let view = ScoreDifferentialChartView(
            history: try scoreHistory(),
            homeTeam: "Seattle Seahawks",
            awayTeam: "Los Angeles Rams",
            sportKey: "americanfootball_nfl",
            commenceTime: at(-600).ISO8601Format(),
            eventStatus: "completed",
            homeTeamColor: .blue,
            awayTeamColor: .gray,
            homeTeamAbbrev: "SEA",
            awayTeamAbbrev: "LAR",
            forcedDomain: at(-600)...axisEnd,
            legacyDataDomain: legacy
        )
        .padding(16)
        .frame(width: 390)
        let renderer = rendererForMeasurement(view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("4974-axis-ink-score-\(name).png")
        try? png.write(to: url)
        print("#4974 axis-ink score render [\(name)]: \(url.path)")
        let maxX = try tealMaxX(image)
        return (png, maxX)
    }

    /// The right-most x holding the actual-score teal (#0d9488): green and blue
    /// high and close, red low. The home blue and the grey are excluded.
    private func tealMaxX(_ image: UIImage) throws -> Int {
        let cg = try XCTUnwrap(image.cgImage)
        let width = cg.width, height = cg.height
        var bytes = [UInt8](repeating: 0, count: width * height * 4)
        let drew = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(data: buffer.baseAddress, width: width, height: height,
                                          bitsPerComponent: 8, bytesPerRow: width * 4,
                                          space: CGColorSpaceCreateDeviceRGB(),
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
            context.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        XCTAssertTrue(drew, "could not read the raster")
        var maxX = -1
        for y in 0..<height {
            for x in 0..<width {
                let i = (y * width + x) * 4
                let r = Int(bytes[i]), g = Int(bytes[i + 1]), b = Int(bytes[i + 2]), a = Int(bytes[i + 3])
                if a > 200, r < 70, g > 110, b > 100, abs(g - b) < 35 { maxX = max(maxX, x) }
            }
        }
        return maxX
    }

    /// The real score chart. With the legacy window its teal line stops at the
    /// original window's end — the carry from the 10–3 final reaches 20:17:30
    /// and no further, and a window ending at 20:16:40 stops it earlier still.
    /// Without one (today) the late rows and the carry run to the widened edge
    /// at 20:21:30. A legacy window equal to or wider than the axis renders
    /// today's chart byte for byte.
    func testTheRenderedScoreLineStopsAtTheOriginalWindow() throws {
        let today = try scoreRaster(legacy: nil, name: "no-legacy-window")
        XCTAssertGreaterThan(today.tealMaxX, 0, "control: the teal actual line must be found at all")
        let bounded = try scoreRaster(legacy: at(-600)...legacyEnd, name: "legacy-2017-30")
        let earlier = try scoreRaster(legacy: at(-600)...at(100), name: "legacy-2016-40")

        // 240 s of a 990 s axis on a ~300 pt plot at 3x is ~215 px; 50 s is ~45 px.
        XCTAssertGreaterThan(today.tealMaxX - bounded.tealMaxX, 120,
                             "the teal line ran into the widened tail: \(bounded.tealMaxX) vs today's \(today.tealMaxX)")
        XCTAssertGreaterThan(bounded.tealMaxX - earlier.tealMaxX, 25,
                             "the final margin is still carried, to the legacy window's own end")

        XCTAssertEqual(try scoreRaster(legacy: at(-600)...axisEnd, name: "legacy-equals-axis").png, today.png)
        XCTAssertEqual(try scoreRaster(legacy: at(-9_000)...at(9_000), name: "legacy-wider-than-axis").png, today.png)
    }

    // MARK: - Hosted: the inline and fullscreen consumers

    private func card() -> GamePlayCardView {
        GamePlayCardView(homeTeam: "Seattle Seahawks", awayTeam: "Los Angeles Rams", lastPoint: nil)
    }

    private func chart(_ history: EventHistoryResponse, journey: Journey?, range: OddsTimeRange,
                       withLegacyWindow: Bool, selection: OddsChartSelection? = nil) -> OddsChartView {
        OddsChartView(eventId: eventID, commenceTime: kickoff.ISO8601Format(), status: "completed",
                      homeTeamName: "Seattle Seahawks", awayTeamName: "Los Angeles Rams",
                      forcedDomain: axis(range),
                      legacyDataDomain: withLegacyWindow ? legacy(range) : nil,
                      selectedRange: .constant(range), preloadedHistory: history, readout: card(),
                      publicationJourney: journey, selection: selection)
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
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("4974-axis-ink-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("#4974 axis-ink rendered evidence: \(url.path)")
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

    /// The fullscreen cover, opened the way the LOOK rig opens it (#9185's
    /// launch flag) in a window on the host's active scene.
    private func hostedFullscreenText(_ chart: OddsChartView, name: String) throws -> String {
        let defaults = UserDefaults.standard
        defaults.set(true, forKey: LaunchRig.chartFullscreenKey)
        defer { defaults.removeObject(forKey: LaunchRig.chartFullscreenKey) }
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let scene = scenes.first { $0.activationState == .foregroundActive } ?? scenes.first
        let previousKey = scene?.windows.first { $0.isKeyWindow }
        let host = hostForMeasurement(chart.frame(width: 390), at: .large)
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow()
        window.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            host.dismiss(animated: false)
            window.isHidden = true
            previousKey?.makeKey()
        }
        let deadline = Date().addingTimeInterval(5)
        while host.presentedViewController == nil, Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        let cover = try XCTUnwrap(host.presentedViewController, "the fullscreen cover never opened")
        pump(cover, times: 12)
        return try visibleText(cover, name: name)
    }

    /// The real inline chart, both ranges: a finger held at 20:19 — in the
    /// widened tail, outside the recorded window — floats the original window's
    /// last reading (57% / 43%). Without the legacy window it floats the drift
    /// (29% / 71%).
    func testHostedInlineFingerOnTheWidenedTailReadsTheOriginalWindow() throws {
        let history = try payload()
        let journey = try lateJourney()
        func floated(_ range: OddsTimeRange, withLegacyWindow: Bool, name: String) throws -> String {
            let selection = OddsChartSelection()
            let (host, window) = hosted(chart(history, journey: journey, range: range,
                                              withLegacyWindow: withLegacyWindow, selection: selection))
            defer { window.isHidden = true }
            selection.hold(date: at(240))
            pump(host)
            return try visibleText(host, name: name)
        }
        for range in Self.ranges {
            let text = try floated(range, withLegacyWindow: true, name: "inline-tail-\(range)")
            XCTAssertTrue(text.contains("57%"), "\(range): \(text)")
            XCTAssertFalse(text.contains("29%") || text.contains("71%"), "\(range): a widened-tail price floated: \(text)")
        }
        // CONTROL — the same finger without the legacy window reads the drift.
        let today = try floated(.sinceStart, withLegacyWindow: false, name: "inline-tail-no-legacy-window")
        XCTAssertTrue(today.contains("29%"), "control: today's finger reads the drift: \(today)")
    }

    /// The real fullscreen sheet, which reads the same selection and the same
    /// filtered points. Both ranges: the finger at 20:19 reads 57%; at rest with
    /// the journey it rests on the stored 96%; at rest with no journey it rests
    /// on the original window's last reading. Without the legacy window it rests
    /// on the drift.
    func testHostedFullscreenReadsTheSameCutAsTheInlineChart() throws {
        let history = try payload()
        let journey = try lateJourney()
        for range in Self.ranges {
            let selection = OddsChartSelection()
            selection.hold(date: at(240))
            let text = try hostedFullscreenText(chart(history, journey: journey, range: range, withLegacyWindow: true,
                                                      selection: selection), name: "fullscreen-tail-\(range)")
            XCTAssertTrue(text.contains("57%"), "\(range): \(text)")
            XCTAssertFalse(text.contains("29%") || text.contains("71%"), "\(range): \(text)")
        }
        let resting = try hostedFullscreenText(chart(history, journey: journey, range: .all, withLegacyWindow: true),
                                               name: "fullscreen-rest-on-checkpoint")
        XCTAssertTrue(resting.contains("96%"), "the stored dot is still drawn and rested on: \(resting)")

        let noJourney = try hostedFullscreenText(chart(history, journey: nil, range: .all, withLegacyWindow: true),
                                                 name: "fullscreen-rest-legacy-window")
        XCTAssertTrue(noJourney.contains("57%"), noJourney)
        XCTAssertFalse(noJourney.contains("29%"), "rested on a widened-tail price: \(noJourney)")
        let today = try hostedFullscreenText(chart(history, journey: nil, range: .all, withLegacyWindow: false),
                                             name: "fullscreen-rest-no-legacy-window")
        XCTAssertTrue(today.contains("29%"), "control: today's sheet rests on the drift: \(today)")
    }

    // MARK: - Source scans (comment-stripped, whitespace-free)

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
}
