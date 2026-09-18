import XCTest
import SwiftUI
@testable import Bain_Luck

/// #7036 — Fulham's Championship Path card rendered entirely in white.
///
/// The reported defect: `bainluck://events/15310639`, Liverpool 0–0 Fulham. The
/// Fulham card drew a blank `FUL` chip, empty-looking bars and invisible
/// `31%` / `3%` / `1%`, beside a Liverpool card that was perfectly legible. The
/// cause was not a missing number — `Fulham.primary_color` is `#ffffff` and the
/// card is white.
///
/// `testFulhamsWhiteBrandColourIsNotPaintedOnAWhiteCard` is that case. The rest
/// hold the two properties that keep it fixed: **nothing below the floor is ever
/// returned as a drawing colour**, and **flooring one side never breaks #2902's
/// pair contract**.
///
/// Every assertion here is about a RESOLVED COLOUR. An assertion that the `31%`
/// text exists passes on the bug — that is how the same class survived #5165 on
/// the web — so text presence is deliberately not what any of these check.
final class TeamTextContrastTests: XCTestCase {

    private typealias C = TeamTextContrast
    private typealias P = ProbabilityBarPalette

    // MARK: - The reported defect

    func testFulhamsWhiteBrandColourIsNotPaintedOnAWhiteCard() {
        XCTAssertEqual(C.contrastVsCardSurface("#ffffff") ?? -1, 1.0, accuracy: 0.0001,
                       "white on white is 1:1 — the definition of invisible")
        XCTAssertFalse(C.readableOnCard("#ffffff"))
        XCTAssertNil(C.usableForText("#ffffff"),
                     "Fulham's colour must reach the palette as ABSENT, so the slot default applies")
    }

    func testLiverpoolKeepsItsCrestColour() {
        // The other half of the same card. A floor that also repaints the teams
        // that were fine is a redesign, not a fix.
        XCTAssertTrue(C.readableOnCard("#d11317"))
        XCTAssertEqual(C.usableForText("#d11317"), "#d11317")
    }

    func testTheReportedPairEndsUpAsTwoLegibleDistinguishableColours() {
        // The whole fix, through the exact entry point the event page calls.
        let pair = C.eventPageColorHexes(awayHex: "#ffffff",   // Fulham, away
                                         homeHex: "#d11317")   // Liverpool, home
        XCTAssertNotEqual(pair.away, "#FFFFFF", "Fulham's card is still being painted white on white")
        XCTAssertTrue(C.readableOnCard(pair.away), "away segment \(pair.away) is invisible on the card")
        XCTAssertTrue(C.readableOnCard(pair.home), "home segment \(pair.home) is invisible on the card")
        XCTAssertEqual(pair.home, "#D11317", "Liverpool's own crest colour must survive the fix")
        XCTAssertTrue(P.distinguishable(pair.away, pair.home),
                      "\(pair.away)/\(pair.home) — flooring one side collapsed #2902's pair contract")
    }

    func testTheEventPageEntryPointNeverYieldsAnInvisibleSideForAnyStoredColour() {
        // The property that makes this a fix rather than a special case for
        // Fulham: whatever pair of stored colours the page is handed, neither
        // resolved side is invisible and the two still read apart.
        let stored: [String?] = [nil, "", "#ffffff", "#FFFFFF", "ffffff", "#ffff00", "#fdb927",
                                 "#d11317", "#2563EB", "#64748B", "#000000", "not-a-color"]
        for away in stored {
            for home in stored {
                let pair = C.eventPageColorHexes(awayHex: away, homeHex: home)
                XCTAssertTrue(C.readableOnCard(pair.away),
                              "away \(String(describing: away)) / home \(String(describing: home)) -> \(pair.away) is invisible")
                XCTAssertTrue(C.readableOnCard(pair.home),
                              "away \(String(describing: away)) / home \(String(describing: home)) -> \(pair.home) is invisible")
                XCTAssertTrue(P.distinguishable(pair.away, pair.home),
                              "away \(String(describing: away)) / home \(String(describing: home)) -> \(pair.away)/\(pair.home) do not read apart")
            }
        }
    }

    /// The floor is only worth anything if the page actually goes through it, and
    /// that last hop is a line of view code no unit test can execute.
    ///
    /// So it is asserted on the source. `EventDetailView.teamColors` is the
    /// single funnel for all ~13 team-coloured elements on the page; a revert to
    /// `ProbabilityBarPalette.colors(awayHex: event.awayTeamData?.primaryColor…)`
    /// compiles, renders, and leaves every other test in this file green.
    func testTheEventPageIsWiredThroughTheFloor() throws {
        let source = try String(contentsOf: Self.eventDetailViewURL, encoding: .utf8)
        let funnel = try XCTUnwrap(
            source.range(of: "private func teamColors(_ event: EventDetail)"),
            "EventDetailView.teamColors has been renamed — re-aim this guard, do not delete it"
        )
        let body = source[funnel.lowerBound...].prefix(600)
        XCTAssertTrue(body.contains("TeamTextContrast.eventPageColors"),
                      "teamColors no longer routes through the #7036 floor")
        XCTAssertFalse(body.contains("ProbabilityBarPalette.colors"),
                       "teamColors calls the palette directly again, bypassing the floor")
    }

    /// Resolved from `#filePath`, and deliberately not by walking up from the
    /// process's working directory.
    ///
    /// 🪤 `#filePath` keeps the spelling the compiler was given (`/tmp/…`) while
    /// `FileManager` hands back the standardised one (`/private/tmp/…`), so any
    /// prefix arithmetic between the two silently produces a path with its
    /// middle eaten out — the failure that made 11 unrelated tree-scan classes
    /// read as product defects. Going straight up the URL avoids the subtraction
    /// entirely.
    private static var eventDetailViewURL: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/TeamTextContrastTests.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
    }

    // MARK: - The floor itself

    func testTheFloorSitsExactlyAtThreeToOneAndNotOneShadeEitherSide() {
        XCTAssertEqual(C.minimumRatio, 3.0,
                       "native and web must answer this question with the same number (#5165)")
        // The tightest pair of greys the floor can separate — one 8-bit step
        // apart, straddling 3:1. Asserting `readableOnCard(x) == (ratio(x) >= 3)`
        // instead would restate the implementation and pass against any floor at
        // all; this pins the number itself, so moving it to 2.9 or 3.1 reddens
        // one of the two lines.
        XCTAssertEqual(C.contrastVsCardSurface("#949494") ?? 0, 3.034, accuracy: 0.005)
        XCTAssertEqual(C.contrastVsCardSurface("#959595") ?? 0, 2.996, accuracy: 0.005)
        XCTAssertTrue(C.readableOnCard("#949494"), "3.03:1 is over the floor and must be kept")
        XCTAssertFalse(C.readableOnCard("#959595"), "2.996:1 is under the floor and must be replaced")

        // The tightest case that exists at all. Brute-forcing all 2^24 8-bit
        // colours: NONE lands exactly on 3.0, and the nearest — `#E969A1` at
        // 3.0000001929942766 — clears it by 1.9e-07. That is why the mutation
        // run's `>=` → `>` mutant SURVIVES and is recorded as an equivalent
        // mutant rather than a gap: the two operators cannot disagree on any
        // input this function can be given. Kept as a case because it is the
        // real discriminator — a floor nudged up by a millionth rejects it.
        XCTAssertTrue(C.readableOnCard("#E969A1"),
                      "the closest colour to the floor in the whole 8-bit space must still be kept")
    }

    func testColoursBrightEnoughToVanishAreAllRejected() {
        // The head of #5165's measured distribution: the ones a reader loses.
        for hex in ["#ffffff", "#FFFFFF", "#fffffe", "#ffff00", "#FACF08", "#fdb927"] {
            XCTAssertFalse(C.readableOnCard(hex), "\(hex) is under 3:1 on white and must not be drawn with")
            XCTAssertNil(C.usableForText(hex))
        }
    }

    func testOrdinaryCrestColoursAreUntouched() {
        for hex in ["#d11317", "#2563EB", "#64748B", "#111827", "#552583", "#006341"] {
            XCTAssertTrue(C.readableOnCard(hex), "\(hex) clears 3:1 and must keep its crest colour")
            XCTAssertEqual(C.usableForText(hex), hex)
        }
    }

    func testBothPaletteDefaultsClearTheFloorThemselves() {
        // Load-bearing: the fallback for a floored team is the palette's slot
        // default. If a default were itself under the floor, this fix would swap
        // one invisible colour for another and every other test here would still
        // pass.
        XCTAssertTrue(C.readableOnCard(P.awayDefault), "away default \(P.awayDefault) is not legible on a card")
        XCTAssertTrue(C.readableOnCard(P.homeDefault), "home default \(P.homeDefault) is not legible on a card")
    }

    /// One ladder rung is itself under the floor, and this records it rather
    /// than asserting it away.
    ///
    /// `#F59E0B` (amber-500) is **2.15:1** on white. It is a rung of #2902's
    /// shared `ladder`, which `partner(for:preferring:)` walks only when the
    /// slot's own default is within 60 of the other side's colour — and it can
    /// only reach amber when a crest is within 60 of `#64748B` **and** of
    /// `#2563EB`, which are 116 apart. So the band is real (roughly `#446BBB`)
    /// and narrow, and no club in the current table sits in it.
    ///
    /// Repairing it means moving a constant that #2902's own contract tests are
    /// written against — a passenger this fix does not get to carry silently. It
    /// is filed on #7036 instead, with this measurement. The test asserts the
    /// hole is exactly where it is believed to be, so the day somebody fixes the
    /// rung, this reddens and gets deleted on purpose rather than quietly
    /// covering a second one that appears.
    func testTheOneLadderRungUnderTheFloorIsTheKnownOne() {
        let unreadable = P.ladder.filter { !C.readableOnCard($0) }
        XCTAssertEqual(unreadable, ["#F59E0B"],
                       "the set of illegible ladder rungs changed — see #7036 before touching this")
        XCTAssertEqual(C.contrastVsCardSurface("#F59E0B") ?? 0, 2.15, accuracy: 0.02)
    }

    // MARK: - Absence is not a colour

    func testAnAbsentOrUnparseableColourIsNotCalledReadable() {
        // `readableOnCard` answering `true` for nil would hand the palette a
        // colour it cannot parse; answering with a *substitute* here would take
        // the decision away from the palette. Absent in, absent out.
        for hex in [nil, "", "not-a-color", "#fff", "#ggggggg", "  "] {
            XCTAssertNil(C.relativeLuminance(hex), "\(String(describing: hex)) has no luminance")
            XCTAssertNil(C.contrastVsCardSurface(hex))
            XCTAssertFalse(C.readableOnCard(hex))
            XCTAssertNil(C.usableForText(hex))
        }
    }

    func testParsingAgreesWithThePaletteExactly() {
        // Two spellings of "is this a colour" is the way this drifts: a value
        // this type floors as unparseable while the palette paints it happily.
        for hex in ["#ffffff", "ffffff", "#d11317", "#fff", "", "not-a-color", "#GGGGGG"] {
            XCTAssertEqual(C.relativeLuminance(hex) != nil, P.rgb(hex) != nil,
                           "\(hex): TeamTextContrast and ProbabilityBarPalette disagree about whether this is a colour")
        }
    }

    func testAHexWithoutItsHashIsStillJudged() {
        // The palette accepts both spellings, so the floor must too — otherwise
        // a hash-less white is "unparseable", reaches the palette as absent for
        // the wrong reason, and the right thing happens by accident.
        XCTAssertEqual(C.contrastVsCardSurface("ffffff"), C.contrastVsCardSurface("#ffffff"))
        XCTAssertFalse(C.readableOnCard("ffffff"))
    }

    // MARK: - Luminance maths

    func testLuminanceEndpointsAndOrdering() {
        XCTAssertEqual(C.relativeLuminance("#000000") ?? -1, 0.0, accuracy: 0.0001)
        XCTAssertEqual(C.relativeLuminance("#ffffff") ?? -1, 1.0, accuracy: 0.0001)
        XCTAssertEqual(C.contrastVsCardSurface("#000000") ?? 0, 21.0, accuracy: 0.05,
                       "black on white is WCAG's maximum, 21:1")
        // Green is weighted far above blue: a channel-order slip in the
        // coefficients is invisible to a black/white test and shows up here.
        let green = C.relativeLuminance("#00ff00") ?? 0
        let red = C.relativeLuminance("#ff0000") ?? 0
        let blue = C.relativeLuminance("#0000ff") ?? 0
        XCTAssertGreaterThan(green, red)
        XCTAssertGreaterThan(red, blue)
        XCTAssertEqual(green, 0.7152, accuracy: 0.0005)
        XCTAssertEqual(red, 0.2126, accuracy: 0.0005)
        XCTAssertEqual(blue, 0.0722, accuracy: 0.0005)
    }

    func testTheLowChannelBranchIsExercised() {
        // `c <= 0.04045` is the linear branch. `#0a0a0a` (10/255 = 0.039) sits
        // inside it; without a case here the branch is never run and could be
        // deleted with every test still green.
        let dark = C.relativeLuminance("#0a0a0a")
        XCTAssertNotNil(dark)
        XCTAssertEqual(dark ?? -1, (10.0 / 255.0) / 12.92, accuracy: 0.0001)
    }

    // MARK: - Totality

    func testEveryStoredColourShapeReturnsAnAnswerAndNeverAnInvisibleOne() {
        // Totality: whatever the column holds, `usableForText` either returns a
        // colour that clears the floor or returns nothing. There is no input
        // that produces a drawable invisible colour.
        let inputs: [String?] = [nil, "", " ", "#ffffff", "#FFFFFF", "ffffff", "#fffffe",
                                 "#d11317", "#000000", "#ffff00", "#7f7f7f", "#808080",
                                 "not-a-color", "#12345", "#1234567", "#GGGGGG"]
        for hex in inputs {
            if let out = C.usableForText(hex) {
                XCTAssertTrue(C.readableOnCard(out),
                              "\(String(describing: hex)) produced \(out), which is invisible on a card")
                XCTAssertEqual(out, hex, "usableForText must return the input or nothing — never a substitute")
            }
        }
    }
}
