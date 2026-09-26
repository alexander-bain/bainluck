import XCTest
@testable import Bain_Luck

/// #8640 — a search answer the venue has already called reads "Won", not a
/// live ">99%".
///
/// Production 2026-09-25, `q=Fed chair`: the family card led with "Who will be
/// confirmed as Fed chair — Kevin Warsh >99%" over a leg served
/// `is_winner: true, resolution_source: "api_settlement"` on a market still
/// `open`. Web's ANSWERS row now asks `outcomeRowVerdict`; these pin the phone's
/// twin (`OutcomeVerdict`) to the same answers, to the same constants (read out
/// of the web files, not retyped), and to the two rows in `SearchView` that
/// print a futures leader.
///
/// SCOPE: the parity half only READS `frontend/**`, which is ux's (notice 41).
/// If it fails because web changed, the finding goes to ux.
final class SearchAnswerGradedLeaderReadsAsResult8640Tests: XCTestCase {

    // MARK: - The payload carries the grade

    /// Verbatim from `/api/events/search?q=Warsh`, 2026-09-25 ~22:00Z (outcomes
    /// trimmed to the five served). Latency's #8648 demotes graded legs on an
    /// open multi-answer market, so the two called senators sit BELOW three
    /// ungraded ones.
    private static let senatorsJSON = """
    {"id": 109237, "name": "Which Senators will vote for Kevin Warsh as Fed chair?", "sport": null, "sport_name": null, "category": "politics", "llm_sport_category": "politics", "market_tier": 2, "market_type_label": "Politics", "status": "open", "source": "kalshi", "resolution_date": "2027-01-01T15:00:00+00:00", "top_outcomes": [{"id": 206769356, "name": "Pete Ricketts", "probability": 0.995, "american_odds": -19900, "rank": 8, "movement": null, "is_winner": false, "resolution_source": null}, {"id": 206769357, "name": "Shelley Moore Capito", "probability": 0.995, "american_odds": -19900, "rank": 9, "movement": null, "is_winner": false, "resolution_source": null}, {"id": 206769358, "name": "Cindy Hyde-Smith", "probability": 0.995, "american_odds": -19900, "rank": 10, "movement": null, "is_winner": false, "resolution_source": null}, {"id": 1595871, "name": "John Kennedy", "probability": 0.9995, "american_odds": -199900, "rank": 2, "movement": null, "is_winner": true, "resolution_source": "api_settlement"}, {"id": 1595875, "name": "John Fetterman", "probability": 0.9995, "american_odds": -199900, "rank": 1, "movement": null, "is_winner": true, "resolution_source": "api_settlement"}], "outcome_count": 18, "updated_at": "2026-09-10T02:50:00.442076+00:00", "prices_updated_at": "2026-07-15T18:50:56.312810+00:00"}
    """

    /// RECONSTRUCTED, not verbatim: the issue's specimen as ux read it while
    /// `open` — market 2558995, leader outcome 14869909 "Kevin Warsh" at 0.9995,
    /// `is_winner: true`, `api_settlement` (both read from the DB 2026-09-25).
    /// It is single-answer, so #8648 does NOT demote its called leg and it stays
    /// the leader. The second leg is filler. The market has since resolved and
    /// left search, so it can no longer be captured live.
    private static let fedChairWhileOpenJSON = """
    {"id": 2558995, "name": "Who will be confirmed as Fed chair?", "category": "politics", "llm_sport_category": "politics", "status": "open", "source": "polymarket", "resolution_date": null, "top_outcomes": [{"id": 14869909, "name": "Kevin Warsh", "probability": 0.9995, "american_odds": null, "rank": 1, "movement": null, "is_winner": true, "resolution_source": "api_settlement"}, {"id": 14869910, "name": "Kevin Hassett", "probability": 0.0005, "american_odds": null, "rank": 2, "movement": null, "is_winner": false, "resolution_source": null}], "outcome_count": 2, "updated_at": null}
    """

    private func decode(_ json: String) throws -> SearchFuturesMarket {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SearchFuturesMarket.self, from: Data(json.utf8))
    }

    func testTheGradeDecodesAndIsNotDropped() throws {
        let outcomes = try XCTUnwrap(decode(Self.senatorsJSON).topOutcomes)
        XCTAssertEqual(outcomes[3].name, "John Kennedy")
        XCTAssertEqual(outcomes[3].isWinner, true)
        XCTAssertEqual(outcomes[3].resolutionSource, "api_settlement")
        XCTAssertEqual(outcomes[0].isWinner, false)
        XCTAssertNil(outcomes[0].resolutionSource)
    }

    /// The row the issue named: the leader reads as a result.
    func testACalledLeaderOnAnOpenMarketReadsWon() throws {
        let market = try decode(Self.fedChairWhileOpenJSON)
        let leader = try XCTUnwrap(SearchGrouping.leaderOutcome(market))
        XCTAssertEqual(leader.name, "Kevin Warsh")
        XCTAssertEqual(leader.verdict(in: market), .won)
        XCTAssertEqual(leader.verdict(in: market)?.label, "Won")
    }

    /// Control, live today: an ungraded leader over demoted called legs keeps
    /// its price; the called legs themselves would read Won.
    func testAnUngradedLeaderKeepsItsPrice() throws {
        let market = try decode(Self.senatorsJSON)
        let leader = try XCTUnwrap(SearchGrouping.leaderOutcome(market))
        XCTAssertEqual(leader.name, "Pete Ricketts")
        XCTAssertNil(leader.verdict(in: market))
        XCTAssertEqual(market.topOutcomes?[3].verdict(in: market), .won)
    }

    /// A payload from before #8648 (no grade keys at all) prints as before.
    func testAPayloadWithoutTheGradeKeepsItsPrice() throws {
        let old = Self.fedChairWhileOpenJSON
            .replacingOccurrences(of: #", "is_winner": true, "resolution_source": "api_settlement""#, with: "")
        XCTAssertNotEqual(old, Self.fedChairWhileOpenJSON, "fixture edit did not apply")
        let market = try decode(old)
        XCTAssertNil(SearchGrouping.leaderOutcome(market)?.verdict(in: market))
    }

    // MARK: - The rule, clause by clause (web's `outcomeRowVerdict`)

    private func v(_ isWinner: Bool?, _ source: String?, resolved: Bool) -> OutcomeVerdict? {
        OutcomeVerdict.verdict(isWinner: isWinner, resolutionSource: source, marketResolved: resolved)
    }

    func testARetractionIsNeverAVerdictEvenWhenCrowned() {
        XCTAssertNil(v(true, "ungradeable_result", resolved: true))
        XCTAssertNil(v(false, "ungradeable_result", resolved: true))
        XCTAssertNil(v(true, "ungradeable_result", resolved: false))
    }

    func testAServedNullSourceSaysNothing() {
        XCTAssertNil(v(true, nil, resolved: true))
        XCTAssertNil(v(false, nil, resolved: true))
    }

    func testAMissingGradeSaysNothing() {
        XCTAssertNil(v(nil, "api_settlement", resolved: true))
    }

    /// Only the WON arm crosses the status line, and only on a venue's own
    /// settlement — a defaulted FALSE on an open market is not a called loss.
    func testAnOpenMarketEarnsOnlyAnAuthoritativeWin() {
        XCTAssertEqual(v(true, "api_settlement", resolved: false), .won)
        XCTAssertNil(v(false, "api_settlement", resolved: false))
        XCTAssertNil(v(true, "clean_resolution", resolved: false))
        XCTAssertNil(v(true, "all_losers", resolved: false))
    }

    func testAResolvedMarketGradesBothWays() {
        XCTAssertEqual(v(true, "clean_resolution", resolved: true), .won)
        XCTAssertEqual(v(false, "all_losers", resolved: true), .lost)
        XCTAssertEqual(OutcomeVerdict.lost.label, "Lost")
    }

    // MARK: - Parity with the web files (read, not retyped)

    private func repoFile(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .deletingLastPathComponent()   // ios
            .deletingLastPathComponent()   // repo root
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testTheAuthoritativeSetMatchesWeb() throws {
        let source = try repoFile("frontend/lib/resolutionAuthority.ts")
        let start = try XCTUnwrap(source.range(of: "AUTHORITATIVE_RESOLUTION_SOURCES: ReadonlySet<string> = new Set(["),
                                  "web's set moved or was renamed — route to ux")
        let end = try XCTUnwrap(source.range(of: "]);", range: start.upperBound..<source.endIndex))
        let body = source[start.upperBound..<end.lowerBound]
        let regex = try NSRegularExpression(pattern: #""([a-z_]+)""#)
        let text = String(body)
        let webSet = Set(regex.matches(in: text, range: NSRange(text.startIndex..., in: text)).compactMap {
            Range($0.range(at: 1), in: text).map { String(text[$0]) }
        })
        XCTAssertFalse(webSet.isEmpty)
        XCTAssertEqual(OutcomeVerdict.authoritativeResolutionSources, webSet)
    }

    func testTheRetractionMatchesWeb() throws {
        let source = try repoFile("frontend/components/futures/OutcomeRow.tsx")
        XCTAssertTrue(
            source.contains("export const RETRACTED_RESOLUTION_SOURCE = \"\(OutcomeVerdict.retractedResolutionSource)\";"),
            "web's retraction constant changed — route to ux"
        )
    }

    // MARK: - Both leader rows ask the rule

    /// `searchFamilyRow` and `searchFuturesRow` are the two places `SearchView`
    /// prints a futures leader's percentage. A row that stops asking prints the
    /// price over a called leg again, and no decode test can see that.
    func testBothLeaderRowsAskTheVerdictBeforeThePrice() throws {
        let view = try repoFile("ios/Bain Luck/Bain Luck/Views/SearchView.swift")
        XCTAssertEqual(view.components(separatedBy: ".verdict(in: market)").count - 1, 2)
        for row in ["private func searchFamilyRow(", "private func searchFuturesRow("] {
            let start = try XCTUnwrap(view.range(of: row))
            let next = view.range(of: "private func ", range: start.upperBound..<view.endIndex)?.lowerBound ?? view.endIndex
            let body = view[start.upperBound..<next]
            let ask = try XCTUnwrap(body.range(of: ".verdict(in: market)"), "\(row) no longer asks the verdict")
            let price = try XCTUnwrap(body.range(of: "formatProbability("))
            XCTAssertLessThan(ask.lowerBound, price.lowerBound, "\(row) prints the price before asking")
        }
    }
}
