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

    func testDelayedTipScheduledGameUpgradesAutomaticallyToFullHistory() async throws {
        let pastKickoff = Date().addingTimeInterval(-300) // 5 min past scheduled start, still status="scheduled"
        let iso = ISO8601DateFormatter()
        let pastStamp = iso.string(from: pastKickoff)
        let pregameEarly = iso.string(from: pastKickoff.addingTimeInterval(-3600))
        let pregameMid = iso.string(from: pastKickoff.addingTimeInterval(-1800))
        let postTip = iso.string(from: pastKickoff.addingTimeInterval(60))

        let d = Self.decoder()
        let delayedEvent = try d.decode(EventDetail.self, from: Data("""
        {
          "id": 15353109,
          "home_team": "Louisville Cardinals",
          "away_team": "Texas Tech Red Raiders",
          "status": "scheduled",
          "sport": "basketball_ncaab",
          "commence_time": "\(pastStamp)",
          "current_odds": {"home_probability": 0.62, "away_probability": 0.38}
        }
        """.utf8))

        let liveEvent = try d.decode(EventDetail.self, from: Data("""
        {
          "id": 15354014,
          "home_team": "UCF Knights",
          "away_team": "Jacksonville Dolphins",
          "status": "live",
          "sport": "basketball_ncaab",
          "commence_time": "\(pastStamp)",
          "current_odds": {"home_probability": 0.85, "away_probability": 0.15}
        }
        """.utf8))

        let stub = try d.decode(EventHistoryResponse.self, from: Data("""
        {
          "event_id": 15353109,
          "home_team": "Louisville Cardinals",
          "away_team": "Texas Tech Red Raiders",
          "status": "scheduled",
          "commence_time": "\(pastStamp)",
          "commence_time_is_kickoff": true,
          "pre_window_omitted": true,
          "history": [
            {"timestamp": "\(pastStamp)", "home_probability": 0.62, "away_probability": 0.38},
            {"timestamp": "\(postTip)", "home_probability": 0.62, "away_probability": 0.38}
          ]
        }
        """.utf8))

        let full = try d.decode(EventHistoryResponse.self, from: Data("""
        {
          "event_id": 15353109,
          "home_team": "Louisville Cardinals",
          "away_team": "Texas Tech Red Raiders",
          "status": "scheduled",
          "commence_time": "\(pastStamp)",
          "commence_time_is_kickoff": true,
          "pre_window_omitted": false,
          "history": [
            {"timestamp": "\(pregameEarly)", "home_probability": 0.55, "away_probability": 0.45},
            {"timestamp": "\(pregameMid)", "home_probability": 0.59, "away_probability": 0.41},
            {"timestamp": "\(pastStamp)", "home_probability": 0.62, "away_probability": 0.38},
            {"timestamp": "\(postTip)", "home_probability": 0.62, "away_probability": 0.38}
          ]
        }
        """.utf8))

        // 1. Pure helper matrix (#13683): scheduled delayed tip & un-offered Since Start must upgrade even at default .sinceStart.
        XCTAssertTrue(
            OddsChartView.needsFullHistoryUpgrade(
                status: "scheduled",
                commenceTime: pastKickoff,
                history: stub,
                selectedRange: .sinceStart
            )
        )
        XCTAssertFalse(
            OddsChartView.needsFullHistoryUpgrade(
                status: "live",
                commenceTime: pastKickoff,
                history: stub,
                selectedRange: .sinceStart
            )
        )
        XCTAssertTrue(
            OddsChartView.needsFullHistoryUpgrade(
                status: "live",
                commenceTime: pastKickoff,
                history: stub,
                selectedRange: .all
            )
        )

        // 2. EventDetailViewModel automatically upgrades delayed scheduled games, leaving live games on since_start.
        let delayedProvider = RecordingEventDetailProvider(detail: delayedEvent, sinceStartPayload: stub, allPayload: full)
        let delayedVM = EventDetailViewModel(eventId: 15353109, client: delayedProvider)
        await delayedVM.load()
        XCTAssertEqual(delayedProvider.requests.map(\.range), ["since_start", "all"])
        XCTAssertEqual(delayedVM.history?.preWindowOmitted, false)
        XCTAssertEqual(delayedVM.history?.history.count, 4)

        let liveProvider = RecordingEventDetailProvider(detail: liveEvent, sinceStartPayload: stub, allPayload: full)
        let liveVM = EventDetailViewModel(eventId: 15354014, client: liveProvider)
        await liveVM.load()
        XCTAssertEqual(liveProvider.requests.map(\.range), ["since_start"])
        XCTAssertEqual(liveVM.history?.preWindowOmitted, true)
        XCTAssertEqual(liveVM.history?.history.count, 2)

        // 3. Standalone OddsChartView (without preloadedHistory) also auto-upgrades on delayed tip.
        var standaloneRanges: [String?] = []
        let chartVM = OddsChartViewModel(eventId: 15353109) { _, range in
            standaloneRanges.append(range)
            return range == "all" ? full : stub
        }
        let chartHostView = OddsChartView(
            eventId: 15353109,
            commenceTime: pastStamp,
            status: "scheduled",
            homeTeamName: "Louisville Cardinals",
            awayTeamName: "Texas Tech Red Raiders",
            sportKey: "basketball_ncaab",
            selectedRange: .constant(.sinceStart),
            model: chartVM
        )
        .frame(width: 390, height: 470)
        let standaloneHost = UIHostingController(rootView: chartHostView)
        let standaloneScene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let standaloneWindow: UIWindow = standaloneScene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 470))
        standaloneWindow.frame = CGRect(x: 0, y: 0, width: 390, height: 470)
        standaloneWindow.rootViewController = standaloneHost
        standaloneWindow.isHidden = false
        let waitDeadline = Date().addingTimeInterval(2.0)
        while standaloneRanges.count < 2 && Date() < waitDeadline {
            RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05))
        }
        standaloneWindow.isHidden = true
        standaloneWindow.rootViewController = nil
        XCTAssertEqual(standaloneRanges, ["since_start", "all"])
        XCTAssertEqual(chartVM.history?.preWindowOmitted, false)
        XCTAssertEqual(chartVM.history?.history.count, 4)
    }

    func testDelayedTip15353109ProofBeforeVsAfterRender390pt() async throws {
        let proofDir = "\(Self.scratchDir)/13683-proof"
        let eventURL = URL(fileURLWithPath: "\(proofDir)/15353109-delayed-event.json")
        let ssURL = URL(fileURLWithPath: "\(proofDir)/15353109-delayed-ss.json")
        let allURL = URL(fileURLWithPath: "\(proofDir)/15353109-delayed-all.json")

        let d = Self.decoder()
        let event: EventDetail
        let ssHistory: EventHistoryResponse
        let allHistory: EventHistoryResponse

        if FileManager.default.fileExists(atPath: eventURL.path),
           FileManager.default.fileExists(atPath: ssURL.path),
           FileManager.default.fileExists(atPath: allURL.path) {
            event = try d.decode(EventDetail.self, from: Data(contentsOf: eventURL))
            ssHistory = try d.decode(EventHistoryResponse.self, from: Data(contentsOf: ssURL))
            allHistory = try d.decode(EventHistoryResponse.self, from: Data(contentsOf: allURL))
        } else {
            let pastStamp = "2026-11-24T01:30:00Z"
            event = try d.decode(EventDetail.self, from: Data("""
            {
              "id": 15353109,
              "home_team": "Louisville Cardinals",
              "away_team": "Texas Tech Red Raiders",
              "status": "scheduled",
              "sport": "basketball_ncaab",
              "commence_time": "\(pastStamp)",
              "current_odds": {"home_probability": 0.62, "away_probability": 0.38}
            }
            """.utf8))
            ssHistory = try makeHistory(preWindowOmitted: true, timestamps: [pastStamp, "2026-11-24T01:35:00Z"])
            allHistory = try makeHistory(preWindowOmitted: false, timestamps: [
                "2026-11-23T12:00:00Z", "2026-11-23T18:00:00Z", pastStamp, "2026-11-24T01:35:00Z",
            ])
        }

        let provider = RecordingEventDetailProvider(detail: event, sinceStartPayload: ssHistory, allPayload: allHistory)
        let vm = EventDetailViewModel(eventId: event.id, client: provider)
        await vm.load()

        XCTAssertEqual(provider.requests.map(\.range), ["since_start", "all"])
        let upgraded = try XCTUnwrap(vm.history)
        XCTAssertEqual(upgraded.preWindowOmitted, false)
        XCTAssertGreaterThan(upgraded.aggregateLine?.count ?? upgraded.history.count, ssHistory.aggregateLine?.count ?? ssHistory.history.count)

        let colors = TeamTextContrast.cardColors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor,
            awaySecondaryHex: event.awayTeamData?.secondaryColor,
            checkHueFamily: true
        )

        func panel(_ history: EventHistoryResponse, scheme: ColorScheme) -> UIImage {
            renderSlice(width: 390, height: 470, scheme: scheme) {
                OddsChartView(
                    eventId: event.id,
                    teamColors: colors,
                    commenceTime: event.commenceTime,
                    status: event.status,
                    homeTeamName: event.homeTeam,
                    awayTeamName: event.awayTeam,
                    homeTeamAbbrev: event.homeTeamData?.abbreviation,
                    awayTeamAbbrev: event.awayTeamData?.abbreviation,
                    sportKey: event.sport,
                    servedHomeProbability: event.currentOdds?.homeProbability,
                    servedAwayProbability: event.currentOdds?.awayProbability,
                    selectedRange: .constant(.sinceStart),
                    preloadedHistory: history
                )
                .padding(12)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
                .padding(12)
                .frame(width: 390, height: 470, alignment: .topLeading)
                .background(Color(.systemGroupedBackground))
            }
        }

        let beforeLight = panel(ssHistory, scheme: .light)
        let afterLight = panel(upgraded, scheme: .light)
        let beforeDark = panel(ssHistory, scheme: .dark)
        let afterDark = panel(upgraded, scheme: .dark)

        XCTAssertEqual(beforeLight.size.width, 390, accuracy: 0.5)
        XCTAssertEqual(afterLight.size.width, 390, accuracy: 0.5)

        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13683_DIR"], !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
            try savePNG(beforeLight, to: "\(outDir)/before-delayed-light-390.png")
            try savePNG(afterLight, to: "\(outDir)/after-delayed-light-390.png")
            try savePNG(beforeDark, to: "\(outDir)/before-delayed-dark-390.png")
            try savePNG(afterDark, to: "\(outDir)/after-delayed-dark-390.png")
        }
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
