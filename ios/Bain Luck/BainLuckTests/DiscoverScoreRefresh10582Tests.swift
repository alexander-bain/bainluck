import XCTest
import Combine
@testable import Bain_Luck

@MainActor
final class DiscoverScoreRefresh10582Tests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_791_244_800)
    private let t1 = "2026-10-05T19:00:00Z"
    private let t2 = "2026-10-05T19:01:00Z"

    private func event(revision: Int = 3, probability: Double = 0.97,
                       home: Int? = 0, away: Int? = 0,
                       clock: String? = "2026-10-05T19:00:00Z", source: String? = "espn",
                       status: String = "live", headline: String = "Held editorial", id: Int = 1) throws -> FeedItem {
        var data: [String: Any] = ["id": id, "home_team": "Home", "away_team": "Away",
            "status": status, "blend_fold_revision": ["1": revision],
            "hero_probability_source": "blend", "hero_probability_observed_at": t1,
            "current_odds": ["home_probability": probability, "away_probability": 1 - probability]]
        if let home { data["home_score"] = home }
        if let away { data["away_score"] = away }
        if let clock { data["score_observed_at"] = clock }
        if let source { data["score_source"] = source }
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedItem.self, from: JSONSerialization.data(withJSONObject:
            ["type": "event", "score": 90, "headline": headline, "data": data]))
    }

    private func apply(_ fresh: FeedItem, to held: FeedItem) -> FeedItem {
        var epochs: [String: Double] = [:]
        return DiscoverPriceRefresh.apply(DiscoverPriceCards(items: [fresh], dispositions: [fresh.id: "updated"],
            builtAt: 100), to: [held], epochs: &epochs, now: now)[0]
    }

    private func bothPaths(_ incoming: FeedItem, _ held: FeedItem) -> [FeedItem] {
        var accepted = [held.id: held]
        return [apply(incoming, to: held),
                DiscoverPriceRefresh.retainingPrices([incoming], accepted: &accepted, now: now)[0]]
    }

    func testEqualFoldAdvancesScoreAndRetainsItAcrossCachedReload() throws {
        let held = try event()
        let newer = try event(home: 5, away: 1, clock: t2, headline: "New editorial")
        for result in bothPaths(newer, held) {
            XCTAssertEqual(result.event?.homeScore, 5)
            XCTAssertEqual(result.event?.awayScore, 1)
            XCTAssertEqual(result.event?.scoreObservedAt, t2)
            XCTAssertEqual(result.event?.currentOdds?.homeProbability, 0.97)
        }
        var accepted = [held.id: held]
        let result = DiscoverPriceRefresh.retainingPrices([newer], accepted: &accepted, now: now)[0]
        XCTAssertEqual(result.headline, "New editorial")
        let reload = DiscoverPriceRefresh.retainingPrices([held], accepted: &accepted, now: now)[0]
        XCTAssertEqual(reload.event?.homeScore, 5)
        XCTAssertEqual(reload.event?.awayScore, 1)
    }

    func testNewProbabilityCannotRollScoreBack() throws {
        let held = try event(home: 5, away: 1, clock: t2)
        let incoming = try event(revision: 4, probability: 0.98, headline: "Incoming")
        for result in bothPaths(incoming, held) {
            XCTAssertEqual(result.event?.currentOdds?.homeProbability, 0.98)
            XCTAssertEqual(result.event?.homeScore, 5)
            XCTAssertEqual(result.event?.awayScore, 1)
            XCTAssertEqual(result.event?.scoreObservedAt, t2)
        }
        XCTAssertEqual(apply(incoming, to: held).headline, held.headline)
    }

    func testOlderProbabilityCanCarryNewerScoreWithoutAuthorizingPriceOrStatus() throws {
        let held = try event()
        let incoming = try event(revision: 2, probability: 0.1, home: 5, away: 1, clock: t2, status: "scheduled")
        for result in bothPaths(incoming, held) {
            XCTAssertEqual(result.event?.homeScore, 5)
            XCTAssertEqual(result.event?.currentOdds?.homeProbability, 0.97)
            XCTAssertEqual(result.event?.status, "live")
        }
    }

    func testUnorderableScoresCannotPiggybackOnNewPrice() throws {
        let held = try event(home: 5, away: 1)
        let invalid = try [
            event(revision: 4, home: 9, away: 9, clock: nil),
            event(revision: 4, home: 9, away: 9, clock: "bad"),
            event(revision: 4, home: 9, away: 9, clock: "2099-01-01T00:00:00Z"),
            event(revision: 4, home: 9, away: 9, clock: t2, source: nil),
            event(revision: 4, home: 9, away: 9, clock: t2, source: "unknown"),
            event(revision: 4, home: 9, away: nil, clock: t2),
            event(revision: 4, home: nil, away: nil, clock: nil),
            event(revision: 4, home: -1, away: 9, clock: t2),
            event(revision: 4, home: 9, away: 9, clock: t1),
            event(revision: 4, home: 9, away: 9, clock: "2026-10-05T18:59:00Z")
        ]
        for incoming in invalid {
            for result in bothPaths(incoming, held) {
                XCTAssertEqual(result.event?.homeScore, 5)
                XCTAssertEqual(result.event?.awayScore, 1)
                XCTAssertEqual(result.event?.scoreObservedAt, t1)
            }
        }
    }

    func testOfficialLowerScoreCorrectionAndSameScoreObservation() throws {
        let held = try event(home: 5, away: 1)
        for result in bothPaths(try event(home: 4, away: 1, clock: t2, source: "statpal"), held) {
            XCTAssertEqual(result.event?.homeScore, 4)
            XCTAssertEqual(result.event?.scoreSource, "statpal")
        }
        XCTAssertEqual(apply(try event(home: 5, away: 1, clock: t2), to: held).event?.scoreObservedAt, t2)
        let legacy = try event(clock: nil, source: nil)
        XCTAssertEqual(apply(try event(home: 5, away: 1, clock: t2), to: legacy).event?.homeScore, 5)
    }

    func testFinalResultAuthorityAndHeldFinalScoreFence() throws {
        let live = try event(home: 5, away: 1)
        let final = try event(home: 6, away: 1, clock: nil, source: nil, status: "completed")
        let finished = apply(final, to: live)
        XCTAssertEqual(finished.event?.status, "completed")
        XCTAssertEqual(finished.event?.homeScore, 6)
        for incoming in [try event(revision: 4, home: 8, away: 1, clock: t2),
                         try event(revision: 4, home: 8, away: 1, clock: t2, status: "completed")] {
            for result in bothPaths(incoming, finished) {
                XCTAssertEqual(result.event?.status, "completed")
                XCTAssertEqual(result.event?.homeScore, 6)
            }
        }
    }

    func testResponseEpochIdentityAndDispositionStillFenceScores() throws {
        let held = try event()
        let fresh = try event(home: 5, away: 1, clock: t2)
        var epochs = [held.id: 100.0]
        for response in [DiscoverPriceCards(items: [fresh], dispositions: [held.id: "unresolved"], builtAt: 101),
                         DiscoverPriceCards(items: [fresh], dispositions: [held.id: "updated"], builtAt: .nan)] {
            XCTAssertEqual(DiscoverPriceRefresh.apply(response, to: [held], epochs: &epochs, now: now)[0].event?.homeScore, 0)
        }
        XCTAssertEqual(apply(try event(home: 5, away: 1, clock: t2, id: 2), to: held).event?.homeScore, 0)
    }
    func testDelayedResponseAdvancesOnlyScoreAndNeverLowersPriceFence() throws {
        let held = try event()
        let fresh = try event(revision: 4, probability: 0.2, home: 5, away: 1, clock: t2)
        var epochs = [held.id: 100.0]
        let result = DiscoverPriceRefresh.apply(DiscoverPriceCards(items: [fresh],
            dispositions: [held.id: "updated"], builtAt: 99), to: [held], epochs: &epochs, now: now)[0]
        XCTAssertEqual(result.event?.homeScore, 5)
        XCTAssertEqual(result.event?.currentOdds?.homeProbability, 0.97)
        XCTAssertEqual(epochs[held.id], 100)
    }

    func testFinalUnknownScoresCanFillWithoutChangingKnownFinalSide() throws {
        let held = try event(home: nil, away: 1, clock: nil, source: nil, status: "completed")
        let filled = try event(revision: 4, home: 6, away: 1, clock: nil, source: nil, status: "completed")
        for result in bothPaths(filled, held) {
            XCTAssertEqual(result.event?.homeScore, 6)
            XCTAssertEqual(result.event?.awayScore, 1)
        }
        let changedKnown = try event(revision: 4, home: 6, away: 2, clock: t2, status: "completed")
        XCTAssertNil(apply(changedKnown, to: held).event?.homeScore)
    }

    private nonisolated final class Client: DiscoverFeedProviding, DiscoverPriceCardsProviding, @unchecked Sendable {
        let feed: FeedResponse
        let response: DiscoverPriceCards
        init(feed: FeedResponse, response: DiscoverPriceCards) { self.feed = feed; self.response = response }
        func fetchDiscoverFeed(limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?) async throws -> FeedResponse { feed }
        func fetchDiscoverPriceCards(eventIds: [Int], marketIds: [Int]) async throws -> DiscoverPriceCards { response }
    }

    private final class Handle: LiveStreamHandle {
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {}
        func close() { isClosed = true }
    }

    func testFirstScoreOnlyRefreshSurvivesActualViewModelCachedReload() async throws {
        let json: [String: Any] = ["items": [["type": "event", "score": 90, "data": [
            "id": 1, "home_team": "Home", "away_team": "Away", "status": "live",
            "home_score": 0, "away_score": 0, "blend_fold_revision": ["1": 3],
            "score_source": "espn", "score_observed_at": t1,
            "hero_probability_source": "blend", "hero_probability_observed_at": t1,
            "current_odds": ["home_probability": 0.97, "away_probability": 0.03]]]],
            "total": 1, "limit": 50, "offset": 0, "has_more": false, "edition": "score-test"]
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let feed = try decoder.decode(FeedResponse.self, from: JSONSerialization.data(withJSONObject: json))
        let held = try XCTUnwrap(feed.items.first)
        let fresh = try event(revision: 2, probability: 0.1, home: 5, away: 1, clock: t2)
        let client = Client(feed: feed, response: DiscoverPriceCards(items: [fresh],
            dispositions: [held.id: "updated"], builtAt: 100))
        let vm = DiscoverViewModel(client: client, priceClient: client,
            makePriceEventHandle: { _ in Handle() }, lastGood: nil, telemetry: nil)
        await vm.load()
        vm.setPriceCardsVisible(owner: held.id, cards: [held], visible: true)
        let arrived = expectation(description: "score-only refresh published")
        let observation = vm.$items.first { $0.first?.event?.homeScore == 5 }.sink { _ in arrived.fulfill() }
        vm.setPriceDeliveryActive(true)
        defer { vm.setPriceDeliveryActive(false) }
        await fulfillment(of: [arrived], timeout: 6)
        observation.cancel()
        vm.setPriceDeliveryActive(false)
        XCTAssertEqual(vm.items.first?.event?.homeScore, 5)
        XCTAssertEqual(vm.items.first?.event?.currentOdds?.homeProbability, 0.97)
        await vm.load()
        XCTAssertEqual(vm.items.first?.event?.homeScore, 5)
        XCTAssertEqual(vm.items.first?.event?.awayScore, 1)
    }

}
