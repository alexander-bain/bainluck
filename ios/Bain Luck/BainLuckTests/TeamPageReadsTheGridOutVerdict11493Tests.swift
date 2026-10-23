import XCTest
@testable import Bain_Luck

/// #11493 — an eliminated club's team page reads as out, the way its own
/// Division Race row already does.
///
/// Specimen: `/api/teams/atlanta-braves` as lane1b's producer (PR #11500) serves
/// it after the Dodgers put Atlanta out in the NLDS. `championship_path[0]` is
/// market 114584 "MLB World Series Champion 2026" still trading at 0.001, now
/// with `state: "eliminated"`; the futures row for the same market carries the
/// same state; the tier-1 award 206639 "MLB: 2026 NL Hank Aaron Winner" is
/// deliberately NOT stamped (the title's verdict is not the award's). The
/// shape mirrors `backend/tests/test_team_page_reads_the_grid_out_verdict_11493.py`.
///
/// Before this, the phone printed "Championship 0%" (0.001 rounded) above a
/// Champion cell that said ✕.
final class TeamPageReadsTheGridOutVerdict11493Tests: XCTestCase {

    // MARK: - Fixtures (served shape, snake_case)

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func futureJSON(
        outcomeId: Int, market: Int, name: String, tier: Int, probability: String,
        rank: String = "10", isWinner: String = "false", state: String? = nil
    ) -> String {
        let stamped = state.map { ", \"state\": \"\($0)\"" } ?? ""
        return """
        {"outcome_id": \(outcomeId), "outcome_name": "Atlanta Braves", "market_id": \(market),
         "market_name": "\(name)", "market_tier": \(tier), "category": "baseball",
         "source": "polymarket", "probability": \(probability),
         "probability_change_24h": null, "rank": \(rank), "total_outcomes": 30,
         "resolution_date": null, "is_winner": \(isWinner), "matched_team": null,
         "canonical_market_key": null\(stamped)}
        """
    }

    private func page(
        pathProbability: String = "0.001", pathState: String? = "eliminated",
        titleRowState: String? = "eliminated"
    ) throws -> TeamPageResponse {
        let stamped = pathState.map { ", \"state\": \"\($0)\"" } ?? ""
        let json = """
        {"team": {"id": 7, "slug": "atlanta-braves", "name": "Atlanta Braves",
                  "sport_key": "baseball_mlb"},
         "upcoming_events": [], "recent_events": [],
         "championship_path": [
           {"tier": 1, "label": "Championship", "market_name": "MLB World Series Champion 2026",
            "market_id": 114584, "probability": \(pathProbability), "rank": 10,
            "movement": null\(stamped)}
         ],
         "futures": [
           \(futureJSON(outcomeId: 1, market: 114584, name: "MLB World Series Champion 2026",
                        tier: 1, probability: "0.001", state: titleRowState)),
           \(futureJSON(outcomeId: 2, market: 206639, name: "MLB: 2026 NL Hank Aaron Winner",
                        tier: 1, probability: "0.001", rank: "12"))
         ]}
        """
        return try decoder().decode(TeamPageResponse.self, from: Data(json.utf8))
    }

    private func row(_ page: TeamPageResponse, market: Int) throws -> TeamFutureItem {
        try XCTUnwrap(page.futures.first { $0.marketId == market })
    }

    // MARK: - Decode

    func testTheServedStateDecodesOnThePathStepAndTheTitleRowOnly() throws {
        let braves = try page()
        XCTAssertEqual(braves.championshipPath[0].gridVerdict, .eliminated)
        // The price is left exactly as served; `state` is the new fact.
        XCTAssertEqual(braves.championshipPath[0].probability, 0.001)
        XCTAssertEqual(try row(braves, market: 114584).gridVerdict, .eliminated)
        XCTAssertNil(try row(braves, market: 206639).gridVerdict,
                     "the award is not stamped and must not read as out")
    }

    func testAnUnknownStateDecodesAndIsIgnored() throws {
        let braves = try page(pathState: "clinched_bye", titleRowState: "clinched_bye")
        XCTAssertNil(braves.championshipPath[0].gridVerdict)
        XCTAssertNil(try row(braves, market: 114584).gridVerdict)
    }

    // MARK: - Championship Path step

    func testAnEliminatedStepPrintsOutNeverAPercent() throws {
        let step = try page().championshipPath[0]
        XCTAssertEqual(ChampionshipPathPresentation.value(step), .out)
        XCTAssertEqual(TeamFutureRowPresentation.outBadge, "Out")
    }

    func testAWonStepPrintsTheWonBadge() throws {
        let step = try page(pathProbability: "0.97", pathState: "won").championshipPath[0]
        XCTAssertEqual(ChampionshipPathPresentation.value(step), .won)
    }

    func testAnUnstampedStepKeepsTodaysNumber() throws {
        let step = try page(pathState: nil).championshipPath[0]
        XCTAssertEqual(ChampionshipPathPresentation.value(step), .percent("0%"))
        let live = try page(pathProbability: "0.64", pathState: nil).championshipPath[0]
        XCTAssertEqual(ChampionshipPathPresentation.value(live), .percent("64%"))
    }

    func testADecidedStepPrintsNoRank() throws {
        let braves = try page()
        XCTAssertNil(TeamDivisionRace.pathRank(
            braves.championshipPath[0], race: nil, raceSettled: true))
        let live = try page(pathState: nil)
        XCTAssertEqual(TeamDivisionRace.pathRank(
            live.championshipPath[0], race: nil, raceSettled: true), 10)
    }

    // MARK: - Season Futures row

    func testAnEliminatedRowIsOutWithNoNumberAndNoRank() throws {
        let presented = TeamFutureRowPresentation.row(try row(try page(), market: 114584))
        XCTAssertTrue(presented.out)
        XCTAssertFalse(presented.settledWon)
        XCTAssertNil(presented.percent, "0.001 under a grid verdict is not a chance")
        XCTAssertNil(presented.rankLine)
    }

    func testAGridWonRowIsAResultWithNoLiveNumber() throws {
        let item = try decoder().decode(TeamFutureItem.self, from: Data(futureJSON(
            outcomeId: 3, market: 114584, name: "MLB World Series Champion 2026",
            tier: 1, probability: "0.97", state: "won").utf8))
        let presented = TeamFutureRowPresentation.row(item)
        XCTAssertTrue(presented.settledWon)
        XCTAssertFalse(presented.out)
        XCTAssertNil(presented.percent)
        XCTAssertNil(presented.rankLine)
    }

    func testAGradedWinnerOutranksTheGridState() throws {
        let item = try decoder().decode(TeamFutureItem.self, from: Data(futureJSON(
            outcomeId: 4, market: 114584, name: "MLB World Series Champion 2026",
            tier: 1, probability: "1.0", isWinner: "true", state: "won").utf8))
        let presented = TeamFutureRowPresentation.row(item)
        XCTAssertTrue(presented.settledWon)
        XCTAssertEqual(presented.percent, "100%", "#9091's graded row is unchanged")
    }

    func testTheUnstampedAwardKeepsItsLiveNumber() throws {
        let presented = TeamFutureRowPresentation.row(try row(try page(), market: 206639))
        XCTAssertFalse(presented.out)
        XCTAssertFalse(presented.settledWon)
        XCTAssertEqual(presented.percent, formatProbability(0.001))
        XCTAssertEqual(presented.rankLine, "#12 of 30")
    }

    // MARK: - The trap: the step stays, so the title row never resurfaces

    func testTheEliminatedStepStillHidesTheSameMarketsFuturesRow() throws {
        let braves = try page()
        let shown = TeamDivisionRace.seasonFutures(
            braves.futures, championshipPath: braves.championshipPath, race: nil,
            sportKey: braves.team.sportKey)
        XCTAssertFalse(shown.contains { $0.marketId == 114584 })
        XCTAssertTrue(shown.contains { $0.marketId == 206639 })
    }

    func testADecidedStepWithNoPriceStillAnswersItsQuestion() throws {
        let braves = try page(pathProbability: "null")
        let shown = TeamDivisionRace.seasonFutures(
            braves.futures, championshipPath: braves.championshipPath, race: nil,
            sportKey: braves.team.sportKey)
        XCTAssertFalse(shown.contains { $0.marketId == 114584 },
                       "a priceless decided step must not let the title row back in")
        XCTAssertEqual(ChampionshipPathPresentation.value(braves.championshipPath[0]), .out)
    }
}
