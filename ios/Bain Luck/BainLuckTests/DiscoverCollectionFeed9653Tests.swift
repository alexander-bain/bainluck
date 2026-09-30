import XCTest
@testable import Bain_Luck

/// Source guards for the additive producer-card consumer. Native owns execution.
@MainActor
final class DiscoverCollectionFeed9653Tests: XCTestCase {
    private func decoder() -> JSONDecoder {
        let result = JSONDecoder()
        result.keyDecodingStrategy = .convertFromSnakeCase
        return result
    }

    private func card(league: String = "nfl", revision: Int = 1) -> [String: Any] {
        let slug = league == "mlb" ? "mlb-2026-postseason" : "nfl-2026-week-4"
        let edition: [String: Any] = league == "mlb"
            ? ["kind": "mlb_postseason", "league": "mlb", "season": 2026]
            : ["kind": "nfl_week", "league": "nfl", "season": 2026, "stage": "Regular Season", "week": 4]
        return ["type": "collection", "id": league == "mlb" ? 902 : 901,
                "name": league == "mlb" ? "MLB 2026 Postseason" : "NFL Week 4",
                "text": "Supplied collection text", "slug": slug, "state": "published",
                "revision": revision, "edition": edition, "status": "upcoming",
                "game_count": 2, "question_count": 3, "matched_event_ids": [7],
                "destination": ["kind": "container", "slug": slug,
                                "web": "/collection/\(slug)", "api": "/api/containers/\(slug)"]]
    }

    private func envelope(_ data: Any, score: Int = 35) -> [String: Any] {
        ["type": "collection", "score": score, "data": data]
    }

    private func futures(_ id: Int) -> [String: Any] {
        ["type": "futures", "score": 92, "data": [
            "id": id, "name": "Question \(id)?", "llm_sport_category": id.isMultiple(of: 2) ? "politics" : "economics",
            "top_outcomes": [["id": id * 10, "name": "Yes", "probability": 0.55]]]]
    }

    private func item(_ payload: [String: Any]) throws -> FeedItem {
        try decoder().decode(FeedItem.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    private func response(_ items: [[String: Any]], offset: Int = 0, limit: Int? = nil, hasMore: Bool = false) throws -> FeedResponse {
        let payload: [String: Any] = ["items": items, "offset": offset, "limit": limit ?? items.count,
                                      "total": 99, "has_more": hasMore]
        return try decoder().decode(FeedResponse.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    func testOrdinaryOldPayloadNeedsNoCollectionField() throws {
        let old = try item(futures(1))
        XCTAssertNil(old.collection)
        XCTAssertEqual(old.id, "futures-1")
        XCTAssertTrue(DiscoverViewModel.isRenderable(old))
    }

    func testCollectionDecodesOnlyTheProducerUnderTheOrdinaryDataEnvelope() throws {
        var data = card()
        data["status"] = "completed"
        let entry = try item(envelope(data, score: 35))
        XCTAssertEqual(entry.collection?.name, "NFL Week 4")
        XCTAssertEqual(entry.score, 35, "The consumer must not add a rank bonus.")
        XCTAssertEqual(entry.id, "collection-nfl-2026-week-4")
        XCTAssertEqual(DiscoverView.feedItemId(entry), entry.id)
        XCTAssertNil(entry.event)
        XCTAssertNil(entry.futures)
        XCTAssertNil(entry.bundle)
        XCTAssertTrue(DiscoverViewModel.isRenderable(entry))
        XCTAssertFalse(DiscoverView.isStaleItem(entry), "Game lifecycle is not collection publication.")
    }

    func testNameRevisionCountsAndScoreChangesCannotChangeCanonicalIdentity() throws {
        let original = try item(envelope(card()))
        var revised = card(revision: 2)
        revised["name"] = "Updated supplied name"
        revised["question_count"] = 8
        let fresh = try item(envelope(revised, score: 99))
        XCTAssertEqual(original.id, fresh.id)
        XCTAssertEqual(DiscoverView.feedItemId(original), DiscoverView.feedItemId(fresh))
        let merged = DiscoverFeedReconcile.merge(painted: [try item(futures(1)), original, try item(futures(2))],
                                                 incoming: [fresh, try item(futures(2)), try item(futures(1))], key: { $0.id })
        XCTAssertEqual(merged.map(\.id), ["futures-1", original.id, "futures-2"])
        XCTAssertEqual(merged[1].collection?.revision, 2)
        XCTAssertEqual(merged[1].collection?.name, "Updated supplied name")
        XCTAssertEqual(merged[1].collection?.questionCount, 8)
    }

    func testBothAcceptedEditionsUseTheExistingBrowseEntryAndCanonicalHubRoute() throws {
        for league in ["nfl", "mlb"] {
            let payload = card(league: league)
            let feed = try item(envelope(payload))
            let entry = try XCTUnwrap(DiscoverCollectionFeed.entry(for: feed.collection))
            XCTAssertEqual(entry.subtitle, "2 games · 3 questions")
            XCTAssertEqual(entry.route, .containerHub(slug: entry.collection.slug, name: entry.collection.name))
            let browse = try decoder().decode(ContainerDiscoveryResponse.self,
                from: JSONSerialization.data(withJSONObject: ["collections": [payload]]))
            let shared = ContainerDiscoveryRequest(league: league == "nfl" ? .nfl : .mlb, season: 2026).entries(in: browse)
            XCTAssertEqual(shared.map(\.id), [entry.id])
            XCTAssertEqual(shared.first?.subtitle, entry.subtitle)
        }
        let nfl = try XCTUnwrap(DiscoverCollectionFeed.entry(for: try item(envelope(card())).collection))
        XCTAssertEqual(DiscoverCollectionFeed.editionLabel(for: nfl), "NFL · 2026 · Regular Season · Week 4")
        let mlb = try XCTUnwrap(DiscoverCollectionFeed.entry(for: try item(envelope(card(league: "mlb"))).collection))
        XCTAssertEqual(DiscoverCollectionFeed.editionLabel(for: mlb), "MLB · 2026 · Postseason")
    }

    func testUnpublishedWithdrawnAndEmptyCollectionDataCannotBecomeCards() throws {
        for state in ["unpublished", "withdrawn", "empty", "unavailable", "unknown"] {
            var data = card()
            data["state"] = state
            XCTAssertEqual(DiscoverViewModel.suppressionReason(try item(envelope(data))), "invalid_collection")
        }
        var empty = card()
        empty["game_count"] = 0; empty["question_count"] = 0
        XCTAssertFalse(DiscoverViewModel.isRenderable(try item(envelope(empty))))
        for data in [NSNull(), "malformed", ["slug": "nfl-2026-week-4"]] as [Any] {
            let value = try item(envelope(data))
            XCTAssertNil(value.collection)
            XCTAssertFalse(DiscoverViewModel.isRenderable(value))
        }
    }

    func testWrongDestinationEditionAndInvalidCountsFailClosed() throws {
        var cases: [[String: Any]] = []
        var wrongDestination = card()
        wrongDestination["destination"] = ["kind": "event", "id": 7, "api": "/api/events/7"]
        cases.append(wrongDestination)
        for slug in ["nfl-2025-week-4", "nfl-2026-week-5", "../nfl-2026-week-4"] {
            var data = card()
            data["slug"] = slug
            data["destination"] = ["kind": "container", "slug": slug, "api": "/api/containers/\(slug)"]
            cases.append(data)
        }
        for field in ["id", "revision", "game_count", "question_count"] {
            var data = card(); data[field] = -1; cases.append(data)
        }
        var unknownEdition = card()
        unknownEdition["edition"] = ["kind": "soccer_round", "league": "soccer", "season": 2026]
        cases.append(unknownEdition)
        for payload in cases {
            XCTAssertFalse(DiscoverViewModel.isRenderable(try item(envelope(payload))))
        }
    }

    func testMalformedSiblingDoesNotLoseAHealthyMixedDeckOrPaginationMetadata() throws {
        let deck = try response([futures(1), envelope(NSNull()), envelope(card()),
                                 envelope(["bad": true]), futures(2)], offset: 20, limit: 5, hasMore: true)
        let healthy = deck.items.filter(DiscoverViewModel.isRenderable)
        XCTAssertEqual(healthy.map(\.id), ["futures-1", "collection-nfl-2026-week-4", "futures-2"])
        XCTAssertEqual(deck.offset, 20)
        XCTAssertEqual(deck.limit, 5)
        XCTAssertTrue(deck.hasMore)
        XCTAssertEqual(healthy.map(\.score), [92, 35, 92])
    }

    func testCollectionSportsFeedbackUsesTheExistingNegativeExceptionAndGuestGate() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        for league in ["nfl", "mlb"] {
            let value = try item(envelope(card(league: league)))
            let category = DiscoverCollectionFeed.category(of: value)
            XCTAssertEqual(category, league == "nfl" ? "americanfootball" : "baseball")
            XCTAssertTrue(DiscoverCollectionFeed.isSportsFeedback(value))
            var profile = DiscoverInteractionProfile.forTesting(scores: [:], recordedAt: now)
            profile.record(category: category, action: .unlike, onSportsCard: DiscoverCollectionFeed.isSportsFeedback(value), now: now)
            XCTAssertEqual(profile.adjustment(for: category, now: now), 0)
        }
        XCTAssertFalse(DiscoverGuestFeedbackGate.allowsFeedback(startedWith: .signedOut, current: .signedOut))
        XCTAssertFalse(DiscoverGuestFeedbackGate.allowsFeedback(startedWith: .signedOut, current: .signedIn(userId: "reader")))
        let market = try item(futures(1))
        XCTAssertEqual(DiscoverCollectionFeed.category(of: market), DiscoverCategory.of(market))
        XCTAssertEqual(DiscoverCollectionFeed.family(of: market), DiscoverCategory.family(market))
    }

    func testOrdinarySpacingDoesNotGiveCollectionsAReservedLeadOrScoreBonus() throws {
        let deck = try response([futures(1), futures(2), envelope(card(), score: 35), futures(3)]).items
        let composed = FeedInterleave.spaced(deck, sportsCategories: DiscoverCategory.sportsCategories,
            category: { DiscoverCollectionFeed.category(of: $0) }, family: { DiscoverCollectionFeed.family(of: $0) })
        XCTAssertEqual(composed.map(\.id), deck.map(\.id))
        XCTAssertEqual(composed[2].score, 35)
    }

    private nonisolated final class FakeFeed: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var pages: [FeedResponse]
        private var offsets: [Int] = []
        init(_ pages: [FeedResponse]) { self.pages = pages }
        var requestedOffsets: [Int] { lock.withLock { offsets } }
        func fetchDiscoverFeed(limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?) async throws -> FeedResponse {
            try lock.withLock {
                offsets.append(offset)
                guard !pages.isEmpty else { throw URLError(.badServerResponse) }
                return pages.removeFirst()
            }
        }
    }

    func testPaginationDeduplicatesTheHubWithoutMovingThePaintedPrefix() async throws {
        let initial = [futures(1), envelope(card())] + (2...12).map(futures)
        let first = try response(initial, hasMore: true)
        let next = try response([envelope(card(revision: 2)), envelope(card(league: "mlb")), futures(99)], offset: 13)
        let client = FakeFeed([first, next])
        let vm = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil)
        await vm.load()
        let painted = vm.items.map(\.id)
        XCTAssertEqual(painted.count, 13)
        await vm.loadMoreIfNeeded()
        XCTAssertEqual(Array(vm.items.prefix(painted.count)).map(\.id), painted)
        XCTAssertEqual(vm.items.filter { $0.id == "collection-nfl-2026-week-4" }.count, 1)
        XCTAssertEqual(vm.items.filter { $0.id == "collection-mlb-2026-postseason" }.count, 1)
        XCTAssertEqual(vm.items.count, 15)
        XCTAssertFalse(vm.hasMore)
        XCTAssertEqual(client.requestedOffsets, [0, 13])
    }

    func testFreshWithdrawalRemovesOnlyTheCollectionAndKeepsTheOrdinaryAnchors() async throws {
        let ordinary = (1...12).map(futures)
        let initial = [ordinary[0], envelope(card())] + Array(ordinary.dropFirst())
        var withdrawn = card(revision: 2)
        withdrawn["state"] = "withdrawn"
        let fresh = [ordinary[0], envelope(withdrawn)] + Array(ordinary.dropFirst())
        let client = FakeFeed([try response(initial), try response(fresh)])
        let vm = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil)
        await vm.load()
        let anchors = vm.items.filter { $0.collection == nil }.map(\.id)
        await vm.load()
        XCTAssertEqual(vm.items.map(\.id), anchors)
        XCTAssertFalse(vm.items.contains { $0.type == "collection" })
    }

}
