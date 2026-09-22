import XCTest
@testable import Bain_Luck

/// #7905 — **a margin is spelled as a margin, not as a betting line.**
///
/// ## The photograph
///
/// `artifacts-native-020/live-t2-margin.png`, iPhone 17 Pro, event 14780545
/// (Giants at Rams) live in Q1 on 2026-09-21 at 17:45 PDT, with the Rams a
/// 10.5-point favourite:
///
/// ```
/// ACTUAL              PROJECTION
/// NYG +0              LAR +10.5          ← the game is 0–0
///
/// NYG by 18+     Tie     LAR by 30.5+    ← the card's own axis, 60 pt below
///
///   NYG +1.5   17%     LAR +1.5   81%
///   NYG +2.5   13%     LAR +2.5   81%
///   NYG +3.5   12%     LAR +3.5   71%
/// ```
///
/// ## Three faults, one grammar
///
/// 1. **`TEAM +N` is a gambling price format and #2442's standing ruling bans
///    it.** Alex counted `+4.5` first among the six he found on one event page.
///    Web answered with `by N+`; the phone never got the port, so the ruling has
///    been broken on the flagship page ever since.
///
/// 2. **In that notation the number beside it is false.** `LAR +1.5` means *the
///    Rams getting 1.5 points*, which with the Rams favoured by 10.5 is worth
///    about 93%. The card says 81%, because the rung measures the opposite —
///    `LAR wins by MORE than 1.5` — which is exactly why
///    `MarketMapRail.totalLadderResult` grades it with `>=`. A reader who knows
///    spread notation resolves every row the wrong way, and nothing on the card
///    tells them to stop.
///
/// 3. **`ACTUAL NYG +0` credits a dead-level scoreboard to the away team.**
///    `margin > 0 ? hAbbr : aAbbr` is a two-way answer to a three-way question.
///
/// ## Why this is a port and not a new decision
///
/// #3743 fixed the tennis half of the ladder on this same card and stopped
/// deliberately at the notation: *"it is a copy change across all sports that
/// cannot be made without moving the NFL labels this issue forbids moving. It
/// wants its own decision, not a rider on this one."* Web had already made that
/// decision twice — #2442 for the `by N+` rung grammar, #7380 for the bare
/// `by N` on a margin that HAPPENED — and `MarketMapSection.tsx` states the
/// reason the two must be one helper: *"so the headline and the ladder cannot
/// drift into two grammars."* On the phone they had.
///
/// ## What is pinned here
///
/// The grammar itself, in all four shapes, plus a source scan proving no margin
/// site reaches for the old spelling. The scan is not decoration: the five call
/// sites were five separate string interpolations, and the axis — which was
/// always correct — was two more. Seven copies of one sentence is how the drift
/// happened, so the guard is that there is now one.
final class AMarginIsNotABettingLine7905Tests: XCTestCase {

    // MARK: - The grammar

    /// 🟢 A rung is a THRESHOLD, so it keeps the `+` — on the far side, where it
    /// means "or more", not on the near side, where it means "getting points".
    func testARungIsSpelledByTheMarginItMeasures() {
        XCTAssertEqual(
            MarketMapRail.marginThresholdLabel(teamAbbr: "LAR", threshold: 1.5),
            "LAR by 1.5+")
        XCTAssertEqual(
            MarketMapRail.marginThresholdLabel(teamAbbr: "Zandschulp", threshold: 2.5),
            "Zandschulp by 2.5+")
    }

    /// A whole line keeps its whole-number label — the rule the ladder has had
    /// since #3552, now shared with the tiles that did not have it.
    func testAWholeLineIsNotGivenAFalseDecimal() {
        XCTAssertEqual(
            MarketMapRail.marginThresholdLabel(teamAbbr: "NE", threshold: 10),
            "NE by 10+")
        XCTAssertEqual(
            MarketMapRail.marginThresholdLabel(teamAbbr: "NE", threshold: 10.5),
            "NE by 10.5+")
    }

    /// 🔴 THE TILE FROM THE PHOTOGRAPH. The PROJECTION tile used to reach for
    /// `String(format: "%.1f", …)` unconditionally, so an even ten-point line
    /// printed `LAR +10.0` directly above a ladder printing `10`. One helper,
    /// one answer.
    func testTheProjectionTileQuotesACoverLineAndKeepsThePlus() {
        XCTAssertEqual(
            MarketMapRail.projectedMarginLabel(homeAbbr: "LAR", awayAbbr: "NYG", margin: 10.5),
            "LAR by 10.5+")
        XCTAssertEqual(
            MarketMapRail.projectedMarginLabel(homeAbbr: "LAR", awayAbbr: "NYG", margin: -3),
            "NYG by 3+",
            "a negative projection is the AWAY side's, named as such rather than signed")
        XCTAssertEqual(
            MarketMapRail.projectedMarginLabel(homeAbbr: "LAR", awayAbbr: "NYG", margin: 10),
            "LAR by 10+",
            "not 'LAR by 10.0+' — the tile shares the ladder's formatter now")
    }

    /// 🔴 #7380's split: ACTUAL and FINAL are the scoreboard, and a scoreboard is
    /// STATED. `by 7+` means seven or more, and a played margin has no more left
    /// in it.
    func testAMarginThatHappenedIsStatedNotThresholded() {
        XCTAssertEqual(
            MarketMapRail.exactMarginLabel(homeAbbr: "BC", awayAbbr: "RUT", margin: 7),
            "BC by 7")
        XCTAssertEqual(
            MarketMapRail.exactMarginLabel(homeAbbr: "LAR", awayAbbr: "NYG", margin: -13),
            "NYG by 13")
        XCTAssertFalse(
            MarketMapRail.exactMarginLabel(homeAbbr: "BC", awayAbbr: "RUT", margin: 7).hasSuffix("+"),
            "a final margin is not a threshold")
    }

    /// 🔴 THE ZERO CASE, WHICH IS THE ONE THAT WAS PHOTOGRAPHED. `NYG +0` over a
    /// 0–0 game. Nobody is ahead by nothing, and the side must not be resolved
    /// by a sign that cannot name it — `sideFinalMargin`'s lesson, one card up.
    func testADeadLevelGameIsNotCreditedToEitherSide() {
        for abbrs in [("LAR", "NYG"), ("NYG", "LAR")] {
            XCTAssertEqual(
                MarketMapRail.exactMarginLabel(homeAbbr: abbrs.0, awayAbbr: abbrs.1, margin: 0),
                "Tied")
            XCTAssertEqual(
                MarketMapRail.projectedMarginLabel(homeAbbr: abbrs.0, awayAbbr: abbrs.1, margin: 0),
                "Tied")
        }
    }

    /// The tie is one string, not three, so the three sites that can reach it
    /// cannot disagree about what a level game is called.
    func testTheTieIsNamedInOnePlace() {
        XCTAssertEqual(MarketMapRail.tiedMarginLabel, "Tied")
        XCTAssertEqual(
            MarketMapRail.exactMarginLabel(homeAbbr: "A", awayAbbr: "B", margin: 0),
            MarketMapRail.projectedMarginLabel(homeAbbr: "A", awayAbbr: "B", margin: 0))
    }

    // MARK: - No site builds its own

    /// 🔴 THE SCAN. `MarketMapView` built this sentence seven times — five in the
    /// banned spelling and two correctly on the axis — which is how one card came
    /// to carry two grammars. A new margin label assembled by hand is the way
    /// this comes back, so the interpolation itself is what is refused.
    ///
    /// Reproduced as a scan rather than a call because the builders are `private`
    /// on a SwiftUI `View` and return `private` types: no unit test can name
    /// their result (the same seam `AChartMarkerSitsOnAnObservedTime6718Tests`
    /// works around, for the same reason).
    func testNoMarginLabelIsAssembledByHand() throws {
        let source = try marketMapViewSource()

        for banned in ["Abbr) +\\(", "abbr) +\\("] {
            XCTAssertFalse(
                source.contains(banned),
                """
                `MarketMapView` interpolates a team abbreviation immediately \
                followed by `+` — the gambling price format #2442 banned. Build \
                the label with `MarketMapRail.marginThresholdLabel`, \
                `projectedMarginLabel` or `exactMarginLabel` instead.
                """)
        }

        XCTAssertFalse(
            source.contains("String(format: \"%.1f\", abs("),
            """
            a tile is formatting its own margin. That is how `LAR +10.0` came to \
            sit above a ladder printing `10`; the helpers share the ladder's \
            formatter.
            """)
    }

    /// 🟢 The positive half of the scan above — a scan that only forbids passes
    /// just as well on a file that draws no margin labels at all.
    func testEveryMarginLabelComesFromTheSharedGrammar() throws {
        let source = try marketMapViewSource()

        XCTAssertEqual(
            source.components(separatedBy: "MarketMapRail.marginThresholdLabel").count - 1, 5,
            "one ladder site and four axis ends")
        XCTAssertEqual(
            source.components(separatedBy: "MarketMapRail.projectedMarginLabel").count - 1, 2,
            "the full-game PROJECTION tile and the half PRE-GAME tile")
        XCTAssertEqual(
            source.components(separatedBy: "MarketMapRail.exactMarginLabel").count - 1, 2,
            "FINAL and ACTUAL")
    }

    // MARK: - Reading the source

    /// The view's CODE, with comment lines removed — #6718's idiom, for its
    /// reason. This file's own prose quotes `NYG +0` and `LAR +1.5` a dozen
    /// times because that is what the photograph said; a scan that read
    /// comments would be red on the day someone documents the defect they
    /// fixed. And the counts below would drift on a mention rather than a call.
    ///
    /// The non-empty assertion is the other half: an over-eager strip makes
    /// every `contains` pass and every count zero, which reads as a clean scan.
    private func marketMapViewSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // the project directory
            .appendingPathComponent("Bain Luck/Components/MarketMapView.swift")
        let stripped = try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertTrue(
            stripped.contains("private func marginLadder")
                || stripped.contains("func marginLadder"),
            "the comment strip left nothing to scan in MarketMapView.swift")
        return stripped
    }
}
