import SwiftUI
import XCTest
@testable import Bain_Luck

/// #11284 — the home-run card's paired comparison (design ref #10868,
/// `native-baseball-paired-home-runs`). The component only draws
/// `MLBHomeRunCard11284`, so these tests read its rows, rail coordinates and
/// details IDs against the card the real builder produces.
///
/// FIXTURES, AND WHAT EACH ONE IS (the same files `MLBFinalReader11284Tests`
/// pins):
/// - `event-15321836-game-markets-11284-mlb-final.20260930.json` — the
///   RETAINED captured Astros–White Sox final. Its typed actuals are all
///   `unknown`, so as captured it deals the likeliest three with no finals.
/// - `game-markets-10237-after.route.json` — the EXISTING route fixture
///   (Ben Rice, 31% saved, an ESPN final of 2 home runs).
/// Cases that need another state are CONSTRUCTED: either one edited value of a
/// retained body (said where it happens) or a card built field by field.
/// The reference's Peña 14.5% / Altuve 10% / one homer each is the constructed
/// homered edit of the capture, exactly as the reader tests type it.
@MainActor
final class MLBHomeRunComparison11284Tests: XCTestCase {
    private static let fixtures = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appendingPathComponent("Fixtures")
    private static let capturedMarkets = "event-15321836-game-markets-11284-mlb-final.20260930.json"
    private static let routeMarkets = "game-markets-10237-after.route.json"

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

    private func homeRuns(_ markets: [String: Any], eventID: Int = 15321836) throws -> MLBHomeRunCard11284 {
        let cards = MLBFinalDeck11284.cards(MLBFinalDeckInput11284(
            eventID: eventID, sportKey: "baseball_mlb", status: "completed",
            homeTeam: "Houston Astros", awayTeam: "Chicago White Sox",
            homeScore: 3, awayScore: 7,
            gameMarkets: try decode(GameMarketsResponse.self, markets),
            relatedFutures: nil))
        var dealt: MLBHomeRunCard11284?
        for case .homeRuns(let card) in cards { dealt = card }
        return try XCTUnwrap(dealt, "no home-run card dealt")
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

    /// CONSTRUCTED: the capture with Peña's and Altuve's actuals typed as ESPN
    /// finals of 1 — the reference's two homers.
    private func referenceHomered() throws -> MLBHomeRunCard11284 {
        var body = try object(Self.capturedMarkets)
        for key in ["s:jeremy pena|home_runs|full_game", "s:jose altuve|home_runs|full_game"] {
            body = try editingActual(body, key: key) {
                $0["state"] = "final"
                $0["value"] = 1
                $0["source_label"] = "ESPN final statistic"
            }
        }
        return try homeRuns(body)
    }

    /// CONSTRUCTED entry. The original's ID is deliberately not the question
    /// key, so a test can tell which one reached the callback.
    private func entry(_ key: String, player: String? = nil, saved: Double, final: Int?,
                       side: PlayerPropsTeam.Side = .unknown) -> MLBHomeRunCard11284.Entry {
        MLBHomeRunCard11284.Entry(
            questionKey: key, player: player ?? key, saved: saved, finalCount: final, side: side,
            original: MLBOriginal11284(id: "mlb-o:1:after:\(key)", title: key, sections: []))
    }

    private func constructed(_ entries: [MLBHomeRunCard11284.Entry],
                             story: MLBHomeRunCard11284.Story = .homered) -> MLBHomeRunCard11284 {
        MLBHomeRunCard11284(eventID: 1, story: story, entries: entries)
    }

    private func view(_ card: MLBHomeRunCard11284,
                      onDetails: ((String) -> Void)? = nil) -> MLBHomeRunComparison11284 {
        MLBHomeRunComparison11284(card: card, awayColor: .blue, homeColor: .orange, onDetails: onDetails)
    }

    // MARK: - Order and identity

    func testTheReferenceHomersKeepTheCardsOrderAndIdentity() throws {
        let card = try referenceHomered()
        let rows = MLBHomeRunComparison11284.rows(card)
        XCTAssertEqual(rows.map(\.player), ["Jose Altuve", "Jeremy Peña"], "the builder's order, not re-sorted")
        XCTAssertEqual(rows.map(\.id), card.entries.map(\.id))
        XCTAssertEqual(rows.map(\.detailsID), card.entries.map(\.original.id))
        XCTAssertEqual(rows.map(\.side), card.entries.map(\.side))
    }

    func testThreeRetainedEntriesDrawThreeRowsInTheSuppliedOrder() throws {
        // RETAINED, unedited: no typed final, so the likeliest three.
        let card = try homeRuns(object(Self.capturedMarkets))
        XCTAssertEqual(card.entries.count, 3)
        let rows = MLBHomeRunComparison11284.rows(card)
        XCTAssertEqual(rows.map(\.player), ["Yordan Alvarez", "Christian Walker", "Munetaka Murakami"])
    }

    func testAConstructedOrderIsNeverReranked() {
        let card = constructed([entry("low", saved: 0.05, final: 1), entry("high", saved: 0.20, final: 1),
                                entry("mid", saved: 0.12, final: 1)])
        XCTAssertEqual(MLBHomeRunComparison11284.rows(card).map(\.id), ["low", "high", "mid"])
    }

    func testAnEmptyCardInventsNoRows() {
        XCTAssertEqual(MLBHomeRunComparison11284.rows(constructed([], story: .likeliest)), [])
    }

    // MARK: - Chance and the shared rail

    func testThePregameFigureIsTheShippingFormatterNotTheReferencesOneDecimal() throws {
        let card = try referenceHomered()
        let rows = MLBHomeRunComparison11284.rows(card)
        XCTAssertEqual(rows.map(\.pregameText), card.entries.map { formatProbability($0.saved) })
        // The reference printed Peña as 14.5%; that precision is the shared
        // formatter owner's later decision, not this component's.
        XCTAssertNotEqual(rows.last?.pregameText, "14.5%")
    }

    func testTheRailKeepsFullPrecisionOnTheCardsCeiling() throws {
        let card = try referenceHomered()
        XCTAssertEqual(card.scaleCeiling, 0.25)
        let rows = MLBHomeRunComparison11284.rows(card)
        XCTAssertEqual(try XCTUnwrap(rows[0].railFraction), 0.1 / 0.25, accuracy: 1e-12)
        XCTAssertEqual(try XCTUnwrap(rows[1].railFraction), 0.145 / 0.25, accuracy: 1e-12)
    }

    func testTheRouteSpecimenAboveTwentyFivePercentWidensTheRailInFivePointSteps() throws {
        let card = try homeRuns(object(Self.routeMarkets), eventID: 15320207)
        XCTAssertEqual(card.entries.map(\.saved), [0.31])
        XCTAssertEqual(card.scaleCeiling, 0.35, accuracy: 1e-9, "next 5% above, not the reference's 25-point step")
        let row = try XCTUnwrap(MLBHomeRunComparison11284.rows(card).first)
        XCTAssertEqual(try XCTUnwrap(row.railFraction), 0.31 / card.scaleCeiling, accuracy: 1e-12)
        XCTAssertEqual(MLBHomeRunComparison11284.axisLabels(ceiling: card.scaleCeiling).upper, "35%")
    }

    func testEveryRowSharesTheCardsCeilingRatherThanItsOwnChance() {
        let card = constructed([entry("a", saved: 0.42, final: 1), entry("b", saved: 0.12, final: 1),
                                entry("c", saved: 0.05, final: 2)])
        XCTAssertEqual(card.scaleCeiling, 0.45, accuracy: 1e-9)
        let fractions = MLBHomeRunComparison11284.rows(card).compactMap(\.railFraction)
        XCTAssertEqual(fractions.count, 3)
        for (fraction, saved) in zip(fractions, [0.42, 0.12, 0.05]) {
            XCTAssertEqual(fraction, saved / 0.45, accuracy: 1e-12)
        }
        XCTAssertLessThan(fractions[0], 1, "the largest chance is not stretched to the rail's end")
    }

    func testAFinalCountNeverMovesTheRail() {
        let card = constructed([entry("none", saved: 0.15, final: 0), entry("three", saved: 0.15, final: 3),
                                entry("unknown", saved: 0.15, final: nil)], story: .homered)
        let fractions = MLBHomeRunComparison11284.rows(card).map(\.railFraction)
        XCTAssertEqual(Set(fractions), [0.15 / card.scaleCeiling])
    }

    func testTheAxisNamesTheSharedDomainItsEnds() {
        XCTAssertEqual(MLBHomeRunComparison11284.axisLabels(ceiling: 0.25).lower, "0%")
        XCTAssertEqual(MLBHomeRunComparison11284.axisLabels(ceiling: 0.25).upper, "25%")
        XCTAssertEqual(MLBHomeRunComparison11284.axisLabels(ceiling: 0.45).upper, "45%")
        XCTAssertEqual(MLBHomeRunComparison11284.axisLabels(ceiling: 1).upper, "100%")
        XCTAssertTrue(MLBHomeRunComparison11284.scaleSpoken(ceiling: 0.35).hasSuffix("from 0% to 35%"))
    }

    // MARK: - Finals: nil, zero, one, several

    func testAnUnavailableFinalIsNeverZero() throws {
        // RETAINED, unedited: every typed actual is `unknown`.
        let rows = try MLBHomeRunComparison11284.rows(homeRuns(object(Self.capturedMarkets)))
        XCTAssertEqual(rows.map(\.finalFigureText), [nil, nil, nil])
        for row in rows {
            XCTAssertEqual(row.finalSpoken, "Official final unavailable")
            XCTAssertFalse(row.spoken.contains("0 home"))
        }
    }

    func testAVerifiedZeroIsAZero() {
        let row = MLBHomeRunComparison11284.row(entry("z", saved: 0.2, final: 0), ceiling: 0.25)
        XCTAssertEqual(row.finalFigureText, "0 HR")
        XCTAssertEqual(row.finalSpoken, "Official final, 0 home runs")
    }

    func testOneAndSeveralHomersSayHRVisiblyAndHomeRunsAloud() throws {
        let one = try XCTUnwrap(MLBHomeRunComparison11284.rows(referenceHomered()).first)
        XCTAssertEqual(one.finalFigureText, "1 HR")
        XCTAssertEqual(one.finalSpoken, "Official final, 1 home run")
        let two = try XCTUnwrap(MLBHomeRunComparison11284.rows(
            homeRuns(object(Self.routeMarkets), eventID: 15320207)).first)
        XCTAssertEqual(two.finalFigureText, "2 HR")
        XCTAssertEqual(two.finalSpoken, "Official final, 2 home runs")
    }

    // MARK: - Details and interaction

    func testDetailsHandBackTheOriginalIDUnchanged() throws {
        let card = try referenceHomered()
        var received: [String] = []
        let comparison = view(card) { received.append($0) }
        let rows = MLBHomeRunComparison11284.rows(card)
        rows.forEach(comparison.details)
        XCTAssertEqual(received, card.entries.map(\.original.id))
        XCTAssertNotEqual(received, card.entries.map(\.id), "the original ID, not the question key")
    }

    func testNoCallbackIsCompactAndInert() {
        let card = constructed([entry("a", saved: 0.1, final: 1)])
        let comparison = view(card)
        XCTAssertFalse(comparison.isInteractive)
        XCTAssertNil(comparison.detailsHint)
        MLBHomeRunComparison11284.rows(card).forEach(comparison.details) // no callback, nothing to reach
    }

    func testACallbackMakesEachWholeRowOneDetailsControl() {
        let comparison = view(constructed([entry("a", saved: 0.1, final: 1)])) { _ in }
        XCTAssertTrue(comparison.isInteractive)
        XCTAssertEqual(comparison.detailsHint, MLBHomeRunComparison11284.detailsHintText)
        XCTAssertGreaterThanOrEqual(MLBHomeRunComparison11284.minimumRowHeight, 44)
    }

    func testTheSpokenRowNamesPlayerChanceAndFinalApartFromTheAction() throws {
        let card = try referenceHomered()
        for (row, entry) in zip(MLBHomeRunComparison11284.rows(card), card.entries) {
            XCTAssertTrue(row.spoken.hasPrefix("\(entry.player)."))
            XCTAssertTrue(row.spoken.contains("Pregame chance of at least one home run, \(formatProbability(entry.saved))"))
            XCTAssertTrue(row.spoken.contains(row.finalSpoken))
            XCTAssertFalse(row.spoken.contains(MLBHomeRunComparison11284.detailsHintText))
            XCTAssertFalse(row.spoken.contains(entry.questionKey), "no internal key as copy")
        }
    }

    // MARK: - Layout intent

    func testALongNameIsKeptWhole() {
        let name = "Christopher Alexander Montgomery-Wellington Jr."
        let row = MLBHomeRunComparison11284.row(entry("long", player: name, saved: 0.08, final: nil), ceiling: 0.25)
        XCTAssertEqual(row.player, name)
        XCTAssertTrue(row.spoken.hasPrefix(name + "."))
    }

    func testAccessibilitySizesStackAndOrdinarySizesPairSideBySide() {
        for size in [DynamicTypeSize.accessibility1, .accessibility3, .accessibility5] {
            XCTAssertTrue(MLBHomeRunComparison11284.stacks(at: size), "\(size)")
        }
        for size in [DynamicTypeSize.small, .large, .xxxLarge] {
            XCTAssertFalse(MLBHomeRunComparison11284.stacks(at: size), "\(size)")
        }
    }

    func testBothFiguresShareOneScaledSizeOfAtLeast26pt() {
        XCTAssertGreaterThanOrEqual(MLBHomeRunComparison11284.figurePointSize, 26)
    }

    func testAPlayersMarkFollowsTheirOriginalIDNotTheirRow() {
        let a = entry("s:jeremy pena|home_runs|full_game|ge:1|over", saved: 0.145, final: 1)
        let b = entry("s:jose altuve|home_runs|full_game|ge:1|over", saved: 0.1, final: 1)
        let forward = MLBHomeRunComparison11284.rows(constructed([a, b]))
        let reversed = MLBHomeRunComparison11284.rows(constructed([b, a]))
        XCTAssertEqual(forward[0].glyph, reversed[1].glyph)
        XCTAssertEqual(forward[1].glyph, reversed[0].glyph)
        XCTAssertEqual(MLBHomeRunComparison11284.glyph(for: a.original.id),
                       MLBHomeRunComparison11284.glyph(for: a.original.id))
    }
}
