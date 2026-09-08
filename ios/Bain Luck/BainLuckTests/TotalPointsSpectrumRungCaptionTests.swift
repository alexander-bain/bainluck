import XCTest
import SwiftUI
@testable import Bain_Luck

/// #3925 — what an **ungraded** rung of the scoring spectrum's ladder calls its
/// own percentage, and how much room that word gets.
///
/// THE PHOTOGRAPH:
/// `artifacts-native-061/BEFORE-3925-tennis-15305795-s900-master-02d9979b.png`,
/// iPhone 17 against production, master `02d9979b`. Event 15305795,
/// `Darderi 0 — Zverev 3`, **`completed`** — five rungs of a finished match,
/// every one captioned `PRE-GAME` over a settlement price:
///
/// ```
/// Darderi 0 - Zverev 3
/// Projected combined scoring
///    3.5+   PRE-GAME   ▬▬▬▬▬▬▬▬   0%
///    4.5+   PRE-GAME   ▬▬▬▬▬▬▬▬   0%
///    8.5+   PRE-GAME   ▬▬▬▬▬▬▬▬   0%
/// ```
///
/// 🔴 **THIS IS #3850's DEFECT, SURVIVING ON THE PATH #3850 COULD NOT REACH.**
/// That fix removed the caption by *replacing* it with a HIT/MISS badge, which
/// only happens where the card has a final to grade against. Tennis scores in
/// SETS, so `SportVocab.scoreboardCountsTheUnit` is false, `actualTotal` is nil,
/// `result` is nil, the badge never renders — and the string #3850 deleted is
/// still on screen, on a settled game, which is precisely what #3850 was about.
///
/// 🟠 **THE VALUE IS CORRECT AND IS NOT TOUCHED.** Measured on the specimen's
/// own payload: the `3.5` rung's `over_probability` is `0.001`, and the match
/// went 3 sets, so `Over 3.5 sets` is genuinely false and `0%` is the right
/// settled number. The rows two steps along carry `is_winner: true` and
/// `resolution_source: clean_resolution`. Only the word above the number lied.
final class TotalPointsSpectrumRungCaptionTests: XCTestCase {

    // MARK: - The ship

    /// 🟢 THE FIX. A finished match whose scoreboard cannot grade this card's
    /// unit stops calling its settlement prices a pre-game forecast.
    func testASettledCardWithNoGradeableFinalSaysLastQuoteNotPreGame() {
        let caption = MarketMapRail.spectrumRungCaption(finalTotal: nil, isSettled: true)

        XCTAssertEqual(
            caption, "LAST QUOTE",
            "event 15305795 is `completed` and has no combined-games total to grade "
            + "against, so its rungs must name the tense of the number they print")
        XCTAssertNotEqual(
            caption, "PRE-GAME",
            "the string in BEFORE-3925-tennis-15305795-s900-master-02d9979b.png")
    }

    /// 🔴 THE REGRESSION THIS COULD SHIP, and the reason the caption keys on two
    /// facts rather than one. Before and during a game the number IS a forecast,
    /// and a card that captioned it "LAST QUOTE" would be making the same class
    /// of false tense claim in the other direction.
    func testAnUnsettledCardStillSaysPreGame() {
        XCTAssertEqual(
            MarketMapRail.spectrumRungCaption(finalTotal: nil, isSettled: false), "PRE-GAME",
            "an unfinished game's rung is still a forecast and must still say so")
    }

    /// A graded rung yields no caption at all: `ladderRow` draws the HIT/MISS
    /// badge in the value column instead, and #3850's whole point was that the
    /// two must not both appear.
    func testAGradedRungHasNoCaptionBecauseTheVerdictOwnsTheRow() {
        XCTAssertNil(MarketMapRail.spectrumRungCaption(finalTotal: 9, isSettled: true))
        XCTAssertNil(
            MarketMapRail.spectrumRungCaption(finalTotal: 0, isSettled: true),
            "0 is a real final — a `finalTotal` of zero must not read as 'no final'")
    }

    /// 🔴 THE PRECEDENCE, stated as its own test because it is the one line of
    /// this rule a future editor could invert without noticing. "The event is
    /// over" and "this card can grade" are different facts, and where BOTH hold
    /// the verdict wins — a settled MLB card must keep printing `HIT`, not
    /// regress to `LAST QUOTE`.
    func testAGradeableFinalBeatsSettledRatherThanTheOtherWayRound() {
        XCTAssertNil(
            MarketMapRail.spectrumRungCaption(finalTotal: 9, isSettled: true),
            "event 15306209 (Reds 3 — Dodgers 6, 9 runs) grades its ladder; it must "
            + "not fall back to the settled caption")
    }

    // MARK: - The words are the page's own, not this file's

    /// 🟢 The settled caption is ``SettledQuote/prefix`` and nothing else, so it
    /// cannot drift from the sentence the same event page prints two inches
    /// lower ("settled — any percentage is a last quote") or from
    /// `frontend/lib/settledQuote.ts`, which the jest parity test holds it to.
    /// A hand-written replacement here would be a second settlement vocabulary
    /// on one screen, which is #1650.
    func testTheSettledCaptionIsThePagesOwnSettledWords() {
        XCTAssertEqual(
            MarketMapRail.spectrumRungCaption(finalTotal: nil, isSettled: true),
            SettledQuote.prefix.uppercased(),
            "if this fails someone has introduced a second wording for one state")
    }

    /// The caption states what the number IS, never what the line DID — the
    /// grade for these rows is not on the game-markets payload, so a verdict
    /// word here would be fabricated. Mirrors `SettledQuoteTests`' own guard.
    func testTheCaptionCarriesNoVerdict() {
        for isSettled in [true, false] {
            let caption = MarketMapRail.spectrumRungCaption(finalTotal: nil, isSettled: isSettled) ?? ""
            for verdict in ["HIT", "MISS", "PUSH", "WON", "LOST"] {
                XCTAssertFalse(
                    caption.contains(verdict),
                    "an ungraded rung must not carry the verdict \(verdict) (isSettled=\(isSettled))")
            }
        }
    }

    // MARK: - The column that has to hold it

    /// 🔴 THE FIX'S OWN REGRESSION RISK, measured rather than asserted. The
    /// caption slot was a bare `.frame(width: 52)` that nothing had ever sized —
    /// the class that ate `Sabalenka +5.5` out of the ladder next to this one
    /// (#3552) — and the string this fix adds is longer than the one it
    /// replaces. A truncated `LAST QUO…` would be a worse card than the bug.
    @MainActor
    func testTheCaptionColumnHoldsBothCaptions() {
        let measured = Self.everyCaption.map { ($0, naturalWidth(of: captionText($0))) }
        let widest = measured.max { $0.1 < $1.1 }!

        XCTAssertGreaterThanOrEqual(
            TotalPointsSpectrumView.captionColumnWidth, widest.1,
            "measured — " + measured.map { "'\($0.0)' \($0.1) pt" }.joined(separator: ", ")
            + ". The widest is '\(widest.0)', against the "
            + "\(TotalPointsSpectrumView.captionColumnWidth) pt the column offers. Short by any "
            + "amount and the row eats the word that names its own tense.")
    }

    /// Everything ``MarketMapRail/spectrumRungCaption(finalTotal:isSettled:)``
    /// can return, read off the function rather than retyped, so a third caption
    /// cannot be added without this column being re-sized.
    private static let everyCaption: [String] = [true, false].compactMap {
        MarketMapRail.spectrumRungCaption(finalTotal: nil, isSettled: $0)
    }

    /// 🔴 **THE HALF OF THIS FIX THAT WOULD HAVE SHIPPED BROKEN**, pinned so it
    /// cannot be undone by someone reverting the width as "unrelated tidying".
    ///
    /// Swapping the string alone — the obvious one-line reading of #3925 — puts
    /// `LAST QUOTE` into a column that cannot hold it. The old slot was a bare
    /// `.frame(width: 52)` that nothing had ever measured, and it fits
    /// `PRE-GAME` with room to spare, so it looks safe right up until the longer
    /// caption is put in it. This is #3552's class exactly: the fix's own
    /// truncation, invisible to every test that checks the string.
    @MainActor
    func testTheOldFiftyTwoPointColumnCouldNotHaveHeldTheSettledCaption() {
        let preGame = naturalWidth(of: captionText("PRE-GAME"))
        let lastQuote = naturalWidth(of: captionText(SettledQuote.prefix.uppercased()))

        XCTAssertLessThan(
            preGame, 52,
            "'PRE-GAME' wants \(preGame) pt and fitted the old 52 pt column — by 3 pt, "
            + "which is why nobody had reason to measure it")
        XCTAssertGreaterThan(
            lastQuote, 52,
            "'LAST QUOTE' wants \(lastQuote) pt against the old 52 pt column: the "
            + "string swap on its own truncates the word it exists to print")
        XCTAssertGreaterThan(
            TotalPointsSpectrumView.captionColumnWidth - lastQuote, 4.0,
            "the new width must clear the measurement by a real margin, not by "
            + "another coincidence — it currently clears by "
            + "\(TotalPointsSpectrumView.captionColumnWidth - lastQuote) pt")
    }

    /// The bar is the data and the caption is its tense, so the widening has to
    /// come out of something — this is the judgement, stated as a number. The
    /// row is `threshold(50) + caption + bar + value(32)` inside a ~338 pt card
    /// with 10 pt spacing, and the bar must stay the biggest thing in it.
    func testWideningTheCaptionDidNotCostTheBarItsDominance() {
        let card: CGFloat = 338
        let spacing: CGFloat = 10 * 3
        let bar = card - 50 - TotalPointsSpectrumView.captionColumnWidth - 32 - spacing

        XCTAssertGreaterThan(bar, TotalPointsSpectrumView.captionColumnWidth * 2,
                             "the measurement must stay far wider than its caption")
        XCTAssertGreaterThan(bar, 150, "the bar is what the reader is actually reading")
    }

    /// Exactly the `Text` the card builds, so the measurement above cannot
    /// silently diverge from what is drawn.
    private func captionText(_ caption: String) -> some View {
        Text(caption)
            .font(TotalPointsSpectrumView.captionFont)
            .tracking(TotalPointsSpectrumView.captionTracking)
            .lineLimit(1)
    }

    @MainActor
    private func naturalWidth<V: View>(of view: V) -> CGFloat {
        let host = UIHostingController(rootView: view)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }
}
