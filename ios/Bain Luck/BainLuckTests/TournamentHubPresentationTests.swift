import XCTest
@testable import Bain_Luck

/// G2 of SHOWABLE-1 — the US Open hub's contract, asserted against the real
/// production payload rather than a hand-built one.
///
/// The class of bug these guard against is D27's: a section that returns nothing
/// and therefore renders nothing, so the phone cannot tell "the tournament has no
/// live matches right now" from "we never built that part". Every section is
/// asserted to resolve to rows OR a sentence, both here and — for the states the
/// live payload does not happen to be in today — from a payload that is empty on
/// purpose.
final class TournamentHubPresentationTests: XCTestCase {

    private func liveFixture() throws -> TournamentHubPresentation {
        TournamentHubPresentation(response: try TournamentHubProdFixture.decode())
    }

    // MARK: - The real payload decodes and reduces

    func testProductionPayloadDecodes() throws {
        let response = try TournamentHubProdFixture.decode()
        XCTAssertEqual(response.slug, "us-open")
        XCTAssertEqual(response.title, "US Open 2026")
        XCTAssertEqual(response.subtitle, "Flushing Meadows")
        XCTAssertEqual(response.slate?.matches.count, 6)
        XCTAssertEqual(response.results?.matches.count, 4)
        XCTAssertEqual(response.boards.count, 2)
    }

    func testLiveAndUpcomingMatchesAreSeparated() throws {
        let p = try liveFixture()
        XCTAssertEqual(p.liveMatches.count, 3)
        XCTAssertEqual(p.upcomingMatches.count, 3)
        XCTAssertTrue(p.liveMatches.allSatisfy(\.isLive))
        XCTAssertTrue(p.upcomingMatches.allSatisfy { !$0.isLive })
        XCTAssertNil(p.liveEmptyNote)
        XCTAssertNil(p.upcomingEmptyNote)
    }

    // MARK: - A missing price is a dash, never a confident "<1%"

    func testUnpricedMatchShowsDashesAndSaysWhy() throws {
        let p = try liveFixture()
        let unpriced = try XCTUnwrap(
            p.upcomingMatches.first { $0.noPriceNote != nil },
            "the fixture carries one unpriced match on purpose")

        XCTAssertEqual(unpriced.noPriceNote, "No price on this match yet.")
        for side in unpriced.sides {
            XCTAssertFalse(side.hasPrice)
            XCTAssertEqual(
                side.percentText, absentProbabilityMarker,
                "a side with no price must render the em-dash — `?? 0` renders "
                + "\"<1%\", which claims the player is nearly certain to lose")
            XCTAssertFalse(side.isFavourite, "nobody is the favourite in an unpriced match")
        }
    }

    func testPricedMatchNamesExactlyOneFavourite() throws {
        let p = try liveFixture()
        for match in p.liveMatches {
            XCTAssertEqual(match.sides.filter(\.isFavourite).count, 1, "match \(match.id)")
        }
        // The favourite is the higher price, not the first side listed. This
        // match is in the fixture precisely because its favourite is SECOND on
        // the wire — "first side" and "favourite" would otherwise be the same
        // answer on every row and the test would prove nothing.
        let popyrin = try XCTUnwrap(p.liveMatches.first { $0.id == "espn:182709" })
        XCTAssertEqual(popyrin.sides.map(\.name), ["Alexei Popyrin", "Alejandro Tabilo"])
        XCTAssertEqual(popyrin.sides.first(where: \.isFavourite)?.name, "Alejandro Tabilo")
        XCTAssertEqual(popyrin.sides.map(\.percentText), ["42%", "58%"])

        // The 99/1 row: `formatProbability`'s "<1%" / ">99%" guards are about the
        // VALUE, so exactly 0.01 and exactly 0.99 stay as integers.
        let bartunkova = try XCTUnwrap(p.liveMatches.first { $0.id == "espn:182542" })
        XCTAssertEqual(bartunkova.sides.map(\.percentText), ["99%", "1%"])
    }

    func testTiedPricesNameNoFavourite() {
        let p = TournamentHubPresentation(
            response: decode(Self.twoSidedJSON(homeProbability: 0.5, awayProbability: 0.5)))
        let match = p.liveMatches.first
        XCTAssertEqual(match?.sides.filter(\.isFavourite).count, 0,
                       "50/50 has no favourite; bolding both is a claim the numbers don't make")
    }

    // MARK: - Results

    func testResultsAreNewestFirstAndBounded() throws {
        let p = try liveFixture()
        XCTAssertFalse(p.results.isEmpty)
        XCTAssertLessThanOrEqual(p.results.count, TournamentHubPresentation.resultsLimit)
        // The feed serves results OLDEST first. Passing them through unsorted put
        // a qualifying match from nine days earlier at the top of "Latest results".
        XCTAssertEqual(p.results.first?.winnerName, "Alexandra Eala")
    }

    func testARetirementIsLabelledAndNotPrintedAsAScoreline() throws {
        let p = try liveFixture()
        let retired = try XCTUnwrap(
            p.results.first { $0.completionNote == "Retired" },
            "the fixture carries one retirement on purpose")
        XCTAssertNotEqual(retired.completionNote, nil)
        let finals = p.results.filter { $0.completionNote == nil }
        XCTAssertFalse(finals.isEmpty, "an ordinary final carries no completion note")
    }

    // MARK: - Event links: the second channel, and no dead chevrons

    func testFinishedMatchesLinkToAnEventPageWhenTheFeedResolvesThem() throws {
        let p = try liveFixture()
        let linked = p.results.filter { $0.eventId != nil }
        XCTAssertEqual(
            linked.count, 3,
            "the three main-draw finals resolve through `event_links.by_espn`")
        XCTAssertEqual(p.results.first?.eventId, 15300877)

        // And the one that does not resolve degrades rather than linking
        // nowhere: the qualifying retirement's ESPN id has no event row, and
        // `by_espn` reports 96 such ids for this tournament. Asserting the
        // linked count alone would pass just as happily if every row silently
        // lost its link.
        XCTAssertEqual(p.results.filter { $0.eventId == nil }.count, 1)
        XCTAssertNil(p.results.first { $0.completionNote == "Retired" }?.eventId)
    }

    func testLiveMatchesDoNotLinkWhenNothingResolvesThem() throws {
        let p = try liveFixture()
        // Today's slate carries `"event_id": null` and the hub resolves ESPN ids
        // for the finished list only, so no live row is tappable. Asserted rather
        // than assumed: when the server widens that call, this test goes red and
        // says so, instead of the app silently keeping a working link dark.
        XCTAssertTrue(p.liveMatches.allSatisfy { $0.eventId == nil })
    }

    func testAMatchWithAnEspnLinkResolvesThroughByEspn() {
        // The second channel, proven: same slate row, one `by_espn` entry added.
        let p = TournamentHubPresentation(response: decode(Self.linkedSlateJSON))
        XCTAssertEqual(p.liveMatches.first?.eventId, 15300835)
    }

    // MARK: - Boards

    func testBoardsAreRankedTrimmedAndAnnounceTheTrim() throws {
        let p = try liveFixture()
        XCTAssertEqual(p.boards.count, 2)
        let mens = try XCTUnwrap(p.boards.first { $0.id == "mens-singles" })
        XCTAssertEqual(mens.title, "Men's Singles")
        XCTAssertEqual(mens.rows.first?.name, "Carlos Alcaraz")
        XCTAssertLessThanOrEqual(mens.rows.count, TournamentHubPresentation.boardRowLimit)
        XCTAssertEqual(mens.rows.map(\.rank), Array(1...mens.rows.count))
        XCTAssertNil(mens.trimNote, "the fixture carries 5 rows, below the 6-row bound")
    }

    func testBoardMovementBelowAPointIsSuppressedRatherThanRoundedToZero() throws {
        let p = try liveFixture()
        let womens = try XCTUnwrap(p.boards.first { $0.id == "womens-singles" })
        let swiatek = try XCTUnwrap(womens.rows.first { $0.name == "Iga Swiatek" })
        // trend_delta -0.00125 → -0.125pp. "+0" reads as a measured non-move.
        XCTAssertNil(swiatek.deltaPoints)
        let sabalenka = try XCTUnwrap(womens.rows.first { $0.name == "Aryna Sabalenka" })
        XCTAssertEqual(try XCTUnwrap(sabalenka.deltaPoints), 1.425, accuracy: 0.001)
    }

    // MARK: - D27: an empty feed is labelled, not omitted

    func testEveryEmptySectionResolvesToASentence() {
        let p = TournamentHubPresentation(response: decode(Self.emptyJSON))

        XCTAssertTrue(p.liveMatches.isEmpty)
        XCTAssertEqual(p.liveEmptyNote, "No match is being played right now.")
        XCTAssertTrue(p.upcomingMatches.isEmpty)
        XCTAssertEqual(p.upcomingEmptyNote, "Nothing else is scheduled in the order of play.")
        XCTAssertTrue(p.results.isEmpty)
        XCTAssertEqual(p.resultsEmptyNote, "No completed matches yet.")
        XCTAssertTrue(p.boards.isEmpty)
        XCTAssertEqual(p.boardsEmptyNote, "Nobody is priced to win the title yet.")
        XCTAssertEqual(
            p.wholePayloadEmptyNote,
            "The tournament feed returned nothing for this event.")
    }

    func testAPopulatedSectionCarriesNoEmptyNote() throws {
        let p = try liveFixture()
        XCTAssertNil(p.liveEmptyNote)
        XCTAssertNil(p.upcomingEmptyNote)
        XCTAssertNil(p.resultsEmptyNote)
        XCTAssertNil(p.boardsEmptyNote)
        XCTAssertNil(p.wholePayloadEmptyNote)
    }

    func testAnEmptyBracketSaysSoAndAPopulatedOneSaysSomethingElse() throws {
        // Production serves `{"mens-singles": [], "womens-singles": []}` today.
        XCTAssertEqual(
            try liveFixture().bracketNote,
            "No bracket yet — the tournament feed returned an empty draw.")

        let populated = TournamentHubPresentation(response: decode(Self.bracketJSON))
        XCTAssertEqual(
            populated.bracketNote,
            "The feed has a bracket; this screen doesn't draw it yet.")
    }

    // MARK: - Freshness

    func testPriceAgeIsTheServersOwnNumber() {
        // Never a device-clock difference: the copy is pinned without the test
        // branching on what time it runs (gotcha #44).
        XCTAssertEqual(
            TournamentHubPresentation.priceAgeNote(hours: 3.99),
            "Match prices last updated 4 hours ago.")
        XCTAssertEqual(
            TournamentHubPresentation.priceAgeNote(hours: 1.0),
            "Match prices last updated 1 hour ago.")
        XCTAssertEqual(
            TournamentHubPresentation.priceAgeNote(hours: 0.5),
            "Match prices last updated 30 minutes ago.")
        XCTAssertEqual(
            TournamentHubPresentation.priceAgeNote(hours: 0.0001),
            "Match prices updated just now.")
        XCTAssertNil(
            TournamentHubPresentation.priceAgeNote(hours: nil),
            "no reported age is not the same claim as fresh")
    }

    func testTheLivePayloadSurfacesItsFourHourOldPrices() throws {
        XCTAssertEqual(
            try liveFixture().priceAgeNote,
            "Match prices last updated 4 hours ago.",
            "eight matches were being played and the slate's newest observation "
            + "was four hours old; the screen must not hide that")
    }

    // MARK: - Status text

    func testStatusTextPrefersTheScoreboardDetailAndFallsBackHonestly() throws {
        let p = try liveFixture()
        XCTAssertTrue(p.liveMatches.contains { $0.statusText == "4th Set" })
        XCTAssertTrue(
            p.upcomingMatches.contains { $0.statusText == "Time TBD" },
            "a match whose start time is not set says so rather than inventing one")
    }

    // MARK: - Helpers

    private func decode(_ json: String) -> TournamentHubResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        // Force-try: these are literals in this file, and a broken literal is a
        // test bug that must fail loudly rather than degrade into an empty value.
        return try! decoder.decode(TournamentHubResponse.self, from: Data(json.utf8))
    }

    private static let emptyJSON = """
    {"slug": "us-open", "title": "US Open 2026", "subtitle": "Flushing Meadows",
     "slate": {"matches": [], "count": 0},
     "results": {"matches": [], "count": 0},
     "boards": [], "bracket": {}, "event_links": {"by_espn": {}}, "broadcasts": []}
    """

    private static let bracketJSON = """
    {"slug": "us-open", "title": "US Open 2026",
     "slate": {"matches": []}, "results": {"matches": []}, "boards": [],
     "bracket": {"mens-singles": [{"column": 1}, {"column": 2}]},
     "event_links": {"by_espn": {}}, "broadcasts": []}
    """

    private static let linkedSlateJSON = """
    {"slug": "us-open", "title": "US Open 2026",
     "slate": {"matches": [{
        "matchup_key": "espn:182735", "event_id": null, "priced": true,
        "draw_label": "Men's Singles", "round": "R64", "live_state": "in_progress",
        "status_detail": "3rd Set", "start_is_tbd": false,
        "sides": [
          {"entity_key": "a", "display_name": "Tristan Schoolkate", "probability": 0.118812},
          {"entity_key": "b", "display_name": "Flavio Cobolli", "probability": 0.881188}]}]},
     "results": {"matches": []}, "boards": [], "bracket": {},
     "event_links": {"by_espn": {"182735": 15300835}}, "broadcasts": []}
    """

    private static func twoSidedJSON(homeProbability: Double, awayProbability: Double) -> String {
        """
        {"slug": "us-open", "title": "US Open 2026",
         "slate": {"matches": [{
            "matchup_key": "espn:1", "priced": true, "live_state": "in_progress",
            "draw_label": "Men's Singles", "round": "R64",
            "sides": [
              {"entity_key": "a", "display_name": "A", "probability": \(homeProbability)},
              {"entity_key": "b", "display_name": "B", "probability": \(awayProbability)}]}]},
         "results": {"matches": []}, "boards": [], "bracket": {},
         "event_links": {"by_espn": {}}, "broadcasts": []}
        """
    }
}
