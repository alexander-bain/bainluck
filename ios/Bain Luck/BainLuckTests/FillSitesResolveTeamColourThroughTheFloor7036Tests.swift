import XCTest
import SwiftUI
@testable import Bain_Luck

/// native/258 (#7036, fourth and last phone arm) — the two sites that paint a
/// team colour as a SHAPE rather than as a number resolve it through the floor.
///
/// **What arm 3 left, and why it left it.** Arms 1–3 floored every site that
/// paints a team colour as a *number*. Two were deferred with an explicit
/// reason: they are "colour-as-background, a different contrast question from
/// colour-as-text — a white tile is an invisible SHAPE, not an unreadable
/// number", and flooring them through `usableForText` would have asserted a
/// guarantee nobody had measured. That was the right call to defer. This arm
/// answers it, and the answer is different for each of the two:
///
///   * `DiscoverView.matchupPanel` — a real fill. Two 36×36 tiles on the guess
///     card, one per side, standing in for crests the app could not load. For
///     Fulham (`#ffffff`) the reader gets a blank square on the app's default
///     landing surface.
///   * `MyStuffView` → `TeamLogoView(color:)` — **not a fill at all.** See
///     `testTheLogoTintIsPaintedAsTextWhichIsWhyTheTextFloorIsTheRightInstrument`
///     below: the callee paints that same argument into
///     `Text(...).foregroundStyle(color)` at full opacity. The argument is named
///     `color` and used as text.
///
/// **So neither site needed a new rule, and that is the finding.** The tile is a
/// PAIR, so it takes the pair helper arm 2 already gave the sibling Discover
/// card; the logo tint is TEXT, so it takes arm 3's text floor. The tempting
/// third option — keep the brand colour and draw a hairline boundary around an
/// invisible tile — is rejected on purpose: it is defensible in isolation and it
/// would make this card the only surface in the app answering "your colour
/// cannot be seen" differently from the three that already answer it. A fourth
/// dialect of one rule is how #7036 started.
///
/// **Why the assertions are on the resolved HEX**, restated from arm 3 because
/// it is the whole reason this class can fail: every view here renders, every
/// label is present and correct, and VoiceOver reads all of it perfectly. Only
/// the pixels are wrong. A test that the tile exists passes on the bug.
final class FillSitesResolveTeamColourThroughTheFloor7036Tests: XCTestCase {

    private typealias C = TeamTextContrast

    /// Team names are parameters and never appended into `body`: Foundation keeps
    /// the FIRST of a duplicate JSON key, so a caller "overriding" a name by
    /// adding a second one silently asserts about the default team instead.
    private func event(homeHex: String?, awayHex: String?,
                       home: String = "Fulham", away: String = "Liverpool") throws -> FeedEventData {
        func teamData(_ hex: String?) -> String {
            hex.map { "{ \"primary_color\": \"\($0)\" }" } ?? "{ }"
        }
        let json = """
        {
          "id": 15310639,
          "sport": "soccer_epl",
          "home_team": "\(home)",
          "away_team": "\(away)",
          "home_team_data": \(teamData(homeHex)),
          "away_team_data": \(teamData(awayHex))
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedEventData.self, from: Data(json.utf8))
    }

    // MARK: - The ship: the guess card's two 36pt tiles

    func testAWhiteShirtedClubGetsATileAReaderCanSee() throws {
        let hex = try GuessCardTeamTileColours.hexes(event(homeHex: "#ffffff", awayHex: "#d11317"))

        XCTAssertNotEqual(hex.home.uppercased(), "#FFFFFF",
                          "Fulham's tile is still a white square on the white guess card")
        XCTAssertTrue(C.readableOnCard(hex.home),
                      "tile colour \(hex.home) is under the 3:1 floor — a 36pt hole where a crest belongs")
    }

    /// The floor must not become a redesign: a club that was always visible keeps
    /// its brand colour exactly.
    func testTwoReadableClubsReachTheTilesUntouched() throws {
        let hex = try GuessCardTeamTileColours.hexes(event(homeHex: "#d11317", awayHex: "#132257"))
        XCTAssertEqual(hex.home.uppercased(), "#D11317", "a legible club was repainted — that is a redesign")
        XCTAssertEqual(hex.away.uppercased(), "#132257")
    }

    /// The panel draws away on the LEFT and home on the RIGHT. Without this, a
    /// call site that swapped them would be a different card with every other
    /// assertion here still green.
    func testTheTilesDoNotSwapSides() throws {
        let hex = try GuessCardTeamTileColours.hexes(event(homeHex: "#d11317", awayHex: "#132257"))
        XCTAssertEqual(hex.home.uppercased(), "#D11317", "the home tile resolved the AWAY team's colour")
        XCTAssertEqual(hex.away.uppercased(), "#132257", "the away tile resolved the HOME team's colour")
    }

    /// 🪤 **The failure a single-sided floor would have shipped.** This card draws
    /// both tiles at once, side by side. Fulham and Lyon are both `#ffffff`, so a
    /// floor that merely substituted "the default" per side would hand back the
    /// SAME colour twice and the matchup would be two identical squares — legible,
    /// and a different lie. Routing through `cardColorHexes` re-runs the palette's
    /// collision ladder on the substituted values, which is why the pair helper is
    /// the right one and a per-side `usableForText` is not.
    func testTwoWhiteShirtedClubsInOneMatchupDoNotCollapseOntoOneColour() throws {
        let hex = try GuessCardTeamTileColours.hexes(
            event(homeHex: "#ffffff", awayHex: "#ffffff", home: "Fulham", away: "Lyon"))

        XCTAssertNotEqual(hex.home.uppercased(), hex.away.uppercased(),
                          "both sides of the matchup floored onto one colour — two identical tiles")
        XCTAssertTrue(C.readableOnCard(hex.home))
        XCTAssertTrue(C.readableOnCard(hex.away))
    }

    /// 📌 The swap this arm made is only safe because the two hardcoded defaults it
    /// replaced (`#2563eb` home, `#64748b` away) are the palette's own. If someone
    /// retunes the palette, the guess card's no-colour appearance moves with it —
    /// which is correct, and is pinned here so it is a decision rather than a
    /// surprise.
    func testTheReplacedHardcodedDefaultsWereThePalettesOwn() throws {
        XCTAssertEqual(ProbabilityBarPalette.homeDefault.uppercased(), "#2563EB")
        XCTAssertEqual(ProbabilityBarPalette.awayDefault.uppercased(), "#64748B")

        let hex = try GuessCardTeamTileColours.hexes(event(homeHex: nil, awayHex: nil))
        XCTAssertEqual(hex.home.uppercased(), "#2563EB",
                       "a team with no stored colour must draw exactly what it drew before this arm")
        XCTAssertEqual(hex.away.uppercased(), "#64748B")
    }

    // MARK: - The ship: My Stuff's team logo circle

    func testAWhiteShirtedClubGetsAVisibleLogoCircleAndBadge() {
        let hex = MyStuffTeamColour.hex("#ffffff")

        XCTAssertNotEqual(hex.uppercased(), "#FFFFFF",
                          "the My Stuff logo circle and its FUL badge are still white on white")
        XCTAssertTrue(C.readableOnCard(hex), "logo colour \(hex) is under the 3:1 floor")
        XCTAssertEqual(hex, MyStuffTeamColour.fallbackHex,
                       "a floored colour must land on the row's OWN existing default, not a new colour")
    }

    func testAReadableTeamColourReachesTheLogoUntouched() {
        XCTAssertEqual(MyStuffTeamColour.hex("#d11317").uppercased(), "#D11317")
    }

    // MARK: - The fallbacks, which are the part that can silently reintroduce the bug

    /// If the default were itself under the floor, every assertion above would
    /// still pass while the badge stayed invisible — the floored branch would hand
    /// back a second unreadable colour.
    func testTheLogoDefaultClearsTheFloorItself() {
        XCTAssertTrue(C.readableOnCard(MyStuffTeamColour.fallbackHex),
                      "My Stuff's logo default is under 3:1 — flooring to it changes nothing a reader can see")
        // Pinned, not merely "over the floor": a default nudged pale enough to
        // matter reddens here before it reaches a screen.
        XCTAssertEqual(C.contrastVsCardSurface(MyStuffTeamColour.fallbackHex) ?? 0, 4.83, accuracy: 0.01)
    }

    /// A colour that *looks* fine tells you nothing about its ratio. Celta Vigo's
    /// `#6cace4` is a pleasant blue at 2.43:1, and the population this arm inherits
    /// is 146 clubs under the floor, not the 26 pure-white ones in the issue title.
    func testAPleasantLookingPaleBlueIsStillUnderTheFloor() throws {
        XCTAssertEqual(C.contrastVsCardSurface("#6cace4") ?? 0, 2.43, accuracy: 0.01)
        XCTAssertEqual(MyStuffTeamColour.hex("#6cace4"), MyStuffTeamColour.fallbackHex)
        XCTAssertNotEqual(
            try GuessCardTeamTileColours.hexes(event(homeHex: "#6cace4", awayHex: "#d11317")).home.lowercased(),
            "#6cace4")
    }

    /// Absent and unparseable both mean "no colour to judge", and both must land on
    /// the default rather than on a crash or a transparent colour.
    func testAnAbsentOrUnparseableColourLandsOnTheDefault() {
        XCTAssertEqual(MyStuffTeamColour.hex(nil), MyStuffTeamColour.fallbackHex)
        XCTAssertEqual(MyStuffTeamColour.hex("not a colour"), MyStuffTeamColour.fallbackHex)
        XCTAssertEqual(MyStuffTeamColour.hex(""), MyStuffTeamColour.fallbackHex)
    }

    /// 🪤 **The approximation this arm knowingly ships, written down as a number
    /// so it is a decision and not a bug someone finds later.**
    ///
    /// `TeamTextContrast` measures against pure white by construction
    /// (`cardSurfaceLuminance = 1.0`), but the playoff journey card sits on
    /// `Color.cardBackgroundDark` — `.tertiarySystemGroupedBackground`, about
    /// `#F2F2F7`. Against that surface every computed ratio is optimistic by
    /// ~1.12×, so the floor UNDER-flags there: a colour it calls exactly 3.0:1 is
    /// really ~2.7:1 on the card.
    ///
    /// That is the safe direction (it never repaints a club it should have left
    /// alone) and it still catches the entire reported population, which is what
    /// the second half of this test says: the white capsule this issue names is
    /// 1.12:1 on its real surface, nowhere near any plausible floor. A
    /// surface-aware floor is the honest general fix and belongs in
    /// `cardSurfaceLuminance`, not smuggled into a bug fix.
    func testTheJourneyCardsSurfaceIsNotWhiteAndTheErrorIsBoundedAndSafe() {
        let journeySurface = C.relativeLuminance("#f2f2f7")
        XCTAssertNotNil(journeySurface)
        XCTAssertEqual(journeySurface ?? 0, 0.891, accuracy: 0.005,
                       "the journey card's surface moved — re-derive the bound below")

        // How optimistic the white-surface floor is on that card.
        let optimism = (C.cardSurfaceLuminance + 0.05) / ((journeySurface ?? 0) + 0.05)
        XCTAssertEqual(optimism, 1.116, accuracy: 0.005)
        XCTAssertGreaterThan(optimism, 1.0,
                             "the error must under-flag; over-flagging would repaint legible clubs")

        // And the reported case is caught with room to spare: a white capsule on
        // that surface is ~1.12:1, so no plausible floor lets it through.
        let whiteOnJourneyCard = ((journeySurface ?? 0) + 0.05) / (1.0 + 0.05)
        XCTAssertLessThan(1 / whiteOnJourneyCard, 1.2)
    }

    // MARK: - The wiring, which is the half no unit test above can reach

    /// `matchupPanel` is a method on a file-private view, so the expression that
    /// actually renders cannot be called from here. This is the only thing standing
    /// between a correct helper and a call site that quietly went back to painting
    /// `primaryColor` raw — which compiles, renders, and leaves every assertion
    /// above green.
    func testTheGuessCardsTilesRouteThroughTheFloor() throws {
        let body = try String(contentsOf: Self.discoverViewURL, encoding: .utf8)

        XCTAssertTrue(body.contains("let tiles = GuessCardTeamTileColours.pair(event)"),
                      "matchupPanel no longer resolves its tiles through the #7036 floor")
        XCTAssertFalse(body.contains("Color(hex: event.homeTeamData?.primaryColor ?? \"#2563eb\")"),
                       "a guess-card tile is being filled from the raw primary_color again")
        XCTAssertFalse(body.contains("Color(hex: event.awayTeamData?.primaryColor ?? \"#64748b\")"),
                       "a guess-card tile is being filled from the raw primary_color again")
    }

    /// ⭐ **Four sites, and arm 3 only knew about one of them.** The two in the
    /// playoff journey card — the probability capsule and the 3pt leading stripe —
    /// key on `journey.teamColor` rather than `primaryColor`, so every search aimed
    /// at the reported spelling missed them for three arms. The capsule is the
    /// *"Relegated bar was a white capsule on a near-white track"* named in this
    /// issue's own opening paragraph. They are pinned individually here so a future
    /// arm cannot quietly drop one and still satisfy a bare count.
    func testMyStuffsFourTeamColourSitesAllRouteThroughTheFloor() throws {
        let body = try String(contentsOf: Self.myStuffViewURL, encoding: .utf8)

        XCTAssertEqual(body.components(separatedBy: "MyStuffTeamColour.color(").count - 1, 4,
                       "all four My Stuff team-colour sites must route through the floor")

        for site in ["color: MyStuffTeamColour.color(journey.teamColor)",
                     "color: MyStuffTeamColour.color(item.matchedTeam?.primaryColor)",
                     ": MyStuffTeamColour.color(journey.teamColor).opacity(0.5))",
                     ".fill(MyStuffTeamColour.color(c))"] {
            XCTAssertTrue(body.contains(site), "a My Stuff team-colour site left the floor: \(site)")
        }

        for raw in ["Color(hex: journey.teamColor ?? \"#6b7280\")",
                    "Color(hex: item.matchedTeam?.primaryColor ?? \"#6b7280\")",
                    ".fill(Color(hex: c))"] {
            XCTAssertFalse(body.contains(raw), "a My Stuff site paints the raw team colour again: \(raw)")
        }
    }

    /// ⭐ **The assertion arm 3 could not write.** Its own suite recorded that a
    /// blanket "this file paints no raw `primary_color`" check failed on exactly
    /// the two lines this arm fixes, so it had to anchor on the text forms
    /// specifically. Both files are now clean, so the blanket form is finally
    /// available — and it is strictly stronger than the four anchors above,
    /// because it also catches a *new* raw site nobody has thought of.
    ///
    /// Written as a regex over `Color(hex: …primaryColor/teamColor…)` so the
    /// floored spellings (which name a helper before the property) pass and a
    /// direct paint does not.
    func testNeitherFilePaintsATeamColourWithoutTheFloor() throws {
        let raw = try NSRegularExpression(
            pattern: #"Color\(hex:\s*(event\.\w+TeamData\?|item\.matchedTeam\?|journey)\.\w*[Cc]olor"#)

        for url in [Self.discoverViewURL, Self.myStuffViewURL] {
            let body = try String(contentsOf: url, encoding: .utf8)
            let hits = raw.numberOfMatches(in: body, range: NSRange(body.startIndex..., in: body))
            XCTAssertEqual(hits, 0,
                           "\(url.lastPathComponent) paints a stored team colour without the #7036 floor")
        }
    }

    /// 🪤 **The load-bearing fact behind using the TEXT floor at a site filed as a
    /// FILL.** `MyStuffTeamColour` hands `TeamLogoView` a colour that the
    /// callee paints as full-opacity TEXT — the badge letters that stand in for a
    /// crest — and only tints the circle behind them. If that stops being true the
    /// instrument choice should be revisited, so the fact is pinned rather than
    /// left in a comment that can quietly go stale.
    func testTheLogoTintIsPaintedAsTextWhichIsWhyTheTextFloorIsTheRightInstrument() throws {
        let body = try String(contentsOf: Self.logoViewURL, encoding: .utf8)
        XCTAssertTrue(body.contains(".foregroundStyle(color)"),
                      "TeamLogoView no longer paints its `color` as text — re-examine whether the TEXT floor is still the right rule for its callers")
    }

    /// Strawman: the scans read real files with real content, so the
    /// `XCTAssertFalse`s above cannot be passing merely because a read failed.
    func testTheSourceScanIsReadingTheFilesItThinksItIs() throws {
        for url in [Self.discoverViewURL, Self.myStuffViewURL, Self.logoViewURL] {
            let body = try String(contentsOf: url, encoding: .utf8)
            XCTAssertGreaterThan(body.count, 3_000, "\(url.lastPathComponent) read back far too small")
            XCTAssertTrue(body.contains("import SwiftUI"), "\(url.lastPathComponent) is not the Swift file")
        }
    }

    /// 🪤 `#filePath` keeps the spelling the compiler was given (`/tmp/…`) while
    /// `FileManager` hands back the standardised one (`/private/tmp/…`), so any
    /// prefix arithmetic between the two silently produces a path with its middle
    /// eaten out. Going straight up the URL avoids the subtraction entirely.
    private static var sourceRoot: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck")
    }

    private static var discoverViewURL: URL { sourceRoot.appendingPathComponent("Views/DiscoverView.swift") }
    private static var myStuffViewURL: URL { sourceRoot.appendingPathComponent("Views/MyStuffView.swift") }
    private static var logoViewURL: URL { sourceRoot.appendingPathComponent("Components/TeamLogoView.swift") }
}
