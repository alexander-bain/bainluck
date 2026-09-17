import XCTest
@testable import Bain_Luck

/// #5603 / Brief 18 — **a slap-fighting card stops wearing a UFC chip.**
///
/// `FeedConceptData.domain` is `"ufc"` for every card the MMA adapter emits: it
/// is the adapter key, the URL segment and the gradient, and it is not something
/// any source said. The card printed `domain.uppercased()`, so on production
/// **Power Slap 23** and every Dana White's Contender Series card were labelled
/// **UFC**. Measured by discover/159 on 2026-09-17: 8 of 8 concept cards on
/// `GET /api/feed?limit=150` carried `domain: "ufc"`.
///
/// The server now sends `sport_label` (discover owns that half). This target owns
/// the decode and the fallback — and **the fallback is the whole fix**, which is
/// why most of this file is about the absent-field case rather than the happy one.
final class AConceptCardNamesItsOwnSport5603Tests: XCTestCase {

    private func chip(_ sportLabel: String?, _ domain: String?) -> String {
        FeedConceptData.sportChip(sportLabel: sportLabel, domain: domain)
    }

    /// The app's own decoding strategy — `sport_label` reaches `sportLabel`
    /// through `.convertFromSnakeCase`, with no `CodingKeys` on the struct, which
    /// is why adding the property is the entire wire change.
    private func decode(_ json: String) throws -> FeedConceptData {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedConceptData.self, from: Data(json.utf8))
    }

    // MARK: - What the server says, wins

    func testADeclaredLabelIsWhatTheReaderSees() {
        XCTAssertEqual(chip("UFC", "ufc"), "UFC")
        XCTAssertEqual(chip("Combat", "ufc"), "COMBAT", "Power Slap rides the ufc adapter")
        XCTAssertEqual(chip("MMA", "ufc"), "MMA", "a schedule row with no promoter named")
    }

    func testADeclaredLabelOutranksTheRoutingDomainEvenWhenTheyDisagree() {
        // The whole point: the two fields disagreeing is the NORMAL case on this
        // adapter, not an anomaly, so the declared one must win unconditionally.
        XCTAssertEqual(chip("Combat", "ufc"), "COMBAT")
        XCTAssertEqual(chip("MMA", "ufc"), "MMA")
    }

    // MARK: - 🪤 The fallback, which is where the defect lives

    /// `sportLabel ?? domain` would pass every test above and still ship the bug.
    /// These are the payloads that spelling gets wrong: everything served before
    /// the backend half released, everything in a `URLCache`, and every device on
    /// an older build.
    func testAnAbsentLabelOnTheMixedNamespaceDegradesToCombatNeverToUFC() {
        for absent: String? in [nil, "", "   "] {
            XCTAssertEqual(
                chip(absent, "ufc"), "COMBAT",
                "\(String(describing: absent)): with nothing declared, UFC is a claim no source made — "
                + "and a blank string must fall THROUGH, not win and render an empty chip")
        }
    }

    /// The scope of that degradation is exactly one domain. Boxing is its own
    /// adapter and its own sport, so `BOXING` is true and must survive.
    func testEveryOtherDomainKeepsTheLabelItAlwaysHad() {
        XCTAssertEqual(chip(nil, "boxing"), "BOXING")
        XCTAssertEqual(chip(nil, "cycling"), "CYCLING")
        XCTAssertEqual(chip(nil, "f1"), "F1")
        XCTAssertEqual(chip(nil, "golf"), "GOLF")
    }

    func testTheMixedNamespaceIsMatchedRegardlessOfCasing() {
        for spelling in ["ufc", "UFC", "Ufc", " ufc "] {
            XCTAssertEqual(
                chip(nil, spelling), "COMBAT",
                "\(spelling.debugDescription): the domain is server-authored text")
        }
    }

    /// Nothing at all to say. Mirrors web rather than rendering a blank chip.
    func testNoLabelAndNoDomainStillNamesSomething() {
        XCTAssertEqual(chip(nil, nil), "EVENT")
        XCTAssertEqual(chip(nil, ""), "EVENT")
        XCTAssertEqual(chip("", "  "), "EVENT")
    }

    /// The chip is never empty. A blank chip is the one outcome worse than either
    /// label, and it is what a naive `?? ""` or an un-trimmed guard produces.
    func testTheChipIsNeverBlank() {
        for label: String? in [nil, "", " ", "UFC", "Combat"] {
            for domain: String? in [nil, "", " ", "ufc", "boxing"] {
                XCTAssertFalse(
                    chip(label, domain).trimmingCharacters(in: .whitespaces).isEmpty,
                    "blank chip for label \(String(describing: label)) / domain \(String(describing: domain))")
            }
        }
    }

    // MARK: - The wire

    /// An ABSENT key decodes as nil with no other change — the contract discover
    /// stated (`sport_label` is absent, never null, when there is nothing to say),
    /// and the reason this ship needs no coordination with the backend release.
    func testAPayloadWithoutTheFieldStillDecodesAndFallsBack() throws {
        let json = """
        {"key": "event:ufc:26sep19", "name": "Power Slap 23", "domain": "ufc"}
        """
        let data = try decode(json)
        XCTAssertNil(data.sportLabel)
        XCTAssertEqual(data.sportChip, "COMBAT", "the pre-release payload must not read UFC")
    }

    func testAPayloadCarryingTheFieldIsDecodedAndUsed() throws {
        let json = """
        {"key": "event:ufc:26sep19", "name": "UFC 331", "domain": "ufc", "sport_label": "UFC"}
        """
        let data = try decode(json)
        XCTAssertEqual(data.sportLabel, "UFC")
        XCTAssertEqual(data.sportChip, "UFC")
    }

    /// An explicit `null` behaves like an absent key rather than throwing — the
    /// contract says absent, but a client that reds on a null it was promised
    /// would never see is a client that breaks on the server's first slip.
    func testAnExplicitNullIsToleratedLikeAnAbsentKey() throws {
        let json = """
        {"key": "event:ufc:x", "name": "X", "domain": "ufc", "sport_label": null}
        """
        let data = try decode(json)
        XCTAssertNil(data.sportLabel)
        XCTAssertEqual(data.sportChip, "COMBAT")
    }
}
