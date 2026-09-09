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

    // MARK: - Two sides of one question are decided together (UX-P114 / #2279)

    /// The US Open served `0.845 / 0.155` on 2026-09-04 and this screen printed
    /// "85%" beside "16%". Each side is independently correct — both land on `.5`
    /// and round half-up — and together they are a card claiming 101%. #2279 fixed
    /// six surfaces; this one was written afterwards and never adopted the rule,
    /// which is why the guard is per-surface rather than one shared assertion.
    func testComplementPairPrintsPercentsThatSumToOneHundred() throws {
        let p = TournamentHubPresentation(
            response: decode(Self.twoSidedJSON(homeProbability: 0.845, awayProbability: 0.155)))
        let match = try XCTUnwrap(p.liveMatches.first)
        XCTAssertEqual(
            match.sides.map(\.percentText), ["85%", "15%"],
            "0.845/0.155 renders 85 and 16 when each side is rounded on its own; the "
            + "pair is one decision, and the derived point lands on the underdog")
    }

    /// The same rule over the real payload rather than a chosen pair — a served
    /// half-cent grid puts BOTH sides on `.5` at once, so this is the shape that
    /// reaches a reader, not an invented edge case.
    func testNoPricedDuelInTheLivePayloadPrintsASumOtherThanOneHundred() throws {
        let p = try liveFixture()
        for match in p.liveMatches + p.upcomingMatches where match.noPriceNote == nil {
            guard match.sides.count == 2 else { continue }
            // "<1%" / ">99%" are claims about the value, not integers to add up.
            let percents = match.sides.compactMap { Int($0.percentText.dropLast()) }
            guard percents.count == 2 else { continue }
            XCTAssertEqual(
                percents.reduce(0, +), 100,
                "\(match.sides.map(\.name).joined(separator: " v ")) prints "
                + "\(match.sides.map(\.percentText).joined(separator: " + "))")
        }
    }

    /// The contract pins the other direction as hard: a field that is not a duel
    /// must render exactly as it did before. A title board is a multi-way field
    /// whose contenders do not complement, and normalising it would invent prices.
    func testTitleBoardRowsAreNotPutThroughTheDuelRule() throws {
        let p = try liveFixture()
        let board = try XCTUnwrap(p.boards.first)
        let percents = board.rows.compactMap { Int($0.percentText.dropLast()) }
        XCTAssertGreaterThan(percents.count, 1, "the fixture's board carries priced rows")
        XCTAssertNotEqual(
            percents.reduce(0, +), 100,
            "a trimmed multi-way board summing to exactly 100 would mean the duel "
            + "rule reached rows that are not two sides of one question")
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

    // MARK: - #4142: a finished row says what the market made each side

    /// The denominator is asserted, not just the hits.
    ///
    /// "Some rows carry a prior" passes just as happily on a payload where one
    /// row does and nine do not. The fixture is four results of which exactly
    /// three were priced before play and one — the qualifying retirement — was
    /// not, so the test states 3 AND states 1, and a regression that drops
    /// priors moves one of the two numbers.
    func testAFinishedRowCarriesWhatTheMarketMadeEachSide() throws {
        let p = try liveFixture()
        XCTAssertEqual(p.results.count, 4, "the fixture's eligible denominator")

        let priced = p.results.filter { $0.winnerPrematchText != nil }
        XCTAssertEqual(
            priced.count, 3,
            "three main-draw results carry a prior on both sides in the fixture")
        XCTAssertEqual(
            p.results.filter { $0.winnerPrematchText == nil }.count, 1,
            "and the qualifying retirement carries none — the control")

        // The exact strings, because "not nil" would survive rendering the
        // loser's number against the winner's name.
        let eala = try XCTUnwrap(p.results.first { $0.winnerName == "Alexandra Eala" })
        XCTAssertEqual(eala.winnerPrematchText, "86%")
        XCTAssertEqual(eala.loserPrematchText, "14%")

        // And the underdog case Alex asked for: a winner the market had behind.
        let fritz = try XCTUnwrap(p.results.first { $0.winnerName == "Taylor Fritz" })
        XCTAssertEqual(fritz.winnerPrematchText, "86%")
        XCTAssertEqual(fritz.loserPrematchText, "14%")
    }

    /// A prior we do not have prints NOTHING — not an em-dash.
    ///
    /// `formatProbabilityOrDash` is the reflex on this surface and it is the
    /// wrong reflex here: an em-dash trailing a player's name on a finished row
    /// reads as a statement about the match. Notice 34 says leave the space
    /// empty and do not explain it, so the field is `nil` and the view omits
    /// the element.
    func testAnAbsentPriorPrintsNothingRatherThanADash() throws {
        let p = try liveFixture()
        let unpriced = try XCTUnwrap(
            p.results.first { $0.completionNote == "Retired" },
            "the qualifying retirement is the fixture's unpriced row")
        XCTAssertNil(unpriced.winnerPrematchText)
        XCTAssertNil(unpriced.loserPrematchText)
        XCTAssertNotEqual(unpriced.winnerPrematchText, absentProbabilityMarker)
    }

    /// The pair is rounded ONCE, together — a finished row cannot print 101.
    ///
    /// Every priced pair in the fixture happens to round cleanly, so asserting
    /// this on the fixture alone would pass without the rule existing. 0.505 /
    /// 0.495 is the case that separates them: rounded independently they are
    /// 51 and 50.
    func testThePrematchPairIsRoundedTogetherSoAFinishedRowCannotPrint101() {
        let p = TournamentHubPresentation(
            response: decode(Self.pricedResultJSON(winner: 0.505, loser: 0.495)))
        let row = p.results.first
        XCTAssertEqual(row?.winnerPrematchText, "51%")
        XCTAssertEqual(
            row?.loserPrematchText, "49%",
            "rounded on its own 0.495 prints 50, and 51 + 50 is the 101 this rule exists to stop")
    }

    // MARK: - #4134: `Next up` says WHICH DAY, not just a clock time

    /// The bug: three upcoming rows read "7:20 PM · 8:30 AM · 9:30 AM" and two
    /// of them were the next day.
    ///
    /// `now` is injected rather than read, so this asserts the branches instead
    /// of asserting whatever today happens to be (gotcha #44).
    func testNextUpNamesTheDayWhenAStartIsNotToday() throws {
        // ONE calendar for both halves. The day comparison and the strings are
        // not independent: `startTimeText` decides "is this today" with the
        // calendar it is handed, while the formatters render in the device's
        // zone. Handing it a zone the formatters do not share makes the two
        // disagree near midnight — which is a bug in a test that forces it, and
        // the reason production passes `.current`.
        let calendar = Calendar.current

        // Offset FIRST from a fixed anchor, then set the clock (gotcha #44):
        // an anchor that branches on today's date is not fixed.
        let anchor = try XCTUnwrap(calendar.date(from: DateComponents(
            timeZone: calendar.timeZone, year: 2026, month: 9, day: 8,
            hour: 19, minute: 0)))
        func at(dayOffset: Int, _ hour: Int, _ minute: Int) throws -> Date {
            let day = try XCTUnwrap(calendar.date(byAdding: .day, value: dayOffset, to: anchor))
            return try XCTUnwrap(calendar.date(
                bySettingHour: hour, minute: minute, second: 0, of: day))
        }
        func text(_ date: Date) -> String {
            TournamentHubPresentation.startTimeText(for: date, now: anchor, calendar: calendar)
        }

        // Today keeps the bare clock — the day is only worth a reader's
        // attention when it is not the one they are standing in.
        let todayLate = try at(dayOffset: 0, 21, 30)
        XCTAssertEqual(
            text(todayLate), startTimeFormatterTestMirror(todayLate),
            "a start later today is still just a time")

        let tomorrowMorning = try at(dayOffset: 1, 8, 30)
        XCTAssertTrue(
            text(tomorrowMorning).hasPrefix("Tomorrow "),
            "the 8:30 AM row that reads as this morning is tomorrow morning")
        XCTAssertTrue(
            text(tomorrowMorning).hasSuffix(startTimeFormatterTestMirror(tomorrowMorning)),
            "naming the day must not cost the time")

        // Later in the week: a weekday, which is shorter than a date and still
        // unambiguous inside seven days. Asserted against Foundation's own
        // symbol table rather than against the formatter under test, so this
        // cannot pass by agreeing with itself.
        let friday = try at(dayOffset: 3, 8, 30)
        let symbol = calendar.shortWeekdaySymbols[calendar.component(.weekday, from: friday) - 1]
        let fridayText = text(friday)
        XCTAssertTrue(fridayText.contains(symbol), "expected \(symbol) in \(fridayText)")
        XCTAssertFalse(fridayText.contains("Tomorrow"))

        // Past seven days a weekday would wrap around and start lying, so the
        // date has to appear instead.
        let far = try at(dayOffset: 12, 8, 30)
        let farText = text(far)
        XCTAssertFalse(farText.contains("Tomorrow"))
        XCTAssertFalse(
            farText.contains(
                calendar.shortWeekdaySymbols[calendar.component(.weekday, from: far) - 1]),
            "twelve days out is a date, not a weekday: \(farText)")
        XCTAssertTrue(farText.hasSuffix(startTimeFormatterTestMirror(far)))
    }

    /// The bare clock, formatted the way the row's time half is.
    ///
    /// Deliberately a local mirror and not a hook into the production
    /// formatter: these assertions are about the DAY the string names, and
    /// reaching into the file's private formatter would make the time half
    /// agree with itself by construction.
    private func startTimeFormatterTestMirror(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateStyle = .none
        f.timeStyle = .short
        return f.string(from: date)
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

    /// One finished match, both sides priced — for the pair-rounding rule the
    /// production fixture cannot exercise.
    private static func pricedResultJSON(winner: Double, loser: Double) -> String {
        """
        {"slug": "us-open", "title": "US Open 2026",
         "slate": {"matches": []},
         "results": {"matches": [{
            "matchup_key": "espn:1", "draw_label": "Men's Singles", "round": "R64",
            "winner_entity_key": "w", "score": "7-6, 7-6", "completion": "final",
            "completed_at": "2026-09-08T20:00:00Z",
            "players": [
              {"entity_key": "w", "display_name": "W", "is_winner": true,
               "prematch_probability": \(winner)},
              {"entity_key": "l", "display_name": "L", "is_winner": false,
               "prematch_probability": \(loser)}]}]},
         "boards": [], "bracket": {},
         "event_links": {"by_espn": {}}, "broadcasts": []}
        """
    }

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
