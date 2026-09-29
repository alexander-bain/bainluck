import XCTest
@testable import Bain_Luck

@MainActor
final class GameMarketsProjectionEdgeTests: XCTestCase {
    private let t0 = "2030-01-01T00:00:00.000001Z"
    private let t1 = "2030-01-01T00:00:00.000002Z"

    private func matchup(_ price: Double? = 0.4, clock: String? = "2030-01-01T00:00:00.000001Z",
                         siblingClock: String = "2030-01-01T00:00:00.000001Z",
                         winner: Bool? = nil, include: Bool = true) throws -> GameMarketsResponse {
        func null(_ value: Any?) -> Any { value ?? NSNull() }
        var nested: [[String: Any]] = []
        if include {
            nested.append(["name": "Bears", "probability": null(price), "observed_at": NSNull(),
                           "contributor_outcome_ids": [1], "is_winner": null(winner)])
        }
        nested.append(["name": "Eagles", "probability": 0.6, "observed_at": NSNull(),
                       "contributor_outcome_ids": [2], "is_winner": NSNull()])
        let bucket: [String: Any] = ["market_name": "First score", "type": "head_to_head",
            "source": "kalshi", "_market_id": 11, "contributor_outcome_ids": [1, 2], "outcomes": nested]
        let dict: [String: Any] = ["event_id": 42, "status": "completed", "home_score": 24,
            "away_score": 17, "stream_market_ids": [11, 99],
            "outcome_market_ids": ["1": 11, "2": 11, "9": 99],
            "outcome_revision_at": ["1": null(clock), "2": t0, "9": siblingClock],
            "matchups": [bucket]]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func prop(actual: Int?, hit: Bool?, clock: String? = "2030-01-01T00:00:00.000001Z") throws -> GameMarketsResponse {
        func null(_ value: Any?) -> Any { value ?? NSNull() }
        let dict: [String: Any] = ["event_id": 42, "status": "live", "stream_market_ids": [11],
            "outcome_market_ids": ["1": 11], "outcome_revision_at": ["1": null(clock)],
            "player_props": [["market_name": "Points", "outcome_name": "Player", "over_probability": 0.6,
                "source": "kalshi", "_market_id": 11, "contributor_outcome_ids": [1],
                "actual": null(actual), "hit": null(hit)]]]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func adopt(_ next: GameMarketsResponse, _ held: GameMarketsResponse?,
                       _ fence: inout GameMarketsPriceReconciliation.Fence) -> GameMarketsResponse {
        GameMarketsPriceReconciliation.adopting(next, over: held, fence: &fence)
    }

    func testNestedMatchupsDecodeAndParticipateInExactOwnRowOrdering() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try matchup(), nil, &fence)
        XCTAssertEqual(held.matchups?.first?._marketId, 11)
        XCTAssertEqual(held.matchups?.first?.outcomes.first?.contributorOutcomeIds, [1])
        XCTAssertEqual(GameMarketsPriceReconciliation.rows(held).count, 2)
        let next = adopt(try matchup(0.5, clock: t1), held, &fence)
        XCTAssertEqual(next.matchups?.first?.outcomes.first?.probability, 0.5)
        XCTAssertEqual(adopt(try matchup(0.7, clock: t0), next, &fence), next)
        XCTAssertEqual(adopt(try matchup(0.7, clock: t1, siblingClock: t1), next, &fence), next)
    }

    func testNestedWithdrawalCannotReturnOnAnotherMarketsClock() throws {
        for remove in [true, false] {
            var fence = GameMarketsPriceReconciliation.Fence()
            let held = adopt(try matchup(), nil, &fence)
            let withdrawn = adopt(try matchup(nil, clock: nil, include: !remove), held, &fence)
            XCTAssertNotEqual(withdrawn, held)
            XCTAssertEqual(adopt(try matchup(siblingClock: t1), withdrawn, &fence), withdrawn)
            let fresh = adopt(try matchup(0.5, clock: t1, siblingClock: t1), withdrawn, &fence)
            XCTAssertEqual(fresh.matchups?.first?.outcomes.first?.probability, 0.5)
        }
    }

    func testNestedGradeSurvivesQuoteUpdatesAndCannotDisappear() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try matchup(), nil, &fence)
        let graded = adopt(try matchup(1, clock: nil, winner: true), held, &fence)
        XCTAssertEqual(graded.matchups?.first?.outcomes.first?.isWinner, true)
        XCTAssertEqual(adopt(try matchup(0.7, clock: t1), graded, &fence), graded)
        XCTAssertEqual(adopt(try matchup(clock: t1, include: false), graded, &fence), graded)
    }

    func testProvisionalActualCanAdvanceUntilAnActualGradeFreezesIt() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try prop(actual: 1, hit: nil), nil, &fence)
        let advanced = adopt(try prop(actual: 2, hit: nil), held, &fence)
        XCTAssertEqual(advanced.playerProps?.first?.actual, 2)
        let graded = adopt(try prop(actual: 3, hit: true), advanced, &fence)
        XCTAssertEqual(graded.playerProps?.first?.actual, 3)
        XCTAssertEqual(graded.playerProps?.first?.hit, true)
        XCTAssertEqual(adopt(try prop(actual: 4, hit: true, clock: t1), graded, &fence), graded)
        XCTAssertEqual(adopt(try prop(actual: 4, hit: nil, clock: t1), graded, &fence), graded)
    }

    func testProvisionalActualStillCannotLaunderAMissingPriceRevision() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try prop(actual: 1, hit: nil), nil, &fence)
        XCTAssertEqual(adopt(try prop(actual: 2, hit: nil, clock: nil), held, &fence), held)
    }
}
