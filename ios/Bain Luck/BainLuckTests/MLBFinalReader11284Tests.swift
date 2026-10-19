import XCTest
@testable import Bain_Luck

/// #11284 — the final MLB page's stories: eligibility, the five slots built
/// from existing deliveries, and the truth limits the handoff names
/// (`mlb-final-production-handoff-20261019`, HANDOFF.md + ACCEPTANCE.md).
///
/// FIXTURES, AND WHAT EACH ONE IS:
/// - `event-15321836-game-markets-11284-mlb-final.20260930.json` and
///   `event-15321836-related-11284-mlb-final.20260930.json` are the retained
///   captured originals of the design specimen (Houston Astros 3–7 Chicago
///   White Sox, final), byte-for-byte `atlas-v6/raw/mlb-15321836-*.json`
///   (sha256 42dfb489… and b844152f…, pinned in the handoff's
///   REFERENCE-INPUTS.json). CAPTURED HISTORICAL DATA: its typed After
///   actuals are all `unknown`, so this capture shows no official final.
/// - `game-markets-10237-after.route.json` is the EXISTING 10237 route
///   fixture (Ben Rice, an ESPN final of 2 home runs).
/// Cases that need another state edit one value of a body and say so: those
/// are CONSTRUCTED MUTATIONS, never claimed as observed data.
@MainActor
final class MLBFinalReader11284Tests: XCTestCase {
    private static let fixtures = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appendingPathComponent("Fixtures")
    private static let capturedMarkets = "event-15321836-game-markets-11284-mlb-final.20260930.json"
    private static let capturedRelated = "event-15321836-related-11284-mlb-final.20260930.json"
    private static let routeMarkets = "game-markets-10237-after.route.json"

    // MARK: - Helpers

    private func object(_ name: String) throws -> [String: Any] {
        let data = try Data(contentsOf: Self.fixtures.appendingPathComponent(name))
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private func decode<T: Decodable>(_ type: T.Type, _ dict: [String: Any]) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func deck(
        markets: [String: Any]?, related: [String: Any]?, status: String? = "completed",
        sport: String? = "baseball_mlb", eventID: Int = 15321836, home: Int? = 3, away: Int? = 7
    ) throws -> [MLBFinalCard11284] {
        MLBFinalDeck11284.cards(MLBFinalDeckInput11284(
            eventID: eventID, sportKey: sport, status: status,
            homeTeam: "Houston Astros", awayTeam: "Chicago White Sox",
            homeScore: home, awayScore: away,
            gameMarkets: try markets.map { try decode(GameMarketsResponse.self, $0) },
            relatedFutures: try related.map { try decode(RelatedFuturesResponse.self, $0) }))
    }

    private func captured() throws -> [MLBFinalCard11284] {
        try deck(markets: object(Self.capturedMarkets), related: object(Self.capturedRelated))
    }

    private func homeRuns(_ cards: [MLBFinalCard11284]) -> MLBHomeRunCard11284? {
        for case .homeRuns(let card) in cards { return card }
        return nil
    }

    private func strikeouts(_ cards: [MLBFinalCard11284]) -> MLBMilestoneCard11284? {
        for case .strikeouts(let card) in cards { return card }
        return nil
    }

    private func totals(_ cards: [MLBFinalCard11284]) -> MLBTotalsCard11284? {
        for case .totals(let card) in cards { return card }
        return nil
    }

    private func series(_ cards: [MLBFinalCard11284]) -> MLBSeriesCard11284? {
        for case .series(let card) in cards { return card }
        return nil
    }

    private func extra(_ cards: [MLBFinalCard11284]) -> MLBExtraInningsCard11284? {
        for case .extraInnings(let card) in cards { return card }
        return nil
    }

    private func fields(_ original: MLBOriginal11284) -> [MLBOriginal11284.Field] {
        original.sections.flatMap(\.fields)
    }

    private func value(_ label: String, in original: MLBOriginal11284) -> [String] {
        fields(original).filter { $0.label == label }.map(\.value)
    }

    /// Edits one typed After actual of a game-markets body, by its key.
    private func editingActual(_ body: [String: Any], key: String,
                               _ change: (inout [String: Any]) -> Void) throws -> [String: Any] {
        var body = body
        var after = try XCTUnwrap(body["after_player_props"] as? [String: Any])
        var actuals = try XCTUnwrap(after["actuals"] as? [[String: Any]])
        let index = try XCTUnwrap(actuals.firstIndex { $0["actual_key"] as? String == key }, "actual \(key)")
        change(&actuals[index])
        after["actuals"] = actuals
        body["after_player_props"] = after
        return body
    }

    // MARK: - Eligibility

    func testOnlyAFinishedMLBGameIsEligibleByItsStatusNeverItsDate() {
        XCTAssertTrue(MLBFinalPage11284.applies(sportKey: "baseball_mlb", status: "completed"))
        XCTAssertTrue(MLBFinalPage11284.applies(sportKey: "baseball_mlb", status: "closed"))
        for status in ["live", "scheduled", "suspended", "postponed", "cancelled", "unknown", "", nil] as [String?] {
            XCTAssertFalse(MLBFinalPage11284.applies(sportKey: "baseball_mlb", status: status),
                           "status \(status ?? "nil") must keep the existing MLB route")
        }
        for sport in ["americanfootball_nfl", "basketball_nba", "icehockey_nhl", "baseball_npb", nil] as [String?] {
            XCTAssertFalse(MLBFinalPage11284.applies(sportKey: sport, status: "completed"))
        }
    }

    func testThePairedPageAdoptsFinalMLBWithoutWideningNFLOrNBA() {
        XCTAssertFalse(NFLRecognizablePage9483.applies(sportKey: "baseball_mlb"),
                       "the NFL/NBA predicate itself stays NFL/NBA only")
        XCTAssertTrue(MLBFinalPage11284.adoptsPairedPage(sportKey: "baseball_mlb", status: "completed"))
        XCTAssertFalse(MLBFinalPage11284.adoptsPairedPage(sportKey: "baseball_mlb", status: "live"))
        XCTAssertFalse(MLBFinalPage11284.adoptsPairedPage(sportKey: "baseball_mlb", status: "scheduled"))
        XCTAssertFalse(MLBFinalPage11284.adoptsPairedPage(sportKey: "baseball_mlb", status: nil))
        for status in ["scheduled", "live", "completed", nil] as [String?] {
            XCTAssertTrue(MLBFinalPage11284.adoptsPairedPage(sportKey: "americanfootball_nfl", status: status))
            XCTAssertTrue(MLBFinalPage11284.adoptsPairedPage(sportKey: "basketball_nba", status: status))
        }
        XCTAssertFalse(MLBFinalPage11284.adoptsPairedPage(sportKey: "icehockey_nhl", status: "completed"))
        // The NFL deck function deals nothing for baseball: MLB has its own builder.
        XCTAssertEqual(NFLEventCardDeck9483.cards(sportKey: "baseball_mlb", finish: nil, milestones: []), [])
    }

    func testUpcomingLiveAndOtherSportsDealNoMLBStories() throws {
        let markets = try object(Self.capturedMarkets), related = try object(Self.capturedRelated)
        XCTAssertFalse(try deck(markets: markets, related: related).isEmpty, "control: the final deals")
        XCTAssertEqual(try deck(markets: markets, related: related, status: "live"), [])
        XCTAssertEqual(try deck(markets: markets, related: related, status: "scheduled"), [])
        XCTAssertEqual(try deck(markets: markets, related: related, status: nil), [])
        XCTAssertEqual(try deck(markets: markets, related: related, sport: "americanfootball_nfl"), [])
    }

    func testAnotherEventsDeliveriesNeverSupplyThisPage() throws {
        let cards = try deck(markets: object(Self.capturedMarkets), related: object(Self.capturedRelated),
                             eventID: 15321837)
        XCTAssertEqual(cards, [], "both payloads name event 15321836; the page is 15321837")
    }

    // MARK: - The captured journey

    func testTheCapturedFinalAccountsForEverySlot() throws {
        let cards = try captured()
        // Extra innings: the specimen's extra-innings quote was an EARLIER
        // retained observation absent from the final catalog, so no served
        // original exists for it and no card is dealt.
        XCTAssertEqual(cards.map(\.family), [.homeRuns, .strikeouts, .totals, .series])
        XCTAssertEqual(cards.map(\.id), ["mlb:homeRuns", "mlb:strikeouts", "mlb:totals", "mlb:series"])
        XCTAssertNil(extra(cards))
        let ids = cards.flatMap(\.originals).map(\.id)
        XCTAssertEqual(Set(ids).count, ids.count, "every original has its own identity")
    }

    func testEveryOriginalStaysReachableInTheExistingCatalog() throws {
        let markets = try decode(GameMarketsResponse.self, object(Self.capturedMarkets))
        // 13 totals + 534 player props + 32 team totals + 13 spreads
        // + 21 period markets + 10 other: the fixture's 623 game originals.
        XCTAssertEqual(QuestionCatalog9483.sourceOutcomeCount(markets), 623)
        XCTAssertFalse(QuestionCatalog9483.build(markets, status: "completed").isEmpty)
        let related = try decode(RelatedFuturesResponse.self, object(Self.capturedRelated))
        let seriesOptions = related.seriesQuestionMatrix?.questions.reduce(0) { $0 + $1.options.count }
        XCTAssertEqual(seriesOptions, 9, "the 9 separately scoped series originals")
    }

    func testHomeRunsUseTheTypedSavedChancesNotTheRawMarks() throws {
        let body = try object(Self.capturedMarkets)
        // Non-vacuous: the capture's raw Kalshi rows carry pregame_mark 0.99
        // for the same players' 1+ outcomes.
        let props = try XCTUnwrap(body["player_props"] as? [[String: Any]])
        XCTAssertTrue(props.contains { $0["outcome_name"] as? String == "Jose Altuve: 1+"
            && $0["pregame_mark"] as? Double == 0.99 })
        let card = try XCTUnwrap(homeRuns(captured()))
        XCTAssertEqual(card.story, .likeliest, "no typed official final exists in this capture")
        XCTAssertEqual(card.entries.map(\.player), ["Yordan Alvarez", "Christian Walker", "Munetaka Murakami"])
        XCTAssertEqual(card.entries.map(\.saved), [0.22, 0.17, 0.155])
        XCTAssertEqual(card.entries.map(\.finalCount), [nil, nil, nil], "unknown never reads as 0")
        XCTAssertFalse(card.entries.contains { $0.saved == 0.99 })
        XCTAssertEqual(card.scaleCeiling, 0.25)
        XCTAssertTrue(card.reason.contains("official finals unavailable"))
        let alvarez = try XCTUnwrap(card.entries.first)
        XCTAssertEqual(value("Official final", in: alvarez.original), ["Unavailable"])
        XCTAssertEqual(value("Saved pregame chance", in: alvarez.original), [formatProbability(0.22)])
    }

    func testTheTwoReferenceHomersReadTheirSavedMarksWhenTheirFinalsAreTyped() throws {
        // CONSTRUCTED: the capture's actuals are `unknown`; this types Peña's
        // and Altuve's as ESPN finals of 1 to exercise the homered story.
        var body = try object(Self.capturedMarkets)
        for key in ["s:jeremy pena|home_runs|full_game", "s:jose altuve|home_runs|full_game"] {
            body = try editingActual(body, key: key) {
                $0["state"] = "final"
                $0["value"] = 1
                $0["source_label"] = "ESPN final statistic"
            }
        }
        let card = try XCTUnwrap(homeRuns(deck(markets: body, related: nil)))
        XCTAssertEqual(card.story, .homered)
        XCTAssertEqual(card.entries.map(\.player), ["Jose Altuve", "Jeremy Peña"], "lowest saved chance first")
        // Altuve's saved mark is 10%: never his 6% opening quote or the raw 0.99.
        XCTAssertEqual(card.entries.map(\.saved), [0.1, 0.145])
        XCTAssertEqual(card.entries.map(\.finalCount), [1, 1])
        XCTAssertEqual(card.scaleCeiling, 0.25)
    }

    func testAChanceAboveTheIllustrationWidensTheScaleRatherThanClipping() throws {
        // CONSTRUCTED: one saved chance edited to 0.42.
        var body = try object(Self.capturedMarkets)
        var after = try XCTUnwrap(body["after_player_props"] as? [String: Any])
        var questions = try XCTUnwrap(after["questions"] as? [[String: Any]])
        let index = try XCTUnwrap(questions.firstIndex {
            $0["question_key"] as? String == "s:yordan alvarez|home_runs|full_game|ge:1|over" })
        var expectation = try XCTUnwrap(questions[index]["expectation"] as? [String: Any])
        expectation["probability"] = 0.42
        questions[index]["expectation"] = expectation
        after["questions"] = questions
        body["after_player_props"] = after
        let card = try XCTUnwrap(homeRuns(deck(markets: body, related: nil)))
        XCTAssertEqual(card.entries.first?.saved, 0.42)
        XCTAssertEqual(card.scaleCeiling, 0.45, accuracy: 1e-9)
    }

    func testStrikeoutsChooseTheExpectedAceAndNeverPromoteALegacyActual() throws {
        let body = try object(Self.capturedMarkets)
        // Non-vacuous: Brown's legacy rows carry actual 2 and a hit flag.
        let props = try XCTUnwrap(body["player_props"] as? [[String: Any]])
        XCTAssertTrue(props.contains { $0["market_name"] as? String == "Hunter Brown: Strikeouts O/U 6.5"
            && $0["actual"] as? Double == 2 && $0["hit"] as? Bool != nil })
        let card = try XCTUnwrap(strikeouts(captured()))
        XCTAssertEqual(card.player, "Hunter Brown", "highest line nearest even odds: Brown 6.5 vs Burke 4.5")
        XCTAssertEqual(card.stat, "Strikeouts")
        XCTAssertEqual(card.source, "polymarket")
        XCTAssertEqual(card.targets.map(\.milestone), [6, 7, 8, 9, 10, 12])
        XCTAssertEqual(card.targets.map(\.pregame), [0.57, 0.445, 0.275, 0.11, 0.07, nil])
        XCTAssertEqual(card.defaultIndex, 1, "opens on 7+")
        XCTAssertNil(card.finalCount, "10237.v1 does not type strikeouts")
        XCTAssertEqual(MLBMilestoneResult11284.result(actual: card.finalCount.map(Double.init), milestone: 7),
                       "Final result unavailable")
        for target in card.targets {
            XCTAssertFalse(fields(target.original).contains { $0.value.contains("2 strikeouts") },
                           "\(target.milestone)+ must not print the legacy count")
            XCTAssertEqual(value("Recorded in game", in: target.original), ["Not captured"])
            XCTAssertEqual(value("Official final", in: target.original), ["Unavailable"])
        }
    }

    func testTheSevenPlusDetailsKeepBothOriginalSidesAndThePendingVenueResult() throws {
        let card = try XCTUnwrap(strikeouts(captured()))
        let seven = card.targets[1]
        XCTAssertEqual(seven.rowID, "Hunter Brown: Strikeouts O/U 6.5-Over")
        let titles = seven.original.sections.compactMap(\.title)
        XCTAssertEqual(titles.prefix(2), ["Over · Hunter Brown: Strikeouts O/U 6.5",
                                          "Under · Hunter Brown: Strikeouts O/U 6.5"])
        XCTAssertEqual(value("Original side", in: seven.original), ["Over", "Under"])
        XCTAssertEqual(value("Outcome", in: seven.original), ["239004630", "239004631"])
        XCTAssertEqual(value("Market", in: seven.original), ["63433308", "63433308"])
        XCTAssertEqual(value("Venue result", in: seven.original), ["Pending", "Pending"])
        XCTAssertEqual(value("Pregame mark · Over", in: seven.original),
                       [formatProbability(0.445), formatProbability(0.445)], "both sides serve the Over-axis mark")
        XCTAssertEqual(value("Count at quote time", in: seven.original), ["Unavailable"])
    }

    func testAConstructedTypedStrikeoutFinalDrivesTheMilestoneComparison() throws {
        // CONSTRUCTED: a typed question + official final for Brown's 7+ Over
        // contributor (239004630). No producer types this today.
        var body = try object(Self.capturedMarkets)
        var after = try XCTUnwrap(body["after_player_props"] as? [String: Any])
        let subject: [String: Any] = ["key": "hunter brown", "label": "Hunter Brown", "kind": "player"]
        var questions = try XCTUnwrap(after["questions"] as? [[String: Any]])
        questions.append([
            "question_key": "s:hunter brown|pitching_strikeouts|full_game|ge:7|over",
            "actual_key": "s:hunter brown|pitching_strikeouts|full_game",
            "subject": subject, "stat_key": "pitching_strikeouts", "period_key": "full_game",
            "predicate": ["kind": "count_at_least", "count": 7, "side": "over", "label": "7+"],
            "expectation": ["state": "unavailable", "reason": "constructed", "contributors": [], "excluded": []],
            "comparison": ["state": "below"],
            "contributor_outcome_ids": [239004630],
        ])
        var actuals = try XCTUnwrap(after["actuals"] as? [[String: Any]])
        actuals.append([
            "actual_key": "s:hunter brown|pitching_strikeouts|full_game", "subject": subject,
            "stat_key": "pitching_strikeouts", "period_key": "full_game", "state": "final", "value": 2,
        ])
        after["questions"] = questions
        after["actuals"] = actuals
        body["after_player_props"] = after
        let card = try XCTUnwrap(strikeouts(deck(markets: body, related: nil)))
        XCTAssertEqual(card.player, "Hunter Brown")
        XCTAssertEqual(card.finalCount, 2)
        XCTAssertEqual(card.targets.map { MLBMilestoneResult11284.result(actual: 2, milestone: Double($0.milestone)) },
                       ["Finished 4 short", "Finished 5 short", "Finished 6 short", "Finished 7 short",
                        "Finished 8 short", "Finished 10 short"])
        XCTAssertEqual(value("Official final", in: card.targets[1].original), ["2 strikeouts"])
        XCTAssertEqual(value("Recorded in game", in: card.targets[1].original), ["Not captured"],
                       "the final count is not an in-game observation")
    }

    func testMilestoneResultPassesTheEighteenV472Cases() {
        // `native-baseball-expectations-v472/milestone-cases.json`, all 18.
        let cases: [(String, Double?, Double?, String)] = [
            ("captured-final-2-target-6", 2, 6, "Finished 4 short"),
            ("captured-final-2-target-7", 2, 7, "Finished 5 short"),
            ("captured-final-2-target-8", 2, 8, "Finished 6 short"),
            ("captured-final-2-target-9", 2, 9, "Finished 7 short"),
            ("captured-final-2-target-10", 2, 10, "Finished 8 short"),
            ("reached", 2, 2, "Reached the milestone"),
            ("above", 5, 2, "Finished 3 above"),
            ("unknown-actual", nil, 6, "Final result unavailable"),
            ("unknown-target", 2, nil, "Final result unavailable"),
            ("negative-actual", -1, 6, "Final result unavailable"),
            ("negative-target", 2, -1, "Final result unavailable"),
            ("fractional-actual", 2.5, 6, "Final result unavailable"),
            ("fractional-target", 2, 6.5, "Final result unavailable"),
            ("zero", 0, 0, "Reached the milestone"),
            ("actual-NaN", .nan, 6, "Final result unavailable"),
            ("actual-Infinity", .infinity, 6, "Final result unavailable"),
            ("milestone-NaN", 2, .nan, "Final result unavailable"),
            ("milestone-Infinity", 2, .infinity, "Final result unavailable"),
        ]
        XCTAssertEqual(cases.count, 18)
        XCTAssertEqual(Set(cases.map(\.0)).count, 18)
        for (id, actual, milestone, expected) in cases {
            XCTAssertEqual(MLBMilestoneResult11284.result(actual: actual, milestone: milestone), expected, id)
        }
    }

    func testTotalsAreTheTypedRunLinesWithVenueResultsAndTheScoreSum() throws {
        let card = try XCTUnwrap(totals(captured()))
        XCTAssertEqual(card.lines.map(\.line), stride(from: 2.5, through: 14.5, by: 1).map { $0 },
                       "full-game lines only: the first-five-innings lines stay in the catalog")
        XCTAssertEqual(card.actualTotal, 10, "3 + 7 from the final score, never a quote")
        XCTAssertEqual(card.lines.map(\.venueResult), Array(repeating: true, count: 8) + Array(repeating: false, count: 5))
        XCTAssertEqual(card.lines.map(\.pregame), Array(repeating: nil, count: 13), "no admitted pin")
        let open = try XCTUnwrap(card.defaultIndex)
        XCTAssertEqual(card.lines[open].line, 9.5, "the highest line the total cleared")
        XCTAssertEqual(card.comparison(card.lines[open]), "Final 10 runs · above this line")
        XCTAssertEqual(card.comparison(card.lines[open + 1]), "Final 10 runs · below this line")
        XCTAssertEqual(value("Venue result", in: card.lines[open].original), ["Won"])
        XCTAssertEqual(value("Pregame chance", in: card.lines[open].original), ["Unavailable"])
    }

    func testTotalsWithoutAPrintedScoreHaveNoActual() throws {
        let card = try XCTUnwrap(totals(deck(markets: object(Self.capturedMarkets), related: nil,
                                             home: nil, away: nil)))
        XCTAssertNil(card.actualTotal)
        XCTAssertEqual(card.defaultIndex, 0)
        XCTAssertNil(card.comparison(card.lines[0]))
    }

    func testTheSeriesIsItsOwnScopeAndNeverSettledByThisGame() throws {
        let card = try XCTUnwrap(series(captured()))
        XCTAssertEqual(card.questions.count, 4)
        XCTAssertEqual(card.optionCount, 9)
        XCTAssertEqual(card.reason, "Separate series markets")
        let games = try XCTUnwrap(card.questions.first { $0.questionKey == "m:62898790" })
        XCTAssertEqual(games.options.map(\.result), ["Open"], "the game's final does not settle the series total")
        XCTAssertEqual(card.questions.flatMap(\.options).map(\.pregame), Array(repeating: nil, count: 9))
        XCTAssertEqual(card.questions.first?.options.map(\.label),
                       ["CWS wins 2-0", "HOU wins 2-0", "HOU wins 2-1", "CWS wins 2-1"])
    }

    func testAServedExtraInningsRowDealsItsCardWithTheVenuesResultOnly() throws {
        // CONSTRUCTED: an extra-innings `other` row added to the final body
        // (the specimen's own was an earlier observation, not in this body).
        var body = try object(Self.capturedMarkets)
        var other = try XCTUnwrap(body["other"] as? [[String: Any]])
        other.append([
            "market_name": "Chicago White Sox vs Houston: Extra Innings", "outcome_name": "Yes",
            "observed_at": "2026-09-30T23:04:20.681782+00:00", "contributor_outcome_ids": [237550051],
            "probability": 0.16, "source": "kalshi", "is_winner": NSNull(), "resolution_source": NSNull(),
            "_market_id": 62972332,
        ])
        body["other"] = other
        let cards = try deck(markets: body, related: object(Self.capturedRelated))
        XCTAssertEqual(cards.map(\.family), [.homeRuns, .strikeouts, .totals, .extraInnings, .series])
        let card = try XCTUnwrap(extra(cards))
        XCTAssertEqual(card.outcomes.map(\.label), ["Yes"])
        XCTAssertNil(card.outcomes[0].venueResult, "ungraded: never inferred from a nine-inning score")
        XCTAssertEqual(value("Venue result", in: card.outcomes[0].original), ["Pending"])
        XCTAssertEqual(value("Pregame chance", in: card.outcomes[0].original), ["Unavailable"])
        // The First Inning Run and First 5 Innings rows are not extra innings.
        XCTAssertEqual(card.outcomes.count, 1)
    }

    // MARK: - The existing 10237 route fixture

    func testTheRouteFixtureShowsTheOfficialHomerAgainstItsSavedChance() throws {
        let cards = try deck(markets: object(Self.routeMarkets), related: nil, eventID: 15320207)
        XCTAssertEqual(cards.map(\.family), [.homeRuns], "no strikeout ladder, matrix or series served")
        let card = try XCTUnwrap(homeRuns(cards))
        XCTAssertEqual(card.story, .homered)
        XCTAssertEqual(card.entries.map(\.player), ["Ben Rice"], "Judge has no saved chance")
        XCTAssertEqual(card.entries.map(\.saved), [0.31])
        XCTAssertEqual(card.entries.map(\.finalCount), [2])
        XCTAssertEqual(value("Final source", in: card.entries[0].original), ["ESPN final statistic"])
        XCTAssertEqual(value("Against 1+", in: card.entries[0].original), ["Reached 1+"])
    }

    func testAPendingFinalIsUnavailableAndAFinalZeroStaysZero() throws {
        let body = try object(Self.routeMarkets)
        let key = "s:ben rice|home_runs|full_game"
        // CONSTRUCTED: Rice's ESPN final made pending.
        let pending = try homeRuns(deck(markets: editingActual(body, key: key) {
            $0["state"] = "pending"
            $0["value"] = NSNull()
        }, related: nil, eventID: 15320207))
        XCTAssertEqual(pending?.story, .likeliest)
        XCTAssertEqual(pending?.entries.map(\.finalCount), [nil])
        XCTAssertEqual(pending.map { value("Official final", in: $0.entries[0].original) }, ["Pending"])
        // CONSTRUCTED: Rice's ESPN final made 0.
        let zero = try homeRuns(deck(markets: editingActual(body, key: key) { $0["value"] = 0 },
                                     related: nil, eventID: 15320207))
        XCTAssertEqual(zero?.entries.map(\.finalCount), [0], "a verified final 0 is a real 0")
        XCTAssertEqual(zero.map { value("Official final", in: $0.entries[0].original) }, ["0 home runs"])
    }

    func testAnotherSubjectsActualNeverSuppliesThisOne() throws {
        // CONSTRUCTED: Rice's actual re-keyed to another subject.
        let body = try editingActual(object(Self.routeMarkets), key: "s:ben rice|home_runs|full_game") {
            $0["subject"] = ["key": "aaron judge", "label": "Aaron Judge", "kind": "player"]
        }
        let card = try XCTUnwrap(homeRuns(deck(markets: body, related: nil, eventID: 15320207)))
        XCTAssertEqual(card.entries.map(\.finalCount), [nil])
    }

    func testAnUnknownAfterContractDealsNoHomeRunCard() throws {
        var body = try object(Self.routeMarkets)
        var after = try XCTUnwrap(body["after_player_props"] as? [String: Any])
        after["contract"] = "10237.v2"
        body["after_player_props"] = after
        XCTAssertEqual(try deck(markets: body, related: nil, eventID: 15320207), [])
    }

    // MARK: - Deck and reader wiring

    func testTheReaderHoldsEachOriginalInsideItsCard() throws {
        let cards = try captured().map(NFLEventCard9483.mlb)
        XCTAssertEqual(cards.map(\.id), ["mlb:homeRuns", "mlb:strikeouts", "mlb:totals", "mlb:series"])
        let now = Date()
        XCTAssertEqual(cards.map { $0.current(at: now) }, cards, "a final's history never expires")
        guard case .mlb(let strike) = cards[1] else { return XCTFail("strikeouts card") }
        let id = strike.originals[1].id
        XCTAssertEqual(MLBFinalDeck11284.original(id, in: cards), strike.originals[1])
        XCTAssertNil(MLBFinalDeck11284.original(id, in: []), "Details read the held cards only")
        XCTAssertNil(MLBFinalDeck11284.original(id, in: [cards[0], cards[2]]))
    }

    func testAStructuralRefreshIsAnUpdateAndTheOpenCardSurvivesIt() throws {
        let held = try captured().map(NFLEventCard9483.mlb)
        var body = try object(Self.capturedMarkets)
        body = try editingActual(body, key: "s:yordan alvarez|home_runs|full_game") {
            $0["state"] = "final"
            $0["value"] = 1
        }
        let live = try deck(markets: body, related: object(Self.capturedRelated)).map(NFLEventCard9483.mlb)
        let header = NFLReaderHeader9483(match: "CWS 7–3 HOU · Final", chances: "")
        XCTAssertTrue(NFLCardReaderHold9483.hasUpdate(held: held, heldHeader: header, live: live, liveHeader: header))
        XCTAssertFalse(NFLCardReaderHold9483.hasUpdate(held: held, heldHeader: header, live: held, liveHeader: header))
        XCTAssertEqual(NFLCardReaderHold9483.reconciled(visible: "mlb:strikeouts", old: held.map(\.id),
                                                        new: live.map(\.id)), "mlb:strikeouts")
    }

    func testSelectionsAreKeptPerSlot() {
        let state = NFLCardDeckState9483()
        XCTAssertNil(state.mlbSelection("15321836|mlb:totals"))
        state.selectMLB("o:244311417", slot: "15321836|mlb:totals")
        XCTAssertEqual(state.mlbSelection("15321836|mlb:totals"), "o:244311417")
        XCTAssertNil(state.mlbSelection("15321837|mlb:totals"), "another event's slot is its own")
    }
}
