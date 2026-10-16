import XCTest
import SwiftUI
import UIKit
import Vision
@testable import Bain_Luck

/// #683 — the LOCAL RENDER of the real Evolution chart over synthetic decoded
/// responses (Root's admitted fixture, 10/15). Every frame is the actual
/// `EvolutionChartView`: its chips, plot, caption and selected readout, loaded
/// through the real `APIClient` over a stubbed origin via `EvolutionChartFixture`.
///
/// 🔴 SYNTHETIC. The bodies below are hand-built in the shape of calibration's
/// contract (PR #11083: archive marks @ c3a9b8ae3a, `history_range` @ 616d0c0a6b);
/// none is a production read. The store is empty until the attended import runs, so
/// a pass here pays local rendering only — the served imported specimen and the
/// installed build are still owed.
///
/// Each frame is written as a PNG (path printed) so a person can look at it, and
/// read back with on-device text recognition so the suite can hold what it says.
@MainActor
final class TheFullChartRendersRecoveredHistory683Tests: XCTestCase {
    private nonisolated final class Origin: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var captured: [URLRequest] = []
        /// path → (full-range body, ordinary body)
        nonisolated(unsafe) private static var bodies: [String: (full: String, ordinary: String)] = [:]

        static func reset(_ bodies: [String: (full: String, ordinary: String)]) {
            lock.lock(); defer { lock.unlock() }
            captured = []; self.bodies = bodies
        }
        static var requests: [URLRequest] {
            lock.lock(); defer { lock.unlock() }
            return captured
        }

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            let full = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?
                .queryItems?.contains { $0.name == "range" && $0.value == "full" } ?? false
            Self.lock.lock()
            Self.captured.append(request)
            let pair = Self.bodies[request.url?.path ?? ""]
            Self.lock.unlock()
            let body = pair.map { full ? $0.full : $0.ordinary }
            let response = HTTPURLResponse(
                url: request.url!, statusCode: body == nil ? 404 : 200, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data((body ?? "{}").utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private static let thunder = "Oklahoma City Thunder"
    private static let celtics = "Boston Celtics"

    private func client() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        configuration.urlCache = nil
        return APIClient(session: URLSession(configuration: configuration))
    }

    /// Instants are dated against the real clock, because the chart's short chips
    /// cut against `Date()`.
    private let now = Date()
    private func iso(daysAgo days: Double, hour: Int = 0) -> String {
        let date = now.addingTimeInterval(-days * 86_400)
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let pinned = calendar.date(bySettingHour: hour, minute: 0, second: 0, of: date)!
        return ISO8601DateFormatter().string(from: pinned)
    }
    private func instant(_ s: String) -> Date { ISO8601DateFormatter().date(from: s)! }

    private struct Point { let at: String; let thunder: Double; let archive: Bool }

    private func timeline(_ points: [Point], block: String?, hours: Int = 4320) -> String {
        let rows = points.map { p -> String in
            let values = #""outcomes":{"\#(Self.thunder)":\#(p.thunder),"\#(Self.celtics)":\#(1 - p.thunder)}"#
            guard p.archive else { return #"{"timestamp":"\#(p.at)",\#(values)}"# }
            let start = ISO8601DateFormatter().string(from: instant(p.at).addingTimeInterval(-3600))
            let mark = #"{"provenance":"kalshi_archive","interval_start":"\#(start)","period_minutes":60,"price_basis":"traded_interval"}"#
            return #"{"timestamp":"\#(p.at)",\#(values),"archive":{"\#(Self.thunder)":\#(mark),"\#(Self.celtics)":\#(mark)}}"#
        }
        let last = points.last!.thunder
        return """
        {"market_id": 68390, "market_name": "NBA Champion (synthetic)", "sport_category": "politics",
         "source": "kalshi", "hours": \(hours), "top": 50, "bucket_seconds": 3600,
         "coverage_hours": \(hours).0, "observation_times": \(points.count),
         "outcomes": [
           {"id": 1, "name": "\(Self.thunder)", "current_probability": \(last), "rank": 1},
           {"id": 2, "name": "\(Self.celtics)", "current_probability": \(1 - last), "rank": 2}],
         "timeline": [\(rows.joined(separator: ",\n"))]
         \(block.map { ", \"history_range\": \($0)" } ?? "")}
        """
    }

    /// Live captures over the last `days`, every 12 hours, on the hour.
    private func livePoints(days: Int = 30) -> [Point] {
        let hour = (now.timeIntervalSince1970 / 3600).rounded(.down) * 3600
        return (0..<(days * 2)).reversed().map { i in
            let at = Date(timeIntervalSince1970: hour - Double(i) * 12 * 3600)
            return Point(at: ISO8601DateFormatter().string(from: at),
                         thunder: 0.40 + 0.10 * sin(Double(i) / 6), archive: false)
        }
    }

    /// Hourly-record closes from 240 to 200 days ago — older than the 4320h floor
    /// and older than our first live capture.
    private func archivePoints() -> [Point] {
        (0..<20).map { i in
            Point(at: iso(daysAgo: 240 - Double(i) * 2, hour: 15),
                  thunder: 0.22 + 0.01 * Double(i), archive: true)
        }
    }

    // MARK: - The camera

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    private func render(_ fixture: EvolutionChartFixture, _ name: String,
                        at size: DynamicTypeSize = .large) throws -> [String] {
        let chart = ScrollView {
            EvolutionChartView(marketId: 68390, hours: 168, fixture: fixture).padding(.vertical)
        }
        let host = hostForMeasurement(chart.environment(\.colorScheme, .light), at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let win = UIWindow(frame: host.view.frame)
        win.rootViewController = host; win.isHidden = false
        defer { win.isHidden = true }
        settle(host, 2.0)
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let png = try XCTUnwrap(image.pngData())
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("evolution-683-\(name).png")
        try png.write(to: url)
        print("Evolution 683 rendered evidence (SYNTHETIC fixture): \(url.path)")
        let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        print("Evolution 683 \(name) text: \(lines)")
        return lines
    }

    private func says(_ lines: [String], _ phrase: String) -> Bool {
        lines.joined(separator: " ").localizedCaseInsensitiveContains(phrase)
    }

    private let path = "/api/futures/68390/probability-timeline"

    // MARK: - (a) wholly live

    func testAWhollyLiveFullChartCarriesNoRecordAttribution() throws {
        let live = livePoints()
        let body = timeline(live, block: #"{"requested":"full","window_start_basis":"live_first_capture","archive_coverage":null,"served_history":"complete"}"#)
        Origin.reset([path: (body, body)])
        let lines = try render(EvolutionChartFixture(
            client: client(), range: .season, selectAt: instant(live[live.count - 10].at)), "a-live")
        XCTAssertTrue(Origin.requests.contains { $0.url?.query?.contains("range=full") == true },
                      "the widest chip asks for the whole history")
        XCTAssertTrue(says(lines, "Max"), "the widest chip renders")
        XCTAssertFalse(says(lines, "record"), "no live value is attributed to a record")
        XCTAssertFalse(says(lines, "older prices"))
    }

    // MARK: - (b) mixed live and recorded, an archived value selected

    func testAMixedFullChartAttributesTheSelectedRecordedInterval() throws {
        let archive = archivePoints()
        let body = timeline(archive + livePoints(), block: """
            {"requested":"full","window_start":"\(archive[0].at)","window_start_basis":"archive_first_interval",
             "archive_coverage":"complete","thinned_outcomes":[],"live_thinned":false,"served_history":"complete"}
            """)
        Origin.reset([path: (body, timeline(livePoints(), block: nil))])
        for (name, size) in [("b-mixed", DynamicTypeSize.large), ("b-mixed-ax3", .accessibility3)] {
            let lines = try render(EvolutionChartFixture(
                client: client(), range: .season, selectAt: instant(archive[5].at)), name, at: size)
            XCTAssertTrue(says(lines, "Kalshi"), "\(name): the record is named as Kalshi's")
            XCTAssertTrue(says(lines, "record"), "\(name): the caption/readout calls it a record")
            XCTAssertTrue(says(lines, "traded"), "\(name): the selected value's basis is read out")
        }
    }

    // MARK: - (c) older than 180 days and ingestion, with a short-range control

    func testFullReachesARecordOlderThanTheFloorAndAShortChipDoesNot() throws {
        let archive = archivePoints()
        XCTAssertLessThan(instant(archive[0].at), now.addingTimeInterval(-4320 * 3600),
                          "the oldest recorded close must lie past the 4320h floor to testify")
        let full = timeline(archive + livePoints(), block: """
            {"requested":"full","window_start":"\(archive[0].at)","window_start_basis":"archive_first_interval",
             "archive_coverage":"incomplete","thinned_outcomes":[],"live_thinned":false}
            """)
        let ordinary = timeline(livePoints(days: 7), block: nil, hours: 168)
        Origin.reset([path: (full, ordinary)])

        let wide = try render(EvolutionChartFixture(client: client(), range: .season), "c-full-240d")
        let fullQueries = Origin.requests.compactMap { $0.url?.query }
        XCTAssertTrue(fullQueries.contains { $0.contains("range=full") && $0.contains("hours=4320") })
        XCTAssertTrue(says(wide, "record"), "the recorded span older than the floor is drawn and labelled")
        XCTAssertFalse(says(wide, "Prices only go back"),
                       "an incomplete import's first interval is not the question's open")

        Origin.reset([path: (full, ordinary)])
        let week = try render(EvolutionChartFixture(client: client(), range: .week), "c-control-7d")
        let weekQueries = Origin.requests.compactMap { $0.url?.query }
        XCTAssertFalse(weekQueries.contains { $0.contains("range=") }, "a short chip's request is unchanged")
        XCTAssertFalse(says(week, "record"), "the control draws no recorded value")
    }

    // MARK: - (d) a partial full read says so

    func testAPartialFullReadRendersItsOneCaption() throws {
        let archive = archivePoints()
        let body = timeline(archive + livePoints(), block: """
            {"requested":"full","window_start_basis":"archive_first_interval","archive_coverage":"complete",
             "thinned_outcomes":[],"live_thinned":true,"served_history":"partial",
             "unresolved_withheld":{"archive_intervals":3,"venue_points":0}}
            """)
        Origin.reset([path: (body, body)])
        let lines = try render(EvolutionChartFixture(client: client(), range: .season), "d-partial")
        XCTAssertTrue(says(lines, "older prices"), "the partial caption renders: \(lines)")
        XCTAssertFalse(says(lines, "withheld"), "no method words on the reader's screen")
    }
}
