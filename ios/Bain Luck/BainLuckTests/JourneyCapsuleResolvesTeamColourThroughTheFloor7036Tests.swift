import XCTest
#if canImport(UIKit)
import UIKit
#endif
@testable import Bain_Luck

/// #7036, sixth arm — the playoff-journey card's probability CAPSULE, the site
/// the issue opened with.
///
/// `TeamTextContrast`'s docstring lists three things Fulham's card lost, and
/// names the second of them in as many words: *"the Relegated bar was a white
/// capsule on a near-white track"*. Arms 1–5 fixed the crest chip and the
/// numbers. The bar was still raw on master five arms later, because the journey
/// card reads `journey.teamColor` — the same stored hex under a local name — so
/// every search for `primaryColor` walked past it.
///
/// **Two claims are under test here and they are different claims.**
///
/// 1. *The resolution.* `progressFillHex` floors the stored colour to the row's
///    own existing default, and `edgeAccentHex` answers `nil` — which is what the
///    stripe already does for a club with no colour at all.
/// 2. *The pixels.* A floor stated against pure white does not, by itself, say
///    anything about a capsule drawn at half alpha ON a track ON a grouped-card
///    surface. So the composite is computed from the **real resolved system
///    colours** (`.tertiarySystemGroupedBackground`, `.secondaryLabel`) rather
///    than argued in prose, and the before/after is asserted as a SIGN CHANGE:
///    today a white bar composites LIGHTER than its own track, so a full bar
///    reads as an empty one.
///
/// 🪤 **Claim 2's arithmetic is a second spelling of the luminance formula, and
/// a second spelling can silently be a different scale.** `testTheCompositeLuminanceAgreesWithTheFloorsOwnFormula`
/// pins the local `luminance(of:)` against `TeamTextContrast.relativeLuminance`
/// on the same colour, so the composite numbers below cannot drift onto a scale
/// of their own while every assertion stays green.
final class JourneyCapsuleResolvesTeamColourThroughTheFloor7036Tests: XCTestCase {

    // Three clubs a person can follow today, with the hexes
    // `/api/shared/team-futures` served on 2026-09-20 and the stage the card
    // draws for them.
    private let saintsSand = "#d3bc8d"        // NFC South Division Winner, 45.5%
    private let predatorsGold = "#fdba31"     // NHL Central Division Winner, 2%
    private let warriorsGold = "#fdb927"      // NBA Championship Winner, 1.3%

    // MARK: - Claim 1: the resolution

    func testAWhiteShirtedClubsBarIsDrawnInTheRowsOwnDefault() {
        XCTAssertEqual(MyStuffTeamTextColour.progressFillHex("#ffffff"),
                       MyStuffTeamTextColour.fallbackHex,
                       "Fulham's capsule is still being filled with #ffffff")
    }

    /// The three specimens above, by hex, so this suite fails if the floor is
    /// raised or lowered past the population it was measured on.
    func testTheThreeClubsServedTodayAllLandOnTheDefault() {
        for hex in [saintsSand, predatorsGold, warriorsGold] {
            XCTAssertLessThan(TeamTextContrast.contrastVsCardSurface(hex) ?? 0, 3.0,
                              "\(hex) was measured under the floor on 2026-09-20")
            XCTAssertEqual(MyStuffTeamTextColour.progressFillHex(hex),
                           MyStuffTeamTextColour.fallbackHex,
                           "\(hex) draws a bar a reader cannot separate from its track")
        }
    }

    func testAReadableClubKeepsItsOwnColour() {
        XCTAssertEqual(MyStuffTeamTextColour.progressFillHex("#d11317").lowercased(), "#d11317",
                       "a club that clears the floor must be passed through untouched")
    }

    func testAnAbsentOrUnparseableColourLandsOnTheDefault() {
        XCTAssertEqual(MyStuffTeamTextColour.progressFillHex(nil), MyStuffTeamTextColour.fallbackHex)
        XCTAssertEqual(MyStuffTeamTextColour.progressFillHex("not a colour"), MyStuffTeamTextColour.fallbackHex)
    }

    /// The stripe answers ABSENCE, not the grey default — a club with no stored
    /// colour draws no stripe at all, and that is what an unusable colour must
    /// look like too.
    func testTheLeadingStripeIsDroppedRatherThanRecoloured() {
        XCTAssertNil(MyStuffTeamTextColour.edgeAccentHex("#ffffff"))
        XCTAssertNil(MyStuffTeamTextColour.edgeAccentHex(saintsSand))
        XCTAssertNil(MyStuffTeamTextColour.edgeAccentHex(nil))
        XCTAssertNotEqual(MyStuffTeamTextColour.edgeAccentHex("#ffffff"), MyStuffTeamTextColour.fallbackHex,
                          "an unreadable club must not be handed an accent this card has never drawn")
        XCTAssertEqual(MyStuffTeamTextColour.edgeAccentHex("#d11317")?.lowercased(), "#d11317")
    }

    /// The fallback has to clear the floor itself, or this swaps one invisible
    /// fill for another.
    func testTheDefaultClearsTheFloorItStandsInFor() {
        XCTAssertTrue(TeamTextContrast.readableOnCard(MyStuffTeamTextColour.fallbackHex))
        XCTAssertEqual(TeamTextContrast.contrastVsCardSurface(MyStuffTeamTextColour.fallbackHex) ?? 0,
                       4.83, accuracy: 0.01)
    }

    // MARK: - Claim 2: the pixels, from the real resolved system colours

    #if canImport(UIKit)

    /// The card is `Color.cardBackgroundDark` = `.tertiarySystemGroupedBackground`.
    private var cardSurface: UIColor {
        UIColor.tertiarySystemGroupedBackground.resolvedColor(with: UITraitCollection(userInterfaceStyle: .light))
    }

    /// The empty half of the bar: `Capsule().fill(Color.secondary.opacity(0.15))`
    /// — `.secondaryLabel`, whose own alpha multiplies with the 0.15.
    private var trackComposite: UIColor {
        let secondary = UIColor.secondaryLabel.resolvedColor(with: UITraitCollection(userInterfaceStyle: .light))
        return Self.composite(secondary, extraAlpha: 0.15, over: cardSurface)
    }

    /// 🪤 The filled half is drawn INSIDE the same `ZStack`, so it composites over
    /// the track, not over the card. Compositing it over the card instead makes
    /// white look better than it is and hides the sign change entirely.
    private func fillComposite(_ hex: String) -> UIColor {
        Self.composite(Self.opaque(hex), extraAlpha: 0.5, over: trackComposite)
    }

    /// Parsed through `ProbabilityBarPalette.rgb` — the same scan
    /// `TeamTextContrast` uses — rather than a second hex reader that could
    /// disagree with the floor about what a colour is.
    private static func opaque(_ hex: String) -> UIColor {
        guard let rgb = ProbabilityBarPalette.rgb(hex) else {
            XCTFail("\(hex) did not parse; every specimen in this suite must")
            return .black
        }
        return UIColor(red: CGFloat(rgb.r) / 255.0,
                       green: CGFloat(rgb.g) / 255.0,
                       blue: CGFloat(rgb.b) / 255.0,
                       alpha: 1)
    }

    /// The defect, measured: a full white bar is LIGHTER than the track it sits
    /// in, so the reader sees a paler gap where the probability should be — the
    /// one direction that reads as *empty* rather than as *unstyled*.
    func testTodaysWhiteBarCompositesLighterThanItsOwnTrack() {
        let track = Self.luminance(of: trackComposite)
        let white = Self.luminance(of: fillComposite("#ffffff"))

        XCTAssertGreaterThan(white, track,
                             "the premise of this fix is that a white fill is lighter than the track")
        XCTAssertLessThan(Self.contrast(white, track), 1.15,
                          "a white fill and its track are within 1.15:1 — indistinguishable at 4pt")
    }

    /// The same three served clubs, before the floor: every one of them within
    /// 1.35:1 of its own track.
    func testTheThreeServedClubsAreAllIndistinguishableFromTheirTrack() {
        let track = Self.luminance(of: trackComposite)
        for hex in ["#ffffff", saintsSand, predatorsGold, warriorsGold] {
            let ratio = Self.contrast(Self.luminance(of: fillComposite(hex)), track)
            XCTAssertLessThan(ratio, 1.35, "\(hex) fills its bar at \(ratio):1 against the track")
        }
    }

    /// And after: the resolved fill is DARKER than the track and separated from
    /// it — the sign change is the fix.
    func testTheResolvedFillIsDarkerThanTheTrackAndSeparatedFromIt() {
        let track = Self.luminance(of: trackComposite)
        let resolved = Self.luminance(of: fillComposite(MyStuffTeamTextColour.progressFillHex("#ffffff")))

        XCTAssertLessThan(resolved, track, "a filled bar must be darker than its empty track")
        XCTAssertGreaterThan(Self.contrast(track, resolved), 1.5,
                             "the resolved fill must clear its track by more than the 1.15:1 white managed")
    }

    /// A club that clears the floor is not repainted, and its bar is not made
    /// worse by passing through the helper.
    func testAReadableClubsBarIsUnchangedByTheFloor() {
        let before = Self.luminance(of: fillComposite("#d11317"))
        let after = Self.luminance(of: fillComposite(MyStuffTeamTextColour.progressFillHex("#d11317")))
        XCTAssertEqual(before, after, accuracy: 0.0001, "#d11317 must reach the capsule untouched")
    }

    /// 🪤 Strawman for every number above: the local composite arithmetic is a
    /// SECOND spelling of the luminance formula, and two spellings can be on two
    /// scales while both look plausible. Pinned against the floor's own function.
    func testTheCompositeLuminanceAgreesWithTheFloorsOwnFormula() throws {
        for hex in ["#ffffff", "#6b7280", "#d11317", saintsSand] {
            let mine = Self.luminance(of: Self.opaque(hex))
            let theirs = try XCTUnwrap(TeamTextContrast.relativeLuminance(hex))
            XCTAssertEqual(mine, theirs, accuracy: 0.001, "\(hex) is being measured on two different scales")
        }
    }

    /// Strawman: the two system colours resolve to the light-mode surfaces this
    /// card is actually drawn on, so the composites are not measuring black.
    func testTheSystemSurfacesResolveToTheLightModeCard() {
        XCTAssertGreaterThan(Self.luminance(of: cardSurface), 0.8, "the card surface is near-white in light mode")
        XCTAssertLessThan(Self.luminance(of: cardSurface), 1.0, "the card surface is not pure white")
        XCTAssertLessThan(Self.luminance(of: trackComposite), Self.luminance(of: cardSurface),
                          "the empty track is a shade darker than the card it sits on")
    }

    private static func composite(_ colour: UIColor, extraAlpha: CGFloat, over background: UIColor) -> UIColor {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        colour.getRed(&r, green: &g, blue: &b, alpha: &a)
        var br: CGFloat = 0, bg: CGFloat = 0, bb: CGFloat = 0, ba: CGFloat = 0
        background.getRed(&br, green: &bg, blue: &bb, alpha: &ba)
        let alpha = a * extraAlpha
        return UIColor(red: r * alpha + br * (1 - alpha),
                       green: g * alpha + bg * (1 - alpha),
                       blue: b * alpha + bb * (1 - alpha),
                       alpha: 1)
    }

    /// WCAG relative luminance, the same formula `TeamTextContrast` uses, on a
    /// resolved `UIColor` rather than a hex.
    private static func luminance(of colour: UIColor) -> Double {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        colour.getRed(&r, green: &g, blue: &b, alpha: &a)
        func channel(_ v: CGFloat) -> Double {
            let c = Double(v)
            return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    }

    private static func contrast(_ a: Double, _ b: Double) -> Double {
        let hi = max(a, b), lo = min(a, b)
        return (hi + 0.05) / (lo + 0.05)
    }

    #endif

    // MARK: - The wiring, which no assertion above can reach

    /// `PlayoffJourneyCard` is file-private, so the two lines this arm changes
    /// cannot be called from a test. These anchors are the only thing standing
    /// between a correct helper and a call site that quietly goes back to
    /// painting the stored hex raw.
    func testTheCapsuleAndTheStripeRouteThroughTheFloor() throws {
        let body = try Self.myStuffViewCode()

        XCTAssertTrue(body.contains("Color(hex: MyStuffTeamTextColour.progressFillHex(journey.teamColor)).opacity(0.5)"),
                      "the journey card's probability capsule is not routing through the floor")
        XCTAssertTrue(body.contains("if let c = MyStuffTeamTextColour.edgeAccentHex(journey.teamColor)"),
                      "the journey card's leading stripe is not routing through the floor")
        XCTAssertFalse(body.contains("Color(hex: journey.teamColor ?? \"#6b7280\").opacity(0.5)"),
                       "the capsule is being filled from the raw stored colour again")
        XCTAssertFalse(body.contains("if let c = journey.teamColor {"),
                       "the stripe is being drawn from the raw stored colour again")
    }

    /// 🪤 **The blanket assertion this file could not carry until now, and the
    /// reason the capsule survived five arms.** Every earlier suite had to anchor
    /// on one spelling at a time (`item.matchedTeam?.primaryColor`), because a
    /// blanket rule failed on the two `journey.teamColor` sites — so the guard
    /// with the power to find an unnamed site was exactly the guard nobody could
    /// write. With those two resolved, every `Color(hex:` in this file names a
    /// resolver, and a SEVENTH site added tomorrow fails here on its first run.
    ///
    /// This is an existence rule over every occurrence, not a ban on one string:
    /// a ban cannot see the site nobody thought of.
    func testEveryColourInThisFileNamesAResolver() throws {
        let body = try Self.myStuffViewCode()

        let occurrences = body.components(separatedBy: "Color(hex:").dropFirst()
        XCTAssertGreaterThanOrEqual(occurrences.count, 6,
                                    "the scan found fewer colour sites than this file has — check the needle")
        for (index, tail) in occurrences.enumerated() {
            XCTAssertTrue(tail.hasPrefix(" MyStuffTeamTextColour.") || tail.hasPrefix(" c)"),
                          "Color(hex: site #\(index + 1) paints a colour that never met the #7036 floor: "
                          + String(tail.prefix(70)))
        }
    }

    /// Strawman: the scan reads a real file with real content, so the
    /// `XCTAssertFalse`s above cannot be passing because the read came back empty
    /// — and the comment stripper cannot be eating the code it is meant to keep.
    func testTheSourceScanIsReadingTheFileItThinksItIs() throws {
        let raw = try String(contentsOf: Self.myStuffViewURL, encoding: .utf8)
        let code = try Self.myStuffViewCode()

        XCTAssertGreaterThan(raw.count, 10_000, "MyStuffView.swift read back far too small")
        XCTAssertTrue(raw.contains("import SwiftUI"), "that is not the Swift file")
        XCTAssertTrue(code.contains("private struct PlayoffJourneyCard"), "the journey card is not in the code scanned")
        XCTAssertGreaterThan(Double(code.count) / Double(raw.count), 0.5,
                             "the comment stripper removed more than half the file — it is eating code")
        XCTAssertFalse(code.contains("/// #7036, sixth arm"),
                       "the comment stripper is not removing doc comments, so a docstring can satisfy a code assertion")
    }

    /// 🪤 **The scan reads CODE, not the file.** Every needle below also appears
    /// in the docstrings that explain it — this suite's first run passed
    /// `testEveryColourInThisFileNamesAResolver` on a prose mention of
    /// `Color(hex:` inside a comment, which is a guard grading its own
    /// explanation. Comment lines are dropped before anything is matched.
    private static func myStuffViewCode() throws -> String {
        try String(contentsOf: myStuffViewURL, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// 🪤 `#filePath` keeps the spelling the compiler was given while
    /// `FileManager` standardises it, so prefix arithmetic between the two eats
    /// the middle out of the path. Going up the URL avoids the subtraction.
    private static var myStuffViewURL: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck/Views/MyStuffView.swift")
    }
}
