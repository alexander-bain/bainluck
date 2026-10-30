import SwiftUI
import XCTest
@testable import Bain_Luck

/// #11284 — the final MLB run-totals comparison (adoption brief
/// `mlb-total-target-adoption-20261027`): the final total against every
/// offered full-game line, the selected line's pregame chance, and the
/// source's result as its own field.
///
/// FIXTURES, AND WHAT EACH ONE IS:
/// - `event-15321836-game-markets-11284-mlb-final.20260930.json` is the
///   retained captured original (Houston Astros 3–7 Chicago White Sox, final;
///   sha256 42dfb489…), read unchanged through the production deck with the
///   page's score tuple home 3 / away 7. Its thirteen run lines carry no
///   admitted pregame chance; eight are Won and five Lost at the source.
/// - Every other case edits one value of that built card and says so: those
///   are CONSTRUCTED CONTROLS, never claimed as observed data.
@MainActor
final class MLBTotalTargetsPresentation11284Tests: XCTestCase {
    private static let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appendingPathComponent("Fixtures")
        .appendingPathComponent("event-15321836-game-markets-11284-mlb-final.20260930.json")

    /// The retained lines in order, by their original option keys and source results.
    private static let retainedLines: [(line: Double, key: String, result: String)] = [
        (2.5, "o:244311416", "Won"), (3.5, "o:244311415", "Won"), (4.5, "o:244311414", "Won"),
        (5.5, "o:244311413", "Won"), (6.5, "o:244311412", "Won"), (7.5, "o:244311411", "Won"),
        (8.5, "o:244311410", "Won"), (9.5, "o:244311417", "Won"), (10.5, "o:244311422", "Lost"),
        (11.5, "o:244311421", "Lost"), (12.5, "o:244311420", "Lost"), (13.5, "o:244311419", "Lost"),
        (14.5, "o:244311418", "Lost"),
    ]
    private static let opening = "o:244311417"
    private static let next = "o:244311422"

    // MARK: - Helpers

    /// The retained card through the production deck. Only the decoding
    /// boilerplate is reproduced here; admission is the deck's own.
    private func retained(home: Int? = 3, away: Int? = 7) throws -> MLBTotalsCard11284 {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let markets = try decoder.decode(GameMarketsResponse.self, from: Data(contentsOf: Self.fixture))
        let cards = MLBFinalDeck11284.cards(MLBFinalDeckInput11284(
            eventID: 15321836, sportKey: "baseball_mlb", status: "completed",
            homeTeam: "Houston Astros", awayTeam: "Chicago White Sox",
            homeScore: home, awayScore: away, gameMarkets: markets, relatedFutures: nil))
        let totals = cards.compactMap { card -> MLBTotalsCard11284? in
            if case .totals(let totals) = card { return totals }
            return nil
        }
        return try XCTUnwrap(totals.first, "the retained capture builds its run-totals card")
    }

    private func present(_ card: MLBTotalsCard11284, key: String? = opening,
                         home: Int? = 3, away: Int? = 7) -> MLBTotalTargetsPresentation11284 {
        MLBTotalTargetsPresentation11284(card: card, selectedOptionKey: key,
                                         homeName: "Houston Astros", awayName: "Chicago White Sox",
                                         homeScore: home, awayScore: away)
    }

    /// CONSTRUCTED: the same card with its total replaced.
    private func withTotal(_ card: MLBTotalsCard11284, _ total: Int?) -> MLBTotalsCard11284 {
        MLBTotalsCard11284(eventID: card.eventID, lines: card.lines, actualTotal: total)
    }

    /// CONSTRUCTED: one line of the card edited.
    private func editing(_ card: MLBTotalsCard11284, key: String,
                         pregame: Double? = nil, result: MLBVenueResult11284? = nil) -> MLBTotalsCard11284 {
        let lines = card.lines.map { line in
            guard line.optionKey == key else { return line }
            return MLBTotalsCard11284.Line(optionKey: line.optionKey, line: line.line, label: line.label,
                                           pregame: pregame ?? line.pregame,
                                           venueResult: result ?? line.venueResult, original: line.original)
        }
        return MLBTotalsCard11284(eventID: card.eventID, lines: lines, actualTotal: card.actualTotal)
    }

    // MARK: - The retained final

    func testTheRetainedFinalKeepsEveryLineItsKeyAndItsSourceResult() throws {
        let p = present(try retained())
        XCTAssertEqual(p.choices.map(\.optionKey), Self.retainedLines.map(\.key), "all 13 originals, in line order")
        XCTAssertEqual(p.choices.map(\.text), Self.retainedLines.map { NBALadderCard9483.number($0.line) })
        XCTAssertEqual(p.lineTicks, Self.retainedLines.map(\.line), "the card's own coordinates, no 3+ conversion")
        XCTAssertEqual(p.card.lines.map(\.venueResult.label), Self.retainedLines.map(\.result))
        XCTAssertEqual(p.choices.filter(\.isSelected).map(\.optionKey), [Self.opening])
        XCTAssertEqual(p.actualValue, "10")
        XCTAssertEqual(p.bar, .stacked(home: 3, away: 7))
        XCTAssertNil(p.breakdownNote)
        XCTAssertEqual(p.heading, "Over 9.5 runs")
        XCTAssertEqual(p.marker, 9.5, "the diamond stands on 9.5, just left of the bar's end at 10")
        XCTAssertEqual(p.markerKey, "Selected line · 9.5")
        XCTAssertEqual(p.sourceResult, "Won")
        XCTAssertEqual(p.axisLabels, [0, 5, 10, 15])
        XCTAssertEqual(p.axisUpper, 15)
    }

    func testEveryRetainedLineSaysItsPregameChanceIsUnavailable() throws {
        let card = try retained()
        for line in card.lines {
            let p = present(card, key: line.optionKey)
            XCTAssertEqual(p.pregameValue, "Unavailable", line.label)
            XCTAssertEqual(p.pregameLabel, "Pregame chance · \(line.label)")
            XCTAssertEqual(p.pregameAccessibilityLabel, "Pregame chance, unavailable.", line.label)
            for spoken in [p.pregameValue, p.pregameAccessibilityLabel] {
                XCTAssertFalse(spoken.contains("%"), "a settled 0/100 quote is never a chance: \(spoken)")
            }
        }
    }

    func testMovingFromNinePointFiveToTenPointFiveFlipsTheComparisonOnly() throws {
        let card = try retained()
        let below = present(card, key: Self.opening), above = present(card, key: Self.next)
        XCTAssertEqual(below.comparison, "Final 10 runs · above this line")
        XCTAssertEqual(above.comparison, "Final 10 runs · below this line")
        XCTAssertEqual(above.heading, "Over 10.5 runs")
        XCTAssertEqual(above.marker, 10.5, "now just right of the bar's end")
        XCTAssertEqual(above.sourceResult, "Lost")
        XCTAssertEqual(above.axisUpper, below.axisUpper, "the scale does not move with the selection")
        XCTAssertEqual(above.axisLabels, below.axisLabels)
        XCTAssertEqual(above.lineTicks, below.lineTicks)
        XCTAssertEqual(above.bar, below.bar)
        XCTAssertEqual(above.actualValue, below.actualValue)
    }

    // MARK: - Constructed controls

    func testControlASuppliedPregameChancePrintsAsAChance() throws {
        // CONSTRUCTED: the 9.5 line given an admitted pregame chance of 62%.
        let p = present(editing(try retained(), key: Self.opening, pregame: 0.62))
        XCTAssertEqual(p.pregameValue, "62%")
        XCTAssertEqual(p.pregameLabel, "Pregame chance · Over 9.5 runs")
        XCTAssertEqual(p.pregameAccessibilityLabel, "Pregame chance, 62%.")
    }

    func testControlTheSourceResultIsTheLinesOwnEvenAgainstTheArithmetic() throws {
        // CONSTRUCTED: the 9.5 line graded Lost although 10 runs is above it.
        let p = present(editing(try retained(), key: Self.opening, result: .lost))
        XCTAssertEqual(p.comparison, "Final 10 runs · above this line", "the score against the number")
        XCTAssertEqual(p.sourceResult, "Lost", "the source's verdict, never read off the comparison")
        XCTAssertEqual(p.sourceAccessibilityLabel, "Source result, Lost.")
        let chip = try XCTUnwrap(p.choices.first { $0.optionKey == Self.opening })
        XCTAssertEqual(chip.accessibilityLabel, "Over 9.5 runs. Source result Lost.")
    }

    func testControlNoOrAWithdrawnSelectionShowsUnavailableAndNoDetails() throws {
        let card = try retained()
        // CONSTRUCTED: the 9.5 line withdrawn from a later card while the host still names it.
        let withdrawn = MLBTotalsCard11284(eventID: card.eventID,
                                           lines: card.lines.filter { $0.optionKey != Self.opening },
                                           actualTotal: card.actualTotal)
        let cases: [(String, MLBTotalTargetsPresentation11284)] = [
            ("nil selection", present(card, key: nil)),
            ("unknown key", present(card, key: "o:0")),
            ("withdrawn key", present(withdrawn, key: Self.opening)),
        ]
        for (name, p) in cases {
            XCTAssertNil(p.selected, name)
            XCTAssertEqual(p.heading, "Selected line unavailable", name)
            XCTAssertEqual(p.pregameValue, "Unavailable", name)
            XCTAssertEqual(p.pregameLabel, "Pregame chance", name)
            XCTAssertNil(p.comparison, name)
            XCTAssertNil(p.sourceResult, name)
            XCTAssertNil(p.marker, name)
            XCTAssertNil(p.markerKey, name)
            XCTAssertNil(p.detailsID, "no Details for a substituted line: \(name)")
            XCTAssertTrue(p.choices.allSatisfy { !$0.isSelected }, "never the card's default: \(name)")
            XCTAssertEqual(p.actualValue, "10", "the total stays: \(name)")
            XCTAssertEqual(p.selectedAccessibilityLabel, "Selected line unavailable.", name)
        }
        XCTAssertEqual(cases[2].1.choices.count, 12, "every line the later card still carries stays selectable")
    }

    func testControlNoTotalDrawsNoBarAndNoComparison() throws {
        // The retained capture read with no printed score (the page prints none).
        let unprinted = try retained(home: nil, away: nil)
        XCTAssertNil(unprinted.actualTotal)
        // CONSTRUCTED: a negative total is not a run count.
        let negative = withTotal(try retained(), -1)
        for (name, p) in [("no score", present(unprinted, home: nil, away: nil)), ("negative", present(negative))] {
            XCTAssertEqual(p.bar, .none, name)
            XCTAssertEqual(p.actualValue, "Unavailable", name)
            XCTAssertNil(p.comparison, name)
            XCTAssertNil(p.breakdownNote, name)
            XCTAssertEqual(p.actualAccessibilityLabel, "Final total unavailable.", name)
            XCTAssertEqual(p.sourceResult, "Won", "the source result is still the line's own: \(name)")
            XCTAssertEqual(p.axisUpper, 15, "the lines alone set the axis: \(name)")
        }
    }

    func testControlTheStackedBarNeedsBothCountsNonnegativeAndSummingToTheTotal() throws {
        let card = try retained()
        XCTAssertEqual(present(card, home: 3, away: 7).bar, .stacked(home: 3, away: 7))
        // CONSTRUCTED: breakdowns that cannot be drawn; the total stays, alone.
        let rejected: [(String, Int?, Int?)] = [
            ("missing home", nil, 7), ("missing away", 3, nil), ("both missing", nil, nil),
            ("mismatched", 4, 7), ("negative", -1, 11), ("overflow", Int.max, 1), ("both max", Int.max, Int.max),
        ]
        for (name, home, away) in rejected {
            let p = present(card, home: home, away: away)
            XCTAssertEqual(p.bar, .totalOnly(10), name)
            XCTAssertEqual(p.breakdownNote, "Team breakdown unavailable", name)
            XCTAssertEqual(p.actualValue, "10", name)
            XCTAssertEqual(p.actualAccessibilityLabel, "Final total, 10 runs. Team breakdown unavailable.", name)
        }
    }

    func testControlZeroTeamCountsStillStack() throws {
        // CONSTRUCTED: a 0–7 and a 0–0 final on the retained lines.
        let shutout = present(withTotal(try retained(), 7), home: 0, away: 7)
        XCTAssertEqual(shutout.bar, .stacked(home: 0, away: 7))
        XCTAssertEqual(shutout.actualAccessibilityLabel, "Final total, 7 runs. Houston Astros 0, Chicago White Sox 7.")
        let scoreless = present(withTotal(try retained(), 0), home: 0, away: 0)
        XCTAssertEqual(scoreless.bar, .stacked(home: 0, away: 0))
        XCTAssertEqual(scoreless.actualValue, "0", "zero is a count, not unavailable")
        XCTAssertEqual(scoreless.comparison, "Final 0 runs · below this line")
    }

    func testControlATotalAboveEveryLineWidensTheAxisToInclude() throws {
        // CONSTRUCTED: a 9–8 final, above the top line of 14.5.
        let p = present(withTotal(try retained(), 17), home: 9, away: 8)
        XCTAssertEqual(p.axisUpper, 20)
        XCTAssertEqual(p.axisLabels, [0, 5, 10, 15, 20])
        XCTAssertEqual(p.bar, .stacked(home: 9, away: 8))
    }

    // MARK: - Host intents

    func testSelectionPassesTheOptionKeyAndDetailsTheBuiltOriginalID() throws {
        let card = try retained()
        var selections: [String] = [], details: [String] = []
        func view(_ key: String?, expanded: Bool = true) -> MLBTotalTargetsCardView11284 {
            MLBTotalTargetsCardView11284(
                card: card, selectedOptionKey: key, homeName: "Houston Astros", awayName: "Chicago White Sox",
                homeColor: .blue, awayColor: .green, homeScore: 3, awayScore: 7, expanded: expanded,
                onSelect: { selections.append($0) }, onDetails: { details.append($0) })
        }
        let opened = view(Self.opening)
        for choice in opened.presentation.choices { opened.select(choice) }
        XCTAssertEqual(selections, Self.retainedLines.map(\.key), "every line reachable by its own option key")

        opened.requestDetails()
        let original = try XCTUnwrap(card.lines.first { $0.optionKey == Self.opening }).original.id
        XCTAssertEqual(details, [original], "the built card's original id")
        XCTAssertNotEqual(original, Self.opening, "Details never assumes the option key is the original id")

        view(nil).requestDetails()
        view("o:0").requestDetails()
        XCTAssertEqual(details, [original], "no Details intent without a selected line")
    }

    func testTheSpokenFieldsAreDistinct() throws {
        let p = present(try retained())
        XCTAssertEqual(p.actualAccessibilityLabel, "Final total, 10 runs. Houston Astros 3, Chicago White Sox 7.")
        XCTAssertEqual(p.selectedAccessibilityLabel, "Selected line, Over 9.5 runs. Final 10 runs · above this line.")
        XCTAssertEqual(p.pregameAccessibilityLabel, "Pregame chance, unavailable.")
        XCTAssertEqual(p.sourceAccessibilityLabel, "Source result, Won.")
        XCTAssertEqual(p.choices.map(\.accessibilityLabel).first, "Over 2.5 runs. Source result Won.")
        XCTAssertEqual(p.choices.map(\.accessibilityLabel).last, "Over 14.5 runs. Source result Lost.")
        let spoken = [p.actualAccessibilityLabel, p.selectedAccessibilityLabel, p.pregameAccessibilityLabel,
                      p.sourceAccessibilityLabel ?? ""]
        XCTAssertEqual(Set(spoken).count, spoken.count, "each field is its own sentence")
    }
}
