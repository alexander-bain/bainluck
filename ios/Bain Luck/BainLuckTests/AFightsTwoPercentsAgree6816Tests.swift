import XCTest
@testable import Bain_Luck

/// #6816 — **a fight's two displayed percentages agree.**
///
/// Seen on THIS screen, simulator against production, 2026-09-17 22:39Z:
///
///     Arman Tsarukyan   74%
///     Mauricio Ruffy    28%      <- 102%
///
/// The quotes are 0.735 / 0.275. A venue's half-cent grid puts both sides of
/// one bout on a rounding boundary, and a row that formats each fighter on its
/// own rounds both up. The combat builder now decides the pair once and serves
/// it as `rendered_percent` on each of a bout's two rows; this file is the
/// phone's decode of that, and the string the row actually prints.
///
/// ## What these fixtures are, honestly
///
/// | file | what it is |
/// |---|---|
/// | `event-ufc-26sep19.served6816.SYNTHETIC.json` | the PATCHED BUILDER'S OWN OUTPUT for the names and quotes of the public response Native209 saved 2026-09-17 (sha256 `2ba8d8cb…`). SYNTHETIC: the rows that drove the builder are invented. `backend/tests/test_combat_pair_display_6816.py` pins it to the builder byte for byte, and the web arm reads the identical file. Nobody typed these integers. |
/// | `event-ufc-26sep19.20260917.json` | PRODUCTION, the existing #6667 capture — a payload from BEFORE the field shipped, so it is the old-payload control. |
///
/// What is asserted is the STRING the row prints —
/// `formatProbabilityOrDash(_:renderedPercent:)` over the model's `percents`,
/// the exact expression `ConceptCardView` uses — not merely that a field decoded.
final class AFightsTwoPercentsAgree6816Tests: XCTestCase {

    // MARK: - Harness

    private static var testsDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    }

    /// The app's own strategy (`APIClient.init`).
    private static var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private static func card(_ name: String) throws -> ConceptCardPresentation {
        let url = testsDir.appendingPathComponent("Fixtures").appendingPathComponent(name)
        return ConceptCardPresentation(
            response: try decoder.decode(EventConceptResponse.self, from: Data(contentsOf: url)))
    }

    private static func card(json: String) throws -> ConceptCardPresentation {
        ConceptCardPresentation(
            response: try decoder.decode(EventConceptResponse.self, from: Data(json.utf8)))
    }

    /// One upcoming two-fighter bout, with whatever `outcomes` the test names.
    private static func bout(outcomes: String) throws -> ConceptBoutRow {
        let card = try card(json: """
        {"event":{"key":"event:ufc:26sep19","status":"upcoming"},
         "primary":{"kind":"co_equal_list","evolution_market_id":1},
         "children":[{"market_id":1,"market_name":"331: Tsarukyan vs Ruffy","source":"kalshi",
                      "kind":"fight","settled":false,"probability":0.735,"outcomes":\(outcomes)}]}
        """)
        return try XCTUnwrap(card.bouts.first)
    }

    /// What `ConceptCardView` prints for each fighter — its own expression.
    private static func printed(_ bout: ConceptBoutRow) -> [String] {
        bout.fighters.enumerated().map { index, fighter in
            formatProbabilityOrDash(
                fighter.probability,
                renderedPercent: bout.percents.indices.contains(index) ? bout.percents[index] : nil)
        }
    }

    private static func total(_ strings: [String]) -> Int {
        strings.compactMap { Int($0.filter(\.isNumber)) }.reduce(0, +)
    }

    // MARK: - The served card

    func testTheNamedBoutsPrintAPairThatAgrees() throws {
        let card = try Self.card("event-ufc-26sep19.served6816.SYNTHETIC.json")
        let expected: [String: [String]] = [
            "331: Tsarukyan vs Ruffy": ["73%", "27%"],
            "331: Chikadze vs Brito": ["78%", "22%"],
            "331: Pitbull vs Choi": ["72%", "28%"],
            "331: Aswell vs Yoo": ["67%", "33%"],
        ]
        for (title, numbers) in expected {
            let bout = try XCTUnwrap(card.bouts.first { $0.title == title }, title)
            XCTAssertEqual(Self.printed(bout), numbers, title)
        }
    }

    func testEveryBoutOnTheServedCardPrintsOneHundred() throws {
        let card = try Self.card("event-ufc-26sep19.served6816.SYNTHETIC.json")
        XCTAssertEqual(card.bouts.count, 12)
        for bout in card.bouts {
            XCTAssertEqual(Self.total(Self.printed(bout)), 100, bout.title)
        }
    }

    func testNoProbabilityMovedToGetThere() throws {
        let card = try Self.card("event-ufc-26sep19.served6816.SYNTHETIC.json")
        let bout = try XCTUnwrap(card.bouts.first { $0.title == "331: Tsarukyan vs Ruffy" })
        XCTAssertEqual(bout.fighters.map(\.name), ["Arman Tsarukyan", "Mauricio Ruffy"])
        XCTAssertEqual(bout.fighters.map(\.probability), [0.735, 0.275])
        XCTAssertEqual(bout.percents, [73, 27])
    }

    // MARK: - The old payload

    func testAPayloadFromBeforeTheFieldDecodesAndPrintsAsItDid() throws {
        let card = try Self.card("event-ufc-26sep19.20260917.json")
        XCTAssertEqual(card.bouts.count, 12)
        let bout = try XCTUnwrap(card.bouts.first { $0.title == "331: Tsarukyan vs Ruffy" })
        XCTAssertEqual(bout.percents, [nil, nil])
        XCTAssertEqual(
            Self.printed(bout),
            bout.fighters.map { formatProbabilityOrDash($0.probability) })
    }

    // MARK: - Both or neither

    func testOneServedSideIsNeverUsedAlone() throws {
        let bout = try Self.bout(outcomes: """
        [{"name":"Arman Tsarukyan","probability":0.735,"rendered_percent":73},
         {"name":"Mauricio Ruffy","probability":0.275}]
        """)
        XCTAssertEqual(bout.percents, [nil, nil])
        XCTAssertEqual(Self.printed(bout), [formatProbabilityOrDash(0.735), formatProbabilityOrDash(0.275)])
    }

    func testTheServersOwnNoClaimPrintsAsBefore() throws {
        let bout = try Self.bout(outcomes: """
        [{"name":"Arman Tsarukyan","probability":0.735,"rendered_percent":null},
         {"name":"Mauricio Ruffy","probability":0.275,"rendered_percent":null}]
        """)
        XCTAssertEqual(bout.percents, [nil, nil])
    }

    /// 🔴 The reason `EventConceptOutcome.init(from:)` is written out. Under the
    /// synthesized decode each of these THROWS, the throw fails the child, and a
    /// malformed display nicety deletes the whole bout from the card.
    func testAMalformedServedValueCostsTheIntegerNotTheBout() throws {
        for bad in ["\"73\"", "72.5", "true", "[73]"] {
            let bout = try Self.bout(outcomes: """
            [{"name":"Arman Tsarukyan","probability":0.735,"rendered_percent":\(bad)},
             {"name":"Mauricio Ruffy","probability":0.275,"rendered_percent":27}]
            """)
            XCTAssertEqual(bout.fighters.count, 2, bad)
            XCTAssertEqual(bout.percents, [nil, nil], bad)
        }
    }

    func testAnOutOfRangeServedValueIsRefusedForThePair() throws {
        let bout = try Self.bout(outcomes: """
        [{"name":"Arman Tsarukyan","probability":0.735,"rendered_percent":173},
         {"name":"Mauricio Ruffy","probability":0.275,"rendered_percent":-73}]
        """)
        XCTAssertEqual(bout.percents, [nil, nil])
    }

    func testTheTopTwoOfALongerMarketAreNeverAPair() throws {
        let bout = try Self.bout(outcomes: """
        [{"name":"Arman Tsarukyan","probability":0.735,"rendered_percent":73},
         {"name":"Mauricio Ruffy","probability":0.275,"rendered_percent":27},
         {"name":"Draw","probability":0.01,"rendered_percent":1}]
        """)
        XCTAssertEqual(bout.fighters.count, 2)
        XCTAssertEqual(bout.percents, [nil, nil])
    }

    func testStoredOrderCannotPutANumberOnTheWrongFighter() throws {
        let bout = try Self.bout(outcomes: """
        [{"name":"Mauricio Ruffy","probability":0.275,"rendered_percent":27},
         {"name":"Arman Tsarukyan","probability":0.735,"rendered_percent":73}]
        """)
        XCTAssertEqual(bout.fighters.map(\.name), ["Arman Tsarukyan", "Mauricio Ruffy"])
        XCTAssertEqual(Self.printed(bout), ["73%", "27%"])
    }

    // MARK: - What was deliberately left alone

    func testAWithheldBoutStaysWithheld() throws {
        let bout = try Self.bout(outcomes: """
        [{"name":"Brandon Wilson","probability":null,"rendered_percent":null},
         {"name":"Brian Ellis","probability":null,"rendered_percent":null}]
        """)
        XCTAssertEqual(Self.printed(bout), [formatProbabilityOrDash(nil), formatProbabilityOrDash(nil)])
    }

    func testAServedIntegerNeverPrintsOverAMissingPrice() throws {
        // Not a shape the builder emits; pinned so "no complement resurrects a
        // refused leg" does not depend on that.
        let bout = try Self.bout(outcomes: """
        [{"name":"Brandon Wilson","probability":null,"rendered_percent":73},
         {"name":"Brian Ellis","probability":null,"rendered_percent":27}]
        """)
        XCTAssertEqual(Self.printed(bout), [formatProbabilityOrDash(nil), formatProbabilityOrDash(nil)])
    }

    func testTheBoundaryMarkersStillRunOnTheProbability() throws {
        let bout = try Self.bout(outcomes: """
        [{"name":"Ann Alpha","probability":0.995,"rendered_percent":100},
         {"name":"Bea Beta","probability":0.005,"rendered_percent":0}]
        """)
        XCTAssertEqual(Self.printed(bout), [">99%", "<1%"])
    }

    func testARealFiftyFiftyStaysFiftyFifty() throws {
        let bout = try Self.bout(outcomes: """
        [{"name":"Ann Alpha","probability":0.5,"rendered_percent":50},
         {"name":"Bea Beta","probability":0.5,"rendered_percent":50}]
        """)
        XCTAssertEqual(Self.printed(bout), ["50%", "50%"])
    }

    func testNoWinnerIsInferredFromAServedInteger() throws {
        let card = try Self.card(json: """
        {"event":{"key":"event:ufc:26sep19","status":"settled"},
         "primary":{"kind":"co_equal_list","evolution_market_id":1},
         "children":[{"market_id":1,"market_name":"331: Tsarukyan vs Ruffy","source":"kalshi",
                      "kind":"fight","settled":true,"probability":1.0,
                      "outcomes":[{"name":"Arman Tsarukyan","probability":1.0,"rendered_percent":100},
                                  {"name":"Mauricio Ruffy","probability":0.0,"rendered_percent":0}]}]}
        """)
        let bout = try XCTUnwrap(card.bouts.first)
        XCTAssertTrue(bout.isSettled)
        XCTAssertNil(bout.winner, "a served 100 is a display integer, not a grade")
    }
}
