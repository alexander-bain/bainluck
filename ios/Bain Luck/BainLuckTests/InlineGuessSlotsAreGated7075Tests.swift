import XCTest
@testable import Bain_Luck

/// #7075 — DISCOVER WAS STILL CONVERTING EVERY FIFTH CARD INTO A GUESS.
///
/// #6445 hid the Higher/Lower experience and #6501 found two entry points it had
/// missed. Both of those rounds were reasoned about — and guarded — in terms of
/// `Route.predictionStats`, which `PredictionsExperienceIsGatedEverywhere6501Tests`
/// calls "the one token every entry point must contain". That sentence is what
/// let build 15 ship with two more: Discover does not NAVIGATE a reader to the
/// guess game at every fifth slot, it REPLACES the market card with one, in
/// place. No route, so the scan was blind to it, and a 1-in-5 cadence meant Alex
/// met two of them in a single pass down the feed on the physical phone:
///
///   "Below that Corn Fairy golf card is a 'What's the probability?' card […]
///   I thought we were going to pull these out altogether until we had figured
///   out how to do them well"
///
/// Reproduced here before the fix, `artifacts/native-239/BEFORE-discover-s1400.png`
/// (master `7980bbbdc`, iPhone 17 Pro, anonymous feed): the Higher / Lower
/// buttons of a guess card are on screen under the navigation bar.
///
/// ## What this file pins, and why in two different ways
///
/// The arithmetic and the wiring fail differently, so they are checked
/// differently. `insertsInlineGuessSlot(at:enabled:)` is a pure function and is
/// called directly — including in the ON configuration this build does not ship,
/// because a guard that can only ever observe `false` cannot tell a flag that
/// hides a surface from arithmetic that stopped selecting cards. The wiring —
/// that both call sites read it, and that the card falls through to the real
/// market rather than disappearing — is a source scan, because it lives in a
/// `@ViewBuilder` no test can instantiate headlessly and CI compiles no Swift.
final class InlineGuessSlotsAreGated7075Tests: XCTestCase {

    // MARK: - The decision itself

    /// The shipping configuration: no slot, anywhere.
    func testNoInlineGuessSlotIsSelectedInTheShippingBuild() {
        for index in 0..<40 {
            XCTAssertFalse(
                ReleaseSurfaces.insertsInlineGuessSlot(at: index),
                """
                card \(index) is still converted into a "What's the probability?" \
                guess. The launch build hides that experience (#6445/#6501); an \
                inline conversion is the same surface reached without navigating.
                """
            )
        }
    }

    /// The cadence has to SURVIVE being switched off, or this is not a flag —
    /// it is a deletion wearing one, and #6445's standing constraint is that
    /// flipping the switch restores the experience rather than re-implementing
    /// it. Every fifth card, counting from the first, is what shipped.
    func testTheEveryFifthCardCadenceIsIntactBehindTheFlag() {
        let selected = (0..<40).filter {
            ReleaseSurfaces.insertsInlineGuessSlot(at: $0, enabled: true)
        }
        XCTAssertEqual(
            selected, [4, 9, 14, 19, 24, 29, 34, 39],
            """
            switched ON, the slots are not the every-fifth-card cadence the feed \
            shipped with. A fix that hid the guess cards by changing WHICH cards \
            are selected would pass the test above and would make the restore a \
            re-implementation.
            """
        )
    }

    /// The two arguments are not the same argument. Without this, a body of
    /// `false` and a body of `enabled` are indistinguishable at index 4.
    func testTheFlagAndTheCadenceAreBothLoadBearing() {
        XCTAssertTrue(ReleaseSurfaces.insertsInlineGuessSlot(at: 4, enabled: true),
                      "the cadence stopped selecting the fifth card even when enabled")
        XCTAssertFalse(ReleaseSurfaces.insertsInlineGuessSlot(at: 3, enabled: true),
                       "a non-slot index was selected — the every-fifth rule is gone")
        XCTAssertFalse(ReleaseSurfaces.insertsInlineGuessSlot(at: 4, enabled: false),
                       "the flag does not switch the slot off, so nothing is hidden")
    }

    // MARK: - The wiring

    private func discover() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views")
            .appendingPathComponent("DiscoverView.swift")
        return try PredictionsExperienceIsGatedEverywhere6501Tests
            .stripped(String(contentsOf: url, encoding: .utf8))
    }

    /// Anti-vacuity: every assertion below is about the contents of a file, so
    /// they all pass on an empty string if the read silently fails.
    func testTheScanReadsDiscoverView() throws {
        let code = try discover()
        XCTAssertTrue(code.contains("navigationTitle(\"Discover\")"),
                      "the scan is not reading DiscoverView.swift")
    }

    /// The slot decision is the switch's, not the body's.
    func testTheSlotDecisionIsTakenFromReleaseSurfaces() throws {
        XCTAssertTrue(
            try discover().contains("letisGuessSlot=ReleaseSurfaces.insertsInlineGuessSlot(at:idx)"),
            """
            DiscoverView computes its guess slots itself again. It read \
            `(idx + 1) % 5 == 0` inline, which is how the cadence came to be \
            unreachable from `ReleaseSurfaces` and invisible to the gating scan.
            """
        )
    }

    /// Neither insertion may be reachable except through that decision. A scan
    /// rather than two pinned line numbers: a third insertion fails here with no
    /// edit to this file, which is the lesson #6501 wrote down and #7075 paid
    /// for anyway.
    func testEveryGuessCardInsertionSitsBehindTheSlotDecision() throws {
        let code = try discover()
        let guarded = PredictionsExperienceIsGatedEverywhere6501Tests
            .gatedRanges(in: code, from: "ifisGuessSlot,")
        XCTAssertFalse(guarded.isEmpty, "no `if isGuessSlot,` branch found — the matcher is broken")

        var cursor = code.startIndex
        var ungated = 0
        var total = 0
        while let hit = code.range(of: "NativeGuessCard(", range: cursor..<code.endIndex) {
            total += 1
            if !guarded.contains(where: { $0.lowerBound <= hit.lowerBound && hit.upperBound <= $0.upperBound }) {
                ungated += 1
            }
            cursor = hit.upperBound
        }

        XCTAssertEqual(total, 2, "Discover should insert the guess card in exactly two places (futures and event)")
        XCTAssertEqual(
            ungated, 0,
            """
            a guess card is inserted into the feed outside the \
            `if isGuessSlot,` branches, so switching the experience off does \
            not switch it off.
            """
        )
    }

    /// Hidden, not deleted — `ReleaseSurfaces`' own contract. A sweep that
    /// removed the card would pass every assertion above and would make
    /// restoring the experience a re-implementation.
    func testTheGuessCardItselfSurvives() throws {
        let code = try discover()
        XCTAssertTrue(code.contains("structNativeGuessCard:View"),
                      "NativeGuessCard was deleted rather than switched off")
        XCTAssertTrue(code.contains("privateenumNativeGuessCardContent"),
                      "the guess card's question builder was deleted rather than switched off")
    }

    /// The reader keeps the MARKET. This is the half that separates "hide the
    /// guess" from "drop every fifth card": both branches must fall through to
    /// the ordinary card, so a slot that is no longer a guess is the event or
    /// futures card it would have replaced, in the same rank.
    func testASlotThatIsNoLongerAGuessStillDrawsItsMarket() throws {
        let code = try discover()
        XCTAssertTrue(
            code.contains("}elseifitem.type==\"event\",lete=item.event{"),
            "the event fall-through is gone: a slot with no guess would draw nothing"
        )
        XCTAssertTrue(
            code.contains("NativeEventDiscoverCard(event:e,"),
            "the ordinary event card is no longer the fall-through"
        )
    }
}
