import SwiftUI
import XCTest
@testable import Bain_Luck

/// #11284 — the associated-series card's comparison (design ref #10868,
/// `reader-final/renders/full-series-375`). The component only draws
/// `MLBSeriesCard11284` with the host's market and outcome keys, so these
/// tests read its market choices, tiles, notices and callbacks against the
/// card the real builder produces.
///
/// FIXTURES, AND WHAT EACH ONE IS (the files `MLBFinalReader11284Tests` pins):
/// - `event-15321836-related-11284-mlb-final.20260930.json` — the RETAINED
///   captured White Sox–Astros series matrix: four markets, nine outcomes,
///   EVERY pregame pin missing, and the producer's own results (one exact
///   score won, the total-games Over still open). Read through the real deck
///   builder, unedited.
/// Cases that need a chance, another result or a shared option key are
/// CONSTRUCTED field by field and say so. The reference's 20.5/31.5/30.5/22.5
/// exact-series values are used only as a constructed control for
/// independent rings; they are not production-native history.
@MainActor
final class MLBSeriesComparison11284Tests: XCTestCase {
    private typealias Comparison = MLBSeriesComparison11284
    private static let fixtures = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appendingPathComponent("Fixtures")
    private static let capturedMarkets = "event-15321836-game-markets-11284-mlb-final.20260930.json"
    private static let capturedRelated = "event-15321836-related-11284-mlb-final.20260930.json"
    private static let exactScore = "m:62898789"
    private static let totalGames = "m:62898790"
    private static let seriesWinner = "m:62898791"
    private static let polymarketWinner = "m:63348824"

    // MARK: - Helpers (the reader tests' fixture pattern)

    private func object(_ name: String) throws -> [String: Any] {
        let data = try Data(contentsOf: Self.fixtures.appendingPathComponent(name))
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private func decode<T: Decodable>(_ type: T.Type, _ dict: [String: Any]) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: JSONSerialization.data(withJSONObject: dict))
    }

    /// RETAINED, unedited.
    private func captured() throws -> MLBSeriesCard11284 {
        let cards = MLBFinalDeck11284.cards(MLBFinalDeckInput11284(
            eventID: 15321836, sportKey: "baseball_mlb", status: "completed",
            homeTeam: "Houston Astros", awayTeam: "Chicago White Sox",
            homeScore: 3, awayScore: 7,
            gameMarkets: try decode(GameMarketsResponse.self, object(Self.capturedMarkets)),
            relatedFutures: try decode(RelatedFuturesResponse.self, object(Self.capturedRelated))))
        var dealt: MLBSeriesCard11284?
        for case .series(let card) in cards { dealt = card }
        return try XCTUnwrap(dealt, "no series card dealt")
    }

    /// CONSTRUCTED option. The original's ID is deliberately not the option
    /// key, so a test can tell which one reached a callback.
    private func option(_ key: String, _ label: String, pregame: Double?,
                        result: MLBVenueResult11284 = .pending, original: String? = nil) -> MLBSeriesCard11284.Option {
        MLBSeriesCard11284.Option(
            optionKey: key, label: label, pregame: pregame, result: result,
            original: MLBOriginal11284(id: original ?? "constructed-original:\(key)", title: label, sections: []))
    }

    private func question(_ key: String, _ label: String,
                          _ options: [MLBSeriesCard11284.Option]) -> MLBSeriesCard11284.Question {
        MLBSeriesCard11284.Question(questionKey: key, label: label, options: options)
    }

    /// CONSTRUCTED control: the reference's four independent exact-series
    /// values (sum 105%), labelled as constructed.
    private func constructedExact() -> MLBSeriesCard11284 {
        MLBSeriesCard11284(eventID: 1, questions: [question("q-exact", "Constructed exact series score", [
            option("o:a20", "Away wins 2-0", pregame: 0.205, result: .won),
            option("o:h20", "Home wins 2-0", pregame: 0.315, result: .lost),
            option("o:h21", "Home wins 2-1", pregame: 0.305, result: .lost),
            option("o:a21", "Away wins 2-1", pregame: 0.225, result: .lost),
        ])])
    }

    private func component(_ card: MLBSeriesCard11284, question: String?, option: String?,
                      onSelectMarket: @escaping (String) -> Void = { _ in },
                      onSelectOption: @escaping (String, String) -> Void = { _, _ in },
                      onDetails: ((String) -> Void)? = nil) -> MLBSeriesComparison11284 {
        MLBSeriesComparison11284(card: card, selectedQuestionKey: question, selectedOptionKey: option,
                                 color: .blue, onSelectMarket: onSelectMarket,
                                 onSelectOption: onSelectOption, onDetails: onDetails)
    }

    private func allWords(_ presentation: Comparison.Presentation) -> [String] {
        [presentation.title, presentation.titleSpoken, presentation.outcomeNotice].compactMap { $0 }
            + presentation.markets.flatMap { [$0.label, $0.spoken] }
            + presentation.tiles.flatMap { [$0.label, $0.chanceText, $0.spoken].compactMap { $0 } }
            + [Comparison.kickerText, Comparison.separateText, Comparison.pregameLabel,
               Comparison.resultLabel, Comparison.unavailableText, Comparison.detailsTitle]
    }

    // MARK: - Retained markets, outcomes and results

    func testTheRetainedSeriesOffersAllFourMarketsAndEveryOutcomeInTheCardsOrder() throws {
        let card = try captured()
        let none = Comparison.presentation(card, questionKey: nil, optionKey: nil)
        XCTAssertEqual(none.markets.map(\.id), [Self.exactScore, Self.totalGames, Self.seriesWinner,
                                                Self.polymarketWinner], "keys and order unchanged")
        XCTAssertEqual(none.markets.map(\.label), card.questions.map(\.label), "exact market text")
        var reached = 0
        for question in card.questions {
            let shown = Comparison.presentation(card, questionKey: question.questionKey, optionKey: nil)
            XCTAssertEqual(shown.markets.count, 4, "every market stays reachable from every market")
            XCTAssertEqual(shown.tiles.map(\.optionKey), question.options.map(\.optionKey), "card order")
            XCTAssertEqual(shown.tiles.map(\.label), question.options.map(\.label), "exact outcome text")
            XCTAssertEqual(shown.title, question.label)
            reached += shown.tiles.count
        }
        XCTAssertEqual(reached, 9, "all nine retained outcomes reachable")
        let exact = Comparison.presentation(card, questionKey: Self.exactScore, optionKey: nil)
        XCTAssertEqual(exact.tiles.map(\.label), ["CWS wins 2-0", "HOU wins 2-0", "HOU wins 2-1", "CWS wins 2-1"],
                       "the producer's order, never regrouped into team columns")
    }

    func testEveryRetainedBaselineIsMissingAndDrawsNoRingAndNoNumber() throws {
        let card = try captured()
        for question in card.questions {
            for tile in Comparison.presentation(card, questionKey: question.questionKey, optionKey: nil).tiles {
                XCTAssertNil(tile.ringFraction, "no zero or decorative ring for \(tile.label)")
                XCTAssertNil(tile.chanceText, "no number invented for \(tile.label)")
                XCTAssertTrue(tile.spoken.contains("Pregame chance unavailable."), tile.spoken)
                XCTAssertFalse(tile.spoken.contains("%"), tile.spoken)
            }
        }
    }

    func testTheRetainedResultsAreTheProducersOwnWords() throws {
        let card = try captured()
        func results(_ key: String) -> [MLBVenueResult11284] {
            Comparison.presentation(card, questionKey: key, optionKey: nil).tiles.map(\.result)
        }
        XCTAssertEqual(results(Self.exactScore), [.won, .lost, .lost, .lost])
        XCTAssertEqual(results(Self.totalGames), [.open], "this game's final does not settle the series total")
        XCTAssertEqual(results(Self.seriesWinner), [.won, .lost])
        XCTAssertEqual(results(Self.polymarketWinner), [.won, .lost])
        let open = try XCTUnwrap(Comparison.presentation(card, questionKey: Self.totalGames, optionKey: nil).tiles.first)
        XCTAssertEqual(open.spoken, "Over 2.5 total games, in Series Total Games: Chicago White Sox vs Houston. "
                       + "Pregame chance unavailable. Venue result Open.")
        XCTAssertFalse(Comparison.celebrates(open.result), "an open outcome is never celebrated")
    }

    func testEachRetainedTileCarriesItsOptionsOwnOriginal() throws {
        let card = try captured()
        for question in card.questions {
            let tiles = Comparison.presentation(card, questionKey: question.questionKey, optionKey: nil).tiles
            XCTAssertEqual(tiles.map(\.originalID), question.options.map(\.original.id))
        }
        let selected = Comparison.presentation(card, questionKey: Self.exactScore, optionKey: "o:237333168")
        XCTAssertEqual(selected.detailsID, "mlb-o:15321836:q:m:62898789|o:237333168")
        XCTAssertEqual(selected.tiles.filter(\.isSelected).map(\.label), ["CWS wins 2-0"])
    }

    // MARK: - Independent rings

    func testConstructedIndependentContractsSumPast100AndEachRingDrawsOnlyItsOwnChance() {
        let card = constructedExact()
        let tiles = Comparison.presentation(card, questionKey: "q-exact", optionKey: nil).tiles
        let inputs = [0.205, 0.315, 0.305, 0.225]
        XCTAssertEqual(tiles.compactMap(\.ringFraction), inputs, "never normalized or partitioned")
        XCTAssertGreaterThan(tiles.compactMap(\.ringFraction).reduce(0, +), 1, "the 105% sum is kept")
        XCTAssertEqual(tiles.compactMap(\.chanceText), inputs.map { formatProbability($0) },
                       "the shared formatter decides the words")
        XCTAssertEqual(tiles.map(\.label), ["Away wins 2-0", "Home wins 2-0", "Home wins 2-1", "Away wins 2-1"])
    }

    func testAnAdmittedZeroAndOneDrawEmptyAndFullRingsDistinctFromAbsence() {
        let card = MLBSeriesCard11284(eventID: 1, questions: [question("q", "Constructed market", [
            option("o:zero", "Zero", pregame: 0),
            option("o:none", "None", pregame: nil),
            option("o:one", "One", pregame: 1),
        ])])
        let tiles = Comparison.presentation(card, questionKey: "q", optionKey: nil).tiles
        XCTAssertEqual(tiles[0].ringFraction, 0, "an empty ring is a value")
        XCTAssertEqual(tiles[0].chanceText, formatProbability(0))
        XCTAssertNil(tiles[1].ringFraction, "absence draws no ring")
        XCTAssertNil(tiles[1].chanceText)
        XCTAssertEqual(tiles[2].ringFraction, 1, "a full ring is a value")
        XCTAssertEqual(tiles[2].chanceText, formatProbability(1))
        XCTAssertEqual(tiles[0].spoken,
                       "Zero, in Constructed market. Pregame chance \(formatProbability(0)). Venue result Pending.")
        XCTAssertEqual(tiles[1].spoken, "None, in Constructed market. Pregame chance unavailable. Venue result Pending.")
        XCTAssertNotEqual(tiles[0].spoken, tiles[1].spoken)
    }

    func testAValueOutsideZeroToOneDrawsNothingRatherThanAClippedRing() {
        XCTAssertNil(Comparison.ringFraction(1.2))
        XCTAssertNil(Comparison.ringFraction(-0.1))
        XCTAssertNil(Comparison.ringFraction(.nan))
        XCTAssertNil(Comparison.ringFraction(.infinity))
        XCTAssertEqual(Comparison.ringFraction(0.42), 0.42)
    }

    // MARK: - Results

    func testAllFiveResultStatesKeepTheirOwnWordsAndSymbolsAndOnlyWonIsTinted() {
        let states: [MLBVenueResult11284] = [.won, .lost, .open, .pending, .notConfirmed]
        let card = MLBSeriesCard11284(eventID: 1, questions: [question("q", "Constructed market",
            states.enumerated().map { option("o:\($0.offset)", "Outcome \($0.offset)", pregame: 0.3, result: $0.element) })])
        let tiles = Comparison.presentation(card, questionKey: "q", optionKey: nil).tiles
        XCTAssertEqual(tiles.map(\.result), states, "no state collapses into another")
        XCTAssertEqual(tiles.map { $0.result.label }, ["Won", "Lost", "Open", "Pending", "Not confirmed"])
        XCTAssertEqual(Set(states.map(Comparison.resultSymbol)).count, 5, "a non-colour cue per state")
        XCTAssertEqual(states.filter(Comparison.celebrates), [.won], "no celebratory fill for open or pending")
        for tile in tiles {
            XCTAssertTrue(tile.spoken.hasSuffix("Venue result \(tile.result.label)."), tile.spoken)
        }
    }

    // MARK: - Selection without fallback

    func testANilMarketShowsNoOtherMarketsOutcomesAndKeepsTheSelector() throws {
        let card = try captured()
        let shown = Comparison.presentation(card, questionKey: nil, optionKey: "o:237333168")
        XCTAssertEqual(shown.title, "Choose a market")
        XCTAssertEqual(shown.titleSpoken, "No market selected")
        XCTAssertTrue(shown.tiles.isEmpty, "the first market is never shown silently")
        XCTAssertNil(shown.detailsID, "an outcome key alone selects nothing")
        XCTAssertEqual(shown.markets.count, 4)
        XCTAssertFalse(shown.markets.contains(where: \.isSelected))
        XCTAssertEqual(Comparison.market(card, questionKey: nil), .unselected)
    }

    func testAMarketTheCardNoLongerCarriesIsUnavailableNeverAnotherMarket() throws {
        let card = try captured()
        let shown = Comparison.presentation(card, questionKey: "m:gone", optionKey: "o:237333168")
        XCTAssertEqual(shown.title, "This market is unavailable in this update")
        XCTAssertEqual(shown.titleSpoken, "Selected market unavailable in this update")
        XCTAssertTrue(shown.tiles.isEmpty)
        XCTAssertNil(shown.detailsID)
        XCTAssertEqual(shown.markets.map(\.id), card.questions.map(\.questionKey), "the selector stays whole")
        XCTAssertFalse(shown.markets.contains(where: \.isSelected))
        XCTAssertEqual(Comparison.market(card, questionKey: "m:gone"), .unavailable)
        XCTAssertNotEqual(Comparison.market(card, questionKey: "m:gone"), Comparison.market(card, questionKey: nil),
                          "missing and absent stay distinct")
    }

    func testANilOutcomeShowsEveryTileUnselectedWithNoDetails() throws {
        let card = try captured()
        let shown = Comparison.presentation(card, questionKey: Self.exactScore, optionKey: nil)
        XCTAssertEqual(shown.tiles.count, 4)
        XCTAssertFalse(shown.tiles.contains(where: \.isSelected), "no first or default outcome is chosen")
        XCTAssertNil(shown.outcomeNotice)
        XCTAssertNil(shown.detailsID)
        XCTAssertEqual(shown.markets.filter(\.isSelected).map(\.id), [Self.exactScore])
    }

    func testAnOutcomeTheMarketNoLongerCarriesIsUnavailableNeverTheFirst() throws {
        let card = try captured()
        let shown = Comparison.presentation(card, questionKey: Self.exactScore, optionKey: "o:gone")
        XCTAssertEqual(shown.outcomeNotice, "The selected outcome is unavailable in this update")
        XCTAssertEqual(shown.tiles.count, 4, "every outcome stays reachable")
        XCTAssertFalse(shown.tiles.contains(where: \.isSelected))
        XCTAssertNil(shown.detailsID)
        let question = try XCTUnwrap(card.questions.first)
        XCTAssertEqual(Comparison.outcome(in: question, optionKey: "o:gone"), .unavailable)
        XCTAssertEqual(Comparison.outcome(in: question, optionKey: nil), .unselected)
    }

    func testAnOutcomeKeyFromAnotherMarketSelectsNothingHere() throws {
        let card = try captured()
        // o:237333171 (White Sox, series winner) is not an exact-score outcome.
        let shown = Comparison.presentation(card, questionKey: Self.exactScore, optionKey: "o:237333171")
        XCTAssertFalse(shown.tiles.contains(where: \.isSelected))
        XCTAssertNil(shown.detailsID)
        XCTAssertNotNil(shown.outcomeNotice)
    }

    func testTheSameOptionKeyInTwoMarketsResolvesOnlyInsideTheSelectedMarket() {
        // CONSTRUCTED: two markets sharing one option key, with distinct originals.
        let card = MLBSeriesCard11284(eventID: 1, questions: [
            question("q-a", "Constructed market A", [
                option("o:shared", "A shared", pregame: 0.4, original: "original-A"),
                option("o:a-only", "A only", pregame: 0.6),
            ]),
            question("q-b", "Constructed market B", [
                option("o:b-only", "B only", pregame: 0.3),
                option("o:shared", "B shared", pregame: 0.7, original: "original-B"),
            ]),
        ])
        let a = Comparison.presentation(card, questionKey: "q-a", optionKey: "o:shared")
        XCTAssertEqual(a.detailsID, "original-A")
        XCTAssertEqual(a.tiles.filter(\.isSelected).map(\.label), ["A shared"])
        let b = Comparison.presentation(card, questionKey: "q-b", optionKey: "o:shared")
        XCTAssertEqual(b.detailsID, "original-B")
        XCTAssertEqual(b.tiles.filter(\.isSelected).map(\.label), ["B shared"])
        XCTAssertEqual(Set(a.tiles.map(\.id) + b.tiles.map(\.id)).count, 4, "tile identity is scoped by market")
    }

    // MARK: - Callbacks

    func testAMarketTapSendsItsQuestionKeyUnchanged() throws {
        let card = try captured()
        var received: [String] = []
        let view = component(card, question: nil, option: nil, onSelectMarket: { received.append($0) })
        for market in view.presentation.markets { view.select(market) }
        XCTAssertEqual(received, card.questions.map(\.questionKey))
    }

    func testAnOutcomeTapSendsItsOwnMarketAndOptionKeys() throws {
        let card = try captured()
        var received: [[String]] = []
        for question in card.questions {
            let view = component(card, question: question.questionKey, option: nil,
                            onSelectOption: { received.append([$0, $1]) })
            for tile in view.presentation.tiles { view.select(tile) }
        }
        XCTAssertEqual(received, card.questions.flatMap { q in q.options.map { [q.questionKey, $0.optionKey] } })
    }

    func testDetailsSendsTheSelectedOriginalIDNotTheOptionKey() {
        let card = constructedExact()
        var received: [String] = []
        let view = component(card, question: "q-exact", option: "o:h21", onDetails: { received.append($0) })
        XCTAssertTrue(view.detailsAvailable)
        view.details()
        XCTAssertEqual(received, ["constructed-original:o:h21"])
    }

    func testDetailsNeedsBothACallbackAndAResolvedOutcome() {
        let card = constructedExact()
        XCTAssertFalse(component(card, question: "q-exact", option: "o:h21").detailsAvailable, "no callback, no control")
        var received: [String] = []
        for (question, option) in [("q-exact", nil), ("q-exact", "o:gone"), (nil, "o:h21"), ("q-gone", "o:h21")]
            as [(String?, String?)] {
            let view = component(card, question: question, option: option, onDetails: { received.append($0) })
            XCTAssertFalse(view.detailsAvailable, "\(String(describing: question)) / \(String(describing: option))")
            view.details()
        }
        XCTAssertEqual(received, [], "nothing is sent without a resolved outcome")
    }

    // MARK: - Words

    func testTheChanceIsPregameNeverPreSeriesBeforeThisGameOrCurrent() throws {
        let retained = try captured()
        var words: [String] = []
        for key in [nil, Self.exactScore, Self.totalGames, Self.seriesWinner, Self.polymarketWinner, "m:gone"] {
            words += allWords(Comparison.presentation(retained, questionKey: key, optionKey: nil))
        }
        words += allWords(Comparison.presentation(constructedExact(), questionKey: "q-exact", optionKey: "o:a20"))
        let text = words.joined(separator: " | ")
        XCTAssertTrue(text.contains("Pregame chance"))
        for banned in ["Pre-series", "pre-series", "before this game", "Before this game", "Current", "current",
                       "live", "Live", "Recorded", "recorded"] {
            XCTAssertFalse(text.contains(banned), "\"\(banned)\" printed")
        }
    }

    func testTheHeadingSaysAssociatedSeriesAndSeparateFromThisGame() {
        XCTAssertEqual(Comparison.kickerText, "Associated series")
        XCTAssertEqual(Comparison.separateText, "Separate from this game")
    }

    func testSpokenPartsNameTheMarketTheOutcomeItsChanceAndItsResult() throws {
        let card = try captured()
        let shown = Comparison.presentation(card, questionKey: Self.exactScore, optionKey: "o:237333168")
        XCTAssertEqual(shown.markets.first?.spoken, "Market, Series Exact Score: Chicago White Sox vs Houston")
        XCTAssertEqual(shown.titleSpoken, "Selected market, Series Exact Score: Chicago White Sox vs Houston")
        XCTAssertEqual(shown.tiles.first?.spoken, "CWS wins 2-0, in Series Exact Score: Chicago White Sox vs Houston. "
                       + "Pregame chance unavailable. Venue result Won.")
        let constructed = Comparison.presentation(constructedExact(), questionKey: "q-exact", optionKey: nil)
        XCTAssertEqual(constructed.tiles.first?.spoken,
                       "Away wins 2-0, in Constructed exact series score. "
                       + "Pregame chance \(formatProbability(0.205)). Venue result Won.")
    }

    func testLongNamesAreKeptWhole() {
        let market = "Constructed market whose very long name runs well past any one line at phone width"
        let outcome = "A constructed outcome name that is far too long to fit beside its ring in one line"
        let card = MLBSeriesCard11284(eventID: 1, questions: [question("q-long", market, [
            option("o:long", outcome, pregame: 0.5),
        ])])
        let shown = Comparison.presentation(card, questionKey: "q-long", optionKey: "o:long")
        XCTAssertEqual(shown.markets.first?.label, market)
        XCTAssertEqual(shown.title, market)
        XCTAssertEqual(shown.tiles.first?.label, outcome)
        XCTAssertTrue(shown.tiles.first?.spoken.hasPrefix(outcome) == true)
        XCTAssertTrue(shown.tiles.first?.spoken.contains(market) == true, "the whole market name is spoken")
        XCTAssertEqual(shown.tiles.first?.chanceText, formatProbability(0.5), "the chance keeps its words")
    }

    func testRepeatedOutcomeNamesInDifferentMarketsAreSpokenApart() throws {
        // CONSTRUCTED: two markets whose outcomes share one name.
        let card = MLBSeriesCard11284(eventID: 1, questions: [
            question("q-1", "Constructed series winner", [option("o:1", "White Sox", pregame: 0.4, result: .won)]),
            question("q-2", "Constructed series winner, second venue", [option("o:2", "White Sox", pregame: nil,
                                                                              result: .won)]),
        ])
        let first = try XCTUnwrap(Comparison.presentation(card, questionKey: "q-1", optionKey: nil).tiles.first)
        let second = try XCTUnwrap(Comparison.presentation(card, questionKey: "q-2", optionKey: nil).tiles.first)
        XCTAssertNotEqual(first.spoken, second.spoken, "jumping between tiles stays unambiguous")
        XCTAssertTrue(first.spoken.contains("Constructed series winner."), first.spoken)
        XCTAssertTrue(second.spoken.contains("Constructed series winner, second venue."), second.spoken)
        let retained = try captured()
        for key in [nil, Self.exactScore, Self.seriesWinner] {
            let words = allWords(Comparison.presentation(retained, questionKey: key, optionKey: nil))
            XCTAssertFalse(words.joined(separator: " ").lowercased().contains("question"),
                           "internal terminology stays out of visible and spoken chrome")
        }
    }

    // MARK: - Layout decisions

    func testTheRingNeverGrowsPastItsDefaultAndFitsACompactPhone() {
        XCTAssertEqual(Comparison.boundedRing(scaled: 260), Comparison.ringPointDiameter, "AX5-scaled is capped")
        XCTAssertEqual(Comparison.boundedRing(scaled: 104), 104, "smaller text keeps a smaller ring")
        // A 320pt viewport less 16pt card insets each side, less the tile's own padding.
        XCTAssertLessThanOrEqual(Comparison.ringPointDiameter + 2 * Comparison.tilePadding, 320 - 2 * 16)
        XCTAssertLessThan(Comparison.belowRingDiameter, Comparison.ringPointDiameter)
    }

    func testTheChanceSitsInsideTheRingOnlyWhileItsFullSizeFits() {
        let card = MLBSeriesCard11284(eventID: 1, questions: [question("q", "Constructed market", [
            option("o:p", "Priced", pregame: 0.42),
            option("o:z", "Zero", pregame: 0),
        ])])
        let tiles = Comparison.presentation(card, questionKey: "q", optionKey: nil).tiles
        let ring = Comparison.ringPointDiameter
        // Figure sizes stand in for .title at each size (28 default, about 34 at XXXL).
        XCTAssertEqual(Comparison.chanceLayout(tiles[0], size: .large, figureSize: 28, ringDiameter: ring), .inside)
        XCTAssertEqual(Comparison.chanceLayout(tiles[0], size: .xxxLarge, figureSize: 34, ringDiameter: ring), .inside)
        XCTAssertEqual(Comparison.chanceLayout(tiles[0], size: .xxLarge, figureSize: 40, ringDiameter: ring), .below,
                       "a figure too wide for the ring moves out rather than shrinking")
        for size in [DynamicTypeSize.accessibility1, .accessibility3, .accessibility5] {
            XCTAssertEqual(Comparison.chanceLayout(tiles[0], size: size, figureSize: 28, ringDiameter: ring), .below,
                           "\(size): an explicit accessibility layout")
        }
        XCTAssertEqual(Comparison.chanceLayout(tiles[1], size: .large, figureSize: 28, ringDiameter: ring), .inside,
                       "an admitted zero still draws its (empty) ring")
        XCTAssertTrue(Comparison.figureFitsInside(figureSize: 28, ringDiameter: ring))
        XCTAssertFalse(Comparison.figureFitsInside(figureSize: 40, ringDiameter: ring))
    }

    func testAMissingChanceIsAbsentAtEverySizeAndReservesNoRing() throws {
        let card = try captured()
        let tile = try XCTUnwrap(Comparison.presentation(card, questionKey: Self.exactScore, optionKey: nil).tiles.first)
        for size in [DynamicTypeSize.xSmall, .large, .xxxLarge, .accessibility1, .accessibility5] {
            XCTAssertEqual(Comparison.chanceLayout(tile, size: size, figureSize: 28,
                                                   ringDiameter: Comparison.ringPointDiameter), .absent, "\(size)")
        }
    }

    func testTilesFallToOneColumnAtXXXLAndAccessibilitySizes() {
        for size in [DynamicTypeSize.xSmall, .small, .medium, .large, .xLarge, .xxLarge] {
            XCTAssertFalse(Comparison.singleColumn(at: size), "\(size)")
        }
        for size in [DynamicTypeSize.xxxLarge, .accessibility1, .accessibility3, .accessibility5] {
            XCTAssertTrue(Comparison.singleColumn(at: size), "\(size)")
        }
    }

    func testTheMarketSelectorBecomesAFullWidthListAtAccessibilitySizes() {
        for size in [DynamicTypeSize.large, .xxxLarge] {
            XCTAssertFalse(Comparison.selectorStacks(at: size), "\(size)")
        }
        for size in [DynamicTypeSize.accessibility1, .accessibility5] {
            XCTAssertTrue(Comparison.selectorStacks(at: size), "\(size)")
        }
    }

    func testTheChanceIsAtLeast28ptAndEveryControlAtLeast44pt() {
        XCTAssertGreaterThanOrEqual(Comparison.figurePointSize, 28)
        XCTAssertGreaterThan(Comparison.ringPointDiameter, Comparison.figurePointSize * 3,
                             "the ring holds a four-character chance without shrinking it")
        XCTAssertGreaterThanOrEqual(Comparison.minimumControlHeight, 44)
    }

    func testPairsKeepTheCardsOrderAndAnOddLastTileStandsAlone() throws {
        let card = try captured()
        let exact = Comparison.presentation(card, questionKey: Self.exactScore, optionKey: nil).tiles
        let pairs = Comparison.pairs(exact)
        XCTAssertEqual(pairs.count, 2)
        XCTAssertEqual(pairs.flatMap { [$0.first] + [$0.second].compactMap { $0 } }, exact, "order unchanged")
        let total = Comparison.presentation(card, questionKey: Self.totalGames, optionKey: nil).tiles
        XCTAssertEqual(Comparison.pairs(total).count, 1)
        XCTAssertNil(Comparison.pairs(total).first?.second)
        XCTAssertTrue(Comparison.pairs([]).isEmpty)
    }
}
