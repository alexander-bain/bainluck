import XCTest
@testable import Bain_Luck

/// #10830 — the iPhone event page's compact market design (the native slice of
/// #10809): one browser for maps, player props, game questions and the related
/// season markets, plus the aligned season table.
///
/// The promise every test here holds is REACHABILITY WITHOUT INVENTION: the
/// browser only decides which slice of a complete collection is on screen, it
/// never drops a row, never merges two markets into one price, and never prints
/// a number a venue did not quote.
final class CompactEventMarkets10830Tests: XCTestCase {

    // MARK: - The browse rule

    func testFamiliesKeepTheCallersOrderAndAppearOnce() {
        XCTAssertEqual(
            MarketBrowserLogic.groups(["Rushing", "Receiving", "Rushing", "Passing", "Receiving"]),
            ["Rushing", "Receiving", "Passing"]
        )
    }

    func testAVanishedChoiceFallsBackToTheFirstFamily() {
        XCTAssertEqual(MarketBrowserLogic.activeGroup(selected: "Passing", groups: ["A", "Passing"]), "Passing")
        XCTAssertEqual(MarketBrowserLogic.activeGroup(selected: "Gone", groups: ["A", "B"]), "A")
        XCTAssertNil(MarketBrowserLogic.activeGroup(selected: nil, groups: []))
    }

    func testWithNoQueryTheWindowIsTheActiveFamily() {
        let groups = ["A", "B", "A", "B"]
        let texts = ["one", "two", "three", "four"]
        XCTAssertEqual(MarketBrowserLogic.matchingIndices(
            groupNames: groups, searchTexts: texts, query: "  ", selected: "B"), [1, 3])
        XCTAssertEqual(MarketBrowserLogic.matchingIndices(
            groupNames: groups, searchTexts: texts, query: "", selected: nil), [0, 2])
    }

    /// A search crosses every family, every term must match, and case and
    /// accents do not matter.
    func testASearchCrossesFamiliesAndNarrowsByEveryTerm() {
        let groups = ["Rushing Yards", "Receiving Yards", "Touchdowns"]
        let texts = ["Ashton Jeanty Rushing Yards", "Brock Bowers Receiving Yards", "Ashton Jeanty Touchdowns"]
        XCTAssertEqual(MarketBrowserLogic.matchingIndices(
            groupNames: groups, searchTexts: texts, query: "JEANTY", selected: "Receiving Yards"), [0, 2])
        XCTAssertEqual(MarketBrowserLogic.matchingIndices(
            groupNames: groups, searchTexts: texts, query: "jeanty touch", selected: nil), [2])
        XCTAssertEqual(MarketBrowserLogic.matchingIndices(
            groupNames: ["Goals"], searchTexts: ["Kylian Mbappé goals"], query: "mbappe", selected: nil), [0])
        XCTAssertEqual(MarketBrowserLogic.matchingIndices(
            groupNames: groups, searchTexts: texts, query: "nobody", selected: nil), [])
    }

    /// STRESS: 1,120 rows over eight families. Every row is reachable by its
    /// family and the window walks a family to its last row a page at a time.
    func testEveryRowOfAThousandRowCollectionIsReachable() {
        let families = (0..<8).map { "Family \($0)" }
        let groups = (0..<1_120).map { families[$0 % 8] }
        let texts = (0..<1_120).map { "Player \($0) \(groups[$0])" }

        var reached = Set<Int>()
        for family in families {
            let matches = MarketBrowserLogic.matchingIndices(
                groupNames: groups, searchTexts: texts, query: "", selected: family)
            XCTAssertEqual(matches.count, 140)
            var limit = MarketBrowserLogic.pageSize
            XCTAssertEqual(matches.prefix(limit).count, 12, "the first window is bounded")
            while limit < matches.count {
                limit = MarketBrowserLogic.nextLimit(current: limit, matchCount: matches.count)
            }
            reached.formUnion(matches.prefix(limit))
            XCTAssertEqual(MarketBrowserLogic.windowStatus(limit: limit, matchCount: matches.count), "140 of 140")
            XCTAssertEqual(MarketBrowserLogic.nextLimit(current: limit, matchCount: matches.count), 12,
                           "the full window collapses back to one page")
        }
        XCTAssertEqual(reached.count, 1_120)

        XCTAssertEqual(MarketBrowserLogic.matchingIndices(
            groupNames: groups, searchTexts: texts, query: "player 1119", selected: "Family 0"), [1_119])
    }

    /// A searchable collection that fits in one window is drawn whole, with no
    /// browse chrome; a tabbed list (the maps) always shows one at a time.
    func testOnlyACollectionLongerThanAWindowGetsBrowseChrome() {
        XCTAssertFalse(MarketBrowserLogic.browses(itemCount: 3, searchable: true))
        XCTAssertFalse(MarketBrowserLogic.browses(itemCount: 12, searchable: true))
        XCTAssertTrue(MarketBrowserLogic.browses(itemCount: 13, searchable: true))
        XCTAssertTrue(MarketBrowserLogic.browses(itemCount: 2, searchable: false))
        XCTAssertTrue(MarketBrowserLogic.browses(itemCount: 9, pageSize: 8, searchable: true))
    }

    func testTheWindowStatusNeverOverstatesTheMatches() {
        XCTAssertEqual(MarketBrowserLogic.windowStatus(limit: 12, matchCount: 77), "12 of 77")
        XCTAssertEqual(MarketBrowserLogic.windowStatus(limit: 24, matchCount: 15), "15 of 15")
    }

    // MARK: - Player props families

    /// The production 14782161 stat names (Oct 10), through the card's own
    /// label rule, land in the families a reader expects. Lines collapse; the
    /// contract words do not.
    func testFamiliesDropTheLineAndKeepTheContract() {
        XCTAssertEqual(PlayerPropsFamily.name(statLabel: "2+ Touchdowns"), "Touchdowns")
        XCTAssertEqual(PlayerPropsFamily.name(statLabel: "Passing Touchdowns O/U 2.5"), "Passing Touchdowns")
        XCTAssertEqual(PlayerPropsFamily.name(statLabel: "Passing Yards O/U 299.5"), "Passing Yards")
        XCTAssertEqual(PlayerPropsFamily.name(statLabel: "Receiving Yards"), "Receiving Yards")
        XCTAssertEqual(PlayerPropsFamily.name(statLabel: "Receiving Yards (Protected)"), "Receiving Yards (Protected)")
        XCTAssertEqual(PlayerPropsFamily.name(statLabel: "Rushing Yards Ladder"), "Rushing Yards Ladder")
        XCTAssertEqual(PlayerPropsFamily.name(statLabel: "Rushing Yards Escalator"), "Rushing Yards Escalator")
        // Never empty: a label that is only a line is kept whole.
        XCTAssertEqual(PlayerPropsFamily.name(statLabel: "2+ "), "2+")
    }

    func testAnUnpricedLadderIsFiledLastWhateverItsStat() {
        XCTAssertEqual(PlayerPropsFamily.family(statLabel: "Touchdowns", isPriced: false),
                       PlayerPropsFamily.unpricedFamily)
        let order = PlayerPropsFamily.orderedFamilies([
            PlayerPropsFamily.unpricedFamily, PlayerPropsFamily.unpricedFamily, PlayerPropsFamily.unpricedFamily,
            "Rushing Yards", "Touchdowns", "Touchdowns", "Receiving Yards", "Receiving Yards",
        ])
        XCTAssertEqual(order, ["Receiving Yards", "Touchdowns", "Rushing Yards", PlayerPropsFamily.unpricedFamily],
                       "most-quoted first, ties by name, unpriced last even when it is the largest")
    }

    /// The opening target is a QUOTED rung, nearest even odds; an unpriced
    /// rung is never chosen, and no priced rung means nothing is chosen.
    func testTheDefaultTargetIsAQuotedRungNearestEvenOdds() {
        XCTAssertEqual(PlayerPropsFamily.defaultTarget(probabilities: [0.9, 0.62, 0.41, 0.2]), 2)
        XCTAssertEqual(PlayerPropsFamily.defaultTarget(probabilities: [0.75, 0.25]), 0, "a tie goes to the lower line")
        XCTAssertEqual(PlayerPropsFamily.defaultTarget(probabilities: [nil, 0.8, nil]), 1)
        XCTAssertNil(PlayerPropsFamily.defaultTarget(probabilities: [nil, nil]))
        XCTAssertNil(PlayerPropsFamily.defaultTarget(probabilities: []))
    }

    func testATargetChipNeverRoundsIntoADifferentLine() {
        XCTAssertEqual(PlayerPropsFamily.targetLabel(2), "2+")
        XCTAssertEqual(PlayerPropsFamily.targetLabel(2.5), "2.5+")
        XCTAssertEqual(PlayerPropsFamily.targetLabel(299.5), "299.5+")
    }

    // MARK: - Related markets catalog

    private func future(
        market: Int, outcome: Int, name: String = "Market", outcomeName: String = "Outcome",
        category: String?, probability: Double? = 0.4
    ) throws -> RelatedFuture {
        var body: [String: Any] = [
            "market_id": market, "market_name": name, "outcome_id": outcome, "outcome_name": outcomeName,
        ]
        if let category { body["display_category"] = category }
        if let probability { body["probability"] = probability }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(RelatedFuture.self, from: JSONSerialization.data(withJSONObject: body))
    }

    /// The game's own rows are browsed on the game's sections; everything
    /// else served is here once, including the `championship` rows
    /// `categorizeFutures` drops.
    func testTheCatalogHoldsEverySeasonRowOnce() throws {
        let home = [
            try future(market: 1, outcome: 10, category: "playoff_path"),
            try future(market: 2, outcome: 20, category: "game_prop"),
            try future(market: 3, outcome: 30, category: "championship"),
            try future(market: 4, outcome: 40, category: "award"),
            try future(market: 9, outcome: 90, category: "other"),
        ]
        let away = [
            try future(market: 1, outcome: 10, category: "playoff_path"), // the same leg filed under both
            try future(market: 1, outcome: 11, category: "playoff_path"),
            try future(market: 5, outcome: 50, category: nil),
        ]
        let rows = RelatedMarketsCatalog.rows(home: home, away: away)

        XCTAssertEqual(rows.map(\.id), ["1-10", "1-11", "4-40", "3-30", "5-50"])
        XCTAssertEqual(rows.map(\.family),
                       ["Season outcomes", "Season outcomes", "Awards", "More questions", "More questions"])
    }

    /// A row the server did not classify stays a link: no number we vouch for.
    /// A classified row with no price prints none either.
    func testOnlyAClassifiedPricedRowPrintsAPrice() throws {
        XCTAssertTrue(RelatedMarketsCatalog.Row(
            id: "a", future: try future(market: 1, outcome: 1, category: "award"), family: "Awards").printsPrice)
        XCTAssertFalse(RelatedMarketsCatalog.Row(
            id: "b", future: try future(market: 1, outcome: 2, category: nil), family: "More questions").printsPrice)
        XCTAssertFalse(RelatedMarketsCatalog.Row(
            id: "c", future: try future(market: 1, outcome: 3, category: "award", probability: nil),
            family: "Awards").printsPrice)
    }

    func testTheCatalogIsSearchableByPlayerAndMarket() throws {
        let row = RelatedMarketsCatalog.Row(
            id: "x", future: try future(market: 1, outcome: 1, name: "MVP Winner?", outcomeName: "Ashton Jeanty",
                                       category: "award"),
            family: "Awards")
        let text = RelatedMarketsCatalog.searchText(row)
        XCTAssertTrue(text.contains("Ashton Jeanty"))
        XCTAssertTrue(text.contains("MVP"))
    }

    // MARK: - Game question cards

    /// A card's outcomes are bounded: the five likeliest closed, every one
    /// open, in the card's own order — no row is dropped, and the closed card
    /// still leads with the likeliest answer. Shape: 14782161's "1st Las Vegas
    /// Touchdown" (15 outcomes, Oct 10).
    func testACardShowsItsLikeliestOutcomesAndOpensToAll() {
        let names = ["No Touchdown", "Ashton Jeanty", "Mike Washington Jr.", "Brock Bowers", "Tre Tucker",
                     "Michael Mayer", "Cody White", "Malik Benson", "Connor Heyward", "Dylan Laube",
                     "Kirk Cousins", "Dareke Young", "LV Raiders D/ST", "Tyler Lockett", "Jakobi Meyers"]
        let rows = names.enumerated().map { i, name in
            GameMarketOther(marketName: "Las Vegas vs New England: 1st Las Vegas Touchdown",
                            outcomeName: name, probability: 0.37 - Double(i) * 0.02,
                            source: "kalshi", observedAt: nil)
        }
        let view = SpecialEventMarketsView(markets: rows, eventStatus: "scheduled", commenceTime: nil)
        let card = try? XCTUnwrap(view.categories.first?.items.first)
        let sorted = view.sortedOutcomes(card?.outcomes ?? [])

        let closed = SpecialEventMarketsView.displayedOutcomes(sorted, expanded: false)
        XCTAssertEqual(closed.map(\.label), Array(names.prefix(5)))
        XCTAssertEqual(SpecialEventMarketsView.displayedOutcomes(sorted, expanded: true).count, 15)
    }

    // MARK: - Season comparison

    private func stage(_ key: String, _ label: String, _ p: Double?) throws -> ProgressionStageData {
        var body: [String: Any] = ["key": key, "label": label]
        if let p { body["probability"] = p }
        return try JSONDecoder().decode(ProgressionStageData.self, from: JSONSerialization.data(withJSONObject: body))
    }

    /// One row per stage KEY across both teams, in the away team's order, with
    /// an empty cell where a team has no such stage — never borrowed.
    func testTheSeasonTableAlignsStagesByKey() throws {
        let away = [try stage("make_playoffs", "Make Playoffs", 0.38), try stage("division", "Division", 0.09)]
        let home = [try stage("division", "Division", 0.28), try stage("make_playoffs", "Make Playoffs", 0.63),
                    try stage("championship", "Super Bowl", 0.03)]
        let rows = SeasonComparisonView.rows(away: away, home: home)

        XCTAssertEqual(rows.map(\.id), ["make_playoffs", "division", "championship"])
        XCTAssertEqual(rows[0].away?.probability, 0.38)
        XCTAssertEqual(rows[0].home?.probability, 0.63)
        XCTAssertNil(rows[2].away, "a stage the away team lacks stays empty for it")
        XCTAssertEqual(rows[2].label, "Super Bowl")
    }

    // MARK: - Game question families

    private func question(_ label: String, kind: QuestionMatrixKind = .namedOptions) -> EventQuestionMatrixAdapter.Row {
        EventQuestionMatrixAdapter.Row(
            id: .init(scope: .game, questionKey: label), kind: kind, label: label, quantity: nil, period: nil,
            subject: nil, predicate: nil, lifecycle: nil, options: [], missingOptions: [],
            offersMoreOptions: false, complete: nil, optionCounts: nil, sourceTotals: [])
    }

    /// The production 14782161 question labels (Oct 10) browse under the
    /// families a reader expects; an unrecognised one is not guessed.
    func testGameQuestionsBrowseByFamily() {
        let family = EventQuestionMatrixSection10238.family
        XCTAssertEqual(family(question("24+ points", kind: .countThreshold)), "Totals")
        XCTAssertEqual(family(question("Raiders vs. Patriots: 1Q O/U 7.5")), "Totals")
        XCTAssertEqual(family(question("LV Raiders vs NE Patriots: 1st Half Total")), "Totals")
        XCTAssertEqual(family(question("Spread: Patriots (-3.5)")), "Spreads")
        XCTAssertEqual(family(question("1H Spread: Patriots (-1.5)")), "Spreads")
        XCTAssertEqual(family(question("Raiders Team Total: O/U 20.5")), "Team totals")
        XCTAssertEqual(family(question("LV Raiders vs NE Patriots: Team Total")), "Team totals")
        XCTAssertEqual(family(question("Raiders vs. Patriots: 1H Moneyline")), "Winners")
        XCTAssertEqual(family(question("LV Raiders vs NE Patriots: 1st Quarter Winner")), "Winners")
        XCTAssertEqual(family(question("Both teams to score")), "More questions")
    }

    /// STRESS: 1,200 served questions are all reachable through the section's
    /// own families and page size.
    func testEveryQuestionOfALargeMatrixIsReachable() {
        let labels = (0..<1_200).map { i -> String in
            switch i % 4 {
            case 0: return "Spread: Team \(i) (-\(i % 20).5)"
            case 1: return "Team \(i) Team Total: O/U \(i % 30).5"
            case 2: return "Quarter \(i) Winner"
            default: return "Novelty \(i)"
            }
        }
        let rows = labels.map { question($0) }
        let groups = rows.map(EventQuestionMatrixSection10238.family)
        let texts = rows.map(EventQuestionMatrixSection10238.searchText)

        var reached = Set<Int>()
        for family in MarketBrowserLogic.groups(groups) {
            let matches = MarketBrowserLogic.matchingIndices(
                groupNames: groups, searchTexts: texts, query: "", selected: family)
            var limit = EventQuestionMatrixSection10238.pageSize
            while limit < matches.count {
                limit = MarketBrowserLogic.nextLimit(
                    current: limit, matchCount: matches.count, pageSize: EventQuestionMatrixSection10238.pageSize)
            }
            reached.formUnion(matches.prefix(limit))
        }
        XCTAssertEqual(reached.count, 1_200)
    }

    // MARK: - Game question focus (#10830)

    private func question(_ key: String, options optionKeys: [String]) -> EventQuestionMatrixAdapter.Row {
        EventQuestionMatrixAdapter.Row(
            id: .init(scope: .game, questionKey: key), kind: .namedOptions, label: key, quantity: nil,
            period: nil, subject: nil, predicate: nil, lifecycle: nil,
            options: optionKeys.map {
                EventQuestionMatrixAdapter.Option(
                    selection: QuestionMatrixSelection(scope: .game, questionKey: key, optionKey: $0),
                    label: $0, side: nil, value: .quoted(0.5), observedAt: nil, basis: nil, result: nil)
            },
            missingOptions: [], offersMoreOptions: false, complete: nil, optionCounts: nil, sourceTotals: [])
    }

    /// Focus returns to the exact option only while its question is both in the
    /// latest payload and drawn by the browser; otherwise to the heading.
    func testFocusReturnsOnlyToAnOptionTheBrowserStillDraws() {
        let rows = [question("m:1", options: ["o:1", "o:2"]), question("m:2", options: ["o:3"])]
        let pick = QuestionMatrixSelection(scope: .game, questionKey: "m:2", optionKey: "o:3")
        let target = EventQuestionMatrixSection10238.focusReturnTarget

        XCTAssertEqual(target(pick, rows, [rows[0].id, rows[1].id]), pick)
        // A refresh moved m:2 to another family or past the window.
        XCTAssertNil(target(pick, rows, [rows[0].id]))
        // Withdrawn from the latest payload, even if the id was on screen.
        XCTAssertNil(target(pick, [rows[0]], [rows[0].id, rows[1].id]))
        // A different option of a visible question is not substituted.
        XCTAssertNil(target(
            QuestionMatrixSelection(scope: .game, questionKey: "m:2", optionKey: "o:9"),
            rows, [rows[0].id, rows[1].id]))
        XCTAssertNil(target(nil, rows, [rows[0].id, rows[1].id]))
    }

    /// A question's last page and a search both reach its one row in a large
    /// typed matrix, and the browse window never hands back a row twice.
    func testSearchReachesTheLastQuestionOfALargeMatrix() {
        let rows = (0..<240).map { question("Spread: Team \($0) (-\($0 % 9).5)") }
        let groups = rows.map(EventQuestionMatrixSection10238.family)
        let texts = rows.map(EventQuestionMatrixSection10238.searchText)
        XCTAssertEqual(MarketBrowserLogic.matchingIndices(
            groupNames: groups, searchTexts: texts, query: "team 239", selected: nil), [239])
        let all = MarketBrowserLogic.matchingIndices(
            groupNames: groups, searchTexts: texts, query: "", selected: "Spreads")
        XCTAssertEqual(all.count, 240)
        XCTAssertEqual(Set(all).count, 240)
        XCTAssertEqual(all.last, 239)
    }

    // MARK: - Period maps (#10830 review)

    /// A first half that is over says so on its own map while the game is
    /// still live; the second half, still in play, keeps its distribution.
    func testAFinishedFirstHalfIsOverWhileTheGameIsLive() {
        let live = HalfScores.Pair(
            first: HalfScoreSplit(home: 14, away: 10),
            second: HalfScoreSplit(home: 3, away: 0),
            secondIsComplete: false
        )
        XCTAssertTrue(MarketMapRail.halfMapIsOver(gameIsDone: false, halfIsComplete: live.isComplete(.first)))
        XCTAssertFalse(MarketMapRail.halfMapIsOver(gameIsDone: false, halfIsComplete: live.isComplete(.second)))
        // The game's final ends every half, with or without a halftime reading.
        XCTAssertTrue(MarketMapRail.halfMapIsOver(gameIsDone: true, halfIsComplete: false))
    }

    /// A half grades only against its OWN finished score — never a half in
    /// play, never a scoreboard that does not count the map's unit, and never
    /// the whole game's final split into halves.
    func testAHalfGradesOnlyAgainstItsOwnFinishedScore() {
        let first = HalfScoreSplit(home: 14, away: 10)
        XCTAssertEqual(MarketMapRail.halfSettledScore(
            halfIsComplete: true, scoreboardCountsTheUnit: true, played: first), first)
        XCTAssertNil(MarketMapRail.halfSettledScore(
            halfIsComplete: false, scoreboardCountsTheUnit: true, played: HalfScoreSplit(home: 3, away: 0)))
        XCTAssertNil(MarketMapRail.halfSettledScore(
            halfIsComplete: true, scoreboardCountsTheUnit: false, played: first))
        XCTAssertNil(MarketMapRail.halfSettledScore(
            halfIsComplete: true, scoreboardCountsTheUnit: true, played: nil))

        // Home won the half by 4: home +3.5 HIT, home +4.5 MISS, away +3.5 MISS.
        let home = MarketMapRail.sideFinalMargin(gameMargin: first.margin, isHome: true)
        let away = MarketMapRail.sideFinalMargin(gameMargin: first.margin, isHome: false)
        XCTAssertEqual(MarketMapRail.totalLadderResult(threshold: 3.5, finalTotal: home), .over)
        XCTAssertEqual(MarketMapRail.totalLadderResult(threshold: 4.5, finalTotal: home), .under)
        XCTAssertEqual(MarketMapRail.totalLadderResult(threshold: 3.5, finalTotal: away), .under)
    }

    /// Every quoted half-total line is reachable behind "All N lines"; the
    /// default window is the short one, and after the half it is the lines the
    /// half's total decided.
    func testEveryHalfTotalLineIsReachable() {
        let lines: [Double] = (0..<11).map { 17.5 + Double($0) * 2 }
        let names = lines.map { "Over: 1H \($0)" } + lines.map { "Under: 1H \($0)" }
        let thresholds: [Double?] = lines + lines
        let overs: [Double?] = lines.enumerated().map { 0.95 - Double($0.offset) * 0.08 } + lines.map { _ in nil }

        let full = MarketMapRail.fullTotalRungs(outcomeNames: names, thresholds: thresholds)
        XCTAssertEqual(full.map(\.threshold), lines)

        let pre = MarketMapRail.drawnFullTotalRungs(
            outcomeNames: names, thresholds: thresholds, overProbabilities: overs,
            settledTotal: nil, limit: MarketMapRail.halfMapLadderLimit)
        XCTAssertEqual(pre.count, MarketMapRail.halfMapLadderLimit)
        XCTAssertLessThan(pre.count, full.count)

        let settled = MarketMapRail.drawnFullTotalRungs(
            outcomeNames: names, thresholds: thresholds, overProbabilities: overs,
            settledTotal: 24, limit: MarketMapRail.halfMapLadderLimit)
        let results = settled.map { MarketMapRail.totalLadderResult(threshold: $0.threshold, finalTotal: 24) }
        XCTAssertTrue(results.contains(.over) && results.contains(.under),
                      "the settled window straddles the half's own total: \(settled.map(\.threshold))")
    }
}
