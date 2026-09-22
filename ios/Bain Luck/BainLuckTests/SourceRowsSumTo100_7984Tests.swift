import XCTest
@testable import Bain_Luck

/// #7984 — **the event page's source rows print a pair that adds up.**
///
/// Photographed on THIS screen, iPhone 17 against production, 2026-09-22 01:59
/// PDT, `bainluck://events/15316315` (Costoulas v Prozorova, WTA, live) —
/// `artifacts-native-020/n293-live-wta.png`:
///
///     Sportsbooks (7)   3%   97%
///     Polymarket        42%  59%      <- 101
///
/// `GET /api/events/15316315` serves the source as ONE number, `0.585`.
/// `sourceContent` derives the away side as an exact complement and then
/// `probabilityBarAndNumbers` formatted the two sides independently, so a venue
/// quoting on the half-percent grid put BOTH on `.5` and half-up rounded both up.
///
/// Measured across 408 production events the same morning: **122 of 332** source
/// rows that print a numeric pair summed to 101, on 113 distinct events, plus 6 of
/// 557 bookmaker rows. Every failure was 101 and none was 99 — the signature of
/// both sides rounding up, not of a data fault.
///
/// ## What is asserted
///
/// The STRINGS the rows print, through `duelProbabilityStrings` — the single
/// function the draw site and both `EventSourceLabelColumn.columns(values:)`
/// sizing arrays now call. Asserting the integers would not have caught the
/// #4208/#5271 hazard this fix had to respect: the numeric column is measured from
/// the strings the rows will actually draw, so the sizing pass and the draw pass
/// must agree on the text, not merely on the arithmetic.
///
/// `test_theGridIsWhereThisFires` is the convicting control. It sweeps the
/// half-percent grid the venues actually quote on and fails on the OLD
/// independent-rounding expression, so this file cannot pass vacuously if someone
/// reverts the call sites.
final class SourceRowsSumTo100_7984Tests: XCTestCase {

    // MARK: - Harness

    /// The integer a printed cell carries, or nil when the cell is a marker
    /// (`<1%`, `>99%`) or the absent-probability dash. A marker row never shows a
    /// reader a numeric pair, so it has no sum to be wrong about.
    private func percent(_ printed: String) -> Int? {
        guard printed.hasSuffix("%"),
              !printed.hasPrefix("<"),
              !printed.hasPrefix(">") else { return nil }
        return Int(printed.dropLast())
    }

    /// The sum a reader would get adding the two cells, or nil if either is a
    /// marker.
    private func printedSum(away: Double?, home: Double) -> Int? {
        let printed = duelProbabilityStrings(away: away, home: home)
        guard let a = percent(printed.away), let h = percent(printed.home) else { return nil }
        return a + h
    }

    // MARK: - The photograph

    func test_thePhotographedPolymarketRowNoLongerPrints101() {
        // The served value, and the away side exactly as `sourceContent` derives
        // it. Written as `1 - home` rather than as the literal 0.415 so the test
        // carries the call site's own arithmetic, including its binary error.
        let home = 0.585
        let printed = duelProbabilityStrings(away: 1 - home, home: home)

        XCTAssertEqual(printed.home, "59%", "the favourite's own number must survive untouched")
        XCTAssertEqual(printed.away, "41%", "the derived point lands on the side nobody is quoting")
        XCTAssertEqual(printedSum(away: 1 - home, home: home), 100)
    }

    /// The WNBA specimen, and it matters because it is a DIFFERENT source (`espn`)
    /// and the favourite is on the home side by one point — the branch of
    /// `renderedDuelPercents` the Polymarket case does not reach.
    func test_theEspnRowOnEvent15316236() {
        let home = 0.515
        let printed = duelProbabilityStrings(away: 1 - home, home: home)

        XCTAssertEqual(printed.home, "52%")
        XCTAssertEqual(printed.away, "48%")
        XCTAssertEqual(printedSum(away: 1 - home, home: home), 100)
    }

    // MARK: - The convicting control

    /// Every value the venues actually quote, and the old expression's own verdict
    /// on each one.
    ///
    /// This is the test that fails if the call sites go back to rounding each side
    /// on its own: it asserts BOTH that the new pair sums to 100 everywhere AND
    /// that there really were values where the old one did not, so a future reader
    /// can see the defect was reachable rather than take this file's word for it.
    func test_theGridIsWhereThisFires() {
        var oldWouldHaveFailed = 0
        var checked = 0

        for step in 1..<200 {
            let home = Double(step) * 0.005   // 0.005 ... 0.995
            let away = 1 - home

            guard let sum = printedSum(away: away, home: home) else { continue }
            checked += 1
            XCTAssertEqual(
                sum, 100,
                "home=\(home) printed \(duelProbabilityStrings(away: away, home: home))")

            // The expression the two rows used before this ship.
            if let a = renderedPercent(away), let h = renderedPercent(home), a + h != 100 {
                oldWouldHaveFailed += 1
            }
        }

        XCTAssertGreaterThan(checked, 150, "the sweep must actually be printing pairs")
        XCTAssertGreaterThan(
            oldWouldHaveFailed, 0,
            "if independent rounding never disagreed, this file is guarding nothing")
    }

    // MARK: - What must NOT move

    /// A pair that already added up is not touched — the four-decimal `betting`
    /// row is 44 of the measured rows and never failed, so it is the population
    /// this fix must leave alone.
    func test_aPairThatAlreadyAddedUpIsUnchanged() {
        let home = 0.9663                      // event 15316315's Sportsbooks row
        let printed = duelProbabilityStrings(away: 1 - home, home: home)

        XCTAssertEqual(printed.away, "3%")
        XCTAssertEqual(printed.home, "97%")
    }

    /// A bookmaker pair is SERVED on both sides (#5271) and need not be a
    /// complement. `renderedDuelPercents` is gated on `isComplementPair`, so such a
    /// row must render exactly as it did — including when that means a sum a
    /// reader could object to for a different reason.
    func test_aNonComplementBookmakerPairIsLeftExactlyAsItWas() {
        let away = 0.53, home = 0.53           // sums to 1.06: three-way, draw discarded
        let printed = duelProbabilityStrings(away: away, home: home)

        XCTAssertEqual(printed.away, formatProbabilityOrDash(away))
        XCTAssertEqual(printed.home, formatProbability(home))
        XCTAssertEqual(printedSum(away: away, home: home), 106)
    }

    /// A withheld away side keeps its dash and does not drag the home number with
    /// it. `DrawPricedWinner.printablePair` returns nil on a draw-priced sport, so
    /// this is the live shape of every soccer row in the list.
    func test_aWithheldAwaySideKeepsItsDashAndLeavesHomeAlone() {
        let printed = duelProbabilityStrings(away: nil, home: 0.585)

        XCTAssertEqual(printed.away, absentProbabilityMarker)
        XCTAssertEqual(printed.home, "59%", "a row with no pair rounds its one number normally")
        XCTAssertNil(percent(printed.away))
    }

    /// The `<1%` / `>99%` markers are a claim about the VALUE, not about the
    /// arithmetic that produced an integer, so handing `formatProbability` a
    /// rendered percent must not defeat them. Without this, the pair rule would
    /// print `100%` for a side the app has always refused to call certain.
    func test_theMarkerRuleSurvivesThePairDecision() {
        let printed = duelProbabilityStrings(away: 0.005, home: 0.995)

        XCTAssertEqual(printed.away, "<1%")
        XCTAssertEqual(printed.home, ">99%")
        XCTAssertNil(printedSum(away: 0.005, home: 0.995), "a marker row shows no numeric pair")
    }
}
