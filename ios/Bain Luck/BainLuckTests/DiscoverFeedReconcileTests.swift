import XCTest
@testable import Bain_Luck

/// native/078, #4110 — a card the reader is looking at stops moving under them.
///
/// Alex, reading Discover in the app Tue 2026-09-08 3:30–3:42pm PT: *"the feed
/// re-rendered several times during load and a card he was reading disappeared."*
///
/// `DiscoverViewModel` had three writers that each assigned the WHOLE `items`
/// array through `FeedInterleave.byCategory`. The interleave is deterministic for
/// a given input, but the boot cache and the fresh network response are DIFFERENT
/// inputs, so they interleave to different orders — the boot paint was not a
/// prefix of the fresh paint. No race required; it is what a normal successful
/// load did.
///
/// These tests are the contract, not the plumbing. The four branches are pure
/// functions precisely so they can be stated as claims about behaviour rather
/// than as assertions about a view model's internals.
final class DiscoverFeedReconcileTests: XCTestCase {

    // MARK: - The four branches (discover/001's contract)

    /// Nothing painted ⇒ nothing to protect. Without this branch the common cold
    /// no-cache load would append every card in raw server order and lose the
    /// category interleave entirely — a regression dressed as a fix.
    func testAnEmptyListTakesTheFullInterleave() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 0, paintedEdition: nil, incomingEdition: "abc"),
            .repaint)
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 0, paintedEdition: "abc", incomingEdition: "abc"),
            .repaint)
    }

    /// THE SHIP. Same edition ⇒ same cards in the same order ⇒ the reader's card
    /// keeps its slot. This is the branch that was missing.
    func testTheSameEditionMayNotReorderThePaintedList() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20, paintedEdition: "9f2c1ab740de55c3",
                incomingEdition: "9f2c1ab740de55c3"),
            .reconcile)
    }

    func testADifferentEditionMayRepaint() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20, paintedEdition: "9f2c1ab740de55c3",
                incomingEdition: "5c7ef69d20eff005"),
            .repaint)
    }

    /// Absent is a REAL branch, not a legacy shim: it covers an older backend and
    /// every empty refusal (`requires_auth`, `leader_unavailable`,
    /// `input_age_ceiling`), for which discover deliberately returns no token
    /// rather than a shared "empty edition" constant — so that three different
    /// failures are not reconciled as one agreed ordering.
    func testAnAbsentIncomingEditionReconcilesRatherThanReordering() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20, paintedEdition: "9f2c1ab740de55c3",
                incomingEdition: nil),
            .reconcile)
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20, paintedEdition: nil, incomingEdition: nil),
            .reconcile)
    }

    /// We painted a list whose ordering we cannot vouch for (a pre-`edition`
    /// cached body), and the server has now stated one. Defer to the one we can
    /// verify rather than pretending the two agree.
    func testAPaintedListWithNoEditionDefersToAServerThatHasOne() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20, paintedEdition: nil, incomingEdition: "abc"),
            .repaint)
    }

    // MARK: - The merge itself

    private func keys(_ items: [String]) -> [String] { items }

    func testAPaintedCardKeepsItsSlotAndTakesTheFreshContent() {
        // Same membership, server order totally different — which is exactly what
        // the interleave of a different input produces, and exactly what used to
        // be assigned over the top.
        let painted = ["a", "b", "c", "d"]
        let incoming = ["d", "c", "b", "a"]
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(painted: painted, incoming: incoming, key: { $0 }),
            painted,
            "same cards ⇒ the reader's order survives, whatever order the server sent")
    }

    /// The incoming copy WINS on content and LOSES on position: a card keeps its
    /// slot but takes the fresh prices the 2-minute poll moved.
    func testTheIncomingCopyWinsOnContentAndLosesOnPosition() {
        struct Card: Equatable { let key: String; let price: Int }
        let painted = [Card(key: "a", price: 1), Card(key: "b", price: 1)]
        let incoming = [Card(key: "b", price: 99), Card(key: "a", price: 99)]
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(painted: painted, incoming: incoming, key: \.key),
            [Card(key: "a", price: 99), Card(key: "b", price: 99)])
    }

    func testNewCardsArriveAtTheEndInTheServersOwnOrder() {
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(
                painted: ["a", "b"], incoming: ["x", "b", "y", "a", "z"], key: { $0 }),
            ["a", "b", "x", "y", "z"])
    }

    func testACardTheServerNoLongerSendsIsRemoved() {
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(
                painted: ["a", "b", "c"], incoming: ["a", "c"], key: { $0 }),
            ["a", "c"])
    }

    /// The property that matters to a reader, stated directly: for any painted
    /// list and any permutation of it, no surviving card changes its index.
    func testNoSurvivingCardEverChangesIndex() {
        let painted = (0..<40).map { "card-\($0)" }
        // A permutation with a third of the list dropped and five cards added.
        var incoming = painted.filter { !$0.hasSuffix("3") && !$0.hasSuffix("7") }.shuffled()
        incoming += ["new-1", "new-2", "new-3", "new-4", "new-5"]

        let merged = DiscoverFeedReconcile.merge(
            painted: painted, incoming: incoming, key: { $0 })
        let survivors = painted.filter(Set(incoming).contains)

        XCTAssertEqual(Array(merged.prefix(survivors.count)), survivors,
                       "survivors must appear in painted order, before anything new")
        XCTAssertEqual(Set(merged), Set(incoming), "membership is the server's")
        XCTAssertEqual(merged.count, Set(merged).count, "no duplicates")
    }

    func testMergingIntoAnEmptyPaintedListIsJustTheIncomingList() {
        // Guarded at the decision layer, but the merge must still be sane if it
        // is ever reached — a silent reorder here would be invisible.
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(painted: [], incoming: ["a", "b"], key: { $0 }),
            ["a", "b"])
    }

    func testAnEmptyIncomingListRemovesEverything() {
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(painted: ["a", "b"], incoming: [], key: { $0 }),
            [])
    }

    // MARK: - Decoding

    /// The token rides the response BODY, not a header, because it has to be
    /// readable out of the client's last-good body cache at boot — which is one
    /// of the three assignment sites this ship changes.
    func testTheEditionDecodesOffTheBody() throws {
        let body = """
        {"items": [], "total": 0, "limit": 50, "offset": 0, "has_more": false,
         "edition": "5c7ef69d20eff005"}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(FeedResponse.self, from: Data(body.utf8))
        XCTAssertEqual(response.edition, "5c7ef69d20eff005")
    }

    /// An older backend, and every empty refusal, carry no token at all. That has
    /// to decode to nil rather than throw — the absent branch is reached through
    /// this line.
    func testAPayloadWithNoEditionDecodesToNilRatherThanThrowing() throws {
        let body = """
        {"items": [], "total": 0, "limit": 50, "offset": 0, "has_more": false}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(FeedResponse.self, from: Data(body.utf8))
        XCTAssertNil(response.edition)
    }

    /// Tolerant like `cache`/`buildQuality`/`degradedReason` beside it: a
    /// malformed token degrades to ABSENT, never to a decode failure that would
    /// take the whole feed down over a string.
    func testAMalformedEditionDegradesToAbsentAndDoesNotKillTheFeed() throws {
        let body = """
        {"items": [], "total": 0, "limit": 50, "offset": 0, "has_more": false,
         "edition": {"not": "a string"}}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(FeedResponse.self, from: Data(body.utf8))
        XCTAssertNil(response.edition)
        XCTAssertEqual(response.limit, 50, "the rest of the payload still decoded")
    }

    // MARK: - #11984: Discover feed holds still until pull-to-refresh

    /// Ruling A: when a deck is already painted and the load is not a pull
    /// (`mayReorder == false`), a different incoming edition still reconciles in
    /// place rather than repainting.
    func testDifferentEditionReconcilesWhenReorderIsDisallowed11984() {
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20,
                mayReorder: false,
                paintedEdition: "9f2c1ab740de55c3",
                incomingEdition: "5c7ef69d20eff005"),
            .reconcile)
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 20,
                mayReorder: false,
                paintedEdition: nil,
                incomingEdition: "5c7ef69d20eff005"),
            .reconcile)
        XCTAssertEqual(
            DiscoverFeedReconcile.decision(
                paintedCount: 0,
                mayReorder: false,
                paintedEdition: nil,
                incomingEdition: "5c7ef69d20eff005"),
            .repaint,
            "an empty screen still paints the initial deck")
    }

    /// Ruling C (merge half): when `preservePainted` is true, painted cards that
    /// the server omitted (e.g. a card that settled since the deck was painted)
    /// stay in their exact painted slots until a pull-to-refresh.
    func testMergeWithPreservePaintedKeepsOmittedCardsInTheirPaintedSlots11984() {
        XCTAssertEqual(
            DiscoverFeedReconcile.merge(
                painted: ["a", "b", "c"],
                incoming: ["c", "a", "d"],
                preservePainted: true,
                key: { $0 }),
            ["a", "b", "c", "d"])
    }

    /// Ruling A (view-model half): a non-pull load over a published network feed
    /// keeps the painted order and retains omitted cards, while a pull-to-refresh
    /// (`mayReorder: true`) applies the newer edition's order.
    @MainActor
    func testNonPullLoadOnViewModelHoldsPaintedOrderUntilPull11984() async throws {
        nonisolated final class ScriptedClient: DiscoverFeedProviding, @unchecked Sendable {
            private let lock = NSLock()
            private var pages: [FeedResponse]
            init(_ pages: [FeedResponse]) { self.pages = pages }
            nonisolated func fetchDiscoverFeed(
                limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
            ) async throws -> FeedResponse {
                lock.withLock { pages.removeFirst() }
            }
        }
        func makePage(ids: [Int], edition: String) throws -> FeedResponse {
            let items = ids.map { id in
                """
                {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1}],"outcome_count":1}}
                """
            }.joined(separator: ",")
            let json = """
            {"items":[\(items)],"total":\(ids.count),"limit":20,"offset":0,"has_more":false,"edition":"\(edition)"}
            """
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(FeedResponse.self, from: Data(json.utf8))
        }

        let client = ScriptedClient([
            try makePage(ids: [1, 2, 3, 4], edition: "ed-1"),
            try makePage(ids: [4, 2, 5], edition: "ed-2"),
            try makePage(ids: [4, 2, 5], edition: "ed-2"),
        ])
        let vm = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil)
        vm.openingEditionEnabled = false

        await vm.load()
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), [1, 2, 3, 4])

        // Non-pull update: order of [1, 2, 3, 4] holds still, omitted cards 1 & 3 stay, 5 appends.
        await vm.load(mayReorder: false)
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), [1, 2, 3, 4, 5])

        // Pull-to-refresh (`mayReorder: true`): the new edition's order and membership apply.
        await vm.load(mayReorder: true)
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), [4, 2, 5])
    }

    /// Ruling A (view personalization half): recording mid-session card
    /// interactions (open, like, share, expand) into the live profile while
    /// `orderingProfile` stays frozen at the last pull leaves the 5-card windows
    /// untouched until a pull-to-refresh snapshots the updated profile.
    func testMidSessionInteractionsDoNotReorderWindowsUntilPullSnapshot11984() {
        struct StubCard: Equatable {
            let id: Int
            let score: Int
            let category: String
        }
        let deck = [
            StubCard(id: 1, score: 95, category: "politics"),
            StubCard(id: 2, score: 94, category: "economics"),
            StubCard(id: 3, score: 93, category: "tech"),
            // First 5-card window after the 3 pinned leads:
            StubCard(id: 4, score: 80, category: "politics"),
            StubCard(id: 5, score: 79, category: "tech"),
            StubCard(id: 6, score: 78, category: "economics"),
            StubCard(id: 7, score: 77, category: "culture"),
            StubCard(id: 8, score: 76, category: "weather"),
        ]

        let orderingProfile = DiscoverInteractionProfile.forTesting(scores: [:], recordedAt: Date())
        var liveProfile = orderingProfile

        let initialOrder = DiscoverView.rankFiveCardWindows(
            deck, profile: orderingProfile, score: \.score, category: \.category
        ).map(\.id)
        XCTAssertEqual(initialOrder, [1, 2, 3, 4, 5, 6, 7, 8])

        // Reader taps/likes/shares "weather" cards mid-session; liveProfile updates,
        // but orderingProfile stays frozen until pull-to-refresh.
        for _ in 0..<5 {
            liveProfile.record(category: "weather", action: .like, onSportsCard: false)
            liveProfile.record(category: "weather", action: .detailOpen, onSportsCard: false)
        }
        let midSessionOrder = DiscoverView.rankFiveCardWindows(
            deck, profile: orderingProfile, score: \.score, category: \.category
        ).map(\.id)
        XCTAssertEqual(midSessionOrder, initialOrder, "mid-session interactions must not reshuffle the window under the reader")

        // On pull-to-refresh, orderingProfile snapshots liveProfile and the boosted card moves up.
        let afterPullOrder = DiscoverView.rankFiveCardWindows(
            deck, profile: liveProfile, score: \.score, category: \.category
        ).map(\.id)
        XCTAssertEqual(afterPullOrder.firstIndex(of: 8), 3, "after pull-to-refresh, boosted card 8 leads the window")
    }

    /// Ruling C (view staleness half): a card admitted when the deck was painted
    /// that settles mid-session stays in place with its settled result until a
    /// pull-to-refresh clears `retainingIds`.
    func testAdmittedCardThatSettlesMidSessionStaysInPlaceWithResultUntilPull11984() throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-06T20:00:00Z")!
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        func decodeItem(_ json: String) throws -> FeedItem {
            try decoder.decode(FeedItem.self, from: Data(json.utf8))
        }

        let liveEvent = try decodeItem("""
        {"type":"event","score":90,"data":{"id":100,"sport":"basketball_nba","home_team":"Celtics","away_team":"Lakers","status":"live","commence_time":"2026-11-06T10:00:00Z","home_score":98,"away_score":97}}
        """)
        let openMarket = try decodeItem("""
        {"type":"futures","score":88,"data":{"id":200,"name":"Will rate cut happen?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":2000,"name":"Yes","probability":0.62,"rank":1}],"outcome_count":1}}
        """)

        let initialEligible = DiscoverView.eligibleItems([liveEvent, openMarket], now: now)
        let admittedIds = DiscoverView.admittedItemIds(in: initialEligible)
        XCTAssertEqual(admittedIds, ["event-100", "futures-200"])

        // Mid-session: the game finishes (>8h after kickoff, with FINAL score 104-99)
        // and the futures market resolves.
        let settledEvent = try decodeItem("""
        {"type":"event","score":90,"data":{"id":100,"sport":"basketball_nba","home_team":"Celtics","away_team":"Lakers","status":"completed","commence_time":"2026-11-06T10:00:00Z","ended_at":"2026-11-06T11:30:00Z","home_score":104,"away_score":99}}
        """)
        let settledMarket = try decodeItem("""
        {"type":"futures","score":88,"data":{"id":200,"name":"Will rate cut happen?","llm_sport_category":"economics","source":"kalshi","status":"resolved","winner":"Yes","top_outcomes":[{"id":2000,"name":"Yes","probability":1.0,"rank":1}],"outcome_count":1}}
        """)

        // Without retainingIds (i.e. on a fresh pull), both are stale and dropped.
        XCTAssertTrue(DiscoverView.isStaleItem(settledEvent, now: now))
        XCTAssertTrue(DiscoverView.isStaleItem(settledMarket, now: now))

        // Before a pull (with `retainingIds: admittedIds`), both stay in place in their exact order with their settled results!
        let keptDuringSession = DiscoverView.eligibleItems(
            [settledEvent, settledMarket], now: now, retainingIds: admittedIds
        )
        XCTAssertEqual(keptDuringSession.map(DiscoverView.feedItemId), ["event-100", "futures-200"])
        XCTAssertEqual(keptDuringSession[0].event?.status, "completed")
        XCTAssertEqual(keptDuringSession[0].event?.homeScore, 104)
        XCTAssertEqual(keptDuringSession[1].futures?.status, "resolved")

        // On pull-to-refresh (`retainingIds` reset to `[]`), settled cards leave the feed.
        let afterPull = DiscoverView.eligibleItems(
            [settledEvent, settledMarket], now: now, retainingIds: []
        )
        XCTAssertTrue(afterPull.isEmpty)
    }

    /// Ruling A (recovery + Retry over cached seed): when a deck is already painted
    /// (including a cached seed before `hasPublishedNetworkFeed`), both a recovery
    /// attempt (`isRecoveryAttempt: true, mayReorder: false`) and a Retry tap
    /// (`mayReorder: false`) hold the painted order still.
    @MainActor
    func testRecoveryAndRetryOverSeededDeckHoldPaintedOrder11984() async throws {
        nonisolated final class ScriptedClient: DiscoverFeedProviding, @unchecked Sendable {
            private let lock = NSLock()
            private var pages: [Result<FeedResponse, Error>]
            init(_ pages: [Result<FeedResponse, Error>]) { self.pages = pages }
            nonisolated func fetchDiscoverFeed(
                limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
            ) async throws -> FeedResponse {
                try lock.withLock { pages.removeFirst() }.get()
            }
        }
        func makePage(ids: [Int], edition: String) throws -> FeedResponse {
            let items = ids.map { id in
                """
                {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1}],"outcome_count":1}}
                """
            }.joined(separator: ",")
            let json = """
            {"items":[\(items)],"total":\(ids.count),"limit":20,"offset":0,"has_more":false,"edition":"\(edition)"}
            """
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(FeedResponse.self, from: Data(json.utf8))
        }

        let seedPage = try makePage(ids: [10, 20, 30], edition: "ed-seed")
        let recoveryPage = try makePage(ids: [30, 10, 40], edition: "ed-recovery")
        let retryPage = try makePage(ids: [40, 30, 50], edition: "ed-retry")
        let pullPage = try makePage(ids: [50, 40, 10], edition: "ed-pull")

        let client = ScriptedClient([
            .success(seedPage),
            .success(recoveryPage),
            .success(retryPage),
            .success(pullPage),
        ])
        let vm = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil)
        vm.openingEditionEnabled = false

        await vm.load()
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), [10, 20, 30])

        // Recovery ladder attempt (`isRecoveryAttempt: true, mayReorder: false`) keeps painted order:
        await vm.load(isRecoveryAttempt: true, mayReorder: false)
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), [10, 20, 30, 40])

        // Retry button (`mayReorder: false`) keeps painted order:
        await vm.load(mayReorder: false)
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), [10, 20, 30, 40, 50])

        // Pull-to-refresh (`mayReorder: true`) applies the incoming order:
        await vm.load(mayReorder: true)
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), [50, 40, 10])
    }

    /// Ruling A (call-site wiring guard): both Retry buttons in `DiscoverView.swift`
    /// pass `mayReorder: false`, the recovery ladder in `DiscoverViewModel.swift`
    /// passes `isRecoveryAttempt: true, mayReorder: false`, and pull-to-refresh
    /// passes `mayReorder: true`.
    func testNonPullLoadCallSitesPassMayReorderFalse11984() throws {
        let testFile = URL(fileURLWithPath: #filePath)
        let root = testFile
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
        let viewSource = try String(
            contentsOf: root.appendingPathComponent("Views/DiscoverView.swift"),
            encoding: .utf8
        )
        let vmSource = try String(
            contentsOf: root.appendingPathComponent("ViewModels/DiscoverViewModel.swift"),
            encoding: .utf8
        )

        let retryMatches = viewSource.components(separatedBy: "Task { await vm.load(mayReorder: false) }").count - 1
        XCTAssertEqual(retryMatches, 2, "Both Retry buttons in DiscoverView must pass mayReorder: false")
        XCTAssertFalse(
            viewSource.contains("Task { await vm.load() }"),
            "No Retry button in DiscoverView may call vm.load() with default mayReorder"
        )
        XCTAssertTrue(
            viewSource.contains("let outcome = await Task { @MainActor in await vm.load() }.value"),
            "Pull-to-refresh is the sole DiscoverView caller using the pull default (mayReorder == true)"
        )
        XCTAssertTrue(
            viewSource.contains("await Task { @MainActor in await model.load(mayReorder: false) }.value"),
            "#11984 Path 1: loadForInitialAppearance must pass mayReorder: false so seeded launches do not reshuffle"
        )
        XCTAssertTrue(
            vmSource.contains("_ = await load(mayReorder: false)"),
            "#11984 Path 2: replaceRetiredEdition must pass mayReorder: false so mid-scroll expiry does not reshuffle"
        )
        XCTAssertTrue(
            vmSource.contains("await self.load(isRecoveryAttempt: true, mayReorder: false)"),
            "Recovery ladder must pass isRecoveryAttempt: true, mayReorder: false"
        )
        XCTAssertTrue(
            vmSource.contains("let allowReorder = (mayReorder && !isRecoveryAttempt) || items.isEmpty"),
            "DiscoverViewModel.load must forbid reorder whenever mayReorder is false or isRecoveryAttempt is true over a non-empty deck"
        )
    }

    /// Ruling C (`MemoizedPresentation<GroupedPresentation>` retention across `pullEpoch`):
    /// non-pull rebuilds at the same `pullEpoch` retain `admittedIds` in `presentationCache`
    /// so settled cards stay in place, and bumping `pullEpoch` clears `retainedItemIds`
    /// so settled cards leave on pull-to-refresh.
    func testMemoizedPresentationRetainsAdmittedIdsUntilPullEpochBumps11984() throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-06T20:00:00Z")!
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        func decodeItem(_ json: String) throws -> FeedItem {
            try decoder.decode(FeedItem.self, from: Data(json.utf8))
        }

        let liveEvent = try decodeItem("""
        {"type":"event","score":90,"data":{"id":100,"sport":"basketball_nba","home_team":"Celtics","away_team":"Lakers","status":"live","commence_time":"2026-11-06T10:00:00Z","home_score":98,"away_score":97}}
        """)
        let openMarket = try decodeItem("""
        {"type":"futures","score":88,"data":{"id":200,"name":"Will rate cut happen?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":2000,"name":"Yes","probability":0.62,"rank":1}],"outcome_count":1}}
        """)
        let settledEvent = try decodeItem("""
        {"type":"event","score":90,"data":{"id":100,"sport":"basketball_nba","home_team":"Celtics","away_team":"Lakers","status":"completed","commence_time":"2026-11-06T10:00:00Z","ended_at":"2026-11-06T11:30:00Z","home_score":104,"away_score":99}}
        """)

        let cache = MemoizedPresentation<DiscoverView.GroupedPresentation>()

        // 1. Initial paint at pullEpoch = 0 admits event-100 and futures-200.
        let initial = DiscoverView.evaluatePresentationRetention(
            [liveEvent, openMarket],
            in: cache,
            signature: "v1|0|0|0|",
            pullEpoch: 0,
            now: now
        )
        XCTAssertEqual(initial.map(DiscoverView.feedItemId), ["event-100", "futures-200"])
        XCTAssertEqual(DiscoverView.retainedItemIds(from: cache, pullEpoch: 0), ["event-100", "futures-200"])

        // 2. Non-pull rebuild (itemsVersion bumps to v2, pullEpoch stays 0): event-100 is now settled,
        //    and cache retains admittedIds so event-100 stays in place with its final score.
        let nonPull = DiscoverView.evaluatePresentationRetention(
            [settledEvent, openMarket],
            in: cache,
            signature: "v2|0|0|0|",
            pullEpoch: 0,
            now: now
        )
        XCTAssertEqual(nonPull.map(DiscoverView.feedItemId), ["event-100", "futures-200"])
        XCTAssertEqual(nonPull.first?.event?.status, "completed")
        XCTAssertEqual(nonPull.first?.event?.homeScore, 104)

        // 3. Pull-to-refresh bumps pullEpoch to 1: retainedItemIds(from: cache, pullEpoch: 1) is empty,
        //    so settled event-100 is dropped and only open futures-200 remains.
        XCTAssertTrue(DiscoverView.retainedItemIds(from: cache, pullEpoch: 1).isEmpty)
        let afterPull = DiscoverView.evaluatePresentationRetention(
            [settledEvent, openMarket],
            in: cache,
            signature: "v3|0|0|1|",
            pullEpoch: 1,
            now: now
        )
        XCTAssertEqual(afterPull.map(DiscoverView.feedItemId), ["futures-200"])
    }

    // MARK: - #11984 Paths 1, 2 & 3 end-to-end stability proofs

    /// Path 1 (`DiscoverView.loadForInitialAppearance`): when the last-good cache
    /// seeds `[10, 20]` and `/api/feed` returns a newer `edition` (`[30, 10]` with
    /// updated probability on `10` plus `has_more: true`), painted `[10, 20]` keep
    /// their exact seats, `10` takes the fresh probability in place, `30` appends,
    /// `loadMoreIfNeeded()` paginates the new edition cleanly (`40` appends), and
    /// pull-to-refresh (`mayReorder: true`) repaints to the server's order!
    @MainActor
    func testPath1SeededInitialAppearanceKeepsPaintedSeatsPaginatesAndPullRepaints11984() async throws {
        nonisolated final class ScriptedClient: DiscoverFeedProviding, @unchecked Sendable {
            private let lock = NSLock()
            private var pages: [FeedResponse]
            init(_ pages: [FeedResponse]) { self.pages = pages }
            nonisolated func fetchDiscoverFeed(
                limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
            ) async throws -> FeedResponse {
                lock.withLock { pages.removeFirst() }
            }
        }
        nonisolated final class SeedCache: DiscoverLastGoodReading, @unchecked Sendable {
            let payload: CachedDiscoverFeed
            init(_ response: FeedResponse) {
                payload = CachedDiscoverFeed(response: response, storedAt: Date(), ttlSeconds: 30, identity: "anon:s1")
            }
            func loadLastGoodFeed() async -> CachedDiscoverFeed? { payload }
        }
        func makePage(items: [(id: Int, prob: Double)], edition: String, offset: Int = 0, hasMore: Bool = false) throws -> FeedResponse {
            let encoded = items.map { entry in
                """
                {"type":"futures","score":90,"data":{"id":\(entry.id),"name":"Market \(entry.id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(entry.id * 10),"name":"Yes","probability":\(entry.prob),"rank":1}],"outcome_count":1}}
                """
            }.joined(separator: ",")
            let json = """
            {"items":[\(encoded)],"total":4,"limit":2,"offset":\(offset),"has_more":\(hasMore),"edition":"\(edition)"}
            """
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(FeedResponse.self, from: Data(json.utf8))
        }

        let cachedSeed = try makePage(items: [(10, 0.40), (20, 0.55)], edition: "ed-cached", hasMore: false)
        let freshPage0 = try makePage(items: [(30, 0.70), (10, 0.62)], edition: "ed-fresh", offset: 0, hasMore: true)
        let freshPage1 = try makePage(items: [(40, 0.81)], edition: "ed-fresh", offset: 2, hasMore: false)
        let pullPage0 = try makePage(items: [(30, 0.70), (10, 0.62)], edition: "ed-fresh", offset: 0, hasMore: false)

        let vm = DiscoverViewModel(
            client: ScriptedClient([freshPage0, freshPage1, pullPage0]),
            lastGood: SeedCache(cachedSeed),
            telemetry: nil
        )
        vm.openingEditionEnabled = false

        let outcome = await DiscoverView.loadForInitialAppearance(vm)
        XCTAssertEqual(outcome, .published)
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), [10, 20, 30], "seeded [10, 20] hold their seats; unseen 30 appends")
        let updatedProb = vm.items.first(where: { $0.futures?.id == 10 })?.futures?.topOutcomes?.first?.probability ?? 0
        XCTAssertEqual(updatedProb, 0.62, accuracy: 0.0001, "painted card 10 updates its probability in place")

        // Page 2 (`ed-fresh`) splices cleanly rather than being dropped for mismatched edition.
        await vm.loadMoreIfNeeded()
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), [10, 20, 30, 40])

        // Pull-to-refresh (`mayReorder: true`) repaints to `ed-fresh` order even though `paintedEdition` was already `ed-fresh`.
        await vm.load(mayReorder: true)
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), [30, 10])
    }

    /// Path 3 (`DiscoverView.resolveGroupedPresentation`): once page 1 is drawn,
    /// appending page 2 at the same `pullEpoch` and `dismissVersion` NEVER
    /// collapses page-1 floor-expanded singles back into groups, NEVER mutates an
    /// already-drawn page-1 group card when a sibling market arrives on page 2,
    /// refreshes page-1 live scores in place, and resets cleanly on `pullEpoch` bump!
    func testPath3GroupedPresentationFreezesPrefixAcrossPaginationAndLiveTicksUntilPull11984() throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-06T20:00:00Z")!
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        func makeFutures(id: Int, name: String, category: String = "economics", prob: Double = 0.55) throws -> FeedItem {
            let json = """
            {"type":"futures","score":90,"data":{"id":\(id),"name":"\(name)","llm_sport_category":"\(category)","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"Yes","probability":\(prob),"rank":1}],"outcome_count":1}}
            """
            return try decoder.decode(FeedItem.self, from: Data(json.utf8))
        }
        func makeLiveEvent(id: Int, homeScore: Int) throws -> FeedItem {
            let json = """
            {"type":"event","score":92,"data":{"id":\(id),"sport":"basketball_nba","home_team":"Celtics","away_team":"Lakers","status":"live","commence_time":"2026-11-06T19:00:00Z","home_score":\(homeScore),"away_score":95}}
            """
            return try decoder.decode(FeedItem.self, from: Data(json.utf8))
        }

        // Page 1 has 1 live game + 2 "Fed Rate:" markets (under `groupExpansionFloor = 8`,
        // so `enforceGroupFloor` expands the "Fed Rate" pair into 2 singles on page 1!).
        let page1: [FeedItem] = [
            try makeLiveEvent(id: 1, homeScore: 98),
            try makeFutures(id: 2, name: "Fed Rate: Cut in Dec", category: "economics"),
            try makeFutures(id: 3, name: "Fed Rate: Hold in Dec", category: "economics"),
        ]
        let firstPass = DiscoverView.resolveGroupedPresentation(
            rawItems: page1,
            cached: nil,
            pullEpoch: 0,
            dismissVersion: 0,
            dismissedAt: [:],
            profile: nil,
            now: now
        )
        let initialIds = firstPass.items.map(\.id)
        XCTAssertEqual(initialIds.count, 3, "under groupExpansionFloor, Fed Rate pair expands into 2 singles")

        // Page 2 arrives with 12 distinct markets (pushing total well past `groupExpansionFloor = 8`)
        // PLUS a 3rd "Fed Rate:" market AND an updated live score on event 1 (`homeScore: 102`).
        var page1UpdatedPlusPage2: [FeedItem] = [
            try makeLiveEvent(id: 1, homeScore: 102),
            page1[1],
            page1[2],
            try makeFutures(id: 4, name: "Fed Rate: Hike in Dec", category: "economics"),
        ]
        for i in 5...15 {
            page1UpdatedPlusPage2.append(
                try makeFutures(id: i, name: "Standalone Market \(i)?", category: i % 2 == 0 ? "politics" : "tech")
            )
        }

        let afterPage2 = DiscoverView.resolveGroupedPresentation(
            rawItems: page1UpdatedPlusPage2,
            cached: firstPass,
            pullEpoch: 0,
            dismissVersion: 0,
            dismissedAt: [:],
            profile: nil,
            now: now
        )

        // Every page-1 card stayed in its exact seat (never collapsed into a group!),
        // event 1 updated its live score in place to 102, and no duplicate SwiftUI IDs exist.
        XCTAssertEqual(Array(afterPage2.items.prefix(initialIds.count)).map(\.id), initialIds)
        let refreshedLeadScore = afterPage2.items.first.flatMap(DiscoverView.primaryFeedItem)?.event?.homeScore
        XCTAssertEqual(refreshedLeadScore, 102, "frozen page-1 card updates its live score in place")
        XCTAssertEqual(afterPage2.items.count, Set(afterPage2.items.map(\.id)).count, "no duplicate Identifiable IDs")

        // On pull-to-refresh (`pullEpoch` bumps to 1), the full deck re-evaluates fresh and groups the 3 Fed Rate items!
        let afterPull = DiscoverView.resolveGroupedPresentation(
            rawItems: page1UpdatedPlusPage2,
            cached: afterPage2,
            pullEpoch: 1,
            dismissVersion: 0,
            dismissedAt: [:],
            profile: nil,
            now: now
        )
        XCTAssertTrue(
            afterPull.items.contains(where: { $0.id == "group-related-Fed Rate" }),
            "after pull-to-refresh, all 3 Fed Rate markets collapse into one grouped card"
        )
    }
}
