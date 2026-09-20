import XCTest
import SwiftUI
@testable import Bain_Luck

/// native/238 (#7036, third arm) — the sites that paint ONE team colour as text
/// resolve it through the contrast floor.
///
/// **What is left after the first two arms.** Arms 1 and 2 floored everything
/// that draws an away/home PAIR: the event page's Championship Path, the
/// Sports/My Stuff/feed row, and the Discover game card. The sites below have no
/// pair — they take a single stored `primary_color` straight into
/// `foregroundStyle` on a white card — so arm 2's funnel does not reach them and
/// they were still painting white on white:
///
///   * `DiscoverView`'s guess card prints `"\(threshold)%"` at 46-point black
///     rounded in `thresholdColor`, and its result line in `resultColor`. Both
///     were `Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")`. This is
///     the largest number on the app's default landing surface.
///   * `MyStuffView`'s merged future rows print the probability in
///     `Color(hex: item.matchedTeam?.primaryColor ?? "#6b7280")`, in both the
///     multi-source and single-source branches.
///
/// **Why the assertions are on the resolved HEX.** Same reason arm 2 recorded:
/// every character is in the view hierarchy and correct, so a test that the text
/// renders passes on the bug and VoiceOver reads the card perfectly. Only the
/// pixels are wrong. The one assertion that can fail when a call site quietly
/// goes back to passing `primaryColor` raw is an assertion about the colour.
///
/// **Why two per-surface types rather than one.** Each site already carried its
/// own default for a team with no stored colour, and those defaults differ
/// (`#2563EB` vs `#6B7280`). The floor's rule is shared
/// (`TeamTextContrast.textHexOnCard`); the default is the surface's own. Both
/// defaults are asserted to clear the floor below, because a fallback under 3:1
/// would swap one invisible colour for another and every other test here would
/// still pass.
final class TextSitesResolveTeamColourThroughTheFloor7036Tests: XCTestCase {

    private typealias C = TeamTextContrast

    /// Team names are parameters and never appended into `body`: Foundation keeps
    /// the FIRST of a duplicate JSON key, so a caller "overriding" a name by
    /// adding a second one silently asserts about the default team instead.
    private func event(homeHex: String?, awayHex: String? = "#ef2f24",
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

    // MARK: - The ship: the guess card's 46-point number

    func testTheGuessCardGivesAWhiteShirtedHomeTeamAVisibleThreshold() throws {
        let hex = GuessCardTeamTextColour.homeHex(try event(homeHex: "#ffffff"))

        XCTAssertNotEqual(hex.uppercased(), "#FFFFFF",
                          "the guess card's threshold is still painted white on the white card")
        XCTAssertTrue(C.readableOnCard(hex),
                      "threshold colour \(hex) is under the 3:1 floor — a 46pt number that cannot be read")
        XCTAssertEqual(hex, GuessCardTeamTextColour.fallbackHex,
                       "a floored colour must land on the card's OWN existing default, not a new colour")
    }

    /// The floor must not become a redesign: a club that was always legible keeps
    /// its brand colour exactly.
    func testAReadableHomeColourReachesTheGuessCardUntouched() throws {
        let hex = GuessCardTeamTextColour.homeHex(try event(homeHex: "#d11317", home: "Liverpool"))
        XCTAssertEqual(hex.uppercased(), "#D11317",
                       "Liverpool was never the problem; a floor that repaints a legible club is a redesign")
    }

    /// The card prints the HOME side's colour. Without this, swapping the call to
    /// `awayTeamData` would be a different card with every other test green.
    func testTheGuessCardPaintsTheHomeSideAndNotTheAway() throws {
        let hex = GuessCardTeamTextColour.homeHex(try event(homeHex: "#d11317", awayHex: "#ffffff"))
        XCTAssertEqual(hex.uppercased(), "#D11317",
                       "the guess card resolved the AWAY team's colour for a home-team number")
    }

    // MARK: - The ship: My Stuff's probability column

    func testMyStuffGivesAWhiteShirtedTeamAVisibleProbability() {
        let hex = MyStuffTeamColour.hex("#ffffff")

        XCTAssertNotEqual(hex.uppercased(), "#FFFFFF",
                          "the My Stuff probability is still painted white on the white row")
        XCTAssertTrue(C.readableOnCard(hex), "probability colour \(hex) is under the 3:1 floor")
        XCTAssertEqual(hex, MyStuffTeamColour.fallbackHex,
                       "a floored colour must land on the row's OWN existing default")
    }

    func testAReadableTeamColourReachesMyStuffUntouched() {
        XCTAssertEqual(MyStuffTeamColour.hex("#d11317").uppercased(), "#D11317")
    }

    // MARK: - The fallbacks, which are the part that can silently reintroduce the bug

    /// If a default were itself under the floor, every assertion above would still
    /// pass while the number stayed invisible — the floored branch would simply
    /// hand back a second unreadable colour.
    func testBothSurfaceDefaultsClearTheFloorThemselves() {
        XCTAssertTrue(C.readableOnCard(GuessCardTeamTextColour.fallbackHex),
                      "the guess card's default is under 3:1 — flooring to it changes nothing a reader can see")
        XCTAssertTrue(C.readableOnCard(MyStuffTeamColour.fallbackHex),
                      "My Stuff's default is under 3:1 — flooring to it changes nothing a reader can see")

        // Pinned, not merely "over the floor": a default nudged pale enough to
        // matter reddens here before it reaches a screen.
        XCTAssertEqual(C.contrastVsCardSurface(GuessCardTeamTextColour.fallbackHex) ?? 0, 5.17, accuracy: 0.01)
        XCTAssertEqual(C.contrastVsCardSurface(MyStuffTeamColour.fallbackHex) ?? 0, 4.83, accuracy: 0.01)
    }

    /// A colour that *looks* fine on screen tells you nothing about its ratio.
    /// Celta Vigo's `#6cace4` is a perfectly pleasant blue and is 2.43:1 — it is
    /// repainted, and the count this arm inherits is 146 clubs, not the 26 pure
    /// white ones. (native/236 wrote this test the wrong way round first and the
    /// suite caught it; kept here so the next reader does not re-guess.)
    func testAPleasantLookingPaleBlueIsStillUnderTheFloor() throws {
        XCTAssertEqual(C.contrastVsCardSurface("#6cace4") ?? 0, 2.43, accuracy: 0.01)
        XCTAssertEqual(GuessCardTeamTextColour.homeHex(try event(homeHex: "#6cace4")),
                       GuessCardTeamTextColour.fallbackHex)
        XCTAssertEqual(MyStuffTeamColour.hex("#6cace4"),
                       MyStuffTeamColour.fallbackHex)
    }

    /// Absent and unparseable both mean "no colour to judge", and both must land
    /// on the default rather than on a crash or a transparent colour.
    func testAnAbsentOrUnparseableColourLandsOnTheDefault() throws {
        XCTAssertEqual(GuessCardTeamTextColour.homeHex(try event(homeHex: nil)),
                       GuessCardTeamTextColour.fallbackHex)
        XCTAssertEqual(MyStuffTeamColour.hex(nil),
                       MyStuffTeamColour.fallbackHex)
        XCTAssertEqual(MyStuffTeamColour.hex("not a colour"),
                       MyStuffTeamColour.fallbackHex)
    }

    // MARK: - The wiring, which is the half no unit test above can reach

    /// `NativeGuessCardContent` and `TeamFuturesSection` are both file-private, so
    /// the properties that actually render cannot be called from here. These two
    /// assertions are the only thing standing between a correct helper and a call
    /// site that quietly went back to painting `primaryColor` raw — which compiles,
    /// renders, and leaves every assertion above green.
    ///
    /// 🪤 **Scoped to the TEXT forms on purpose, and that is not a hedge.** When
    /// this arm shipped, each of these files still held one raw
    /// `Color(hex: …primaryColor ?? …)` it deliberately did not touch —
    /// `DiscoverView`'s 36pt `teamBadge` tile and `MyStuffView`'s `TeamLogoView`
    /// tint — because colour-as-BACKGROUND is a different contrast question from
    /// colour-as-text, and flooring them through `usableForText` would have
    /// asserted a guarantee nobody had measured. A blanket "this file contains no
    /// raw primary_color" assertion fails on those two lines — it did, on the
    /// first run of this suite — so each anchor below is the text form
    /// specifically. Both are the exact strings mutants 1-4 of
    /// `tools/native-238-mutations-7036-text-sites.py` write back, which is what
    /// keeps them from being absences that could never occur.
    ///
    /// **Arm 4 has since answered that question** (`FillSites…7036Tests`), so the
    /// blanket form now exists there and is strictly stronger than these anchors.
    /// These stay: an anchor that names the exact rendered expression fails with a
    /// sentence about which row went raw, which a regex count cannot say. Arm 4
    /// also folded this file's `MyStuffTeamTextColour` into the one
    /// `MyStuffTeamColour` — the names below moved with it, the rule did not.
    func testTheGuessCardsRenderedPropertiesRouteThroughTheFloor() throws {
        let body = try String(contentsOf: Self.discoverViewURL, encoding: .utf8)

        XCTAssertEqual(body.components(separatedBy: "Color(hex: GuessCardTeamTextColour.homeHex(event))").count - 1, 2,
                       "both thresholdColor AND resultColor must route through the #7036 floor")
        XCTAssertFalse(body.contains("return Color(hex: event.homeTeamData?.primaryColor ?? \"#2563eb\")"),
                       "a guess-card TEXT colour is being painted from the raw primary_color again")
    }

    /// 🪤 **The anchor carries `.foregroundStyle(` for a reason that only appeared
    /// when arm 4 folded the two helpers into one.** Bare
    /// `MyStuffTeamColour.color(item.matchedTeam?.primaryColor)` now matches a
    /// THIRD site — `TeamFuturesSection`'s logo, which takes the same argument as
    /// `color:` — so the count read 3 and this test reddened on a tree where all
    /// three sites were correct. A source-scan anchor is only as specific as the
    /// spelling it happens to be unique under, and folding two helpers together is
    /// exactly the change that takes that uniqueness away. Anchoring on the
    /// rendered modifier keeps the count meaning "the two probability branches".
    func testMyStuffsProbabilityColumnRoutesThroughTheFloor() throws {
        let body = try String(contentsOf: Self.myStuffViewURL, encoding: .utf8)

        XCTAssertEqual(
            body.components(separatedBy: ".foregroundStyle(MyStuffTeamColour.color(item.matchedTeam?.primaryColor))").count - 1, 2,
            "both the multi-source and single-source branches must route through the floor")
        XCTAssertFalse(body.contains(".foregroundStyle(Color(hex: item.matchedTeam?.primaryColor ?? \"#6b7280\"))"),
                       "a My Stuff probability is being painted from the raw primary_color again")
    }

    /// Strawman: the scan reads a real file with real content, so the two
    /// `XCTAssertFalse`s above cannot be passing merely because the read failed.
    func testTheSourceScanIsReadingTheFilesItThinksItIs() throws {
        for url in [Self.discoverViewURL, Self.myStuffViewURL] {
            let body = try String(contentsOf: url, encoding: .utf8)
            XCTAssertGreaterThan(body.count, 10_000, "\(url.lastPathComponent) read back far too small")
            XCTAssertTrue(body.contains("import SwiftUI"), "\(url.lastPathComponent) is not the Swift file")
        }
    }

    /// 🪤 `#filePath` keeps the spelling the compiler was given (`/tmp/…`) while
    /// `FileManager` hands back the standardised one (`/private/tmp/…`), so any
    /// prefix arithmetic between the two silently produces a path with its middle
    /// eaten out — the failure that made 11 unrelated tree-scan classes read as
    /// product defects. Going straight up the URL avoids the subtraction entirely.
    private static var viewsDirectory: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck/Views")
    }

    private static var discoverViewURL: URL { viewsDirectory.appendingPathComponent("DiscoverView.swift") }
    private static var myStuffViewURL: URL { viewsDirectory.appendingPathComponent("MyStuffView.swift") }
}
