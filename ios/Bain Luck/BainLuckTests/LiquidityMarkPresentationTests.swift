import XCTest
@testable import Bain_Luck

/// UX-P157 — the illiquidity mark's native half (#2256 / #2257).
///
/// Alex's ruling, 2026-08-28, includes a clause aimed straight at this file:
/// *native needs a non-hover equivalent (tap/long-press or inline subtext)
/// designed at the same time, not later.* Designing it later means designing it
/// against whatever layout arrives first, which is how the phone and the web
/// end up with two different answers to one question.
///
/// These assertions are about the CONTRACT the pair shares, not about layout:
///
///   1. **Four levels, two of which draw.** `traded` and `unknown` are silent,
///      and an unrecognised value is `unknown` — never a mark invented from a
///      value we do not understand.
///   2. **The reveal is one sentence and it matches the web's.** Both are
///      generated from the same three parts in the same order, so a change on
///      one side that is not made on the other fails here. The strings below
///      are the web's, verbatim, from `frontend/lib/liquidity.ts`.
///   3. **The reveal says PRECISELY when**, which is Alex's word — an absolute
///      clock time, because the relative age is what he called ambiguous.
///   4. **It never claims a trade happened.** We do not receive trades; the
///      timestamp is when a probability last reached us.
///
/// There is no native surface consuming `liquidity` yet — checked 2026-08-28,
/// the app has no tournament hub — and `LiquidityMarkView`'s own header says so.
/// The contract is still worth holding: it is what stops the first surface that
/// does consume it from inventing a second vocabulary.
final class LiquidityMarkPresentationTests: XCTestCase {

    // MARK: - The level

    func testTheFourLevelsRoundTrip() {
        XCTAssertEqual(LiquidityLevel.normalize("traded"), .traded)
        XCTAssertEqual(LiquidityLevel.normalize("thin"), .thin)
        XCTAssertEqual(LiquidityLevel.normalize("barely"), .barely)
        XCTAssertEqual(LiquidityLevel.normalize("unknown"), .unknown)
    }

    func testAnUnrecognisedValueIsUnknownAndNeverAMark() {
        for raw in [nil, "", "illiquid", "THIN", "0", "Barely"] {
            let level = LiquidityLevel.normalize(raw)
            XCTAssertEqual(level, .unknown, "\(raw ?? "nil") must fail closed")
            XCTAssertFalse(level.isMarked)
        }
    }

    func testOnlyTwoLevelsDrawAnything() {
        XCTAssertFalse(LiquidityLevel.traded.isMarked)
        XCTAssertFalse(LiquidityLevel.unknown.isMarked)
        XCTAssertTrue(LiquidityLevel.thin.isMarked)
        XCTAssertTrue(LiquidityLevel.barely.isMarked)
    }

    func testTheGlyphGradesEmptierAsThinner() {
        // Alex asked for at least two levels and for the grade to be legible
        // without a key. "Less filled" is the whole of that promise.
        XCTAssertGreaterThan(LiquidityLevel.thin.fill, LiquidityLevel.barely.fill)
        XCTAssertEqual(LiquidityLevel.barely.fill, 0.0)
        XCTAssertEqual(LiquidityLevel.thin.fill, 0.5)
    }

    // MARK: - The reveal

    func testSilenceForATradedOrUncheckableNumber() {
        XCTAssertNil(Liquidity.reveal(level: .traded, reasons: []))
        XCTAssertNil(Liquidity.reveal(level: .unknown, reasons: ["no_trades_24h"]))
    }

    func testTheSentenceMatchesTheWebWordForWord() {
        // Verbatim from `frontend/lib/liquidity.ts`. If either side is reworded
        // without the other, this fails — which is the only mechanism keeping
        // one signal from becoming two.
        let sentence = Liquidity.reveal(
            level: .barely,
            reasons: ["no_trades_24h", "spread_exceeds_price"]
        )
        XCTAssertEqual(
            sentence,
            "Barely traded — nobody has traded it in the last day, and the gap between what "
                + "buyers offer and what sellers want is wider than the number itself. "
                + "Treat this as little more than a guess."
        )
    }

    func testTheThinSentenceMatchesTooAndNamesOnlyItsOwnReason() {
        XCTAssertEqual(
            Liquidity.reveal(level: .thin, reasons: ["no_trades_24h"]),
            "Thinly traded — nobody has traded it in the last day. Treat this as a rough guide."
        )
    }

    func testItSaysPreciselyWhenTheNumberReachedUs() {
        // Alex's constraint verbatim: the reveal says precisely WHEN the
        // probability was last updated. An absolute clock time, in the reader's
        // own timezone — "32 hours ago" is the phrasing he called ambiguous.
        let observed = Date(timeIntervalSince1970: 1_787_000_040)
        let sentence = Liquidity.reveal(
            level: .thin,
            reasons: ["no_trades_24h"],
            observedAt: observed
        )
        let expected = Liquidity.preciseObservedAt(observed)
        XCTAssertNotNil(expected)
        XCTAssertTrue(sentence?.contains("Last number: ") == true)
        XCTAssertTrue(sentence?.contains(expected!) == true)
    }

    func testWithNoTimestampItDropsTheClauseRatherThanPrintingAHole() {
        let sentence = Liquidity.reveal(level: .thin, reasons: ["no_trades_24h"])
        XCTAssertFalse(sentence?.contains("Last number") == true)
        XCTAssertFalse(sentence?.contains("nil") == true)
    }

    func testItNeverClaimsTheMarketTraded() {
        // We do not receive trades. The timestamp is the last time a
        // probability reached us, and over-claiming here is the mistake
        // `tournamentProps.FRESHNESS_DEFINITION` exists to stop.
        let sentence = Liquidity.reveal(
            level: .barely,
            reasons: ["no_trades_24h", "spread_exceeds_price"],
            observedAt: Date(timeIntervalSince1970: 1_787_000_040)
        ) ?? ""
        for claim in ["changed hands", "last traded at", "last trade"] {
            XCTAssertFalse(
                sentence.lowercased().contains(claim),
                "the reveal must not assert a trade we never observed: \(claim)"
            )
        }
    }

    func testAnUnrecognisedReasonIsDroppedNotPrinted() {
        let sentence = Liquidity.reveal(level: .barely, reasons: ["cosmic-rays"]) ?? ""
        XCTAssertTrue(sentence.hasPrefix("Barely traded."))
        XCTAssertFalse(sentence.contains("cosmic-rays"))
        XCTAssertFalse(sentence.contains("  "))
    }

    // MARK: - The definition

    func testTheDefinitionSaysAnUnmarkedNumberHasNotBeenCleared() {
        // GOTCHA #53 in one clause. Where a venue publishes nothing to check we
        // cannot mark, so silence is a limit on us, not a verdict on the market.
        XCTAssertTrue(Liquidity.definition.contains("no mark"))
        XCTAssertTrue(Liquidity.definition.contains("not been able to question"))
    }

    func testTheDefinitionTeachesBothGlyphs() {
        XCTAssertTrue(Liquidity.definition.contains("half mark"))
        XCTAssertTrue(Liquidity.definition.contains("hollow mark"))
    }

    func testTheDefinitionCarriesNoBannedTradingVocabulary() {
        // Ruling 138: the `price` stem is banned — the word is PROBABILITY.
        // Ruling 141: no venue name is the subject of reader copy.
        let text = Liquidity.definition.lowercased()
        for banned in ["price", "priced", "unpriced", "kalshi", "polymarket", "stale"] {
            XCTAssertFalse(text.contains(banned), "banned in reader copy: \(banned)")
        }
    }
}
