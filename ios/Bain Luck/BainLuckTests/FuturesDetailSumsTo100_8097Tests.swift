import XCTest
@testable import Bain_Luck

/// #8097 — the futures DETAIL page is the surface one tap below the Discover
/// futures card that #8035 fixed, and it had the same defect: three renderers
/// (the share sentence, the 52pt hero numeral, and every outcome row) each
/// rounded a probability on its own, so a two-outcome complement pair quoted on
/// the venues' half-cent grid printed `60%` above `41%` in one frame.
///
/// The specimen is production, not invented: `GET /api/futures/61963212` on
/// 2026-09-22 served **Elise Mertens 0.595 / Barbora Krejcikova 0.405** — an
/// exact complement, both sides on the `.5` boundary. Measured the same day,
/// **6,743 open two-outcome complement markets sit on that boundary, 227 of them
/// tier 1.**
final class FuturesDetailSumsTo100_8097Tests: XCTestCase {

    // MARK: - Harness

    private func outcomes(_ json: String) throws -> [FuturesOutcome] {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode([FuturesOutcome].self, from: Data(json.utf8))
    }

    /// `GET /api/futures/61963212`, 2026-09-22, trimmed to the decoded fields.
    private func mertensKrejcikova() throws -> [FuturesOutcome] {
        try outcomes("""
        [
          {"id": 233891049, "name": "Elise Mertens", "probability": 0.595,
           "opening_probability": 0.57},
          {"id": 233891050, "name": "Barbora Krejcikova", "probability": 0.405,
           "opening_probability": 0.43}
        ]
        """)
    }

    // MARK: - The defect

    func test_theProductionPairPrintsOneHundred() throws {
        let field = try mertensKrejcikova()
        let percents = futuresDetailRenderedPercents(field)

        let mertens = try XCTUnwrap(percents[233891049])
        let krejcikova = try XCTUnwrap(percents[233891050])

        XCTAssertEqual(mertens + krejcikova, 100, "the page printed 60 + 41 = 101 before #8097")
        XCTAssertEqual(mertens, 60)
        XCTAssertEqual(krejcikova, 40)
    }

    /// A sum-only assertion is satisfied by moving the WRONG side — 59 + 41 also
    /// sums to 100 and is wrong twice. The leader is the number the reader
    /// anchors on, so it keeps its own value and the derived point lands on the
    /// side nobody is quoting.
    func test_theLeaderKeepsItsOwnNumberAndTheDerivedPointLandsOnTheOtherSide() throws {
        let percents = futuresDetailRenderedPercents(try mertensKrejcikova())
        XCTAssertEqual(percents[233891049], 60, "the favourite's own number must not move")
        XCTAssertEqual(percents[233891050], 40)
    }

    // MARK: - Re-sorting the table must not reprice it

    /// The reader can sort this table by name, by 24-hour change, and in either
    /// direction. The decision is taken over probability-descending order and
    /// looked up by identity, so a control that reorders rows cannot change what
    /// any row says. Deciding over the DISPLAYED order is the mutant this kills:
    /// it would hand index 0 to whoever the reader happened to sort to the top,
    /// and the underdog would keep 41 while the favourite became the derived one.
    func test_theSameOutcomeGetsTheSamePercentWhateverOrderTheFieldArrivesIn() throws {
        let served = try mertensKrejcikova()
        let reversed = Array(served.reversed())

        let a = futuresDetailRenderedPercents(served)
        let b = futuresDetailRenderedPercents(reversed)

        XCTAssertEqual(a, b, "row order is a display choice; it must not move a printed number")
        XCTAssertEqual(b[233891049], 60, "the favourite is still the favourite when served last")
        XCTAssertEqual(b[233891050], 40)
    }

    /// Ties are broken by id rather than left to `sorted(by:)`, which Swift does
    /// not guarantee to be stable — otherwise a 50/50 market could hand the
    /// headline to a different side between two reloads of the same page.
    ///
    /// ⚠️ THIS ASSERTION CANNOT FAIL ON THE TIE-BREAK, AND THAT IS RECORDED RATHER
    /// THAN PAPERED OVER. The battery's `tie-break-removed` mutant SURVIVED, and it
    /// survived because it is an EQUIVALENT mutant, not because the guard is weak:
    /// when two probabilities are equal, `first / total` is 0.5 either way, so the
    /// pair renders 50/50 whichever side is handed index 0. The tie-break buys
    /// determinism in the dictionary's construction, not a different printed
    /// number, and no behavioural test can distinguish it. Kept for that
    /// determinism; claimed as nothing more.
    func test_aTiedPairIsDecidedTheSameWayEveryTime() throws {
        let tied = try outcomes("""
        [{"id": 2, "name": "B", "probability": 0.5},
         {"id": 1, "name": "A", "probability": 0.5}]
        """)
        let first = futuresDetailRenderedPercents(tied)
        let second = futuresDetailRenderedPercents(Array(tied.reversed()))
        XCTAssertEqual(first, second)
        XCTAssertEqual(first[1], 50)
        XCTAssertEqual(first[2], 50)
    }

    // MARK: - What deliberately does NOT change

    /// The pair rule fires on a complement PAIR. A three-way field is not one,
    /// and normalising it here would invent a number no venue quoted. Asserted
    /// in the same direction the contract pins it: untouched, even when the
    /// three independently-correct percents sum to 101.
    func test_aThreeWayFieldIsLeftAlone() throws {
        let threeWay = try outcomes("""
        [{"id": 1, "name": "A", "probability": 0.605},
         {"id": 2, "name": "B", "probability": 0.235},
         {"id": 3, "name": "C", "probability": 0.165}]
        """)
        let p = futuresDetailRenderedPercents(threeWay)
        XCTAssertEqual(p[1], 61)
        XCTAssertEqual(p[2], 24)
        XCTAssertEqual(p[3], 17)
        XCTAssertEqual((p[1] ?? 0) + (p[2] ?? 0) + (p[3] ?? 0), 102,
                       "a non-pair field keeps its own arithmetic — #2088 explains those, this rule does not touch them")
    }

    /// Two outcomes that are NOT a complement (one side unpriced) are not a pair
    /// either: the rule needs two finite probabilities that sum to ~1.
    func test_aPairWithAnUnpricedSideIsNotAComplementPair() throws {
        let withdrawn = try outcomes("""
        [{"id": 1, "name": "Priced", "probability": 0.595},
         {"id": 2, "name": "Withdrawn", "probability": null}]
        """)
        let p = futuresDetailRenderedPercents(withdrawn)
        XCTAssertEqual(p[1], 60, "the priced side still renders")
        XCTAssertNil(p[2], "an unpriced outcome gets no printed percent, and never a derived one")
    }

    /// A pair that was already right does not move.
    func test_aPairThatAlreadySumsToOneHundredIsUntouched() throws {
        let fine = try outcomes("""
        [{"id": 1, "name": "Yield above", "probability": 0.93},
         {"id": 2, "name": "Yield below", "probability": 0.07}]
        """)
        let p = futuresDetailRenderedPercents(fine)
        XCTAssertEqual(p[1], 93)
        XCTAssertEqual(p[2], 7)
    }

    // MARK: - The override changes the integer, never the rule

    /// #5899's `<1%` marker is a claim about the VALUE, so it survives a
    /// card-level integer being handed to the formatter. A mutant that lets the
    /// override win would print `0` for an outcome the venue is still pricing —
    /// the exact regression #5899 fixed.
    func test_theSubOnePercentMarkerBeatsTheOverride() {
        XCTAssertEqual(percentNumber(0.05, renderedPercent: 0), "<1")
        XCTAssertEqual(formatProbability(0.0005, renderedPercent: 0), "<1%")
    }

    func test_theOverrideSuppliesTheIntegerWhenTheRuleIsSilent() {
        XCTAssertEqual(percentNumber(40.5, renderedPercent: 40), "40",
                       "without the override this is the 41 that made the page print 101")
        XCTAssertEqual(percentNumber(40.5), "41", "the un-overridden scale is unchanged")
        XCTAssertEqual(formatProbability(0.405, renderedPercent: 40), "40%")
    }

    /// The top marker is deliberately NOT symmetric (a resolved winner reads
    /// `100%`, not `>99%` — see `percentNumber`), so the override must not
    /// quietly introduce a hedge at the top end either.
    func test_theOverrideDoesNotInventATopEndHedge() {
        XCTAssertEqual(percentNumber(99.6, renderedPercent: 100), "100")
    }

    // MARK: - The wiring

    /// The three renderers live inside `some View` bodies and a computed property,
    /// which XCTest cannot call, so the behavioural assertions above cannot see
    /// whether the view still ASKS for the decision. #8035's mutation battery
    /// proved that gap is real: a mutant that reverted one call site survived
    /// every behavioural test. This scan is aimed at the three call sites rather
    /// than at one spelling of the old defect — the mistake that let
    /// `caller-filters-the-field-again` survive on the share image.
    func test_everyPrintedPercentOnThePageComesFromTheOneDecision() throws {
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("Bain Luck")
                .appendingPathComponent("Views")
                .appendingPathComponent("FuturesDetailView.swift"),
            encoding: .utf8
        )

        XCTAssertTrue(
            source.contains("percentNumber(prob * 100, renderedPercent: heroPercent)"),
            "the 52pt hero numeral must print the market's decision, not its own rounding"
        )
        XCTAssertTrue(
            source.contains("formatProbability(prob, renderedPercent: percent)"),
            "a non-leader row must print the market's decision"
        )
        // BOTH row renderers, counted rather than merely found.
        //
        // The first cut of this test asserted `contains("renderedPercent: percent")`
        // and the battery's `leader-row-ignores-the-decision` SURVIVED it: the
        // non-leader branch one line below spells the same substring, so blanking
        // the leader's `ProbabilityNumber` left the assertion satisfied by its
        // sibling. An anchor that two call sites can satisfy only ever proves that
        // ONE of them is alive. Two occurrences: the leader's `ProbabilityNumber`
        // and the non-leader's `formatProbability`.
        XCTAssertEqual(
            source.components(separatedBy: "renderedPercent: percent").count - 1, 2,
            "both row renderers must carry the decision — the leader's ProbabilityNumber and every other row's formatProbability"
        )

        // The list must hand each row ITS OWN decision. `list-passes-nil-to-every-row`
        // also survived the first cut: every assertion above still held while the
        // rows were handed `nil` and each quietly fell back to rounding alone. The
        // renderers being wired proves nothing if the thing feeding them is dead.
        XCTAssertTrue(
            source.contains("percent: percents[outcome.id]"),
            "each row must receive the decision for its own outcome, looked up by identity"
        )

        XCTAssertTrue(
            source.contains("futuresDetailRenderedPercents(market.outcomes)[leader.id]"),
            "the share sentence must quote the same integer the page prints"
        )

        // The decision is taken over the SERVED field. `sortedOutcomes` is the
        // reader's display choice and must never be what gets priced.
        XCTAssertFalse(
            source.contains("futuresDetailRenderedPercents(sorted)"),
            "pricing the displayed order lets a sort control change a printed number"
        )
    }
}
