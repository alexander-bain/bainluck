import XCTest
@testable import Bain_Luck

/// #7998 — **the share IMAGE prints the numbers the card printed.**
///
/// The Discover card's share button carries three outputs: the strip in the card
/// body, the share SENTENCE, and — behind the same `ShareLink`'s `contextMenu` —
/// the rendered image ("Copy Image" / "Save Image"). The first two asked
/// `duelPercents` with the served pair. The image rounded each side alone.
///
/// Measured 2026-09-22 over the 408 production event payloads cached in
/// `artifacts/native-293/event-details.json`. Of the **295** two-way events
/// serving a printable pair, **119 (40%)** produced an image disagreeing with the
/// card the reader had just long-pressed:
///
/// | specimen | the card | the image, before |
/// |---|---|---|
/// | Gabriela Ruse @ Eva Lys `15314911` | `59% / 41%` | `59% / 42%` — **101** |
/// | NY Islanders @ NY Rangers `15313235` | `42% / 58%` | `43% / 57%` — **100** |
///
/// **105** were the first kind. **14 were the second**, and those are the ones
/// this file exists for: the pair sums to 100, so no sum guard can see them, and
/// the image simply states a probability the app does not hold — in 32pt type, on
/// the one artefact we ship that travels to people who never opened the app.
///
/// ## Two distinct causes, and only asserting the sum catches one of them
///
/// 1. **THE PAIR.** `routes/feed.py` derives away as `round(1.0 - home, 6)`, so
///    when `home * 100` lands on `.5` both half-up roundings round up: 101, never
///    99 (#2084 / UX-P114).
/// 2. **THE SCALE.** Bare `formatProbability` rounds `value * 100`; the contract's
///    `renderedPercent` rounds `value * 1000 / 10` (#3867, contract v5) precisely
///    because `0.575 * 100` is `57.4999…`. The image printed 57 where the card and
///    the server both said 58.
///
/// So the assertion throughout is **equality with the card's pair**, not "the sum
/// is 100". A sum guard passes every one of the 14.
///
/// ## Why the subject is a `static func`
///
/// The arithmetic lived inside a `some View`, where no test can reach it — which
/// is how #4963's iOS clearance came to be written. That issue fixed this class on
/// the web OG image and recorded "iOS is NOT affected — checked, not assumed",
/// naming the share SENTENCE's `duelPercents` call. The reading was right; the
/// image is a different output of the same affordance and was never examined.
/// `printedPercents` is static for the same reason ``ShareableEventCardView``'s
/// `eyebrow` is (#4044): so the suite runs the production path.
///
/// `test_theOldRuleReallyDidDisagree` is the convicting control. It re-runs the
/// pre-fix expression over the grid the venues quote on and fails if independent
/// rounding never disagreed — so this file cannot pass vacuously.
final class ShareImageMatchesItsCard_7998Tests: XCTestCase {

    // MARK: - Harness

    /// What the CARD prints for a pair — `DiscoverEventCard`'s strip, verbatim.
    ///
    /// Written out here rather than imported because the card's copy is inline in
    /// a `some View`. That is a real hazard (#6931: a test exercising its own copy
    /// of the arithmetic proved nothing), and it is answered by the jest scanner
    /// `frontend/__tests__/ios/shareImageMatchesItsCard_7998.test.ts`, which pins
    /// both call sites to the same `duelPercents` shape in the Swift source.
    private func cardPair(
        away: Double?, home: Double, servedAway: Int?, servedHome: Int?
    ) -> (away: String?, home: String) {
        let duel = duelPercents(
            away: away ?? (1 - home),
            home: home,
            servedAway: servedAway,
            servedHome: servedHome
        )
        return (
            away.map { formatProbability($0, renderedPercent: duel[0]) },
            formatProbability(home, renderedPercent: duel[1])
        )
    }

    /// The pre-fix expression, kept so the control below can convict.
    private func independentlyRounded(_ value: Double) -> String {
        formatProbability(value)
    }

    private func assertImageMatchesCard(
        away: Double?, home: Double,
        servedAway: Int?, servedHome: Int?,
        _ message: String = "",
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let image = ShareableEventCardView.printedPercents(
            away: away, home: home, servedAway: servedAway, servedHome: servedHome
        )
        let card = cardPair(
            away: away, home: home, servedAway: servedAway, servedHome: servedHome
        )
        XCTAssertEqual(image.away, card.away, "away — \(message)", file: file, line: line)
        XCTAssertEqual(image.home, card.home, "home — \(message)", file: file, line: line)
    }

    // MARK: - The photographed specimens

    func test_theTennisSpecimen_printsTheCardsPairAndSumsTo100() {
        // Gabriela Ruse @ Eva Lys, 15314911. Served 0.585/0.415 -> 59/41.
        // Before: the image printed 59 / 42.
        let printed = ShareableEventCardView.printedPercents(
            away: 0.585, home: 0.415, servedAway: 59, servedHome: 41
        )
        XCTAssertEqual(printed.away, "59%")
        XCTAssertEqual(printed.home, "41%")
    }

    /// 🔴 THE ONE A SUM GUARD CANNOT SEE.
    ///
    /// NY Islanders @ NY Rangers, 15313235, served 0.425/0.575 -> 42/58. The old
    /// image printed `43% / 57%`: a clean 100, and the wrong pair.
    func test_theScaleSpecimen_whereTheOldPairAlreadySummedTo100() {
        let printed = ShareableEventCardView.printedPercents(
            away: 0.425, home: 0.575, servedAway: 42, servedHome: 58
        )
        XCTAssertEqual(printed.away, "42%")
        XCTAssertEqual(printed.home, "58%")

        // The defect, stated: both old numbers summed to 100 and both were wrong.
        XCTAssertEqual(independentlyRounded(0.425), "43%")
        XCTAssertEqual(independentlyRounded(0.575), "57%")
    }

    func test_theMlbSpecimen() {
        // NY Mets @ Texas Rangers, 15316900 — the same shape in a major league.
        assertImageMatchesCard(
            away: 0.425, home: 0.575, servedAway: 42, servedHome: 58,
            "Mets @ Rangers"
        )
    }

    // MARK: - The grid the venues actually quote on

    func test_everyHalfPercentPair_theImageEqualsTheCard() {
        var checked = 0
        for step in 1..<200 {
            let home = Double(step) * 0.005
            let away = 1 - home
            checked += 1
            // No served pair: this is the cached / pre-deploy payload path, where
            // #2279's both-or-neither rule sends the pair WHOLE to the fallback.
            assertImageMatchesCard(
                away: away, home: home, servedAway: nil, servedHome: nil,
                "home=\(home)"
            )
        }
        XCTAssertGreaterThan(checked, 150)
    }

    /// The convicting control: if independent rounding never disagreed with the
    /// card, every assertion above would hold on the unfixed code too.
    func test_theOldRuleReallyDidDisagree() {
        var disagreed = 0
        var summedTo101 = 0
        for step in 1..<200 {
            let home = Double(step) * 0.005
            let away = 1 - home
            let card = cardPair(away: away, home: home, servedAway: nil, servedHome: nil)
            let old = (away: independentlyRounded(away), home: independentlyRounded(home))
            if old.away != card.away || old.home != card.home { disagreed += 1 }
            if let a = Int(old.away.dropLast()), let h = Int(old.home.dropLast()),
               a + h == 101 {
                summedTo101 += 1
            }
        }
        XCTAssertGreaterThan(disagreed, 0, "the guard is pointed at nothing")
        XCTAssertGreaterThan(summedTo101, 0, "the 101 arm is pointed at nothing")
        // And the other arm: disagreements that a sum guard would have passed.
        XCTAssertGreaterThan(
            disagreed - summedTo101, 0,
            "the scale arm is pointed at nothing — a sum guard would suffice"
        )
    }

    // MARK: - The served pair wins, and it is read as a pair

    func test_theServedPairIsUsedWhenBothArePresent() {
        // A deliberately odd served pair the local rule would never produce, so
        // the assertion can only pass by actually reading the served values.
        let printed = ShareableEventCardView.printedPercents(
            away: 0.5, home: 0.5, servedAway: 37, servedHome: 63
        )
        XCTAssertEqual(printed.away, "37%")
        XCTAssertEqual(printed.home, "63%")
    }

    func test_aHalfServedPairFallsBackWholeRatherThanMixing() {
        // #2279 — a payload written across a partial rollout. Coalescing per side
        // would print a served value beside a derived one and re-open the 101.
        // `RenderedPercent`'s own worked example: on 0.505 / 0.495 the served home
        // is 51 and a naively derived away is 50.
        let printed = ShareableEventCardView.printedPercents(
            away: 0.495, home: 0.505, servedAway: nil, servedHome: 63
        )
        XCTAssertEqual(printed.home, "51%", "must not take the lone served 63")
        XCTAssertEqual(printed.away, "49%")
    }

    // MARK: - What must NOT move

    func test_theAwaySlotIsStillWithheldWhenThereIsNoAwayNumber() {
        // #5363 — nil is *withheld*, and the view draws an empty slot rather than
        // a dash. The home number still comes from the pair decision.
        let printed = ShareableEventCardView.printedPercents(
            away: nil, home: 0.475, servedAway: nil, servedHome: 48
        )
        XCTAssertNil(printed.away)
        XCTAssertEqual(printed.home, "47%", "the card's answer on this branch")
    }

    func test_theMarkersSurviveThePairDecision() {
        // `<1%` / `>99%` are claims about the VALUE, not about the arithmetic that
        // produced an integer, so they outrank a served percent.
        let printed = ShareableEventCardView.printedPercents(
            away: 0.999, home: 0.001, servedAway: 100, servedHome: 0
        )
        XCTAssertEqual(printed.away, ">99%")
        XCTAssertEqual(printed.home, "<1%")
    }

    func test_aNonComplementPairIsLeftAlone() {
        // The pairing is `renderedDuelPercents`' decision and it is gated on
        // `isComplementPair`. Two prices that are not a complement — a served away
        // price (#5271) — must render exactly as they did before.
        let printed = ShareableEventCardView.printedPercents(
            away: 0.40, home: 0.50, servedAway: nil, servedHome: nil
        )
        XCTAssertEqual(printed.away, "40%")
        XCTAssertEqual(printed.home, "50%")
    }
}
