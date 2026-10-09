import XCTest
@testable import Bain_Luck

/// L2-192 Item 2 / C26 P2 — `DiscoverViewModel` pagination must always terminate
/// in one of three honest states (new cards, honest exhaustion, or a retryable
/// error) and never sit on an indefinite "Finding fresh markets…" spinner.
///
/// These drive the view model through a deterministic fake feed client (the
/// `DiscoverFeedProviding` seam) so offsets, `hasMore`, duplicate-only pages,
/// decoded-empty pages, failures, cancellation, and concurrent calls are all
/// exercised — none of which a pure predicate test can reach.
final class DiscoverViewModelPaginationTests: XCTestCase {

    // MARK: - Fake client

    /// Holds one request until the test explicitly releases it.
    private actor HeldRequest {
        private let entered: XCTestExpectation
        private var continuation: CheckedContinuation<Void, Never>?
        private var released = false

        init(entered: XCTestExpectation) { self.entered = entered }

        func wait() async {
            entered.fulfill()
            await withCheckedContinuation { continuation in
                if released {
                    continuation.resume()
                } else {
                    self.continuation = continuation
                }
            }
        }

        func release() {
            released = true
            continuation?.resume()
            continuation = nil
        }
    }

    private enum Reply {
        case ok(FeedResponse)
        case fail(Error)
    }

    /// Nonisolated (off-MainActor) fake so `fetchDiscoverFeed` genuinely suspends
    /// when awaited from the MainActor view model — required for the concurrency
    /// guard test. State is lock-guarded (`@unchecked Sendable`).
    private nonisolated final class FakeFeedClient: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var script: [Reply]
        private var offsets: [Int] = []
        private var editions: [String?] = []
        private var limits: [Int] = []
        private var heldRequest: HeldRequest?

        init(_ script: [Reply]) { self.script = script }

        var requestedOffsets: [Int] { lock.withLock { offsets } }
        /// #5105: the edition token each request carried (nil = unpinned).
        var requestedEditions: [String?] { lock.withLock { editions } }
        var requestedLimits: [Int] { lock.withLock { limits } }

        func reset() {
            lock.withLock { offsets.removeAll(); editions.removeAll(); limits.removeAll() }
        }

        func append(_ replies: [Reply]) { lock.withLock { script += replies } }

        func holdNextRequest(_ request: HeldRequest) {
            lock.withLock { heldRequest = request }
        }

        nonisolated func fetchDiscoverFeed(
            limit: Int,
            offset: Int,
            eventPct: Double?,
            cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            try await fetchDiscoverFeed(
                limit: limit, offset: offset, eventPct: eventPct, edition: nil, cacheTTL: cacheTTL)
        }

        nonisolated func fetchDiscoverFeed(
            limit: Int,
            offset: Int,
            eventPct: Double?,
            edition: String?,
            cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            let held = lock.withLock {
                let request = heldRequest
                heldRequest = nil
                return request
            }
            if let held {
                await withTaskCancellationHandler {
                    await held.wait()
                } onCancel: {
                    Task { await held.release() }
                }
            }
            return try lock.withLock {
                offsets.append(offset)
                editions.append(edition)
                limits.append(limit)
                guard !script.isEmpty else {
                    // Safety default: honest exhaustion so an over-scan can't crash.
                    return try DiscoverViewModelPaginationTests.emptyResponse(offset: offset, hasMore: false)
                }
                switch script.removeFirst() {
                case .ok(let r): return r
                case .fail(let e): throw e
                }
            }
        }
    }

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private static func futuresJSON(id: Int, probability: Double = 0.55) -> String {
        """
        {
          "type": "futures",
          "score": 90,
          "data": {
            "id": \(id),
            "name": "Market \(id)?",
            "llm_sport_category": "economics",
            "source": "kalshi",
            "status": "open",
            "top_outcomes": [{"id": \(id * 10), "name": "A", "probability": \(probability), "rank": 1, "movement": 0.02}],
            "outcome_count": 1
          }
        }
        """
    }

    /// `limit` defaults to the decoded item count so no-malformed fixtures
    /// advance one page == one returned batch. Pass an explicit `limit` (the
    /// server page width) to model tolerant decode loss, where the client decodes
    /// FEWER items than the server sent and pagination must still advance by
    /// `offset + limit` (C29).
    private static func response(ids: [Int], offset: Int, hasMore: Bool, limit: Int? = nil) throws -> FeedResponse {
        let items = ids.map { futuresJSON(id: $0) }.joined(separator: ",")
        let json = """
        {"items":[\(items)],"total":9999,"limit":\(limit ?? ids.count),"offset":\(offset),"has_more":\(hasMore)}
        """
        return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private static func emptyResponse(offset: Int, hasMore: Bool, limit: Int = 200) throws -> FeedResponse {
        let json = """
        {"items":[],"total":9999,"limit":\(limit),"offset":\(offset),"has_more":\(hasMore)}
        """
        return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    /// A malformed feed element the tolerant `FeedResponse` decoder drops: no
    /// `type` key → `FeedItem.init` throws → the SkipOne fallback consumes it.
    private static func malformedItemJSON() -> String {
        """
        {"garbage": true, "score": 1}
        """
    }

    /// A full server page of `count` slots, ALL of which fail to decode — decoded
    /// `items` is empty though the server reports `limit` slots and `has_more`.
    /// Models total decode loss on a page (C29 P1).
    private static func malformedPage(count: Int, offset: Int, hasMore: Bool, limit: Int = 200) throws -> FeedResponse {
        let items = Array(repeating: malformedItemJSON(), count: count).joined(separator: ",")
        let json = """
        {"items":[\(items)],"total":9999,"limit":\(limit),"offset":\(offset),"has_more":\(hasMore)}
        """
        return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    /// A server page mixing valid futures with malformed slots — decoded
    /// `items.count` < server `limit`. Models partial decode loss (C29 P1).
    private static func mixedPage(validIds: [Int], malformedCount: Int, offset: Int, hasMore: Bool, limit: Int = 200) throws -> FeedResponse {
        let valid = validIds.map { futuresJSON(id: $0) }
        let bad = Array(repeating: malformedItemJSON(), count: malformedCount)
        let items = (valid + bad).joined(separator: ",")
        let json = """
        {"items":[\(items)],"total":9999,"limit":\(limit),"offset":\(offset),"has_more":\(hasMore)}
        """
        return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    /// Initial load page with enough renderable items (>10) that `load()` takes
    /// the primary path and does not trigger its low-count fallback fetch.
    private static func initialPage(hasMore: Bool = true) throws -> FeedResponse {
        try response(ids: Array(1...12), offset: 0, hasMore: hasMore)
    }

    /// Build a VM already past initial load, with the fake's call log cleared so
    /// pagination-offset assertions start from a clean slate.
    @MainActor
    private func loadedVM(_ replies: [Reply]) async throws -> (DiscoverViewModel, FakeFeedClient) {
        let fake = FakeFeedClient([.ok(try Self.initialPage())] + replies)
        // lastGood/telemetry nil so these pagination tests stay hermetic (no disk
        // cache read, no Firebase) — the SWR cache path is covered separately.
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)
        await vm.load()
        XCTAssertFalse(vm.loading, "initial load should clear loading")
        XCTAssertEqual(vm.items.count, 12, "initial page should populate 12 items")
        fake.reset()
        return (vm, fake)
    }

    // MARK: - Tests

    @MainActor
    func testNewEligiblePageAppendsCards() async throws {
        let (vm, fake) = try await loadedVM([
            .ok(try Self.response(ids: [500], offset: 12, hasMore: true)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(vm.items.count, 13)
        XCTAssertTrue(vm.hasMore)
        XCTAssertNil(vm.error)
        let offsets = fake.requestedOffsets
        XCTAssertEqual(offsets, [12], "should fetch exactly the next page, not offset 0")
    }

    @MainActor
    func testDistinctAllStalePagesThenExhaustion() async throws {
        // Each page has NEW ids (so items.count grows and the view would retrigger)
        // and the final page reports no more — pagination must reach hasMore=false.
        let (vm, _) = try await loadedVM([
            .ok(try Self.response(ids: [100, 101, 102], offset: 12, hasMore: true)),
            .ok(try Self.response(ids: [200, 201, 202], offset: 15, hasMore: false)),
        ])
        await vm.loadMoreIfNeeded()   // page A appended, hasMore still true
        XCTAssertTrue(vm.hasMore)
        XCTAssertEqual(vm.items.count, 15)

        await vm.loadMoreIfNeeded()   // page B appended, server says done
        XCTAssertFalse(vm.hasMore, "must terminate as caught-up")
        XCTAssertNil(vm.error)
        XCTAssertEqual(vm.items.count, 18)
    }

    @MainActor
    func testDuplicateOnlyPagesSurfaceRetry() async throws {
        // Every page returns only already-loaded ids (1...12) but the server keeps
        // claiming hasMore=true and the offset advances each page. The paginator
        // must scan a bounded window then surface a retryable error — never spin.
        var replies: [Reply] = []
        for k in 1...6 {
            replies.append(.ok(try Self.response(ids: Array(1...12), offset: 12 * k, hasMore: true)))
        }
        let (vm, fake) = try await loadedVM(replies)
        await vm.loadMoreIfNeeded()

        XCTAssertNotNil(vm.error, "bounded duplicate scan must expose a retryable error")
        XCTAssertTrue(vm.hasMore, "server still claims more; not a false exhaustion")
        XCTAssertEqual(vm.items.count, 12, "no duplicate content appended")
        let offsets = fake.requestedOffsets
        XCTAssertFalse(offsets.contains(0), "must never refetch offset 0")
        XCTAssertEqual(offsets, offsets.sorted(), "offset must advance monotonically")
        XCTAssertEqual(Set(offsets).count, offsets.count, "no repeated offset")
    }

    @MainActor
    func testDecodedEmptyPageWithHasMoreScansToTerminal() async throws {
        // C29 P1: a decoded-empty page with hasMore=true must NOT falsely end the
        // feed. It advances by the server page boundary (offset + limit) and keeps
        // scanning; only the SERVER's own hasMore=false terminates.
        let (vm, fake) = try await loadedVM([
            .ok(try Self.emptyResponse(offset: 12, hasMore: true)),   // decoded-empty, server says more
            .ok(try Self.emptyResponse(offset: 212, hasMore: false)), // server now says done
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertFalse(vm.hasMore, "terminates only on server hasMore=false")
        XCTAssertNil(vm.error)
        XCTAssertEqual(vm.items.count, 12)
        let offsets = fake.requestedOffsets
        XCTAssertEqual(offsets, [12, 212], "must scan past the decoded-empty page to the next server page (offset + limit)")
    }

    @MainActor
    func testTerminalEmptyPageTerminates() async throws {
        // A single empty page that the SERVER marks hasMore=false is honest
        // exhaustion — caught-up, no error, no further fetch.
        let (vm, fake) = try await loadedVM([
            .ok(try Self.emptyResponse(offset: 12, hasMore: false)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertFalse(vm.hasMore, "server hasMore=false is caught-up")
        XCTAssertNil(vm.error)
        XCTAssertEqual(vm.items.count, 12)
        XCTAssertEqual(fake.requestedOffsets, [12])
    }

    @MainActor
    func testFullyMalformedPageAdvancesToValidContent() async throws {
        // C29 P1: an entire page whose slots all fail to decode (items.count == 0)
        // while hasMore=true must advance by the server boundary and reach valid
        // content on the next page — never declare exhaustion on decode loss.
        let (vm, fake) = try await loadedVM([
            .ok(try Self.malformedPage(count: 8, offset: 12, hasMore: true, limit: 200)),
            .ok(try Self.response(ids: [500], offset: 212, hasMore: true, limit: 200)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(vm.items.count, 13, "valid content on the next server page appends")
        XCTAssertTrue(vm.hasMore, "not a false exhaustion — decode loss must not end the feed")
        XCTAssertNil(vm.error)
        XCTAssertEqual(fake.requestedOffsets, [12, 212], "advance by offset + limit (server boundary), not decoded count")
    }

    @MainActor
    func testPartiallyMalformedPageAdvancesByServerBoundaryNoOverlap() async throws {
        // C29 P1: a page with one valid item + malformed slots must advance the
        // NEXT fetch to offset + limit (212), not offset + decoded-count (13) —
        // otherwise the next request overlaps the prior server page and burns the
        // scan budget on duplicates.
        let (vm, fake) = try await loadedVM([
            .ok(try Self.mixedPage(validIds: [500], malformedCount: 5, offset: 12, hasMore: true, limit: 200)),
            .ok(try Self.response(ids: [600], offset: 212, hasMore: false, limit: 200)),
        ])
        await vm.loadMoreIfNeeded()   // appends 500, advances offset to 212
        XCTAssertEqual(vm.items.count, 13)
        XCTAssertTrue(vm.hasMore)

        await vm.loadMoreIfNeeded()   // appends 600, server done
        XCTAssertEqual(vm.items.count, 14)
        XCTAssertFalse(vm.hasMore)
        XCTAssertNil(vm.error)
        XCTAssertEqual(fake.requestedOffsets, [12, 212], "second fetch targets the next server page, not an overlapping offset")
    }

    @MainActor
    func testSixMalformedPagesSurfaceRetry() async throws {
        // C29 P1: a run of fully-malformed hasMore=true pages must scan the bounded
        // window (six pages), advancing by the server boundary each time, then
        // surface a retryable error — never a false exhaustion, never a spin.
        var replies: [Reply] = []
        for k in 1...6 {
            replies.append(.ok(try Self.malformedPage(count: 4, offset: 12 + 200 * (k - 1), hasMore: true, limit: 200)))
        }
        let (vm, fake) = try await loadedVM(replies)
        await vm.loadMoreIfNeeded()

        XCTAssertNotNil(vm.error, "bounded malformed scan must expose a retryable error")
        XCTAssertTrue(vm.hasMore, "server still claims more; not a false exhaustion")
        XCTAssertEqual(vm.items.count, 12, "no content appended from malformed pages")
        let offsets = fake.requestedOffsets
        XCTAssertEqual(offsets.count, 6, "exactly the six-page scan bound")
        XCTAssertFalse(offsets.contains(0), "must never refetch offset 0")
        XCTAssertEqual(offsets, offsets.sorted(), "offset advances monotonically")
        XCTAssertEqual(Set(offsets).count, offsets.count, "no repeated offset")
        XCTAssertEqual(offsets, [12, 212, 412, 612, 812, 1012], "each scan advances by the server page boundary")
    }

    @MainActor
    func testInitialLoadUsesServerPageBoundary() async throws {
        // C29 P1 (acceptance: initial and incremental load share the page-boundary
        // contract): an initial page with a malformed tail (decoded 12, server
        // limit 200, hasMore=true) must set the next offset to 200, so the first
        // loadMore targets offset 200 — not 12 (decoded count).
        let fake = FakeFeedClient([
            .ok(try Self.mixedPage(validIds: Array(1...12), malformedCount: 5, offset: 0, hasMore: true, limit: 200)),
            .ok(try Self.response(ids: [500], offset: 200, hasMore: false, limit: 200)),
        ])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)
        await vm.load()
        XCTAssertEqual(vm.items.count, 12, "12 valid items decoded; malformed tail dropped")
        fake.reset()

        await vm.loadMoreIfNeeded()
        XCTAssertEqual(vm.items.count, 13)
        XCTAssertEqual(fake.requestedOffsets, [200], "initial load advanced by offset + limit, not decoded count")
    }

    @MainActor
    func testRequestFailureThenRetrySucceeds() async throws {
        let (vm, _) = try await loadedVM([
            .fail(URLError(.timedOut)),
            .ok(try Self.response(ids: [500], offset: 12, hasMore: true)),
        ])
        await vm.loadMoreIfNeeded()
        XCTAssertNotNil(vm.error, "network failure must surface a retryable error")
        XCTAssertEqual(vm.items.count, 12, "no partial content on failure")
        XCTAssertTrue(vm.hasMore)

        await vm.loadMoreIfNeeded()   // retry
        XCTAssertNil(vm.error, "successful retry clears the error")
        XCTAssertEqual(vm.items.count, 13)
    }

    @MainActor
    func testCancellationLeavesStateClean() async throws {
        let (vm, _) = try await loadedVM([
            .fail(CancellationError()),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertNil(vm.error, "cancellation is not a user-facing error")
        XCTAssertTrue(vm.hasMore, "cancellation leaves pagination retryable")
        XCTAssertEqual(vm.items.count, 12)
        XCTAssertFalse(vm.loadingMore)
    }

    @MainActor
    func testWrappedCancellationLeavesStateClean() async throws {
        // Production cancellation shape: pagination's fetch wraps URLSession errors,
        // so a torn-down scroll task surfaces cancellation as APIError.networkError.
        // It must not paint "Couldn't load more markets" (L2-214 Item 2).
        let (vm, _) = try await loadedVM([
            .fail(APIError.networkError(underlying: URLError(.cancelled))),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertNil(vm.error, "wrapped cancellation is not a user-facing error")
        XCTAssertTrue(vm.hasMore, "cancellation leaves pagination retryable")
        XCTAssertEqual(vm.items.count, 12)
        XCTAssertFalse(vm.loadingMore)
    }

    @MainActor
    func testConcurrentCallsIssueSingleRequest() async throws {
        let (vm, fake) = try await loadedVM([
            .ok(try Self.response(ids: [500], offset: 12, hasMore: true)),
        ])
        let entered = expectation(description: "first pagination request entered")
        let finished = expectation(description: "first pagination request finished")
        let held = HeldRequest(entered: entered)
        fake.holdNextRequest(held)
        let first = Task {
            await vm.loadMoreIfNeeded()
            finished.fulfill()
        }
        defer {
            first.cancel()
            Task { await held.release() }
        }
        await fulfillment(of: [entered], timeout: 5)
        XCTAssertTrue(vm.loadingMore, "the first request must remain in flight")
        guard vm.loadingMore else {
            await held.release()
            first.cancel()
            return
        }

        // The first request is held, so the second must exit through the guard.
        await vm.loadMoreIfNeeded()
        // Release even after an entered-wait timeout so a late request cannot
        // leave its checked continuation suspended.
        await held.release()
        await fulfillment(of: [finished], timeout: 5)

        let offsets = fake.requestedOffsets
        XCTAssertEqual(offsets.count, 1, "concurrent loadMore must not double-fetch")
        XCTAssertEqual(vm.items.count, 13)
    }

    // MARK: - #1773: the empty-envelope filter must cover EVERY page, not just page 1

    // Bug report #144 (2026-08-11, Alex): "None of these cards show probabilities."
    // The attached screenshot is six consecutive `concept` cards — two F1 Grand
    // Prix, four UFC fight cards — each rendering a title and a market count and
    // nothing else. A concept card is probability-free by construction
    // (`DiscoverConceptCard.swift`: "Concept cards are hubs, not single markets");
    // its backend payload carries `entry_count`/`fight_count` and no outcomes at
    // all (`routes/feed.py` `_score_event_concepts`).
    //
    // L2-215 Item 1 / #1486 added `renderable` precisely to fail these closed, and
    // wired it into BOTH initial-load paths — the cache seed and the network
    // publish. It was never wired into `loadMoreIfNeeded`, whose only filter was
    // the dedup `loadedIds` check. So the first page was filtered and every page
    // after it was not, and a reader who scrolled — as #144 did, all the way to
    // the bottom — fell out of the filtered region into the unfiltered one.
    //
    // The suppression METRIC had the same blind spot (`reportSuppressedEnvelopes`
    // fired only on the initial network publish), which is why nine months of
    // telemetry never showed it.

    /// A live/upcoming concept: the exact #144 card shape. Probability-free, not
    /// settled, so `suppressionReason` == `empty_concept`.
    private static func liveConceptJSON(key: String, domain: String = "ufc") -> String {
        """
        {
          "type": "concept", "score": 95, "reason": "4 fights on the card",
          "data": {
            "key": "\(key)", "name": "\(key)",
            "domain": "\(domain)", "status": "scheduled",
            "fight_count": 4, "entry_count": 0, "marquee_whathit": false
          }
        }
        """
    }

    /// A settled concept — renderable, because it can lead with a real result.
    private static func settledConceptJSON(key: String) -> String {
        """
        {
          "type": "concept", "score": 95,
          "data": {
            "key": "\(key)", "name": "\(key)",
            "domain": "ufc", "status": "settled", "marquee_whathit": true,
            "winner": "A Fighter"
          }
        }
        """
    }

    /// A futures envelope with zero outcomes and no settled state → `empty_futures`.
    private static func emptyFuturesJSON(id: Int) -> String {
        """
        {
          "type": "futures", "score": 80,
          "data": { "id": \(id), "name": "Envelope \(id)?", "status": "open",
                    "top_outcomes": [], "outcome_count": 0 }
        }
        """
    }

    /// A tournament with no golfers and no settled result → `empty_tournament`.
    private static func emptyTournamentJSON(key: String) -> String {
        """
        {
          "type": "tournament", "score": 80,
          "data": { "key": "\(key)", "name": "\(key)", "golfers": [],
                    "marquee_whathit": false }
        }
        """
    }

    private static func pageOfRawItems(
        _ raw: [String], offset: Int, hasMore: Bool, limit: Int? = nil
    ) throws -> FeedResponse {
        let json = """
        {"items":[\(raw.joined(separator: ","))],"total":9999,\
        "limit":\(limit ?? raw.count),"offset":\(offset),"has_more":\(hasMore)}
        """
        return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    @MainActor
    func testPaginationDropsLiveConceptEnvelopes() async throws {
        // The #144 page: one real market buried in six probability-free concepts.
        let (vm, _) = try await loadedVM([
            .ok(try Self.pageOfRawItems(
                [
                    Self.liveConceptJSON(key: "ufc:wells-vs-uulu"),
                    Self.liveConceptJSON(key: "ufc:van-vs-pantoja"),
                    Self.liveConceptJSON(key: "f1:italian-gp", domain: "f1"),
                    Self.liveConceptJSON(key: "ufc:silva-vs-rodriguez"),
                    Self.liveConceptJSON(key: "ufc:ruffy-vs-tsarukyan"),
                    Self.liveConceptJSON(key: "f1:washington-gp", domain: "f1"),
                    Self.futuresJSON(id: 500),
                ],
                offset: 12, hasMore: true)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(vm.items.count, 13, "only the one real market may be appended")
        let conceptCount = vm.items.filter { $0.concept != nil }.count
        XCTAssertEqual(conceptCount, 0, "no live concept envelope may survive pagination")
        XCTAssertNil(vm.error)
    }

    @MainActor
    func testPaginationKeepsSettledConceptCards() async throws {
        // The filter is fail-CLOSED, not concept-hostile: a settled concept leads
        // with a real result and must still arrive. Guards the other direction so
        // this fix cannot be "passed" by dropping concepts wholesale (gotcha #43).
        let (vm, _) = try await loadedVM([
            .ok(try Self.pageOfRawItems(
                [
                    Self.liveConceptJSON(key: "ufc:live-card"),
                    Self.settledConceptJSON(key: "ufc:settled-card"),
                ],
                offset: 12, hasMore: true)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(vm.items.count, 13)
        let concepts = vm.items.compactMap { $0.concept }
        XCTAssertEqual(concepts.count, 1, "exactly the settled concept survives")
        XCTAssertEqual(concepts.first?.marqueeWhathit, true)
    }

    @MainActor
    func testPaginationDropsEmptyFuturesAndTournamentEnvelopes() async throws {
        // The hole leaked the whole envelope matrix, not just concepts.
        let (vm, _) = try await loadedVM([
            .ok(try Self.pageOfRawItems(
                [
                    Self.emptyFuturesJSON(id: 901),
                    Self.emptyTournamentJSON(key: "golf:empty-open"),
                    Self.futuresJSON(id: 500),
                ],
                offset: 12, hasMore: true)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(vm.items.count, 13, "both envelopes dropped, the real market kept")
        XCTAssertTrue(
            vm.items.allSatisfy { DiscoverViewModel.isRenderable($0) },
            "every card in the feed must pass the same predicate the first page uses")
    }

    @MainActor
    func testAllEnvelopePageDoesNotEndTheFeed() async throws {
        // A page that is ENTIRELY envelopes must not read as exhaustion. Only the
        // server's own `has_more` may close the feed (the L2-238 rule), so the scan
        // continues to the next page and finds the real content behind it.
        let (vm, fake) = try await loadedVM([
            .ok(try Self.pageOfRawItems(
                [
                    Self.liveConceptJSON(key: "ufc:a"),
                    Self.liveConceptJSON(key: "ufc:b"),
                ],
                offset: 12, hasMore: true, limit: 200)),
            .ok(try Self.response(ids: [500], offset: 212, hasMore: false)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(vm.items.count, 13, "the real market behind the envelope page arrives")
        XCTAssertFalse(vm.hasMore, "the server's own has_more=false ends the feed")
        XCTAssertNil(vm.error, "an all-envelope page is not an error")
        XCTAssertEqual(
            fake.requestedOffsets, [12, 212],
            "offset advances by the SERVER page width (200), never by retained count")
    }

    @MainActor
    func testEnvelopeFilterDoesNotDisturbOffsetAdvancement() async throws {
        // The filter runs AFTER `pageBoundary`, so dropping items must not shorten
        // the stride. A 200-slot page whose decoded content is all envelopes still
        // advances a full 200 (C29 P1 — never advance by decoded/retained count).
        let (vm, fake) = try await loadedVM([
            .ok(try Self.pageOfRawItems(
                [Self.liveConceptJSON(key: "ufc:only")],
                offset: 12, hasMore: true, limit: 200)),
            .ok(try Self.response(ids: [777], offset: 212, hasMore: false)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(fake.requestedOffsets, [12, 212])
        XCTAssertEqual(vm.items.count, 13)
    }

    @MainActor
    func testDuplicateEnvelopeDoesNotBurnTheScanBudget() async throws {
        // An envelope must not be counted as "fresh" and then filtered by the view,
        // which would let a repeating envelope page masquerade as forward progress.
        let (vm, _) = try await loadedVM([
            .ok(try Self.pageOfRawItems(
                [Self.liveConceptJSON(key: "ufc:repeat")],
                offset: 12, hasMore: true, limit: 200)),
            .ok(try Self.pageOfRawItems(
                [Self.liveConceptJSON(key: "ufc:repeat")],
                offset: 212, hasMore: false, limit: 200)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(vm.items.count, 12, "no envelope was ever appended")
        XCTAssertFalse(vm.hasMore, "honest exhaustion, not a spin")
        XCTAssertNil(vm.error)
    }

    /// Pins the OLD behaviour against a literal reference copy of the shipped
    /// pre-fix line, so the defect can never be reintroduced as "just a dedup".
    /// House standard for this class of bug (the `DiscoverSwipeState` technique
    /// from UX-P081, and `DiscoverInterleaveTests` before it): assert what the
    /// broken code DID, next to what the fixed code does.
    @MainActor
    func testLegacyPaginationAdmittedEveryEnvelope() async throws {
        let page = try Self.pageOfRawItems(
            [
                Self.liveConceptJSON(key: "ufc:a"),
                Self.liveConceptJSON(key: "f1:b", domain: "f1"),
                Self.emptyFuturesJSON(id: 902),
                Self.futuresJSON(id: 500),
            ],
            offset: 12, hasMore: true)

        // VERBATIM the shipped pre-fix line: dedup against loaded ids, and nothing
        // else. `renderable` was never consulted on this path.
        let alreadyLoaded = Set<String>()
        let legacyFresh = page.items.filter { item in
            !alreadyLoaded.contains(item.id)
        }
        XCTAssertEqual(
            legacyFresh.count, 4,
            "OLD behaviour: all four items admitted, three of them empty envelopes")
        XCTAssertEqual(
            legacyFresh.filter { DiscoverViewModel.isRenderable($0) }.count, 1,
            "…and only ONE of those four could actually render a probability")

        // NEW behaviour, through the real view model on the same page.
        let (vm, _) = try await loadedVM([.ok(page)])
        await vm.loadMoreIfNeeded()
        XCTAssertEqual(vm.items.count, 13, "NEW behaviour: exactly the one renderable card")
    }

    // MARK: - #5105: a retired seated edition is replaced, never scanned past

    /// A page in the seated format: `edition` + `continuation_start`, and an
    /// `edition_status` when the request was pinned.
    private static func seatedPage(
        ids: [Int], offset: Int, edition: String?, status: String? = nil,
        start: Int? = 3, limit: Int = 12, hasMore: Bool = true,
        total: Int = 9999, malformedAt: [Int] = []
    ) throws -> FeedResponse {
        // `malformedAt` are RAW slots: a row there fails to decode, so every
        // later card's raw position is one more than its decoded index.
        var rows = ids.map { futuresJSON(id: $0) }
        for slot in malformedAt.sorted() { rows.insert(#"{"garbage": true}"#, at: slot) }
        let items = rows.joined(separator: ",")
        var extra = ""
        if let edition { extra += #","edition":"\#(edition)""# }
        if let start { extra += #","continuation_start":\#(start)"# }
        if let status { extra += #","edition_status":"\#(status)""# }
        let json = """
        {"items":[\(items)],"total":\(total),"limit":\(limit),"offset":\(offset),"has_more":\(hasMore)\(extra)}
        """
        return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    /// The opening-edition option ON (`openingEditionEnabled`), page 0 with a
    /// boundary at 3 — or none, for a deck with no "Live events" continuation.
    private func seatedVM(
        _ replies: [Reply], start: Int? = 3
    ) async throws -> (DiscoverViewModel, FakeFeedClient) {
        let fake = FakeFeedClient(
            [.ok(try Self.seatedPage(ids: Array(1...12), offset: 0, edition: "ed-1", start: start))] + replies)
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)
        vm.openingEditionEnabled = true
        await vm.load()
        XCTAssertEqual(vm.acceptedSeatedEdition, "ed-1", "a seated network page is accepted")
        fake.reset()
        return (vm, fake)
    }

    @MainActor private func ids(_ vm: DiscoverViewModel) -> [Int] { vm.items.compactMap(\.futures?.id) }

    /// A pinned page continues the deck: token and the edition's own page size
    /// ride the request, and the cards append as before.
    @MainActor
    func testPinnedPageCarriesTokenAtTheEditionsPageSize5105() async throws {
        let (vm, fake) = try await seatedVM([
            .ok(try Self.seatedPage(ids: [13, 14], offset: 12, edition: "ed-1", status: "pinned")),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(fake.requestedOffsets, [12])
        XCTAssertEqual(fake.requestedEditions, ["ed-1"])
        XCTAssertEqual(fake.requestedLimits, [12],
            "the server binds an edition to its limit; 200 would read superseded every time")
        XCTAssertEqual(ids(vm), Array(1...14))
        XCTAssertFalse(vm.awaitingEditionReplacement)
    }

    /// An expired page N: nothing from it appends, the cursor does not move, no
    /// forward scan happens, and exactly ONE unpinned page 0 replaces the deck.
    @MainActor
    func testExpiredPageIsReplacedByOneUnpinnedPageZero5105() async throws {
        let (vm, fake) = try await seatedVM([
            .ok(try Self.seatedPage(ids: [900, 901], offset: 12, edition: "ed-2", status: "expired")),
            .ok(try Self.seatedPage(ids: Array(201...212), offset: 0, edition: "ed-2")),
            .ok(try Self.seatedPage(ids: [213], offset: 12, edition: "ed-2", status: "pinned")),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(fake.requestedOffsets, [12, 0], "one pinned ask, then one page 0 — no scan")
        XCTAssertEqual(fake.requestedEditions, ["ed-1", nil], "the replacement is unpinned")
        XCTAssertEqual(ids(vm), Array(201...212), "the replacement deck lands whole")
        XCTAssertFalse(ids(vm).contains(900), "the retired page never appends")
        XCTAssertEqual(vm.acceptedSeatedEdition, "ed-2")
        XCTAssertFalse(vm.awaitingEditionReplacement)

        // The cursor was reset with the deck: the next page is the NEW list's.
        fake.reset()
        await vm.loadMoreIfNeeded()
        XCTAssertEqual(fake.requestedOffsets, [12])
        XCTAssertEqual(fake.requestedEditions, ["ed-2"])
        XCTAssertEqual(ids(vm), Array(201...213))
    }

    /// The replacement is refused: the cards stay, nothing ends the feed, and
    /// Retry asks for page 0 again (one request per action), never the old offset.
    @MainActor
    func testRefusedReplacementKeepsCardsAndRetryTargetsPageZero5105() async throws {
        let (vm, fake) = try await seatedVM([
            .ok(try Self.seatedPage(ids: [900], offset: 12, edition: "ed-2", status: "superseded")),
            .ok(try Self.unavailablePage()),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(fake.requestedOffsets, [12, 0])
        XCTAssertEqual(ids(vm), Array(1...12), "a refused replacement keeps the deck")
        XCTAssertTrue(vm.awaitingEditionReplacement)
        XCTAssertTrue(vm.hasMore, "no false end state")

        fake.reset()
        fake.append([.ok(try Self.unavailablePage())])
        await vm.loadMoreIfNeeded()
        XCTAssertEqual(fake.requestedOffsets, [0], "Retry is the replacement page 0 again")
        XCTAssertEqual(fake.requestedEditions, [nil])
        XCTAssertEqual(ids(vm), Array(1...12))
        XCTAssertTrue(vm.awaitingEditionReplacement)

        fake.reset()
        fake.append([.ok(try Self.seatedPage(ids: Array(301...312), offset: 0, edition: "ed-3"))])
        await vm.loadMoreIfNeeded()
        XCTAssertEqual(fake.requestedOffsets, [0])
        XCTAssertEqual(ids(vm), Array(301...312))
        XCTAssertEqual(vm.acceptedSeatedEdition, "ed-3")
        XCTAssertFalse(vm.awaitingEditionReplacement)
    }

    /// A legacy deck with no edition is never opted in: 200-card pages, no token.
    @MainActor
    func testLegacyDeckPaginatesUnpinnedAt200_5105() async throws {
        let (vm, fake) = try await loadedVM([
            .ok(try Self.response(ids: [500], offset: 12, hasMore: true)),
        ])
        XCTAssertNil(vm.acceptedSeatedEdition)
        await vm.loadMoreIfNeeded()
        XCTAssertEqual(fake.requestedEditions, [nil])
        XCTAssertEqual(fake.requestedLimits, [200])
    }

    /// Explicitly disabling the option preserves
    /// today's Discover whatever page 0 states: an edition alone, an edition
    /// with a boundary, even a malformed boundary. Nothing pins, nothing pages
    /// at the edition's size, nothing is sectioned or refused.
    @MainActor
    func testOptionOffIsTheLegacyPathWhateverPageZeroStates5105() async throws {
        let pages: [(String, Int?)] = [("edition, no boundary", nil), ("boundary 3", 3), ("malformed", -1)]
        for (label, start) in pages {
            let fake = FakeFeedClient([
                .ok(try Self.seatedPage(ids: Array(1...12), offset: 0, edition: "ed-1", start: start)),
                .ok(try Self.seatedPage(ids: [13], offset: 12, edition: "ed-1", start: start)),
            ])
            let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)
            vm.openingEditionEnabled = false
            XCTAssertFalse(vm.openingEditionEnabled, label)
            await vm.load()
            XCTAssertEqual(ids(vm), Array(1...12), "\(label): painted, never refused")
            XCTAssertNil(vm.acceptedSeatedEdition, label)
            XCTAssertNil(section(vm, 1), "\(label): no section record")

            fake.reset()
            await vm.loadMoreIfNeeded()
            XCTAssertEqual(fake.requestedEditions, [nil], label)
            XCTAssertEqual(fake.requestedLimits, [200], label)
            XCTAssertEqual(ids(vm), Array(1...13), label)
        }
    }

    /// The option ON over a page 0 with no edition (an older backend, a token
    /// the server could not mint): there is nothing to pin, so it is the legacy
    /// path — not a seated deck and not a refusal.
    @MainActor
    func testOptionOnWithoutAnEditionStaysLegacy5105() async throws {
        let fake = FakeFeedClient([
            .ok(try Self.seatedPage(ids: Array(1...12), offset: 0, edition: nil, start: nil)),
            .ok(try Self.response(ids: [13], offset: 12, hasMore: true)),
        ])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)
        vm.openingEditionEnabled = true
        await vm.load()
        XCTAssertEqual(ids(vm), Array(1...12))
        XCTAssertNil(vm.acceptedSeatedEdition)

        fake.reset()
        await vm.loadMoreIfNeeded()
        XCTAssertEqual(fake.requestedEditions, [nil])
        XCTAssertEqual(fake.requestedLimits, [200])
    }

    // MARK: - #5105: an edition with no continuation is still one seated edition

    /// THE GAP (Root on 02e9eae59f): `continuation_start` absent beside an
    /// edition read as legacy, so the next page went out unpinned at 200. Heading
    /// presence is not participation: the edition is accepted, its next page is
    /// pinned at its own size, and every card is opening — no heading drawn.
    @MainActor
    func testNoHeadingEditionIsPinnedAtItsOwnPageSize5105() async throws {
        let (vm, fake) = try await seatedVM([
            .ok(try Self.seatedPage(ids: [13, 14], offset: 12, edition: "ed-1", status: "pinned", start: nil)),
        ], start: nil)
        XCTAssertEqual(section(vm, 1), .opening)
        XCTAssertEqual(section(vm, 12), .opening)

        await vm.loadMoreIfNeeded()
        XCTAssertEqual(fake.requestedOffsets, [12])
        XCTAssertEqual(fake.requestedEditions, ["ed-1"])
        XCTAssertEqual(fake.requestedLimits, [12])
        XCTAssertEqual(ids(vm), Array(1...14))
        XCTAssertEqual(section(vm, 14), .opening)
        XCTAssertFalse(vm.awaitingEditionReplacement)
        let split = DiscoverView.partitionBySection(vm.items, section: vm.seatedSection(of:))
        XCTAssertEqual(split?.continuation.count, 0, "no continuation card, so no heading")
    }

    /// A no-heading edition retires like any other: the expired page never
    /// appends, the cursor does not move, and exactly one unpinned page 0
    /// replaces the deck.
    @MainActor
    func testNoHeadingEditionRetiredIsReplacedByOneUnpinnedPageZero5105() async throws {
        let (vm, fake) = try await seatedVM([
            .ok(try Self.seatedPage(ids: [900], offset: 12, edition: "ed-2", status: "expired", start: nil)),
            .ok(try Self.seatedPage(ids: Array(201...212), offset: 0, edition: "ed-2", start: nil)),
        ], start: nil)
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(fake.requestedOffsets, [12, 0])
        XCTAssertEqual(fake.requestedEditions, ["ed-1", nil])
        XCTAssertEqual(ids(vm), Array(201...212))
        XCTAssertEqual(vm.acceptedSeatedEdition, "ed-2")
        XCTAssertFalse(vm.awaitingEditionReplacement)
    }

    /// A boundary appearing or vanishing mid-edition is another deck in both
    /// directions: the page is refused and replaced, never appended.
    @MainActor
    func testBoundaryAppearingOrVanishingMidEditionIsReplaced5105() async throws {
        for (accepted, stated) in [(nil, 3), (3, nil)] as [(Int?, Int?)] {
            let (vm, fake) = try await seatedVM([
                .ok(try Self.seatedPage(ids: [13, 14], offset: 12, edition: "ed-1", status: "pinned", start: stated)),
                .ok(try Self.seatedPage(ids: Array(201...212), offset: 0, edition: "ed-2", start: nil)),
            ], start: accepted)
            await vm.loadMoreIfNeeded()
            let label = "accepted \(String(describing: accepted)), page \(String(describing: stated))"
            XCTAssertEqual(fake.requestedOffsets, [12, 0], label)
            XCTAssertEqual(fake.requestedEditions, ["ed-1", nil], label)
            XCTAssertFalse(ids(vm).contains(13), label)
            XCTAssertEqual(vm.acceptedSeatedEdition, "ed-2", label)
        }
    }

    // MARK: - #5105: a bundle is sectioned by its OWN served slot

    /// The grouping bug: a bundle's lead is one of its children, which the
    /// server never placed, so a boundary read back from a grouped card put the
    /// heading in the wrong place. The record holds the bundle itself, and the
    /// partition the presentation splits on keeps it in its served section.
    @MainActor
    func testBundleServedInTheContinuationIsSectionedByItsOwnSlot5105() async throws {
        let bundle = """
        {"type":"bundle","score":95,"data":{"id":"b-5105","title":"Tonight","kind":"comparison",
          "items":[\(Self.futuresJSON(id: 50)),\(Self.futuresJSON(id: 51))]}}
        """
        let rows = [Self.futuresJSON(id: 1), Self.futuresJSON(id: 2), bundle,
                    Self.futuresJSON(id: 3), Self.futuresJSON(id: 4)].joined(separator: ",")
        let json = """
        {"items":[\(rows)],"total":9999,"limit":5,"offset":0,"has_more":true,"edition":"ed-b","continuation_start":2}
        """
        let page = try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
        let vm = DiscoverViewModel(client: FakeFeedClient([.ok(page)]), lastGood: nil, telemetry: nil)
        vm.openingEditionEnabled = true
        await vm.load()

        let served = try XCTUnwrap(vm.items.first { $0.bundle?.id == "b-5105" }, "the bundle is painted")
        XCTAssertEqual(vm.seatedSection(of: served), .continuation, "raw slot 2 IS the boundary")
        let child = try XCTUnwrap(served.bundle?.items.first)
        XCTAssertNil(vm.seatedSection(of: child), "a child was never served, so it cannot place the bundle")

        let split = try XCTUnwrap(DiscoverView.partitionBySection(vm.items, section: vm.seatedSection(of:)))
        XCTAssertEqual(split.opening.compactMap(\.futures?.id).sorted(), [1, 2])
        XCTAssertTrue(split.continuation.contains { $0.bundle?.id == "b-5105" })
        XCTAssertEqual(split.continuation.compactMap(\.futures?.id).sorted(), [3, 4])
    }

    // MARK: - #5105: the real server transcript, through the caller

    /// The web/server gate's generated transcript (`get_feed` with the served
    /// switch ON, fixed request clocks) — shared, not copied, so both clients are
    /// graded on one file: `frontend/__tests__/fixtures/discover5105ServerTranscript.json`
    /// (generator `backend/tests/integration/test_discover_web_transcript_5105.py`).
    private static var transcriptURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .deletingLastPathComponent()      // ios
            .deletingLastPathComponent()      // repo root
            .appendingPathComponent("frontend/__tests__/fixtures/discover5105ServerTranscript.json")
    }

    private struct TranscriptStep {
        let label: String
        let offset: Int
        let limit: Int
        let edition: String?
        let response: FeedResponse
    }

    /// One scenario. Every envelope field (offset, limit, total, has_more,
    /// edition, edition_status, continuation_start, cache) is the server's,
    /// verbatim. The synthetic cards are too sparse to decode as native cards, so
    /// each futures/event card becomes a decodable futures card with the SAME
    /// identity (futures N → N, event N → 100_000 + N); any other row (the
    /// tournament card) stays raw, slot for slot.
    private static func transcript(_ scenario: String) throws -> [TranscriptStep] {
        let root = try JSONSerialization.jsonObject(with: Data(contentsOf: transcriptURL)) as! [String: Any]
        let steps = (root["scenarios"] as! [String: Any])[scenario] as! [[String: Any]]
        return try steps.map { step in
            var body = try JSONSerialization.jsonObject(
                with: Data((step["body"] as! String).utf8)) as! [String: Any]
            body["items"] = try (body["items"] as! [[String: Any]]).map { row -> Any in
                let id = (row["data"] as? [String: Any])?["id"] as? Int
                switch (row["type"] as? String, id) {
                case ("futures", let id?): return try JSONSerialization.jsonObject(with: Data(futuresJSON(id: id).utf8))
                case ("event", let id?): return try JSONSerialization.jsonObject(with: Data(futuresJSON(id: 100_000 + id).utf8))
                default: return row
                }
            }
            let url = URLComponents(string: (step["request"] as! [String: Any])["url"] as! String)!
            let query = { (name: String) in url.queryItems?.first { $0.name == name }?.value }
            return TranscriptStep(
                label: step["label"] as! String,
                offset: Int(query("offset") ?? "0")!,
                limit: Int(query("limit")!)!,
                edition: query("edition"),
                response: try decoder().decode(
                    FeedResponse.self, from: JSONSerialization.data(withJSONObject: body)))
        }
    }

    /// The caller asked for exactly what the web client asked the server for.
    private func assertRequests(
        _ fake: FakeFeedClient, _ steps: [TranscriptStep],
        file: StaticString = #filePath, line: UInt = #line
    ) {
        XCTAssertEqual(fake.requestedOffsets, steps.map(\.offset), "offsets", file: file, line: line)
        XCTAssertEqual(fake.requestedEditions, steps.map(\.edition), "editions", file: file, line: line)
        XCTAssertEqual(fake.requestedLimits, steps.map(\.limit), "limits", file: file, line: line)
    }

    private func transcriptVM(_ steps: [TranscriptStep], enabled: Bool? = nil) -> (DiscoverViewModel, FakeFeedClient) {
        let fake = FakeFeedClient(steps.map { .ok($0.response) })
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)
        if let enabled { vm.openingEditionEnabled = enabled }
        return (vm, fake)
    }

    /// `full_opening_back`: a full opening, no `continuation_start` on any page.
    /// Page 1 goes out pinned at the edition's size, exactly as the server's
    /// transcript asked. (`back-revalidate-page0` is the web's Back restore,
    /// which the phone has no twin of.)
    @MainActor
    func testTranscriptFullOpeningNoHeadingPinsPageOne5105() async throws {
        XCTAssertTrue(DiscoverOpeningEditionOption.enabled, "the enabled candidate must exercise the shipping default")
        let steps = try Self.transcript("full_opening_back").filter { $0.label != "back-revalidate-page0" }
        XCTAssertEqual(steps.map(\.label), ["page0", "page1"])
        let (vm, fake) = transcriptVM(steps)
        await vm.load()
        XCTAssertEqual(vm.acceptedSeatedEdition, "676a36a9753e4b02")
        await vm.loadMoreIfNeeded()

        assertRequests(fake, steps)
        XCTAssertEqual(Set(ids(vm)), Set(0...39))
        XCTAssertEqual(vm.items.count, 40)
        XCTAssertFalse(vm.hasMore)
        XCTAssertTrue(vm.items.allSatisfy { vm.seatedSection(of: $0) == .opening }, "no heading")
    }

    /// The legacy control on the same transcript: option OFF, page 1 goes out
    /// unpinned at 200 — today's request, and the one the gap sent with it ON.
    @MainActor
    func testTranscriptFullOpeningWithOptionOffIsTodaysRequest5105() async throws {
        let steps = try Self.transcript("full_opening_back").filter { $0.label != "back-revalidate-page0" }
        let (vm, fake) = transcriptVM(steps, enabled: false)
        await vm.load()
        await vm.loadMoreIfNeeded()

        XCTAssertNil(vm.acceptedSeatedEdition)
        XCTAssertEqual(fake.requestedOffsets, [0, 20])
        XCTAssertEqual(fake.requestedEditions, [nil, nil])
        XCTAssertEqual(fake.requestedLimits, [20, 200])
    }

    /// `tournament_start`: a no-heading edition expires when the tournament
    /// starts. The retired page 1 never appends; one unpinned page 0 brings the
    /// new edition; its pages 1 and 2 go out pinned to IT — all five requests
    /// the server's transcript holds, in order.
    @MainActor
    func testTranscriptTournamentStartReplacesTheNoHeadingEdition5105() async throws {
        let steps = try Self.transcript("tournament_start")
        XCTAssertEqual(steps.map(\.label),
                       ["page0", "retired-page1", "replacement-page0", "page1", "lookahead-page2"])
        let (vm, fake) = transcriptVM(steps)
        await vm.load()
        XCTAssertEqual(vm.acceptedSeatedEdition, "d31e2f0e879afa1c")

        await vm.loadMoreIfNeeded()
        XCTAssertEqual(vm.acceptedSeatedEdition, "c3fbea5ff011f662", "the replacement edition")
        XCTAssertFalse(vm.awaitingEditionReplacement)
        XCTAssertTrue(ids(vm).contains(500), "the replacement deck landed")
        XCTAssertEqual(Set(ids(vm)), Set(steps[2].response.items.compactMap(\.futures?.id)),
                       "nothing from the retired page appended")

        await vm.loadMoreIfNeeded()
        await vm.loadMoreIfNeeded()
        assertRequests(fake, steps)
        XCTAssertFalse(vm.hasMore)
        let served = steps[2...].flatMap { $0.response.items.compactMap(\.futures?.id) }
        XCTAssertEqual(Set(ids(vm)), Set(served))
        XCTAssertTrue(vm.items.allSatisfy { vm.seatedSection(of: $0) == .opening }, "no heading")
    }

    /// `unavailable_replacement`: the replacement page 0 is refused, so the
    /// retired edition's cards stay and the pager waits on page 0. The phone's
    /// Retry is an UNPINNED page 0 (the web's retry carries the old token and
    /// reads `expired`), so it is answered with the server's reply to exactly
    /// that request — `tournament_start`'s `replacement-page0`.
    @MainActor
    func testTranscriptUnavailableReplacementKeepsTheDeckThenRetries5105() async throws {
        let steps = Array(try Self.transcript("unavailable_replacement").prefix(3))
        XCTAssertEqual(steps.map(\.label), ["page0", "retired-page1", "unavailable-page0"])
        let replacement = try XCTUnwrap(
            try Self.transcript("tournament_start").first { $0.label == "replacement-page0" })
        let (vm, fake) = transcriptVM(steps)
        await vm.load()
        let painted = ids(vm)
        await vm.loadMoreIfNeeded()

        assertRequests(fake, steps)
        XCTAssertEqual(ids(vm), painted, "a refused replacement keeps the deck")
        XCTAssertTrue(vm.awaitingEditionReplacement)
        XCTAssertTrue(vm.hasMore, "no false end state")

        fake.reset()
        fake.append([.ok(replacement.response)])
        await vm.loadMoreIfNeeded()
        assertRequests(fake, [replacement])
        XCTAssertEqual(vm.acceptedSeatedEdition, "c3fbea5ff011f662")
        XCTAssertFalse(vm.awaitingEditionReplacement)
    }

    // MARK: - #5105: the served section survives decode, filters and merges

    @MainActor private func section(_ vm: DiscoverViewModel, _ id: Int) -> FeedSection? {
        vm.items.first { $0.futures?.id == id }.flatMap(vm.seatedSection(of:))
    }

    /// The opening cards come first in the published deck, whatever the spacing
    /// pass does inside each section.
    @MainActor private func assertSectionsContiguous(
        _ vm: DiscoverViewModel, file: StaticString = #filePath, line: UInt = #line
    ) {
        let sections = vm.items.map { vm.seatedSection(of: $0) }
        let firstContinuation = sections.firstIndex(of: .continuation) ?? sections.count
        XCTAssertFalse(sections[firstContinuation...].contains(.opening),
            "an opening card was published after the continuation began", file: file, line: line)
        XCTAssertFalse(sections.contains(nil), "every published card has a served section", file: file, line: line)
    }

    /// E=3 with raw slot 1 malformed: the two SURVIVING opening cards are the
    /// opening; the card at raw slot 3 is continuation, never pulled up by the
    /// compaction.
    @MainActor
    func testPageZeroSectionsAreReadFromRawPositions5105() async throws {
        let fake = FakeFeedClient([.ok(try Self.seatedPage(
            ids: [1, 3, 4, 5, 6], offset: 0, edition: "ed-1", malformedAt: [1]))])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)
        vm.openingEditionEnabled = true
        await vm.load()

        XCTAssertEqual(vm.acceptedSeatedEdition, "ed-1")
        XCTAssertEqual(section(vm, 1), .opening)
        XCTAssertEqual(section(vm, 3), .opening, "raw slot 2 is before the boundary")
        XCTAssertEqual(section(vm, 4), .continuation, "raw slot 3 IS the boundary")
        XCTAssertEqual(section(vm, 6), .continuation)
        assertSectionsContiguous(vm)
    }

    /// A pinned page's sections are read against ITS offset, and a card the
    /// edition already placed keeps its first section.
    @MainActor
    func testPinnedPageSectionsReadAgainstItsOffsetFirstSightWins5105() async throws {
        let (vm, _) = try await seatedVM([
            .ok(try Self.seatedPage(ids: [13, 2, 14], offset: 12, edition: "ed-1", status: "pinned")),
        ])
        XCTAssertEqual(section(vm, 2), .opening)
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(ids(vm), Array(1...14), "the duplicate is not appended twice")
        XCTAssertEqual(section(vm, 2), .opening, "first sight wins: raw slot 13 does not re-section it")
        XCTAssertEqual(section(vm, 13), .continuation)
        XCTAssertEqual(section(vm, 14), .continuation)
        assertSectionsContiguous(vm)
    }

    /// A pinned page that restates a DIFFERENT boundary is not the same deck:
    /// it is refused like a retired page (one unpinned page 0), never appended.
    @MainActor
    func testPinnedPageWithAnotherBoundaryIsReplacedNotAppended5105() async throws {
        let (vm, fake) = try await seatedVM([
            .ok(try Self.seatedPage(ids: [13, 14], offset: 12, edition: "ed-1", status: "pinned", start: 5)),
            .ok(try Self.seatedPage(ids: Array(201...212), offset: 0, edition: "ed-2", start: 0)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(fake.requestedOffsets, [12, 0])
        XCTAssertEqual(fake.requestedEditions, ["ed-1", nil])
        XCTAssertFalse(ids(vm).contains(13), "a page from another boundary never appends")
        XCTAssertEqual(ids(vm), Array(201...212))
        XCTAssertEqual(section(vm, 201), .continuation, "the replacement's own record: E=0, all continuation")
    }

    /// A page 0 whose boundary cannot be backed — malformed, out of range, or
    /// with no edition to bind it — is refused, never flattened into the legacy
    /// single list: a cold screen gets the honest error, a painted deck stays.
    @MainActor
    func testPageZeroWithUnusableBoundaryIsRefusedNotFlattened5105() async throws {
        let unusable: [(String, FeedResponse)] = [
            ("negative", try Self.seatedPage(ids: [1, 2], offset: 0, edition: "ed-x", start: -1)),
            ("at total", try Self.seatedPage(ids: [1, 2], offset: 0, edition: "ed-x", start: 2, total: 2)),
            ("no edition", try Self.seatedPage(ids: [1, 2], offset: 0, edition: nil, start: 1)),
        ]
        for (label, page) in unusable {
            let cold = DiscoverViewModel(
                client: FakeFeedClient([.ok(page)]), lastGood: nil, telemetry: nil,
                autoRecoveryDelays: [])
            cold.openingEditionEnabled = true
            await cold.load()
            XCTAssertTrue(cold.items.isEmpty, "cold, \(label): nothing painted")
            XCTAssertEqual(cold.error, "Couldn't load feed", "cold, \(label)")
            XCTAssertNil(cold.acceptedSeatedEdition, "cold, \(label)")

            let (warm, fake) = try await seatedVM([.ok(page)])
            await warm.load()
            XCTAssertEqual(fake.requestedOffsets, [0])
            XCTAssertEqual(ids(warm), Array(1...12), "painted, \(label): the deck stays")
            XCTAssertTrue(warm.refreshFailedShowingCache, "painted, \(label)")
            XCTAssertEqual(warm.acceptedSeatedEdition, "ed-1", "painted, \(label): still the accepted deck")
            XCTAssertEqual(section(warm, 4), .continuation, "painted, \(label): its record stays too")
        }
    }

    /// The record belongs to the edition: an account change clears it with the
    /// deck, so the same card can land in another section of the next edition.
    @MainActor
    func testIdentityRebindClearsTheSectionRecord5105() async throws {
        let (vm, fake) = try await seatedVM([])
        XCTAssertEqual(section(vm, 2), .opening)
        fake.append([.ok(try Self.seatedPage(ids: Array(1...12), offset: 0, edition: "ed-9", start: 0))])
        await vm.rebindForIdentityChange()

        XCTAssertEqual(vm.acceptedSeatedEdition, "ed-9")
        XCTAssertEqual(section(vm, 2), .continuation, "the new edition's record, not the old one's")
    }

    private static func unavailablePage() throws -> FeedResponse {
        let json = #"{"items":[],"total":0,"limit":12,"offset":0,"has_more":false,"cache":{"status":"unavailable"}}"#
        return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }
}
