import XCTest
@testable import Bain_Luck

/// #5176 — the iPhone Player Props card dropped every "Most Receiving Yards" /
/// "Most Rushing Yards" market, because its player ladders are built only from
/// `Player: N+` outcomes and a field's outcome is a bare name.
///
/// Every row below is served verbatim by `/api/events/{id}/game-markets` on
/// 2026-09-28 01:20Z: LAR@DEN 14780548 (live) and SEA–WAS 14781702 (final).
/// The admission half matters as much as the drawing half: the same guard also
/// drops Polymarket O/U legs, Yes/No team markets and Kalshi "Ladder" rows, and
/// none of them is a field.
final class PlayerPropsField5176Tests: XCTestCase {

    private func props(_ json: String) throws -> [GameMarketPlayerProp] {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode([GameMarketPlayerProp].self, from: Data(json.utf8))
    }

    /// LAR@DEN, live: Most Receiving Yards as served (3 legs), plus one real
    /// ladder rung that must stay the player cards' business.
    private let liveDenver = """
    [
     {"market_name": "Los Angeles Rams vs Denver: Most Receiving Yards", "outcome_name": "Courtland Sutton",
      "threshold": null, "over_probability": 0.1, "pregame_mark": 0.1, "source": "kalshi"},
     {"market_name": "Los Angeles Rams vs Denver: Most Receiving Yards", "outcome_name": "Davante Adams",
      "threshold": null, "over_probability": 0.89, "pregame_mark": 0.195, "source": "kalshi"},
     {"market_name": "Los Angeles Rams vs Denver: Most Receiving Yards", "outcome_name": "Jaylen Waddle",
      "threshold": null, "over_probability": 0.77, "pregame_mark": 0.145, "source": "kalshi"},
     {"market_name": "Los Angeles Rams vs Denver: Receiving Yards", "outcome_name": "Davante Adams: 70+",
      "threshold": 70.0, "over_probability": 0.62, "pregame_mark": 0.3, "source": "kalshi"}
    ]
    """

    // MARK: - The reported defect

    func testTheLiveFieldIsBuiltWithEveryLegLikeliestFirst() throws {
        let fields = PlayerPropsField.fields(from: try props(liveDenver))
        XCTAssertEqual(fields.count, 1)
        XCTAssertEqual(fields.first?.title, "Most Receiving Yards")
        XCTAssertEqual(fields.first?.candidates.map(\.name),
                       ["Davante Adams", "Jaylen Waddle", "Courtland Sutton"])
        XCTAssertEqual(fields.first?.candidates.map(\.probability), [0.89, 0.77, 0.1])
        XCTAssertEqual(fields.first?.candidates.first?.pregameMark, 0.195)
    }

    /// Unnormalised, like the web and every leaderboard in the app: 89% stays 89%
    /// even though the three legs sum to 176%.
    func testEachLegKeepsItsOwnPrice() throws {
        let legs = PlayerPropsField.fields(from: try props(liveDenver)).first?.candidates ?? []
        XCTAssertEqual(legs.map { PlayerPropsPricing.displayPercent($0.probability) }, [89, 77, 10])
    }

    /// SEA–WAS, final: the server graded the leader. He comes first whatever the
    /// order the rows arrived in, and the losers keep a verdict too.
    func testAFinishedFieldPutsTheGradedLeaderFirst() throws {
        let json = """
        [
         {"market_name": "Seattle vs Washington: Most Rushing Yards", "outcome_name": "Jadarian Price",
          "threshold": null, "over_probability": 0.0, "pregame_mark": 0.47, "hit": false, "source": "kalshi"},
         {"market_name": "Seattle vs Washington: Most Rushing Yards", "outcome_name": "Marcus Mariota",
          "threshold": null, "over_probability": 0.0, "pregame_mark": 0.07, "hit": false, "source": "kalshi"},
         {"market_name": "Seattle vs Washington: Most Rushing Yards", "outcome_name": "Jacory Croskey-Merritt",
          "threshold": null, "over_probability": 1.0, "pregame_mark": 0.27, "hit": true, "source": "kalshi"}
        ]
        """
        let field = try XCTUnwrap(PlayerPropsField.fields(from: try props(json)).first)
        XCTAssertTrue(field.isGraded)
        XCTAssertEqual(field.candidates.first?.name, "Jacory Croskey-Merritt")
        XCTAssertEqual(field.candidates.first?.hit, true)
        XCTAssertEqual(field.candidates.dropFirst().map(\.hit), [false, false])
    }

    /// On a graded field the leader leads even where his price does not (a
    /// stale leg can sit above him). Probability alone would put Price first.
    func testTheGradeOutranksThePrice() {
        let ordered = PlayerPropsField.ordered([
            .init(name: "Jadarian Price", probability: 0.6, pregameMark: nil, hit: false),
            .init(name: "Jacory Croskey-Merritt", probability: 0.4, pregameMark: nil, hit: true),
        ])
        XCTAssertEqual(ordered.map(\.name), ["Jacory Croskey-Merritt", "Jadarian Price"])
    }

    /// SEA–WAS, final: every loser settles at 0%, so the pregame mark orders
    /// them — McLaurin (13%) above Barner (4%) and Williams (3%), and a leg with
    /// no mark last. Alphabetical order hid McLaurin behind "+4 more".
    func testSettledLosersOrderByWhoWasExpected() {
        let ordered = PlayerPropsField.ordered([
            .init(name: "AJ Barner", probability: 0, pregameMark: 0.04, hit: false),
            .init(name: "Antonio Williams", probability: 0, pregameMark: 0.03, hit: false),
            .init(name: "Aaron Nomark", probability: 0, pregameMark: nil, hit: false),
            .init(name: "Terry McLaurin", probability: 0, pregameMark: 0.13, hit: false),
            .init(name: "Jaxon Smith-Njigba", probability: 1, pregameMark: 0.615, hit: true),
        ])
        XCTAssertEqual(ordered.map(\.name),
                       ["Jaxon Smith-Njigba", "Terry McLaurin", "AJ Barner", "Antonio Williams", "Aaron Nomark"])
    }

    /// Two equal prices keep one order across launches.
    func testEqualPricesOrderByName() {
        let ordered = PlayerPropsField.ordered([
            .init(name: "Rashid Shaheed", probability: 0.2, pregameMark: nil, hit: nil),
            .init(name: "Nick Kallerup", probability: 0.2, pregameMark: nil, hit: nil),
        ])
        XCTAssertEqual(ordered.map(\.name), ["Nick Kallerup", "Rashid Shaheed"])
    }

    // MARK: - Nothing that is not a field gets in

    func testTheShapesTheColonGuardAlsoDropsAreNotFields() throws {
        let json = """
        [
         {"market_name": "Dyami Brown: Receiving Yards O/U 29.5", "outcome_name": "Over",
          "threshold": null, "over_probability": 0.4, "source": "polymarket"},
         {"market_name": "Rams vs. Broncos: Both Teams to Score Points - 2Q", "outcome_name": "Yes",
          "threshold": null, "over_probability": 0.7, "source": "polymarket"},
         {"market_name": "Los Angeles Rams vs Denver: Receiving Yards Ladder", "outcome_name": "Davante Adams",
          "threshold": null, "over_probability": 0.225, "source": "kalshi"},
         {"market_name": "Los Angeles Rams vs Denver: Most Receiving Yards", "outcome_name": "No",
          "threshold": null, "over_probability": 0.3, "source": "kalshi"},
         {"market_name": "Los Angeles Rams vs Denver: Most Receiving Yards", "outcome_name": "Davante Adams: 100+",
          "threshold": null, "over_probability": 0.3, "source": "kalshi"},
         {"market_name": "Los Angeles Rams vs Denver: Most Receiving Yards", "outcome_name": "Davante Adams",
          "threshold": 100.0, "over_probability": 0.3, "source": "kalshi"},
         {"market_name": "Most Receiving Yards", "outcome_name": "Davante Adams",
          "threshold": null, "over_probability": 0.3, "source": "kalshi"},
         {"market_name": "Los Angeles Rams vs Denver: Most", "outcome_name": "Davante Adams",
          "threshold": null, "over_probability": 0.3, "source": "kalshi"}
        ]
        """
        for prop in try props(json) {
            XCTAssertFalse(PlayerPropsField.isFieldLeg(prop),
                           "\(prop.marketName) / \(prop.outcomeName) was admitted as a field leg")
        }
        XCTAssertTrue(PlayerPropsField.fields(from: try props(json)).isEmpty)
    }

    func testAPlayerLadderRungIsNotAFieldLeg() throws {
        let rung = try XCTUnwrap(try props(liveDenver).last)
        XCTAssertFalse(PlayerPropsField.isFieldLeg(rung))
    }

    // MARK: - What a field may not print

    /// #5176's own filed specimen read 37% · 37% · 37% — the no-book placeholder
    /// #5137 hides on ladders. Unpriced and ungraded, it is not drawn.
    func testAFlatUngradedFieldIsNotDrawn() throws {
        let json = """
        [
         {"market_name": "New England vs Seattle: Most Receiving Yards", "outcome_name": "Rashid Shaheed",
          "threshold": null, "over_probability": 0.37, "source": "kalshi"},
         {"market_name": "New England vs Seattle: Most Receiving Yards", "outcome_name": "Nick Kallerup",
          "threshold": null, "over_probability": 0.37, "source": "kalshi"},
         {"market_name": "New England vs Seattle: Most Receiving Yards", "outcome_name": "Montorie Foster Jr.",
          "threshold": null, "over_probability": 0.37, "source": "kalshi"}
        ]
        """
        XCTAssertTrue(PlayerPropsField.fields(from: try props(json)).isEmpty)
    }

    /// A graded field is drawn even when its prices are flat: the verdict is true.
    func testAFlatGradedFieldIsStillDrawn() throws {
        let json = """
        [
         {"market_name": "Seattle vs Washington: Most Receiving Yards", "outcome_name": "Cooper Kupp",
          "threshold": null, "over_probability": 0.0, "hit": false, "source": "kalshi"},
         {"market_name": "Seattle vs Washington: Most Receiving Yards", "outcome_name": "AJ Barner",
          "threshold": null, "over_probability": 0.0, "hit": false, "source": "kalshi"}
        ]
        """
        XCTAssertEqual(PlayerPropsField.fields(from: try props(json)).count, 1)
    }

    func testALegWithNoPriceIsDroppedAndADuplicateNameCountsOnce() throws {
        let json = """
        [
         {"market_name": "Los Angeles Rams vs Denver: Most Rushing Yards", "outcome_name": "Kyren Williams",
          "threshold": null, "over_probability": 0.95, "source": "kalshi"},
         {"market_name": "Los Angeles Rams vs Denver: Most Rushing Yards", "outcome_name": "Kyren Williams",
          "threshold": null, "over_probability": 0.5, "source": "kalshi"},
         {"market_name": "Los Angeles Rams vs Denver: Most Rushing Yards", "outcome_name": "Blake Corum",
          "threshold": null, "over_probability": null, "source": "kalshi"},
         {"market_name": "Los Angeles Rams vs Denver: Most Rushing Yards", "outcome_name": "J.K. Dobbins",
          "threshold": null, "over_probability": 0.34, "source": "kalshi"}
        ]
        """
        let field = try XCTUnwrap(PlayerPropsField.fields(from: try props(json)).first)
        XCTAssertEqual(field.candidates.map(\.name), ["Kyren Williams", "J.K. Dobbins"])
        XCTAssertEqual(field.candidates.first?.probability, 0.95)
    }

    /// Two fields, stable order, never merged across markets.
    func testTwoFieldsStayApartInAStableOrder() throws {
        let json = """
        [
         {"market_name": "Los Angeles Rams vs Denver: Most Rushing Yards", "outcome_name": "Kyren Williams",
          "threshold": null, "over_probability": 0.95, "source": "kalshi"},
         {"market_name": "Los Angeles Rams vs Denver: Most Receiving Yards", "outcome_name": "Davante Adams",
          "threshold": null, "over_probability": 0.89, "source": "kalshi"}
        ]
        """
        let fields = PlayerPropsField.fields(from: try props(json))
        XCTAssertEqual(fields.map(\.title), ["Most Receiving Yards", "Most Rushing Yards"])
        XCTAssertEqual(fields.map { $0.candidates.count }, [1, 1])
    }

    // MARK: - Caption

    func testTheCaptionSpeaksOfLeadingAndTakesTheLaddersTense() {
        XCTAssertEqual(PlayerPropsField.caption(eventStatus: "live", commenceTime: nil, isGraded: false),
                       "chance of leading")
        XCTAssertEqual(PlayerPropsField.caption(eventStatus: "completed", commenceTime: nil, isGraded: true),
                       "chance of leading")
        XCTAssertEqual(PlayerPropsField.caption(eventStatus: "completed", commenceTime: nil, isGraded: false),
                       "last quoted chance")
    }

    // MARK: - The card draws it (source scan)

    private func cardSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("PlayerPropsCardView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// If this fails, the scans below are asserting about an empty string.
    func testTheScanCanSeeTheFileItIsAbout() throws {
        let source = try cardSource()
        XCTAssertGreaterThan(source.count, 5_000)
        XCTAssertTrue(source.contains("struct PlayerPropsCardView"))
    }

    /// A rule nothing calls is an inert ship; and a card that still returns
    /// EmptyView when it has no player ladders hides a fields-only page.
    func testTheCardBuildsItsFieldsAndDrawsThemWithoutPlayerCards() throws {
        let source = try cardSource()
        XCTAssertTrue(source.contains("PlayerPropsField.fields(from: playerProps)"),
                      "the card no longer asks PlayerPropsField for its fields — #5176")
        XCTAssertTrue(source.contains("ForEach(fields)") && source.contains("fieldView(field)"),
                      "the card builds its fields and draws none of them — #5176")
        XCTAssertTrue(source.contains("if allPlayerCards.isEmpty && fields.isEmpty { EmptyView() }"),
                      "a page whose only props are fields would draw no card — #5176")
        XCTAssertFalse(source.contains("if allPlayerCards.isEmpty { EmptyView() }"),
                       "the old empty-card guard is back — #5176")
    }
}
