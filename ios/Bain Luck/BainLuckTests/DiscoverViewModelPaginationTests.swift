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

        init(_ script: [Reply]) { self.script = script }

        var requestedOffsets: [Int] { lock.withLock { offsets } }

        func reset() { lock.withLock { offsets.removeAll() } }

        nonisolated func fetchDiscoverFeed(
            limit: Int,
            offset: Int,
            eventPct: Double?,
            cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            // Yield first so a concurrent second call observes loadingMore=true
            // before this one records its request.
            await Task.yield()
            return try lock.withLock {
                offsets.append(offset)
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
        async let a: Void = vm.loadMoreIfNeeded()
        async let b: Void = vm.loadMoreIfNeeded()
        _ = await (a, b)

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
}
