import XCTest
import Foundation
@testable import Bain_Luck

/// #9387 — the page-level half of the verified championship detail: what the
/// detail asks for, what pull-to-refresh reloads, a newer verified answer
/// adopted through the real view model, the share sentence, and the request the
/// real `APIClient` puts on the wire. Fixtures: `VerifiedTitle9387Fixtures`
/// (real-route responses; provenance on `VerifiedTitleConsumer9387Tests`).
@MainActor
final class VerifiedTitleReconciliation9387Tests: XCTestCase {
    private typealias F = VerifiedTitle9387Fixtures
    private let buffalo = 1_309_486

    private func detail(_ json: String) throws -> FuturesMarketDetail {
        try VerifiedTitleConsumer9387Tests.detail(json)
    }

    /// The verified trio body after an eligible sibling venue moved Buffalo to
    /// `value`. Every clock — `last_updated`, `observed_at` — is unchanged.
    private func siblingMoved(_ value: Double) throws -> FuturesMarketDetail {
        try detail(try VerifiedTitleConsumer9387Tests.edited(F.detailVerified) { object in
            VerifiedTitleConsumer9387Tests.editOutcome(&object, "Buffalo Bills") { $0["probability"] = value }
        })
    }

    @MainActor
    private final class Provider: FuturesDetailProviding {
        var response: FuturesMarketDetail
        var asked: [FuturesRepresentation] = []
        var beforeResponse: (() async -> Void)?
        init(_ response: FuturesMarketDetail) { self.response = response }
        func fetchFuturesDetail(id: Int) async throws -> FuturesMarketDetail {
            try await fetchFuturesDetail(id: id, representation: .source)
        }
        func fetchFuturesDetail(id: Int, representation: FuturesRepresentation) async throws -> FuturesMarketDetail {
            asked.append(representation)
            let result = response
            if let beforeResponse { await beforeResponse() }
            return result
        }
    }

    /// A provider written before #9387 existed: the one-argument method only.
    @MainActor
    private final class PreFeatureProvider: FuturesDetailProviding {
        let response: FuturesMarketDetail
        var count = 0
        init(_ response: FuturesMarketDetail) { self.response = response }
        func fetchFuturesDetail(id: Int) async throws -> FuturesMarketDetail {
            count += 1
            return response
        }
    }

    private func settle(_ condition: () -> Bool) async {
        for _ in 0..<300 where !condition() { await Task.yield() }
    }

    private func buffaloValue(_ vm: FuturesDetailViewModel) -> Double? {
        vm.market?.outcomes.first { $0.id == buffalo }?.probability
    }

    // MARK: - What the page asks for

    func testTheDetailPageAsksForVerifiedAndAnExplicitSourcePageDoesNot() async throws {
        let provider = Provider(try detail(F.detailVerified))
        let vm = FuturesDetailViewModel(marketId: 86832, client: provider)
        XCTAssertEqual(vm.representation, .verifiedTitle)
        await vm.load()
        XCTAssertEqual(provider.asked, [.verifiedTitle])
        XCTAssertEqual(vm.market?.effectiveRepresentation, .verifiedTitle)

        let control = Provider(try detail(F.detailDefault))
        await FuturesDetailViewModel(marketId: 86832, representation: .source, client: control).load()
        XCTAssertEqual(control.asked, [.source])
    }

    func testAProviderWrittenBeforeTheOptInStillServesThePage() async throws {
        let provider = PreFeatureProvider(try detail(F.detailDefault))
        let vm = FuturesDetailViewModel(marketId: 86832, client: provider)
        await vm.load()
        XCTAssertEqual(provider.count, 1)
        XCTAssertEqual(vm.market?.effectiveRepresentation, .source)
    }

    // MARK: - Newer answers, refresh and stale generations

    /// Item 6 through the real page: the origin clock stands still, a sibling
    /// venue moved the blend, and the page adopts it and moves its chart.
    func testANewerVerifiedAnswerIsAdoptedThroughThePageAndMovesTheChart() async throws {
        let provider = Provider(try detail(F.detailVerified))
        let vm = FuturesDetailViewModel(marketId: 86832, client: provider)
        await vm.load()
        let token = vm.chartRefreshToken
        provider.response = try siblingMoved(0.14)
        await vm.load()
        XCTAssertEqual(buffaloValue(vm), 0.14)
        XCTAssertEqual(vm.chartRefreshToken, token + 1)
    }

    func testPullToRefreshReloadsTheDetailAndTheChartExactlyOnce() async throws {
        let provider = Provider(try detail(F.detailVerified))
        let vm = FuturesDetailViewModel(marketId: 86832, client: provider)
        await vm.load()
        let token = vm.chartRefreshToken
        // Unchanged body: the chart still owes the reader one fresh read.
        await vm.refresh()
        XCTAssertEqual(provider.asked.count, 2)
        XCTAssertEqual(vm.chartRefreshToken, token + 1)
        // Changed body: the adoption moves the chart; refresh adds nothing more.
        provider.response = try siblingMoved(0.14)
        await vm.refresh()
        XCTAssertEqual(buffaloValue(vm), 0.14)
        XCTAssertEqual(vm.chartRefreshToken, token + 2)
    }

    func testAnOlderInFlightVerifiedReadCannotOverwriteANewerOne() async throws {
        let provider = Provider(try detail(F.detailVerified))
        let vm = FuturesDetailViewModel(marketId: 86832, client: provider)
        var waiting: CheckedContinuation<Void, Never>?
        provider.beforeResponse = { await withCheckedContinuation { waiting = $0 } }
        let older = Task { await vm.load() }
        await settle { waiting != nil }
        provider.beforeResponse = nil
        provider.response = try siblingMoved(0.14)
        await vm.load()
        waiting?.resume()
        await older.value
        XCTAssertEqual(buffaloValue(vm), 0.14, "the 0.13 read was asked first and lands last")
    }

    // MARK: - Share

    func testAVerifiedShareNamesTheQuestionAndCarriesNoNumber() throws {
        let message = futuresDetailShareMessage(try detail(F.detailVerified))
        XCTAssertEqual(message, "NFL Super Bowl Winner on Bain Luck")
        XCTAssertFalse(message.contains("%"))
    }

    func testASourceShareIsUnchanged() throws {
        XCTAssertEqual(futuresDetailShareMessage(try detail(F.detailDefault)),
                       "Buffalo Bills at 11% — NFL Super Bowl Winner on Bain Luck")
        XCTAssertEqual(futuresDetailShareMessage(nil), "Check this out on Bain Luck")
    }

    // MARK: - The request on the wire (real APIClient, stubbed server)

    private nonisolated final class Origin: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var captured: [URLRequest] = []

        static func reset() {
            lock.lock(); defer { lock.unlock() }
            captured = []
        }
        static func requests() -> [URLRequest] {
            lock.lock(); defer { lock.unlock() }
            return captured
        }
        private static func response(to request: URLRequest) -> (Int, Data) {
            lock.lock(); defer { lock.unlock() }
            captured.append(request)
            let path = request.url?.path ?? ""
            let verified = request.url?.query?.contains("representation=verified_title") == true
            if path == "/api/futures/86832" {
                return (200, Data((verified ? F.detailVerified : F.detailDefault).utf8))
            }
            if path == "/api/futures/86832/probability-timeline" {
                return (200, Data((verified ? F.timelineVerified : F.timelineDefault).utf8))
            }
            return (404, Data("{}".utf8))
        }
        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            let (status, data) = Self.response(to: request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private func api() -> APIClient {
        Origin.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        return APIClient(session: URLSession(configuration: configuration))
    }

    func testTheOptInIsAQueryParameterAndTheDefaultRequestIsUnchanged() async throws {
        let client = api()
        let source = try await client.fetchFuturesDetail(id: 86832)
        let verified = try await client.fetchFuturesDetail(id: 86832, representation: .verifiedTitle)
        let sourceChart = try await client.fetchProbabilityTimeline(marketId: 86832, top: 50, hours: 168)
        let verifiedChart = try await client.fetchProbabilityTimeline(
            marketId: 86832, top: 50, hours: 168, representation: .verifiedTitle)

        let queries = Origin.requests().map {
            URLComponents(url: $0.url!, resolvingAgainstBaseURL: false)?.queryItems ?? []
        }
        XCTAssertEqual(queries.count, 4)
        let representation = queries.map { items in items.first { $0.name == "representation" }?.value }
        XCTAssertEqual(representation, [nil, "verified_title", nil, "verified_title"])
        XCTAssertEqual(queries[3].first { $0.name == "top" }?.value, "50")
        XCTAssertEqual(queries[3].first { $0.name == "hours" }?.value, "168")

        XCTAssertEqual(source.effectiveRepresentation, .source)
        XCTAssertEqual(verified.effectiveRepresentation, .verifiedTitle)
        XCTAssertNil(sourceChart.historyBasis)
        XCTAssertEqual(verifiedChart.historyBasis?.source, "odds_api")
    }
}
