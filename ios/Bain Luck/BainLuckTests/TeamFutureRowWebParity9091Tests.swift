import XCTest
@testable import Bain_Luck

/// #9091 — the iPhone team page's "Season Futures" row, against the served
/// payload and against its web twin.
///
/// Specimens are the Red Sox rows `/api/teams/boston-red-sox-mlb` served on
/// 2026-09-27, verbatim in the fields the row reads: a player award
/// ("Gold Glove: AL Center Field", Ceddanne Rafaela, 0.98) that printed with no
/// player named, and a settled leg ("MLB: Team to make postseason",
/// `is_winner: true`, `resolution_source: api_settlement` in the DB) that
/// printed "100% #1 of 30" as if the race were still on.
///
/// SCOPE: the parity half only READS `frontend/components/TeamFutureRow.tsx`,
/// which is ux's (notice 41). A failure there is a conversation, not an edit.
final class TeamFutureRowWebParity9091Tests: XCTestCase {

    // MARK: - Fixtures (served shape, snake_case)

    private func decode(_ json: String) throws -> TeamFutureItem {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(TeamFutureItem.self, from: Data(json.utf8))
    }

    private func item(
        outcome: String, market: String, probability: String,
        rank: String = "1", total: String = "9", isWinner: String? = "false"
    ) throws -> TeamFutureItem {
        let winner = isWinner.map { ", \"is_winner\": \($0)" } ?? ""
        return try decode("""
        {"outcome_id": 1, "outcome_name": "\(outcome)", "market_id": 2,
         "market_name": "\(market)", "market_tier": 5, "category": "baseball",
         "source": "kalshi", "probability": \(probability),
         "probability_change_24h": null, "rank": \(rank), "total_outcomes": \(total),
         "resolution_date": null\(winner), "matched_team": null,
         "canonical_market_key": null}
        """)
    }

    private var playerAward: TeamFutureItem {
        get throws {
            try item(outcome: "Ceddanne Rafaela", market: "Gold Glove: AL Center Field",
                     probability: "0.98")
        }
    }

    private var settledPostseason: TeamFutureItem {
        get throws {
            try item(outcome: "Boston Red Sox", market: "MLB: Team to make postseason",
                     probability: "1.0", total: "30", isWinner: "true")
        }
    }

    // MARK: - Decode

    func testIsWinnerDecodesFromTheServedKey() throws {
        XCTAssertEqual(try settledPostseason.isWinner, true)
        XCTAssertEqual(try playerAward.isWinner, false)
    }

    /// `/api/me/teams/futures` shares this model. A payload without the key
    /// must still decode, and absence must not read as a result.
    func testAnAbsentIsWinnerDecodesAndIsNotAResult() throws {
        let absent = try item(outcome: "Boston Red Sox", market: "MLB: Team to make postseason",
                              probability: "1.0", total: "30", isWinner: nil)
        XCTAssertNil(absent.isWinner)
        let row = TeamFutureRowPresentation.row(absent)
        XCTAssertFalse(row.settledWon)
        XCTAssertEqual(row.rankLine, "#1 of 30")
    }

    // MARK: - Who the row is about

    func testAPlayerRowNamesThePlayerAndCaptionsTheMarket() throws {
        let row = TeamFutureRowPresentation.row(try playerAward)
        XCTAssertEqual(row.title, "Ceddanne Rafaela")
        XCTAssertEqual(row.caption, "Gold Glove: AL Center Field")
        XCTAssertEqual(row.percent, "98%")
        XCTAssertEqual(row.rankLine, "#1 of 9")
        XCTAssertFalse(row.settledWon)
    }

    // MARK: - Settled means settled

    func testASettledWinnerIsAResultWithNoRank() throws {
        let row = TeamFutureRowPresentation.row(try settledPostseason)
        XCTAssertTrue(row.settledWon)
        XCTAssertNil(row.rankLine, "a rank is a claim about a race still being run")
        // The result prints its served value; the live formatter would hedge
        // an exact 1.0 to ">99%".
        XCTAssertEqual(row.percent, "100%")
    }

    // MARK: - Boundary formatting (#7710's class)

    func testAPricedSliverDoesNotPrintZero() throws {
        let row = TeamFutureRowPresentation.row(
            try item(outcome: "Munetaka Murakami", market: "AL Rookie of the Year",
                     probability: "0.004", rank: "3", total: "46"))
        XCTAssertEqual(row.percent, "<1%")
    }

    func testAnUnsettledNearCertaintyDoesNotPrintAHundred() throws {
        let row = TeamFutureRowPresentation.row(
            try item(outcome: "Milwaukee Brewers", market: "Team to advance to NLDS",
                     probability: "0.9955", total: "13"))
        XCTAssertEqual(row.percent, ">99%")
        XCTAssertFalse(row.settledWon)
    }

    func testANullProbabilityPrintsNoNumber() throws {
        let row = TeamFutureRowPresentation.row(
            try item(outcome: "Boston", market: "Pro Baseball Champion", probability: "null"))
        XCTAssertNil(row.percent)
    }

    // MARK: - Web parity (reads ux's file, never edits it)

    private var webRowSource: String {
        get throws {
            let url = URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()   // BainLuckTests
                .deletingLastPathComponent()   // Bain Luck (project dir)
                .deletingLastPathComponent()   // ios
                .deletingLastPathComponent()   // repo root
                .appendingPathComponent("frontend/components/TeamFutureRow.tsx")
            return try String(contentsOf: url, encoding: .utf8)
        }
    }

    func testTheWebRowIsWhereWeThinkItIs() throws {
        XCTAssertFalse(try webRowSource.isEmpty)
    }

    func testTheWonBadgeIsTheWebRowsWord() throws {
        XCTAssertTrue(try webRowSource.contains(TeamFutureRowPresentation.wonBadge),
                      "web's settled badge text changed — align with ux")
    }

    /// The three rules this file mirrors, read off the web row rather than
    /// restated on trust: settled is `is_winner === true`, the outcome name is
    /// drawn, and the rank is withheld when settled.
    func testTheWebRowStillCarriesTheRulesMirroredHere() throws {
        let web = try webRowSource
        XCTAssertTrue(web.contains("item.is_winner === true"))
        XCTAssertTrue(web.contains("{item.outcome_name}"))
        XCTAssertTrue(web.contains("!settledWon && item.rank && item.total_outcomes"))
    }
}
