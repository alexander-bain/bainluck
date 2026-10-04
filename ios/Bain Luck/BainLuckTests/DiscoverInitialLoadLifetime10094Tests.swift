import Foundation
import XCTest
@testable import Bain_Luck

@MainActor
final class DiscoverInitialLoadLifetime10094Tests: XCTestCase {
    /// Unlike a continuation that ignores cancellation, this transport throws when
    /// its owning fetch task is cancelled. The direct-load control proves that
    /// property, so the appearance test cannot pass because of an inert fake.
    private nonisolated final class Client: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var continuation: CheckedContinuation<Void, Error>?
        private var terminal: Result<Void, Error>?
        private var count = 0
        private var principal = "anon:s1"
        private let first: FeedResponse
        private let later: FeedResponse
        let arrived: XCTestExpectation

        init(first: FeedResponse, later: FeedResponse, arrived: XCTestExpectation) {
            self.first = first; self.later = later; self.arrived = arrived
        }
        var callCount: Int { lock.withLock { count } }
        func changePrincipal(to value: String) { lock.withLock { principal = value } }
        func release() { finish(.success(())) }
        private func finish(_ result: Result<Void, Error>) {
            let pending = lock.withLock { () -> CheckedContinuation<Void, Error>? in
                guard terminal == nil else { return nil }
                terminal = result
                let pending = continuation; continuation = nil
                return pending
            }
            pending?.resume(with: result)
        }
        func currentFeedPrincipal() async -> String { lock.withLock { principal } }
        func fetchDiscoverFeed(limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?) async throws -> FeedResponse {
            try await fetchDiscoverFeedResolvingPrincipal(limit: limit, offset: offset, eventPct: eventPct, cacheTTL: cacheTTL).response
        }
        func fetchDiscoverFeedResolvingPrincipal(limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?) async throws -> DiscoverFeedFetchResult {
            let (number, dispatch) = lock.withLock { () -> (Int, String) in
                count += 1; return (count, principal)
            }
            if number == 1 {
                try await withTaskCancellationHandler {
                    try await withCheckedThrowingContinuation { (pending: CheckedContinuation<Void, Error>) in
                        let result = lock.withLock { () -> Result<Void, Error>? in
                            if let terminal { return terminal }
                            continuation = pending; return nil
                        }
                        if let result { pending.resume(with: result) }
                        arrived.fulfill()
                    }
                } onCancel: {
                    self.finish(.failure(CancellationError()))
                }
            }
            return DiscoverFeedFetchResult(response: number == 1 ? first : later,
                identityAtFetch: dispatch, wasAuthenticated: dispatch.hasPrefix("user:"),
                expectedSignedIn: dispatch.hasPrefix("user:"))
        }
    }

    private nonisolated final class Cache: DiscoverLastGoodReading, @unchecked Sendable {
        let payload: CachedDiscoverFeed
        init(_ response: FeedResponse) {
            payload = CachedDiscoverFeed(response: response, storedAt: Date(), ttlSeconds: 5, identity: "anon:s1")
        }
        func loadLastGoodFeed() async -> CachedDiscoverFeed? { payload }
    }

    private func response(_ id: Int) throws -> FeedResponse {
        let json = """
        {"items":[{"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1}],"outcome_count":1}}],"total":1,"limit":50,"offset":0,"has_more":false}
        """
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedResponse.self, from: Data(json.utf8))
    }
    private func ids(_ model: DiscoverViewModel) -> [Int] { model.items.compactMap { $0.futures?.id } }

    func testAppearanceOwnerCancellationStillReplacesSeedWithFreshFeed() async throws {
        let arrived = expectation(description: "initial fetch suspended after cache seed")
        let finished = expectation(description: "cancelled appearance owner completed")
        let client = Client(first: try response(20), later: try response(30), arrived: arrived)
        let model = DiscoverViewModel(client: client, lastGood: Cache(try response(10)), telemetry: nil)
        var outcome: DiscoverLoadOutcome?
        let owner = Task { @MainActor in
            outcome = await DiscoverView.loadForInitialAppearance(model)
            finished.fulfill()
        }
        await fulfillment(of: [arrived], timeout: 5)
        XCTAssertEqual(ids(model), [10]); XCTAssertTrue(model.isShowingCachedContent)
        owner.cancel()
        client.release()
        await fulfillment(of: [finished], timeout: 5)
        XCTAssertEqual(outcome, .published)
        XCTAssertEqual(ids(model), [20]); XCTAssertFalse(model.isShowingCachedContent)
        XCTAssertFalse(model.loading); XCTAssertNil(model.error)
        XCTAssertEqual(client.callCount, 1)
    }

    func testDirectLoadCancellationRemainsQuietAndKeepsSeed() async throws {
        let arrived = expectation(description: "direct load suspended")
        let finished = expectation(description: "direct cancellation settled")
        let client = Client(first: try response(20), later: try response(30), arrived: arrived)
        let model = DiscoverViewModel(client: client, lastGood: Cache(try response(10)), telemetry: nil)
        var outcome: DiscoverLoadOutcome?
        let owner = Task { @MainActor in outcome = await model.load(); finished.fulfill() }
        await fulfillment(of: [arrived], timeout: 5)
        owner.cancel()
        await fulfillment(of: [finished], timeout: 5)
        client.release() // Cleanup if the control failed; does not rescue its assertions.
        XCTAssertEqual(outcome, .cancelled)
        XCTAssertEqual(ids(model), [10]); XCTAssertTrue(model.isShowingCachedContent)
        XCTAssertFalse(model.loading); XCTAssertNil(model.error)
        XCTAssertEqual(client.callCount, 1)
    }

    func testCancelledAppearanceCannotOverwriteIdentityRebind() async throws {
        let arrived = expectation(description: "old identity request suspended")
        let finished = expectation(description: "old appearance settled")
        let client = Client(first: try response(20), later: try response(30), arrived: arrived)
        let model = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil)
        var outcome: DiscoverLoadOutcome?
        let owner = Task { @MainActor in
            outcome = await DiscoverView.loadForInitialAppearance(model); finished.fulfill()
        }
        await fulfillment(of: [arrived], timeout: 5)
        owner.cancel()
        client.changePrincipal(to: "user:b")
        await model.rebindForIdentityChange()
        XCTAssertEqual(ids(model), [30])
        client.release()
        await fulfillment(of: [finished], timeout: 5)
        XCTAssertEqual(outcome, .superseded)
        XCTAssertEqual(ids(model), [30]); XCTAssertNil(model.error)
    }

    func testPrincipalChangeWithoutRebindRejectsLateAppearanceResponse() async throws {
        let arrived = expectation(description: "anonymous dispatch suspended")
        let finished = expectation(description: "appearance settled under changed principal")
        let client = Client(first: try response(20), later: try response(30), arrived: arrived)
        let model = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil, retryBackoff: 0)
        let owner = Task { @MainActor in
            _ = await DiscoverView.loadForInitialAppearance(model); finished.fulfill()
        }
        await fulfillment(of: [arrived], timeout: 5)
        owner.cancel()
        client.changePrincipal(to: "user:b")
        client.release()
        await fulfillment(of: [finished], timeout: 5)
        XCTAssertEqual(ids(model), [30], "The old anonymous response must be refused before a current-principal response can publish")
        XCTAssertEqual(client.callCount, 2)
        XCTAssertNil(model.error)
    }
}
