import Foundation
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class ChartHistoryRange13606Tests: XCTestCase {
    private static let scratchDir = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch"
    private static let outputDir = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/sheets"

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    // MARK: - URLProtocol Stub for APIClient

    private nonisolated final class HistoryURLProtocol: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        private static var _requestedURLs: [URL] = []

        static var requestedURLs: [URL] { lock.withLock { _requestedURLs } }
        static func reset() { lock.withLock { _requestedURLs.removeAll() } }

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            guard let url = request.url else {
                client?.urlProtocol(self, didFailWithError: URLError(.badURL))
                return
            }
            Self.lock.withLock { Self._requestedURLs.append(url) }
            let payload = Data("""
            {
              "event_id": 14639207,
              "home_team": "San Francisco 49ers",
              "away_team": "Minnesota Vikings",
              "status": "completed",
              "pre_window_omitted": true,
              "history": [
                {"timestamp": "2026-11-22T21:05:00Z", "home_probability": 0.55, "away_probability": 0.45},
                {"timestamp": "2026-11-23T00:05:00Z", "home_probability": 0.80, "away_probability": 0.20}
              ]
            }
            """.utf8)
            let response = HTTPURLResponse(
                url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: payload)
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}
    }

    // MARK: - EventDetailProviding Stub

    private nonisolated final class RecordingEventDetailProvider: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        struct HistoryRequest: Equatable {
            let id: Int
            let hours: Int
            let range: String?
            let isFresh: Bool
        }

        private let lock = NSLock()
        private let detail: EventDetail
        private let sinceStartPayload: EventHistoryResponse
        private let allPayload: EventHistoryResponse
        private var _requests: [HistoryRequest] = []

        init(detail: EventDetail, sinceStartPayload: EventHistoryResponse, allPayload: EventHistoryResponse) {
            self.detail = detail
            self.sinceStartPayload = sinceStartPayload
            self.allPayload = allPayload
        }

        var requests: [HistoryRequest] { lock.withLock { _requests } }

        func fetchEvent(id: Int) async throws -> EventDetail { detail }

        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            try await fetchEventHistory(id: id, hours: hours, range: nil)
        }

        func fetchEventHistory(id: Int, hours: Int, range: String?) async throws -> EventHistoryResponse {
            lock.withLock { _requests.append(HistoryRequest(id: id, hours: hours, range: range, isFresh: false)) }
            return range == "all" ? allPayload : sinceStartPayload
        }

        func fetchFreshEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            try await fetchFreshEventHistory(id: id, hours: hours, range: nil)
        }

        func fetchFreshEventHistory(id: Int, hours: Int, range: String?) async throws -> EventHistoryResponse {
            lock.withLock { _requests.append(HistoryRequest(id: id, hours: hours, range: range, isFresh: true)) }
            return range == "all" ? allPayload : sinceStartPayload
        }

        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private func makeEventDetail(id: Int = 14639207) throws -> EventDetail {
        try Self.decoder().decode(EventDetail.self, from: Data("""
        {
          "id": \(id),
          "home_team": "San Francisco 49ers",
          "away_team": "Minnesota Vikings",
          "status": "completed",
          "sport": "americanfootball_nfl",
          "commence_time": "2026-11-22T21:05:00Z",
          "completed_at": "2026-11-23T00:15:00Z",
          "home_score": 24,
          "away_score": 17,
          "current_odds": {"home_probability": 0.99, "away_probability": 0.01}
        }
        """.utf8))
    }

    private func makeHistory(
        preWindowOmitted: Bool?,
        timestamps: [String] = ["2026-11-22T21:05:00Z", "2026-11-23T00:15:00Z"]
    ) throws -> EventHistoryResponse {
        let pointsJSON = timestamps.enumerated().map { idx, ts in
            let p = idx == timestamps.count - 1 ? 0.99 : 0.55
            return "{\"timestamp\":\"\(ts)\",\"home_probability\":\(p),\"away_probability\":\(1.0 - p)}"
        }.joined(separator: ",")
        let omittedField = preWindowOmitted.map { "\"pre_window_omitted\": \($0)," } ?? ""
        return try Self.decoder().decode(EventHistoryResponse.self, from: Data("""
        {
          "event_id": 14639207,
          "home_team": "San Francisco 49ers",
          "away_team": "Minnesota Vikings",
          "status": "completed",
          \(omittedField)
          "history": [\(pointsJSON)]
        }
        """.utf8))
    }

    // MARK: - Unit Tests

    func testAPIClientEncodesRangeQueryParameterWhenProvided() async throws {
        HistoryURLProtocol.reset()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [HistoryURLProtocol.self]
        let client = APIClient(session: URLSession(configuration: config))

        let sinceStart = try await client.fetchEventHistory(id: 14639207, hours: 168, range: "since_start")
        XCTAssertEqual(sinceStart.preWindowOmitted, true)

        _ = try await client.fetchFreshEventHistory(id: 14639207, hours: 168, range: "all")
        _ = try await client.fetchEventHistory(id: 14639207, hours: 24)

        let urls = HistoryURLProtocol.requestedURLs
        XCTAssertEqual(urls.count, 3)

        let items0 = URLComponents(url: urls[0], resolvingAgainstBaseURL: false)?.queryItems ?? []
        XCTAssertEqual(items0.first(where: { $0.name == "hours" })?.value, "168")
        XCTAssertEqual(items0.first(where: { $0.name == "range" })?.value, "since_start")

        let items1 = URLComponents(url: urls[1], resolvingAgainstBaseURL: false)?.queryItems ?? []
        XCTAssertEqual(items1.first(where: { $0.name == "hours" })?.value, "168")
        XCTAssertEqual(items1.first(where: { $0.name == "range" })?.value, "all")
        XCTAssertEqual(items1.first(where: { $0.name == "fresh" })?.value, "true")

        let items2 = URLComponents(url: urls[2], resolvingAgainstBaseURL: false)?.queryItems ?? []
        XCTAssertEqual(items2.first(where: { $0.name == "hours" })?.value, "24")
        XCTAssertNil(items2.first(where: { $0.name == "range" }))
    }

    func testEventDetailViewModelSendsSinceStartFirstAndUpgradesLazilyOnlyWhenOmitted() async throws {
        let sinceStart = try makeHistory(
            preWindowOmitted: true,
            timestamps: ["2026-11-22T21:05:00Z", "2026-11-23T00:15:00Z"]
        )
        let full = try makeHistory(
            preWindowOmitted: false,
            timestamps: ["2026-11-16T12:00:00Z", "2026-11-22T21:05:00Z", "2026-11-23T00:15:00Z"]
        )
        let clientWithOmitted = RecordingEventDetailProvider(
            detail: try makeEventDetail(),
            sinceStartPayload: sinceStart,
            allPayload: full
        )
        let vm = EventDetailViewModel(eventId: 14639207, client: clientWithOmitted)
        await vm.load()

        XCTAssertEqual(clientWithOmitted.requests.count, 1)
        XCTAssertEqual(clientWithOmitted.requests[0].range, "since_start")
        XCTAssertEqual(vm.history?.preWindowOmitted, true)
        XCTAssertEqual(vm.history?.history.count, 2)

        // Switching picker to All upgrades lazily because pre_window_omitted == true.
        await vm.loadFullHistoryIfNeeded()
        XCTAssertEqual(clientWithOmitted.requests.count, 2)
        XCTAssertEqual(clientWithOmitted.requests[1].range, "all")
        XCTAssertEqual(vm.history?.preWindowOmitted, false)
        XCTAssertEqual(vm.history?.history.count, 3)

        // Calling again is a no-op once full history is already loaded.
        await vm.loadFullHistoryIfNeeded()
        XCTAssertEqual(clientWithOmitted.requests.count, 2)

        // When server already returned complete history under since_start (`pre_window_omitted == false`),
        // switching to All must NOT issue a redundant network read.
        let complete = try makeHistory(preWindowOmitted: false)
        let clientAlreadyFull = RecordingEventDetailProvider(
            detail: try makeEventDetail(),
            sinceStartPayload: complete,
            allPayload: complete
        )
        let vm2 = EventDetailViewModel(eventId: 14639207, client: clientAlreadyFull)
        await vm2.load()
        await vm2.loadFullHistoryIfNeeded()
        XCTAssertEqual(clientAlreadyFull.requests.count, 1)
        XCTAssertEqual(clientAlreadyFull.requests[0].range, "since_start")
    }

    func testOddsChartViewModelStandaloneRequestsSinceStartAndUpgradesToAll() async throws {
        let sinceStart = try makeHistory(preWindowOmitted: true)
        let full = try makeHistory(
            preWindowOmitted: false,
            timestamps: ["2026-11-16T12:00:00Z", "2026-11-22T21:05:00Z", "2026-11-23T00:15:00Z"]
        )
        var requestedRanges: [String?] = []
        let chartVM = OddsChartViewModel(eventId: 14639207) { _, range in
            requestedRanges.append(range)
            return range == "all" ? full : sinceStart
        }
        await chartVM.load()
        XCTAssertEqual(requestedRanges, ["since_start"])
        XCTAssertEqual(chartVM.history?.preWindowOmitted, true)

        await chartVM.loadFullHistoryIfNeeded()
        XCTAssertEqual(requestedRanges, ["since_start", "all"])
        XCTAssertEqual(chartVM.history?.history.count, 3)
        XCTAssertEqual(chartVM.history?.preWindowOmitted, false)
    }

    func testEventHistoryFreshnessAdoptsFullUpgradeOverOmittedWindow() throws {
        let omittedNewerEdge = try makeHistory(
            preWindowOmitted: true,
            timestamps: ["2026-11-22T21:05:00Z", "2026-11-23T00:20:00Z"]
        )
        let full = try makeHistory(
            preWindowOmitted: false,
            timestamps: ["2026-11-16T12:00:00Z", "2026-11-22T21:05:00Z", "2026-11-23T00:15:00Z"]
        )
        XCTAssertTrue(
            EventHistoryFreshness.shouldAdopt(full, over: omittedNewerEdge),
            "Upgrading from pre_window_omitted: true to range=all must adopt full history"
        )
    }

    func testFinishedNFL14639207ChartRangeProofRender390pt() throws {
        let eventPath = "\(Self.scratchDir)/13606-event-14639207.json"
        let sinceStartPath = "\(Self.scratchDir)/13606-history-since-start.json"
        let allPath = "\(Self.scratchDir)/13606-history-all.json"
        guard FileManager.default.fileExists(atPath: eventPath),
              FileManager.default.fileExists(atPath: sinceStartPath),
              FileManager.default.fileExists(atPath: allPath) else {
            return
        }

        let d = Self.decoder()
        let event = try d.decode(EventDetail.self, from: Data(contentsOf: URL(fileURLWithPath: eventPath)))
        let sinceStart = try d.decode(EventHistoryResponse.self, from: Data(contentsOf: URL(fileURLWithPath: sinceStartPath)))
        let all = try d.decode(EventHistoryResponse.self, from: Data(contentsOf: URL(fileURLWithPath: allPath)))

        XCTAssertEqual(event.id, 14639207)
        XCTAssertEqual(sinceStart.preWindowOmitted, true)
        XCTAssertEqual(all.preWindowOmitted, false)
        XCTAssertLessThan(sinceStart.aggregateLine?.count ?? 0, all.aggregateLine?.count ?? 0)

        func chartPanel(history: EventHistoryResponse, range: OddsTimeRange, scheme: ColorScheme) -> UIImage {
            renderSlice(width: 390, height: 470, scheme: scheme) {
                OddsChartView(
                    eventId: event.id,
                    commenceTime: event.commenceTime,
                    status: event.status,
                    homeTeamName: event.homeTeam,
                    awayTeamName: event.awayTeam,
                    homeTeamLogo: event.homeTeamData?.logoSmall,
                    awayTeamLogo: event.awayTeamData?.logoSmall,
                    homeTeamAbbrev: event.homeTeamData?.abbreviation,
                    awayTeamAbbrev: event.awayTeamData?.abbreviation,
                    sportKey: event.sport,
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    servedHomeProbability: event.heroProbabilitySource == OpeningLineHero.openingSource ? nil : event.currentOdds?.homeProbability,
                    servedAwayProbability: event.heroProbabilitySource == OpeningLineHero.openingSource ? nil : event.currentOdds?.awayProbability,
                    selectedRange: .constant(range),
                    preloadedHistory: history
                )
                .padding(12)
                .frame(width: 390, height: 470, alignment: .topLeading)
                .background(Color(.systemGroupedBackground))
            }
        }

        let sinceLight = chartPanel(history: sinceStart, range: .sinceStart, scheme: .light)
        let sinceDark = chartPanel(history: sinceStart, range: .sinceStart, scheme: .dark)
        let allLight = chartPanel(history: all, range: .all, scheme: .light)
        let allDark = chartPanel(history: all, range: .all, scheme: .dark)

        try FileManager.default.createDirectory(atPath: Self.outputDir, withIntermediateDirectories: true)
        let sheet = stitchSheet(
            sinceLight: sinceLight, sinceDark: sinceDark,
            allLight: allLight, allDark: allDark,
            sinceCount: sinceStart.aggregateLine?.count ?? sinceStart.history.count,
            allCount: all.aggregateLine?.count ?? all.history.count
        )
        try savePNG(sheet, to: "\(Self.outputDir)/sheet-13606-nfl-chart-range-390.png")

        let ocrSince = recognizeText(in: sinceLight)
        XCTAssertTrue(ocrSince.contains("Win Probability"), "Missing Win Probability header: \(ocrSince)")
        XCTAssertTrue(ocrSince.contains("Since Start"), "Missing Since Start toggle: \(ocrSince)")
        XCTAssertTrue(ocrSince.contains("All"), "Missing All toggle: \(ocrSince)")
    }

    private func stitchSheet(
        sinceLight: UIImage, sinceDark: UIImage,
        allLight: UIImage, allDark: UIImage,
        sinceCount: Int, allCount: Int
    ) -> UIImage {
        let colW: CGFloat = 390
        let panelH: CGFloat = 470
        let headerH: CGFloat = 28
        let gap: CGFloat = 16
        let margin: CGFloat = 16
        let totalW = margin * 2 + colW * 2 + gap
        let totalH = margin * 2 + (headerH + panelH) * 2 + gap
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.5
        return UIGraphicsImageRenderer(size: CGSize(width: totalW, height: totalH), format: fmt).image { ctx in
            UIColor(white: 0.94, alpha: 1).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: totalW, height: totalH))
            func draw(_ img: UIImage, title: String, x: CGFloat, y: CGFloat) {
                let attr: [NSAttributedString.Key: Any] = [
                    .font: UIFont.systemFont(ofSize: 11, weight: .semibold),
                    .foregroundColor: UIColor.black,
                ]
                NSString(string: title).draw(in: CGRect(x: x, y: y + 5, width: colW, height: headerH - 5), withAttributes: attr)
                img.draw(in: CGRect(x: x, y: y + headerH, width: colW, height: panelH))
            }
            let y1 = margin
            draw(sinceLight, title: "NFL 14639207 since_start (\(sinceCount) pts) Light · simulator results, not phone results", x: margin, y: y1)
            draw(sinceDark, title: "NFL 14639207 since_start (\(sinceCount) pts) Dark · simulator results, not phone results", x: margin + colW + gap, y: y1)
            let y2 = y1 + headerH + panelH + gap
            draw(allLight, title: "NFL 14639207 all (\(allCount) pts) Light · simulator results, not phone results", x: margin, y: y2)
            draw(allDark, title: "NFL 14639207 all (\(allCount) pts) Dark · simulator results, not phone results", x: margin + colW + gap, y: y2)
        }
    }

    private func renderSlice<Content: View>(
        width: CGFloat, height: CGFloat, scheme: ColorScheme,
        @ViewBuilder content: () -> Content
    ) -> UIImage {
        let host = UIHostingController(
            rootView: content()
                .environment(\.colorScheme, scheme)
                .environment(\.dynamicTypeSize, .large)
        )
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        host.view.backgroundColor = scheme == .dark ? .black : .white
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<5 {
            host.view.frame = bounds
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.04))
        }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        let img = UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        window.isHidden = true
        window.rootViewController = nil
        return img
    }

    private func recognizeText(in image: UIImage) -> String {
        guard let cg = image.cgImage else { return "" }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    private func savePNG(_ image: UIImage, to path: String) throws {
        guard let data = image.pngData() else { return }
        try data.write(to: URL(fileURLWithPath: path), options: .atomic)
    }
}
