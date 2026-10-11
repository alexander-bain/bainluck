import XCTest
@testable import Bain_Luck

@MainActor
final class HeldEventScoreObservation10866Tests: XCTestCase {
    private let earlier = "2026-10-11T00:48:00Z"
    private let later = "2026-10-11T00:48:10Z"
    private let newest = "2026-10-11T00:48:20Z"

    private func detail(_ changes: [String: Any] = [:]) throws -> EventDetail {
        var values: [String: Any] = [
            "id": 15323924, "sport": "basketball_nba", "status": "live",
            "home_team": "Boston Celtics", "away_team": "Philadelphia 76ers",
            "home_score": 35, "away_score": 28, "score_source": "statpal",
            "score_observed_at": later,
            "current_odds": ["home_probability": 0.73, "away_probability": 0.27]
        ]
        for (key, value) in changes { values[key] = value }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: JSONSerialization.data(withJSONObject: values))
    }

    private func assertScore(_ actual: EventDetail?, equals expected: EventDetail,
                             file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(actual?.homeScore, expected.homeScore, file: file, line: line)
        XCTAssertEqual(actual?.awayScore, expected.awayScore, file: file, line: line)
        XCTAssertEqual(actual?.scoreSource, expected.scoreSource, file: file, line: line)
        XCTAssertEqual(actual?.scoreObservedAt, expected.scoreObservedAt, file: file, line: line)
    }

    func testOlderScoreRetainsItsWholeObservationWithoutHoldingNewPriceOrMetadata() throws {
        let held = try detail()
        let response = try detail([
            "home_score": 33, "score_observed_at": earlier,
            "current_odds": ["home_probability": 0.74, "away_probability": 0.26],
            "hero_probability_observed_at": newest, "event_tags": ["incoming"]
        ])
        let result = LiveEventScoreReconciliation.keepingNewerHeldScore(response, held: held)
        assertScore(result, equals: held)
        XCTAssertEqual(result.currentOdds?.homeProbability, 0.74)
        XCTAssertEqual(result.heroProbabilityObservedAt, newest)
        XCTAssertEqual(result.eventTags, ["incoming"])
    }

    func testNewerDownwardCorrectionAndEqualClockRemainAuthoritative() throws {
        let held = try detail()
        for clock in [later, newest] {
            let response = try detail(["home_score": 32, "away_score": 27,
                                       "score_observed_at": clock])
            assertScore(LiveEventScoreReconciliation.keepingNewerHeldScore(response, held: held),
                        equals: response)
        }
    }

    func testUnknownIdentityLifecycleSourceClockAndIncompletePairsKeepResponseAuthority() throws {
        // Each uncertainty is tested on either side of the comparison. None
        // is permission to borrow a timestamp from a price or receipt.
        let uncertainties: [[String: Any]] = [
            ["id": 999], ["id": 0], ["sport": "basketball_wnba"],
            ["sport": NSNull()], ["sport": ""],
            ["home_team": "Philadelphia 76ers", "away_team": "Boston Celtics"],
            ["status": "completed"], ["status": "suspended"], ["status": "scheduled"],
            ["status": NSNull()], ["score_source": "espn"],
            ["score_source": NSNull()], ["score_source": "   "],
            ["score_observed_at": NSNull()], ["score_observed_at": "invalid"],
            ["home_score": NSNull()], ["away_score": NSNull()],
            ["home_score": -1], ["away_score": -1]
        ]
        for uncertainty in uncertainties {
            let older: [String: Any] = ["home_score": 33, "score_observed_at": earlier]
            let held = try detail()
            let response = try detail(older.merging(uncertainty, uniquingKeysWith: { _, new in new }))
            assertScore(LiveEventScoreReconciliation.keepingNewerHeldScore(response, held: held),
                        equals: response)
            let uncertainHeld = try detail(uncertainty)
            let plainResponse = try detail(older)
            assertScore(LiveEventScoreReconciliation.keepingNewerHeldScore(plainResponse, held: uncertainHeld),
                        equals: plainResponse)
        }
        let response = try detail(["home_score": 33, "score_observed_at": earlier])
        assertScore(LiveEventScoreReconciliation.keepingNewerHeldScore(response, held: nil), equals: response)
    }

    private nonisolated final class Client: EventDetailProviding, @unchecked Sendable {
        struct Unavailable: Error {}
        private let lock = NSLock()
        private var responses: [EventDetail]
        private var count = 0
        init(_ responses: [EventDetail]) { self.responses = responses }
        var fetchCount: Int { lock.withLock { count } }
        func fetchEvent(id: Int) async throws -> EventDetail {
            let response = lock.withLock { () -> EventDetail? in
                count += 1
                return responses.isEmpty ? nil : responses.removeFirst()
            }
            guard let response else { throw Unavailable() }
            return response
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Unavailable() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Unavailable() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Unavailable() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Unavailable() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Unavailable() }
    }

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() {}
        @MainActor func open() { for handler in handlers["open", default: []] { handler("") } }
    }

    private nonisolated final class Sleeper: @unchecked Sendable {
        private let lock = NSLock()
        private var wakes = 0
        func release() { lock.withLock { wakes += 1 } }
        func sleep(_ seconds: TimeInterval) async {
            while !Task.isCancelled {
                let go = lock.withLock { () -> Bool in
                    guard wakes > 0, !Task.isCancelled else { return false }
                    wakes -= 1
                    return true
                }
                if go { return }
                try? await Task.sleep(nanoseconds: 200_000)
            }
        }
    }

    func testFullLoadKeepsNewerScoreThenTakesOfficialCorrectionAndFinal() async throws {
        let held = try detail()
        let stale = try detail(["home_score": 33, "score_observed_at": earlier,
                                "current_odds": ["home_probability": 0.74, "away_probability": 0.26]])
        let corrected = try detail(["home_score": 32, "score_observed_at": newest])
        let final = try detail(["status": "completed", "home_score": 31,
                                "score_observed_at": earlier])
        let client = Client([held, stale, corrected, final])
        let sleeper = Sleeper()
        let vm = EventDetailViewModel(eventId: held.id, client: client,
                                      makeStreamHandle: { _ in Handle() },
                                      sleep: { await sleeper.sleep($0) })
        defer { vm.stopRefresh() }
        await vm.load()
        await vm.load()
        assertScore(vm.event, equals: held)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.74)
        await vm.load()
        assertScore(vm.event, equals: corrected)
        await vm.load()
        assertScore(vm.event, equals: final)
        XCTAssertEqual(vm.event?.status, "completed")
        XCTAssertEqual(client.fetchCount, 4)
    }

    func testGameStatePollKeepsNewerScoreThroughTheSameAdoptionPath() async throws {
        let held = try detail()
        let stale = try detail(["home_score": 33, "score_observed_at": earlier,
                                "current_odds": ["home_probability": 0.74, "away_probability": 0.26]])
        let client = Client([held, stale])
        let handle = Handle()
        let sleeper = Sleeper()
        let vm = EventDetailViewModel(eventId: held.id, client: client,
                                      makeStreamHandle: { _ in handle },
                                      sleep: { await sleeper.sleep($0) })
        defer { vm.stopRefresh() }
        await vm.load()
        let fullLoadAt = vm.lastLoadedAt
        handle.open()
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: EventRefreshPlan.livePushPollInterval))
        sleeper.release()
        let deadline = Date().addingTimeInterval(3)
        while vm.event?.currentOdds?.homeProbability != 0.74 && Date() < deadline {
            await Task.yield()
            try? await Task.sleep(nanoseconds: 200_000)
        }
        XCTAssertEqual(client.fetchCount, 2)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.74)
        assertScore(vm.event, equals: held)
        XCTAssertEqual(vm.lastLoadedAt, fullLoadAt, "The first pushed slot reads game state, not a full load")
    }
}
