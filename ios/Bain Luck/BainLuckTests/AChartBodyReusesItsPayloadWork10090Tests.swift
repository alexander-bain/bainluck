import XCTest
import SwiftUI
import Combine
import UIKit
@testable import Bain_Luck

/// #10090 — **an update the payload did not change re-derives nothing from the
/// payload; a pushed frame re-derives only what the frame moves.**
///
/// Every body pass of the game chart — a pushed price, a score, a status, a
/// tick of the page's clock — re-derived its pure products from the whole
/// payload on the main thread before the chart could commit. Measured on a
/// week-shaped 10,021-point live NFL payload (Debug simulator, hosted chart):
/// an unrelated update cost ~76 ms, ~48 ms of it Since Start's opening
/// (`ObservedPlayStart.cut`, every ESPN and win-probability row, ~24 ms a
/// call, twice a pass) and ~13 ms the period sightings. Both are now built
/// once per payload; the drawn cut once per frame and window.
///
/// The hosted count test and the wiring scan are the RED ones (the scan is red
/// on `fa9656c9`). The equivalence tests are the control: each memo answers
/// exactly what its plain builder answers, across every input that keys it.
@MainActor
final class AChartBodyReusesItsPayloadWork10090Tests: XCTestCase {

    private static let kickoff = Date(timeIntervalSince1970: 1_793_275_200)  // 2026-10-29T12:00:00Z

    private static func stamp(_ date: Date) -> String { date.ISO8601Format() }

    private static func at(_ minute: Int, _ second: Int = 0) -> Date {
        kickoff.addingTimeInterval(Double(minute * 60 + second))
    }

    /// A live NFL blend that kicked off 20 minutes late: pregame prices, then
    /// ESPN rows from the first observed Q1 at 12:20, Q2 at 12:50 and (with
    /// `third`) Q3 at 13:30.
    private static func payload(third: Bool = false, edge: Double = 0.6) throws -> EventHistoryResponse {
        func row(_ minute: Int, _ p: Double) -> String {
            #"{"timestamp":"\#(stamp(at(minute)))","home_probability":\#(p)}"#
        }
        var espn: [String] = []
        let periods = third ? [(20, "1"), (35, "1"), (50, "2"), (65, "2"), (90, "3")] : [(20, "1"), (35, "1"), (50, "2"), (65, "2")]
        for (minute, period) in periods {
            espn.append(#"{"timestamp":"\#(stamp(at(minute)))","home_probability":0.5,"game_clock":"10:00","period":"\#(period)","home_score":\#(minute / 10),"away_score":0}"#)
        }
        let minutes = Array(stride(from: -120, through: third ? 90 : 70, by: 5))
        let json = """
        {"event_id":1,"home_team":"Home","away_team":"Away","status":"live",
         "history":[\(minutes.map { row($0, 0.5) }.joined(separator: ","))],
         "win_prob_history":{"kalshi":[\(minutes.map { row($0, 0.55) }.joined(separator: ","))]},
         "aggregate_line":[\(minutes.dropLast().map { row($0, 0.52) }.joined(separator: ",")),\(row(minutes.last!, edge))],
         "espn_history":[\(espn.joined(separator: ","))]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private static func frame(_ i: Int) -> LiveBlendPoint {
        LiveBlendPoint(date: at(71, i), homeProbability: 0.6 + Double(i % 5) / 100)
    }

    // MARK: - RED before: every update re-derived the payload

    private final class Input: ObservableObject {
        @Published var frames: [LiveBlendPoint] = []
        @Published var score = 0
    }

    private struct Fixture: View {
        @ObservedObject var input: Input
        let payload: EventHistoryResponse
        let model: OddsChartViewModel
        var body: some View {
            OddsChartView(eventId: 1, commenceTime: AChartBodyReusesItsPayloadWork10090Tests.stamp(
                              AChartBodyReusesItsPayloadWork10090Tests.kickoff),
                          status: "live", homeTeamName: "Home", awayTeamName: "Away",
                          sportKey: "americanfootball_nfl", homeScore: input.score, awayScore: 0,
                          preloadedHistory: payload, liveFrames: input.frames, model: model)
                .environment(\.scenePhase, .active)
        }
    }

    private func pump(_ host: UIViewController, times: Int = 3) {
        for _ in 0..<times {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
    }

    private struct Counts: Equatable {
        let playStart: Int, sightings: Int, drawn: Int, enrichment: Int
    }

    private func counts(_ model: OddsChartViewModel) -> Counts {
        Counts(playStart: model.playStartBuildCount, sightings: model.periodSightingsBuildCount,
               drawn: model.drawnBuildCount, enrichment: model.enrichmentBuildCount)
    }

    func testAnUnrelatedUpdateRebuildsNothingAndAFrameRebuildsOnlyWhatItMoves() throws {
        let payload = try Self.payload()
        let model = OddsChartViewModel(eventId: 1, preloaded: payload)
        var plotBuilds = 0
        model.onPlotBuild = { plotBuilds += 1 }
        let input = Input()
        let host = hostForMeasurement(Fixture(input: input, payload: payload, model: model).frame(width: 390), at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true; model.onPlotBuild = nil }
        pump(host, times: 8)
        XCTAssertGreaterThan(plotBuilds, 0, "the plot never rendered — the counts below would be vacuous")
        let mounted = counts(model)
        XCTAssertEqual(mounted.playStart, 1, "the mounted chart scanned the payload for its start \(mounted.playStart) times")
        XCTAssertEqual(mounted.sightings, 1, "the mounted chart parsed the period sightings \(mounted.sightings) times")
        XCTAssertNotNil(model.observedPlayStart(scheduled: Self.kickoff, sportKey: "americanfootball_nfl"),
                        "the fixture's late Q1 sets no Since Start cut — the start it reuses is vacuous")

        let beforeScores = plotBuilds
        for _ in 0..<5 {
            input.score += 1
            pump(host, times: 1)
        }
        let afterScores = plotBuilds
        XCTAssertGreaterThan(afterScores, beforeScores,
                             "a score never re-ran the chart's body — the counts below would be vacuous")
        XCTAssertEqual(counts(model), mounted,
                       "an unrelated update re-derived the payload — every score and clock tick pays for the whole history")

        for i in 0..<3 {
            input.frames.append(Self.frame(i))
            pump(host, times: 1)
        }
        let afterFrames = counts(model)
        XCTAssertEqual(afterFrames.playStart, mounted.playStart, "a pushed frame scanned the payload for its start")
        XCTAssertEqual(afterFrames.sightings, mounted.sightings, "a pushed frame re-parsed the period sightings")
        XCTAssertEqual(afterFrames.enrichment, mounted.enrichment + 3)
        XCTAssertEqual(afterFrames.drawn, mounted.drawn + 3, "a pushed frame did not re-cut the drawn points")
        XCTAssertGreaterThan(plotBuilds, afterScores, "a pushed frame must still reach the plot")
        XCTAssertTrue(model.enrichedChartPoints(liveFrames: input.frames).contains {
            $0.source == "aggregate" && $0.date == Self.frame(2).date
        }, "the third frame is not on the chart")

        model.history = try Self.payload(third: true, edge: 0.66)
        pump(host)
        XCTAssertEqual(model.playStartBuildCount, mounted.playStart + 1, "a new payload kept the old payload's start")
        XCTAssertEqual(model.periodSightingsBuildCount, mounted.sightings + 1,
                       "a new payload kept the old payload's period sightings")
        XCTAssertTrue(model.periodSightings(sportKey: "americanfootball_nfl").sorted.contains { $0.label == "Q3" },
                      "the new payload's Q3 is not among the chart's sightings")
    }

    // MARK: - The controls: each memo answers what its builder answers

    /// Everything a point carries except its `id`.
    private func drawn(_ points: [ChartDataPoint]) -> [String] {
        points.map { point in
            Mirror(reflecting: point).children
                .filter { $0.label != "id" }
                .map { "\($0.label ?? "?")=\(String(describing: $0.value))" }
                .joined(separator: " ")
        }
    }

    private static func windows() -> [OddsChartView.DrawnWindow] {
        let cut = at(18)
        let forced = at(10)...at(80)
        let legacy = at(-30)...at(60)
        return [
            .init(finishedEnd: nil, forcedDomain: nil, legacyDataDomain: nil, started: false, range: .all, sinceStart: nil),
            .init(finishedEnd: nil, forcedDomain: nil, legacyDataDomain: nil, started: true, range: .all, sinceStart: cut),
            .init(finishedEnd: nil, forcedDomain: nil, legacyDataDomain: nil, started: true, range: .sinceStart, sinceStart: cut),
            .init(finishedEnd: nil, forcedDomain: nil, legacyDataDomain: nil, started: true, range: .sinceStart, sinceStart: at(40)),
            .init(finishedEnd: nil, forcedDomain: forced, legacyDataDomain: nil, started: true, range: .sinceStart, sinceStart: cut),
            .init(finishedEnd: nil, forcedDomain: forced, legacyDataDomain: legacy, started: true, range: .sinceStart, sinceStart: cut),
            .init(finishedEnd: at(55), forcedDomain: nil, legacyDataDomain: nil, started: true, range: .all, sinceStart: cut),
        ]
    }

    func testTheDrawnPointsAreTheCutOfTheEnrichedPointsForEveryWindowAndFrame() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try Self.payload())
        var frames: [LiveBlendPoint] = []
        for step in 0...2 {
            if step > 0 { frames.append(Self.frame(step)) }
            for window in Self.windows() {
                let builds = vm.drawnBuildCount
                let memo = vm.drawnPoints(liveFrames: frames, window: window)
                let plain = OddsChartView.drawnPoints(vm.enrichedChartPoints(liveFrames: frames), window: window)
                XCTAssertEqual(drawn(memo), drawn(plain), "\(frames.count) frame(s), window \(window)")
                XCTAssertEqual(memo.map(\.id), plain.map(\.id), "the memo drew different points than the cut")
                XCTAssertEqual(vm.drawnBuildCount, builds + 1, "a changed window was answered from the memo: \(window)")
                XCTAssertEqual(vm.drawnPoints(liveFrames: frames, window: window).map(\.id), memo.map(\.id))
                XCTAssertEqual(vm.drawnBuildCount, builds + 1, "the same window and frames were cut again")
            }
        }
        XCTAssertFalse(vm.drawnPoints(liveFrames: frames, window: Self.windows()[2]).isEmpty,
                       "the fixture draws nothing Since Start — the comparisons above would be vacuous")
    }

    func testTheDrawnPointsFollowANewPayload() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try Self.payload())
        let window = Self.windows()[2]
        _ = vm.drawnPoints(liveFrames: [], window: window)
        vm.history = try Self.payload(third: true, edge: 0.66)
        let after = vm.drawnPoints(liveFrames: [], window: window)
        XCTAssertEqual(drawn(after), drawn(OddsChartView.drawnPoints(vm.enrichedChartPoints(liveFrames: []), window: window)))
        XCTAssertTrue(after.contains { $0.source == "aggregate" && $0.probability == 0.66 },
                      "the new payload's edge is not drawn — the old payload's points were served")
        vm.history = nil
        XCTAssertTrue(vm.drawnPoints(liveFrames: [], window: window).isEmpty)
    }

    func testThePlayStartIsTheScanForEveryPayloadStartAndSport() throws {
        let first = try Self.payload()
        let vm = OddsChartViewModel(eventId: 1, preloaded: first)
        let cases: [(Date, String?)] = [
            (Self.kickoff, "americanfootball_nfl"), (Self.kickoff, "americanfootball_nfl"),
            (Self.at(5), "americanfootball_nfl"), (Self.kickoff, "basketball_nba"), (Self.kickoff, nil),
        ]
        for (scheduled, sport) in cases {
            XCTAssertEqual(vm.observedPlayStart(scheduled: scheduled, sportKey: sport),
                           ObservedPlayStart.cut(scheduled: scheduled, history: first, sportKey: sport),
                           "scheduled \(scheduled), sport \(sport ?? "nil")")
        }
        XCTAssertEqual(vm.playStartBuildCount, cases.count - 1, "the repeated first ask scanned the payload again")
        XCTAssertEqual(vm.observedPlayStart(scheduled: Self.kickoff, sportKey: "americanfootball_nfl"), Self.at(18),
                       "the fixture's late Q1 at 12:20 should open Since Start two minutes before it")

        let second = try Self.decodeLateQ1(at: 30)
        vm.history = second
        XCTAssertEqual(vm.observedPlayStart(scheduled: Self.kickoff, sportKey: "americanfootball_nfl"), Self.at(28),
                       "a new payload's later Q1 was answered with the old payload's start")
        vm.history = nil
        XCTAssertNil(vm.observedPlayStart(scheduled: Self.kickoff, sportKey: "americanfootball_nfl"))
    }

    private static func decodeLateQ1(at minute: Int) throws -> EventHistoryResponse {
        let json = """
        {"event_id":1,"home_team":"Home","away_team":"Away","status":"live",
         "history":[{"timestamp":"\(stamp(at(0)))","home_probability":0.5}],
         "espn_history":[{"timestamp":"\(stamp(at(minute)))","home_probability":0.5,"period":"1","game_clock":"15:00"},
                         {"timestamp":"\(stamp(at(minute + 10)))","home_probability":0.5,"period":"1","game_clock":"9:00"}]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func described(_ sightings: OddsChartView.PeriodSightings) -> [String] {
        sightings.sorted.map { "\($0.label)@\($0.date.timeIntervalSince1970) \(String(describing: sightings.provenance[$0.label]))" }
    }

    func testThePeriodSightingsAreThePayloadsForEveryPayloadAndSport() throws {
        let first = try Self.payload()
        let vm = OddsChartViewModel(eventId: 1, preloaded: first)
        for sport in ["americanfootball_nfl", "americanfootball_nfl", "basketball_nba"] {
            XCTAssertEqual(described(vm.periodSightings(sportKey: sport)),
                           described(OddsChartView.periodSightings(first, sportKey: sport)), sport)
        }
        XCTAssertEqual(vm.periodSightingsBuildCount, 2, "the repeated sport parsed the payload again")
        XCTAssertEqual(vm.periodSightings(sportKey: "americanfootball_nfl").sorted.map(\.label), ["Q1", "Q2"])

        let second = try Self.payload(third: true)
        vm.history = second
        XCTAssertEqual(described(vm.periodSightings(sportKey: "americanfootball_nfl")),
                       described(OddsChartView.periodSightings(second, sportKey: "americanfootball_nfl")))
        XCTAssertEqual(vm.periodSightings(sportKey: "americanfootball_nfl").sorted.map(\.label), ["Q1", "Q2", "Q3"],
                       "a new payload's Q3 was answered with the old payload's sightings")
    }

    // MARK: - The wiring (comment-stripped scan: bodies are not rendered in tests)

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

    /// The payload scans and the drawn cut each have one caller: the view
    /// model's memo. A body that calls one directly pays for the whole payload
    /// on every update again.
    func testTheChartDerivesItsPayloadProductsOnlyThroughItsMemos() throws {
        let chart = try code("Bain Luck/Components/OddsChartView.swift")
        XCTAssertTrue(chart.contains("vm.observedPlayStart(scheduled:kickoffDate,sportKey:sportKey)"),
                      "Since Start's opening is not read through the view model's memo")
        XCTAssertTrue(chart.contains("vm.periodMarkers(sportKey:sportKey,minSpacing:minSpacing)"),
                      "the period markers are not read through the view model's memo")
        XCTAssertTrue(chart.contains("vm.drawnPoints(liveFrames:liveFrames,window:drawnWindow)"),
                      "the drawn points are not read through the view model's memo")
        for builder in ["ObservedPlayStart.cut(", "OddsChartView.periodSightings(", "OddsChartView.drawnPoints("] {
            let calls = chart.components(separatedBy: builder).count - 1
            XCTAssertEqual(calls, 1, "\(builder) is called \(calls) times; only its memo may call it")
        }
    }
}
