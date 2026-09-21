import XCTest
@testable import Bain_Luck

/// #7655 — A LIVE PRICE MAY NOT WEAR A PRE-GAME TENSE.
///
/// THE PHOTOGRAPH: event 14780544 (`Colts 13 at Chiefs 10`, `live`, 37:45 left),
/// iPhone 17 at phone width, production, 2026-09-20 18:27 PT,
/// `artifacts-native-020/n278-before-2150.png`:
///
/// ```
/// Projected combined points
///    27.5+   PRE-GAME   ███████████   99%
///    36.5+   PRE-GAME   █████████     82%
///    44.5+   PRE-GAME   █████████     82%
///    50.5+   PRE-GAME   ███████       67%
///    59.5+   PRE-GAME   █████         36%
/// ```
///
/// 23 points were already on the board. `27.5+` prices at 99% *because* the game
/// is underway — it is the most live number on the card — and it is captioned as
/// though the game had not started.
///
/// 🔴 **THE MECHANISM IS A TENSE WITH TWO MEANINGS.**
/// ``MarketMapRail/SpectrumTense/of(finalTotal:isSettled:)`` answers `.projected`
/// for "not over and nothing to grade", and a third quarter satisfies both. Every
/// consumer of `.projected` therefore inherited "pre-game" as a synonym for "no
/// verdict yet". #3850 fixed the settled arm and #4018 the abandoned one; the live
/// arm was the one nobody had looked at, because the word is TRUE on the card the
/// caption was written for.
///
/// 🟠 **WHY NOTHING IS DRAWN IN ITS PLACE.** #6290 is the same false tense over a
/// LINE and had an honest substitute — `opening_odds.over_under`, a served
/// pre-game number. There is no per-rung equivalent, and that is measured rather
/// than assumed: #3925 records that `movement` carries no capture timestamp, that
/// 28 of 566 openings were captured 52–172 minutes after first pitch, and that
/// 51.4% have no opening at all. The alternative to dropping the word is inventing
/// one for "this is the price now", which would be a second tense vocabulary on a
/// screen Alex ruled must have exactly one. An uncaptioned row is a line, a bar
/// and a percentage — which is what the graded row beside it already looks like.
///
/// The gate lives in ``MarketMapRail/spectrumRowCaption(finalTotal:isSettled:canStillBeGraded:hasStarted:rungResult:)``
/// beside #4018's, for the reason that whole file exists: `TotalPointsSpectrumView`
/// is SwiftUI and cannot be asserted without rasterising it.
final class ALiveLadderRungDoesNotSayPreGame7655Tests: XCTestCase {

    private func caption(
        hasStarted: Bool,
        isSettled: Bool = false,
        finalTotal: Int? = nil,
        canStillBeGraded: Bool = true,
        rungResult: MarketMapRail.TotalLadderResult? = nil
    ) -> String? {
        MarketMapRail.spectrumRowCaption(
            finalTotal: finalTotal,
            isSettled: isSettled,
            canStillBeGraded: canStillBeGraded,
            hasStarted: hasStarted,
            rungResult: rungResult
        )
    }

    // MARK: - The defect

    /// The photographed row, as a value. Five rungs, none of them cleared yet,
    /// on a game that has started.
    func testNoUngradedRungOfALiveLadderIsCaptionedPreGame() {
        for _ in 0..<5 {
            XCTAssertNil(
                caption(hasStarted: true),
                "a rung priced during the game may not be captioned PRE-GAME"
            )
        }
    }

    /// 🔴 **THE PAIR THAT IS THE WHOLE FIX.** Same card, same rung, same absence of
    /// a verdict — the ONLY thing that differs is whether the clock has passed
    /// kickoff. Before #7655 both sides answered `PRE-GAME`, so this is the
    /// assertion the shipped code could not have satisfied.
    func testTheClockIsTheOnlyThingThatDecidesIt() {
        XCTAssertEqual(
            caption(hasStarted: false), "PRE-GAME",
            "before kickoff the word is true and must still print"
        )
        XCTAssertNil(
            caption(hasStarted: true),
            "after kickoff the same row must lose it"
        )
    }

    // MARK: - What the gate must NOT reach

    /// 🟠 The gate is scoped to the `.projected` arm. A finished match has
    /// obviously started, and #3925's `LAST QUOTE` must survive that — reading
    /// `hasStarted` alone, without asking the tense, would silence it and re-open
    /// #3925 in the act of closing this.
    func testASettledCardKeepsItsLastQuoteEvenThoughItObviouslyStarted() {
        let settled = caption(hasStarted: true, isSettled: true, canStillBeGraded: false)
        XCTAssertEqual(
            settled, MarketMapRail.spectrumRungCaption(finalTotal: nil, isSettled: true),
            "#3925: a settled tennis card still names its tense"
        )
        XCTAssertNotNil(settled)
        XCTAssertNotEqual(settled, "PRE-GAME")
    }

    /// A finished, gradeable card is unchanged: the verdict badge owns every row
    /// and has since #3850, whatever the clock says.
    func testAGradedCardIsUnchanged() {
        XCTAssertNil(
            caption(hasStarted: true, isSettled: true, finalTotal: 11,
                    canStillBeGraded: false, rungResult: .over)
        )
        XCTAssertNil(
            caption(hasStarted: false, isSettled: true, finalTotal: 11,
                    canStillBeGraded: false, rungResult: .over)
        )
    }

    /// #4018's abandoned game wears no chip on either side of kickoff. The two
    /// gates are independent, so closing this one cannot have re-opened that one.
    func testAnAbandonedGameIsStillChipless() {
        for started in [true, false] {
            XCTAssertNil(
                caption(hasStarted: started, canStillBeGraded: false),
                "#4018: a game that can never be graded wears no chip"
            )
        }
    }

    // MARK: - The exhaustive table

    /// Every reachable combination, stated once, so a later change to any clause
    /// has to come through here. `canStillBeGraded` is false exactly where the
    /// production card sets it false (settled, or abandoned).
    func testTheWholeTruthTable() {
        // (hasStarted, isSettled, finalTotal, canStillBeGraded, verdict) -> caption
        let cases: [(Bool, Bool, Int?, Bool, MarketMapRail.TotalLadderResult?, String?)] = [
            // Pre-game, nothing graded: the one surviving PRE-GAME.
            (false, false, nil, true, nil, "PRE-GAME"),
            // Live, ungraded: #7655.
            (true, false, nil, true, nil, nil),
            // Live, this rung cleared: #4907's badge.
            (true, false, nil, true, .over, nil),
            // Settled, no final in this unit: #3925's last quote.
            (true, true, nil, false, nil, SettledQuote.prefix.uppercased()),
            // Settled with a final: #3850's badge owns it.
            (true, true, 11, false, .over, nil),
            // Abandoned: #4018.
            (true, false, nil, false, nil, nil),
        ]
        for (started, settled, final, gradeable, verdict, expected) in cases {
            XCTAssertEqual(
                caption(hasStarted: started, isSettled: settled, finalTotal: final,
                        canStillBeGraded: gradeable, rungResult: verdict),
                expected,
                "started=\(started) settled=\(settled) final=\(String(describing: final)) "
                + "gradeable=\(gradeable) verdict=\(String(describing: verdict))"
            )
        }
    }

    /// 🟢 **PRE-GAME IS STILL REACHABLE.** A gate that suppressed the caption
    /// everywhere would pass every test above — they are all `XCTAssertNil` bar
    /// two — so this states the positive separately: exactly one of the six rows
    /// in the table prints it, and it is the one whose game has not begun.
    func testPreGameSurvivesOnExactlyTheRowThatEarnsIt() {
        let started = [true, false]
        let printed = started.filter { caption(hasStarted: $0) == "PRE-GAME" }
        XCTAssertEqual(printed, [false], "only the not-yet-started card says PRE-GAME")
    }

    // MARK: - The call site

    /// 🔴 **THE INERT FIX IS THE REAL HAZARD HERE, AND NOTHING ABOVE CAN SEE IT.**
    /// Every assertion in this file is about a pure function taking a `Bool`. Wire
    /// the view to `hasStarted: false` — or to any constant — and the rule stays
    /// perfect, the suite stays green, and the phone shows exactly the frame
    /// `n278-before-2150.png` photographed. `TotalPointsSpectrumView.ladderRow` is
    /// SwiftUI and cannot be rasterised here, so the wiring is read from the
    /// source, the way #6290's page wiring is.
    ///
    /// 🟠 **COMMENTS ARE STRIPPED FIRST.** `hasStarted` appears in the prose
    /// explaining the call site as well as in the call itself, so a raw-file scan
    /// would count this test's own explanation as the wiring it is checking.
    func testTheLadderRowActuallyPassesTheClock() throws {
        let code = try Self.code(at: "Bain Luck/Components/TotalPointsSpectrumView.swift")

        XCTAssertEqual(
            Self.occurrences(of: "hasStarted: isLive || EventState.hasStarted(commenceTime: commenceTime)", in: code), 1,
            "the ladder must be handed the live status OR the clock — a constant, "
            + "or `isPre`, makes this whole ship inert"
        )
        for constant in ["hasStarted: true", "hasStarted: false"] {
            XCTAssertEqual(
                Self.occurrences(of: constant, in: code), 0,
                "\(constant) at the call site is a fix that does nothing"
            )
        }

        // 🟠 EXACTLY ONE, AND THIS IS THE CLAUSE THAT KEEPS THE COMMENT-STRIPPER
        // HONEST. The raw file mentions `hasStarted:` twice — once in the
        // DocC link naming the rail function, once in the call — so this count
        // is 2 without the strip and 1 with it. Drop the strip and this reds,
        // which is the only way this file can prove its own scan is reading
        // code rather than prose. It doubles as the real assertion: the ladder
        // is handed the clock in one place, not several that can disagree.
        XCTAssertEqual(
            Self.occurrences(of: "hasStarted:", in: code), 1,
            "the clock reaches the caption through exactly one call"
        )

        let row = try XCTUnwrap(
            Self.function(named: "ladderRow", in: code),
            "ladderRow moved or was renamed — this scan is now grading nothing"
        )
        XCTAssertTrue(
            row.contains("MarketMapRail.spectrumRowCaption("),
            "the row must still defer to the rail rather than re-deriving the caption"
        )
        XCTAssertTrue(row.contains("hasStarted:"), "…and must pass the clock to it")
    }

    // MARK: - Reading the source

    private static func code(at path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)      // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()               // …/BainLuckTests
            .deletingLastPathComponent()               // …/ios/Bain Luck
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    private static func occurrences(of needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }

    /// The body of one declaration, signature to the brace that closes it at the
    /// same indentation. Enough to tell what a declaration reads; deliberately not
    /// a parser. Same shape as #6290's, which is the file this idiom comes from.
    private static func function(named name: String, in code: String) -> String? {
        let lines = code.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        guard let start = lines.firstIndex(where: {
            $0.contains("func \(name)(") || $0.contains("var \(name):")
        }) else { return nil }
        let indent = lines[start].prefix(while: { $0 == " " }).count
        let close = String(repeating: " ", count: indent) + "}"
        guard let end = lines[(start + 1)...].firstIndex(where: { $0 == close }) else { return nil }
        return lines[start...end].joined(separator: "\n")
    }
}
